"""Contratos canônicos da medição de obra pública.

O JSON destes modelos é a fonte de verdade da medição; a planilha é um render auditado
dele. Todo valor que chega à planilha é `Decimal`: dinheiro trunca em duas casas
(`money_trunc`) e quantidade arredonda (`quantity_round`), e os validadores recomputam
cada total em vez de confiar no que foi informado.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Final, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from croquito_core.ids import new_uuid7
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.rounding import money_trunc, quantity_round
from croquito_valuation.sco import CONTRACT_CODE_PATTERN, SCO_CODE_PATTERN

if TYPE_CHECKING:  # pragma: no cover - só para anotação; `contract` importa deste módulo
    from croquito_valuation.contract import ContractLine, ContractWorkbook

VALUATION_SCHEMA_VERSION: Final = "2.0.0"
ITEM_NUMBER_PATTERN: Final = r"^\d{1,3}(\.\d{1,3}){0,3}$"
WORKSITE_KEY_PATTERN: Final = r"^[a-z0-9][a-z0-9-]{2,63}$"
REFERENCE_MONTH_PATTERN: Final = r"^\d{4}-\d{2}$"
SHA256_PATTERN: Final = r"^[a-f0-9]{64}$"

MAX_DESCRIPTION_LENGTH: Final = 2000
"""Tamanho máximo da descrição copiada do catálogo do cliente.

Não é folga arbitrária: a descrição de composição do catálogo público é um parágrafo
inteiro — o arquivo real do contrato traz 151 itens acima de 480 caracteres e o maior
deles tem 1356. Truncar seria alterar o texto que a prefeitura publicou, então o limite
admite o dado real em vez de recusá-lo.
"""


def _reject_binary_float(value: object) -> object:
    """Recusa `float` em campo decimal: precisão de centavo não nasce de binário."""
    if isinstance(value, float):
        raise ValuationValidationError(
            "DECIMAL_FROM_FLOAT",
            "valor decimal não pode vir de float; informe Decimal, int ou string decimal",
            {"value": repr(value)},
        )
    return value


ExactDecimal = Annotated[Decimal, BeforeValidator(_reject_binary_float)]
"""Decimal que recusa `float` na entrada; a conversão só é feita na leitura da planilha."""


def product_of(values: Sequence[Decimal]) -> Decimal:
    """Produto exato de uma sequência não vazia de decimais."""
    result = Decimal(1)
    for value in values:
        result *= value
    return result


class ValuationContractModel(BaseModel):
    """Configuração comum dos contratos de medição."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class PriceCatalogEntry(ValuationContractModel):
    """Item de preço do catálogo público, já normalizado."""

    code: str = Field(pattern=SCO_CODE_PATTERN)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    unit_price: ExactDecimal = Field(ge=0)
    family_code: str = Field(min_length=1, max_length=20)
    family_name: str = Field(min_length=1, max_length=200)
    subgroup_code: str = Field(min_length=1, max_length=20)
    subgroup_name: str = Field(min_length=1, max_length=200)


