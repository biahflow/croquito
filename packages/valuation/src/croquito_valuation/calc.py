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

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from pydantic import Field, model_validator

from croquito_valuation.assignment import CodeAssignmentSet
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    BulletinLine,
    CalcBlock,
    CalcOperand,
    CalcRecipe,
    CalcSheet,
    PriceCatalog,
    PriceOrigin,
    Valuation,
    ValuationContractModel,
    WorksiteBulletin,
    product_of,
)
from croquito_valuation.rounding import money_trunc, quantity_round
from croquito_valuation.takeoff import TakeoffItem, TakeoffPacket

if TYPE_CHECKING:
    # Import só para anotação: `calc_matrix` importa `build_calc_blocks` DESTE módulo, então
    # o `resolve_calc_matrix` de runtime entra por import tardio dentro do builder.
    from croquito_valuation.calc_matrix import CalcMatrix

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
    """Resultado do builder: boletim, memórias, numeração e itens excluídos por rejeição.

    `item_numbers` (item de takeoff → número da linha) vale no regime legado, onde cada item
    é uma linha; no regime da matriz, um elemento alimenta vários serviços e a numeração é
    por SERVIÇO, então quem responde "onde este código foi impresso" é `service_numbers`
    (código → número da linha).
    """

    bulletin: WorksiteBulletin
    calc_sheets: tuple[CalcSheet, ...]
    item_numbers: dict[str, str]
    service_numbers: dict[str, str]
    excluded_item_ids: tuple[str, ...]
    safety_notes: tuple[str, ...]
    fused_item_ids: tuple[str, ...] = ()
    """Itens desta folha cuja parcela foi absorvida por fusão declarada (F-046).

    Vazio em toda folha isolada — inclusive na praça de uma folha só, que não tem com quem
    fundir. Quem lê o resultado precisa distinguir a leitura que ZEROU por fusão da que
    saiu do boletim por rejeição de código (`excluded_item_ids`): a primeira continua no
    boletim, com linha e memória; a segunda não está lá."""


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


