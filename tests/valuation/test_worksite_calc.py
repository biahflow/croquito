"""O boletim da praça: união das folhas, fusão declarada e recusa com folha pendente.

O teste que manda nesta suíte é o primeiro: praça de uma folha tem de responder EXATAMENTE
como a rodada de prancha única de hoje — mesmo boletim, mesma memória, mesmo digest. Ele não
compara com um retrato gravado, e sim com o resultado do builder de hoje
(`calc.build_worksite_valuation`) rodando lado a lado, para que qualquer mudança futura no
caminho de uma folha tenha de mover as duas cadeias juntas ou reprovar aqui.
"""

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
    CalcBlockPlan,
    CalcPlan,
    ItemCalcPlan,
    build_worksite_valuation,
)
from croquito_valuation.calc_matrix import (
    FUSED_BLOCK_LABEL_PREFIX,
    FUSED_READING_OPERAND,
    CalcContribution,
    CalcMatrix,
    ServiceContributions,
)
from croquito_valuation.contract import ContractLine, ContractWorkbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    CalcOperand,
    CalcRecipe,
    ContributionBasis,
    PriceCatalog,
    PriceCatalogEntry,
    ReviewerDecision,
    Valuation,
)
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_valuation.template import default_template
from croquito_valuation.workbook_writer import WorkbookPlan, plan_workbook
from croquito_valuation.worksite_calc import (
    WorksitePlateInput,
    build_worksite_takeoff_bulletins,
    build_worksite_takeoff_valuation,
)
from croquito_valuation.worksite_takeoff import (
    TakeoffItemAddress,
    TakeoffItemIdentityLink,
    build_worksite_takeoff,
)

_WORKSITE_KEY = "praca-sintetica-norte"
_WORKSITE_NAME = "PRACA NORTE"
# As praças deste produto, como elas se chamam. Nome real é o caso que a aba de 31
# caracteres aperta: "Campo do Morro da Bandeira" tem 26 e `MEMÓRIA ` come 8.
_PRACAS_REAIS = (
    "Campo do Guaxindiba",
    "Praça Noel de Carvalho",
    "Praça Raul Campelo",
    "Campo do Morro da Bandeira",
    "Praça das Casinhas",
    "Campo da Toca",
)
_PLATE_A = "praca-sintetica-norte-prancha-01"
_PLATE_B = "praca-sintetica-norte-prancha-02"
_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64
_PDF_DIGEST = "d" * 64
_CATALOG_DIGEST = "c" * 64
_REVIEWER = "orcamentista-sintetico"
_DECIDED_AT = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)

_ITEM_A1 = "ti_00000000000000a1"[:19]
_ITEM_A2 = "ti_00000000000000a2"[:19]
_ITEM_B1 = "ti_00000000000000b1"[:19]
_ITEM_B2 = "ti_00000000000000b2"[:19]

_PISO = "AD04050050(/)"
_MEIO_FIO = "AD04100015(/)"
_TRANSPORTE = "SP01050010(/)"
_PISO_PRICE = Decimal("89.30")
_MEIO_FIO_PRICE = Decimal("40.00")
_TRANSPORTE_PRICE = Decimal("2.50")

_DIGEST_BY_PLATE = {_PLATE_A: _DIGEST_A, _PLATE_B: _DIGEST_B}


def _decision(action: Literal["confirm", "reject"] = "confirm") -> ReviewerDecision:
    return ReviewerDecision(
        decision_id="vd_0123456789abcdef",
        action=action,
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
    )


def _item(
    *,
    plate_id: str,
    item_id: str,
    label: str = "PISO INTERTRAVADO SINTETICO",
    unit: str = "m2",
    quantity: Decimal | None = Decimal("200.00"),
    status: TakeoffItemStatus = TakeoffItemStatus.CONFIRMED,
) -> TakeoffItem:
    return TakeoffItem(
        id=item_id,
        evidence=PlateEvidence(
            plate_id=plate_id,
            page_number=1,
            image_sha256=_DIGEST_BY_PLATE[plate_id],
            bbox=PlateBox(left=10, top=10, right=110, bottom=60),
        ),
        raw_text=f"{label} {quantity} {unit}",
        label=label,
        quantity=quantity if status is TakeoffItemStatus.CONFIRMED else None,
        unit=unit,
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=status,
        decision=_decision() if status is TakeoffItemStatus.CONFIRMED else None,
    )


