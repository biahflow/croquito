"""Consolidado contratual importado do MAPÃO anterior.

Este agregado é a fonte do saldo: para cada código contratado ele guarda o que foi
contratado, o que vigora depois das revisões (RE-RA), o que já foi lançado em cada
medição anterior, o acumulado e o saldo. A medição corrente (`Valuation`) não carrega
saldo nenhum: quem responde "ainda cabe?" é este consolidado, passado por parâmetro ao
portão de exportação.

RE-RA é **só leitura** no v1: o módulo reconcilia o efeito declarado de cada revisão
sobre o código correspondente, mas não cria nem altera aditivo. Acumulado e saldo chegam
declarados na planilha da prefeitura e são recomputados aqui — nenhum total informado
vale sem recomputo, como no resto do contexto de medição.

Duas coisas do contrato real mandam na forma deste agregado:

- as medições são identificadas pelo **número** que a planilha declara, não pela posição:
  `period_numbers` pode ter buraco (13ª → 15ª) e é ele que diz qual é a próxima;
- o mesmo código SCO aparece em grupos diferentes, então a chave de unicidade é o par
  grupo+código. Quem cita um código repetido sem dizer o grupo recebe
  `CODE_AMBIGUOUS_IN_CONTRACT`; o agregado nunca escolhe a linha.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise
from typing import Final, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from croquito_core.ids import new_uuid7
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    ITEM_NUMBER_PATTERN,
    MAX_DESCRIPTION_LENGTH,
    SHA256_PATTERN,
    ExactDecimal,
    ValuationContractModel,
)
from croquito_valuation.rounding import money_trunc
from croquito_valuation.sco import CONTRACT_CODE_PATTERN

CONTRACT_SCHEMA_VERSION: Final = "2.0.0"

_CONTRACT_WORKBOOK_ID_NAMESPACE: Final = uuid5(
    NAMESPACE_URL, "https://croquito.local/valuation/contract-workbook"
)


def contract_workbook_id_for(source_sha256: str) -> UUID:
    """Id derivado do conteúdo: reimportar o mesmo arquivo devolve o mesmo consolidado."""
    return uuid5(_CONTRACT_WORKBOOK_ID_NAMESPACE, source_sha256)


def _duplicated(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicated: set[str] = set()
    for value in values:
        if value in seen:
            duplicated.add(value)
        seen.add(value)
    return sorted(duplicated)


def _duplicated_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Pares repetidos, na ordem em que a repetição aparece."""
    seen: set[tuple[str, str]] = set()
    duplicated: list[tuple[str, str]] = []
    for pair in pairs:
        if pair in seen and pair not in duplicated:
            duplicated.append(pair)
        seen.add(pair)
    return duplicated


class PeriodProgress(ValuationContractModel):
    """Par QUANTIDADE|VALOR de uma medição já lançada no consolidado."""

    period_number: int = Field(ge=1)
    quantity: ExactDecimal = Field(ge=0)
    amount: ExactDecimal = Field(ge=0)


class AmendmentLine(ValuationContractModel):
    """Efeito de uma RE-RA sobre um código: delta com sinal ou item novo."""

    code: str = Field(pattern=CONTRACT_CODE_PATTERN)
    quantity_delta: ExactDecimal
    is_new_item: bool = False
    note: str | None = Field(default=None, min_length=1, max_length=200)


class Amendment(ValuationContractModel):
    """Uma revisão contratual (RE-RA) e o conjunto de códigos que ela altera."""

    label: str = Field(min_length=1, max_length=60)
    lines: list[AmendmentLine] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_codes(self) -> Amendment:
        duplicated = _duplicated([line.code for line in self.lines])
        if duplicated:
            raise ValuationValidationError(
                "AMENDMENT_DUPLICATE_CODE",
                "a mesma RE-RA altera o mesmo código mais de uma vez",
                {"label": self.label, "codes": duplicated},
            )
        return self


