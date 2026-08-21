"""Relatório LOCAL de calibração do score de confiança (F-029 T3) — nunca decide o corte.

Replay puro sobre `review_revisions`: para cada leitura que já tem decisão HUMANA final,
compara o que a grade de shadow (`association_confidence.CONFIDENCE_THRESHOLD_GRID`, T1)
TERIA auto-decidido no instante em que essa decisão nasceu contra o que a pessoa de fato
decidiu. A tabela threshold x (auto_rate, review_rate, erro de associação, erro de leitura)
é o que instrui a escolha humana do corte operacional (gate 3 do plano da F-029); esta
ferramenta nunca aprova nem reprova nada, e nunca deveria rodar no CI — os dados que ela lê
são do stack local (Guaxindiba real + PDFs de calibração), nunca sintéticos versionados.

## Verdade e o instante da comparação

Cada revisão de `review_revisions` é uma fotografia imutável: `packet_json` (as leituras e
a decisão vigente de cada uma no momento em que a linha foi gravada), `selected_associations_json`
(a associação explícita escolhida pela pessoa, quando houve) e `confidence_shadow_json` (o que
a grade TERIA escolhido sobre esse mesmo pacote, computado por
`association_confidence.confidence_shadow_json` no MESMO instante — nunca recomputado
depois, porque recompor compararia a decisão de ontem com o score de hoje).

Uma leitura pode aparecer em várias revisões do mesmo job (o pacote inteiro viaja em cada
revisão, decisão incluída, até um ato humano novo mudar aquela leitura). A revisão em que
uma decisão "nasce" é a primeira, em ordem de versão, em que o `decision_id` daquela
leitura muda — inclusive por retificação, que sucede a decisão anterior com um id novo
(`rectifies_decision_id`). Percorrer as revisões do job em ordem crescente de versão e
guardar, por leitura, a última troca de `decision_id` observada equivale a seguir a
cadeia de retificação até a ponta: não há necessidade de indexar `rectifies_decision_id`
explicitamente, porque a ordem das revisões já é a ordem cronológica dos atos humanos.

Decisão de ATOR-MÁQUINA (`actor="system"`, ADR-0041) nunca é verdade: se a última decisão
conhecida de uma leitura ainda é do sistema, ela segue sem toque humano e fica de fora —
exatamente o texto do contrato ("decisão de sistema NUNCA é verdade").

## Por que o shadow usado é o da revisão ANTERIOR ao nascimento, não o da própria

O shadow da revisão em que a decisão nasceu já é PÓS-decisão: `packet_json` daquela linha
inclui a confirmação em si, e sinais como o componente de cadeia de `reading_confidence`
(`association_confidence._chain_component`) sobem quando a PRÓPRIA confirmação fecha uma
cadeia que antes não fechava. Comparar contra esse shadow perguntaria "o corte teria
decidido isto, sabendo o que só a pessoa decidiu?" — um viés de look-ahead que superestima
`auto_rate` e subestima erro exatamente nos cortes altos (0,9/0,95), a região onde a
escolha operacional (gate 3 do plano da F-029) importa mais. O estado honesto do que a
máquina sabia ANTES do ato humano é o shadow da revisão imediatamente anterior à do
nascimento: para uma decisão nascida em `v_n`, usa-se o shadow de `v_{n-1}`. Uma decisão
humana nunca nasce na primeira revisão do job (a revisão 1 só existe antes de qualquer
revisão humana ter acontecido), então a anterior sempre existe nesse caso; se por algum
motivo ela não existir ou não tiver `score_version` gravado, a leitura fica inelegível —
nunca é aproximada pelo shadow pós-decisão. `has_candidate` e as demais associações podem
continuar vindo da revisão de nascimento: candidatos viajam verbatim entre revisões (só a
decisão humana muda o pacote), então não há look-ahead nisso.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import RowMapping

from croquito_worker.association import AssociationSet
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.review_store import json_column

__all__ = [
    "CalibrationReport",
    "CalibrationReportError",
    "CalibrationScoreVersionReport",
    "CalibrationThresholdRow",
    "run_calibration_report",
]


class CalibrationReportError(RuntimeError):
    """No eligible data was found; nothing was written."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CalibrationThresholdRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reading_threshold: float
    association_threshold: float
    eligible_count: int = Field(ge=0)
    auto_decidable_count: int = Field(ge=0)
    auto_rate: float = Field(ge=0, le=1)
    review_rate: float = Field(ge=0, le=1)
    confirm_auto_decidable_count: int = Field(ge=0)
    association_error_count: int = Field(ge=0)
    association_error_rate: float | None = Field(default=None, ge=0, le=1)
    reading_error_count: int = Field(ge=0)
    reading_error_rate: float | None = Field(default=None, ge=0, le=1)


class CalibrationScoreVersionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score_version: str
    eligible_reading_count: int = Field(ge=0)
    rows: list[CalibrationThresholdRow]


class CalibrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs_considered: int = Field(ge=0)
    revisions_considered: int = Field(ge=0)
    readings_with_truth: int = Field(ge=0)
    score_versions: list[CalibrationScoreVersionReport]


@dataclass(frozen=True, slots=True)
class _TruthEntry:
    """A decisão humana vigente de uma leitura, presa à revisão em que ela nasceu."""

    job_key: tuple[str, str]
    reading_id: str
    action: str
    associated_proposal_id: str | None
    has_candidate: bool
    score_version: str
    shadow_decisions: list[dict[str, Any]]


@dataclass
class _ThresholdAccumulator:
    eligible_count: int = 0
    auto_decidable_count: int = 0
    confirm_auto_decidable_count: int = 0
    association_error_count: int = 0
    reading_error_count: int = 0


@dataclass
class _ScoreVersionAccumulator:
    reading_ids: set[tuple[tuple[str, str], str]] = field(default_factory=set)
    by_threshold: dict[tuple[float, float], _ThresholdAccumulator] = field(default_factory=dict)

    def threshold(self, key: tuple[float, float]) -> _ThresholdAccumulator:
        return self.by_threshold.setdefault(key, _ThresholdAccumulator())


def _load_revisions(database_url: str) -> list[RowMapping]:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT tenant_id, job_id, version, packet_json, associations_json, "
                    "selected_associations_json, confidence_shadow_json "
                    "FROM review_revisions ORDER BY tenant_id, job_id, version"
                )
            )
            .mappings()
            .all()
        )
    return list(rows)


def _birth_entries(rows: list[RowMapping]) -> list[_TruthEntry]:
    """Um `_TruthEntry` por leitura com decisão humana vigente, medida ANTES do ato.

    A associação e `has_candidate` vêm da revisão de nascimento (candidatos viajam
    verbatim entre revisões), mas o shadow comparado vem da revisão IMEDIATAMENTE
    ANTERIOR — ver a seção do docstring do módulo sobre por quê: usar o shadow da própria
    revisão de nascimento seria olhar o que o corte teria feito sabendo o resultado do
    próprio ato humano.
    """
    jobs: dict[tuple[str, str], list[RowMapping]] = {}
    for row in rows:
        jobs.setdefault((row["tenant_id"], str(row["job_id"])), []).append(row)

    entries: list[_TruthEntry] = []
    for job_key, job_rows in jobs.items():
        ordered = sorted(job_rows, key=lambda row: int(row["version"]))
        last_decision_id: dict[str, str | None] = {}
        birth_index: dict[str, int] = {}
        birth_decision: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(ordered):
            packet_data = json_column(row["packet_json"])
            for reading in packet_data.get("readings", []):
                decision = reading.get("decision")
                if decision is None:
                    continue
                reading_id = reading["id"]
                decision_id = decision.get("decision_id")
                if decision_id != last_decision_id.get(reading_id):
                    last_decision_id[reading_id] = decision_id
                    birth_index[reading_id] = index
                    birth_decision[reading_id] = decision

        for reading_id, decision in birth_decision.items():
            # Ausência do campo é decisão humana persistida antes dele existir (o default
            # do modelo pydantic é "human"); só "system" explícito exclui.
            if decision.get("actor", "human") != "human":
                # Ator-máquina nunca é verdade (ADR-0041): a leitura segue sem toque
                # humano, e não é o que este relatório mede.
                continue
            birth = birth_index[reading_id]
            if birth == 0:
                # Decisão humana "nascida" na primeira revisão do job: não deveria
                # acontecer (a revisão 1 só existe antes de qualquer revisão humana), mas
                # sem uma anterior para medir o que a máquina sabia ANTES do ato, a
                # leitura é inelegível — nunca aproximada pelo shadow pós-decisão.
                continue
            birth_row = ordered[birth]
            pre_decision_row = ordered[birth - 1]
            shadow = json_column(pre_decision_row["confidence_shadow_json"]) or {}
            score_version = shadow.get("score_version")
            if not score_version:
                # Revisão anterior sem shadow gravado (anterior à coluna, ou caminho que
                # não a preenche): ausência de registro, não elegível para calibração.
                continue
            associations = AssociationSet.model_validate(
                json_column(birth_row["associations_json"])
            )
            has_candidate = any(
                candidate.reading_id == reading_id for candidate in associations.candidates
            )
            selected_associations = json_column(birth_row["selected_associations_json"]) or {}
            entries.append(
                _TruthEntry(
                    job_key=job_key,
                    reading_id=reading_id,
                    action=decision["action"],
                    associated_proposal_id=selected_associations.get(reading_id),
                    has_candidate=has_candidate,
                    score_version=score_version,
                    shadow_decisions=shadow.get("decisions", []),
                )
            )
    return entries


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _build_report(entries: list[_TruthEntry]) -> CalibrationReport:
    by_version: dict[str, _ScoreVersionAccumulator] = {}
    for entry in entries:
        if not entry.has_candidate:
            # Sem candidato nenhum, a leitura nunca é auto-decidível em corte algum — não
            # entra no denominador de `auto_rate`, que pergunta "das que tinham a quem
            # associar, quantas o corte resolveria sozinho?" (mesmo critério da API).
            continue
        accumulator = by_version.setdefault(entry.score_version, _ScoreVersionAccumulator())
        accumulator.reading_ids.add((entry.job_key, entry.reading_id))
        for decision in entry.shadow_decisions:
            key = (float(decision["reading_threshold"]), float(decision["association_threshold"]))
            bucket = accumulator.threshold(key)
            bucket.eligible_count += 1
            auto_choice = next(
                (
                    choice
                    for choice in decision.get("auto_choices", [])
                    if choice["reading_id"] == entry.reading_id
                ),
                None,
            )
            if auto_choice is None:
                continue
            bucket.auto_decidable_count += 1
            if entry.action == "reject":
                bucket.reading_error_count += 1
            elif entry.action == "confirm":
                bucket.confirm_auto_decidable_count += 1
                if auto_choice["proposal_id"] != entry.associated_proposal_id:
                    bucket.association_error_count += 1

    score_versions: list[CalibrationScoreVersionReport] = []
    for score_version in sorted(by_version):
        accumulator = by_version[score_version]
        rows = [
            CalibrationThresholdRow(
                reading_threshold=reading_threshold,
                association_threshold=association_threshold,
                eligible_count=bucket.eligible_count,
                auto_decidable_count=bucket.auto_decidable_count,
                auto_rate=_rate(bucket.auto_decidable_count, bucket.eligible_count) or 0.0,
                review_rate=1.0
                - (_rate(bucket.auto_decidable_count, bucket.eligible_count) or 0.0),
                confirm_auto_decidable_count=bucket.confirm_auto_decidable_count,
                association_error_count=bucket.association_error_count,
                association_error_rate=_rate(
                    bucket.association_error_count, bucket.confirm_auto_decidable_count
                ),
                reading_error_count=bucket.reading_error_count,
                reading_error_rate=_rate(bucket.reading_error_count, bucket.auto_decidable_count),
            )
            for (reading_threshold, association_threshold), bucket in sorted(
                accumulator.by_threshold.items()
            )
        ]
        score_versions.append(
            CalibrationScoreVersionReport(
                score_version=score_version,
                eligible_reading_count=len(accumulator.reading_ids),
                rows=rows,
            )
        )
    return CalibrationReport(
        jobs_considered=len({entry.job_key for entry in entries}),
        revisions_considered=0,  # preenchido por `run_calibration_report`
        readings_with_truth=len(entries),
        score_versions=score_versions,
    )


