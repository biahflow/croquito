"""Sugestão lexical de código SCO nunca confirma; confirmação é fail-closed e imutável.

O refino pago entra pela mesma porta: ele **reordena e anota** a shortlist lexical e nada
mais — código que não estava lá, item que não existe e nota que não cabe no campo recusam
o refino inteiro em vez de virarem shortlist nova.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import ValidationError

from croquito_valuation.assignment import (
    SCO_CASCADE_SUGGESTER_VERSION,
    SCO_REFINED_SUGGESTER_VERSION,
    SCO_SUGGESTER_VERSION,
    CodeAssignment,
    CodeAssignmentBatch,
    CodeAssignmentInput,
    CodeAssignmentSet,
    CodeCandidate,
    CodeSuggestionSet,
    SuggestionConfig,
    SuggestionRefinement,
    SuggestionSemantics,
    apply_code_assignments,
    apply_code_assignments_over_cascade,
    apply_refinement,
    ensure_price_cascade,
    suggest_codes,
    suggest_codes_over_cascade,
)
from croquito_valuation.catalog import (
    DomainSynonyms,
    ExpandedTerms,
    LegendNoiseList,
    default_domain_synonyms,
    default_legend_noise,
    expand_terms,
    lexical_similarity,
    lexical_stems,
    lexical_tokens,
)
from croquito_valuation.contract import ContractLine, ContractWorkbook
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.models import (
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
    ReviewerDecision,
)
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)

_PLATE_ID = "praca-sintetica-norte-prancha-01"
_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_CATALOG_DIGEST = "c" * 64
_OTHER_CATALOG_DIGEST = "e" * 64
_CONTRACT_DIGEST = "d" * 64
_ITEM_1 = "ti_0000000000000001"
_ITEM_2 = "ti_0000000000000002"
_ITEM_3 = "ti_0000000000000003"
_REVIEWER = "orcamentista-sintetico"
_DECIDED_AT = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)


def _evidence(
    *, plate_id: str = _PLATE_ID, page_number: int = 1, image_sha256: str = _DIGEST
) -> PlateEvidence:
    return PlateEvidence(
        plate_id=plate_id,
        page_number=page_number,
        image_sha256=image_sha256,
        bbox=PlateBox(left=10, top=10, right=110, bottom=60),
    )


def _decision(action: Literal["confirm", "reject"] = "confirm") -> ReviewerDecision:
    return ReviewerDecision(
        decision_id="vd_0123456789abcdef",
        action=action,
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
    )


def _confirmed_item(
    *,
    item_id: str = _ITEM_1,
    label: str = "ALAMBRADO GALVANIZADO",
    unit: str = "m",
    quantity: Decimal = Decimal("10.00"),
) -> TakeoffItem:
    return TakeoffItem(
        id=item_id,
        evidence=_evidence(),
        raw_text=f"{label} {quantity} {unit}",
        label=label,
        quantity=quantity,
        unit=unit,
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.CONFIRMED,
        decision=_decision(),
    )


def _ambiguous_item(*, item_id: str = _ITEM_2) -> TakeoffItem:
    return TakeoffItem(
        id=item_id,
        evidence=_evidence(),
        raw_text="ELEMENTO ILEGIVEL",
        label="ELEMENTO ILEGIVEL",
        quantity=None,
        unit="un",
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.AMBIGUOUS,
        decision=None,
    )


def _rejected_item(*, item_id: str = _ITEM_2) -> TakeoffItem:
    return TakeoffItem(
        id=item_id,
        evidence=_evidence(),
        raw_text="ITEM DESCARTADO",
        label="ITEM DESCARTADO",
        quantity=Decimal("1.00"),
        unit="un",
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.REJECTED,
        decision=_decision("reject"),
    )


def _packet(items: list[TakeoffItem] | None = None) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        items=items if items is not None else [_confirmed_item()],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _catalog_entry(
    *,
    code: str = "CE04100010(/)",
    description: str = "ALAMBRADO GALVANIZADO",
    unit: str = "m",
    unit_price: Decimal = Decimal("50.00"),
) -> PriceCatalogEntry:
    return PriceCatalogEntry(
        code=code,
        description=description,
        unit=unit,
        unit_price=unit_price,
        family_code="CE",
        family_name="CERCAS SINTETICAS",
        subgroup_code="CE0410",
        subgroup_name="ALAMBRADOS SINTETICOS",
    )


def _catalog(
    entries: list[PriceCatalogEntry] | None = None, *, source_sha256: str = _CATALOG_DIGEST
) -> PriceCatalog:
    return PriceCatalog(
        source_label="CATALOGO SINTETICO",
        reference_month="2026-01",
        source_sha256=source_sha256,
        entries=entries if entries is not None else [_catalog_entry()],
    )


def _contract_line(
    *,
    code: str = "CE04100010(/)",
    group_label: str = "CERCAS",
    item_number: str = "1",
    unit: str = "m",
    unit_price: Decimal = Decimal("50.00"),
) -> ContractLine:
    return ContractLine(
        group_label=group_label,
        item_number=item_number,
        code=code,
        description="ALAMBRADO GALVANIZADO",
        unit=unit,
        unit_price=unit_price,
        contract_quantity=Decimal("100.00"),
        amended_quantity=Decimal("100.00"),
        periods=[],
        accumulated_quantity=Decimal("0.00"),
        accumulated_amount=Decimal("0.00"),
        balance_quantity=Decimal("100.00"),
    )


def _contract(
    lines: list[ContractLine] | None = None, *, source_sha256: str = _CONTRACT_DIGEST
) -> ContractWorkbook:
    return ContractWorkbook(
        source_label="MAPÃO SINTÉTICO (fixture)",
        source_sha256=source_sha256,
        period_numbers=[],
        lines=lines if lines is not None else [_contract_line()],
    )


def _assignment_input(
    *,
    item_id: str = _ITEM_1,
    action: Literal["confirm", "reject"] = "confirm",
    code: str | None = "CE04100010(/)",
    decided_at: datetime = _DECIDED_AT,
    **overrides: object,
) -> CodeAssignmentInput:
    return CodeAssignmentInput(
        item_id=item_id,
        action=action,
        code=code,
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=decided_at,
        **overrides,
    )


# --------------------------------------------------------------------------------------
# lexical_tokens / lexical_similarity
# --------------------------------------------------------------------------------------


def test_lexical_similarity_is_insensitive_to_case_and_accent() -> None:
    assert lexical_similarity("Alambrado galvanizado", "ALAMBRADO GALVANIZADO") == 1.0


def test_lexical_similarity_is_deterministic_across_calls() -> None:
    first = lexical_similarity("PISO INTERTRAVADO SINTETICO 6CM", "PISO INTERTRAVADO 6CM")
    second = lexical_similarity("PISO INTERTRAVADO SINTETICO 6CM", "PISO INTERTRAVADO 6CM")
    assert first == second


def test_lexical_similarity_of_disjoint_texts_is_zero() -> None:
    """Sem token em comum e sem nenhum caractere em comum: nem Dice nem `SequenceMatcher`
    encontram correspondência, e o score é exatamente 0.0 — não apenas próximo de zero."""
    assert lexical_similarity("QWQW", "ZXZX") == 0.0


def test_lexical_similarity_of_blank_or_symbol_only_text_is_zero() -> None:
    assert lexical_similarity("", "ALAMBRADO GALVANIZADO") == 0.0
    assert lexical_similarity("... - ,,,", "ALAMBRADO GALVANIZADO") == 0.0
    assert lexical_tokens("... - ,,,") == ()


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("ALAMBRADO GALVANIZADO", "ALAMBRADO GALVANIZADO 1,20M"),
        ("PISO INTERTRAVADO SINTETICO 6CM", "MEIO FIO DE GRANITO SINTETICO"),
        ("", ""),
    ],
)
def test_lexical_similarity_is_always_within_unit_interval(left: str, right: str) -> None:
    score = lexical_similarity(left, right)
    assert 0.0 <= score <= 1.0


# --------------------------------------------------------------------------------------
# lexical_stems — radical conservador pt-BR
# --------------------------------------------------------------------------------------


def test_stems_unify_singular_plural_and_the_domain_derivation() -> None:
    """ "gramado"/"grama"/"gramados" são a mesma palavra sob o radical mínimo do domínio."""
    assert lexical_stems("GRAMADO") == lexical_stems("grama") == lexical_stems("gramados")
    assert lexical_stems("gramado") == ("grama",)


def test_stems_of_intertravado_match_the_spec_example() -> None:
    assert lexical_stems("intertravado") == ("intertrava",)


def test_programador_does_not_collide_with_gramado() -> None:
    """ "programador" termina em "dor", não em nenhum dos sufixos de radicalização."""
    assert lexical_stems("programador") != lexical_stems("gramado")
    assert lexical_stems("programador") == ("programador",)


def test_concreto_and_concretado_stay_distinct() -> None:
    """Radical mínimo por construção: "concreto" não termina em "-ado", então não colide
    com "concretado"→"concreta". Nenhuma das duas formas foi forçada a colidir."""
    assert lexical_stems("concreto") == ("concreto",)
    assert lexical_stems("concretado") == ("concreta",)
    assert lexical_stems("concreto") != lexical_stems("concretado")


def test_stems_unify_plural_of_oes_with_the_singular_of_ao() -> None:
    """ "licitações"/"licitação": o -ões plural vira -ão, igual ao singular normalizado."""
    assert lexical_stems("licitações") == lexical_stems("licitação")


def test_short_words_are_never_stemmed() -> None:
    """Abaixo do piso de comprimento, a regra não dispara — "lado" não vira "la"."""
    assert lexical_stems("lado") == ("lado",)


def test_lexical_similarity_dice_is_computed_over_stems() -> None:
    """Duas descrições cujo único traço em comum é singular/plural do mesmo radical
    pontuam mais que zero — o defeito que motivou a Fase 1 do M7 (GRAMADO sem candidato
    porque "gramado" != "grama" em tokens exatos)."""
    assert lexical_similarity("GRAMADO", "PLANTIO DE GRAMA EM PLACAS") > 0.0


# --------------------------------------------------------------------------------------
# DomainSynonyms / expand_terms — sinônimos de domínio como dado
# --------------------------------------------------------------------------------------


def test_default_domain_synonyms_loads_the_packaged_seed() -> None:
    synonyms = default_domain_synonyms()

    assert synonyms.version == "sco-synonyms-v1"
    assert "refletor" in synonyms.terms
    assert synonyms.terms["refletor"] == ["projetor"]


def test_domain_synonyms_normalizes_accent_and_hyphen_at_load() -> None:
    synonyms = DomainSynonyms(version="v1", terms={"Meio-Fio": ["Guia"]})

    assert synonyms.terms == {"meio fio": ["guia"]}


def test_domain_synonyms_refuses_an_empty_term() -> None:
    with pytest.raises(ValidationError) as raised:
        DomainSynonyms(version="v1", terms={"   ": ["guia"]})

    assert valuation_error_codes(raised.value) == ["SYNONYMS_TERM_EMPTY"]


def test_domain_synonyms_refuses_a_term_duplicated_within_the_same_group() -> None:
    with pytest.raises(ValidationError) as raised:
        DomainSynonyms(version="v1", terms={"meio-fio": ["guia", "Guia"]})

    assert valuation_error_codes(raised.value) == ["SYNONYMS_TERM_DUPLICATE"]


def test_domain_synonyms_refuses_a_term_shared_across_two_groups() -> None:
    with pytest.raises(ValidationError) as raised:
        DomainSynonyms(version="v1", terms={"refletor": ["projetor"], "farol": ["projetor"]})

    assert valuation_error_codes(raised.value) == ["SYNONYMS_TERM_DUPLICATE"]


def test_domain_synonyms_refuses_an_empty_group() -> None:
    with pytest.raises(ValidationError) as raised:
        DomainSynonyms(version="v1", terms={"refletor": []})

    assert valuation_error_codes(raised.value) == ["SYNONYMS_GROUP_EMPTY"]


def test_expand_terms_without_synonyms_returns_the_input_unchanged() -> None:
    expanded = expand_terms(("refletor", "existente"), None)

    assert expanded == ExpandedTerms(terms=("refletor", "existente"), origins={})


def test_expand_terms_adds_the_equivalent_with_its_origin() -> None:
    synonyms = DomainSynonyms(version="v1", terms={"refletor": ["projetor"]})

    expanded = expand_terms(("refletor", "existente"), synonyms)

    assert expanded.terms == ("refletor", "existente", "projetor")
    assert expanded.origins == {"projetor": ("refletor",)}


def test_expand_terms_matches_in_both_directions() -> None:
    """Um único par declarado (`refletor: [projetor]`) expande consulta com "refletor" OU
    com "projetor" — o seed não precisa da entrada duplicada nos dois sentidos."""
    synonyms = DomainSynonyms(version="v1", terms={"refletor": ["projetor"]})

    expanded = expand_terms(("projetor",), synonyms)

    assert "refletor" in expanded.terms
    assert expanded.origins["refletor"] == ("projetor",)


def test_expand_terms_matches_a_multi_word_phrase_by_stem_subset() -> None:
    """ "tela de arame galvanizado" só expande quando TODOS os radicais da frase aparecem
    na entrada — presença parcial não casa o grupo."""
    synonyms = DomainSynonyms(version="v1", terms={"alambrado": ["tela de arame galvanizado"]})

    full = expand_terms(lexical_stems("TELA DE ARAME GALVANIZADO"), synonyms)
    partial = expand_terms(lexical_stems("TELA DE ARAME"), synonyms)

    alambrado_stem = lexical_stems("alambrado")[0]
    assert alambrado_stem in full.terms
    assert alambrado_stem not in partial.terms


def test_lexical_similarity_with_synonyms_finds_the_toca_refletor_case() -> None:
    """A descrição real de IP49150409(/) não compartilha nenhum token com "REFLETOR
    EXISTENTE" — só o sinônimo refletor<->projetor cria a interseção."""
    synonyms = DomainSynonyms(version="v1", terms={"refletor": ["projetor"]})
    description = "Projetor PRJ-01, modelo IP-67, para lâmpada a vapor de sódio"

    without_synonyms = lexical_similarity("REFLETOR EXISTENTE", description)
    with_synonyms = lexical_similarity("REFLETOR EXISTENTE", description, synonyms=synonyms)

    assert without_synonyms < with_synonyms


