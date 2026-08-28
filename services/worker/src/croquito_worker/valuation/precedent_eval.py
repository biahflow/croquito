"""Leitura do que já está gravado das rodadas de orçamento, para medir precedente (F-044 T1).

`croquito_valuation.precedent` é o domínio puro que mede; este módulo é a única parte do
comando que conhece o formato REAL de cada entrada — as tabelas `estimate_rounds` /
`estimate_round_revisions` exportadas em CSV (entrada A), um JSON solto por praça
(entrada B, para quando o dado chega fora do banco), ou uma planilha `.xlsx` real de
"memória de cálculo" (entrada C, escopo ampliado — a praça ainda não foi lançada no
sistema, só existe como planilha de orçamento). Nenhuma das três paga nada nem toca a
rede: são arquivos locais, e a C em especial é a mesma família de ferramenta LOCAL que
`parity`/`bulletin_compare` — fora da cadeia de medição, fora do CI, arquivo de cliente
que nunca é copiado para o repositório (muito menos para `tests/`, cujas fixtures
continuam sintéticas) e nunca é versionado.

Escolhas de leitura que ficam registradas aqui, e só aqui:

- **Revisão escolhida por rodada** (entrada A): a de MAIOR `version` que tenha
  `code_assignments_json` não vazio. `takeoff_packet_json` vem da MESMA revisão
  selecionada — nunca de uma versão diferente, porque misturar rótulo de uma versão com
  pacote de código de outra produziria um par (rótulo, código) que o orçamentista nunca
  viu junto.
- **Fonte de preço do precedente** (entradas A/B): `CodeAssignment.catalog_sha256`, não
  `PriceOrigin`. O par confirmado (`CodeAssignmentSet.assignments`,
  `assignment.py:1036-1073`) grava `catalog_sha256`, nunca `PriceOrigin` — esse enum só
  aparece em `CodeCandidate.catalog_origin` (`assignment.py:242`), do lado da SUGESTÃO,
  não da confirmação. Medir sobre o dado que a confirmação de fato grava evita inventar
  uma fonte que a leitura não sustenta. Rodada com um catálogo só (o normal da medição
  licitada — ver docstring de `CodeAssignment`) grava `catalog_sha256=None`; aqui essa
  ausência vira a string vazia (`PRICE_SOURCE_UNDECLARED`, importada de
  `croquito_valuation.precedent` desde a T2, para que a medição e o índice de precedentes
  usem o MESMO valor), uma chave válida e estável dentro da mesma execução.
- **Fonte de preço da memória de cálculo** (entrada C): a aba não grava `catalog_sha256`
  nenhum — a lista de preços é a do CONTRATO, uma só por arquivo, nunca por linha
  (`MEMORIA_PRICE_SOURCE`, string legível, nunca um hash inventado). As praças lidas por
  `--memoria` numa MESMA execução do comando compartilham essa fonte: são o mesmo pedido
  de medição, entre praças do mesmo contrato, e comparar entre fontes diferentes é
  exatamente o que a decisão 4 do escopo (chave = rótulo + fonte) existe para impedir —
  se um dia `--memoria` precisar juntar praças de contratos DIFERENTES numa mesma leitura,
  isso exige uma opção nova (`--memoria-fonte` ou parecido) que ainda não existe.

Rodada sem nenhuma revisão com `code_assignments_json`, ou cuja revisão selecionada não
tem `takeoff_packet_json`, ou cujo JSON não valida contra o contrato Pydantic, é PULADA
com um aviso nomeado (`SkippedRound`) — nunca em silêncio; o mesmo vale, na entrada C,
para o bloco item+código que termina sem rótulo (`MemoriaSourceReport.unlabeled_*`).
Entrada com menos de duas praças depois de pular o que não deu para ler é recusada
(`PRECEDENT_NOT_ENOUGH_WORKSITES`); é a mesma regra que `measure_repetition` já impõe,
replicada aqui com o detalhe de LEITURA que o domínio puro não tem como saber.

O relatório publicado (`precedent-repetition.json`) contém rótulo de legenda, que é
texto de cliente: vai para `--output` (ignorado pelo Git, retenção local de 7 dias) e
NUNCA para um log estruturado.
"""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from croquito_valuation.assignment import CodeAssignmentSet
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.precedent import (
    PRICE_SOURCE_UNDECLARED,
    RepetitionReport,
    WorksitePrecedents,
    build_worksite_precedents,
    measure_repetition,
    report_to_json_dict,
    worksite_precedents_from_memoria,
)
from croquito_valuation.takeoff import TakeoffPacket
from croquito_worker.io_utils import atomic_write_text
from croquito_worker.valuation.memoria_reader import read_memoria_sheet

