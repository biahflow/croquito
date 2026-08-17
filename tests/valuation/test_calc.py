"""A quantidade confirmada manda: o plano de cálculo só explica como ela se decompõe."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest
from pydantic import ValidationError

from croquito_valuation.assignment import CodeAssignment, CodeAssignmentSet
from croquito_valuation.calc import (
    DEFAULT_BLOCK_LABEL,
    DEFAULT_OPERAND_NAME,
    CalcBlockPlan,
    CalcPlan,
    ItemCalcPlan,
    build_worksite_bulletin,
    build_worksite_valuation,
)
from croquito_valuation.contract import ContractLine, ContractWorkbook
from croquito_valuation.errors import ValuationValidationError, valuation_error_codes
from croquito_valuation.models import (
    CalcOperand,
    CalcRecipe,
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
    decision = ReviewerDecision(
        decision_id=f"vd_{item_id[3:]}",
        action="confirm",
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
    )
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
        decision=decision,
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
    description: str = "ITEM SINTETICO",
    unit: str = "m2",
    unit_price: Decimal = Decimal("50.00"),
) -> PriceCatalogEntry:
    return PriceCatalogEntry(
        code=code,
        description=description,
        unit=unit,
        unit_price=unit_price,
        family_code="CE",
        family_name="SERVICOS SINTETICOS",
        subgroup_code="CE0410",
        subgroup_name="ITENS SINTETICOS",
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


def _assignment(
    item_id: str,
    *,
    status: Literal["confirmed", "rejected"] = "confirmed",
    code: str | None = None,
    unit_compatible: bool = True,
) -> CodeAssignment:
    action: Literal["confirm", "reject"] = "confirm" if status == "confirmed" else "reject"
    decision = ReviewerDecision(
        decision_id=f"vd_{item_id[3:]}",
        action=action,
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
    )
    return CodeAssignment(
        item_id=item_id,
        status=status,
        code=code if status == "confirmed" else None,
        unit_compatible=unit_compatible if status == "confirmed" else False,
        decision=decision,
    )


def _assignment_set(
    packet: TakeoffPacket, catalog: PriceCatalog, assignments: list[CodeAssignment]
) -> CodeAssignmentSet:
    return CodeAssignmentSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=catalog.source_sha256,
        assignments=assignments,
        safety_notes=[
            "Confirmação de código é ato humano rastreável; a sugestão lexical nunca "
            "confirma sozinha.",
            "Preço e unidade impressos continuam sendo conferidos contra catálogo e "
            "contrato no portão de exportação.",
        ],
    )


# --------------------------------------------------------------------------------------
# item sem plano → bloco padrão
# --------------------------------------------------------------------------------------


def test_item_without_plan_gets_a_direct_quantity_block_with_default_numbering() -> None:
    item1 = _confirmed_item(
        item_id=_ITEM_1, label="PISO INTERTRAVADO SINTETICO", unit="m2", quantity=Decimal("5.00")
    )
    item2 = _confirmed_item(
        item_id=_ITEM_2, label="MEIO FIO DE GRANITO", unit="m", quantity=Decimal("3.00")
    )
    packet = _packet([item1, item2])
    entry1 = _catalog_entry(
        code="AD04050050(/)",
        description="PISO INTERTRAVADO SINTETICO 6CM",
        unit="m2",
        unit_price=Decimal("89.30"),
    )
    entry2 = _catalog_entry(
        code="AD04100015(/)",
        description="MEIO FIO DE GRANITO SINTETICO",
        unit="m",
        unit_price=Decimal("40.00"),
    )
    catalog = _catalog([entry1, entry2])
    assignments = _assignment_set(
        packet,
        catalog,
        [_assignment(item1.id, code=entry1.code), _assignment(item2.id, code=entry2.code)],
    )

    result = build_worksite_bulletin(
        packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
    )

    assert result.item_numbers == {item1.id: "1", item2.id: "2"}
    line1, line2 = result.bulletin.lines
    assert line1.item_number == "1"
    assert line1.description == entry1.description
    assert line1.unit == entry1.unit
    assert line1.unit_price == entry1.unit_price
    assert line1.total == Decimal("446.50")
    assert line2.item_number == "2"
    assert line2.description == entry2.description

    block1 = result.calc_sheets[0].blocks[0]
    assert block1.label == DEFAULT_BLOCK_LABEL
    assert block1.recipe == CalcRecipe.DIRECT_QUANTITY
    assert block1.operands[0].name == DEFAULT_OPERAND_NAME
    assert block1.operands[0].value == item1.quantity
    assert block1.operands[0].unit == item1.unit

    valuation = build_worksite_valuation(
        packet,
        assignments,
        catalog,
        worksite_key=_WORKSITE_KEY,
        worksite_name=_WORKSITE_NAME,
        period_number=1,
        reference_label="JANEIRO/2026",
    )
    assert valuation.calc_sheet_for(_WORKSITE_KEY, "1").total_quantity == item1.quantity
    assert valuation.calc_sheet_for(_WORKSITE_KEY, "2").total_quantity == item2.quantity


# --------------------------------------------------------------------------------------
# item com plano
# --------------------------------------------------------------------------------------


def test_item_with_plan_computes_subtotals_and_total_quantity_by_construction() -> None:
    plain = _confirmed_item(
        item_id=_ITEM_1, label="ALAMBRADO GALVANIZADO", unit="m2", quantity=Decimal("48.00")
    )
    with_opening = _confirmed_item(
        item_id=_ITEM_2, label="ALAMBRADO COM VAO", unit="m2", quantity=Decimal("40.00")
    )
    packet = _packet([plain, with_opening])
    entry1 = _catalog_entry(code="CE04100010(/)", description="ALAMBRADO GALVANIZADO", unit="m2")
    entry2 = _catalog_entry(code="CE04100020(/)", description="ALAMBRADO COM VAO", unit="m2")
    catalog = _catalog([entry1, entry2])
    assignments = _assignment_set(
        packet,
        catalog,
        [_assignment(plain.id, code=entry1.code), _assignment(with_opening.id, code=entry2.code)],
    )
    calc_plan = CalcPlan(
        plans=[
            ItemCalcPlan(
                item_id=plain.id,
                blocks=[
                    CalcBlockPlan(
                        label="ALAMBRADO NORTE",
                        recipe=CalcRecipe.PERIMETER_TIMES_HEIGHT,
                        operands=[
                            CalcOperand(name="PERIMETRO", value=Decimal("40.00"), unit="m"),
                            CalcOperand(name="ALTURA", value=Decimal("1.20"), unit="m"),
                        ],
                    )
                ],
            ),
            ItemCalcPlan(
                item_id=with_opening.id,
                blocks=[
                    CalcBlockPlan(
                        label="ALAMBRADO COM VAO",
                        recipe=CalcRecipe.PERIM_HEIGHT_MINUS_OPENINGS,
                        operands=[
                            CalcOperand(name="PERIMETRO", value=Decimal("45.00"), unit="m"),
                            CalcOperand(name="ALTURA", value=Decimal("1.00"), unit="m"),
                        ],
                        deductions=[CalcOperand(name="VAOS", value=Decimal("5.00"), unit="m2")],
                    )
                ],
            ),
        ]
    )

    result = build_worksite_bulletin(
        packet,
        assignments,
        catalog,
        worksite_key=_WORKSITE_KEY,
        worksite_name=_WORKSITE_NAME,
        calc_plan=calc_plan,
    )

    sheets_by_number = {sheet.item_number: sheet for sheet in result.calc_sheets}
    assert sheets_by_number["1"].blocks[0].subtotal == Decimal("48.00")
    assert sheets_by_number["1"].total_quantity == Decimal("48.00")
    assert sheets_by_number["2"].blocks[0].subtotal == Decimal("40.00")
    assert sheets_by_number["2"].total_quantity == Decimal("40.00")


def test_plan_that_does_not_close_with_the_confirmed_quantity_is_refused() -> None:
    item = _confirmed_item(
        item_id=_ITEM_1, label="ALAMBRADO GALVANIZADO", unit="m2", quantity=Decimal("48.00")
    )
    packet = _packet([item])
    entry = _catalog_entry(code="CE04100010(/)", description="ALAMBRADO GALVANIZADO", unit="m2")
    catalog = _catalog([entry])
    assignments = _assignment_set(packet, catalog, [_assignment(item.id, code=entry.code)])
    calc_plan = CalcPlan(
        plans=[
            ItemCalcPlan(
                item_id=item.id,
                blocks=[
                    CalcBlockPlan(
                        label="ALAMBRADO NORTE",
                        recipe=CalcRecipe.PERIMETER_TIMES_HEIGHT,
                        operands=[
                            CalcOperand(name="PERIMETRO", value=Decimal("40.00"), unit="m"),
                            CalcOperand(name="ALTURA", value=Decimal("1.00"), unit="m"),
                        ],
                    )
                ],
            )
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet,
            assignments,
            catalog,
            worksite_key=_WORKSITE_KEY,
            worksite_name=_WORKSITE_NAME,
            calc_plan=calc_plan,
        )

    assert raised.value.code == "CALC_PLAN_QUANTITY_MISMATCH"


# --------------------------------------------------------------------------------------
# matriz de recusa
# --------------------------------------------------------------------------------------


def test_missing_assignment_for_a_confirmed_item_is_refused() -> None:
    item = _confirmed_item()
    packet = _packet([item])
    catalog = _catalog()
    assignments = _assignment_set(packet, catalog, [])

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
        )

    assert raised.value.code == "CALC_ASSIGNMENT_MISSING"


def test_assignment_for_an_unknown_item_is_refused() -> None:
    item = _confirmed_item()
    packet = _packet([item])
    entry = _catalog_entry()
    catalog = _catalog([entry])
    assignments = _assignment_set(
        packet,
        catalog,
        [
            _assignment(item.id, code=entry.code),
            _assignment("ti_ffffffffffffffff", code=entry.code),
        ],
    )

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
        )

    assert raised.value.code == "CALC_ASSIGNMENT_UNKNOWN_ITEM"


def test_assignments_from_another_packet_are_refused() -> None:
    item = _confirmed_item()
    packet = _packet([item])
    entry = _catalog_entry()
    catalog = _catalog([entry])
    assignments = _assignment_set(packet, catalog, [_assignment(item.id, code=entry.code)])
    other_assignments = assignments.model_copy(update={"plate_id": "outra-prancha"})

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet,
            other_assignments,
            catalog,
            worksite_key=_WORKSITE_KEY,
            worksite_name=_WORKSITE_NAME,
        )

    assert raised.value.code == "CALC_ASSIGNMENT_PACKET_MISMATCH"


def test_assignments_from_another_catalog_are_refused() -> None:
    item = _confirmed_item()
    packet = _packet([item])
    entry = _catalog_entry()
    catalog = _catalog([entry])
    assignments = _assignment_set(packet, catalog, [_assignment(item.id, code=entry.code)])
    other_assignments = assignments.model_copy(update={"catalog_sha256": "e" * 64})

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet,
            other_assignments,
            catalog,
            worksite_key=_WORKSITE_KEY,
            worksite_name=_WORKSITE_NAME,
        )

    assert raised.value.code == "CALC_CATALOG_MISMATCH"


def test_bulletin_refuses_a_catalog_whose_origin_is_not_sco() -> None:
    """A cadeia da medição licitada é SEMPRE SCO: EMOP/composição só valem pré-licitação."""
    item = _confirmed_item()
    packet = _packet([item])
    entry = PriceCatalogEntry(
        code="EMOP.CE.001",
        description="ITEM SINTETICO EMOP",
        unit="m2",
        unit_price=Decimal("50.00"),
        family_code="CE",
        family_name="SERVICOS SINTETICOS EMOP",
        subgroup_code="CE0410",
        subgroup_name="ITENS SINTETICOS EMOP",
        origin=PriceOrigin.EMOP,
    )
    catalog = PriceCatalog(
        source_label="CATALOGO EMOP SINTETICO",
        reference_month="2026-01",
        source_sha256=_CATALOG_DIGEST,
        entries=[entry],
        origin=PriceOrigin.EMOP,
    )
    assignments = _assignment_set(packet, catalog, [_assignment(item.id, code=entry.code)])

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet,
            assignments,
            catalog,
            worksite_key=_WORKSITE_KEY,
            worksite_name=_WORKSITE_NAME,
        )

    assert raised.value.code == "BULLETIN_PRICE_ORIGIN_FORBIDDEN"


def test_plan_for_a_rejected_item_is_refused() -> None:
    rejected = _confirmed_item(item_id=_ITEM_1)
    included = _confirmed_item(
        item_id=_ITEM_2, label="MEIO FIO DE GRANITO", unit="m", quantity=Decimal("3.00")
    )
    packet = _packet([rejected, included])
    entry = _catalog_entry(
        code="AD04100015(/)",
        description="MEIO FIO DE GRANITO",
        unit="m",
        unit_price=Decimal("40.00"),
    )
    catalog = _catalog([entry])
    assignments = _assignment_set(
        packet,
        catalog,
        [_assignment(rejected.id, status="rejected"), _assignment(included.id, code=entry.code)],
    )
    calc_plan = CalcPlan(
        plans=[
            ItemCalcPlan(
                item_id=rejected.id,
                blocks=[
                    CalcBlockPlan(
                        label="BLOCO",
                        recipe=CalcRecipe.DIRECT_QUANTITY,
                        operands=[
                            CalcOperand(name="QUANTIDADE", value=Decimal("10.00"), unit="m2")
                        ],
                    )
                ],
            )
        ]
    )

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet,
            assignments,
            catalog,
            worksite_key=_WORKSITE_KEY,
            worksite_name=_WORKSITE_NAME,
            calc_plan=calc_plan,
        )

    assert raised.value.code == "CALC_PLAN_UNKNOWN_ITEM"


def test_calc_plan_refuses_a_duplicated_item() -> None:
    block_plan = CalcBlockPlan(
        label="BLOCO",
        recipe=CalcRecipe.DIRECT_QUANTITY,
        operands=[CalcOperand(name="QUANTIDADE", value=Decimal("1.00"), unit="un")],
    )
    plan = ItemCalcPlan(item_id=_ITEM_1, blocks=[block_plan])

    with pytest.raises(ValidationError) as raised:
        CalcPlan(plans=[plan, plan])

    assert valuation_error_codes(raised.value) == ["CALC_PLAN_DUPLICATE_ITEM"]


def test_no_items_left_after_every_rejection_is_refused() -> None:
    item = _confirmed_item()
    packet = _packet([item])
    catalog = _catalog()
    assignments = _assignment_set(packet, catalog, [_assignment(item.id, status="rejected")])

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
        )

    assert raised.value.code == "CALC_NO_ITEMS"


def test_quantity_with_unsupported_scale_is_refused() -> None:
    item = _confirmed_item(quantity=Decimal("12.345"))
    packet = _packet([item])
    entry = _catalog_entry()
    catalog = _catalog([entry])
    assignments = _assignment_set(packet, catalog, [_assignment(item.id, code=entry.code)])

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
        )

    assert raised.value.code == "CALC_QUANTITY_SCALE_UNSUPPORTED"


# --------------------------------------------------------------------------------------
# dinheiro trunca, quantidade excluída, portão de exportação
# --------------------------------------------------------------------------------------


def test_money_is_truncated_not_rounded() -> None:
    item = _confirmed_item(label="ESCAVACAO SINTETICA", unit="m3", quantity=Decimal("1.15"))
    packet = _packet([item])
    entry = _catalog_entry(
        code="SP01050010(/)",
        description="ESCAVACAO SINTETICA MANUAL",
        unit="m3",
        unit_price=Decimal("10.30"),
    )
    catalog = _catalog([entry])
    assignments = _assignment_set(packet, catalog, [_assignment(item.id, code=entry.code)])

    result = build_worksite_bulletin(
        packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
    )

    assert result.bulletin.lines[0].total == Decimal("11.84")


def test_rejected_assignment_is_excluded_from_the_bulletin() -> None:
    included = _confirmed_item(
        item_id=_ITEM_1, label="MEIO FIO DE GRANITO", unit="m", quantity=Decimal("3.00")
    )
    rejected = _confirmed_item(
        item_id=_ITEM_2, label="ALAMBRADO GALVANIZADO", unit="m2", quantity=Decimal("10.00")
    )
    packet = _packet([included, rejected])
    entry = _catalog_entry(
        code="AD04100015(/)",
        description="MEIO FIO DE GRANITO",
        unit="m",
        unit_price=Decimal("40.00"),
    )
    catalog = _catalog([entry])
    assignments = _assignment_set(
        packet,
        catalog,
        [_assignment(included.id, code=entry.code), _assignment(rejected.id, status="rejected")],
    )

    result = build_worksite_bulletin(
        packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
    )

    assert result.excluded_item_ids == (rejected.id,)
    assert rejected.id not in result.item_numbers
    assert len(result.bulletin.lines) == 1


def test_valuation_speaks_to_the_export_gate_without_adapting() -> None:
    item = _confirmed_item(label="MEIO FIO DE GRANITO", unit="m", quantity=Decimal("3.00"))
    packet = _packet([item])
    entry = _catalog_entry(
        code="AD04100015(/)",
        description="MEIO FIO DE GRANITO SINTETICO",
        unit="m",
        unit_price=Decimal("40.00"),
    )
    catalog = _catalog([entry])
    assignments = _assignment_set(packet, catalog, [_assignment(item.id, code=entry.code)])
    contract = ContractWorkbook(
        source_label="MAPÃO SINTÉTICO (fixture)",
        source_sha256="d" * 64,
        period_numbers=[],
        lines=[
            ContractLine(
                group_label="PAVIMENTACAO",
                item_number="1",
                code=entry.code,
                description=entry.description,
                unit=entry.unit,
                unit_price=entry.unit_price,
                contract_quantity=Decimal("100.00"),
                amended_quantity=Decimal("100.00"),
                periods=[],
                accumulated_quantity=Decimal("0.00"),
                accumulated_amount=Decimal("0.00"),
                balance_quantity=Decimal("100.00"),
            )
        ],
    )

    valuation = build_worksite_valuation(
        packet,
        assignments,
        catalog,
        worksite_key=_WORKSITE_KEY,
        worksite_name=_WORKSITE_NAME,
        period_number=1,
        reference_label="JANEIRO/2026",
    )

    assert valuation.export_errors(contract) == ["VALUATION_NOT_APPROVED"]