# --------------------------------------------------------------------------------------
# LegendNoiseList — lista de ruído de legenda como dado (rodada 2.2 do M7)
# --------------------------------------------------------------------------------------


def test_default_legend_noise_loads_the_packaged_seed() -> None:
    noise = default_legend_noise()

    assert noise.version == "sco-legend-noise-v1"
    assert "existente" in noise.terms
    assert "a ser recuperar" in noise.terms


def test_legend_noise_normalizes_accent_and_hyphen_at_load() -> None:
    noise = LegendNoiseList(version="v1", terms=["Existente", "A-Ser Recuperar"])

    assert noise.terms == ["existente", "a ser recuperar"]


def test_legend_noise_refuses_an_empty_term() -> None:
    with pytest.raises(ValidationError) as raised:
        LegendNoiseList(version="v1", terms=["existente", "   "])

    assert valuation_error_codes(raised.value) == ["LEGEND_NOISE_TERM_EMPTY"]


def test_legend_noise_refuses_a_duplicated_term() -> None:
    with pytest.raises(ValidationError) as raised:
        LegendNoiseList(version="v1", terms=["existente", "Existente"])

    assert valuation_error_codes(raised.value) == ["LEGEND_NOISE_TERM_DUPLICATE"]


def test_legend_noise_stems_cover_every_word_of_a_phrase_term() -> None:
    """Um termo-frase contribui TODOS os seus radicais, não só a frase inteira casada."""
    noise = LegendNoiseList(version="v1", terms=["a ser recuperar"])

    assert noise.noise_stems() == {"ser", "recuperar"}