MEMORIA_PRICE_SOURCE: Final = "memoria-xlsx:lista-de-precos-do-contrato"
"""Fonte de preço única para toda leitura `--memoria` de uma execução (ver docstring do
módulo): não é um hash, é um rótulo legível — a aba de memória de cálculo não grava
`catalog_sha256`, e inventar um seria pior que declarar a limitação."""

REVISION_SELECTION_NOTE: Final = (
    "entrada A (estimate_rounds/estimate_round_revisions): por rodada, a revisão usada é "
    "a de MAIOR version que tenha code_assignments_json não vazio; takeoff_packet_json "
    "vem da MESMA revisão selecionada"
)

DIRECTORY_SELECTION_NOTE: Final = (
    "entrada B (--revision-dir): um JSON por praça, com worksite_key/takeoff_packet/"
    "code_assignments já resolvidos — não há seleção de versão nesta entrada"
)

MEMORIA_SELECTION_NOTE: Final = (
    "entrada C (--memoria): bloco = linha em que a coluna B casa item e a C casa código; "
    "rótulo = primeiro texto não vazio da coluna D nas linhas seguintes com B e C vazias, "
    "até o próximo bloco começar; bloco sem rótulo é contado e pulado, nunca descartado "
    "em silêncio; fonte de preço única desta leitura: " + MEMORIA_PRICE_SOURCE
)

REPORT_FILENAME: Final = "precedent-repetition.json"

REASON_NO_CONFIRMED_ASSIGNMENTS: Final = "NO_CONFIRMED_ASSIGNMENTS"
"""Nenhuma revisão da rodada tem `code_assignments_json` não vazio."""

REASON_NO_TAKEOFF_PACKET: Final = "NO_TAKEOFF_PACKET"
"""A revisão selecionada (maior version com assignments) não tem `takeoff_packet_json`."""

REASON_UNREADABLE_TAKEOFF_PACKET: Final = "UNREADABLE_TAKEOFF_PACKET"
"""`takeoff_packet_json` presente mas não valida contra `TakeoffPacket`."""

REASON_UNREADABLE_CODE_ASSIGNMENTS: Final = "UNREADABLE_CODE_ASSIGNMENTS"
"""`code_assignments_json` presente mas não valida contra `CodeAssignmentSet`."""

REASON_MISSING_WORKSITE_KEY: Final = "MISSING_WORKSITE_KEY"
"""Entrada B: o JSON da praça não declara `worksite_key`."""


@dataclass(frozen=True, slots=True)
class SkippedRound:
    """Uma rodada/praça que não entrou na medição, e por quê — nunca em silêncio.

    `source` é o `round_id` na entrada A (CSV) ou o nome do arquivo na entrada B
    (diretório) — o identificador que a entrada correspondente de fato tem.
    """

    source: str
    worksite_key: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class MemoriaSourceReport:
    """O que a leitura de um `<arquivo>:<aba>` (entrada C) encontrou.

    `unlabeled_block_rows` é a lista de linhas (1-indexadas) dos blocos sem rótulo —
    achado nomeado, não silenciado; `distinct_label_count` conta rótulos CRUS distintos
    (sem normalização: a normalização por estratégia é obra de `measure_repetition`).
    """

    path: str
    sheet: str
    worksite_key: str
    price_source: str
    block_count: int
    labeled_block_count: int
    unlabeled_block_count: int
    unlabeled_block_rows: tuple[int, ...]
    distinct_label_count: int


