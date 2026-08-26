"""A quantidade confirmada manda: o plano de cálculo só explica como ela se decompõe."""

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
from croquito_valuation.calc import (
    DEFAULT_BLOCK_LABEL,
    DEFAULT_OPERAND_NAME,
    CalcBlockPlan,
    CalcPlan,
    ItemCalcPlan,
    build_worksite_bulletin,
    build_worksite_valuation,
)
from croquito_valuation.calc_matrix import (
    CalcContribution,
    CalcMatrix,
    ServiceContributions,
)
from croquito_valuation.contract import ContractLine, ContractWorkbook
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
        # Fixture no regime de pacote (`2.0.0`): cada item confirmado nasce com o pacote
        # FECHADO, que é o que a orçamentista faz quando o elemento dispara um serviço só.
        # Sem isso o boletim recusaria em `CALC_PACKAGE_NOT_CLOSED`, e com razão.
        closures=[
            ItemPackageClosure(item_id=item_id, decision=decision)
            # Um fechamento por ELEMENTO, não por par: o item que dispara dois serviços tem
            # dois assignments e um pacote só.
            for item_id, decision in {
                item.item_id: item.decision for item in assignments if item.status == "confirmed"
            }.items()
        ],
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


@pytest.mark.parametrize("origin", [PriceOrigin.SINAPI, PriceOrigin.SICRO])
def test_bulletin_refuses_a_catalog_whose_origin_is_sinapi_or_sicro(
    origin: PriceOrigin,
) -> None:
    """As origens novas do ADR-0039 caem na mesma recusa que a EMOP: SEMPRE SCO na
    medição licitada — SINAPI/SICRO/EMOP/composição só valem pré-licitação (F-026)."""
    item = _confirmed_item()
    packet = _packet([item])
    entry = PriceCatalogEntry(
        code="REF.001",
        description=f"ITEM SINTETICO {origin.name}",
        unit="m2",
        unit_price=Decimal("50.00"),
        family_code="CE",
        family_name=f"SERVICOS SINTETICOS {origin.name}",
        subgroup_code="CE0410",
        subgroup_name=f"ITENS SINTETICOS {origin.name}",
        origin=origin,
    )
    catalog = PriceCatalog(
        source_label=f"CATALOGO {origin.name} SINTETICO",
        reference_month="2026-01",
        source_sha256=_CATALOG_DIGEST,
        entries=[entry],
        origin=origin,
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


# --------------------------------------------------------------------------------------
# pacote de serviços: o boletim não é montado pela metade nem escolhe um dos códigos
# --------------------------------------------------------------------------------------


def _open_package_set(
    packet: TakeoffPacket, catalog: PriceCatalog, assignments: list[CodeAssignment]
) -> CodeAssignmentSet:
    """Conjunto no regime de pacote SEM fechamento — o estado normal entre dois lotes."""
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


def test_item_with_an_open_package_does_not_become_a_bulletin() -> None:
    """Sem o fechamento, o item pode estar pela metade — e meio boletim é número errado."""
    item = _confirmed_item()
    packet = _packet([item])
    entry = _catalog_entry()
    catalog = _catalog([entry])
    assignments = _open_package_set(packet, catalog, [_assignment(item.id, code=entry.code)])

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
        )

    assert raised.value.code == "CALC_PACKAGE_NOT_CLOSED"
    assert raised.value.details == {"item_ids": [item.id]}


def test_item_with_two_codes_refuses_instead_of_picking_one() -> None:
    """O portão temporário até a matriz existir (#78).

    O que ele impede não é uma exceção a mais: é o `{item_id: assignment}` de antes ficar com
    o último código e montar UMA linha, em silêncio, para um elemento que dispara dois
    serviços.
    """
    item = _confirmed_item()
    packet = _packet([item])
    first = _catalog_entry(code="CE04100010(/)")
    second = _catalog_entry(code="CE04100020(/)", description="TELA DO ALAMBRADO")
    catalog = _catalog([first, second])
    assignments = _assignment_set(
        packet,
        catalog,
        [_assignment(item.id, code=first.code), _assignment(item.id, code=second.code)],
    )

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
        )

    assert raised.value.code == "CALC_PACKAGE_NOT_SUPPORTED"
    assert raised.value.details == {"item_ids": [item.id]}


def test_a_legacy_set_still_builds_the_same_bulletin() -> None:
    """Rodada gravada antes do ADR-0053 não tem fechamento e não precisa de nenhum."""
    item = _confirmed_item()
    packet = _packet([item])
    entry = _catalog_entry()
    catalog = _catalog([entry])
    legacy = CodeAssignmentSet(
        schema_version="1.0.0",
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=catalog.source_sha256,
        assignments=[_assignment(item.id, code=entry.code)],
        safety_notes=[
            "Confirmação de código é ato humano rastreável; a sugestão lexical nunca "
            "confirma sozinha.",
            "Preço e unidade impressos continuam sendo conferidos contra catálogo e "
            "contrato no portão de exportação.",
        ],
    )

    result = build_worksite_bulletin(
        packet, legacy, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
    )

    assert [line.item_number for line in result.bulletin.lines] == ["1"]
    assert result.bulletin.lines[0].unit_price == entry.unit_price


# --------------------------------------------------------------------------------------
# regime da matriz (T6): o builder itera SERVIÇOS, não itens
# --------------------------------------------------------------------------------------

