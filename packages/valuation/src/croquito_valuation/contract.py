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

from collections.abc import Mapping
from datetime import datetime
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

CONTRACT_SCHEMA_VERSION: Final = "4.0.0"

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
    """Par QUANTIDADE|VALOR de uma medição já lançada no consolidado.

    `unit_price` é o preço **daquele** período, e só existe quando ele difere do contratado —
    isto é, depois de um reajuste (F-039, ADR-0055). Ausente significa "medido pelo preço
    contratado", que é a verdade sobre todo período anterior à feature e sobre todo contrato
    que nunca reajustou.

    Sem este campo o consolidado não conseguiria representar o próprio passado: a linha tem UM
    `unit_price`, e `validate_periods` exige que cada período bata com ele. Um contrato
    reajustado tem períodos em bases diferentes, e forçá-los ao mesmo preço reescreveria
    dinheiro já pago — que é exatamente o que a decisão 6 do ADR proíbe.
    """

    period_number: int = Field(ge=1)
    quantity: ExactDecimal = Field(ge=0)
    amount: ExactDecimal = Field(ge=0)
    unit_price: ExactDecimal | None = Field(default=None, gt=0)


class AmendmentLine(ValuationContractModel):
    """Efeito de uma RE-RA sobre um código: delta com sinal ou item novo."""

    code: str = Field(pattern=CONTRACT_CODE_PATTERN)
    quantity_delta: ExactDecimal
    is_new_item: bool = False
    note: str | None = Field(default=None, min_length=1, max_length=200)

    #: Só quando `is_new_item` e a linha nasce no sistema: um consolidado vindo do orçamento
    #: assinado não tem linha zerada para um código nunca contratado, então a linha nova precisa
    #: trazer texto, unidade e preço, resolvidos no catálogo contratual e materializados no ato
    #: (ADR-0056, decisão 7). Opcionais no modelo porque a leitura do MAPÃO histórico já traz a
    #: linha zerada pronta e não os informa — lá são redundantes.
    description: str | None = Field(default=None, min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    unit_price: ExactDecimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_new_item_fields(self) -> AmendmentLine:
        materialized = {
            "description": self.description,
            "unit": self.unit,
            "unit_price": self.unit_price,
        }
        if not self.is_new_item:
            present = sorted(name for name, value in materialized.items() if value is not None)
            if present:
                raise ValuationValidationError(
                    "AMENDMENT_MATERIALIZATION_UNEXPECTED",
                    "só item novo materializa descrição, unidade e preço; item existente os "
                    "herda da linha e não pode declarar uma segunda fonte",
                    {"code": self.code, "fields": present},
                )
        return self


class Amendment(ValuationContractModel):
    """Uma revisão contratual (RE-RA) e o conjunto de códigos que ela altera.

    A procedência — quem declarou, quando e contra qual publicação — é **opcional no modelo** e
    exigida no ato de declaração (`ensure_declared`). Enquanto a RE-RA só era lida do MAPÃO, a
    procedência era implícita e bastava (veio da planilha que a prefeitura assinou); consolidado
    gravado antes desta feature e a leitura do MAPÃO histórico nascem sem ela e precisam
    continuar validando (ADR-0056, decisões 1 e 8). No dia em que a RE-RA nasce aqui dentro, a
    ausência vira lacuna de auditoria, e o guard recusa.
    """

    label: str = Field(min_length=1, max_length=60)
    lines: list[AmendmentLine] = Field(min_length=1)
    declared_by: str | None = Field(default=None, min_length=1, max_length=120)
    declared_at: datetime | None = None
    #: O período que a RE-RA cobre, como a publicação oficial o nomeia. Texto porque é citação,
    #: não intervalo a calcular — simétrico a `PriceAdjustment.reference_period`.
    reference_period: str | None = Field(default=None, min_length=1, max_length=60)
    note: str | None = Field(default=None, min_length=1, max_length=300)

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

    @model_validator(mode="after")
    def validate_declared_at_aware(self) -> Amendment:
        if self.declared_at is not None and (
            self.declared_at.tzinfo is None or self.declared_at.utcoffset() is None
        ):
            raise ValuationValidationError(
                "AMENDMENT_TIMESTAMP_NAIVE",
                "declaração de RE-RA exige data e hora com fuso horário",
                {"label": self.label, "declared_at": self.declared_at.isoformat()},
            )
        return self

    @property
    def has_provenance(self) -> bool:
        """Se a RE-RA carrega os três campos de procedência que a tornam conferível."""
        return (
            self.declared_by is not None
            and self.declared_at is not None
            and self.reference_period is not None
        )

    def ensure_declared(self) -> None:
        """Guard do ato de declaração: RE-RA nascida no sistema exige procedência.

        A leitura do MAPÃO não passa por aqui — lá a procedência é implícita. Chamado no
        caminho de entrada da API (ADR-0056, decisão 1): fator sem índice não é conferível, e
        RE-RA sem citação da publicação também não.
        """
        missing = [
            name
            for name, value in (
                ("declared_by", self.declared_by),
                ("declared_at", self.declared_at),
                ("reference_period", self.reference_period),
            )
            if value is None
        ]
        if missing:
            raise ValuationValidationError(
                "AMENDMENT_PROVENANCE_MISSING",
                "declaração de RE-RA exige autor, instante com fuso e período de referência",
                {"label": self.label, "missing": missing},
            )


class PriceAdjustment(ValuationContractModel):
    """Reajuste declarado sobre o consolidado (F-039, ADR-0055).

    É **ato humano**, não cálculo implícito: carrega autor, instante e a citação que torna a
    declaração conferível contra a publicação oficial. Um tipo só, discriminado por `kind`,
    porque o consumidor — boletim, portão de exportação e memória — precisa de UMA noção de
    preço vigente (ADR-0055, decisão 2).

    `index_factor` é o mecanismo legal típico da obra licitada: um fator sobre o preço
    contratado, com índice e período de referência. `catalog_version` é o contrato que passou
    a pagar por outra data-base da tabela, e por isso **materializa o preço de cada código**
    no ato (decisão 4): o consolidado precisa explicar o próprio preço meses depois, sem
    depender de aquele catálogo ainda estar instalado em algum lugar.

    O que este modelo deliberadamente NÃO tem: escopo por item. Fórmula paramétrica — índices
    distintos para mão de obra e insumos — é extensão declarada (decisão 10), e a ausência do
    campo já significa "contrato inteiro".
    """

    kind: Literal["index_factor", "catalog_version"]
    declared_by: str = Field(min_length=1, max_length=120)
    declared_at: datetime
    #: O período que o reajuste cobre, como a publicação oficial o nomeia ("08/2025 a
    #: 07/2026"). Texto porque é citação, não intervalo a calcular.
    reference_period: str = Field(min_length=1, max_length=60)
    note: str | None = Field(default=None, min_length=1, max_length=300)

    #: Só em `index_factor`. Nome do índice, obrigatório junto do fator: fator sem índice não
    #: é conferível, e número que ninguém consegue conferir não entra na medição.
    index_label: str | None = Field(default=None, min_length=1, max_length=60)
    factor: ExactDecimal | None = Field(default=None, gt=0)

    #: Só em `catalog_version`. A versão de onde os preços saíram, e o preço por código.
    catalog_label: str | None = Field(default=None, min_length=1, max_length=200)
    catalog_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    prices_by_code: dict[str, ExactDecimal] | None = None

    @model_validator(mode="after")
    def validate_kind(self) -> PriceAdjustment:
        if self.declared_at.tzinfo is None or self.declared_at.utcoffset() is None:
            raise ValuationValidationError(
                "PRICE_ADJUSTMENT_TIMESTAMP_NAIVE",
                "reajuste exige data e hora com fuso horário",
                {"declared_at": self.declared_at.isoformat()},
            )
        if self.kind == "index_factor":
            if self.factor is None or self.index_label is None:
                raise ValuationValidationError(
                    "PRICE_ADJUSTMENT_INDEX_INCOMPLETE",
                    "reajuste por índice exige fator e índice declarados",
                    {"factor": str(self.factor), "index_label": self.index_label},
                )
            if self.catalog_sha256 is not None or self.prices_by_code is not None:
                raise ValuationValidationError(
                    "PRICE_ADJUSTMENT_KIND_MISMATCH",
                    "reajuste por índice não carrega versão de tabela",
                    {"kind": self.kind},
                )
            return self
        if self.catalog_sha256 is None or not self.prices_by_code:
            raise ValuationValidationError(
                "PRICE_ADJUSTMENT_CATALOG_INCOMPLETE",
                "reajuste por versão de tabela exige o digest da versão e o preço por código",
                {"catalog_sha256": self.catalog_sha256},
            )
        if self.factor is not None or self.index_label is not None:
            raise ValuationValidationError(
                "PRICE_ADJUSTMENT_KIND_MISMATCH",
                "reajuste por versão de tabela não carrega fator de índice",
                {"kind": self.kind},
            )
        for price in self.prices_by_code.values():
            if price <= 0:
                raise ValuationValidationError(
                    "PRICE_ADJUSTMENT_PRICE_INVALID",
                    "preço de versão nova precisa ser maior que zero",
                    {"prices": sorted(self.prices_by_code)},
                )
        return self

    def apply_to(self, code: str, price: Decimal) -> Decimal:
        """O preço depois DESTE reajuste, exato — o truncamento é do fim da cadeia.

        `index_factor` multiplica; `catalog_version` **substitui**, porque a versão nova não
        é um percentual sobre o contratado, é outro preço. Truncar aqui, a cada passo,
        acumularia o erro do truncamento na composição.
        """
        if self.kind == "index_factor":
            assert self.factor is not None  # garantido por `validate_kind`
            return price * self.factor
        assert self.prices_by_code is not None
        return self.prices_by_code.get(code, price)


class ContractLine(ValuationContractModel):
    """Linha do consolidado: contratado, vigente, medido por período, acumulado e saldo."""

    group_label: str = Field(min_length=1, max_length=120)
    item_number: str = Field(pattern=ITEM_NUMBER_PATTERN)
    code: str = Field(pattern=CONTRACT_CODE_PATTERN)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    unit_price: ExactDecimal = Field(ge=0)
    contract_quantity: ExactDecimal = Field(ge=0)
    #: Quantidade vigente. **Opcional e conferência, nunca dono** (ADR-0056, decisão 3): o
    #: vigente é derivado por `ContractWorkbook.current_quantity`. Quando presente — a leitura
    #: do MAPÃO e o consolidado gravado antes desta feature a trazem —, é asserção externa que
    #: precisa bater com o derivado, e a divergência recusa com `AMENDMENT_APPLICATION_MISMATCH`.
    amended_quantity: ExactDecimal | None = Field(default=None, ge=0)
    periods: list[PeriodProgress] = Field(default_factory=list)
    accumulated_quantity: ExactDecimal = Field(ge=0)
    accumulated_amount: ExactDecimal = Field(ge=0)
    #: Saldo. Opcional e conferência, como `amended_quantity`: derivado por
    #: `ContractWorkbook.current_balance_quantity` (`vigente − acumulado`). Presente, confere.
    balance_quantity: ExactDecimal | None = Field(default=None, ge=0)

    @property
    def expected_accumulated_quantity(self) -> Decimal:
        """Acumulado de quantidade recomputado a partir dos períodos lançados."""
        return sum((period.quantity for period in self.periods), Decimal("0.00"))

    @property
    def expected_accumulated_amount(self) -> Decimal:
        """Soma dos valores já truncados; o acumulado não trunca duas vezes."""
        return sum((period.amount for period in self.periods), Decimal("0.00"))

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
            # O preço DAQUELE período: o dele quando declarado, o contratado quando não.
            # Conferir tudo contra o contratado recusaria todo período medido depois de um
            # reajuste, e a recusa estaria errada — o dinheiro daquele período é aquele.
            expected = money_trunc(period.quantity * (period.unit_price or self.unit_price))
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


class ContractWorkbook(ValuationContractModel):
    """Consolidado contratual de um contrato, como lido da planilha da prefeitura."""

    # `2.0.0` e `3.0.0` continuam válidos: consolidado gravado antes da F-039/F-040 responde
    # sem reajuste e sem RE-RA com procedência, que é a verdade sobre ele (ADR-0055 decisão 8,
    # ADR-0056 decisão 8). Mesma disciplina de `Valuation`.
    schema_version: Literal["2.0.0", "3.0.0", "4.0.0"] = CONTRACT_SCHEMA_VERSION
    id: UUID = Field(default_factory=new_uuid7)
    source_label: str = Field(min_length=1, max_length=200)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_label: str | None = Field(default=None, min_length=1, max_length=120)
    period_numbers: list[int]
    lines: list[ContractLine] = Field(min_length=1)
    amendments: list[Amendment] = Field(default_factory=list)
    #: Reajustes declarados, na ordem em que valeram. Lista, e não campo único, porque
    #: reajuste anual COMPÕE sobre o anterior e porque a segunda medição precisa poder mostrar
    #: de onde veio o preço da primeira (ADR-0055, decisão 5).
    adjustments: list[PriceAdjustment] = Field(default_factory=list, max_length=40)

    @property
    def period_count(self) -> int:
        """Quantas medições o consolidado já traz lançadas."""
        return len(self.period_numbers)

    @property
    def is_adjusted(self) -> bool:
        """Se algum reajuste foi declarado. Sem nenhum, vigente é contratado, bit a bit."""
        return bool(self.adjustments)

    def current_unit_price(self, line: ContractLine) -> Decimal:
        """O preço que o contrato paga HOJE por esta linha.

        DERIVADO, nunca gravado (ADR-0055, decisão 3): um campo ao lado da declaração que o
        produz seria um segundo lugar dizendo a mesma coisa, e aqui a discordância é dinheiro.

        Os reajustes se aplicam na ordem declarada e o dinheiro trunca **uma vez, no fim**:
        truncar a cada passo acumularia o erro do truncamento na composição.
        """
        price = line.unit_price
        for adjustment in self.adjustments:
            price = adjustment.apply_to(line.code, price)
        return money_trunc(price)

    def amendment_deltas(self) -> dict[str, Decimal]:
        """Soma dos deltas de RE-RA por código, na ordem declarada.

        Quantidade não trunca: é `ExactDecimal`, e o truncamento é do dinheiro no fim da
        cadeia (ADR-0056, decisão 6; feature.md, Constraints).
        """
        deltas: dict[str, Decimal] = {}
        for amendment in self.amendments:
            for amendment_line in amendment.lines:
                deltas[amendment_line.code] = (
                    deltas.get(amendment_line.code, Decimal("0.00")) + amendment_line.quantity_delta
                )
        return deltas

    def current_quantity(self, line: ContractLine) -> Decimal:
        """A quantidade que o contrato vigora HOJE para esta linha.

        DERIVADA, nunca gravada (ADR-0056, decisão 3), espelhando `current_unit_price`:
        `contract_quantity` mais a soma dos deltas das RE-RA que citam o código. Sem RE-RA
        declarada, devolve o contratado **bit a bit**.
        """
        return line.contract_quantity + self.amendment_deltas().get(line.code, Decimal("0.00"))

    def current_balance_quantity(self, line: ContractLine) -> Decimal:
        """O saldo vigente: quantidade vigente menos o acumulado da linha."""
        return self.current_quantity(line) - line.accumulated_quantity

    @model_validator(mode="after")
    def validate_adjustments_cover_every_code(self) -> ContractWorkbook:
        """Versão nova de tabela precifica TODO código contratado, ou não precifica nenhum.

        Reprecificar metade do contrato é pior do que não reprecificar: metade das linhas
        andaria e a outra metade ficaria, sem que nada na planilha explicasse a diferença
        (ADR-0055, decisão 4).
        """
        codes = {line.code for line in self.lines}
        for adjustment in self.adjustments:
            if adjustment.kind != "catalog_version":
                continue
            precificados = set(adjustment.prices_by_code or {})
            faltando = sorted(codes - precificados)
            if faltando:
                raise ValuationValidationError(
                    "PRICE_ADJUSTMENT_CODE_MISSING",
                    "a versão nova da tabela não precifica todo código contratado",
                    {"missing": faltando[:20], "catalog_sha256": adjustment.catalog_sha256},
                )
        return self

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
        deltas = self.amendment_deltas()
        for line in self.lines:
            # Vigente DERIVADO: contratado mais os deltas das RE-RA do código (decisão 3).
            vigente = line.contract_quantity + deltas.get(line.code, Decimal("0.00"))
            if vigente < 0:
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
            # `amended_quantity` é conferência, não dono: presente, precisa bater com o
            # derivado; ausente, não há segunda fonte a conferir (decisão 3).
            if line.amended_quantity is not None and line.amended_quantity != vigente:
                raise ValuationValidationError(
                    "AMENDMENT_APPLICATION_MISMATCH",
                    "quantidade vigente não confere com contratual mais as RE-RA do código",
                    {
                        "item_number": line.item_number,
                        "code": line.code,
                        "expected": str(vigente),
                        "declared": str(line.amended_quantity),
                    },
                )
            # Saldo vigente = vigente − acumulado. Negativo recusa; o saldo declarado, quando
            # presente, é conferência contra o derivado (validação migrada da linha, que não
            # conhecia as RE-RA — feature.md, Risks).
            balance = vigente - line.accumulated_quantity
            if balance < 0:
                raise ValuationValidationError(
                    "CONTRACT_BALANCE_NEGATIVE",
                    "acumulado da linha excede a quantidade vigente",
                    {
                        "item_number": line.item_number,
                        "code": line.code,
                        "current_quantity": str(vigente),
                        "accumulated_quantity": str(line.accumulated_quantity),
                    },
                )
            if line.balance_quantity is not None and line.balance_quantity != balance:
                raise ValuationValidationError(
                    "CONTRACT_BALANCE_MISMATCH",
                    "saldo declarado não confere com vigente menos acumulado",
                    {
                        "item_number": line.item_number,
                        "code": line.code,
                        "expected": str(balance),
                        "declared": str(line.balance_quantity),
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


def _next_item_number(lines: list[ContractLine], group_label: str) -> str:
    """Próximo `item_number` inteiro livre no grupo, para a linha de um item novo."""
    tops = [
        int(head)
        for line in lines
        if line.group_label == group_label and (head := line.item_number.split(".")[0]).isdigit()
    ]
    return str(max(tops) + 1 if tops else 1)


def apply_declared_amendment(workbook: ContractWorkbook, amendment: Amendment) -> ContractWorkbook:
    """Aplica uma RE-RA declarada ao consolidado, antes de ele ser gravado (ADR-0056, decisão 1).

    - Exige procedência (`ensure_declared`): a RE-RA nasce aqui dentro, não é lida do MAPÃO.
    - Materializa a linha do item novo cujo código ainda não existe no consolidado, a partir de
      `description`, `unit` e `unit_price` já resolvidos no catálogo contratual pelo chamador
      (decisão 7). Código ausente do consolidado e sem materialização recusa — não há de onde a
      linha nascer.
    - Devolve um consolidado **novo e revalidado**: `current_quantity` passa a refletir a RE-RA,
      e a imutabilidade na rodada faz a declaração valer para o período inteiro. Reconstruir o
      modelo (em vez de `model_copy`) reexecuta `validate_amendments`, que recusa item novo
      sobre linha não zerada, alvo inexistente e divergência de conferência.
    """
    amendment.ensure_declared()
    lines = list(workbook.lines)
    existing_codes = {line.code for line in lines}
    group_labels = {line.group_label for line in lines}
    for amendment_line in amendment.lines:
        if amendment_line.code in existing_codes or not amendment_line.is_new_item:
            # Item existente e item que já tem linha zerada (leitura do MAPÃO): nada a criar; a
            # aplicação é o delta, e `validate_amendments` confere. Item novo sem linha e sem
            # `is_new_item` cai em `AMENDMENT_TARGET_UNKNOWN` na revalidação.
            continue
        if amendment_line.description is None or amendment_line.unit is None or (
            amendment_line.unit_price is None
        ):
            raise ValuationValidationError(
                "AMENDMENT_NEW_ITEM_INVALID",
                "item novo cujo código não existe no consolidado precisa materializar descrição, "
                "unidade e preço do catálogo contratual",
                {"label": amendment.label, "code": amendment_line.code},
            )
        if len(group_labels) != 1:
            raise ValuationValidationError(
                "AMENDMENT_NEW_ITEM_GROUP_AMBIGUOUS",
                "consolidado com mais de um grupo não determina em qual criar a linha do item novo",
                {
                    "label": amendment.label,
                    "code": amendment_line.code,
                    "groups": sorted(group_labels),
                },
            )
        group_label = next(iter(group_labels))
        lines.append(
            ContractLine(
                group_label=group_label,
                item_number=_next_item_number(lines, group_label),
                code=amendment_line.code,
                description=amendment_line.description,
                unit=amendment_line.unit,
                unit_price=amendment_line.unit_price,
                contract_quantity=Decimal("0.00"),
                periods=[],
                accumulated_quantity=Decimal("0.00"),
                accumulated_amount=Decimal("0.00"),
            )
        )
        existing_codes.add(amendment_line.code)
    return ContractWorkbook(
        schema_version=CONTRACT_SCHEMA_VERSION,
        id=workbook.id,
        source_label=workbook.source_label,
        source_sha256=workbook.source_sha256,
        contract_label=workbook.contract_label,
        period_numbers=list(workbook.period_numbers),
        lines=lines,
        amendments=[*workbook.amendments, amendment],
        adjustments=list(workbook.adjustments),
    )


def build_next_round_contract(
    previous: ContractWorkbook,
    *,
    measured: Mapping[str, Decimal],
    period_number: int,
) -> ContractWorkbook:
    """Consolidado da rodada `n+1`: nasce da rodada anterior mais o período aprovado nela.

    Exerce a decisão 8 do ADR-0048 (da segunda medição em diante o consolidado soma os
    períodos já lançados) e a decisão 4 do ADR-0056: **cita a rodada anterior, não o
    orçamento**. Reajustes e RE-RA já estão no consolidado anterior e são preservados — não
    reaplicados a partir do orçamento, o que exigiria reaplicar toda a história declarada e
    concordar consigo mesma para sempre.

    `measured` é a quantidade medida por código no período aprovado; o preço lançado é o
    vigente na rodada anterior (`current_unit_price`), e ele só vira `unit_price` do período
    quando difere do contratado — isto é, depois de um reajuste. Vigente e saldo continuam
    derivados: a linha nova não grava `amended_quantity` nem `balance_quantity`.
    """
    if period_number != previous.next_period_number:
        raise ValuationValidationError(
            "NEXT_ROUND_PERIOD_NOT_SEQUENTIAL",
            "a medição seguinte precisa ser o período imediatamente após o último lançado",
            {"expected": previous.next_period_number, "declared": period_number},
        )
    lines: list[ContractLine] = []
    for line in previous.lines:
        price = previous.current_unit_price(line)
        quantity = measured.get(line.code, Decimal("0.00"))
        amount = money_trunc(quantity * price)
        period = PeriodProgress(
            period_number=period_number,
            quantity=quantity,
            amount=amount,
            # Só quando o preço lançado difere do contratado (reajuste): ausente significa
            # "medido pelo contratado", que é a verdade sobre todo período não reajustado.
            unit_price=price if price != line.unit_price else None,
        )
        new_periods = [*line.periods, period]
        # Reconstrói a linha (não `model_copy`) para reexecutar os validadores de período e
        # acumulado sobre o período recém-lançado.
        lines.append(
            ContractLine(
                group_label=line.group_label,
                item_number=line.item_number,
                code=line.code,
                description=line.description,
                unit=line.unit,
                unit_price=line.unit_price,
                contract_quantity=line.contract_quantity,
                periods=new_periods,
                accumulated_quantity=sum((p.quantity for p in new_periods), Decimal("0.00")),
                accumulated_amount=sum((p.amount for p in new_periods), Decimal("0.00")),
            )
        )
    return ContractWorkbook(
        schema_version=CONTRACT_SCHEMA_VERSION,
        id=previous.id,
        source_label=previous.source_label,
        source_sha256=previous.source_sha256,
        contract_label=previous.contract_label,
        period_numbers=[*previous.period_numbers, period_number],
        lines=lines,
        amendments=list(previous.amendments),
        adjustments=list(previous.adjustments),
    )