@dataclass(frozen=True, slots=True)
class PrecedentEvalReport:
    """O que a leitura produziu: praças usadas, praças puladas e a medição sobre as usadas.

    `memoria_sources` só é preenchido na entrada C; nas entradas A/B fica vazio.
    """

    worksites_used: tuple[str, ...]
    skipped: tuple[SkippedRound, ...]
    selection_note: str
    repetition: RepetitionReport
    memoria_sources: tuple[MemoriaSourceReport, ...] = ()


def _ensure_csv_field_limit() -> None:
    """O `code_assignments_json`/`takeoff_packet_json` reais passam de 1MB por linha —
    bem acima do limite padrão do módulo `csv` (128KB), que rejeitaria a leitura real."""
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:  # pragma: no cover - depende do tamanho de C long da plataforma
        csv.field_size_limit(2**31 - 1)


def _parse_json_cell(value: str) -> object | None:
    """`None` para célula ausente (`""`) ou nula (`"null"`); o objeto decodificado senão.

    Um objeto "vazio" decodificado (`{}`/`[]`/`0`/`false`) também vira `None`: nenhuma
    dessas formas é um `TakeoffPacket`/`CodeAssignmentSet` válido, e tratar como ausente
    é mais correto do que deixar a validação do Pydantic falhar com uma mensagem que
    não fala desta camada de leitura.
    """
    if not value or not value.strip():
        return None
    parsed: object = json.loads(value)
    if not parsed:
        return None
    return parsed


def _build_precedents(
    worksite_key: str, packet: TakeoffPacket, assignments: CodeAssignmentSet
) -> WorksitePrecedents:
    labels_by_item = {item.id: item.label for item in packet.items}
    confirmed_codes: list[tuple[str, str, str]] = []
    for assignment in assignments.assignments:
        if assignment.status != "confirmed" or assignment.code is None:
            continue
        price_source = assignment.catalog_sha256 or PRICE_SOURCE_UNDECLARED
        confirmed_codes.append((assignment.item_id, assignment.code, price_source))
    return build_worksite_precedents(worksite_key, labels_by_item, confirmed_codes)


def read_worksites_from_rounds_csv(
    rounds_path: Path, revisions_path: Path
) -> tuple[list[WorksitePrecedents], list[SkippedRound]]:
    """Entrada A: `estimate_rounds.csv` + `estimate_round_revisions.csv`, no formato
    exato do export das tabelas (colunas `id`/`worksite_key` e
    `round_id`/`version`/`takeoff_packet_json`/`code_assignments_json`)."""
    _ensure_csv_field_limit()

    with rounds_path.open(newline="", encoding="utf-8") as handle:
        rounds = {row["id"]: row["worksite_key"] for row in csv.DictReader(handle)}

    revisions_by_round: dict[str, list[dict[str, str]]] = {}
    with revisions_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            revisions_by_round.setdefault(row["round_id"], []).append(row)

    worksites: list[WorksitePrecedents] = []
    skipped: list[SkippedRound] = []

    for round_id, worksite_key in rounds.items():
        revisions = sorted(
            revisions_by_round.get(round_id, ()),
            key=lambda row: int(row["version"]),
            reverse=True,
        )
        selected_row: dict[str, str] | None = None
        selected_assignments_raw: object | None = None
        for row in revisions:
            parsed = _parse_json_cell(row["code_assignments_json"])
            if parsed is not None:
                selected_row, selected_assignments_raw = row, parsed
                break

        if selected_row is None or selected_assignments_raw is None:
            skipped.append(SkippedRound(round_id, worksite_key, REASON_NO_CONFIRMED_ASSIGNMENTS))
            continue

        parsed_packet = _parse_json_cell(selected_row["takeoff_packet_json"])
        if parsed_packet is None:
            skipped.append(SkippedRound(round_id, worksite_key, REASON_NO_TAKEOFF_PACKET))
            continue

        try:
            packet = TakeoffPacket.model_validate(parsed_packet)
        except ValidationError:
            skipped.append(SkippedRound(round_id, worksite_key, REASON_UNREADABLE_TAKEOFF_PACKET))
            continue

        try:
            assignments = CodeAssignmentSet.model_validate(selected_assignments_raw)
        except ValidationError:
            skipped.append(SkippedRound(round_id, worksite_key, REASON_UNREADABLE_CODE_ASSIGNMENTS))
            continue

        worksites.append(_build_precedents(worksite_key, packet, assignments))

    return worksites, skipped


