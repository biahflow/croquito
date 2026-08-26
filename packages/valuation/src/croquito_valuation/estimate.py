"""Orçamento-base de PRÉ-licitação: cascata de fontes com proveniência por linha.

Este é o outro lado da fronteira que o `ADR-0027` fixou. Em obra **licitada** (medição), o
contrato manda e o preço nunca vem de outra tabela: item confirmado sem código no contrato
vira dossiê de aditivo (`amendment_dossier.py`). **Antes** da licitação, o orçamentista
monta o orçamento-base e aí vale a cadeia SCO → EMOP → composição manual — que é o que este
módulo entrega.

Três coisas definem o `Estimate` e nenhuma delas é opcional:

1. **A cascata é dado.** A ordem das fontes é a que o chamador declarou (a sequência de
   `--catalog` do comando), nunca um `if` de "SCO primeiro" no código. O manifesto
   ordenado viaja no artefato (`cascade`), com origem, digest, data-base e rótulo de cada
   catálogo.
2. **A proveniência é por linha.** Cada `EstimateLine` diz de qual origem, de qual catálogo
   e de qual data-base saiu aquele preço; a releitura confere que a linha aponta para uma
   fonte que está na cascata declarada.
3. **Item sem preço é declarado, nunca inventado.** O item confirmado no takeoff cujo
   código o orçamentista rejeitou (isto é: nenhuma das fontes o precifica) sai em
   `unpriced_item_ids` — é a lista de candidatos a composição nova, e não vira linha com
   preço aproximado de item parecido.

O que este módulo **não** tem, de propósito: contrato, saldo e período. Nada disso existe
antes da licitação, e o `Estimate` não passa — nem tenta passar — pelo portão de exportação
da medição (`Valuation.ensure_exportable`), que recebe o contrato por parâmetro.

Aprovação, essa existe, e é **própria** (ADR-0046): `Estimate.approval` é nominal, amarrada
por digest ao conteúdo exato assinado, e o portão daqui — `export_errors()` /
`ensure_exportable()` — não recebe contrato nenhum, que é o que mantém a fronteira do
ADR-0027 de pé: saldo, período e código no contrato não têm como entrar por ele. Fora o
portão, a regra é a de sempre: tudo recomputado na construção e revalidado na leitura.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from croquito_valuation.assignment import CodeAssignmentSet, ensure_price_cascade
from croquito_valuation.calc import CalcPlan, build_calc_blocks
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    ITEM_NUMBER_PATTERN,
    MAX_DESCRIPTION_LENGTH,
    NON_SCO_CODE_PATTERN,
    REFERENCE_MONTH_PATTERN,
    SHA256_PATTERN,
    WORKSITE_KEY_PATTERN,
    CalcSheet,
    DigestPruning,
    ExactDecimal,
    PriceCatalog,
    PriceOrigin,
    ValuationContractModel,
    versioned_content_digest,
)
from croquito_valuation.rounding import money_trunc, quantity_round
from croquito_valuation.sco import SCO_CODE_PATTERN
from croquito_valuation.takeoff import TakeoffItem, TakeoffPacket

ESTIMATE_SCHEMA_VERSION: Final = "3.0.0"

ESTIMATE_DIGEST_PRUNING: Final[DigestPruning] = {
    "2.2.0": [
        (
            ("calc_sheets", "blocks"),
            frozenset({"source_item_id", "basis", "derived_from_code"}),
        ),
    ],
}
"""Orçamento assinado antes da matriz não conhecia os vínculos do bloco de cálculo.