def test_a_v1_hybrid_artifact_still_validates_after_the_v2_bump() -> None:
    """Releitura: um `CodeSuggestionSet` gravado com `hybrid-sco-suggester-v1` (antes do bump
    para v2 na rodada 2.2) continua carregando sem erro. `validate_semantic_lineage`
    reconhece a FAMÍLIA híbrida pelo prefixo `SCO_HYBRID_SUGGESTER_FAMILY`, não pela versão
    corrente (`SCO_HYBRID_SUGGESTER_VERSION`) — senão um artefato v1 com lineage semântico
    reprovaria só por ter sido gravado antes do bump."""
    artifact = CodeSuggestionSet(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        catalog_sha256=_CATALOG_DIGEST,
        suggester_version="hybrid-sco-suggester-v1",
        semantic=SuggestionSemantics(
            provider="openai",
            model_id="text-embedding-3-small",
            dims=1536,
            index_sha256=_DIGEST,
        ),
        suggestions=[],
        unmatched_item_ids=[],
        safety_notes=["nota 1", "nota 2", "nota 3"],
    )

    assert artifact.suggester_version == "hybrid-sco-suggester-v1"
    assert artifact.semantic is not None


# --------------------------------------------------------------------------------------
# suggest_codes
# --------------------------------------------------------------------------------------


def test_unit_compatible_candidate_ranks_before_higher_score_with_incompatible_unit() -> None:
    item = _confirmed_item(label="PISO INTERTRAVADO SINTETICO 6CM", unit="m2")
    right_unit = _catalog_entry(
        code="AD04050050(/)",
        description="PISO INTERTRAVADO SINTETICO 6CM CINZA",
        unit="m2",
        unit_price=Decimal("12.00"),
    )
    wrong_unit = _catalog_entry(
        code="AD04050099(/)",
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit="un",
        unit_price=Decimal("10.00"),
    )
    catalog = _catalog([right_unit, wrong_unit])

    result = suggest_codes(_packet([item]), catalog)

    candidates = result.suggestions[0].candidates
    assert candidates[0].code == right_unit.code
    assert candidates[0].unit_compatible is True
    # A candidata correta vence mesmo tendo score lexical estritamente menor.
    assert candidates[0].lexical_score < candidates[1].lexical_score
    assert candidates[1].code == wrong_unit.code
    assert candidates[1].unit_compatible is False


def test_in_contract_candidate_ranks_before_higher_score_outside_contract() -> None:
    item = _confirmed_item(label="MEIO FIO DE GRANITO SINTETICO", unit="m")
    in_contract_entry = _catalog_entry(
        code="AD04100015(/)",
        description="MEIO FIO DE GRANITO SINTETICO PADRAO",
        unit="m",
        unit_price=Decimal("89.30"),
    )
    outside_contract_entry = _catalog_entry(
        code="AD04100020(/)",
        description="MEIO FIO DE GRANITO SINTETICO",
        unit="m",
        unit_price=Decimal("95.00"),
    )
    catalog = _catalog([in_contract_entry, outside_contract_entry])
    contract = _contract([_contract_line(code=in_contract_entry.code, group_label="MEIO-FIO")])

    result = suggest_codes(_packet([item]), catalog, contract)

    candidates = result.suggestions[0].candidates
    assert candidates[0].code == in_contract_entry.code
    assert candidates[0].in_contract is True
    assert candidates[0].lexical_score < candidates[1].lexical_score
    assert candidates[1].code == outside_contract_entry.code
    assert candidates[1].in_contract is False


def test_candidates_are_cut_at_max_candidates_per_item() -> None:
    item = _confirmed_item(label="ALAMBRADO GALVANIZADO", unit="m")
    entries = [
        _catalog_entry(code=f"CE0410001{index}(/)", description="ALAMBRADO GALVANIZADO")
        for index in range(4)
    ]
    catalog = _catalog(entries)

    result = suggest_codes(
        _packet([item]), catalog, config=SuggestionConfig(max_candidates_per_item=2)
    )

    assert len(result.suggestions[0].candidates) == 2