def _packet(plate_id: str, items: list[TakeoffItem]) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=plate_id,
        page_number=1,
        image_sha256=_DIGEST_BY_PLATE[plate_id],
        source_pdf_sha256=_PDF_DIGEST,
        items=items,
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _entry(code: str, description: str, unit: str, unit_price: Decimal) -> PriceCatalogEntry:
    return PriceCatalogEntry(
        code=code,
        description=description,
        unit=unit,
        unit_price=unit_price,
        family_code="AD",
        family_name="SERVICOS SINTETICOS",
        subgroup_code="AD0405",
        subgroup_name="ITENS SINTETICOS",
    )


def _catalog() -> PriceCatalog:
    return PriceCatalog(
        source_label="CATALOGO SINTETICO",
        reference_month="2026-01",
        source_sha256=_CATALOG_DIGEST,
        entries=[
            _entry(_PISO, "PISO INTERTRAVADO SINTETICO 6CM", "m2", _PISO_PRICE),
            _entry(_MEIO_FIO, "MEIO FIO DE GRANITO SINTETICO", "m", _MEIO_FIO_PRICE),
            _entry(_TRANSPORTE, "TRANSPORTE DE MATERIAL SINTETICO", "m2", _TRANSPORTE_PRICE),
        ],
    )


def _assignments(
    packet: TakeoffPacket,
    pairs: list[tuple[str, str]],
    *,
    closed_item_ids: set[str] | None = None,
) -> CodeAssignmentSet:
    """Conjunto no regime de pacote: um assignment por par e um fechamento por elemento."""
    item_ids = sorted({item_id for item_id, _ in pairs})
    closed = item_ids if closed_item_ids is None else sorted(closed_item_ids)
    return CodeAssignmentSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=_CATALOG_DIGEST,
        assignments=[
            CodeAssignment(
                item_id=item_id,
                status="confirmed",
                code=code,
                unit_compatible=True,
                decision=_decision(),
            )
            for item_id, code in pairs
        ],
        closures=[ItemPackageClosure(item_id=item_id, decision=_decision()) for item_id in closed],
        safety_notes=[
            "Confirmação de código é ato humano rastreável; a sugestão lexical nunca "
            "confirma sozinha.",
            "Preço e unidade impressos continuam sendo conferidos contra catálogo e "
            "contrato no portão de exportação.",
        ],
    )


def _link(kept: tuple[str, str], discarded: tuple[str, str]) -> TakeoffItemIdentityLink:
    return TakeoffItemIdentityLink(
        kept=TakeoffItemAddress(plate_id=kept[0], item_id=kept[1]),
        discarded=TakeoffItemAddress(plate_id=discarded[0], item_id=discarded[1]),
        declared_by=_REVIEWER,
        declared_at=_DECIDED_AT,
        note="mesma quadra na planta geral e no detalhe",
    )


def _two_plate_inputs(
    *,
    quantity_a: Decimal = Decimal("200.00"),
    quantity_b: Decimal = Decimal("50.00"),
    pending_on_b: bool = False,
    closed_on_b: bool = True,
) -> tuple[WorksitePlateInput, WorksitePlateInput]:
    """Duas folhas com o MESMO serviço lido em cada uma; a folha B traz também o meio-fio."""
    packet_a = _packet(_PLATE_A, [_item(plate_id=_PLATE_A, item_id=_ITEM_A1, quantity=quantity_a)])
    items_b = [
        _item(
            plate_id=_PLATE_B,
            item_id=_ITEM_B1,
            quantity=quantity_b,
            status=(TakeoffItemStatus.PROPOSED if pending_on_b else TakeoffItemStatus.CONFIRMED),
        ),
        _item(
            plate_id=_PLATE_B,
            item_id=_ITEM_B2,
            label="MEIO FIO DE GRANITO",
            unit="m",
            quantity=Decimal("30.00"),
        ),
    ]
    packet_b = _packet(_PLATE_B, items_b)
    pairs_b = [(_ITEM_B2, _MEIO_FIO)]
    if not pending_on_b:
        pairs_b.insert(0, (_ITEM_B1, _PISO))
    closed_b = {_ITEM_B2} | ({_ITEM_B1} if closed_on_b and not pending_on_b else set())
    return (
        WorksitePlateInput(
            packet=packet_a, assignments=_assignments(packet_a, [(_ITEM_A1, _PISO)])
        ),
        WorksitePlateInput(
            packet=packet_b, assignments=_assignments(packet_b, pairs_b, closed_item_ids=closed_b)
        ),
    )