Aqui a poda vale mais do que compatibilidade de leitura: sob o ADR-0048 o orçamento
assinado é o consolidado contratual da medição, e mover esse digest invalidaria um
contrato."""

_ITEM_ID_PATTERN: Final = r"^ti_[a-f0-9]{16}$"

_ESTIMATE_SAFETY_NOTES: Final = (
    "Orçamento-base de PRÉ-licitação: não é medição, não tem contrato nem saldo e não "
    "passa pelo portão de exportação da medição.",
    "Cada linha declara a origem, o catálogo e a data-base do preço; conferir a data-base "
    "antes de usar o valor.",
    "Item confirmado sem preço em nenhuma fonte fica declarado em unpriced_item_ids; ele "
    "exige composição nova, nunca preço de item parecido.",
)


def _code_pattern_for(origin: PriceOrigin) -> str:
    """Forma estrutural do código conforme a origem — o mesmo desenho do catálogo."""
    return SCO_CODE_PATTERN if origin == PriceOrigin.SCO else NON_SCO_CODE_PATTERN


class CatalogSource(ValuationContractModel):
    """Uma fonte de preço no manifesto da cascata: quem é, de quando e de qual arquivo."""

    origin: PriceOrigin
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_month: str = Field(pattern=REFERENCE_MONTH_PATTERN)
    source_label: str = Field(min_length=1, max_length=200)

    @classmethod
    def of(cls, catalog: PriceCatalog) -> CatalogSource:
        """Manifesto de um catálogo já importado; nada aqui é digitado de novo."""
        return cls(
            origin=catalog.origin,
            source_sha256=catalog.source_sha256,
            reference_month=catalog.reference_month,
            source_label=catalog.source_label,
        )


class EstimateLine(ValuationContractModel):
    """Linha do orçamento-base: preço, quantidade e a fonte de onde o preço veio.

    Espelho de `BulletinLine` com a diferença que dá nome ao módulo: o boletim só tem preço
    de contrato e por isso não precisa dizer de onde ele veio; aqui a fonte é parte da
    linha, e o código obedece à forma da origem dela. `unit_price` é o preço de fonte, sem
    BDI; `unit_price_with_bdi` é o preço com o percentual do orçamento aplicado e truncado
    no centavo (ADR-0038, decisão 3) — é ele, não `unit_price`, que o total recomputa.
    """

    item_number: str = Field(pattern=ITEM_NUMBER_PATTERN)
    code: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    unit_price: ExactDecimal = Field(ge=0)
    unit_price_with_bdi: ExactDecimal = Field(ge=0)
    quantity: ExactDecimal = Field(ge=0)
    total: ExactDecimal = Field(ge=0)
    price_origin: PriceOrigin
    catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_month: str = Field(pattern=REFERENCE_MONTH_PATTERN)
    source_label: str = Field(min_length=1, max_length=200)

    @property
    def expected_total(self) -> Decimal:
        """Total recomputado sobre o preço COM BDI: dinheiro trunca, nunca arredonda."""
        return money_trunc(self.quantity * self.unit_price_with_bdi)

    @model_validator(mode="after")
    def validate_code_for_origin(self) -> EstimateLine:
        if re.fullmatch(_code_pattern_for(self.price_origin), self.code) is None:
            raise ValuationValidationError(
                "ESTIMATE_CODE_INVALID_FOR_ORIGIN",
                "código da linha não tem o formato esperado para a origem do preço",
                {
                    "item_number": self.item_number,
                    "code": self.code,
                    "price_origin": self.price_origin.value,
                },
            )
        return self

    @model_validator(mode="after")
    def validate_total(self) -> EstimateLine:
        expected = self.expected_total
        if self.total != expected:
            raise ValuationValidationError(
                "ESTIMATE_LINE_TOTAL_MISMATCH",
                "total da linha não confere com quantidade x preço truncado",
                {
                    "item_number": self.item_number,
                    "expected": str(expected),
                    "declared": str(self.total),
                },
            )
        return self


class EstimateApproverDecision(ValuationContractModel):
    """Decisão humana rastreável de quem aprova o orçamento-base.

    Duplicação local deliberada da FORMA de `ReviewerDecision` (ADR-0046, decisão 4), não
    reuso dele: lá o papel é `Literal["orcamentista"]` e ampliá-lo faria um papel do
    orçamento aparecer no vocabulário da medição. Aqui o papel é `aprovador` — na cadeia
    real quem assina o orçamento não é quem o montou (decisão 5) — e o prefixo do id é
    próprio. O que se repete é a forma, não o significado.
    """

    decision_id: str = Field(pattern=r"^ed_[a-f0-9]{16}$")
    action: Literal["confirm", "reject"]
    approver_id: str = Field(min_length=1, max_length=120)
    approver_role: Literal["aprovador"]
    decided_at: datetime
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValuationValidationError(
                "ESTIMATE_DECISION_TIMESTAMP_NAIVE",
                "decisão do aprovador exige data e hora com fuso horário",
                {"decided_at": value.isoformat()},
            )
        return value


class EstimateApproval(ValuationContractModel):
    """Aprovação nominal amarrada por digest ao conteúdo exato aprovado.

    Aprovar um conteúdo e despachar outro é o erro que este modelo existe para impedir: o
    digest é recomputado no portão e qualquer edição posterior do orçamento torna a
    aprovação caduca em vez de silenciosamente válida.
    """

    decision: EstimateApproverDecision
    estimate_digest: str = Field(pattern=SHA256_PATTERN)


class Estimate(ValuationContractModel):
    """Orçamento-base de uma obra, amarrado à prancha e à cascata que o precificou.

    Sem período, sem contrato e sem saldo: nenhum desses conceitos existe antes da
    licitação. Aprovação existe e é própria (`approval`, ADR-0046): nominal, amarrada por
    digest ao conteúdo exato assinado, com portão de exportação
    (`export_errors()`/`ensure_exportable()`) que **não** recebe contrato — é a assinatura
    sem contrato que mantém a fronteira do ADR-0027 de pé.

    A memória de cálculo é a MESMA do boletim (`CalcSheet`, montada por
    `build_calc_blocks`), e a relação 1:1 entre linha e memória é validada como na medição —
    quantidade que diverge da memória recusa.

    `bdi_percent` é o BDI do orçamento inteiro (ADR-0038): percentual único, nunca por
    linha nem por grupo. `total_amount` já embute o BDI (é a soma dos `total` das linhas,
    que recomputam sobre `unit_price_with_bdi`); `total_amount_without_bdi` é a mesma soma
    sem o percentual, para quem for imprimir a diferença entre os dois totais truncados —
    nunca o percentual aplicado ao total geral (decisão 4).
    """

    schema_version: Literal["2.2.0", "3.0.0"] = ESTIMATE_SCHEMA_VERSION
    worksite_key: str = Field(pattern=WORKSITE_KEY_PATTERN)
    worksite_name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, min_length=1, max_length=200)
    plate_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=SHA256_PATTERN)
    source_pdf_sha256: str = Field(pattern=SHA256_PATTERN)
    bdi_percent: ExactDecimal = Field(ge=0)
    cascade: list[CatalogSource] = Field(min_length=1)
    lines: list[EstimateLine] = Field(min_length=1)
    unpriced_item_ids: list[str] = Field(default_factory=list)
    calc_sheets: list[CalcSheet] = Field(min_length=1)
    total_amount_without_bdi: ExactDecimal = Field(ge=0)
    total_amount: ExactDecimal = Field(ge=0)
    safety_notes: list[str] = Field(min_length=2)
    approval: EstimateApproval | None = None

    @property
    def expected_total_amount(self) -> Decimal:
        """Soma dos totais já truncados; o total do orçamento não trunca duas vezes."""
        return sum((line.total for line in self.lines), Decimal("0.00"))

    @model_validator(mode="after")
    def validate_cascade(self) -> Estimate:
        origins = [source.origin.value for source in self.cascade]
        duplicated = sorted({origin for origin in origins if origins.count(origin) > 1})
        if duplicated:
            raise ValuationValidationError(
                "ESTIMATE_CASCADE_ORIGIN_DUPLICATE",
                "cascata declara mais de uma fonte da mesma origem de preço",
                {"origins": duplicated},
            )
        return self

    @model_validator(mode="after")
    def validate_lines(self) -> Estimate:
        item_numbers = [line.item_number for line in self.lines]
        duplicated = sorted({number for number in item_numbers if item_numbers.count(number) > 1})
        if duplicated:
            raise ValuationValidationError(
                "ESTIMATE_DUPLICATE_ITEM",
                "orçamento possui item repetido",
                {"item_numbers": duplicated},
            )
        sources = {source.source_sha256: source for source in self.cascade}
        for line in self.lines:
            source = sources.get(line.catalog_sha256)
            if (
                source is None
                or source.origin != line.price_origin
                or source.reference_month != line.reference_month
                or source.source_label != line.source_label
            ):
                raise ValuationValidationError(
                    "ESTIMATE_LINE_SOURCE_UNKNOWN",
                    "linha aponta para uma fonte de preço que não está na cascata declarada",
                    {"item_number": line.item_number, "catalog_sha256": line.catalog_sha256},
                )
        return self

    @model_validator(mode="after")
    def validate_line_bdi(self) -> Estimate:
        """Preço com BDI de cada linha recomputa sobre o percentual único do orçamento."""
        mismatched = [
            line.item_number
            for line in self.lines
            if line.unit_price_with_bdi
            != money_trunc(line.unit_price * (1 + self.bdi_percent / 100))
        ]
        if mismatched:
            raise ValuationValidationError(
                "ESTIMATE_LINE_BDI_MISMATCH",
                "preço com BDI da linha não confere com o percentual declarado no orçamento",
                {"item_numbers": mismatched, "bdi_percent": str(self.bdi_percent)},
            )
        return self

    @model_validator(mode="after")
    def validate_unpriced_item_ids(self) -> Estimate:
        invalid = sorted(
            item_id
            for item_id in self.unpriced_item_ids
            if re.fullmatch(_ITEM_ID_PATTERN, item_id) is None
        )
        if invalid:
            raise ValuationValidationError(
                "ESTIMATE_UNPRICED_ITEM_INVALID",
                "id de item sem preço fora do formato de item de takeoff",
                {"item_ids": invalid},
            )
        duplicated = sorted(
            {
                item_id
                for item_id in self.unpriced_item_ids
                if self.unpriced_item_ids.count(item_id) > 1
            }
        )
        if duplicated:
            raise ValuationValidationError(
                "ESTIMATE_UNPRICED_ITEM_INVALID",
                "id de item sem preço repetido",
                {"item_ids": duplicated},
            )
        return self

    @model_validator(mode="after")
    def validate_total_amount_without_bdi(self) -> Estimate:
        expected = sum(
            (money_trunc(line.unit_price * line.quantity) for line in self.lines),
            Decimal("0.00"),
        )
        if self.total_amount_without_bdi != expected:
            raise ValuationValidationError(
                "ESTIMATE_TOTAL_WITHOUT_BDI_MISMATCH",
                "total sem BDI do orçamento não confere com a soma dos totais das linhas sem BDI",
                {
                    "worksite_key": self.worksite_key,
                    "expected": str(expected),
                    "declared": str(self.total_amount_without_bdi),
                },
            )
        return self

    @model_validator(mode="after")
    def validate_total_amount(self) -> Estimate:
        expected = self.expected_total_amount
        if self.total_amount != expected:
            raise ValuationValidationError(
                "ESTIMATE_TOTAL_MISMATCH",
                "total do orçamento não confere com a soma dos totais das linhas",
                {
                    "worksite_key": self.worksite_key,
                    "expected": str(expected),
                    "declared": str(self.total_amount),
                },
            )
        return self

    @model_validator(mode="after")
    def validate_calc_sheets(self) -> Estimate:
        orphan_keys = sorted(
            {sheet.worksite_key for sheet in self.calc_sheets} - {self.worksite_key}
        )
        if orphan_keys:
            raise ValuationValidationError(
                "ESTIMATE_CALC_SHEET_MISMATCH",
                "há memória de cálculo de outra obra no orçamento",
                {"worksite_key": self.worksite_key, "only_in_calc_sheets": orphan_keys},
            )
        sheet_numbers = [sheet.item_number for sheet in self.calc_sheets]
        line_numbers = {line.item_number for line in self.lines}
        if len(sheet_numbers) != len(set(sheet_numbers)) or set(sheet_numbers) != line_numbers:
            raise ValuationValidationError(
                "ESTIMATE_CALC_SHEET_MISMATCH",
                "memórias de cálculo e linhas do orçamento não são 1:1 por item",
                {
                    "only_in_estimate": sorted(line_numbers - set(sheet_numbers)),
                    "only_in_calc_sheets": sorted(set(sheet_numbers) - line_numbers),
                },
            )
        sheets_by_number = {sheet.item_number: sheet for sheet in self.calc_sheets}
        for line in self.lines:
            sheet = sheets_by_number[line.item_number]
            if sheet.total_quantity != line.quantity:
                raise ValuationValidationError(
                    "ESTIMATE_QUANTITY_MISMATCH",
                    "quantidade da linha não confere com a memória de cálculo do item",
                    {
                        "item_number": line.item_number,
                        "estimate": str(line.quantity),
                        "calc_sheet": str(sheet.total_quantity),
                    },
                )
        return self

    def content_digest(self) -> str:
        """SHA-256 do conteúdo canônico do orçamento, sem a aprovação que o referencia.

        Excluir `approval` do cálculo é o que faz assinar não mudar o que foi assinado: o
        digest gravado no ato continua conferindo com o do orçamento logo depois dele.
        """
        return versioned_content_digest(
            self.model_dump(mode="json", exclude={"approval"}),
            self.schema_version,
            ESTIMATE_DIGEST_PRUNING,
        )

    def export_errors(self) -> list[str]:
        """Violações que impedem despachar o orçamento, no formato `CODE`.

        Sem `ContractWorkbook`, ao contrário do portão da medição (ADR-0046, decisão 3):
        saldo, período e código no contrato não existem deste lado da fronteira, e é a
        assinatura sem contrato que impede esses códigos de entrarem aqui por cópia.
        """
        errors: list[str] = []
        approval = self.approval
        if approval is None:
            errors.append("ESTIMATE_NOT_APPROVED")
        else:
            if approval.decision.action == "reject":
                errors.append("ESTIMATE_APPROVAL_REJECTED")
            if approval.estimate_digest != self.content_digest():
                errors.append("APPROVAL_CONTENT_MISMATCH")
        return errors

    def ensure_exportable(self) -> None:
        """Portão de exportação: com qualquer violação aberta, nada é publicado."""
        errors = self.export_errors()
        if errors:
            raise ValuationValidationError(
                "ESTIMATE_EXPORT_BLOCKED",
                "orçamento possui violações abertas e não pode ser exportado",
                {"errors": errors},
            )


@dataclass(frozen=True, slots=True)
class EstimateBuildResult:
    """Orçamento montado e a numeração que ligou cada item de takeoff à linha dele."""

    estimate: Estimate
    item_numbers: dict[str, str]


def _confirmed_quantity(item: TakeoffItem) -> Decimal:
    """Quantidade do item confirmado; `TakeoffItem.validate_review_state` garante que existe."""
    assert item.quantity is not None
    return item.quantity


def build_worksite_estimate(
    packet: TakeoffPacket,
    assignments: CodeAssignmentSet,
    cascade: Sequence[PriceCatalog],
    *,
    worksite_key: str,
    worksite_name: str,
    bdi_percent: Decimal,
    address: str | None = None,
    calc_plan: CalcPlan | None = None,
) -> EstimateBuildResult:
    """Monta o orçamento-base de uma obra a partir do takeoff confirmado e da cascata.

    Espelho fiel de `build_worksite_bulletin` na ordem das recusas — divergência de pacote,
    cascata inválida, item confirmado sem confirmação de código, confirmação de item
    desconhecido, nenhum item restante, plano citando item de fora, escala de quantidade
    não suportada e plano que não fecha com a quantidade confirmada —, mais as três que só
    existem quando há várias fontes:

    - confirmação sem citar catálogo (`ESTIMATE_ASSIGNMENT_CATALOG_REQUIRED`): com mais de
      uma tabela, resolver o código pela ordem da cascata seria a máquina escolhendo quem
      precifica o item;
    - citação fora da cascata (`ASSIGNMENT_CATALOG_UNKNOWN`);
    - código com forma incompatível com a origem do catálogo citado
      (`ESTIMATE_CODE_INVALID_FOR_ORIGIN`), checada ANTES da busca — um código SCO citado
      contra a EMOP é erro de fonte, não código ausente.

    Item confirmado no takeoff cujo código foi rejeitado não vira linha: ele sai declarado
    em `unpriced_item_ids`, porque rejeitar o código com a cascata inteira à vista significa
    que nenhuma fonte o precifica.

    `bdi_percent` é o percentual único do orçamento (ADR-0038): cada linha recebe
    `unit_price_with_bdi = TRUNC(unit_price * (1 + bdi_percent / 100), 2)` e o total da
    linha passa a recomputar sobre esse preço, não sobre `unit_price`.
    """
    if (
        assignments.plate_id != packet.plate_id
        or assignments.page_number != packet.page_number
        or assignments.image_sha256 != packet.image_sha256
    ):
        raise ValuationValidationError(
            "ESTIMATE_ASSIGNMENT_PACKET_MISMATCH",
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
    ensure_price_cascade(cascade)
    catalogs_by_digest = {catalog.source_sha256: catalog for catalog in cascade}

    confirmed_items = packet.confirmed_items()
    confirmed_ids = {item.id for item in confirmed_items}
    assignment_ids = {assignment.item_id for assignment in assignments.assignments}

    missing_ids = sorted(confirmed_ids - assignment_ids)
    if missing_ids:
        raise ValuationValidationError(
            "ESTIMATE_ASSIGNMENT_MISSING",
            "item confirmado no takeoff não possui confirmação de código",
            {"item_ids": missing_ids},
        )
    unknown_ids = sorted(assignment_ids - confirmed_ids)
    if unknown_ids:
        raise ValuationValidationError(
            "ESTIMATE_ASSIGNMENT_UNKNOWN_ITEM",
            "assignment aponta para item desconhecido ou não confirmado no pacote",
            {"item_ids": unknown_ids},
        )

    # Espelho de `CALC_PACKAGE_NOT_CLOSED`: sob a cardinalidade N:N a presença de um código
    # deixou de significar que o elemento acabou, e um pacote pela metade viraria orçamento
    # pela metade sem ninguém ser avisado.
    open_ids = sorted(assignments.open_package_item_ids() & confirmed_ids)
    if open_ids:
        raise ValuationValidationError(
            "ESTIMATE_PACKAGE_NOT_CLOSED",
            "item confirmado tem pacote de serviços em aberto; o orçamento não é montado "
            "pela metade",
            {"item_ids": open_ids},
        )

    packages = assignments.confirmed_codes_by_item()
    # PORTÃO TEMPORÁRIO, removido pela T6 (#78). Enquanto o builder iterar ITENS, cada item
    # vira uma linha, e um pacote precisaria escolher um dos códigos. Escolher em silêncio é
    # o defeito que a F-038 ataca.
    packaged_ids = sorted(
        item_id for item_id in confirmed_ids if len(packages.get(item_id, ())) > 1
    )
    if packaged_ids:
        raise ValuationValidationError(
            "ESTIMATE_PACKAGE_NOT_SUPPORTED",
            "item com mais de um código confirmado ainda não vira orçamento; a matriz de "
            "contribuições é que resolve o pacote",
            {"item_ids": packaged_ids},
        )

    assignments_by_item = {
        assignment.item_id: assignment
        for assignment in assignments.assignments
        if assignment.status == "confirmed"
    }
    rejected_ids = {
        assignment.item_id
        for assignment in assignments.assignments
        if assignment.status == "rejected"
    }
    unpriced_item_ids: list[str] = []
    included_items: list[TakeoffItem] = []
    for item in confirmed_items:
        if item.id in rejected_ids:
            unpriced_item_ids.append(item.id)
            continue
        included_items.append(item)

    if not included_items:
        raise ValuationValidationError(
            "ESTIMATE_NO_ITEMS",
            "todos os itens confirmados tiveram o código rejeitado; nenhum item restante",
            {"plate_id": packet.plate_id},
        )

    included_ids = {item.id for item in included_items}
    if calc_plan is not None:
        unknown_plan_ids = sorted({plan.item_id for plan in calc_plan.plans} - included_ids)
        if unknown_plan_ids:
            raise ValuationValidationError(
                "ESTIMATE_PLAN_UNKNOWN_ITEM",
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
            "ESTIMATE_QUANTITY_SCALE_UNSUPPORTED",
            "quantidade confirmada com mais de duas casas decimais não é suportada",
            {"item_ids": scale_unsupported},
        )

    plan_by_item = {plan.item_id: plan for plan in calc_plan.plans} if calc_plan else {}
    item_numbers: dict[str, str] = {}
    lines: list[EstimateLine] = []
    calc_sheets: list[CalcSheet] = []
    for index, item in enumerate(included_items, start=1):
        item_number = str(index)
        item_numbers[item.id] = item_number
        quantity = _confirmed_quantity(item)

        blocks = build_calc_blocks(plan_by_item.get(item.id), quantity=quantity, unit=item.unit)
        total_quantity = quantity_round(sum((block.subtotal for block in blocks), Decimal(0)))
        if total_quantity != quantity:
            raise ValuationValidationError(
                "ESTIMATE_PLAN_QUANTITY_MISMATCH",
                "plano de cálculo não fecha com a quantidade confirmada pelo orçamentista",
                {
                    "item_id": item.id,
                    "expected": str(quantity),
                    "recomputed": str(total_quantity),
                },
            )

        assignment = assignments_by_item[item.id]
        code = assignment.code
        assert code is not None  # assignment incluído sempre é "confirmed"
        cited_catalog = assignment.catalog_sha256
        if cited_catalog is None:
            raise ValuationValidationError(
                "ESTIMATE_ASSIGNMENT_CATALOG_REQUIRED",
                "confirmação de código sem fonte citada não precifica no orçamento-base; "
                "com mais de uma tabela, quem escolhe a fonte é o orçamentista",
                {"item_id": item.id, "code": code},
            )
        catalog = catalogs_by_digest.get(cited_catalog)
        if catalog is None:
            raise ValuationValidationError(
                "ASSIGNMENT_CATALOG_UNKNOWN",
                "confirmação cita uma fonte de preço que não está na cascata do orçamento",
                {
                    "item_id": item.id,
                    "cited": cited_catalog,
                    "available": [entry.source_sha256 for entry in cascade],
                },
            )
        if re.fullmatch(_code_pattern_for(catalog.origin), code) is None:
            raise ValuationValidationError(
                "ESTIMATE_CODE_INVALID_FOR_ORIGIN",
                "código confirmado não tem o formato da origem do catálogo citado",
                {"item_id": item.id, "code": code, "price_origin": catalog.origin.value},
            )

        entry = catalog.entry_for(code)
        unit_price_with_bdi = money_trunc(entry.unit_price * (1 + bdi_percent / 100))
        lines.append(
            EstimateLine(
                item_number=item_number,
                code=code,
                description=entry.description,
                unit=entry.unit,
                unit_price=entry.unit_price,
                unit_price_with_bdi=unit_price_with_bdi,
                quantity=quantity,
                total=money_trunc(quantity * unit_price_with_bdi),
                price_origin=catalog.origin,
                catalog_sha256=catalog.source_sha256,
                reference_month=catalog.reference_month,
                source_label=catalog.source_label,
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

    estimate = Estimate(
        worksite_key=worksite_key,
        worksite_name=worksite_name,
        address=address,
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        source_pdf_sha256=packet.source_pdf_sha256,
        bdi_percent=bdi_percent,
        cascade=[CatalogSource.of(catalog) for catalog in cascade],
        lines=lines,
        unpriced_item_ids=unpriced_item_ids,
        calc_sheets=calc_sheets,
        total_amount_without_bdi=sum(
            (money_trunc(line.unit_price * line.quantity) for line in lines), Decimal("0.00")
        ),
        total_amount=sum((line.total for line in lines), Decimal("0.00")),
        safety_notes=list(_ESTIMATE_SAFETY_NOTES),
    )
    return EstimateBuildResult(estimate=estimate, item_numbers=item_numbers)