def test_item_below_min_lexical_score_is_unmatched() -> None:
    item = _confirmed_item(label="ALAMBRADO GALVANIZADO", unit="m")
    catalog = _catalog([_catalog_entry(description="TELA MOSQUITEIRO SINTETICA")])

    result = suggest_codes(
        _packet([item]), catalog, config=SuggestionConfig(min_lexical_score=0.99)
    )

    assert result.suggestions == []
    assert result.unmatched_item_ids == [item.id]


def test_suggest_codes_refuses_a_packet_without_confirmed_items() -> None:
    packet = _packet([_ambiguous_item()])

    with pytest.raises(ValuationValidationError) as raised:
        suggest_codes(packet, _catalog())

    assert raised.value.code == "SUGGESTION_NO_CONFIRMED_ITEMS"


@pytest.mark.parametrize(
    "config",
    [
        SuggestionConfig(max_candidates_per_item=0),
        SuggestionConfig(min_lexical_score=-0.1),
        SuggestionConfig(min_lexical_score=1.1),
    ],
)
def test_suggest_codes_refuses_invalid_config(config: SuggestionConfig) -> None:
    with pytest.raises(ValuationValidationError) as raised:
        suggest_codes(_packet(), _catalog(), config=config)

    assert raised.value.code == "SUGGESTION_CONFIG_INVALID"


def test_pending_and_rejected_items_never_get_a_suggestion() -> None:
    confirmed = _confirmed_item(item_id=_ITEM_1)
    ambiguous = _ambiguous_item(item_id=_ITEM_2)
    rejected = _rejected_item(item_id=_ITEM_3)
    packet = _packet([confirmed, ambiguous, rejected])

    result = suggest_codes(packet, _catalog())

    referenced_ids = {s.item_id for s in result.suggestions} | set(result.unmatched_item_ids)
    assert referenced_ids == {_ITEM_1}


def test_suggestion_set_records_packet_and_catalog_digests() -> None:
    packet = _packet()
    catalog = _catalog()

    result = suggest_codes(packet, catalog)

    assert result.plate_id == packet.plate_id
    assert result.page_number == packet.page_number
    assert result.image_sha256 == packet.image_sha256
    assert result.catalog_sha256 == catalog.source_sha256
    assert result.contract_sha256 is None


def test_suggestion_set_has_exactly_three_safety_notes() -> None:
    result = suggest_codes(_packet(), _catalog())

    assert len(result.safety_notes) == 3


def test_suggest_codes_is_deterministic() -> None:
    packet = _packet()
    catalog = _catalog()

    first = suggest_codes(packet, catalog)
    second = suggest_codes(packet, catalog)

    assert first.model_dump() == second.model_dump()


# --------------------------------------------------------------------------------------
# apply_code_assignments — caminho feliz
# --------------------------------------------------------------------------------------


def test_apply_confirms_and_rejects_in_the_same_batch() -> None:
    packet = _packet([_confirmed_item(item_id=_ITEM_1), _confirmed_item(item_id=_ITEM_2)])
    batch = CodeAssignmentBatch(
        assignments=[
            _assignment_input(item_id=_ITEM_1, action="confirm", code="CE04100010(/)"),
            _assignment_input(item_id=_ITEM_2, action="reject", code=None),
        ]
    )

    result = apply_code_assignments(packet, batch, _catalog())

    confirmed = next(a for a in result.assignments if a.item_id == _ITEM_1)
    rejected = next(a for a in result.assignments if a.item_id == _ITEM_2)
    assert confirmed.status == "confirmed"
    assert confirmed.code == "CE04100010(/)"
    assert confirmed.unit_compatible is True
    assert confirmed.decision.action == "confirm"
    assert rejected.status == "rejected"
    assert rejected.code is None
    assert rejected.unit_compatible is False
    assert rejected.decision.action == "reject"


def test_decision_id_is_deterministic_for_the_same_input() -> None:
    packet = _packet()
    batch = CodeAssignmentBatch(assignments=[_assignment_input()])

    first = apply_code_assignments(packet, batch, _catalog())
    second = apply_code_assignments(packet, batch, _catalog())

    assert first.assignments[0].decision.decision_id == second.assignments[0].decision.decision_id


def test_apply_never_mutates_packet_or_batch() -> None:
    packet = _packet()
    batch = CodeAssignmentBatch(assignments=[_assignment_input()])
    packet_before = packet.model_dump()
    batch_before = batch.model_dump()

    apply_code_assignments(packet, batch, _catalog())

    assert packet.model_dump() == packet_before
    assert batch.model_dump() == batch_before


def test_apply_merges_with_previous_preserving_order_and_digests() -> None:
    packet = _packet([_confirmed_item(item_id=_ITEM_1), _confirmed_item(item_id=_ITEM_2)])
    catalog = _catalog()

    first = apply_code_assignments(
        packet, CodeAssignmentBatch(assignments=[_assignment_input(item_id=_ITEM_1)]), catalog
    )
    second = apply_code_assignments(
        packet,
        CodeAssignmentBatch(
            assignments=[_assignment_input(item_id=_ITEM_2, action="reject", code=None)]
        ),
        catalog,
        previous=first,
    )

    assert [a.item_id for a in second.assignments] == [_ITEM_1, _ITEM_2]
    assert second.plate_id == first.plate_id == packet.plate_id
    assert second.catalog_sha256 == first.catalog_sha256 == catalog.source_sha256


# --------------------------------------------------------------------------------------
# apply_code_assignments — matriz de recusa
# --------------------------------------------------------------------------------------


def test_apply_refuses_unknown_item() -> None:
    packet = _packet()
    batch = CodeAssignmentBatch(assignments=[_assignment_input(item_id="ti_ffffffffffffffff")])

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(packet, batch, _catalog())

    assert raised.value.code == "ASSIGNMENT_UNKNOWN_ITEM"


def test_apply_refuses_ambiguous_takeoff_item() -> None:
    packet = _packet([_ambiguous_item(item_id=_ITEM_2)])
    batch = CodeAssignmentBatch(
        assignments=[_assignment_input(item_id=_ITEM_2, action="reject", code=None)]
    )

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(packet, batch, _catalog())

    assert raised.value.code == "ASSIGNMENT_ITEM_NOT_CONFIRMED"


def test_apply_refuses_rejected_takeoff_item() -> None:
    packet = _packet([_rejected_item(item_id=_ITEM_2)])
    batch = CodeAssignmentBatch(
        assignments=[_assignment_input(item_id=_ITEM_2, action="reject", code=None)]
    )

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(packet, batch, _catalog())

    assert raised.value.code == "ASSIGNMENT_ITEM_NOT_CONFIRMED"


def test_apply_refuses_re_deciding_an_already_decided_item() -> None:
    packet = _packet()
    catalog = _catalog()
    first = apply_code_assignments(
        packet, CodeAssignmentBatch(assignments=[_assignment_input()]), catalog
    )

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(
            packet,
            CodeAssignmentBatch(
                assignments=[_assignment_input(decided_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC))]
            ),
            catalog,
            previous=first,
        )

    assert raised.value.code == "ASSIGNMENT_ITEM_ALREADY_DECIDED"