def _contract() -> ContractWorkbook:
    return ContractWorkbook(
        source_label="MAPÃO SINTÉTICO (fixture)",
        source_sha256="e" * 64,
        period_numbers=[],
        lines=[
            ContractLine(
                group_label="PAVIMENTACAO",
                item_number="1",
                code=_PISO,
                description="PISO INTERTRAVADO SINTETICO 6CM",
                unit="m2",
                unit_price=_PISO_PRICE,
                contract_quantity=Decimal("500.00"),
                periods=[],
                accumulated_quantity=Decimal("0.00"),
                accumulated_amount=Decimal("0.00"),
            ),
            ContractLine(
                group_label="PAVIMENTACAO",
                item_number="2",
                code=_MEIO_FIO,
                description="MEIO FIO DE GRANITO SINTETICO",
                unit="m",
                unit_price=_MEIO_FIO_PRICE,
                contract_quantity=Decimal("200.00"),
                periods=[],
                accumulated_quantity=Decimal("0.00"),
                accumulated_amount=Decimal("0.00"),
            ),
        ],
    )


# --------------------------------------------------------------------------------------
# praça de UMA folha é a rodada de hoje
# --------------------------------------------------------------------------------------


def test_single_plate_worksite_is_byte_identical_to_the_single_plate_valuation() -> None:
    """Critério 6: consolidado de um pacote é a rodada de hoje, até o digest."""
    item = _item(plate_id=_PLATE_A, item_id=_ITEM_A1, quantity=Decimal("200.00"))
    packet = _packet(_PLATE_A, [item])
    assignments = _assignments(packet, [(_ITEM_A1, _PISO)])
    catalog = _catalog()
    calc_plan = CalcPlan(
        plans=[
            ItemCalcPlan(
                item_id=_ITEM_A1,
                blocks=[
                    CalcBlockPlan(
                        label="QUADRA NORTE",
                        recipe=CalcRecipe.LENGTH_TIMES_WIDTH,
                        operands=[
                            CalcOperand(name="COMPRIMENTO", value=Decimal("20.00"), unit="m"),
                            CalcOperand(name="LARGURA", value=Decimal("10.00"), unit="m"),
                        ],
                    )
                ],
            )
        ]
    )
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [packet])

    today = build_worksite_valuation(
        packet,
        assignments,
        catalog,
        worksite_key=_WORKSITE_KEY,
        worksite_name=_WORKSITE_NAME,
        period_number=1,
        reference_label="JANEIRO/2026",
        calc_plan=calc_plan,
    )
    consolidated = build_worksite_takeoff_valuation(
        worksite,
        [WorksitePlateInput(packet=packet, assignments=assignments, calc_plan=calc_plan)],
        catalog,
        worksite_name=_WORKSITE_NAME,
        period_number=1,
        reference_label="JANEIRO/2026",
    )

    assert consolidated.model_dump(mode="json", exclude={"id"}) == today.model_dump(
        mode="json", exclude={"id"}
    )
    # O `id` é UUIDv7 novo a cada build, então o digest só é comparável com os dois alinhados.
    aligned = today.model_copy(update={"id": consolidated.id})
    assert aligned.content_digest() == consolidated.content_digest()


def test_single_plate_worksite_keeps_the_worksite_key_and_name_without_suffix() -> None:
    packet = _packet(_PLATE_A, [_item(plate_id=_PLATE_A, item_id=_ITEM_A1)])
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [packet])

    result = build_worksite_takeoff_bulletins(
        worksite,
        [WorksitePlateInput(packet=packet, assignments=_assignments(packet, [(_ITEM_A1, _PISO)]))],
        _catalog(),
        worksite_name=_WORKSITE_NAME,
    )

    assert [plate.worksite_key for plate in result.plates] == [_WORKSITE_KEY]
    assert result.bulletins[0].worksite_name == _WORKSITE_NAME
    assert result.fusions == ()


# --------------------------------------------------------------------------------------
# sem declaração, as duas leituras contam
# --------------------------------------------------------------------------------------


def test_without_a_declaration_the_repeated_item_contributes_twice_from_named_plates() -> None:
    """Critério 4: o fail-closed erra para o lado de somar demais, e visivelmente."""
    plate_a, plate_b = _two_plate_inputs()
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [plate_a.packet, plate_b.packet])

    result = build_worksite_takeoff_bulletins(
        worksite, [plate_a, plate_b], _catalog(), worksite_name=_WORKSITE_NAME
    )

    assert [plate.plate_id for plate in result.plates] == [_PLATE_A, _PLATE_B]
    assert [plate.worksite_key for plate in result.plates] == [
        f"{_WORKSITE_KEY}-p1",
        f"{_WORKSITE_KEY}-p2",
    ]
    measured = [
        (plate.plate_id, line.code, line.quantity)
        for plate in result.plates
        for line in plate.bulletin.lines
    ]
    assert measured == [
        (_PLATE_A, _PISO, Decimal("200.00")),
        (_PLATE_B, _PISO, Decimal("50.00")),
        (_PLATE_B, _MEIO_FIO, Decimal("30.00")),
    ]
    assert result.total_amount == Decimal("250.00") * _PISO_PRICE + Decimal("30.00") * (
        _MEIO_FIO_PRICE
    )


