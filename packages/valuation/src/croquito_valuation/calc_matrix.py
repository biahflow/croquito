"""Matriz de contribuições: a célula elemento x serviço vira modelo (ADR-0053).

Um elemento da prancha alimenta vários serviços, e um serviço soma parcelas de vários
elementos — a relação é N:N com quantidade por par. `CalcPlan` (`calc.py`) é indexado **por
item** e fica **intocado**; esta é sua irmã indexada **por serviço**.

A `CalcMatrix` é o artefato que a orçamentista monta sobre a shortlist de códigos. Cada
`ServiceContributions` reúne, sob um `code`, as parcelas (`CalcContribution`) que os
elementos acrescentam à quantidade daquele serviço. O transporte é uma parcela `DEPENDENT`:
sua quantidade vem de OUTRO serviço, resolvida no build e materializada como operando
literal — a pasta continua autocontida, sem referência cruzada entre abas.

`resolve_calc_matrix` normaliza os dois regimes num único formato (`ResolvedMatrix`) que os
builders (T6) consomem. No regime legado — assignments de código único, sem matriz — o
resultado é **byte-idêntico** ao de hoje, porque a decomposição impressa vem exatamente de
`calc.build_calc_blocks`; nada é fundido nem renumerado.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from pydantic import Field, model_validator

from croquito_valuation.assignment import CodeAssignmentSet
from croquito_valuation.calc import CalcPlan, build_calc_blocks
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    NON_SCO_CODE_PATTERN,
    TAKEOFF_ITEM_ID_PATTERN,
    CalcBlock,
    CalcOperand,
    CalcRecipe,
    ContributionBasis,
    SiteSetupOrigin,
    ValuationContractModel,
    product_of,
)
from croquito_valuation.rounding import quantity_round
from croquito_valuation.sco import SCO_CODE_PATTERN
from croquito_valuation.takeoff import TakeoffItem

CALC_MATRIX_SCHEMA_VERSION: Final = "1.0.0"

_ELEMENT_BASES: Final = (
    ContributionBasis.FULL,
    ContributionBasis.DERIVED,
    ContributionBasis.PARTIAL,
)
"""Bases cuja parcela nasce de UM elemento da prancha; exigem `source_item_id`."""


class CalcContribution(ValuationContractModel):
    """Parcela que UM elemento acrescenta à quantidade de UM serviço: a célula da matriz.

    `label` é o texto que o escritor imprime na memória; `source_item_id` é o mesmo vínculo,
    conferível por máquina. A coerência entre `basis`, `source_item_id` e `depends_on_code`
    espelha a de `CalcBlock` (`models.py`): é o mesmo invariante, aqui no lado da autoria.

    `depends_on_code` é a aresta de dependência (guia o topo-sort); ao materializar, o
    resolver a grava em `CalcBlock.derived_from_code` como proveniência.
    """

    source_item_id: str | None = Field(default=None, pattern=TAKEOFF_ITEM_ID_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    basis: ContributionBasis
    recipe: CalcRecipe
    operands: list[CalcOperand] = Field(min_length=1)
    deductions: list[CalcOperand] = Field(default_factory=list)
    depends_on_code: str | None = Field(default=None, min_length=1, max_length=30)
    note: str | None = Field(default=None, max_length=500)
    kit_origin: SiteSetupOrigin | None = None
    """Proveniência quando a parcela nasceu de um acervo de canteiro (F-042), em vez de
    autorada à mão. `None` é o regime de hoje: nenhuma matriz já válida deixa de ser válida
    por causa deste campo, que é opcional e tem default."""

    @model_validator(mode="after")
    def validate_contribution(self) -> CalcContribution:
        """Coerência que a parcela sabe sozinha; o teto de `PARTIAL` é conferência do build."""
        if self.basis is ContributionBasis.STANDALONE and self.source_item_id is not None:
            raise ValuationValidationError(
                "CALC_CONTRIBUTION_STANDALONE_WITH_ITEM",
                "parcela de canteiro não nasce de elemento da prancha",
                {"label": self.label, "source_item_id": self.source_item_id},
            )
        if self.basis is ContributionBasis.DEPENDENT:
            if self.depends_on_code is None:
                raise ValuationValidationError(
                    "CALC_CONTRIBUTION_DEPENDENT_WITHOUT_CODE",
                    "parcela derivada precisa dizer de qual serviço ela vem",
                    {"label": self.label},
                )
        elif self.depends_on_code is not None:
            raise ValuationValidationError(
                "CALC_CONTRIBUTION_CODE_WITHOUT_DEPENDENCY",
                "só parcela derivada de outro serviço cita um código de origem",
                {"label": self.label, "basis": self.basis.value},
            )
        if self.basis in _ELEMENT_BASES and self.source_item_id is None:
            raise ValuationValidationError(
                "CALC_CONTRIBUTION_WITHOUT_SOURCE_ITEM",
                "parcela com origem em elemento precisa apontar para o elemento",
                {"label": self.label, "basis": self.basis.value},
            )
        # A parcela `PARTIAL` é o ponto de honestidade do desenho (ADR-0053, decisão 3): os
        # 170 m² de limpeza dentro dos 418,12 do piso não saem de conta nenhuma. Como o número
        # é DECLARADO e nunca recomputado, a nota que o justifica é obrigatória — sem ela a
        # célula afirma um recorte medido sem dizer de onde ele veio. O teto (`≤ quantidade do
        # item`) é conferência do build, porque depende do `TakeoffItem`.
        if self.basis is ContributionBasis.PARTIAL and not (self.note and self.note.strip()):
            raise ValuationValidationError(
                "CALC_PARTIAL_NOTE_REQUIRED",
                "parcela parcial precisa de nota que justifique o recorte medido",
                {"label": self.label},
            )
        if self.depends_on_code is not None and (
            re.fullmatch(SCO_CODE_PATTERN, self.depends_on_code) is None
            and re.fullmatch(NON_SCO_CODE_PATTERN, self.depends_on_code) is None
        ):
            raise ValuationValidationError(
                "CALC_CONTRIBUTION_CODE_INVALID",
                "código de origem da parcela não tem formato de código de catálogo",
                {"label": self.label, "depends_on_code": self.depends_on_code},
            )
        if self.kit_origin is not None and self.basis is not ContributionBasis.STANDALONE:
            raise ValuationValidationError(
                "CALC_CONTRIBUTION_KIT_ORIGIN_NOT_STANDALONE",
                "proveniência de acervo de canteiro só é válida em parcela standalone",
                {"label": self.label, "basis": self.basis.value},
            )
        return self


class ServiceContributions(ValuationContractModel):
    """As parcelas que um serviço (`code`) recebe de todos os elementos que o alimentam."""

    code: str = Field(min_length=1, max_length=30)
    contributions: list[CalcContribution] = Field(min_length=1)


class CalcMatrix(ValuationContractModel):
    """Matriz elemento x serviço de uma prancha: um `ServiceContributions` por código.

    A guarda de ciclo roda **na leitura do artefato**: uma matriz gravada com ciclo ou
    auto-referência nunca volta do banco. Alvo de dependência fora da própria matriz **não**
    falha aqui — é o build que conhece o boletim.
    """

    schema_version: Literal["1.0.0"] = CALC_MATRIX_SCHEMA_VERSION
    services: list[ServiceContributions] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_codes(self) -> CalcMatrix:
        codes = [service.code for service in self.services]
        duplicated = sorted({code for code in codes if codes.count(code) > 1})
        if duplicated:
            raise ValuationValidationError(
                "CALC_MATRIX_DUPLICATE_CODE",
                "há mais de um conjunto de contribuições para o mesmo serviço",
                {"codes": duplicated},
            )
        return self

    @model_validator(mode="after")
    def validate_acyclic(self) -> CalcMatrix:
        """Recusa auto-referência e ciclo entre serviços na leitura do artefato (Kahn)."""
        edges = _dependency_edges(self.services)

        self_referencing = sorted(code for code, targets in edges.items() if code in targets)
        if self_referencing:
            raise ValuationValidationError(
                "CALC_MATRIX_SELF_DEPENDENCY",
                "serviço não pode depender de si mesmo",
                {"codes": self_referencing},
            )

        if _topological_order(self.services) is None:
            raise ValuationValidationError(
                "CALC_MATRIX_DEPENDENCY_CYCLE",
                "há dependência cíclica entre serviços; a memória não tem ordem de cálculo",
                {"codes": sorted(edges)},
            )
        return self


def _dependency_edges(services: list[ServiceContributions]) -> dict[str, set[str]]:
    """Grafo `code → {códigos de que ele depende}`, só das parcelas `DEPENDENT`."""
    edges: dict[str, set[str]] = {}
    for service in services:
        targets = edges.setdefault(service.code, set())
        for contribution in service.contributions:
            if contribution.basis is ContributionBasis.DEPENDENT and contribution.depends_on_code:
                targets.add(contribution.depends_on_code)
    return edges


def _topological_order(services: list[ServiceContributions]) -> list[str] | None:
    """Ordem em que os serviços podem ser calculados; `None` se houver ciclo.

    O serviço que alimenta outro vem antes. Empate desfeito pela ordem de primeira aparição
    em `services` — determinismo é obrigatório, `valuation-demo` é golden. Arestas para
    códigos fora da matriz são ignoradas (o build decide sobre alvo desconhecido).
    """
    order = [service.code for service in services]
    known = set(order)
    edges = {
        code: {target for target in targets if target in known}
        for code, targets in _dependency_edges(services).items()
    }
    in_degree = {code: len(edges.get(code, set())) for code in order}

    ready = deque(code for code in order if in_degree[code] == 0)
    resolved: list[str] = []
    while ready:
        code = ready.popleft()
        resolved.append(code)
        # `code` ficou pronto: quem dependia dele perde uma aresta pendente.
        for dependent in order:
            if code in edges.get(dependent, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    ready.append(dependent)
    if len(resolved) != len(order):
        return None
    return resolved


@dataclass(frozen=True, slots=True)
class ResolvedService:
    """Um serviço pronto para virar linha de boletim: numeração, código e memória literal."""

    item_number: str
    code: str
    blocks: tuple[CalcBlock, ...]
    total_quantity: Decimal


@dataclass(frozen=True, slots=True)
class ResolvedMatrix:
    """Serviços resolvidos na ordem de numeração; a costura que os builders (T6) consomem."""

    services: tuple[ResolvedService, ...]


def materialize_contribution(
    contribution: CalcContribution, *, upstream_quantity: Decimal | None
) -> CalcBlock:
    """Constrói o `CalcBlock` literal de uma parcela; o subtotal é recomputado, não declarado.

    Pública desde a F-042: `site_setup.py` precisa da mesma materialização para pré-visualizar
    o que uma parcela de acervo vai virar, e uma segunda aritmética de quantidade no
    repositório divergiria da primeira no primeiro ajuste.

    A parcela `DEPENDENT` recebe, como PRIMEIRO operando literal, a quantidade já resolvida
    do serviço de que ela depende (o código citado no nome) — é o que mantém a memória sem
    referência cruzada. `depends_on_code` viaja para `derived_from_code` como proveniência.
    """
    if contribution.basis is ContributionBasis.DEPENDENT:
        assert upstream_quantity is not None and contribution.depends_on_code is not None
        operands = [
            CalcOperand(
                name=f"QUANTIDADE {contribution.depends_on_code}"[:60],
                value=upstream_quantity,
            ),
            *contribution.operands,
        ]
        derived_from_code = contribution.depends_on_code
    else:
        operands = list(contribution.operands)
        derived_from_code = None

    subtotal = quantity_round(
        product_of([operand.value for operand in operands])
        - sum((operand.value for operand in contribution.deductions), Decimal(0))
    )
    return CalcBlock(
        label=contribution.label,
        source_item_id=contribution.source_item_id,
        basis=contribution.basis,
        derived_from_code=derived_from_code,
        recipe=contribution.recipe,
        operands=operands,
        deductions=contribution.deductions,
        subtotal=subtotal,
    )


def _resolve_legacy(
    included_items: list[TakeoffItem],
    assignments: CodeAssignmentSet,
    *,
    calc_plan: CalcPlan | None,
) -> ResolvedMatrix:
    """Regime legado: um serviço por item, na ordem e numeração de hoje, byte-idêntico.

    A decomposição vem de `build_calc_blocks` — a mesma função dos builders —, então os
    blocos são idênticos aos de hoje (inclusive `basis=None`: forçar `FULL` mudaria o bloco
    e quebraria a igualdade). Dois itens que apontam para o mesmo código continuam sendo
    dois serviços; fusão por código só existe no regime da matriz.
    """
    packages = assignments.confirmed_codes_by_item()
    plan_by_item = {plan.item_id: plan for plan in calc_plan.plans} if calc_plan else {}

    resolved: list[ResolvedService] = []
    for index, item in enumerate(included_items, start=1):
        quantity = item.quantity
        assert quantity is not None
        blocks = build_calc_blocks(plan_by_item.get(item.id), quantity=quantity, unit=item.unit)
        total_quantity = quantity_round(sum((block.subtotal for block in blocks), Decimal(0)))
        resolved.append(
            ResolvedService(
                item_number=str(index),
                code=packages[item.id][0],
                blocks=tuple(blocks),
                total_quantity=total_quantity,
            )
        )
    return ResolvedMatrix(services=tuple(resolved))


def _partial_cap_by_item(included_items: list[TakeoffItem]) -> dict[str, Decimal]:
    """Teto de cada elemento incluído: a quantidade confirmada que uma parcela não ultrapassa."""
    return {item.id: item.quantity for item in included_items if item.quantity is not None}


def _check_partial_cap(
    *,
    service_code: str,
    contribution: CalcContribution,
    declared: Decimal,
    cap_by_item: dict[str, Decimal],
) -> None:
    """Confere o teto da parcela `PARTIAL`: o declarado nunca passa da quantidade do elemento.

    É conferência de BUILD porque o teto vem de `TakeoffItem.quantity`, que o modelo da célula
    não alcança (ADR-0053, decisão 3). O `declared` é o produto que os operandos já computaram
    (o subtotal do bloco materializado), nunca um número novo. O código é fixo `CALC_PARTIAL_*`,
    e não `error_prefix`: como o teto e a nota descrevem a semântica da célula (não a resolução
    da cadeia), as duas famílias de PARTIAL têm um nome só nas duas cadeias — igual ao
    `CALC_PARTIAL_NOTE_REQUIRED`, que nasce no validador do modelo, sem cadeia.
    """
    source_item_id = contribution.source_item_id
    assert source_item_id is not None  # invariante da célula: `PARTIAL` aponta para o elemento.
    cap = cap_by_item.get(source_item_id)
    if cap is None:
        # Elemento fora dos itens incluídos: não há quantidade para conferir o teto. O vínculo
        # entre `source_item_id` e item incluído não é validado aqui para nenhuma base, então
        # inventar recusa seria alargar escopo — o teto só existe quando há elemento de origem.
        return
    if declared > cap:
        raise ValuationValidationError(
            "CALC_PARTIAL_EXCEEDS_ITEM",
            "parcela parcial ultrapassa a quantidade do elemento de origem",
            {
                "code": service_code,
                "source_item_id": source_item_id,
                "declared": str(declared),
                "cap": str(cap),
            },
        )


def _resolve_matrix(
    included_items: list[TakeoffItem],
    assignments: CodeAssignmentSet,
    calc_matrix: CalcMatrix,
    *,
    error_prefix: str,
) -> ResolvedMatrix:
    """Regime novo: funde por serviço, resolve a dependência e numera na ordem topológica."""
    order = _topological_order(calc_matrix.services)
    assert order is not None  # o validador de `CalcMatrix` já recusou ciclo na leitura.
    cap_by_item = _partial_cap_by_item(included_items)
    service_by_code = {service.code: service for service in calc_matrix.services}
    matrix_codes = set(service_by_code)
    priced_codes = {
        code for codes in assignments.confirmed_codes_by_item().values() for code in codes
    }

    for service in calc_matrix.services:
        for contribution in service.contributions:
            target = contribution.depends_on_code
            if target is None:
                continue
            if target not in matrix_codes:
                raise ValuationValidationError(
                    f"{error_prefix}_MATRIX_DEPENDENCY_UNKNOWN",
                    "parcela derivada aponta para serviço que não está no boletim",
                    {"code": service.code, "depends_on_code": target},
                )
            if target not in priced_codes:
                raise ValuationValidationError(
                    f"{error_prefix}_MATRIX_DEPENDENCY_UNPRICED",
                    "parcela derivada aponta para serviço sem código confirmado",
                    {"code": service.code, "depends_on_code": target},
                )

    resolved_by_code: dict[str, ResolvedService] = {}
    for index, code in enumerate(order, start=1):
        service = service_by_code[code]
        materialized: list[CalcBlock] = []
        for contribution in service.contributions:
            block = materialize_contribution(
                contribution,
                upstream_quantity=(
                    resolved_by_code[contribution.depends_on_code].total_quantity
                    if contribution.basis is ContributionBasis.DEPENDENT
                    and contribution.depends_on_code is not None
                    else None
                ),
            )
            if contribution.basis is ContributionBasis.PARTIAL:
                _check_partial_cap(
                    service_code=code,
                    contribution=contribution,
                    declared=block.subtotal,
                    cap_by_item=cap_by_item,
                )
            materialized.append(block)
        blocks = tuple(materialized)
        total_quantity = quantity_round(sum((block.subtotal for block in blocks), Decimal(0)))
        resolved_by_code[code] = ResolvedService(
            item_number=str(index),
            code=code,
            blocks=blocks,
            total_quantity=total_quantity,
        )

    return ResolvedMatrix(services=tuple(resolved_by_code[code] for code in order))


def resolve_calc_matrix(
    included_items: list[TakeoffItem],
    assignments: CodeAssignmentSet,
    *,
    calc_plan: CalcPlan | None = None,
    calc_matrix: CalcMatrix | None = None,
    error_prefix: str = "CALC",
) -> ResolvedMatrix:
    """Normaliza os dois regimes num único formato que os builders consomem.

    Sem `calc_matrix`, é o regime legado (código único por item): resultado byte-idêntico ao
    de hoje. Com `calc_matrix`, é o regime da matriz: fusão por serviço, dependência resolvida
    como operando literal e ordem topológica como numeração. `error_prefix` (`CALC` na cadeia
    da medição licitada, `ESTIMATE` no orçamento-base) espelha a convenção das duas famílias
    de erro já existentes.
    """
    if calc_matrix is not None:
        return _resolve_matrix(included_items, assignments, calc_matrix, error_prefix=error_prefix)
    return _resolve_legacy(included_items, assignments, calc_plan=calc_plan)