def test_batch_refuses_two_decisions_for_the_same_item() -> None:
    decision = _assignment_input()

    with pytest.raises(ValidationError) as raised:
        CodeAssignmentBatch(assignments=[decision, decision])

    assert valuation_error_codes(raised.value) == ["ASSIGNMENT_DUPLICATE_ITEM"]


def test_confirm_without_code_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        _assignment_input(action="confirm", code=None)

    assert valuation_error_codes(raised.value) == ["ASSIGNMENT_CODE_REQUIRED"]


def test_reject_with_code_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        _assignment_input(action="reject", code="CE04100010(/)")

    assert valuation_error_codes(raised.value) == ["ASSIGNMENT_CODE_ON_REJECT"]


@pytest.mark.parametrize("code", ["not-a-code", "IE00040849"])
def test_invalid_code_structure_is_refused(code: str) -> None:
    """`IE00040849` é código nu válido no contrato, mas não tem preço SCO publicado."""
    with pytest.raises(ValidationError) as raised:
        _assignment_input(action="confirm", code=code)

    assert valuation_error_codes(raised.value) == ["ASSIGNMENT_CODE_INVALID"]


def test_apply_refuses_a_code_outside_the_catalog() -> None:
    packet = _packet()
    batch = CodeAssignmentBatch(assignments=[_assignment_input(code="AD04050050(/)")])

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(packet, batch, _catalog())

    assert raised.value.code == "ASSIGNMENT_CODE_NOT_IN_CATALOG"


def test_apply_refuses_a_code_outside_the_contract() -> None:
    packet = _packet()
    catalog = _catalog()
    contract = _contract([_contract_line(code="AD04050050(/)")])
    batch = CodeAssignmentBatch(assignments=[_assignment_input()])

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(packet, batch, catalog, contract)

    assert raised.value.code == "CODE_NOT_IN_CONTRACT"


def test_apply_refuses_a_code_ambiguous_in_the_contract() -> None:
    packet = _packet()
    catalog = _catalog()
    contract = _contract(
        [_contract_line(), _contract_line(group_label="OUTRO GRUPO DA MESMA OBRA")]
    )
    batch = CodeAssignmentBatch(assignments=[_assignment_input()])

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(packet, batch, catalog, contract)

    assert raised.value.code == "CODE_AMBIGUOUS_IN_CONTRACT"


def test_apply_refuses_incompatible_unit_without_note() -> None:
    item = _confirmed_item(unit="m2")
    packet = _packet([item])
    batch = CodeAssignmentBatch(assignments=[_assignment_input(note=None)])

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(packet, batch, _catalog())

    assert raised.value.code == "ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE"


def test_apply_confirms_incompatible_unit_with_note_and_records_it() -> None:
    item = _confirmed_item(unit="m2")
    packet = _packet([item])
    batch = CodeAssignmentBatch(
        assignments=[_assignment_input(note="unidade conferida manualmente pelo orçamentista")]
    )

    result = apply_code_assignments(packet, batch, _catalog())

    assert result.assignments[0].status == "confirmed"
    assert result.assignments[0].unit_compatible is False


def test_decision_without_timezone_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        CodeAssignmentInput(
            item_id=_ITEM_1,
            action="confirm",
            code="CE04100010(/)",
            reviewer_id=_REVIEWER,
            reviewer_role="orcamentista",
            decided_at=datetime(2026, 2, 1, 12, 0),
        )

    assert valuation_error_codes(raised.value) == ["ASSIGNMENT_DECISION_TIMESTAMP_NAIVE"]


@pytest.mark.parametrize(
    "previous_kwargs",
    [
        {"plate_id": "outra-prancha"},
        {"page_number": 2},
        {"image_sha256": "f" * 64},
    ],
)
def test_apply_refuses_a_previous_set_from_another_packet(
    previous_kwargs: dict[str, object],
) -> None:
    packet = _packet()
    catalog = _catalog()
    previous = CodeAssignmentSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=catalog.source_sha256,
        assignments=[],
        safety_notes=[
            "Confirmação de código é ato humano rastreável; a sugestão lexical nunca "
            "confirma sozinha.",
            "Preço e unidade impressos continuam sendo conferidos contra catálogo e "
            "contrato no portão de exportação.",
        ],
    )
    previous = previous.model_copy(update=previous_kwargs)

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(
            packet,
            CodeAssignmentBatch(assignments=[_assignment_input()]),
            catalog,
            previous=previous,
        )

    assert raised.value.code == "ASSIGNMENT_PACKET_MISMATCH"


def test_apply_refuses_a_previous_set_from_another_catalog() -> None:
    packet = _packet()
    catalog = _catalog()
    previous = CodeAssignmentSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=_OTHER_CATALOG_DIGEST,
        assignments=[],
        safety_notes=[
            "Confirmação de código é ato humano rastreável; a sugestão lexical nunca "
            "confirma sozinha.",
            "Preço e unidade impressos continuam sendo conferidos contra catálogo e "
            "contrato no portão de exportação.",
        ],
    )

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(
            packet,
            CodeAssignmentBatch(assignments=[_assignment_input()]),
            catalog,
            previous=previous,
        )

    assert raised.value.code == "ASSIGNMENT_CATALOG_MISMATCH"


# --------------------------------------------------------------------------------------
# apply_refinement — o refino pago reordena e anota, nunca substitui
# --------------------------------------------------------------------------------------


_REFINEMENT_DIGEST = "f" * 64
_REFINEMENT = SuggestionRefinement(
    provider="anthropic",
    model_id="claude-sonnet-5",
    prompt_version="sco-refinement@1.0.1",
    input_digest=_REFINEMENT_DIGEST,
)


def _shortlist_set() -> CodeSuggestionSet:
    """Shortlist lexical de um item com três candidatos, para o refino permutar."""
    item = _confirmed_item(label="ALAMBRADO GALVANIZADO", unit="m")
    catalog = _catalog(
        [
            _catalog_entry(code="CE04100010(/)", description="ALAMBRADO GALVANIZADO"),
            _catalog_entry(code="CE04100020(/)", description="ALAMBRADO GALVANIZADO PESADO"),
            _catalog_entry(code="CE04100030(/)", description="ALAMBRADO GALVANIZADO LEVE"),
        ]
    )
    suggestions = suggest_codes(_packet([item]), catalog)
    assert len(suggestions.suggestions[0].candidates) == 3
    return suggestions


def _codes(suggestions: CodeSuggestionSet) -> list[str]:
    return [candidate.code for candidate in suggestions.suggestions[0].candidates]