_TABLE_HEADER: Final = (
    "score_version  read_thr  assoc_thr  auto_rate  review_rate  assoc_err_rate  "
    "read_err_rate  auto_n  eligible_n"
)


def _render_text_table(report: CalibrationReport) -> str:
    lines = [
        "Relatório de calibração de associação (F-029 T3) — LOCAL, nunca CI.",
        "A escolha do threshold operacional é ato humano; esta tabela só instrui.",
        "",
        f"jobs considerados: {report.jobs_considered}",
        f"leituras com verdade humana: {report.readings_with_truth}",
        "",
        _TABLE_HEADER,
        "-" * len(_TABLE_HEADER),
    ]
    for version_report in report.score_versions:
        for row in version_report.rows:
            assoc_err = (
                "n/d" if row.association_error_rate is None else f"{row.association_error_rate:.4f}"
            )
            read_err = "n/d" if row.reading_error_rate is None else f"{row.reading_error_rate:.4f}"
            lines.append(
                f"{version_report.score_version:<14} {row.reading_threshold:<8} "
                f"{row.association_threshold:<10} {row.auto_rate:<10.4f} "
                f"{row.review_rate:<12.4f} {assoc_err:<14} {read_err:<14} "
                f"{row.auto_decidable_count:<7} {row.eligible_count}"
            )
    return "\n".join(lines) + "\n"


def run_calibration_report(
    database_url: str, output_dir: Path
) -> tuple[CalibrationReport, Path, Path]:
    """Lê `review_revisions` local, monta o relatório e grava JSON + tabela texto.

    Nunca escreve em revisão nenhuma. Levanta `CalibrationReportError("NO_ELIGIBLE_DATA")`
    quando nenhuma leitura tem, ao mesmo tempo, decisão humana final e shadow gravado — o
    chamador (CLI) traduz isso em saída 2, igual a qualquer outra entrada inválida deste
    projeto.
    """
    rows = _load_revisions(database_url)
    entries = _birth_entries(rows)
    if not entries:
        raise CalibrationReportError("NO_ELIGIBLE_DATA")

    report = _build_report(entries)
    report = report.model_copy(update={"revisions_considered": len(rows)})

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "association-calibration.json"
    table_path = output_dir / "association-calibration.txt"
    atomic_write_text(
        report_path,
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )
    atomic_write_text(table_path, _render_text_table(report))
    return report, report_path, table_path