def read_worksites_from_revision_dir(
    directory: Path,
) -> tuple[list[WorksitePrecedents], list[SkippedRound]]:
    """Entrada B: um JSON por praça em `directory`, cada um com `worksite_key`,
    `takeoff_packet` e `code_assignments` — para quando o dado chega fora do banco."""
    worksites: list[WorksitePrecedents] = []
    skipped: list[SkippedRound] = []

    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        worksite_key = payload.get("worksite_key")
        if not worksite_key:
            skipped.append(SkippedRound(path.name, None, REASON_MISSING_WORKSITE_KEY))
            continue

        raw_packet = payload.get("takeoff_packet")
        if not raw_packet:
            skipped.append(SkippedRound(path.name, worksite_key, REASON_NO_TAKEOFF_PACKET))
            continue

        raw_assignments = payload.get("code_assignments")
        if not raw_assignments:
            skipped.append(SkippedRound(path.name, worksite_key, REASON_NO_CONFIRMED_ASSIGNMENTS))
            continue

        try:
            packet = TakeoffPacket.model_validate(raw_packet)
        except ValidationError:
            skipped.append(SkippedRound(path.name, worksite_key, REASON_UNREADABLE_TAKEOFF_PACKET))
            continue

        try:
            assignments = CodeAssignmentSet.model_validate(raw_assignments)
        except ValidationError:
            skipped.append(
                SkippedRound(path.name, worksite_key, REASON_UNREADABLE_CODE_ASSIGNMENTS)
            )
            continue

        worksites.append(_build_precedents(worksite_key, packet, assignments))

    return worksites, skipped


def parse_memoria_spec(raw: str) -> tuple[Path, str]:
    """`<arquivo.xlsx>:<aba>` -> `(Path, aba)`.

    Separa no ÚLTIMO `:` — caminho absoluto em macOS/Linux nunca leva `:`, então a aba
    pode conter qualquer caractere exceto `:`. Espec malformada (sem separador, caminho
    vazio ou aba vazia) é recusa fechada nomeada, nunca um `IndexError` cru.
    """
    path_text, separator, sheet_name = raw.rpartition(":")
    if not separator or not path_text or not sheet_name:
        raise ValuationValidationError(
            "PRECEDENT_MEMORIA_SPEC_INVALID",
            "--memoria exige o formato <arquivo.xlsx>:<nome da aba>",
            {"value": raw},
        )
    return Path(path_text), sheet_name