class PriceCatalog(ValuationContractModel):
    """Catálogo de preços importado de uma planilha de referência."""

    id: UUID = Field(default_factory=new_uuid7)
    source_label: str = Field(min_length=1, max_length=200)
    reference_month: str = Field(pattern=REFERENCE_MONTH_PATTERN)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    entries: list[PriceCatalogEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_codes(self) -> PriceCatalog:
        seen: set[str] = set()
        duplicated: list[str] = []
        for entry in self.entries:
            if entry.code in seen:
                duplicated.append(entry.code)
            seen.add(entry.code)
        if duplicated:
            raise ValuationValidationError(
                "CATALOG_DUPLICATE_CODE",
                "catálogo possui código repetido",
                {"codes": sorted(set(duplicated))},
            )
        return self

    def entry_for(self, code: str) -> PriceCatalogEntry:
        """Devolve o item do catálogo; código ausente falha alto."""
        for entry in self.entries:
            if entry.code == code:
                return entry
        raise ValuationValidationError(
            "CATALOG_CODE_UNKNOWN",
            "código não existe no catálogo importado",
            {"code": code},
        )

    def has_code(self, code: str) -> bool:
        """`True` quando o código existe no catálogo."""
        return any(entry.code == code for entry in self.entries)


class CalcRecipe(StrEnum):
    """Receitas de cálculo aceitas na memória; a lista é fechada por marco."""

    DIRECT_QUANTITY = "direct_quantity"
    LENGTH_TIMES_WIDTH = "length_times_width"
    PERIMETER_TIMES_HEIGHT = "perimeter_times_height"
    PERIM_HEIGHT_MINUS_OPENINGS = "perim_height_minus_openings"
    QTY_TIMES_MONTHS = "qty_times_months"
    DAYS_TIMES_HOURS = "days_times_hours"


class CalcOperand(ValuationContractModel):
    """Parcela impressa da memória de cálculo.

    `name` é dado, não identificador: chega em português na planilha ("PERÍMETRO").
    """

    name: str = Field(min_length=1, max_length=60)
    value: ExactDecimal
    unit: str | None = Field(default=None, min_length=1, max_length=20)


class CalcBlock(ValuationContractModel):
    """Bloco de cálculo de um item: operandos multiplicados menos deduções."""

    label: str = Field(min_length=1, max_length=120)
    recipe: CalcRecipe
    operands: list[CalcOperand] = Field(min_length=1)
    deductions: list[CalcOperand] = Field(default_factory=list)
    subtotal: ExactDecimal

    @property
    def expected_subtotal(self) -> Decimal:
        """Subtotal recomputado a partir dos operandos e deduções."""
        product = product_of([operand.value for operand in self.operands])
        deducted = sum((operand.value for operand in self.deductions), Decimal(0))
        return quantity_round(product - deducted)

    @model_validator(mode="after")
    def validate_subtotal(self) -> CalcBlock:
        expected = self.expected_subtotal
        if self.subtotal != expected:
            raise ValuationValidationError(
                "CALC_SUBTOTAL_MISMATCH",
                "subtotal do bloco não confere com os operandos declarados",
                {"label": self.label, "expected": str(expected), "declared": str(self.subtotal)},
            )
        return self


class CalcSheet(ValuationContractModel):
    """Memória de cálculo de um item do boletim de uma obra.

    A obra faz parte da identidade: o mesmo `item_number` se repete entre obras da mesma
    medição, e só o par `(worksite_key, item_number)` identifica a memória.
    """

    worksite_key: str = Field(pattern=WORKSITE_KEY_PATTERN)
    item_number: str = Field(pattern=ITEM_NUMBER_PATTERN)
    blocks: list[CalcBlock] = Field(min_length=1)
    total_quantity: ExactDecimal

    @property
    def expected_total_quantity(self) -> Decimal:
        """Quantidade recomputada a partir dos subtotais dos blocos."""
        return quantity_round(sum((block.subtotal for block in self.blocks), Decimal(0)))

    @model_validator(mode="after")
    def validate_total_quantity(self) -> CalcSheet:
        expected = self.expected_total_quantity
        if self.total_quantity != expected:
            raise ValuationValidationError(
                "CALC_TOTAL_MISMATCH",
                "quantidade total da memória não confere com a soma dos blocos",
                {
                    "worksite_key": self.worksite_key,
                    "item_number": self.item_number,
                    "expected": str(expected),
                    "declared": str(self.total_quantity),
                },
            )
        return self


class BulletinLine(ValuationContractModel):
    """Linha do boletim de medição de uma obra."""

    item_number: str = Field(pattern=ITEM_NUMBER_PATTERN)
    code: str = Field(pattern=CONTRACT_CODE_PATTERN)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    unit_price: ExactDecimal = Field(ge=0)
    quantity: ExactDecimal = Field(ge=0)
    total: ExactDecimal = Field(ge=0)

    @property
    def expected_total(self) -> Decimal:
        """Total recomputado: dinheiro trunca, nunca arredonda."""
        return money_trunc(self.quantity * self.unit_price)

    @model_validator(mode="after")
    def validate_total(self) -> BulletinLine:
        expected = self.expected_total
        if self.total != expected:
            raise ValuationValidationError(
                "LINE_TOTAL_MISMATCH",
                "total da linha não confere com quantidade x preço truncado",
                {
                    "item_number": self.item_number,
                    "expected": str(expected),
                    "declared": str(self.total),
                },
            )
        return self


class WorksiteBulletin(ValuationContractModel):
    """Boletim de medição de uma obra."""

    worksite_key: str = Field(pattern=WORKSITE_KEY_PATTERN)
    worksite_name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, min_length=1, max_length=200)
    contract_label: str | None = Field(default=None, min_length=1, max_length=120)
    lines: list[BulletinLine] = Field(min_length=1)
    total_amount: ExactDecimal = Field(ge=0)

    @property
    def expected_total_amount(self) -> Decimal:
        """Soma dos totais já truncados; o total da obra não trunca duas vezes."""
        return sum((line.total for line in self.lines), Decimal("0.00"))

    @model_validator(mode="after")
    def validate_bulletin(self) -> WorksiteBulletin:
        seen: set[str] = set()
        duplicated: list[str] = []
        for line in self.lines:
            if line.item_number in seen:
                duplicated.append(line.item_number)
            seen.add(line.item_number)
        if duplicated:
            raise ValuationValidationError(
                "BULLETIN_DUPLICATE_ITEM",
                "boletim possui item repetido",
                {"item_numbers": sorted(set(duplicated))},
            )
        expected = self.expected_total_amount
        if self.total_amount != expected:
            raise ValuationValidationError(
                "BULLETIN_TOTAL_MISMATCH",
                "total da obra não confere com a soma dos totais das linhas",
                {
                    "worksite_key": self.worksite_key,
                    "expected": str(expected),
                    "declared": str(self.total_amount),
                },
            )
        return self