def build_calc_blocks(
    item_plan: ItemCalcPlan | None, *, quantity: Decimal, unit: str
) -> list[CalcBlock]:
    """Blocos de memória de um item: os do plano, ou o bloco único de quantidade direta.

    Ponto único da decomposição impressa na memória, usado pelas duas cadeias — o boletim
    da medição licitada (`build_worksite_bulletin`) e o orçamento-base de pré-licitação
    (`estimate.py`). O que se decompõe é a quantidade CONFIRMADA; item sem plano recebe o
    bloco direto para que todo item tenha memória, mesmo sem detalhamento explícito.
    """
    if item_plan is None:
        return [
            CalcBlock(
                label=DEFAULT_BLOCK_LABEL,
                recipe=CalcRecipe.DIRECT_QUANTITY,
                operands=[CalcOperand(name=DEFAULT_OPERAND_NAME, value=quantity, unit=unit)],
                subtotal=quantity_round(quantity),
            )
        ]
    return [_build_block(block_plan) for block_plan in item_plan.blocks]


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
    calc_matrix: CalcMatrix | None = None,
    fused_into: Mapping[str, str] | None = None,
) -> CalcBuildResult:
    """Constrói o boletim e a memória de cálculo de uma obra a partir do takeoff confirmado.

    Fail-closed, na ordem: divergência de pacote/catálogo com `assignments`, item
    confirmado sem assignment ou assignment de item desconhecido/não confirmado, nenhum
    item restante após excluir rejeitados, plano referenciando item fora dos incluídos,
    quantidade confirmada com escala não suportada (mais de duas casas) e por fim o plano
    que não fecha com a quantidade confirmada.

    `fused_into` (`item_id` desta folha → `plate_id` da folha que ficou com a parcela) é a
    fusão declarada do consolidado da praça (F-046, ADR-0057 D4/D6), e chega sempre vazia
    em quem monta uma folha isolada — o boletim de hoje. Duas coisas mudam quando ela vem
    preenchida, e só duas: a contribuição do item fundido é zerada com a quantidade ainda
    impressa na memória (`calc_matrix._fuse_block`), e o item deixa de precisar de
    `ItemPackageClosure` próprio. A segunda é a decisão 6 do ADR: o pacote de serviços é do
    ELEMENTO DA OBRA, e um elemento fundido é fechado uma vez, do lado que fica. O que NÃO
    muda é `CALC_ASSIGNMENT_MISSING`: a leitura absorvida continua exigindo código decidido,
    porque é o código que lhe dá linha e memória — sem ele ela sumiria da folha onde foi
    lida, que é o oposto de fundir visivelmente.
    """
    fused = dict(fused_into or {})
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
    if catalog.origin != PriceOrigin.SCO:
        # O boletim É a cadeia da medição de obra licitada por definição: o contrato
        # manda, e preço nunca vem da EMOP (nem de composição). Item fora do
        # contrato/SCO vira dossiê de aditivo (`amendment_dossier.py`), nunca preço de
        # outra tabela — a cadeia SCO → EMOP → composição só vale pré-licitação.
        raise ValuationValidationError(
            "BULLETIN_PRICE_ORIGIN_FORBIDDEN",
            "medição de obra licitada não aceita catálogo cuja origem não seja o SCO; "
            "item fora do contrato vira dossiê de aditivo, nunca preço de outra tabela",
            {"origin": catalog.origin.value},
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

    # Irmão de `CALC_ASSIGNMENT_MISSING`, e pelo mesmo motivo: com a cardinalidade N:N a
    # presença de um assignment deixou de significar que o item acabou. Um elemento com um
    # de seis códigos passaria por aqui e viraria boletim pela metade, em silêncio — que é
    # exatamente o erro que `CALC_ASSIGNMENT_MISSING` existe para impedir no caso vizinho.
    # O item fundido sai desta conferência porque o pacote dele é fechado do lado que fica
    # (ADR-0057 D6): exigir um segundo fechamento aqui seria pedir duas vezes a mesma
    # afirmação sobre UM elemento da obra.
    open_ids = sorted((assignments.open_package_item_ids() & confirmed_ids) - set(fused))
    if open_ids:
        raise ValuationValidationError(
            "CALC_PACKAGE_NOT_CLOSED",
            "item confirmado tem pacote de serviços em aberto; o boletim não é montado pela metade",
            {"item_ids": open_ids},
        )

    packages = assignments.confirmed_codes_by_item()
    # Sem matriz, o builder itera itens e cada item é uma linha: um pacote de vários códigos
    # precisaria escolher um deles, e escolher em silêncio é o defeito que a F-038 ataca. Com
    # matriz, é ela quem funde o pacote em serviços — então o portão só vale no regime legado.
    if calc_matrix is None:
        packaged_ids = sorted(
            item_id for item_id in confirmed_ids if len(packages.get(item_id, ())) > 1
        )
        if packaged_ids:
            raise ValuationValidationError(
                "CALC_PACKAGE_NOT_SUPPORTED",
                "item com mais de um código confirmado exige a matriz de contribuições para "
                "virar boletim",
                {"item_ids": packaged_ids},
            )

    rejected_ids = {
        assignment.item_id
        for assignment in assignments.assignments
        if assignment.status == "rejected"
    }
    excluded_item_ids: list[str] = []
    included_items: list[TakeoffItem] = []
    for item in confirmed_items:
        if item.id in rejected_ids:
            excluded_item_ids.append(item.id)
            continue
        included_items.append(item)

    if not included_items:
        raise ValuationValidationError(
            "CALC_NO_ITEMS",
            "todos os itens confirmados tiveram o código rejeitado; nenhum item restante",
            {"plate_id": packet.plate_id},
        )

    # F-047 T5 (ADR-0058 decisão 6): o boletim não imprime número que ninguém escolheu. O
    # portão vive aqui além de viver no fechamento do pacote porque a divergência pode nascer
    # DEPOIS do fechamento — a cena é aprovada quando é aprovada, e o pacote pode já estar
    # completo quando o segundo número aparece. Só os itens que virariam linha são olhados:
    # item com o código rejeitado não imprime nada e não trava o boletim dos outros.
    divergent_ids = sorted(item.id for item in included_items if item.has_open_divergence())
    if divergent_ids:
        raise ValuationValidationError(
            "CALC_QUANTITY_DIVERGENCE_OPEN",
            "item com divergência de quantidade em aberto entre a cena e a legenda não vira "
            "linha de boletim; resolva a divergência antes de medir",
            {"item_ids": divergent_ids},
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

    # Import tardio: `calc_matrix` importa `build_calc_blocks` deste módulo (ciclo).
    from croquito_valuation.calc_matrix import resolve_calc_matrix

    resolved = resolve_calc_matrix(
        included_items,
        assignments,
        calc_plan=calc_plan,
        calc_matrix=calc_matrix,
        error_prefix="CALC",
        fused_into=fused,
    )

    if calc_matrix is None:
        # Regime legado: cada serviço é um item, na ordem de `included_items`. A conferência
        # de que o plano fecha com a quantidade CONFIRMADA continua sendo do builder — o
        # resolver só soma os subtotais, não conhece a quantidade humana. A parcela fundida
        # volta para a soma aqui de propósito: ela não conta no total da praça, mas continua
        # tendo de bater com o que a orçamentista confirmou naquela folha.
        for item, service in zip(included_items, resolved.services, strict=True):
            if service.total_quantity + service.fused_quantity != _confirmed_quantity(item):
                raise ValuationValidationError(
                    "CALC_PLAN_QUANTITY_MISMATCH",
                    "plano de cálculo não fecha com a quantidade confirmada pelo orçamentista",
                    {
                        "item_id": item.id,
                        "expected": str(_confirmed_quantity(item)),
                        "recomputed": str(service.total_quantity + service.fused_quantity),
                    },
                )

    # No regime legado a numeração é por item (byte-idêntico); no da matriz, por serviço, e
    # é `service_numbers` (código único → linha) quem responde onde cada código foi impresso.
    item_numbers: dict[str, str] = (
        {
            item.id: service.item_number
            for item, service in zip(included_items, resolved.services, strict=True)
        }
        if calc_matrix is None
        else {}
    )
    service_numbers: dict[str, str] = {}
    lines: list[BulletinLine] = []
    calc_sheets: list[CalcSheet] = []
    for service in resolved.services:
        entry = catalog.entry_for(service.code)
        total = money_trunc(service.total_quantity * entry.unit_price)
        lines.append(
            BulletinLine(
                item_number=service.item_number,
                code=service.code,
                description=entry.description,
                unit=entry.unit,
                unit_price=entry.unit_price,
                quantity=service.total_quantity,
                total=total,
            )
        )
        calc_sheets.append(
            CalcSheet(
                worksite_key=worksite_key,
                item_number=service.item_number,
                blocks=list(service.blocks),
                total_quantity=service.total_quantity,
            )
        )
        if calc_matrix is not None:
            service_numbers[service.code] = service.item_number

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
        service_numbers=service_numbers,
        excluded_item_ids=tuple(excluded_item_ids),
        safety_notes=_CALC_SAFETY_NOTES,
        fused_item_ids=tuple(item.id for item in included_items if item.id in fused),
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
    calc_matrix: CalcMatrix | None = None,
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
        calc_matrix=calc_matrix,
    )
    return Valuation(
        period_number=period_number,
        reference_label=reference_label,
        bulletins=[result.bulletin],
        calc_sheets=list(result.calc_sheets),
    )