def test_the_memory_of_each_plate_reproduces_the_worksite_total() -> None:
    """Critério 7: o total sai da memória, folha a folha, sem número que não esteja lá."""
    plate_a, plate_b = _two_plate_inputs()
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [plate_a.packet, plate_b.packet])
    catalog = _catalog()

    result = build_worksite_takeoff_bulletins(
        worksite, [plate_a, plate_b], catalog, worksite_name=_WORKSITE_NAME
    )

    from_memory = Decimal("0.00")
    for plate in result.plates:
        sheets = {sheet.item_number: sheet for sheet in plate.calc_sheets}
        for line in plate.bulletin.lines:
            sheet = sheets[line.item_number]
            assert sheet.worksite_key == plate.worksite_key
            assert sheet.total_quantity == line.quantity
            from_memory += (
                sum((block.subtotal for block in sheet.blocks), Decimal("0.00"))
                * catalog.entry_for(line.code).unit_price
            )
    assert from_memory == result.total_amount


# --------------------------------------------------------------------------------------
# fusão declarada
# --------------------------------------------------------------------------------------


def test_declared_fusion_counts_once_and_keeps_the_discarded_reading_in_the_memory() -> None:
    """Critério 3: a leitura absorvida continua impressa, com a quantidade, marcada."""
    plate_a, plate_b = _two_plate_inputs()
    worksite = build_worksite_takeoff(
        _WORKSITE_KEY,
        [plate_a.packet, plate_b.packet],
        [_link(kept=(_PLATE_A, _ITEM_A1), discarded=(_PLATE_B, _ITEM_B1))],
    )

    result = build_worksite_takeoff_bulletins(
        worksite, [plate_a, plate_b], _catalog(), worksite_name=_WORKSITE_NAME
    )

    folha_a, folha_b = result.plates
    assert folha_a.bulletin.lines[0].quantity == Decimal("200.00")
    fused_line = next(line for line in folha_b.bulletin.lines if line.code == _PISO)
    assert fused_line.quantity == Decimal("0.00")
    assert fused_line.total == Decimal("0.00")
    assert folha_b.build.fused_item_ids == (_ITEM_B1,)

    fused_sheet = next(
        sheet for sheet in folha_b.calc_sheets if sheet.item_number == fused_line.item_number
    )
    block = fused_sheet.blocks[0]
    assert block.label.startswith(f"{FUSED_BLOCK_LABEL_PREFIX}{_PLATE_A}")
    assert block.operands[0].name == FUSED_READING_OPERAND
    assert block.operands[0].value == Decimal("50.00")
    assert block.subtotal == Decimal("0.00")
    assert fused_sheet.total_quantity == Decimal("0.00")

    # O total da praça é o da leitura que fica, uma vez só.
    assert result.total_amount == Decimal("200.00") * _PISO_PRICE + Decimal("30.00") * (
        _MEIO_FIO_PRICE
    )


def test_the_same_item_id_on_two_plates_is_two_elements_until_declared() -> None:
    """Critério 2: a identidade é `(plate_id, item_id, code)` — o `ti_` colide entre folhas.

    O id de item só é único DENTRO do pacote (ADR-0057, decisão 5), então duas folhas podem
    cunhar exatamente o mesmo `ti_...`. Sem declaração são dois elementos da obra e as duas
    parcelas contam; com a declaração, só a folha do lado descartado é zerada — o elemento
    homônimo da outra folha não é tocado.
    """
    shared = _ITEM_A1
    packet_a = _packet(
        _PLATE_A, [_item(plate_id=_PLATE_A, item_id=shared, quantity=Decimal("200.00"))]
    )
    packet_b = _packet(
        _PLATE_B, [_item(plate_id=_PLATE_B, item_id=shared, quantity=Decimal("50.00"))]
    )
    plate_a = WorksitePlateInput(
        packet=packet_a, assignments=_assignments(packet_a, [(shared, _PISO)])
    )
    plate_b = WorksitePlateInput(
        packet=packet_b, assignments=_assignments(packet_b, [(shared, _PISO)])
    )
    packets = [packet_a, packet_b]

    both = build_worksite_takeoff_bulletins(
        build_worksite_takeoff(_WORKSITE_KEY, packets),
        [plate_a, plate_b],
        _catalog(),
        worksite_name=_WORKSITE_NAME,
    )
    assert [line.quantity for plate in both.plates for line in plate.bulletin.lines] == [
        Decimal("200.00"),
        Decimal("50.00"),
    ]

    declared = build_worksite_takeoff_bulletins(
        build_worksite_takeoff(
            _WORKSITE_KEY, packets, [_link(kept=(_PLATE_A, shared), discarded=(_PLATE_B, shared))]
        ),
        [plate_a, plate_b],
        _catalog(),
        worksite_name=_WORKSITE_NAME,
    )
    assert [line.quantity for plate in declared.plates for line in plate.bulletin.lines] == [
        Decimal("200.00"),
        Decimal("0.00"),
    ]
    assert declared.plates[0].build.fused_item_ids == ()
    assert declared.plates[1].build.fused_item_ids == (shared,)