def test_refinement_reorders_the_shortlist_and_annotates_the_first_candidate() -> None:
    lexical = _shortlist_set()
    reversed_codes = list(reversed(_codes(lexical)))
    item_id = lexical.suggestions[0].item_id

    refined = apply_refinement(
        lexical,
        {item_id: reversed_codes},
        {item_id: "unidade e bitola batem com a descrição do item"},
        None,
        _REFINEMENT,
    )

    assert _codes(refined) == reversed_codes
    assert refined.suggester_version == SCO_REFINED_SUGGESTER_VERSION
    assert refined.refinement == _REFINEMENT
    first, *rest = refined.suggestions[0].candidates
    assert first.refinement_note == "unidade e bitola batem com a descrição do item"
    assert all(candidate.refinement_note is None for candidate in rest)


def test_refinement_preserves_every_measured_field_of_the_candidates() -> None:
    """Ordem e anotação são o que muda; score, unidade, preço e status são da via lexical."""
    lexical = _shortlist_set()
    item_id = lexical.suggestions[0].item_id
    before = {
        candidate.code: candidate.model_dump(exclude={"refinement_note"})
        for candidate in lexical.suggestions[0].candidates
    }

    refined = apply_refinement(
        lexical, {item_id: list(reversed(_codes(lexical)))}, None, None, _REFINEMENT
    )

    after = {
        candidate.code: candidate.model_dump(exclude={"refinement_note"})
        for candidate in refined.suggestions[0].candidates
    }
    assert after == before
    assert refined.unmatched_item_ids == lexical.unmatched_item_ids
    assert refined.safety_notes == lexical.safety_notes
    assert refined.catalog_sha256 == lexical.catalog_sha256


def test_refinement_folds_the_flags_into_the_note_of_the_first_candidate() -> None:
    lexical = _shortlist_set()
    item_id = lexical.suggestions[0].item_id

    refined = apply_refinement(
        lexical,
        {item_id: _codes(lexical)},
        {item_id: "nenhum candidato descreve a bitola"},
        {item_id: ["unidade-divergente", "revisar-manualmente"]},
        _REFINEMENT,
    )

    assert refined.suggestions[0].candidates[0].refinement_note == (
        "nenhum candidato descreve a bitola | flags: unidade-divergente; revisar-manualmente"
    )


def test_refinement_keeps_the_flags_even_without_a_rationale() -> None:
    lexical = _shortlist_set()
    item_id = lexical.suggestions[0].item_id

    refined = apply_refinement(
        lexical, {}, None, {item_id: ["sem-candidato-aplicavel"]}, _REFINEMENT
    )

    assert _codes(refined) == _codes(lexical)
    assert refined.suggestions[0].candidates[0].refinement_note == (
        "flags: sem-candidato-aplicavel"
    )


def test_refinement_never_mutates_the_lexical_set() -> None:
    lexical = _shortlist_set()
    item_id = lexical.suggestions[0].item_id
    before = lexical.model_dump()

    apply_refinement(
        lexical, {item_id: list(reversed(_codes(lexical)))}, {item_id: "nota"}, None, _REFINEMENT
    )

    assert lexical.model_dump() == before
    assert lexical.suggester_version == SCO_SUGGESTER_VERSION
    assert lexical.refinement is None


def test_item_not_cited_by_the_refinement_keeps_the_lexical_order_untouched() -> None:
    lexical = _shortlist_set()

    refined = apply_refinement(lexical, {}, None, None, _REFINEMENT)

    assert _codes(refined) == _codes(lexical)
    assert all(candidate.refinement_note is None for candidate in refined.suggestions[0].candidates)
    # Mesmo sem reordenar nada, o conjunto declara que passou pelo refino: quem publicou o
    # artefato pagou a chamada, e o lineage não pode sumir por a ordem ter se mantido.
    assert refined.suggester_version == SCO_REFINED_SUGGESTER_VERSION


def test_refinement_refuses_a_code_that_was_not_in_the_shortlist() -> None:
    lexical = _shortlist_set()
    item_id = lexical.suggestions[0].item_id
    intruder = [*_codes(lexical)[:-1], "AD04050050(/)"]

    with pytest.raises(ValuationValidationError) as raised:
        apply_refinement(lexical, {item_id: intruder}, None, None, _REFINEMENT)

    assert raised.value.code == "REFINEMENT_CODES_MISMATCH"


def test_refinement_refuses_dropping_a_code_from_the_shortlist() -> None:
    lexical = _shortlist_set()
    item_id = lexical.suggestions[0].item_id

    with pytest.raises(ValuationValidationError) as raised:
        apply_refinement(lexical, {item_id: _codes(lexical)[:2]}, None, None, _REFINEMENT)

    assert raised.value.code == "REFINEMENT_CODES_MISMATCH"


def test_refinement_refuses_repeating_a_code_to_pad_the_shortlist() -> None:
    lexical = _shortlist_set()
    item_id = lexical.suggestions[0].item_id
    codes = _codes(lexical)

    with pytest.raises(ValuationValidationError) as raised:
        apply_refinement(lexical, {item_id: [*codes, codes[0]]}, None, None, _REFINEMENT)

    assert raised.value.code == "REFINEMENT_CODES_MISMATCH"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ranked_codes_by_item": {"ti_ffffffffffffffff": ["CE04100010(/)"]}},
        {"notes_by_item": {"ti_ffffffffffffffff": "nota de item que não existe"}},
        {"flags_by_item": {"ti_ffffffffffffffff": ["flag"]}},
    ],
)
def test_refinement_refuses_an_item_outside_the_shortlist(kwargs: dict[str, object]) -> None:
    """Citar item que a shortlist não tem é o provider inventando alvo; recusa fechada."""
    lexical = _shortlist_set()
    arguments: dict[str, object] = {
        "ranked_codes_by_item": {},
        "notes_by_item": None,
        "flags_by_item": None,
        **kwargs,
    }

    with pytest.raises(ValuationValidationError) as raised:
        apply_refinement(
            lexical,
            arguments["ranked_codes_by_item"],  # type: ignore[arg-type]
            arguments["notes_by_item"],  # type: ignore[arg-type]
            arguments["flags_by_item"],  # type: ignore[arg-type]
            _REFINEMENT,
        )

    assert raised.value.code == "REFINEMENT_UNKNOWN_ITEM"


def test_the_largest_note_the_provider_contract_allows_still_fits() -> None:
    """A composição cabe por construção: 300 de rationale + 5 flags de 120 = 918 ≤ 1000.

    É o pior caso que o schema de saída do provider permite. Ele passar aqui é o que impede
    `REFINEMENT_NOTE_TOO_LONG` de cair sobre uma resposta que obedeceu ao contrato — foi
    exatamente esse o defeito visto na segunda rodada paga.
    """
    lexical = _shortlist_set()
    item_id = lexical.suggestions[0].item_id

    refined = apply_refinement(
        lexical, {}, {item_id: "r" * 300}, {item_id: ["f" * 120] * 5}, _REFINEMENT
    )

    note = refined.suggestions[0].candidates[0].refinement_note
    assert note is not None
    assert len(note) == 918
    assert note.startswith("r" * 300)
    assert note.count("f" * 120) == 5