def read_worksites_from_memoria(
    specs: Sequence[str],
) -> tuple[list[WorksitePrecedents], list[MemoriaSourceReport]]:
    """Entrada C: um `--memoria <arquivo.xlsx>:<aba>` por praça, repetível.

    Cada arquivo:aba vira uma `WorksitePrecedents` (chave = nome do arquivo + aba, para
    não colidir se duas praças usarem o mesmo nome de aba) sob `MEMORIA_PRICE_SOURCE`,
    a fonte única desta leitura (ver docstring do módulo). Bloco sem rótulo não é
    descartado: fica fora da medição, mas é contado em `MemoriaSourceReport`.
    """
    worksites: list[WorksitePrecedents] = []
    sources: list[MemoriaSourceReport] = []
    for raw in specs:
        path, sheet_name = parse_memoria_spec(raw)
        scan = read_memoria_sheet(path, sheet_name)
        worksite_key = f"{path.name}::{sheet_name}"
        worksites.append(worksite_precedents_from_memoria(worksite_key, scan, MEMORIA_PRICE_SOURCE))
        sources.append(
            MemoriaSourceReport(
                path=str(path),
                sheet=sheet_name,
                worksite_key=worksite_key,
                price_source=MEMORIA_PRICE_SOURCE,
                block_count=len(scan.blocks),
                labeled_block_count=len(scan.labeled_blocks),
                unlabeled_block_count=len(scan.unlabeled_blocks),
                unlabeled_block_rows=tuple(block.row for block in scan.unlabeled_blocks),
                distinct_label_count=len(
                    {block.label for block in scan.labeled_blocks if block.label is not None}
                ),
            )
        )
    return worksites, sources


def _skipped_to_json_dict(item: SkippedRound) -> dict[str, object]:
    return {"source": item.source, "worksite_key": item.worksite_key, "reason": item.reason}


def _memoria_source_to_json_dict(item: MemoriaSourceReport) -> dict[str, object]:
    return {
        "path": item.path,
        "sheet": item.sheet,
        "worksite_key": item.worksite_key,
        "price_source": item.price_source,
        "block_count": item.block_count,
        "labeled_block_count": item.labeled_block_count,
        "unlabeled_block_count": item.unlabeled_block_count,
        "unlabeled_block_rows": list(item.unlabeled_block_rows),
        "distinct_label_count": item.distinct_label_count,
    }


def precedent_eval_report_to_json_dict(report: PrecedentEvalReport) -> dict[str, object]:
    """Forma serializável e determinística de `PrecedentEvalReport` (para `--output`)."""
    return {
        "selection_note": report.selection_note,
        "worksites_used": list(report.worksites_used),
        "worksite_count": len(report.worksites_used),
        "skipped": [_skipped_to_json_dict(item) for item in report.skipped],
        "skipped_count": len(report.skipped),
        "memoria_sources": [_memoria_source_to_json_dict(item) for item in report.memoria_sources],
        "repetition": report_to_json_dict(report.repetition),
    }