def test_fusion_uses_the_kept_quantity_and_reports_the_difference() -> None:
    """Critério 8: quantidades diferentes não são erro; a diferença é informação."""
    plate_a, plate_b = _two_plate_inputs(quantity_a=Decimal("200.00"), quantity_b=Decimal("180.00"))
    worksite = build_worksite_takeoff(
        _WORKSITE_KEY,
        [plate_a.packet, plate_b.packet],
        [_link(kept=(_PLATE_A, _ITEM_A1), discarded=(_PLATE_B, _ITEM_B1))],
    )

    result = build_worksite_takeoff_bulletins(
        worksite, [plate_a, plate_b], _catalog(), worksite_name=_WORKSITE_NAME
    )

    (fusion,) = result.fusions
    assert fusion.kept_quantity == Decimal("200.00")
    assert fusion.discarded_quantity == Decimal("180.00")
    assert fusion.difference == Decimal("20.00")
    measured_piso = sum(
        (
            line.quantity
            for plate in result.plates
            for line in plate.bulletin.lines
            if line.code == _PISO
        ),
        Decimal("0.00"),
    )
    assert measured_piso == Decimal("200.00")
    # A leitura descartada continua impressa com os 180,00 que a orçamentista leu.
    folha_b = result.plates[1]
    fused_sheet = folha_b.calc_sheets[0]
    assert fused_sheet.blocks[0].operands[0].value == Decimal("180.00")


def test_fused_item_does_not_need_a_package_closure_of_its_own() -> None:
    """Critério 2: o pacote é do ELEMENTO DA OBRA, e o fundido é fechado uma vez."""
    plate_a, plate_b = _two_plate_inputs(closed_on_b=False)
    packets = [plate_a.packet, plate_b.packet]

    with pytest.raises(ValuationValidationError) as without_link:
        build_worksite_takeoff_bulletins(
            build_worksite_takeoff(_WORKSITE_KEY, packets),
            [plate_a, plate_b],
            _catalog(),
            worksite_name=_WORKSITE_NAME,
        )
    assert without_link.value.code == "CALC_PACKAGE_NOT_CLOSED"
    assert without_link.value.details["item_ids"] == [_ITEM_B1]

    fused = build_worksite_takeoff(
        _WORKSITE_KEY,
        packets,
        [_link(kept=(_PLATE_A, _ITEM_A1), discarded=(_PLATE_B, _ITEM_B1))],
    )
    result = build_worksite_takeoff_bulletins(
        fused, [plate_a, plate_b], _catalog(), worksite_name=_WORKSITE_NAME
    )
    assert result.plates[1].build.fused_item_ids == (_ITEM_B1,)


def test_fusion_over_a_reading_that_is_not_confirmed_is_refused() -> None:
    """Fundir sobre leitura não confirmada perderia o elemento inteiro, em silêncio."""
    plate_a, plate_b = _two_plate_inputs()
    rejected = _item(plate_id=_PLATE_A, item_id=_ITEM_A2, quantity=Decimal("10.00"))
    rejected = rejected.model_copy(
        update={
            "status": TakeoffItemStatus.REJECTED,
            "decision": _decision("reject"),
            "quantity": None,
        }
    )
    packet_a = _packet(_PLATE_A, [*plate_a.packet.items, rejected])
    plate_a = WorksitePlateInput(packet=packet_a, assignments=plate_a.assignments)
    worksite = build_worksite_takeoff(
        _WORKSITE_KEY,
        [packet_a, plate_b.packet],
        [_link(kept=(_PLATE_A, _ITEM_A2), discarded=(_PLATE_B, _ITEM_B1))],
    )

    with pytest.raises(ValuationValidationError) as error:
        build_worksite_takeoff_bulletins(
            worksite, [plate_a, plate_b], _catalog(), worksite_name=_WORKSITE_NAME
        )

    assert error.value.code == "WORKSITE_TAKEOFF_LINK_TARGET_NOT_CONFIRMED"
    assert error.value.details["addresses"] == [f"{_PLATE_A}:{_ITEM_A2}"]


# --------------------------------------------------------------------------------------
# fusão no regime da matriz
# --------------------------------------------------------------------------------------


