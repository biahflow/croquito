"""A matriz funde por serviço; o regime legado continua byte-idêntico ao boletim de hoje."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import ValidationError

from croquito_valuation.assignment import (
    CodeAssignment,
    CodeAssignmentSet,
    ItemPackageClosure,
)
from croquito_valuation.calc import build_worksite_bulletin
from croquito_valuation.calc_matrix import (
    CalcContribution,
    CalcMatrix,
    ServiceContributions,
    resolve_calc_matrix,
)
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.models import (
    CalcOperand,
    CalcRecipe,
    ContributionBasis,
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
_WORKSITE_KEY = "praca-sintetica-norte"
_WORKSITE_NAME = "PRACA SINTETICA NORTE"
_REVIEWER = "orcamentista-sintetico"
_DECIDED_AT = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
_ITEM_1 = "ti_0000000000000001"
_ITEM_2 = "ti_0000000000000002"

_SAIBRO = "BP04050350(/)"
_TRANSPORTE = "MT14150050(A)"
_TELA = "ET39050109(/)"


def _decision(suffix: str, *, action: Literal["confirm", "reject"] = "confirm") -> ReviewerDecision:
    return ReviewerDecision(
        decision_id=f"vd_{suffix * 16}"[:19],
        action=action,
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
    )


def _evidence() -> PlateEvidence:
    return PlateEvidence(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        bbox=PlateBox(left=10, top=10, right=110, bottom=60),
    )


def _confirmed_item(
    *,
    item_id: str = _ITEM_1,
    label: str = "ITEM SINTETICO",
    unit: str = "m2",
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
        decision=ReviewerDecision(
            decision_id=f"vd_{item_id[3:]}",
            action="confirm",
            reviewer_id=_REVIEWER,
            reviewer_role="orcamentista",
            decided_at=_DECIDED_AT,
        ),
    )


def _packet(items: list[TakeoffItem]) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        items=items,
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _catalog_entry(code: str, *, unit: str = "m2") -> PriceCatalogEntry:
    return PriceCatalogEntry(
        code=code,
        description=f"SERVICO {code}",
        unit=unit,
        unit_price=Decimal("50.00"),
        family_code="BP",
        family_name="SERVICOS SINTETICOS",
        subgroup_code="BP0405",
        subgroup_name="ITENS SINTETICOS",
    )


def _catalog(codes: list[str]) -> PriceCatalog:
    return PriceCatalog(
        source_label="CATALOGO SINTETICO",
        reference_month="2026-01",
        source_sha256=_CATALOG_DIGEST,
        origin=PriceOrigin.SCO,
        entries=[_catalog_entry(code) for code in codes],
    )


def _assignment(item_id: str, code: str, suffix: str) -> CodeAssignment:
    return CodeAssignment(
        item_id=item_id,
        status="confirmed",
        code=code,
        unit_compatible=True,
        decision=_decision(suffix),
    )


def _assignment_set(assignments: list[CodeAssignment]) -> CodeAssignmentSet:
    # Um fechamento por ELEMENTO, reusando a decisão do próprio assignment (ids distintos).
    closed = {a.item_id: a.decision for a in assignments if a.status == "confirmed"}
    return CodeAssignmentSet(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_DIGEST,
        catalog_sha256=_CATALOG_DIGEST,
        assignments=assignments,
        closures=[ItemPackageClosure(item_id=item_id, decision=d) for item_id, d in closed.items()],
        safety_notes=[
            "Confirmação de código é ato humano rastreável.",
            "Preço e unidade impressos são conferidos no portão de exportação.",
        ],
    )


def _full(item_id: str, *, value: Decimal, label: str = "AREA") -> CalcContribution:
    return CalcContribution(
        source_item_id=item_id,
        label=label,
        basis=ContributionBasis.FULL,
        recipe=CalcRecipe.LENGTH_TIMES_WIDTH,
        operands=[CalcOperand(name="AREA", value=value, unit="m2")],
    )


def _dependent(code: str, *, factor: Decimal = Decimal("2")) -> CalcContribution:
    return CalcContribution(
        label=f"TRANSPORTE DE {code}",
        basis=ContributionBasis.DEPENDENT,
        recipe=CalcRecipe.DECLARED_PRODUCT,
        operands=[CalcOperand(name="P.ESP", value=factor, unit="t/m3")],
        depends_on_code=code,
    )


def _partial(
    item_id: str,
    *,
    value: Decimal,
    note: str | None = "170 m2 medidos em campo pela orcamentista",
    label: str = "LIMPEZA",
) -> CalcContribution:
    return CalcContribution(
        source_item_id=item_id,
        label=label,
        basis=ContributionBasis.PARTIAL,
        recipe=CalcRecipe.DECLARED_PRODUCT,
        operands=[CalcOperand(name="AREA", value=value, unit="m2")],
        note=note,
    )


# --------------------------------------------------------------------------------------
# guardas na leitura do artefato
# --------------------------------------------------------------------------------------


def test_cycle_rejected_at_read() -> None:
    with pytest.raises(ValidationError) as raised:
        CalcMatrix(
            services=[
                ServiceContributions(code=_SAIBRO, contributions=[_dependent(_TRANSPORTE)]),
                ServiceContributions(code=_TRANSPORTE, contributions=[_dependent(_SAIBRO)]),
            ]
        )
    assert valuation_error_codes(raised.value) == ["CALC_MATRIX_DEPENDENCY_CYCLE"]


def test_self_dependency_rejected_at_read() -> None:
    with pytest.raises(ValidationError) as raised:
        CalcMatrix(
            services=[ServiceContributions(code=_SAIBRO, contributions=[_dependent(_SAIBRO)])]
        )
    assert valuation_error_codes(raised.value) == ["CALC_MATRIX_SELF_DEPENDENCY"]


def test_duplicate_code_rejected_at_read() -> None:
    with pytest.raises(ValidationError) as raised:
        CalcMatrix(
            services=[
                ServiceContributions(
                    code=_SAIBRO, contributions=[_full(_ITEM_1, value=Decimal("1"))]
                ),
                ServiceContributions(
                    code=_SAIBRO, contributions=[_full(_ITEM_2, value=Decimal("2"))]
                ),
            ]
        )
    assert valuation_error_codes(raised.value) == ["CALC_MATRIX_DUPLICATE_CODE"]


def test_full_contribution_without_source_item_rejected() -> None:
    with pytest.raises(ValidationError) as raised:
        CalcContribution(
            label="AREA",
            basis=ContributionBasis.FULL,
            recipe=CalcRecipe.LENGTH_TIMES_WIDTH,
            operands=[CalcOperand(name="AREA", value=Decimal("10"))],
        )
    assert valuation_error_codes(raised.value) == ["CALC_CONTRIBUTION_WITHOUT_SOURCE_ITEM"]


def test_dependent_contribution_without_code_rejected() -> None:
    with pytest.raises(ValidationError) as raised:
        CalcContribution(
            label="TRANSPORTE",
            basis=ContributionBasis.DEPENDENT,
            recipe=CalcRecipe.DECLARED_PRODUCT,
            operands=[CalcOperand(name="P.ESP", value=Decimal("2"))],
        )
    assert valuation_error_codes(raised.value) == ["CALC_CONTRIBUTION_DEPENDENT_WITHOUT_CODE"]


# --------------------------------------------------------------------------------------
# ordem topológica e materialização da dependência
# --------------------------------------------------------------------------------------


def _priced_set(codes: list[str]) -> CodeAssignmentSet:
    return _assignment_set(
        [_assignment(_ITEM_1, code, chr(ord("a") + i)) for i, code in enumerate(codes)]
    )


def test_topological_order_is_numbering_and_deterministic() -> None:
    # TRANSPORTE depende de SAIBRO, mas é declarado ANTES na lista: o resolver reordena.
    matrix = CalcMatrix(
        services=[
            ServiceContributions(code=_TRANSPORTE, contributions=[_dependent(_SAIBRO)]),
            ServiceContributions(
                code=_SAIBRO, contributions=[_full(_ITEM_1, value=Decimal("100"))]
            ),
        ]
    )
    resolved = resolve_calc_matrix([], _priced_set([_SAIBRO, _TRANSPORTE]), calc_matrix=matrix)

    numbering = [(s.item_number, s.code) for s in resolved.services]
    assert numbering == [("1", _SAIBRO), ("2", _TRANSPORTE)]


def test_dependent_parcel_materializes_upstream_quantity_as_literal() -> None:
    matrix = CalcMatrix(
        services=[
            ServiceContributions(
                code=_SAIBRO, contributions=[_full(_ITEM_1, value=Decimal("100"))]
            ),
            ServiceContributions(
                code=_TRANSPORTE, contributions=[_dependent(_SAIBRO, factor=Decimal("2"))]
            ),
        ]
    )
    resolved = resolve_calc_matrix([], _priced_set([_SAIBRO, _TRANSPORTE]), calc_matrix=matrix)

    transporte = next(s for s in resolved.services if s.code == _TRANSPORTE)
    block = transporte.blocks[0]
    # O primeiro operando é a quantidade resolvida do serviço de origem, literal, com o
    # código citado no nome; a proveniência viaja em `derived_from_code`.
    assert block.operands[0] == CalcOperand(name=f"QUANTIDADE {_SAIBRO}", value=Decimal("100.00"))
    assert block.derived_from_code == _SAIBRO
    assert transporte.total_quantity == Decimal("200.00")


def test_fusion_by_code_sums_contributions_from_many_elements() -> None:
    # Dois elementos alimentam o MESMO serviço: uma linha, soma das parcelas.
    matrix = CalcMatrix(
        services=[
            ServiceContributions(
                code=_SAIBRO,
                contributions=[
                    _full(_ITEM_1, value=Decimal("418.12"), label="PISO EM CONCRETO"),
                    _full(_ITEM_2, value=Decimal("59.34"), label="PAVIMENTO INTERTRAVADO"),
                ],
            )
        ]
    )
    resolved = resolve_calc_matrix([], _priced_set([_SAIBRO]), calc_matrix=matrix)

    assert len(resolved.services) == 1
    assert resolved.services[0].total_quantity == Decimal("477.46")
    assert len(resolved.services[0].blocks) == 2


# --------------------------------------------------------------------------------------
# recusas de build, espelhadas por prefixo de cadeia
# --------------------------------------------------------------------------------------


def test_dependency_unknown_target_outside_matrix() -> None:
    matrix = CalcMatrix(
        services=[ServiceContributions(code=_SAIBRO, contributions=[_dependent(_TELA)])]
    )
    with pytest.raises(ValuationValidationError) as raised:
        resolve_calc_matrix([], _priced_set([_SAIBRO]), calc_matrix=matrix)
    assert raised.value.code == "CALC_MATRIX_DEPENDENCY_UNKNOWN"


def test_dependency_unpriced_target_without_confirmed_code() -> None:
    # TELA está na matriz mas nenhum código confirmado a precifica.
    matrix = CalcMatrix(
        services=[
            ServiceContributions(code=_TELA, contributions=[_full(_ITEM_2, value=Decimal("5"))]),
            ServiceContributions(code=_SAIBRO, contributions=[_dependent(_TELA)]),
        ]
    )
    with pytest.raises(ValuationValidationError) as raised:
        resolve_calc_matrix([], _priced_set([_SAIBRO]), calc_matrix=matrix, error_prefix="ESTIMATE")
    assert raised.value.code == "ESTIMATE_MATRIX_DEPENDENCY_UNPRICED"


# --------------------------------------------------------------------------------------
# regime legado byte-idêntico ao boletim de hoje
# --------------------------------------------------------------------------------------


def test_legacy_regime_is_byte_identical_to_bulletin_builder() -> None:
    items = [
        _confirmed_item(item_id=_ITEM_1, label="PISO", unit="m2", quantity=Decimal("5.00")),
        _confirmed_item(item_id=_ITEM_2, label="GRAMA", unit="m2", quantity=Decimal("8.90")),
    ]
    packet = _packet(items)
    catalog = _catalog([_SAIBRO, _TRANSPORTE])
    assignments = _assignment_set(
        [_assignment(_ITEM_1, _SAIBRO, "a"), _assignment(_ITEM_2, _TRANSPORTE, "b")]
    )

    built = build_worksite_bulletin(
        packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
    )
    resolved = resolve_calc_matrix(list(packet.confirmed_items()), assignments)

    # Mesma numeração, mesmos códigos, e a memória resolvida bate bloco a bloco com a do
    # builder — nada fundido, nada renumerado.
    assert [s.item_number for s in resolved.services] == list(built.item_numbers.values())
    assert [s.code for s in resolved.services] == [line.code for line in built.bulletin.lines]
    for service, sheet in zip(resolved.services, built.calc_sheets, strict=True):
        assert [b.model_dump() for b in service.blocks] == [b.model_dump() for b in sheet.blocks]
        assert service.total_quantity == sheet.total_quantity


def test_legacy_regime_keeps_two_items_with_same_code_as_two_services() -> None:
    items = [
        _confirmed_item(item_id=_ITEM_1, label="PISO", unit="m2", quantity=Decimal("5.00")),
        _confirmed_item(item_id=_ITEM_2, label="OUTRO", unit="m2", quantity=Decimal("8.00")),
    ]
    packet = _packet(items)
    assignments = _assignment_set(
        [_assignment(_ITEM_1, _SAIBRO, "a"), _assignment(_ITEM_2, _SAIBRO, "b")]
    )
    resolved = resolve_calc_matrix(list(packet.confirmed_items()), assignments)

    # Mesmo código nos dois: NÃO funde no regime legado — fusão mexeria em boletim assinado.
    assert [s.code for s in resolved.services] == [_SAIBRO, _SAIBRO]
    assert [s.item_number for s in resolved.services] == ["1", "2"]


# --------------------------------------------------------------------------------------
# parcela PARTIAL: nota obrigatória (leitura) e teto do elemento (build) — ADR-0053, d.3
# --------------------------------------------------------------------------------------


def test_partial_without_note_rejected_at_read() -> None:
    with pytest.raises(ValidationError) as raised:
        _partial(_ITEM_1, value=Decimal("170"), note=None)
    assert valuation_error_codes(raised.value) == ["CALC_PARTIAL_NOTE_REQUIRED"]


def test_partial_with_blank_note_rejected_at_read() -> None:
    with pytest.raises(ValidationError) as raised:
        _partial(_ITEM_1, value=Decimal("170"), note="   ")
    assert valuation_error_codes(raised.value) == ["CALC_PARTIAL_NOTE_REQUIRED"]


def test_partial_within_item_cap_builds() -> None:
    # 170 m2 de limpeza dentro dos 418,12 do piso: declarado, com nota, e abaixo do teto.
    item = _confirmed_item(item_id=_ITEM_1, quantity=Decimal("418.12"))
    matrix = CalcMatrix(
        services=[
            ServiceContributions(
                code=_SAIBRO, contributions=[_partial(_ITEM_1, value=Decimal("170"))]
            )
        ]
    )
    resolved = resolve_calc_matrix([item], _priced_set([_SAIBRO]), calc_matrix=matrix)
    assert resolved.services[0].total_quantity == Decimal("170.00")


def test_partial_equal_to_item_cap_builds() -> None:
    # Fronteira: declarado == teto não ultrapassa (a recusa é estrita, `>`).
    item = _confirmed_item(item_id=_ITEM_1, quantity=Decimal("418.12"))
    matrix = CalcMatrix(
        services=[
            ServiceContributions(
                code=_SAIBRO, contributions=[_partial(_ITEM_1, value=Decimal("418.12"))]
            )
        ]
    )
    resolved = resolve_calc_matrix([item], _priced_set([_SAIBRO]), calc_matrix=matrix)
    assert resolved.services[0].total_quantity == Decimal("418.12")


def test_partial_over_item_cap_rejected_at_build() -> None:
    item = _confirmed_item(item_id=_ITEM_1, quantity=Decimal("418.12"))
    matrix = CalcMatrix(
        services=[
            ServiceContributions(
                code=_SAIBRO, contributions=[_partial(_ITEM_1, value=Decimal("500"))]
            )
        ]
    )
    with pytest.raises(ValuationValidationError) as raised:
        resolve_calc_matrix([item], _priced_set([_SAIBRO]), calc_matrix=matrix)
    assert raised.value.code == "CALC_PARTIAL_EXCEEDS_ITEM"
    assert raised.value.details["source_item_id"] == _ITEM_1
    assert raised.value.details["declared"] == "500.00"
    assert raised.value.details["cap"] == "418.12"


def test_partial_cap_code_is_fixed_across_chains() -> None:
    # O teto e a nota descrevem a semântica da célula, não a resolução da cadeia: o código é
    # `CALC_PARTIAL_*` fixo mesmo no orçamento-base (`error_prefix="ESTIMATE"`).
    item = _confirmed_item(item_id=_ITEM_1, quantity=Decimal("418.12"))
    matrix = CalcMatrix(
        services=[
            ServiceContributions(
                code=_SAIBRO, contributions=[_partial(_ITEM_1, value=Decimal("500"))]
            )
        ]
    )
    with pytest.raises(ValuationValidationError) as raised:
        resolve_calc_matrix(
            [item], _priced_set([_SAIBRO]), calc_matrix=matrix, error_prefix="ESTIMATE"
        )
    assert raised.value.code == "CALC_PARTIAL_EXCEEDS_ITEM"