def _serialize(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def run_precedent_eval(
    *,
    rounds_path: Path | None,
    revisions_path: Path | None,
    revision_dir: Path | None,
    memoria: Sequence[str] = (),
    output_dir: Path,
) -> tuple[PrecedentEvalReport, Path]:
    """Lê o que já está gravado, mede a repetição e publica `precedent-repetition.json`.

    Exige exatamente UMA das três entradas: `--rounds`+`--revisions` (A), `--revision-dir`
    (B) ou `--memoria` (C, uma ou mais vezes). Recusa fechada e nada é publicado quando,
    depois de pular o que não deu para ler, sobra menos de duas praças
    (`PRECEDENT_NOT_ENOUGH_WORKSITES`) — medir repetição com uma praça só é o erro que
    uma medição anterior da feature já cometeu (`feature.md`, unknown 1).
    """
    if (rounds_path is None) != (revisions_path is None):
        raise ValuationValidationError(
            "PRECEDENT_INPUT_INCOMPLETE",
            "--rounds e --revisions são exigidos juntos, na entrada A",
            {"rounds": str(rounds_path), "revisions": str(revisions_path)},
        )
    has_csv_input = rounds_path is not None
    has_dir_input = revision_dir is not None
    has_memoria_input = bool(memoria)
    active_input_count = sum([has_csv_input, has_dir_input, has_memoria_input])
    if active_input_count != 1:
        raise ValuationValidationError(
            "PRECEDENT_INPUT_AMBIGUOUS",
            "informe exatamente uma entrada: --rounds/--revisions (A), --revision-dir (B) "
            "ou --memoria (C) — nunca mais de uma nem nenhuma",
            {
                "has_csv_input": has_csv_input,
                "has_dir_input": has_dir_input,
                "has_memoria_input": has_memoria_input,
            },
        )

    worksites: list[WorksitePrecedents]
    skipped: list[SkippedRound] = []
    memoria_sources: list[MemoriaSourceReport] = []
    if has_csv_input:
        assert rounds_path is not None and revisions_path is not None  # garantido acima
        worksites, skipped = read_worksites_from_rounds_csv(rounds_path, revisions_path)
        selection_note = REVISION_SELECTION_NOTE
    elif has_dir_input:
        assert revision_dir is not None  # narrow para o mypy: garantido pelo XOR acima
        worksites, skipped = read_worksites_from_revision_dir(revision_dir)
        selection_note = DIRECTORY_SELECTION_NOTE
    else:
        worksites, memoria_sources = read_worksites_from_memoria(memoria)
        selection_note = MEMORIA_SELECTION_NOTE

    if len(worksites) < 2:
        raise ValuationValidationError(
            "PRECEDENT_NOT_ENOUGH_WORKSITES",
            "medição de repetição exige ao menos duas praças com precedentes; a leitura "
            "encontrou menos",
            {
                "worksite_count": len(worksites),
                "worksite_keys": [worksite.worksite_key for worksite in worksites],
                "skipped": [_skipped_to_json_dict(item) for item in skipped],
                "memoria_sources": [_memoria_source_to_json_dict(item) for item in memoria_sources],
            },
        )

    repetition = measure_repetition(worksites)
    report = PrecedentEvalReport(
        worksites_used=tuple(worksite.worksite_key for worksite in worksites),
        skipped=tuple(skipped),
        selection_note=selection_note,
        repetition=repetition,
        memoria_sources=tuple(memoria_sources),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / REPORT_FILENAME
    atomic_write_text(report_path, _serialize(precedent_eval_report_to_json_dict(report)))
    return report, report_path


def summary_text(report: PrecedentEvalReport) -> str:
    """Resumo legível para stdout — PODE conter rótulo de legenda (texto de cliente);
    nunca vai para log estruturado, só para o terminal de quem rodou o comando."""
    lines = [
        f"praças usadas: {len(report.worksites_used)} ({', '.join(report.worksites_used)})",
        f"praças puladas: {len(report.skipped)}",
    ]
    for item in report.skipped:
        worksite_label = item.worksite_key or "sem worksite_key"
        lines.append(f"  - {item.source} ({worksite_label}): {item.reason}")
    for source in report.memoria_sources:
        lines.append(
            f"  memória {source.path} :: {source.sheet} — blocos={source.block_count} "
            f"rotulados={source.labeled_block_count} sem_rotulo={source.unlabeled_block_count} "
            f"linhas_sem_rotulo={list(source.unlabeled_block_rows)}"
        )
    lines.append(f"seleção de leitura: {report.selection_note}")
    for strategy, strategy_report in report.repetition.by_strategy.items():
        stability = (
            "n/a"
            if strategy_report.stability_rate is None
            else f"{strategy_report.stability_rate:.1%}"
        )
        lines.append(
            f"[{strategy.value}] rótulos distintos={strategy_report.distinct_label_count} "
            f"repetidos={len(strategy_report.repeated_labels)} "
            f"repetição={strategy_report.repetition_rate:.1%} estabilidade={stability}"
        )
        for repeated in strategy_report.repeated_labels:
            price_source = repeated.price_source or "<sem fonte>"
            lines.append(
                f'    - "{repeated.normalized_label}" (fonte={price_source}) '
                f"praças={repeated.worksite_count} pacote={repeated.classification.value}"
            )
    return "\n".join(lines)