class ContractLine(ValuationContractModel):
    """Linha do consolidado: contratado, vigente, medido por período, acumulado e saldo."""

    group_label: str = Field(min_length=1, max_length=120)
    item_number: str = Field(pattern=ITEM_NUMBER_PATTERN)
    code: str = Field(pattern=CONTRACT_CODE_PATTERN)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    unit_price: ExactDecimal = Field(ge=0)
    contract_quantity: ExactDecimal = Field(ge=0)
    amended_quantity: ExactDecimal = Field(ge=0)
    periods: list[PeriodProgress] = Field(default_factory=list)
    accumulated_quantity: ExactDecimal = Field(ge=0)
    accumulated_amount: ExactDecimal = Field(ge=0)
    balance_quantity: ExactDecimal = Field(ge=0)

    @property
    def expected_accumulated_quantity(self) -> Decimal:
        """Acumulado de quantidade recomputado a partir dos períodos lançados."""
        return sum((period.quantity for period in self.periods), Decimal("0.00"))

    @property
    def expected_accumulated_amount(self) -> Decimal:
        """Soma dos valores já truncados; o acumulado não trunca duas vezes."""
        return sum((period.amount for period in self.periods), Decimal("0.00"))

    @property
    def expected_balance_quantity(self) -> Decimal:
        """Saldo previsto: quantidade vigente menos o acumulado."""
        return self.amended_quantity - self.accumulated_quantity

    def _identity(self) -> dict[str, object]:
        return {"item_number": self.item_number, "code": self.code}

    @model_validator(mode="after")
    def validate_periods(self) -> ContractLine:
        numbers = [period.period_number for period in self.periods]
        if any(later <= earlier for earlier, later in pairwise(numbers)):
            raise ValuationValidationError(
                "PERIOD_SEQUENCE_BROKEN",
                "os períodos lançados na linha não estão em ordem crescente",
                {**self._identity(), "period_numbers": numbers},
            )
        for period in self.periods:
            expected = money_trunc(period.quantity * self.unit_price)
            if period.amount != expected:
                raise ValuationValidationError(
                    "PERIOD_AMOUNT_MISMATCH",
                    "valor do período não confere com quantidade x preço truncado",
                    {
                        **self._identity(),
                        "period_number": period.period_number,
                        "expected": str(expected),
                        "declared": str(period.amount),
                    },
                )
        return self

    @model_validator(mode="after")
    def validate_accumulated(self) -> ContractLine:
        checks = (
            ("accumulated_quantity", self.accumulated_quantity, self.expected_accumulated_quantity),
            ("accumulated_amount", self.accumulated_amount, self.expected_accumulated_amount),
        )
        for field_name, declared, expected in checks:
            if declared != expected:
                raise ValuationValidationError(
                    "CONTRACT_ACCUMULATED_MISMATCH",
                    "acumulado declarado não confere com a soma dos períodos",
                    {
                        **self._identity(),
                        "field": field_name,
                        "expected": str(expected),
                        "declared": str(declared),
                    },
                )
        return self

    @model_validator(mode="after")
    def validate_balance(self) -> ContractLine:
        expected = self.expected_balance_quantity
        if expected < 0:
            raise ValuationValidationError(
                "CONTRACT_BALANCE_NEGATIVE",
                "acumulado da linha excede a quantidade vigente",
                {
                    **self._identity(),
                    "amended_quantity": str(self.amended_quantity),
                    "accumulated_quantity": str(self.accumulated_quantity),
                },
            )
        if self.balance_quantity != expected:
            raise ValuationValidationError(
                "CONTRACT_BALANCE_MISMATCH",
                "saldo declarado não confere com vigente menos acumulado",
                {
                    **self._identity(),
                    "expected": str(expected),
                    "declared": str(self.balance_quantity),
                },
            )
        return self