def test_refinement_refuses_a_note_that_does_not_fit_the_candidate() -> None:
    """Defesa do domínio, não do contrato: truncar seria descartar em silêncio.

    Só é alcançável por um chamador que não passe pelo schema do provider — nenhuma
    resposta dentro do contrato chega a este limite.
    """
    lexical = _shortlist_set()
    item_id = lexical.suggestions[0].item_id

    with pytest.raises(ValuationValidationError) as raised:
        apply_refinement(lexical, {}, {item_id: "x" * 1001}, None, _REFINEMENT)

    assert raised.value.code == "REFINEMENT_NOTE_TOO_LONG"


def test_a_refined_set_without_lineage_is_refused() -> None:
    lexical = _shortlist_set()
    payload = {**lexical.model_dump(), "suggester_version": SCO_REFINED_SUGGESTER_VERSION}

    with pytest.raises(ValidationError) as raised:
        CodeSuggestionSet.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["SUGGESTION_REFINEMENT_MISSING"]


def test_a_lexical_set_carrying_lineage_is_refused() -> None:
    lexical = _shortlist_set()
    payload = {**lexical.model_dump(), "refinement": _REFINEMENT.model_dump()}

    with pytest.raises(ValidationError) as raised:
        CodeSuggestionSet.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["SUGGESTION_REFINEMENT_UNEXPECTED"]


def test_the_refined_set_survives_a_json_round_trip() -> None:
    lexical = _shortlist_set()
    item_id = lexical.suggestions[0].item_id
    refined = apply_refinement(
        lexical,
        {item_id: list(reversed(_codes(lexical)))},
        {item_id: "reordenado pelo refino"},
        {item_id: ["lexical-top1-divergente"]},
        _REFINEMENT,
    )

    restored = CodeSuggestionSet.model_validate_json(refined.model_dump_json())

    assert restored == refined
    assert restored.schema_version == "1.2.0"


# --------------------------------------------------------------------------------------
# M8: retrocompatibilidade dos campos de fonte (artefato antigo continua legível)
# --------------------------------------------------------------------------------------


def _emop_entry(
    *,
    code: str = "EMOP.CE.001",
    unit: str = "m",
    description: str = "ALAMBRADO SINTETICO EMOP",
) -> PriceCatalogEntry:
    return PriceCatalogEntry(
        code=code,
        description=description,
        unit=unit,
        unit_price=Decimal("70.00"),
        family_code="CE",
        family_name="CERCAS EMOP",
        subgroup_code="CE02",
        subgroup_name="ALAMBRADOS EMOP",
        origin=PriceOrigin.EMOP,
    )


def _emop_catalog(
    entries: list[PriceCatalogEntry] | None = None, *, source_sha256: str = _OTHER_CATALOG_DIGEST
) -> PriceCatalog:
    return PriceCatalog(
        source_label="CATALOGO EMOP SINTETICO",
        reference_month="2026-06",
        source_sha256=source_sha256,
        entries=entries if entries is not None else [_emop_entry()],
        origin=PriceOrigin.EMOP,
    )


def test_a_candidate_written_before_m8_is_read_back_as_a_sco_candidate() -> None:
    """Artefato M1-M7 não tem os campos de fonte; os defaults os relêem sem migração."""
    candidate = CodeCandidate.model_validate(
        {
            "code": "CE04100010(/)",
            "description": "ALAMBRADO GALVANIZADO",
            "unit": "m",
            "unit_price": "50.00",
            "unit_compatible": True,
            "in_contract": True,
            "lexical_score": 0.5,
            "status": "suggested",
            "refinement_note": None,
        }
    )

    assert candidate.catalog_origin is PriceOrigin.SCO
    assert candidate.catalog_sha256 is None


def test_a_candidate_code_is_validated_against_the_origin_of_its_catalog() -> None:
    payload = {
        "code": "EMOP.CE.001",
        "description": "ALAMBRADO SINTETICO EMOP",
        "unit": "m",
        "unit_price": "70.00",
        "unit_compatible": True,
        "in_contract": False,
        "lexical_score": 0.5,
    }

    with pytest.raises(ValidationError) as raised:
        CodeCandidate.model_validate(payload)

    assert valuation_error_codes(raised.value) == ["CANDIDATE_CODE_INVALID_FOR_ORIGIN"]
    assert CodeCandidate.model_validate({**payload, "catalog_origin": "emop"}).code == "EMOP.CE.001"


def test_an_assignment_written_before_m8_is_read_back_without_a_cited_source() -> None:
    assignment = CodeAssignment.model_validate(
        {
            "item_id": _ITEM_1,
            "status": "confirmed",
            "code": "CE04100010(/)",
            "unit_compatible": True,
            "decision": _decision().model_dump(),
        }
    )

    assert assignment.catalog_sha256 is None


def test_the_single_catalog_flow_keeps_writing_assignments_without_a_source() -> None:
    """O fluxo da medição não mudou: sem citação na entrada, nada de fonte na saída."""
    packet = _packet()
    batch = CodeAssignmentBatch(assignments=[_assignment_input()])

    result = apply_code_assignments(packet, batch, _catalog())

    assert result.assignments[0].catalog_sha256 is None
    assert result.contract_sha256 is None