def test_fusion_in_the_matrix_regime_zeroes_only_the_fused_contribution() -> None:
    """A parcela derivada (transporte) resolve DEPOIS da fusão, não antes."""
    plate_a, plate_b = _two_plate_inputs()
    matrix_b = CalcMatrix(
        services=[
            ServiceContributions(
                code=_PISO,
                contributions=[
                    CalcContribution(
                        source_item_id=_ITEM_B1,
                        label="PISO DO DETALHE",
                        basis=ContributionBasis.FULL,
                        recipe=CalcRecipe.DIRECT_QUANTITY,
                        operands=[
                            CalcOperand(name="QUANTIDADE", value=Decimal("50.00"), unit="m2")
                        ],
                    )
                ],
            ),
            ServiceContributions(
                code=_MEIO_FIO,
                contributions=[
                    CalcContribution(
                        source_item_id=_ITEM_B2,
                        label="MEIO FIO DO DETALHE",
                        basis=ContributionBasis.FULL,
                        recipe=CalcRecipe.DIRECT_QUANTITY,
                        operands=[CalcOperand(name="QUANTIDADE", value=Decimal("30.00"), unit="m")],
                    )
                ],
            ),
            ServiceContributions(
                code=_TRANSPORTE,
                contributions=[
                    CalcContribution(
                        label="TRANSPORTE DO PISO",
                        basis=ContributionBasis.DEPENDENT,
                        recipe=CalcRecipe.DECLARED_PRODUCT,
                        operands=[CalcOperand(name="COEFICIENTE", value=Decimal("1.00"))],
                        depends_on_code=_PISO,
                    )
                ],
            ),
        ]
    )
    plate_b = WorksitePlateInput(
        packet=plate_b.packet,
        assignments=_assignments(
            plate_b.packet,
            [(_ITEM_B1, _PISO), (_ITEM_B2, _MEIO_FIO), (_ITEM_B2, _TRANSPORTE)],
        ),
        calc_matrix=matrix_b,
    )
    worksite = build_worksite_takeoff(
        _WORKSITE_KEY,
        [plate_a.packet, plate_b.packet],
        [_link(kept=(_PLATE_A, _ITEM_A1), discarded=(_PLATE_B, _ITEM_B1))],
    )

    result = build_worksite_takeoff_bulletins(
        worksite, [plate_a, plate_b], _catalog(), worksite_name=_WORKSITE_NAME
    )

    quantities = {line.code: line.quantity for line in result.plates[1].bulletin.lines}
    assert quantities[_PISO] == Decimal("0.00")
    assert quantities[_MEIO_FIO] == Decimal("30.00")
    # O transporte deriva do piso: fundido o piso, ele não pode transportar 50,00 m².
    assert quantities[_TRANSPORTE] == Decimal("0.00")


# --------------------------------------------------------------------------------------
# a praça falha fechado
# --------------------------------------------------------------------------------------


def test_pending_item_in_any_plate_blocks_the_worksite_bulletin() -> None:
    """Critério 5: uma folha a menos é meia praça, e meia praça parece uma praça inteira."""
    plate_a, plate_b = _two_plate_inputs(pending_on_b=True)
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [plate_a.packet, plate_b.packet])

    with pytest.raises(ValuationValidationError) as error:
        build_worksite_takeoff_bulletins(
            worksite, [plate_a, plate_b], _catalog(), worksite_name=_WORKSITE_NAME
        )

    assert error.value.code == "WORKSITE_TAKEOFF_PLATE_PENDING"
    assert error.value.details["plate_ids"] == [_PLATE_B]
    assert error.value.details["pending_by_plate"] == {_PLATE_B: 1}


def test_plate_of_the_consolidated_without_a_packet_is_refused() -> None:
    plate_a, plate_b = _two_plate_inputs()
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [plate_a.packet, plate_b.packet])

    with pytest.raises(ValuationValidationError) as error:
        build_worksite_takeoff_bulletins(
            worksite, [plate_a], _catalog(), worksite_name=_WORKSITE_NAME
        )

    assert error.value.code == "WORKSITE_PACKET_MISSING"
    assert error.value.details["plate_id"] == _PLATE_B


def test_packet_outside_the_consolidated_is_refused() -> None:
    plate_a, plate_b = _two_plate_inputs()
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [plate_a.packet])

    with pytest.raises(ValuationValidationError) as error:
        build_worksite_takeoff_bulletins(
            worksite, [plate_a, plate_b], _catalog(), worksite_name=_WORKSITE_NAME
        )

    assert error.value.code == "WORKSITE_TAKEOFF_PLATE_UNKNOWN"
    assert error.value.details["plate_ids"] == [_PLATE_B]


