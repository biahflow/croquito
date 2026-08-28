"""Medição da hipótese de repetição de rótulo de legenda entre praças (F-044 T1).

As fixtures cobrem, de propósito, os quatro casos que a medição precisa distinguir
(ver `docs/features/F-044-precedente-de-codigo/tasks/T1-medir-a-repeticao.md`): rótulo
idêntico com pacote idêntico, rótulo que só reaparece após normalização, rótulo igual
com pacotes diferentes (o caso que derruba a hipótese) e mesmo rótulo em fontes de preço
diferentes, que NUNCA conta como repetição.

A segunda metade (`scan_memoria_rows`/`worksite_precedents_from_memoria`) cobre o
escopo ampliado da mesma T1 — a leitura de linhas de uma aba de memória de cálculo real
(entrada C). Sintéticas de propósito: nenhum dado das planilhas reais entra em `tests/`.

A terceira metade é da T2: o contrato do `PrecedentSeedPacket`, que atravessa a fronteira
HTTP entre a extração local e a ingestão do índice de precedentes. Ele mora neste módulo
porque as duas pontas precisam do MESMO contrato, e um contrato escrito duas vezes
divergiria.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.precedent import (
    NORMALIZATION_STRATEGIES,
    PRICE_SOURCE_UNDECLARED,
    LabelObservation,
    MemoriaBlock,
    NormalizationStrategy,
    PackageClassification,
    PrecedentSeedPacket,
    WorksitePrecedents,
    build_worksite_precedents,
    measure_repetition,
    normalize_label,
    report_to_json_dict,
    scan_memoria_rows,
    worksite_precedents_from_memoria,
)


def _worksite(worksite_key: str, *observations: LabelObservation) -> WorksitePrecedents:
    return WorksitePrecedents(worksite_key=worksite_key, observations=tuple(observations))


def _obs(label: str, price_source: str, *codes: str) -> LabelObservation:
    return LabelObservation(label=label, price_source=price_source, codes=frozenset(codes))


# --------------------------------------------------------------------------------------
# normalize_label: as cinco estratégias, isoladas
# --------------------------------------------------------------------------------------


def test_exact_preserves_the_raw_text() -> None:
    assert normalize_label("  Piso   EM Concreto  ", NormalizationStrategy.EXACT) == (
        "  Piso   EM Concreto  "
    )


def test_casefold_collapses_case_and_whitespace_but_not_accent() -> None:
    assert (
        normalize_label("Alambrado  Do Campo", NormalizationStrategy.CASEFOLD)
        == "alambrado do campo"
    )
    assert normalize_label("Área", NormalizationStrategy.CASEFOLD) == "área"


def test_folded_also_strips_accent() -> None:
    assert normalize_label("Área de Intervenção", NormalizationStrategy.FOLDED) == (
        "area de intervencao"
    )


def test_tokens_and_stems_reuse_catalog_normalization() -> None:
    assert normalize_label("Gramados intertravados", NormalizationStrategy.TOKENS) == (
        "gramados intertravados"
    )
    assert normalize_label("Gramados intertravados", NormalizationStrategy.STEMS) == (
        "grama intertrava"
    )


# --------------------------------------------------------------------------------------
# build_worksite_precedents: agregação item -> observação
# --------------------------------------------------------------------------------------


def test_build_worksite_precedents_unions_codes_of_the_same_label_and_source() -> None:
    precedents = build_worksite_precedents(
        "praca-a",
        labels_by_item={"ti_0000000000000001": "PISO EM CONCRETO"},
        confirmed_codes=[
            ("ti_0000000000000001", "BP09100050(B)", "cat-1"),
            ("ti_0000000000000001", "ET39050109(/)", "cat-1"),
        ],
    )
    assert precedents.worksite_key == "praca-a"
    assert len(precedents.observations) == 1
    observation = precedents.observations[0]
    assert observation.label == "PISO EM CONCRETO"
    assert observation.price_source == "cat-1"
    assert observation.codes == frozenset({"BP09100050(B)", "ET39050109(/)"})


def test_build_worksite_precedents_ignores_items_without_a_known_label() -> None:
    precedents = build_worksite_precedents(
        "praca-a",
        labels_by_item={"ti_0000000000000001": "PISO EM CONCRETO"},
        confirmed_codes=[("ti_desconhecido", "X001", "cat-1")],
    )
    assert precedents.observations == ()


def test_label_observation_refuses_an_empty_package() -> None:
    with pytest.raises(ValuationValidationError) as excinfo:
        LabelObservation(label="PISO EM CONCRETO", price_source="cat-1", codes=frozenset())
    assert excinfo.value.code == "PRECEDENT_OBSERVATION_EMPTY_PACKAGE"


# --------------------------------------------------------------------------------------
# measure_repetition: os quatro casos que a medição precisa distinguir
# --------------------------------------------------------------------------------------


def test_identical_label_and_identical_package_is_identical_and_stable() -> None:
    worksites = [
        _worksite("praca-a", _obs("PISO EM CONCRETO", "cat-1", "BP09100050(B)", "ET39050109(/)")),
        _worksite("praca-b", _obs("PISO EM CONCRETO", "cat-1", "BP09100050(B)", "ET39050109(/)")),
    ]

    report = measure_repetition(worksites)

    strategy_report = report.by_strategy[NormalizationStrategy.EXACT]
    assert strategy_report.distinct_label_count == 1
    assert len(strategy_report.repeated_labels) == 1
    repeated = strategy_report.repeated_labels[0]
    assert repeated.normalized_label == "PISO EM CONCRETO"
    assert repeated.price_source == "cat-1"
    assert repeated.worksite_count == 2
    assert repeated.worksite_keys == ("praca-a", "praca-b")
    assert repeated.classification is PackageClassification.IDENTICAL
    assert strategy_report.repetition_rate == 1.0
    assert strategy_report.stability_rate == 1.0


def test_label_reappears_only_after_normalization() -> None:
    """Dois pares, cada um convergindo numa estratégia diferente: o par de
    caixa/espaço duplo só converge a partir de `casefold` (que colapsa espaço) — e só
    volta a convergir em `tokens`/`stems`, que também colapsam espaço via tokenização;
    `folded` só normaliza acento, não espaço, então esse par continua distinto ali. O
    par de acento só converge a partir de `folded` (que remove acento via NFKD).
    `exact` não vê repetição nenhuma."""
    worksites = [
        _worksite(
            "praca-a",
            _obs("Alambrado  Do Campo", "cat-1", "X001"),
            _obs("Área de Intervenção", "cat-1", "X002"),
        ),
        _worksite(
            "praca-b",
            _obs("alambrado do campo", "cat-1", "X001"),
            _obs("AREA DE INTERVENCAO", "cat-1", "X002"),
        ),
    ]

    report = measure_repetition(worksites)

    exact = report.by_strategy[NormalizationStrategy.EXACT]
    assert exact.repeated_labels == ()
    assert exact.distinct_label_count == 4
    assert exact.repetition_rate == 0.0
    assert exact.stability_rate is None

    casefold = report.by_strategy[NormalizationStrategy.CASEFOLD]
    casefold_labels = {item.normalized_label for item in casefold.repeated_labels}
    assert casefold_labels == {"alambrado do campo"}
    assert casefold.distinct_label_count == 3  # o par de acento ainda não convergiu

    folded = report.by_strategy[NormalizationStrategy.FOLDED]
    folded_labels = {item.normalized_label for item in folded.repeated_labels}
    assert folded_labels == {"area de intervencao"}
    assert folded.distinct_label_count == 3  # o par de espaço duplo ainda não convergiu

    for strategy in (NormalizationStrategy.TOKENS, NormalizationStrategy.STEMS):
        strategy_report = report.by_strategy[strategy]
        assert len(strategy_report.repeated_labels) == 2
        assert strategy_report.distinct_label_count == 2
        assert strategy_report.stability_rate == 1.0


def test_same_label_different_package_is_the_hypothesis_breaking_case() -> None:
    worksites = [
        _worksite("praca-a", _obs("TELA DE ARAME", "cat-1", "A", "B")),
        _worksite("praca-b", _obs("TELA DE ARAME", "cat-1", "B", "C")),
    ]

    report = measure_repetition(worksites)
    repeated = report.by_strategy[NormalizationStrategy.EXACT].repeated_labels
    assert len(repeated) == 1
    assert repeated[0].classification is PackageClassification.OVERLAPPING


def test_subset_package_classification() -> None:
    worksites = [
        _worksite("praca-a", _obs("TELA DE ARAME", "cat-1", "A", "B", "C")),
        _worksite("praca-b", _obs("TELA DE ARAME", "cat-1", "A", "B")),
    ]

    report = measure_repetition(worksites)
    repeated = report.by_strategy[NormalizationStrategy.EXACT].repeated_labels
    assert repeated[0].classification is PackageClassification.SUBSET


def test_disjoint_wins_over_subset_when_a_third_worksite_shares_nothing() -> None:
    worksites = [
        _worksite("praca-a", _obs("TELA DE ARAME", "cat-1", "A", "B")),
        _worksite("praca-b", _obs("TELA DE ARAME", "cat-1", "A", "B")),
        _worksite("praca-c", _obs("TELA DE ARAME", "cat-1", "C")),
    ]

    report = measure_repetition(worksites)
    repeated = report.by_strategy[NormalizationStrategy.EXACT].repeated_labels
    assert len(repeated) == 1
    assert repeated[0].worksite_count == 3
    assert repeated[0].classification is PackageClassification.DISJOINT


def test_same_label_different_price_source_is_never_counted_as_repetition() -> None:
    worksites = [
        _worksite("praca-a", _obs("PISO EM CONCRETO", "cat-1", "X001")),
        _worksite("praca-b", _obs("PISO EM CONCRETO", "cat-2", "X001")),
    ]

    report = measure_repetition(worksites)

    for strategy in NORMALIZATION_STRATEGIES:
        strategy_report = report.by_strategy[strategy]
        assert strategy_report.repeated_labels == ()
        assert strategy_report.distinct_label_count == 2
        assert strategy_report.repetition_rate == 0.0
        assert strategy_report.stability_rate is None


# --------------------------------------------------------------------------------------
# recusa e determinismo
# --------------------------------------------------------------------------------------


def test_refuses_with_fewer_than_two_worksites() -> None:
    worksites = [_worksite("praca-a", _obs("PISO EM CONCRETO", "cat-1", "X001"))]

    with pytest.raises(ValuationValidationError) as excinfo:
        measure_repetition(worksites)

    assert excinfo.value.code == "PRECEDENT_NOT_ENOUGH_WORKSITES"
    assert excinfo.value.details["worksite_count"] == 1


def test_refuses_with_zero_worksites() -> None:
    with pytest.raises(ValuationValidationError) as excinfo:
        measure_repetition([])

    assert excinfo.value.code == "PRECEDENT_NOT_ENOUGH_WORKSITES"
    assert excinfo.value.details["worksite_count"] == 0


def test_measurement_is_byte_deterministic() -> None:
    def _build() -> list[WorksitePrecedents]:
        return [
            _worksite(
                "praca-a", _obs("PISO EM CONCRETO", "cat-1", "BP09100050(B)", "ET39050109(/)")
            ),
            _worksite(
                "praca-b", _obs("PISO EM CONCRETO", "cat-1", "BP09100050(B)", "ET39050109(/)")
            ),
        ]

    first = json.dumps(report_to_json_dict(measure_repetition(_build())), sort_keys=True)
    second = json.dumps(report_to_json_dict(measure_repetition(_build())), sort_keys=True)
    assert first == second


# --------------------------------------------------------------------------------------
# scan_memoria_rows / worksite_precedents_from_memoria: entrada C (memória de cálculo)
# --------------------------------------------------------------------------------------


def _row(
    item: str | None = None, code: str | None = None, desc: str | None = None
) -> tuple[str | None, str | None, str | None, str | None]:
    """Uma linha sintética de aba de memória: (A vazio, B=item, C=código, D=descrição)."""
    return (None, item, code, desc)


def test_memoria_patterns_match_the_documented_real_examples() -> None:
    from croquito_valuation.precedent import MEMORIA_CODE_PATTERN, MEMORIA_ITEM_PATTERN

    assert MEMORIA_ITEM_PATTERN.match("01.30")
    assert MEMORIA_ITEM_PATTERN.match("1.5")
    assert MEMORIA_ITEM_PATTERN.match("12.345")
    assert not MEMORIA_ITEM_PATTERN.match("1.5.2")
    assert MEMORIA_CODE_PATTERN.match("AD39050218(A)")
    assert not MEMORIA_CODE_PATTERN.match("ad39050218(a)")
    assert not MEMORIA_CODE_PATTERN.match("AD3905021(A)")


def test_scan_memoria_finds_the_block_and_the_label_after_it() -> None:
    rows = [
        _row(item="01.30", code="AD39050218(A)", desc="descrição do código"),
        _row(),
        _row(desc="VIGIA"),
    ]

    scan = scan_memoria_rows(rows)

    assert scan.blocks == (MemoriaBlock(row=1, item="01.30", code="AD39050218(A)", label="VIGIA"),)


def test_scan_memoria_block_without_label_when_the_next_block_starts_immediately() -> None:
    rows = [
        _row(item="01.30", code="AD39050218(A)", desc="descrição 1"),
        _row(item="01.31", code="ET04600200(/)", desc="descrição 2"),
    ]

    scan = scan_memoria_rows(rows)

    assert len(scan.blocks) == 2
    assert scan.blocks[0].label is None
    assert scan.blocks[1].label is None
    assert scan.unlabeled_blocks == scan.blocks
    assert scan.labeled_blocks == ()


def test_scan_memoria_block_without_label_at_end_of_sheet() -> None:
    rows = [
        _row(item="01.30", code="AD39050218(A)", desc="descrição"),
        _row(),
        _row(),
    ]

    scan = scan_memoria_rows(rows)

    assert len(scan.blocks) == 1
    assert scan.blocks[0].label is None


def test_scan_memoria_skips_a_malformed_row_while_searching_the_label() -> None:
    """Linha com só B ou só C preenchida não é bloco (falha o casamento de par) e não
    tem B e C ambas vazias — não interrompe nem alimenta a busca do rótulo."""
    rows = [
        _row(item="01.30", code="AD39050218(A)", desc="descrição"),
        _row(item="02.10", desc="linha malformada, sem código"),
        _row(desc="VIGIA"),
    ]

    scan = scan_memoria_rows(rows)

    assert len(scan.blocks) == 1
    assert scan.blocks[0].label == "VIGIA"


def test_scan_memoria_skips_blank_description_rows_before_finding_the_label() -> None:
    rows = [
        _row(item="01.30", code="AD39050218(A)", desc="descrição"),
        _row(),
        _row(),
        _row(desc="ALAMBRADO CAMPO E QUADRA"),
    ]

    scan = scan_memoria_rows(rows)

    assert scan.blocks[0].label == "ALAMBRADO CAMPO E QUADRA"


def test_worksite_precedents_from_memoria_unions_codes_of_a_repeated_label() -> None:
    rows = [
        _row(item="01.10", code="PJ14150203(A)", desc="descrição 1"),
        _row(desc="ALAMBRADO"),
        _row(item="01.11", code="PJ14100500(/)", desc="descrição 2"),
        _row(desc="ALAMBRADO"),
    ]
    scan = scan_memoria_rows(rows)
    assert len(scan.blocks) == 2

    precedents = worksite_precedents_from_memoria("praca-a", scan, "fonte-x")

    assert len(precedents.observations) == 1
    observation = precedents.observations[0]
    assert observation.label == "ALAMBRADO"
    assert observation.price_source == "fonte-x"
    assert observation.codes == frozenset({"PJ14150203(A)", "PJ14100500(/)"})


def test_worksite_precedents_from_memoria_excludes_unlabeled_blocks() -> None:
    rows = [
        _row(
            item="01.10", code="PJ14150203(A)", desc="descrição 1"
        ),  # sem rótulo: próximo já começa
        _row(item="01.11", code="PJ14100500(/)", desc="descrição 2"),
        _row(desc="CAMPO"),
    ]
    scan = scan_memoria_rows(rows)
    assert len(scan.unlabeled_blocks) == 1
    assert len(scan.labeled_blocks) == 1

    precedents = worksite_precedents_from_memoria("praca-a", scan, "fonte-x")

    assert len(precedents.observations) == 1
    assert precedents.observations[0].label == "CAMPO"
    assert precedents.observations[0].codes == frozenset({"PJ14100500(/)"})


# --------------------------------------------------------------------------------------
# Contrato do pacote de semeadura (T2): o que liga a extração local à ingestão da API
# --------------------------------------------------------------------------------------


def _seed_observation(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "label_original": "PISO EM CONCRETO",
        "label_normalized": "piso em concreto",
        "code": "BP09100050(B)",
        "price_source": "a" * 64,
    }
    payload.update(overrides)
    return payload


def _seed_packet(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "worksite_key": "praca-passada-sul",
        "normalization_strategy": NormalizationStrategy.FOLDED.value,
        "observations": [_seed_observation()],
    }
    payload.update(overrides)
    return payload


def test_seed_packet_reads_back_what_the_extraction_wrote() -> None:
    """Ida e volta pelo JSON: é assim que o pacote atravessa a fronteira HTTP."""
    packet = PrecedentSeedPacket.model_validate(
        json.loads(json.dumps(_seed_packet(unlabeled_block_rows=[7, 12])))
    )

    assert packet.worksite_key == "praca-passada-sul"
    assert packet.normalization_strategy is NormalizationStrategy.FOLDED
    assert packet.unlabeled_block_rows == (7, 12)
    assert packet.observations[0].code == "BP09100050(B)"


def test_seed_packet_requires_a_worksite_key_from_the_real_key_space() -> None:
    """A chave da praça semeada é a mesma das rodadas reais — é por ela que a ingestão
    detecta a colisão que faria a contagem de praças contar a mesma obra duas vezes."""
    with pytest.raises(ValidationError):
        PrecedentSeedPacket.model_validate(_seed_packet(worksite_key="Praça Passada"))


def test_seed_packet_accepts_the_undeclared_price_source() -> None:
    """Rodada de catálogo único grava `catalog_sha256=None`, e a ausência vira a string
    vazia: uma chave PRÓPRIA e válida, nunca um curinga que case com toda fonte."""
    packet = PrecedentSeedPacket.model_validate(
        _seed_packet(observations=[_seed_observation(price_source=PRICE_SOURCE_UNDECLARED)])
    )

    assert packet.observations[0].price_source == PRICE_SOURCE_UNDECLARED


def test_seed_packet_refuses_an_unknown_field() -> None:
    """`extra="forbid"`: um campo que o servidor não conhece é engano de versão, e aceitá-lo
    em silêncio faria o extrator achar que mandou algo que ninguém leu."""
    with pytest.raises(ValidationError):
        PrecedentSeedPacket.model_validate(_seed_packet(price_source="a" * 64))


def test_seed_packet_may_carry_no_observation_and_still_count_the_blocks() -> None:
    """Aba em que nenhum bloco tem rótulo é leitura legítima, não falha.

    Recusar o pacote esconderia justamente o que quem semeia precisa saber: que a planilha
    não deu nenhuma chave de índice, e por quê.
    """
    packet = PrecedentSeedPacket.model_validate(
        _seed_packet(observations=[], block_count=4, unlabeled_block_count=4)
    )

    assert packet.observations == ()
    assert packet.unlabeled_block_count == 4
