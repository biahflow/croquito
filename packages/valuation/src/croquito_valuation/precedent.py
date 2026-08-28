"""Medição da hipótese de repetição de rótulo de legenda entre praças (F-044 T1).

Domínio puro, sem I/O de rede nem de disco: quem lê o que está gravado (CSV das tabelas
`estimate_rounds`/`estimate_round_revisions`, ou um JSON por praça) é
`croquito_worker.valuation.precedent_eval`, que monta `WorksitePrecedents` e chama
`measure_repetition`.

Esta é a PRIMEIRA e ÚNICA tarefa do primeiro Human Gate da F-044 (`feature.md`,
unknown 1): medir se um rótulo de legenda que reaparece numa praça nova reencontra o
mesmo pacote de códigos confirmados. Este módulo **mede**; ele não constrói o índice de
precedentes, não decide limiar de confiança (unknown 3 da feature) e não julga se a
hipótese está provada — isso é decisão humana posterior, sobre o número que sai daqui.

A chave do precedente é **(rótulo normalizado, fonte de preço)**, nunca o rótulo
sozinho (decisão 4 do escopo da feature): um rótulo aprendido no contrato de uma praça
não vale para outro com tabela diferente, e contar essa repetição como se fosse a mesma
coisa inflaria a métrica com um caso que a feature promete NUNCA sugerir. `price_source`
aqui é uma string opaca — este módulo não decide de onde ela vem; ver
`precedent_eval.py` para a escolha registrada (`CodeAssignment.catalog_sha256`).

As cinco estratégias de normalização (`NormalizationStrategy`) reusam, sem reimplementar,
o que já existe em `catalog.py`: `casefold` é o mesmo molde de
`bulletin_compare._normalize_label`, e `folded`/`tokens`/`stems` chamam diretamente
`catalog._lexical_normalize` (privada, mas é a normalização canônica que a T1 foi
instruída a reusar), `catalog.lexical_tokens` e `catalog.lexical_stems`.

Escopo ampliado (mesma T1, autorizado depois do primeiro corte): além da leitura do que
já está gravado no sistema (`precedent_eval.py`), uma praça real pode chegar como
planilha `.xlsx` de "memória de cálculo" — formato completamente diferente, sem
`item_id`/`CodeAssignment` nenhum. `scan_memoria_rows`/`worksite_precedents_from_memoria`,
no fim deste arquivo, interpretam esse formato — ainda em domínio puro, sobre linhas já
lidas por fora (`croquito_worker.valuation.memoria_reader` é quem abre o `.xlsx` real).
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from croquito_valuation import catalog
from croquito_valuation.errors import ValuationValidationError

MIN_WORKSITES_FOR_MEASUREMENT: Final = 2


class NormalizationStrategy(StrEnum):
    """As cinco estratégias de normalização de rótulo que a medição compara lado a lado.

    Do texto cru (`EXACT`) à normalização mais agressiva (`STEMS`, que junta singular e
    plural e as derivações mais comuns do domínio). A T1 não escolhe uma vencedora — o
    unknown 2 da feature ("como normalizar o rótulo") é decisão humana sobre o relatório
    que `measure_repetition` produz para cada uma.
    """

    EXACT = "exact"
    CASEFOLD = "casefold"
    FOLDED = "folded"
    TOKENS = "tokens"
    STEMS = "stems"


NORMALIZATION_STRATEGIES: Final[tuple[NormalizationStrategy, ...]] = tuple(NormalizationStrategy)


class PackageClassification(StrEnum):
    """Como o pacote de códigos confirmados de um rótulo repetido se compara entre praças.

    Calculada sobre TODOS os pares de praças que compartilham a chave (rótulo
    normalizado, fonte), não só o primeiro par encontrado:

    - `IDENTICAL` — o mesmo pacote em toda praça.
    - `SUBSET` — nenhum par é disjunto e, em todo par, um pacote contém o outro (uma
      cadeia por inclusão) — sem ser `IDENTICAL`.
    - `OVERLAPPING` — nenhum par é disjunto, mas ao menos um par não tem relação de
      inclusão nos dois sentidos.
    - `DISJOINT` — ao menos um par de praças não compartilha nenhum código. Vence sobre
      as outras classificações porque é o caso que mais derruba a hipótese: mostrar
      "subset" ou "overlapping" quando um par nem se cruza esconderia o pior resultado.
    """

    IDENTICAL = "identical"
    SUBSET = "subset"
    OVERLAPPING = "overlapping"
    DISJOINT = "disjoint"


def _casefold_label(label: str) -> str:
    """Espelho de `bulletin_compare._normalize_label`: espaços colapsados + casefold."""
    return " ".join(label.split()).casefold()


def normalize_label(label: str, strategy: NormalizationStrategy) -> str:
    """Rótulo normalizado sob `strategy`, reusando as normalizações de `catalog.py`."""
    if strategy is NormalizationStrategy.EXACT:
        return label
    if strategy is NormalizationStrategy.CASEFOLD:
        return _casefold_label(label)
    if strategy is NormalizationStrategy.FOLDED:
        # Reuso deliberado da normalização privada de catalog.py (ver docstring do módulo):
        # é a mesma função que decide "folded" em toda a via léxica do catálogo.
        return catalog._lexical_normalize(label)
    if strategy is NormalizationStrategy.TOKENS:
        return " ".join(catalog.lexical_tokens(label))
    if strategy is NormalizationStrategy.STEMS:
        return " ".join(catalog.lexical_stems(label))
    raise AssertionError(f"estratégia de normalização não coberta: {strategy}")  # pragma: no cover


@dataclass(frozen=True, slots=True)
class LabelObservation:
    """Uma linha de takeoff confirmada: o rótulo cru, a fonte de preço e o pacote de
    códigos confirmados que ela disparou.

    `codes` nunca é vazio: uma observação só existe quando ao menos um código foi
    confirmado (rejeitado nunca entra aqui) para aquele item, naquela fonte de preço.
    """

    label: str
    price_source: str
    codes: frozenset[str]

    def __post_init__(self) -> None:
        if not self.codes:
            raise ValuationValidationError(
                "PRECEDENT_OBSERVATION_EMPTY_PACKAGE",
                "observação de precedente exige ao menos um código confirmado",
                {"label": "<omitido: texto de cliente>", "price_source": self.price_source},
            )


@dataclass(frozen=True, slots=True)
class WorksitePrecedents:
    """O que uma praça contribui para a medição: suas observações rótulo→pacote, cruas.

    A normalização e o agrupamento por (rótulo normalizado, fonte) acontecem dentro de
    `measure_repetition`, uma vez por estratégia — estratégias diferentes agrupam
    rótulos diferentes, então agregar antes de escolher a estratégia perderia
    informação.
    """

    worksite_key: str
    observations: tuple[LabelObservation, ...]


def build_worksite_precedents(
    worksite_key: str,
    labels_by_item: Mapping[str, str],
    confirmed_codes: Sequence[tuple[str, str, str]],
) -> WorksitePrecedents:
    """Agrega confirmações `(item_id, código, fonte de preço)` em observações por rótulo.

    Um `item_id` cuja legenda não está em `labels_by_item` é ignorado — quem monta
    `confirmed_codes` (`precedent_eval.py`) já filtra e reporta essa lacuna como aviso
    nomeado; este agregador não silencia nada por conta própria, só não inventa rótulo
    para um item que não tem um.

    Os códigos de um mesmo `(rótulo, fonte)` se UNEM: duas linhas de takeoff diferentes
    com o mesmo rótulo cru e a mesma fonte, na mesma praça, contam como uma única
    observação com o pacote completo — é o que fica disponível para reencontrar depois.
    """
    grouped: dict[tuple[str, str], set[str]] = {}
    for item_id, code, price_source in confirmed_codes:
        label = labels_by_item.get(item_id)
        if label is None:
            continue
        grouped.setdefault((label, price_source), set()).add(code)
    observations = tuple(
        LabelObservation(label=label, price_source=price_source, codes=frozenset(codes))
        for (label, price_source), codes in sorted(grouped.items())
    )
    return WorksitePrecedents(worksite_key=worksite_key, observations=observations)


@dataclass(frozen=True, slots=True)
class RepeatedLabel:
    """Um rótulo (já normalizado) que aparece em duas ou mais praças, sob a mesma fonte."""

    normalized_label: str
    price_source: str
    worksite_count: int
    worksite_keys: tuple[str, ...]
    classification: PackageClassification


@dataclass(frozen=True, slots=True)
class StrategyReport:
    """A medição completa de uma estratégia de normalização, sobre o mesmo conjunto de
    praças que as outras quatro estratégias."""

    strategy: NormalizationStrategy
    worksite_count: int
    labels_per_worksite: dict[str, int]
    distinct_label_count: int
    repeated_labels: tuple[RepeatedLabel, ...]
    repetition_rate: float
    stability_rate: float | None
    """`None` quando não há nenhum rótulo repetido: taxa de estabilidade não tem
    denominador, e `0.0` mentiria dizendo "nenhum é estável" quando a resposta correta é
    "a pergunta não se aplica"."""


@dataclass(frozen=True, slots=True)
class RepetitionReport:
    """O relatório completo: uma `StrategyReport` por estratégia de normalização, sobre
    o mesmo conjunto de praças."""

    worksite_keys: tuple[str, ...]
    by_strategy: dict[NormalizationStrategy, StrategyReport]


def _classify_package(packages: Sequence[frozenset[str]]) -> PackageClassification:
    unique_packages = {frozenset(package) for package in packages}
    if len(unique_packages) == 1:
        return PackageClassification.IDENTICAL
    pairs = list(itertools.combinations(packages, 2))
    if any(not (left & right) for left, right in pairs):
        return PackageClassification.DISJOINT
    if all(left <= right or right <= left for left, right in pairs):
        return PackageClassification.SUBSET
    return PackageClassification.OVERLAPPING


def _measure_strategy(
    strategy: NormalizationStrategy, worksites: Sequence[WorksitePrecedents]
) -> StrategyReport:
    per_worksite_packages: dict[str, dict[tuple[str, str], frozenset[str]]] = {}
    for worksite in worksites:
        grouped: dict[tuple[str, str], set[str]] = {}
        for observation in worksite.observations:
            key = (normalize_label(observation.label, strategy), observation.price_source)
            grouped.setdefault(key, set()).update(observation.codes)
        per_worksite_packages[worksite.worksite_key] = {
            key: frozenset(codes) for key, codes in grouped.items()
        }

    labels_per_worksite = {
        worksite_key: len(keys) for worksite_key, keys in per_worksite_packages.items()
    }

    key_to_worksite_packages: dict[tuple[str, str], dict[str, frozenset[str]]] = {}
    for worksite_key, keys in per_worksite_packages.items():
        for key, package in keys.items():
            key_to_worksite_packages.setdefault(key, {})[worksite_key] = package

    distinct_label_count = len(key_to_worksite_packages)

    repeated: list[RepeatedLabel] = []
    for (normalized_label, price_source), packages_by_worksite in key_to_worksite_packages.items():
        if len(packages_by_worksite) < MIN_WORKSITES_FOR_MEASUREMENT:
            continue
        classification = _classify_package(list(packages_by_worksite.values()))
        repeated.append(
            RepeatedLabel(
                normalized_label=normalized_label,
                price_source=price_source,
                worksite_count=len(packages_by_worksite),
                worksite_keys=tuple(sorted(packages_by_worksite)),
                classification=classification,
            )
        )
    repeated_sorted = tuple(
        sorted(repeated, key=lambda item: (item.normalized_label, item.price_source))
    )

    repetition_rate = len(repeated_sorted) / distinct_label_count if distinct_label_count else 0.0
    identical_count = sum(
        1 for item in repeated_sorted if item.classification is PackageClassification.IDENTICAL
    )
    stability_rate = identical_count / len(repeated_sorted) if repeated_sorted else None

    return StrategyReport(
        strategy=strategy,
        worksite_count=len(worksites),
        labels_per_worksite=dict(sorted(labels_per_worksite.items())),
        distinct_label_count=distinct_label_count,
        repeated_labels=repeated_sorted,
        repetition_rate=repetition_rate,
        stability_rate=stability_rate,
    )


def measure_repetition(worksites: Sequence[WorksitePrecedents]) -> RepetitionReport:
    """Mede a repetição de rótulo entre `worksites`, sob as cinco estratégias.

    Função pura: não recomenda limiar, não decide se a hipótese está provada, só conta.
    Recusa fechada com menos de duas praças — medir repetição com uma praça só é o erro
    que uma medição anterior da feature já cometeu (`feature.md`, unknown 1) e que este
    guardrail existe para impedir em qualquer chamador, presente ou futuro.
    """
    if len(worksites) < MIN_WORKSITES_FOR_MEASUREMENT:
        raise ValuationValidationError(
            "PRECEDENT_NOT_ENOUGH_WORKSITES",
            "medição de repetição exige ao menos duas praças com precedentes",
            {
                "worksite_count": len(worksites),
                "worksite_keys": [worksite.worksite_key for worksite in worksites],
            },
        )
    by_strategy = {
        strategy: _measure_strategy(strategy, worksites) for strategy in NORMALIZATION_STRATEGIES
    }
    return RepetitionReport(
        worksite_keys=tuple(worksite.worksite_key for worksite in worksites),
        by_strategy=by_strategy,
    )


def report_to_json_dict(report: RepetitionReport) -> dict[str, object]:
    """Forma serializável e determinística de `RepetitionReport` (para `--output`)."""
    return {
        "worksite_keys": list(report.worksite_keys),
        "worksite_count": len(report.worksite_keys),
        "strategies": {
            strategy.value: _strategy_to_json_dict(strategy_report)
            for strategy, strategy_report in report.by_strategy.items()
        },
    }


def _strategy_to_json_dict(strategy_report: StrategyReport) -> dict[str, object]:
    return {
        "strategy": strategy_report.strategy.value,
        "worksite_count": strategy_report.worksite_count,
        "labels_per_worksite": dict(strategy_report.labels_per_worksite),
        "distinct_label_count": strategy_report.distinct_label_count,
        "repeated_label_count": len(strategy_report.repeated_labels),
        "repetition_rate": strategy_report.repetition_rate,
        "stability_rate": strategy_report.stability_rate,
        "repeated_labels": [
            {
                "normalized_label": item.normalized_label,
                "price_source": item.price_source,
                "worksite_count": item.worksite_count,
                "worksite_keys": list(item.worksite_keys),
                "classification": item.classification.value,
            }
            for item in strategy_report.repeated_labels
        ],
    }


# --------------------------------------------------------------------------------------
# Entrada C: memória de cálculo real (.xlsx) — formato observado, não gravado pelo sistema
# --------------------------------------------------------------------------------------
#
# Uma aba de memória de cálculo não tem `item_id`/`TakeoffItem`/`CodeAssignment` nenhum:
# item, código e rótulo são só texto em colunas fixas (1-indexadas, como a planilha
# mostra): B = item ("01.30"), C = código ("AD39050218(A)"), D = descrição do código
# NA LINHA DO BLOCO e rótulo do elemento nas linhas seguintes. Este trecho só INTERPRETA
# linhas já lidas (`Sequence[Sequence[object]]`, o formato de
# `worksheet.iter_rows(values_only=True)`) — quem abre o `.xlsx` real é
# `croquito_worker.valuation.memoria_reader.read_memoria_sheet`.

MEMORIA_ITEM_PATTERN: Final = re.compile(r"^\d{1,2}\.\d{1,3}$")
MEMORIA_CODE_PATTERN: Final = re.compile(r"^[A-Z]{2}\d{8}\(.\)$")

_MEMORIA_ITEM_COLUMN: Final = 1  # B, 0-indexado dentro da tupla de uma linha
_MEMORIA_CODE_COLUMN: Final = 2  # C
_MEMORIA_DESCRIPTION_COLUMN: Final = 3  # D


@dataclass(frozen=True, slots=True)
class MemoriaBlock:
    """Um bloco item+código de uma aba de memória de cálculo, com o rótulo achado — ou não.

    `row` é 1-indexado, como a planilha mostra, para apontar direto na aba real.
    `label` é `None` quando o bloco termina (o próximo começa, ou a aba acaba) sem que
    nenhuma linha intermediária com B e C vazias tenha trazido texto na coluna D — existe
    no dado real e é reportado, nunca descartado.
    """

    row: int
    item: str
    code: str
    label: str | None


@dataclass(frozen=True, slots=True)
class MemoriaScan:
    """Todo bloco item+código de uma aba, na ordem em que apareceram — rotulado ou não."""

    blocks: tuple[MemoriaBlock, ...]

    @property
    def labeled_blocks(self) -> tuple[MemoriaBlock, ...]:
        return tuple(block for block in self.blocks if block.label is not None)

    @property
    def unlabeled_blocks(self) -> tuple[MemoriaBlock, ...]:
        return tuple(block for block in self.blocks if block.label is None)


def _memoria_cell_text(row: Sequence[object], index: int) -> str:
    if index >= len(row):
        return ""
    value = row[index]
    if value is None:
        return ""
    return str(value).strip()


def _is_memoria_block_start(row: Sequence[object]) -> bool:
    item = _memoria_cell_text(row, _MEMORIA_ITEM_COLUMN)
    code = _memoria_cell_text(row, _MEMORIA_CODE_COLUMN)
    return bool(MEMORIA_ITEM_PATTERN.match(item) and MEMORIA_CODE_PATTERN.match(code))


def _find_memoria_label(rows: Sequence[Sequence[object]], start: int, total: int) -> str | None:
    """Primeiro texto não vazio da coluna D, nas linhas com B e C vazias, antes do
    próximo bloco começar (ou a aba acabar)."""
    index = start
    while index < total:
        row = rows[index]
        if _is_memoria_block_start(row):
            return None
        item = _memoria_cell_text(row, _MEMORIA_ITEM_COLUMN)
        code = _memoria_cell_text(row, _MEMORIA_CODE_COLUMN)
        if not item and not code:
            label = _memoria_cell_text(row, _MEMORIA_DESCRIPTION_COLUMN)
            if label:
                return label
        index += 1
    return None


def scan_memoria_rows(rows: Sequence[Sequence[object]]) -> MemoriaScan:
    """Varre `rows` (uma aba inteira, já lida) e acha todo bloco item+código.

    Pura: não abre arquivo, não sabe o que é um `.xlsx`. `rows[i]` é a linha 1-indexada
    `i + 1` da planilha.
    """
    blocks: list[MemoriaBlock] = []
    total = len(rows)
    index = 0
    while index < total:
        row = rows[index]
        if _is_memoria_block_start(row):
            item = _memoria_cell_text(row, _MEMORIA_ITEM_COLUMN)
            code = _memoria_cell_text(row, _MEMORIA_CODE_COLUMN)
            label = _find_memoria_label(rows, index + 1, total)
            blocks.append(MemoriaBlock(row=index + 1, item=item, code=code, label=label))
        index += 1
    return MemoriaScan(blocks=tuple(blocks))


def worksite_precedents_from_memoria(
    worksite_key: str, scan: MemoriaScan, price_source: str
) -> WorksitePrecedents:
    """`MemoriaScan` -> `WorksitePrecedents`, reusando `build_worksite_precedents`.

    Cada bloco ROTULADO vira um item sintético (`"row<N>"`, a linha do bloco na planilha)
    com um único código confirmado — a mesma agregação por `(rótulo, fonte)` da entrada
    A/B faz o resto: dois blocos com o mesmo rótulo, na mesma praça, unem os códigos no
    mesmo pacote N:N. Bloco sem rótulo (`scan.unlabeled_blocks`) não entra aqui; quem
    conta e reporta esses blocos é `precedent_eval.read_worksites_from_memoria`.
    """
    labels_by_item: dict[str, str] = {}
    confirmed_codes: list[tuple[str, str, str]] = []
    for block in scan.labeled_blocks:
        assert block.label is not None  # garantido por `labeled_blocks`
        item_id = f"row{block.row}"
        labels_by_item[item_id] = block.label
        confirmed_codes.append((item_id, block.code, price_source))
    return build_worksite_precedents(worksite_key, labels_by_item, confirmed_codes)