_SAIBRO = "BP04050350(/)"
_ITEM_3 = "ti_0000000000000003"
_PACOTE_PISO = (
    "MT14150050(A)",
    "BP04050350(/)",
    "ET39050109(/)",
    "BP09100050(B)",
    "SC34150200(/)",
    "SC29100100(A)",
)


def _full_contribution(item_id: str, *, value: Decimal, label: str) -> CalcContribution:
    return CalcContribution(
        source_item_id=item_id,
        label=label,
        basis=ContributionBasis.FULL,
        recipe=CalcRecipe.DECLARED_PRODUCT,
        operands=[CalcOperand(name="AREA", value=value, unit="m2")],
    )


def test_matrix_regime_fuses_many_elements_into_one_service_line() -> None:
    # Três elementos alimentam o mesmo serviço: uma linha, quantidade = soma das parcelas.
    items = [
        _confirmed_item(item_id=_ITEM_1, label="PISO EM CONCRETO", quantity=Decimal("418.12")),
        _confirmed_item(item_id=_ITEM_2, label="PAVIMENTO INTERTRAVADO", quantity=Decimal("59.34")),
        _confirmed_item(item_id=_ITEM_3, label="FORRACAO EM GRAMA", quantity=Decimal("1.28")),
    ]
    packet = _packet(items)
    catalog = _catalog([_catalog_entry(code=_SAIBRO, unit="m2")])
    assignments = _assignment_set(
        packet,
        catalog,
        [
            _assignment(_ITEM_1, code=_SAIBRO),
            _assignment(_ITEM_2, code=_SAIBRO),
            _assignment(_ITEM_3, code=_SAIBRO),
        ],
    )
    matrix = CalcMatrix(
        services=[
            ServiceContributions(
                code=_SAIBRO,
                contributions=[
                    _full_contribution(_ITEM_1, value=Decimal("418.12"), label="PISO EM CONCRETO"),
                    _full_contribution(
                        _ITEM_2, value=Decimal("59.34"), label="PAVIMENTO INTERTRAVADO"
                    ),
                    _full_contribution(_ITEM_3, value=Decimal("1.28"), label="FORRACAO EM GRAMA"),
                ],
            )
        ]
    )

    result = build_worksite_bulletin(
        packet,
        assignments,
        catalog,
        worksite_key=_WORKSITE_KEY,
        worksite_name=_WORKSITE_NAME,
        calc_matrix=matrix,
    )

    # Uma linha só, com a soma das três parcelas (418,12 + 59,34 + 1,28 = 478,74).
    assert [line.code for line in result.bulletin.lines] == [_SAIBRO]
    assert result.bulletin.lines[0].quantity == Decimal("478.74")
    assert result.service_numbers == {_SAIBRO: "1"}
    assert result.item_numbers == {}
    sheet = result.calc_sheets[0]
    assert len(sheet.blocks) == 3
    assert sheet.total_quantity == Decimal("478.74")


def test_matrix_regime_expands_one_element_into_many_service_lines() -> None:
    # Um elemento (PISO EM CONCRETO) dispara a pilha construtiva inteira: seis linhas.
    piso = _confirmed_item(item_id=_ITEM_1, label="PISO EM CONCRETO", quantity=Decimal("418.12"))
    packet = _packet([piso])
    catalog = _catalog([_catalog_entry(code=code, unit="m2") for code in _PACOTE_PISO])
    assignments = _assignment_set(
        packet, catalog, [_assignment(_ITEM_1, code=code) for code in _PACOTE_PISO]
    )
    matrix = CalcMatrix(
        services=[
            ServiceContributions(
                code=code,
                contributions=[
                    _full_contribution(_ITEM_1, value=Decimal("418.12"), label="PISO EM CONCRETO")
                ],
            )
            for code in _PACOTE_PISO
        ]
    )

    result = build_worksite_bulletin(
        packet,
        assignments,
        catalog,
        worksite_key=_WORKSITE_KEY,
        worksite_name=_WORKSITE_NAME,
        calc_matrix=matrix,
    )

    assert len(result.bulletin.lines) == 6
    assert {line.code for line in result.bulletin.lines} == set(_PACOTE_PISO)
    assert len(result.service_numbers) == 6
    assert all(line.quantity == Decimal("418.12") for line in result.bulletin.lines)


def test_a_package_without_a_matrix_is_still_refused() -> None:
    # Sem matriz, um item com dois códigos não pode virar boletim: escolher em silêncio é o
    # defeito que a F-038 ataca. O portão continua no regime legado.
    item = _confirmed_item(item_id=_ITEM_1, quantity=Decimal("10.00"))
    packet = _packet([item])
    catalog = _catalog([_catalog_entry(code=_SAIBRO), _catalog_entry(code="MT14150050(A)")])
    assignments = _assignment_set(
        packet,
        catalog,
        [_assignment(_ITEM_1, code=_SAIBRO), _assignment(_ITEM_1, code="MT14150050(A)")],
    )

    with pytest.raises(ValuationValidationError) as raised:
        build_worksite_bulletin(
            packet, assignments, catalog, worksite_key=_WORKSITE_KEY, worksite_name=_WORKSITE_NAME
        )

    assert raised.value.code == "CALC_PACKAGE_NOT_SUPPORTED"