def test_the_same_plate_delivered_twice_is_refused() -> None:
    plate_a, _ = _two_plate_inputs()
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [plate_a.packet])

    with pytest.raises(ValuationValidationError) as error:
        build_worksite_takeoff_bulletins(
            worksite, [plate_a, plate_a], _catalog(), worksite_name=_WORKSITE_NAME
        )

    assert error.value.code == "WORKSITE_TAKEOFF_DUPLICATE_PLATE"
    assert error.value.details["plate_ids"] == [_PLATE_A]


def test_worksite_key_that_does_not_fit_the_plate_suffix_is_refused() -> None:
    long_key = "praca-" + "n" * 58
    plate_a, plate_b = _two_plate_inputs()
    worksite = build_worksite_takeoff(long_key, [plate_a.packet, plate_b.packet])

    with pytest.raises(ValuationValidationError) as error:
        build_worksite_takeoff_bulletins(
            worksite, [plate_a, plate_b], _catalog(), worksite_name=_WORKSITE_NAME
        )

    assert error.value.code == "WORKSITE_TAKEOFF_PLATE_LABEL_TOO_LONG"


# --------------------------------------------------------------------------------------
# praça de nome real chega até a pasta
# --------------------------------------------------------------------------------------


def _single_plate_input() -> WorksitePlateInput:
    packet = _packet(_PLATE_A, [_item(plate_id=_PLATE_A, item_id=_ITEM_A1)])
    return WorksitePlateInput(packet=packet, assignments=_assignments(packet, [(_ITEM_A1, _PISO)]))


def _named_worksite_plan(worksite_name: str, *, plates: int) -> WorkbookPlan:
    """A pasta planejada de uma praça com este nome e este tanto de folhas."""
    inputs = [_single_plate_input()] if plates == 1 else list(_two_plate_inputs()[:plates])
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [plate.packet for plate in inputs])
    catalog = _catalog()
    valuation = build_worksite_takeoff_valuation(
        worksite,
        inputs,
        catalog,
        worksite_name=worksite_name,
        period_number=1,
        reference_label="JANEIRO/2026",
    )
    return plan_workbook(valuation, catalog, default_template(), _contract())


@pytest.mark.parametrize("worksite_name", _PRACAS_REAIS)
@pytest.mark.parametrize("plates", [1, 2])
def test_a_worksite_with_a_real_name_reaches_the_workbook(worksite_name: str, plates: int) -> None:
    """Critério 2: praça de nome real exporta, com uma folha e com duas.

    Antes desta tarefa "Campo do Morro da Bandeira" reprovava em `SHEET_NAME_TOO_LONG` já
    na primeira folha, e a recusa só aparecia ao publicar o `.xlsx`.
    """
    plan = _named_worksite_plan(worksite_name, plates=plates)

    sheets = [sheet for sheet in plan.sheets if sheet.kind in {"bulletin", "memory"}]
    assert len(sheets) == 2 * plates
    assert all(len(sheet.name) <= 31 for sheet in sheets)
    # Critério 5: nome encurtado não funde duas folhas numa aba só.
    assert len({sheet.name for sheet in sheets}) == 2 * plates


@pytest.mark.parametrize("plates", [1, 2])
def test_the_whole_name_stays_inside_the_sheet_when_the_tab_shortens(plates: int) -> None:
    """Critério 3: o rótulo da aba encurta, o nome da praça e da folha não."""
    plan = _named_worksite_plan("Campo do Morro da Bandeira", plates=plates)

    esperado = {
        "Campo do Morro da Bandeira" if plates == 1 else f"Campo do Morro da Bandeira P{n}"
        for n in range(1, plates + 1)
    }
    for kind in ("bulletin", "memory"):
        impresso = {
            cell.text
            for sheet in plan.sheets
            if sheet.kind == kind
            for cell in sheet.cells
            if cell.role == "header_value" and cell.text in esperado
        }
        assert impresso == esperado


def test_a_single_plate_worksite_keeps_the_sheet_names_it_has_today() -> None:
    """Critério 4: a pasta que a prefeitura já recebe não muda de nome de aba."""
    plan = _named_worksite_plan(_WORKSITE_NAME, plates=1)

    assert sorted(sheet.name for sheet in plan.sheets if sheet.kind in {"bulletin", "memory"}) == [
        "BM PRACA NORTE",
        "MEMÓRIA PRACA NORTE",
    ]


