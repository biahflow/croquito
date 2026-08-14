"""Builder de boletim e memória de cálculo a partir do takeoff confirmado.

A quantidade confirmada pelo orçamentista manda: o plano de cálculo (`CalcPlan`) só
explica como essa quantidade se decompõe em operandos e deduções impressos na memória.
Um plano que não fecha com a quantidade confirmada recusa (`CALC_PLAN_QUANTITY_MISMATCH`)
em vez de ajustar a quantidade ou o plano silenciosamente — a decisão humana nunca é a
que cede.

Item sem plano recebe um bloco único de quantidade direta (`DIRECT_QUANTITY`), para que
todo item confirmado tenha memória de cálculo mesmo sem detalhamento explícito.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from pydantic import Field, model_validator

from croquitodxf_valuation.assignment import CodeAssignmentSet
from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.models import (
    BulletinLine,
    CalcBlock,
    CalcOperand,
    CalcRecipe,
    CalcSheet,
    PriceCatalog,
    Valuation,
    ValuationContractModel,
    WorksiteBulletin,
    product_of,
)
from croquitodxf_valuation.rounding import money_trunc, quantity_round
from croquitodxf_valuation.takeoff import TakeoffItem, TakeoffPacket

_ITEM_ID_PATTERN: Final = r"^ti_[a-f0-9]{16}$"

DEFAULT_BLOCK_LABEL: Final = "QUANTIDADE CONFIRMADA"
DEFAULT_OPERAND_NAME: Final = "QUANTIDADE"

_CALC_SAFETY_NOTES: Final = (
    "Boletim e memória nascem do takeoff confirmado com código confirmado; nada aqui "
    "está aprovado para exportação.",
    "O portão de exportação (aprovação nominal, saldo e contrato) continua obrigatório.",
)


class CalcBlockPlan(ValuationContractModel):
    """Um bloco de memória proposto para um item; o subtotal é sempre computado, não declarado."""

    label: str = Field(min_length=1, max_length=120)
    recipe: CalcRecipe
    operands: list[CalcOperand] = Field(min_length=1)
    deductions: list[CalcOperand] = Field(default_factory=list)


class ItemCalcPlan(ValuationContractModel):
    """Plano de memória de cálculo de um item: um ou mais blocos, na ordem de impressão."""

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    blocks: list[CalcBlockPlan] = Field(min_length=1)


class CalcPlan(ValuationContractModel):
    """Conjunto de planos de memória de cálculo de uma prancha; um plano por item, no máximo."""

    plans: list[ItemCalcPlan] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_items(self) -> CalcPlan:
        item_ids = [plan.item_id for plan in self.plans]
        duplicated = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
        if duplicated:
            raise ValuationValidationError(
                "CALC_PLAN_DUPLICATE_ITEM",
                "há mais de um plano de cálculo para o mesmo item",
                {"item_ids": duplicated},
            )
        return self


@dataclass(frozen=True, slots=True)
class CalcBuildResult:
    """Resultado do builder: boletim, memórias, numeração e itens excluídos por rejeição."""

    bulletin: WorksiteBulletin
    calc_sheets: tuple[CalcSheet, ...]
    item_numbers: dict[str, str]
    excluded_item_ids: tuple[str, ...]
    safety_notes: tuple[str, ...]


def _confirmed_quantity(item: TakeoffItem) -> Decimal:
    """Quantidade do item confirmado; `TakeoffItem.validate_review_state` já garante que existe."""
    assert item.quantity is not None
    return item.quantity


def _build_block(plan: CalcBlockPlan) -> CalcBlock:
    """Constrói o bloco com o subtotal recomputado; o validador do modelo confere por construção."""
    subtotal = quantity_round(
        product_of([operand.value for operand in plan.operands])
        - sum((operand.value for operand in plan.deductions), Decimal(0))
    )
    return CalcBlock(
        label=plan.label,
        recipe=plan.recipe,
        operands=plan.operands,
        deductions=plan.deductions,
        subtotal=subtotal,
    )


def build_worksite_bulletin(
    packet: TakeoffPacket,
    assignments: CodeAssignmentSet,
    catalog: PriceCatalog,
    *,
    worksite_key: str,
    worksite_name: str,
    address: str | None = None,
    contract_label: str | None = None,
    calc_plan: CalcPlan | None = None,
) -> CalcBuildResult:
    """Constrói o boletim e a memória de cálculo de uma obra a partir do takeoff confirmado.

    Fail-closed, na ordem: divergência de pacote/catálogo com `assignments`, item
    confirmado sem assignment ou assignment de item desconhecido/não confirmado, nenhum
    item restante após excluir rejeitados, plano referenciando item fora dos incluídos,
    quantidade confirmada com escala não suportada (mais de duas casas) e por fim o plano
    que não fecha com a quantidade confirmada.
    """
    if (
        assignments.plate_id != packet.plate_id
        or assignments.page_number != packet.page_number
        or assignments.image_sha256 != packet.image_sha256
    ):
        raise ValuationValidationError(
            "CALC_ASSIGNMENT_PACKET_MISMATCH",
            "conjunto de assignments pertence a outra prancha",
            {
                "expected_plate_id": packet.plate_id,
                "expected_page_number": packet.page_number,
                "expected_image_sha256": packet.image_sha256,
                "assignments_plate_id": assignments.plate_id,
                "assignments_page_number": assignments.page_number,
                "assignments_image_sha256": assignments.image_sha256,
            },
        )
    if assignments.catalog_sha256 != catalog.source_sha256:
        raise ValuationValidationError(
            "CALC_CATALOG_MISMATCH",
            "conjunto de assignments foi calculado com outro catálogo",
            {"expected": catalog.source_sha256, "declared": assignments.catalog_sha256},
        )

    confirmed_items = packet.confirmed_items()
    confirmed_by_id = {item.id: item for item in confirmed_items}
    confirmed_ids = set(confirmed_by_id)
    assignment_ids = {assignment.item_id for assignment in assignments.assignments}

    missing_ids = sorted(confirmed_ids - assignment_ids)
    if missing_ids:
        raise ValuationValidationError(
            "CALC_ASSIGNMENT_MISSING",
            "item confirmado no takeoff não possui confirmação de código",
            {"item_ids": missing_ids},
        )
    unknown_ids = sorted(assignment_ids - confirmed_ids)
    if unknown_ids:
        raise ValuationValidationError(
            "CALC_ASSIGNMENT_UNKNOWN_ITEM",
            "assignment aponta para item desconhecido ou não confirmado no pacote",
            {"item_ids": unknown_ids},
        )

    assignments_by_item = {assignment.item_id: assignment for assignment in assignments.assignments}
    excluded_item_ids: list[str] = []
    included_items: list[TakeoffItem] = []
    for item in confirmed_items:
        if assignments_by_item[item.id].status == "rejected":
            excluded_item_ids.append(item.id)
            continue
        included_items.append(item)

    if not included_items:
        raise ValuationValidationError(
            "CALC_NO_ITEMS",
            "todos os itens confirmados tiveram o código rejeitado; nenhum item restante",
            {"plate_id": packet.plate_id},
        )

    included_ids = {item.id for item in included_items}
    if calc_plan is not None:
        plan_ids = {plan.item_id for plan in calc_plan.plans}
        unknown_plan_ids = sorted(plan_ids - included_ids)
        if unknown_plan_ids:
            raise ValuationValidationError(
                "CALC_PLAN_UNKNOWN_ITEM",
                "plano de cálculo referencia item que não está entre os itens incluídos",
                {"item_ids": unknown_plan_ids},
            )

    scale_unsupported = sorted(
        item.id
        for item in included_items
        if quantity_round(quantity := _confirmed_quantity(item)) != quantity
    )
    if scale_unsupported:
        raise ValuationValidationError(
            "CALC_QUANTITY_SCALE_UNSUPPORTED",
            "quantidade confirmada com mais de duas casas decimais não é suportada na planilha",
            {"item_ids": scale_unsupported},
        )

    plan_by_item = {plan.item_id: plan for plan in calc_plan.plans} if calc_plan else {}
    item_numbers: dict[str, str] = {}
    lines: list[BulletinLine] = []
    calc_sheets: list[CalcSheet] = []
    for index, item in enumerate(included_items, start=1):
        item_number = str(index)
        item_numbers[item.id] = item_number
        quantity = _confirmed_quantity(item)

        item_plan = plan_by_item.get(item.id)
        if item_plan is not None:
            blocks = [_build_block(block_plan) for block_plan in item_plan.blocks]
        else:
            blocks = [
                CalcBlock(
                    label=DEFAULT_BLOCK_LABEL,
                    recipe=CalcRecipe.DIRECT_QUANTITY,
                    operands=[
                        CalcOperand(name=DEFAULT_OPERAND_NAME, value=quantity, unit=item.unit)
                    ],
                    subtotal=quantity_round(quantity),
                )
            ]

        total_quantity = quantity_round(sum((block.subtotal for block in blocks), Decimal(0)))
        if total_quantity != quantity:
            raise ValuationValidationError(
                "CALC_PLAN_QUANTITY_MISMATCH",
                "plano de cálculo não fecha com a quantidade confirmada pelo orçamentista",
                {
                    "item_id": item.id,
                    "expected": str(quantity),
                    "recomputed": str(total_quantity),
                },
            )

        code = assignments_by_item[item.id].code
        assert code is not None  # assignment incluído sempre é "confirmed" (excluídos já saíram)
        entry = catalog.entry_for(code)
        total = money_trunc(quantity * entry.unit_price)
        lines.append(
            BulletinLine(
                item_number=item_number,
                code=code,
                description=entry.description,
                unit=entry.unit,
                unit_price=entry.unit_price,
                quantity=quantity,
                total=total,
            )
        )
        calc_sheets.append(
            CalcSheet(
                worksite_key=worksite_key,
                item_number=item_number,
                blocks=blocks,
                total_quantity=total_quantity,
            )
        )

    bulletin = WorksiteBulletin(
        worksite_key=worksite_key,
        worksite_name=worksite_name,
        address=address,
        contract_label=contract_label,
        lines=lines,
        total_amount=sum((line.total for line in lines), Decimal("0.00")),
    )
    return CalcBuildResult(
        bulletin=bulletin,
        calc_sheets=tuple(calc_sheets),
        item_numbers=item_numbers,
        excluded_item_ids=tuple(excluded_item_ids),
        safety_notes=_CALC_SAFETY_NOTES,
    )


def build_worksite_valuation(
    packet: TakeoffPacket,
    assignments: CodeAssignmentSet,
    catalog: PriceCatalog,
    *,
    worksite_key: str,
    worksite_name: str,
    period_number: int,
    reference_label: str,
    address: str | None = None,
    contract_label: str | None = None,
    calc_plan: CalcPlan | None = None,
) -> Valuation:
    """Constrói o boletim/memória e devolve a medição de um período, sem aprovação.

    Aprovação é um ato humano posterior (`ValuationApproval`) e não é responsabilidade
    deste builder.
    """
    result = build_worksite_bulletin(
        packet,
        assignments,
        catalog,
        worksite_key=worksite_key,
        worksite_name=worksite_name,
        address=address,
        contract_label=contract_label,
        calc_plan=calc_plan,
    )
    return Valuation(
        period_number=period_number,
        reference_label=reference_label,
        bulletins=[result.bulletin],
        calc_sheets=list(result.calc_sheets),
    )