class ContractWorkbook(ValuationContractModel):
    """Consolidado contratual de um contrato, como lido da planilha da prefeitura."""

    schema_version: Literal["2.0.0"] = CONTRACT_SCHEMA_VERSION
    id: UUID = Field(default_factory=new_uuid7)
    source_label: str = Field(min_length=1, max_length=200)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_label: str | None = Field(default=None, min_length=1, max_length=120)
    period_numbers: list[int]
    lines: list[ContractLine] = Field(min_length=1)
    amendments: list[Amendment] = Field(default_factory=list)

    @property
    def period_count(self) -> int:
        """Quantas medições o consolidado já traz lançadas."""
        return len(self.period_numbers)

    @property
    def next_period_number(self) -> int:
        """Número da próxima medição: a seguinte à última lançada, ou a primeira."""
        return self.period_numbers[-1] + 1 if self.period_numbers else 1

    @model_validator(mode="after")
    def validate_period_sequence(self) -> ContractWorkbook:
        numbers = self.period_numbers
        broken = any(number < 1 for number in numbers) or any(
            later <= earlier for earlier, later in pairwise(numbers)
        )
        if broken:
            raise ValuationValidationError(
                "PERIOD_SEQUENCE_BROKEN",
                "os números de medição do consolidado não crescem a partir de 1",
                {"period_numbers": list(numbers)},
            )
        return self

    @model_validator(mode="after")
    def validate_unique_lines(self) -> ContractWorkbook:
        duplicated_items = _duplicated_pairs(
            [(line.group_label, line.item_number) for line in self.lines]
        )
        if duplicated_items:
            raise ValuationValidationError(
                "CONTRACT_DUPLICATE_ITEM",
                "o consolidado possui item repetido no mesmo grupo",
                {
                    "items": [
                        {"group_label": group, "item_number": item}
                        for group, item in duplicated_items
                    ]
                },
            )
        duplicated_codes = _duplicated_pairs([(line.group_label, line.code) for line in self.lines])
        if duplicated_codes:
            raise ValuationValidationError(
                "CONTRACT_DUPLICATE_CODE",
                "o consolidado possui código repetido no mesmo grupo",
                {
                    "codes": [
                        {"group_label": group, "code": code} for group, code in duplicated_codes
                    ]
                },
            )
        return self

    @model_validator(mode="after")
    def validate_period_numbers(self) -> ContractWorkbook:
        for line in self.lines:
            declared = [period.period_number for period in line.periods]
            if declared and declared != self.period_numbers:
                raise ValuationValidationError(
                    "CONTRACT_PERIOD_NUMBERS_MISMATCH",
                    "linha lança medições diferentes das que o consolidado declara",
                    {
                        "item_number": line.item_number,
                        "code": line.code,
                        "expected": list(self.period_numbers),
                        "declared": declared,
                    },
                )
        return self

    @model_validator(mode="after")
    def validate_amendments(self) -> ContractWorkbook:
        lines_by_code = self._lines_by_code()
        for amendment in self.amendments:
            for amendment_line in amendment.lines:
                targets = lines_by_code.get(amendment_line.code, [])
                if len(targets) > 1:
                    raise ValuationValidationError(
                        "CODE_AMBIGUOUS_IN_CONTRACT",
                        "a RE-RA altera um código que o consolidado repete em mais de um "
                        "grupo, e o agregado não escolhe a linha",
                        {
                            "label": amendment.label,
                            "code": amendment_line.code,
                            "groups": [line.group_label for line in targets],
                        },
                    )
        deltas: dict[str, Decimal] = {}
        for amendment in self.amendments:
            for amendment_line in amendment.lines:
                deltas[amendment_line.code] = (
                    deltas.get(amendment_line.code, Decimal("0.00")) + amendment_line.quantity_delta
                )
        for line in self.lines:
            expected = line.contract_quantity + deltas.get(line.code, Decimal("0.00"))
            if expected < 0:
                raise ValuationValidationError(
                    "AMENDMENT_NEGATIVE_RESULT",
                    "as RE-RA reduzem o código abaixo de zero",
                    {
                        "item_number": line.item_number,
                        "code": line.code,
                        "contract_quantity": str(line.contract_quantity),
                        "delta": str(deltas.get(line.code, Decimal("0.00"))),
                    },
                )
            if line.amended_quantity != expected:
                raise ValuationValidationError(
                    "AMENDMENT_APPLICATION_MISMATCH",
                    "quantidade vigente não confere com contratual mais as RE-RA do código",
                    {
                        "item_number": line.item_number,
                        "code": line.code,
                        "expected": str(expected),
                        "declared": str(line.amended_quantity),
                    },
                )
        for amendment in self.amendments:
            for amendment_line in amendment.lines:
                targets = lines_by_code.get(amendment_line.code, [])
                target = targets[0] if targets else None
                if amendment_line.is_new_item:
                    if target is None or target.contract_quantity != 0:
                        raise ValuationValidationError(
                            "AMENDMENT_NEW_ITEM_INVALID",
                            "item novo de RE-RA precisa existir no consolidado com contratual zero",
                            {
                                "label": amendment.label,
                                "code": amendment_line.code,
                                "contract_quantity": (
                                    None if target is None else str(target.contract_quantity)
                                ),
                            },
                        )
                elif target is None:
                    raise ValuationValidationError(
                        "AMENDMENT_TARGET_UNKNOWN",
                        "RE-RA altera código que não existe no consolidado",
                        {"label": amendment.label, "code": amendment_line.code},
                    )
        return self

    def _lines_by_code(self) -> dict[str, list[ContractLine]]:
        """Linhas por código; o mesmo código pode responder por mais de um grupo."""
        by_code: dict[str, list[ContractLine]] = {}
        for line in self.lines:
            by_code.setdefault(line.code, []).append(line)
        return by_code

    def lines_for_code(self, code: str) -> list[ContractLine]:
        """Todas as linhas do código, na ordem do consolidado; sem o código, lista vazia."""
        return [line for line in self.lines if line.code == code]

    def line_for_code(self, code: str, *, group_label: str | None = None) -> ContractLine:
        """Linha do consolidado; código fora do contrato ou ambíguo falha alto.

        Sem `group_label` o código precisa ser único no consolidado: com o mesmo código em
        grupos diferentes, escolher uma linha seria adivinhar de qual grupo é a medição.
        """
        matches = self.lines_for_code(code)
        if group_label is not None:
            matches = [line for line in matches if line.group_label == group_label]
        if not matches:
            raise ValuationValidationError(
                "CODE_NOT_IN_CONTRACT",
                "código não existe no consolidado contratual importado",
                {"code": code, "group_label": group_label},
            )
        if len(matches) > 1:
            raise ValuationValidationError(
                "CODE_AMBIGUOUS_IN_CONTRACT",
                "código existe em mais de um grupo do consolidado e o grupo não foi informado",
                {"code": code, "groups": [line.group_label for line in matches]},
            )
        return matches[0]