class ReviewerDecision(ValuationContractModel):
    """Decisão humana rastreável do orçamentista.

    Duplicação local deliberada do `HumanDecision` do contexto de cena: o ADR-0016 mantém
    os dois contextos separados, e uma decisão sobre medição não é uma decisão sobre
    geometria. O que se repete é a forma, não o significado.
    """

    decision_id: str = Field(pattern=r"^vd_[a-f0-9]{16}$")
    action: Literal["confirm", "reject"]
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["orcamentista"]
    decided_at: datetime
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValuationValidationError(
                "DECISION_TIMESTAMP_NAIVE",
                "decisão do orçamentista exige data e hora com fuso horário",
                {"decided_at": value.isoformat()},
            )
        return value


class ValuationApproval(ValuationContractModel):
    """Aprovação nominal amarrada por digest ao conteúdo exato aprovado.

    Aprovar um conteúdo e exportar outro é o erro que este modelo existe para impedir:
    o digest é recomputado no portão e qualquer edição posterior invalida a aprovação.
    """

    decision: ReviewerDecision
    valuation_digest: str = Field(pattern=SHA256_PATTERN)


class Valuation(ValuationContractModel):
    """Medição de um período: um boletim por obra e as memórias de cálculo de cada item.

    Nada aqui carrega saldo contratual: o que já foi medido antes vive no
    `ContractWorkbook`, que entra por parâmetro no portão de exportação
    (`export_errors()`/`ensure_exportable()`). O portão falha fechado — medição sem
    aprovação nominal válida, fora da sequência de períodos ou acima do saldo não vira
    planilha publicada. Ver docs/architecture/VALUATION_CONTEXT.md.
    """

    schema_version: Literal["2.0.0"] = VALUATION_SCHEMA_VERSION
    id: UUID = Field(default_factory=new_uuid7)
    period_number: int = Field(ge=1)
    reference_label: str = Field(min_length=1, max_length=120)
    bulletins: list[WorksiteBulletin] = Field(min_length=1)
    calc_sheets: list[CalcSheet] = Field(min_length=1)
    approval: ValuationApproval | None = None

    @property
    def total_amount(self) -> Decimal:
        """Soma dos totais já truncados de cada obra; a medição não trunca duas vezes."""
        return sum((bulletin.total_amount for bulletin in self.bulletins), Decimal("0.00"))

    @model_validator(mode="after")
    def validate_worksites(self) -> Valuation:
        keys = [bulletin.worksite_key for bulletin in self.bulletins]
        if len(keys) != len(set(keys)):
            raise ValuationValidationError(
                "VALUATION_DUPLICATE_WORKSITE",
                "a medição possui mais de um boletim para a mesma obra",
                {"worksite_keys": sorted(keys)},
            )
        return self

    @model_validator(mode="after")
    def validate_calc_sheets(self) -> Valuation:
        sheet_keys = [(sheet.worksite_key, sheet.item_number) for sheet in self.calc_sheets]
        if len(sheet_keys) != len(set(sheet_keys)):
            raise ValuationValidationError(
                "VALUATION_DUPLICATE_CALC_SHEET",
                "há mais de uma memória de cálculo para o mesmo item da mesma obra",
                {"items": sorted(f"{key}/{item}" for key, item in sheet_keys)},
            )
        worksite_keys = {bulletin.worksite_key for bulletin in self.bulletins}
        orphan_keys = sorted({key for key, _ in sheet_keys} - worksite_keys)
        if orphan_keys:
            raise ValuationValidationError(
                "VALUATION_CALC_SHEET_MISMATCH",
                "há memória de cálculo de obra que não tem boletim na medição",
                {"worksite_key": orphan_keys[0], "only_in_calc_sheets": orphan_keys},
            )
        sheets_by_key = {
            (sheet.worksite_key, sheet.item_number): sheet for sheet in self.calc_sheets
        }
        for bulletin in self.bulletins:
            line_numbers = {line.item_number for line in bulletin.lines}
            sheet_numbers = {item for key, item in sheet_keys if key == bulletin.worksite_key}
            if sheet_numbers != line_numbers:
                raise ValuationValidationError(
                    "VALUATION_CALC_SHEET_MISMATCH",
                    "memórias de cálculo e linhas do boletim não são 1:1 por item",
                    {
                        "worksite_key": bulletin.worksite_key,
                        "only_in_bulletin": sorted(line_numbers - sheet_numbers),
                        "only_in_calc_sheets": sorted(sheet_numbers - line_numbers),
                    },
                )
            for line in bulletin.lines:
                sheet = sheets_by_key[(bulletin.worksite_key, line.item_number)]
                if sheet.total_quantity != line.quantity:
                    raise ValuationValidationError(
                        "VALUATION_QUANTITY_MISMATCH",
                        "quantidade da linha não confere com a memória de cálculo do item",
                        {
                            "worksite_key": bulletin.worksite_key,
                            "item_number": line.item_number,
                            "bulletin": str(line.quantity),
                            "calc_sheet": str(sheet.total_quantity),
                        },
                    )
        return self

    def calc_sheet_for(self, worksite_key: str, item_number: str) -> CalcSheet:
        """Memória de cálculo do item da obra; ausência falha alto (invariante validado)."""
        for sheet in self.calc_sheets:
            if sheet.worksite_key == worksite_key and sheet.item_number == item_number:
                return sheet
        raise ValuationValidationError(
            "VALUATION_CALC_SHEET_MISSING",
            "item do boletim não possui memória de cálculo",
            {"worksite_key": worksite_key, "item_number": item_number},
        )

    def content_digest(self) -> str:
        """SHA-256 do conteúdo canônico da medição, sem a aprovação que o referencia."""
        payload = json.dumps(
            self.model_dump(mode="json", exclude={"approval"}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def export_errors(self, contract: ContractWorkbook) -> list[str]:
        """Violações que impedem publicar a medição, no formato `CODE` ou `CODE:detalhe`."""
        errors: list[str] = []
        approval = self.approval
        if approval is None:
            errors.append("VALUATION_NOT_APPROVED")
        else:
            if approval.decision.action == "reject":
                errors.append("VALUATION_APPROVAL_REJECTED")
            if approval.valuation_digest != self.content_digest():
                errors.append("APPROVAL_CONTENT_MISMATCH")

        expected_period = contract.next_period_number
        if self.period_number != expected_period:
            errors.append(f"PERIOD_NOT_SEQUENTIAL:{expected_period}:{self.period_number}")

        contract_lines: dict[str, list[ContractLine]] = {}
        for contract_line in contract.lines:
            contract_lines.setdefault(contract_line.code, []).append(contract_line)
        measured: dict[str, Decimal] = {}
        for bulletin in self.bulletins:
            for line in bulletin.lines:
                matches = contract_lines.get(line.code, [])
                if not matches:
                    errors.append(
                        "CODE_NOT_IN_CONTRACT:"
                        f"{bulletin.worksite_key}:{line.item_number}:{line.code}"
                    )
                    continue
                if len(matches) > 1:
                    # O código responde por mais de um grupo do contrato: preço, unidade e
                    # saldo dependeriam de escolher um deles, e o portão não escolhe.
                    errors.append(
                        "CODE_AMBIGUOUS_IN_CONTRACT:"
                        f"{bulletin.worksite_key}:{line.item_number}:{line.code}"
                    )
                    continue
                contract_line = matches[0]
                if line.unit_price != contract_line.unit_price:
                    errors.append(f"LINE_PRICE_NOT_IN_CONTRACT:{line.code}")
                if line.unit != contract_line.unit:
                    errors.append(f"LINE_UNIT_NOT_IN_CONTRACT:{line.code}")
                measured[line.code] = measured.get(line.code, Decimal("0.00")) + line.quantity

        for code, quantity in measured.items():
            if quantity > contract_lines[code][0].balance_quantity:
                errors.append(f"BALANCE_EXCEEDED:{code}")
        return errors

    def ensure_exportable(self, contract: ContractWorkbook) -> None:
        """Portão de exportação: com qualquer violação aberta, nada é publicado."""
        errors = self.export_errors(contract)
        if errors:
            raise ValuationValidationError(
                "VALUATION_EXPORT_BLOCKED",
                "medição possui violações abertas e não pode ser exportada",
                {"errors": errors},
            )