def test_the_decision_id_of_a_decision_without_a_cited_source_did_not_change() -> None:
    """O id é o digest do conteúdo da decisão; a chave nova só entra quando existe.

    O gabarito abaixo é a forma HISTÓRICA do conteúdo digerido (sem `catalog_sha256`):
    incluir a chave com `null` mudaria o id de toda decisão já gravada no M4-M7.
    """
    packet = _packet()
    batch = CodeAssignmentBatch(assignments=[_assignment_input()])
    canonical = json.dumps(
        {
            "item_id": _ITEM_1,
            "action": "confirm",
            "code": "CE04100010(/)",
            "reviewer_id": _REVIEWER,
            "reviewer_role": "orcamentista",
            "decided_at": _DECIDED_AT.isoformat(),
            "note": None,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    expected = f"vd_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"

    result = apply_code_assignments(packet, batch, _catalog())

    assert result.assignments[0].decision.decision_id == expected


def test_citing_the_source_makes_it_another_decision() -> None:
    packet = _packet()
    catalog = _catalog()
    plain = apply_code_assignments(
        packet, CodeAssignmentBatch(assignments=[_assignment_input()]), catalog
    )
    cited = apply_code_assignments(
        packet,
        CodeAssignmentBatch(assignments=[_assignment_input(catalog_sha256=catalog.source_sha256)]),
        catalog,
    )

    assert cited.assignments[0].catalog_sha256 == catalog.source_sha256
    assert cited.assignments[0].decision.decision_id != plain.assignments[0].decision.decision_id


def test_a_cited_source_that_is_not_the_catalog_of_the_round_is_refused() -> None:
    packet = _packet()
    batch = CodeAssignmentBatch(
        assignments=[_assignment_input(catalog_sha256=_OTHER_CATALOG_DIGEST)]
    )

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments(packet, batch, _catalog())

    assert raised.value.code == "ASSIGNMENT_CATALOG_UNKNOWN"


def test_a_non_sco_code_without_a_cited_source_is_refused_on_input() -> None:
    with pytest.raises(ValidationError) as raised:
        _assignment_input(code="EMOP.CE.001")

    assert valuation_error_codes(raised.value) == ["ASSIGNMENT_CODE_INVALID"]


def test_a_non_sco_code_with_a_cited_source_passes_the_structural_check() -> None:
    decision = _assignment_input(code="EMOP.CE.001", catalog_sha256=_OTHER_CATALOG_DIGEST)

    assert decision.code == "EMOP.CE.001"


def test_a_rejection_cannot_cite_a_source() -> None:
    with pytest.raises(ValidationError) as raised:
        _assignment_input(action="reject", code=None, catalog_sha256=_CATALOG_DIGEST)

    assert valuation_error_codes(raised.value) == ["ASSIGNMENT_CATALOG_ON_REJECT"]


# --------------------------------------------------------------------------------------
# M8: sugestão e confirmação sobre a cascata de fontes
# --------------------------------------------------------------------------------------


def test_a_cascade_with_two_catalogs_of_the_same_origin_is_refused() -> None:
    with pytest.raises(ValuationValidationError) as raised:
        ensure_price_cascade([_catalog(), _catalog(source_sha256=_OTHER_CATALOG_DIGEST)])

    assert raised.value.code == "ESTIMATE_CASCADE_ORIGIN_DUPLICATE"


def test_the_cascade_shortlist_keeps_the_declared_order_and_declares_each_source() -> None:
    packet = _packet()
    sco = _catalog()
    emop = _emop_catalog()

    suggestions = suggest_codes_over_cascade(packet, [sco, emop])

    candidates = suggestions.suggestions[0].candidates
    assert [candidate.catalog_origin for candidate in candidates] == [
        PriceOrigin.SCO,
        PriceOrigin.EMOP,
    ]
    assert [candidate.catalog_sha256 for candidate in candidates] == [
        sco.source_sha256,
        emop.source_sha256,
    ]
    assert suggestions.suggester_version == SCO_CASCADE_SUGGESTER_VERSION
    assert suggestions.catalog_sha256 == sco.source_sha256
    assert suggestions.contract_sha256 is None
    # Pré-licitação não tem contrato: nenhum candidato é marcado como contratado.
    assert all(candidate.in_contract is False for candidate in candidates)


def test_an_item_without_a_candidate_in_any_source_stays_unmatched_in_the_cascade() -> None:
    packet = _packet([_confirmed_item(label="ELEMENTO SEM PARENTESCO LEXICAL ALGUM")])

    suggestions = suggest_codes_over_cascade(
        packet,
        [
            _catalog([_catalog_entry(description="ZZZZZZZZ")]),
            _emop_catalog([_emop_entry(description="ZZZZZZZZ")]),
        ],
    )

    assert suggestions.suggestions == []
    assert suggestions.unmatched_item_ids == [_ITEM_1]


def test_the_cascade_confirmation_records_the_source_of_each_item() -> None:
    packet = _packet([_confirmed_item(item_id=_ITEM_1), _confirmed_item(item_id=_ITEM_2)])
    sco = _catalog()
    emop = _emop_catalog()
    batch = CodeAssignmentBatch(
        assignments=[
            _assignment_input(item_id=_ITEM_1, catalog_sha256=sco.source_sha256),
            _assignment_input(
                item_id=_ITEM_2, code="EMOP.CE.001", catalog_sha256=emop.source_sha256
            ),
        ]
    )

    result = apply_code_assignments_over_cascade(packet, batch, [sco, emop])

    assert [assignment.catalog_sha256 for assignment in result.assignments] == [
        sco.source_sha256,
        emop.source_sha256,
    ]
    # O cabeçalho fica com o catálogo CABEÇA da cascata; a fonte de cada linha é a citada.
    assert result.catalog_sha256 == sco.source_sha256
    assert result.contract_sha256 is None


def test_the_cascade_confirmation_requires_the_source_to_be_cited() -> None:
    packet = _packet()
    batch = CodeAssignmentBatch(assignments=[_assignment_input()])

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments_over_cascade(packet, batch, [_catalog(), _emop_catalog()])

    assert raised.value.code == "ASSIGNMENT_CATALOG_REQUIRED"


def test_the_cascade_confirmation_refuses_a_source_outside_the_cascade() -> None:
    packet = _packet()
    batch = CodeAssignmentBatch(assignments=[_assignment_input(catalog_sha256="9" * 64)])

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments_over_cascade(packet, batch, [_catalog(), _emop_catalog()])

    assert raised.value.code == "ASSIGNMENT_CATALOG_UNKNOWN"


def test_the_cascade_confirmation_refuses_a_code_absent_from_the_cited_source() -> None:
    """O código existe na cascata, mas em outro catálogo — a citação é que manda."""
    packet = _packet()
    emop = _emop_catalog()
    batch = CodeAssignmentBatch(
        assignments=[_assignment_input(code="CE04100010(/)", catalog_sha256=emop.source_sha256)]
    )

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments_over_cascade(packet, batch, [_catalog(), emop])

    assert raised.value.code == "ASSIGNMENT_CODE_NOT_IN_CATALOG"


def test_the_cascade_confirmation_refuses_an_incompatible_unit_without_note() -> None:
    packet = _packet()
    emop = _emop_catalog([_emop_entry(unit="un")])
    batch = CodeAssignmentBatch(
        assignments=[_assignment_input(code="EMOP.CE.001", catalog_sha256=emop.source_sha256)]
    )

    with pytest.raises(ValuationValidationError) as raised:
        apply_code_assignments_over_cascade(packet, batch, [_catalog(), emop])

    assert raised.value.code == "ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE"


def test_the_cascade_rejection_carries_no_source_at_all() -> None:
    packet = _packet()
    batch = CodeAssignmentBatch(assignments=[_assignment_input(action="reject", code=None)])

    result = apply_code_assignments_over_cascade(packet, batch, [_catalog(), _emop_catalog()])

    assert result.assignments[0].status == "rejected"
    assert result.assignments[0].catalog_sha256 is None