def test_a_name_that_does_not_fit_the_sheet_is_refused_when_the_bulletin_is_composed() -> None:
    """Critério 1: a recusa sai na composição, não na publicação do arquivo.

    O nome escolhido abre com uma palavra de 21 caracteres, e a primeira palavra nunca
    abrevia: nem a forma curta faz esta praça caber, e nome impossível é recusado onde o
    humano ainda pode encurtá-lo.
    """
    plate_a, plate_b = _two_plate_inputs()
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [plate_a.packet, plate_b.packet])

    with pytest.raises(ValuationValidationError) as error:
        build_worksite_takeoff_bulletins(
            worksite,
            [plate_a, plate_b],
            _catalog(),
            worksite_name="Complexopoliesportivo Interlagos",
        )

    assert error.value.code == "WORKSITE_NAME_DOES_NOT_FIT_SHEET"
    assert error.value.details["limit"] == 23


# --------------------------------------------------------------------------------------
# a consolidação por código entre boletins
# --------------------------------------------------------------------------------------


def test_the_general_sheet_consolidates_the_worksite_total_by_code() -> None:
    """Critério 1: a PLANILHA GERAL soma os boletins por código e o guardrail fica verde."""
    plate_a, plate_b = _two_plate_inputs()
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [plate_a.packet, plate_b.packet])
    catalog = _catalog()
    valuation = build_worksite_takeoff_valuation(
        worksite,
        [plate_a, plate_b],
        catalog,
        worksite_name=_WORKSITE_NAME,
        period_number=1,
        reference_label="JANEIRO/2026",
    )

    plan = plan_workbook(valuation, catalog, default_template(), _contract())

    assert len(valuation.bulletins) == 2
    assert [worksite_plan.worksite_key for worksite_plan in plan.worksites] == [
        f"{_WORKSITE_KEY}-p1",
        f"{_WORKSITE_KEY}-p2",
    ]
    # A coluna do período corrente da GERAL é por CÓDIGO: ela recebe a soma das duas folhas
    # e tem de fechar com o total da medição — é exatamente o que `_check_consolidated_total`
    # confere antes de deixar a pasta ser planejada.
    general = next(sheet for sheet in plan.sheets if sheet.kind == "general")
    by_code = {
        cell.item_number: cell.number
        for cell in general.cells
        if cell.role == "general_current_quantity"
    }
    consolidated_amount = sum(
        (
            cell.number
            for cell in general.cells
            if cell.role == "general_current_amount" and cell.number is not None
        ),
        Decimal("0.00"),
    )
    assert by_code == {"1": Decimal("250.00"), "2": Decimal("30.00")}
    assert consolidated_amount == valuation.total_amount


def test_the_workbook_plans_a_worksite_with_a_declared_fusion() -> None:
    """A pasta é planejável com a leitura fundida dentro: linha zerada e bloco impresso.

    Vale como conferência de que a forma do bloco fundido cabe no escritor — a memória
    imprime no máximo uma dedução por bloco, e é por isso que a fusão é fator zero e não
    dedução acrescentada.
    """
    plate_a, plate_b = _two_plate_inputs()
    worksite = build_worksite_takeoff(
        _WORKSITE_KEY,
        [plate_a.packet, plate_b.packet],
        [_link(kept=(_PLATE_A, _ITEM_A1), discarded=(_PLATE_B, _ITEM_B1))],
    )
    catalog = _catalog()
    valuation = build_worksite_takeoff_valuation(
        worksite,
        [plate_a, plate_b],
        catalog,
        worksite_name=_WORKSITE_NAME,
        period_number=1,
        reference_label="JANEIRO/2026",
    )

    plan = plan_workbook(valuation, catalog, default_template(), _contract())

    general = next(sheet for sheet in plan.sheets if sheet.kind == "general")
    piso_quantity = next(
        cell.number
        for cell in general.cells
        if cell.role == "general_current_quantity" and cell.item_number == "1"
    )
    assert piso_quantity == Decimal("200.00")
    memory = next(
        sheet for sheet in plan.sheets if sheet.kind == "memory" and sheet.name.endswith("P2")
    )
    assert any(
        cell.role == "block_label"
        and cell.text is not None
        and cell.text.startswith(FUSED_BLOCK_LABEL_PREFIX)
        for cell in memory.cells
    )


def test_the_consolidated_valuation_refuses_a_calc_sheet_that_does_not_match() -> None:
    """A medição da praça continua sendo uma `Valuation`: memórias e linhas são 1:1."""
    plate_a, plate_b = _two_plate_inputs()
    worksite = build_worksite_takeoff(_WORKSITE_KEY, [plate_a.packet, plate_b.packet])
    result = build_worksite_takeoff_bulletins(
        worksite, [plate_a, plate_b], _catalog(), worksite_name=_WORKSITE_NAME
    )

    with pytest.raises(ValidationError):
        Valuation(
            period_number=1,
            reference_label="JANEIRO/2026",
            bulletins=result.bulletins,
            calc_sheets=result.plates[0].calc_sheets,
        )
