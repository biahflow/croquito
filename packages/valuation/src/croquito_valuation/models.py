"""Contratos canônicos da medição de obra pública.

O JSON destes modelos é a fonte de verdade da medição; a planilha é um render auditado
dele. Todo valor que chega à planilha é `Decimal`: dinheiro trunca em duas casas
(`money_trunc`) e quantidade arredonda (`quantity_round`), e os validadores recomputam
cada total em vez de confiar no que foi informado.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal
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

VALUATION_SCHEMA_VERSION: Final = "3.0.0"
ITEM_NUMBER_PATTERN: Final = r"^\d{1,3}(\.\d{1,3}){0,3}$"
WORKSITE_KEY_PATTERN: Final = r"^[a-z0-9][a-z0-9-]{2,63}$"
REFERENCE_MONTH_PATTERN: Final = r"^\d{4}-\d{2}$"
SHA256_PATTERN: Final = r"^[a-f0-9]{64}$"
TAKEOFF_ITEM_ID_PATTERN: Final = r"^ti_[a-f0-9]{16}$"
"""Identidade do item de legenda. Vive aqui, e não em `takeoff`, porque a memória de
cálculo passa a apontar para o elemento e `takeoff` importa deste módulo, não o contrário."""
NON_SCO_CODE_PATTERN: Final = r"^[A-Z0-9][A-Z0-9./()-]{1,29}$"
"""Superset ESTRUTURAL do código de origem EMOP/composição: maiúsculas e dígitos com
pontuação limitada (`./()-`), sem espaço, 2 a 30 caracteres. Só garante estrutura — o
padrão REAL de um código EMOP é dado do layout do importador
(`EmopCatalogLayout.code_pattern`, `croquito_valuation.emop`) e revalida cada linha na
fronteira da leitura; mesmo desenho de `WorkbookTemplate.extra_code_patterns` para o
código contratual nu (`sco.py`, `CONTRACT_CODE_PATTERN`)."""

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


class PriceOrigin(StrEnum):
    """Fonte de preço de um catálogo: onde a cotação nasceu.

    Regra da orçamentista (M8): em obra LICITADA (`Valuation`/`WorksiteBulletin`), o
    contrato manda e preço nunca vem de outra fonte (`BULLETIN_PRICE_ORIGIN_FORBIDDEN` em
    `calc.py`/`workbook_writer.py`). A cadeia SCO → EMOP → SINAPI → SICRO → composição só
    vale PRÉ-licitação (orçamento-base, fase futura); um catálogo carrega só UMA origem
    (`CATALOG_ORIGIN_MIXED`) — mistura de fontes acontece na cascata, nunca dentro dele.

    `SINAPI` e `SICRO` (ADR-0039) são as duas tabelas de referência nacionais, cada uma
    com importador próprio (F-026); caem no mesmo superset estrutural não-SCO que a EMOP
    e a composição (`NON_SCO_CODE_PATTERN`) — o padrão real do código de cada fonte é
    dado do layout do importador dela, não deste enum.
    """

    SCO = "sco"
    EMOP = "emop"
    COMPOSITION = "composition"
    SINAPI = "sinapi"
    SICRO = "sicro"


class PriceCatalogEntry(ValuationContractModel):
    """Item de preço do catálogo público, já normalizado.

    `code` não tem mais o formato fixado no `Field`: a forma exigida depende de `origin`
    (`validate_code_for_origin`), porque só a origem `sco` tem o formato fechado do
    catálogo público. O default de `origin` (`sco`) preserva byte a byte a validação de
    todo artefato M1-M7 relido sem o campo novo.
    """

    code: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    unit_price: ExactDecimal = Field(ge=0)
    family_code: str = Field(min_length=1, max_length=20)
    family_name: str = Field(min_length=1, max_length=200)
    subgroup_code: str = Field(min_length=1, max_length=20)
    subgroup_name: str = Field(min_length=1, max_length=200)
    origin: PriceOrigin = PriceOrigin.SCO

    @model_validator(mode="after")
    def validate_code_for_origin(self) -> PriceCatalogEntry:
        pattern = SCO_CODE_PATTERN if self.origin == PriceOrigin.SCO else NON_SCO_CODE_PATTERN
        if re.fullmatch(pattern, self.code) is None:
            raise ValuationValidationError(
                "CATALOG_CODE_INVALID_FOR_ORIGIN",
                "código do catálogo não tem o formato esperado para a origem declarada",
                {"code": self.code, "origin": self.origin.value},
            )
        return self


class PriceCatalog(ValuationContractModel):
    """Catálogo de preços importado de uma planilha de referência ou tabela externa."""

    id: UUID = Field(default_factory=new_uuid7)
    source_label: str = Field(min_length=1, max_length=200)
    reference_month: str = Field(pattern=REFERENCE_MONTH_PATTERN)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    entries: list[PriceCatalogEntry] = Field(min_length=1)
    origin: PriceOrigin = PriceOrigin.SCO

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

    @model_validator(mode="after")
    def validate_origin_consistency(self) -> PriceCatalog:
        mismatched = sorted({entry.code for entry in self.entries if entry.origin != self.origin})
        if mismatched:
            raise ValuationValidationError(
                "CATALOG_ORIGIN_MIXED",
                "catálogo mistura entradas de mais de uma origem de preço; um catálogo é "
                "sempre uma fonte só — mistura de fontes acontece na cascata (fase futura)",
                {"origin": self.origin.value, "codes": mismatched},
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
    DECLARED_PRODUCT = "declared_product"
    """Produto dos operandos que a orçamentista declarou, sem forma fixa.

    A memória real não tem um repertório fechado de fórmulas: o orçamento do Campo do Toca
    traz 45 formas distintas e 43 termos de operando, 21 deles usados uma única vez
    (`GOLAS x QTD/GOLA`, `REFLETORES x M/REFLETOR`, `COMP x ALT x TAXA x COEF EMOP`). Nomear
    cada uma seria perseguir um alvo que a próxima obra move; esta receita nomeia o que
    todas têm em comum e que `expected_subtotal` já recomputa — o produto. O sentido de cada
    fator continua onde sempre esteve: no `name` do operando, que é dado, não identificador.
    """


class ContributionBasis(StrEnum):
    """De onde vem a parcela que um bloco acrescenta à quantidade do serviço.

    É o eixo que o [ADR-0053] acrescentou: um elemento da prancha alimenta vários serviços,
    e cada bloco declara COMO. A lista é fechada porque descreve a relação, não a fórmula.
    """

    FULL = "full"
    """A parcela é a quantidade confirmada do elemento, inteira."""

    DERIVED = "derived"
    """Sai da geometria do elemento por uma fórmula declarada (perímetro x altura)."""

    PARTIAL = "partial"
    """Recorte medido à parte, que a aritmética do elemento não produz.

    O piso de 418,12 m² recebe limpeza em 170 m²: não há conta que tire um do outro. O
    número é declarado pela orçamentista e conferido só contra o teto do elemento — o que
    depende do item e por isso é validação do builder, não do modelo.
    """

    DEPENDENT = "dependent"
    """Vem da quantidade de OUTRO serviço, não da prancha (transporte, carga, bota-fora)."""

    STANDALONE = "standalone"
    """Não tem origem geométrica: canteiro e administração (placa, container, vigia)."""


class CalcOperand(ValuationContractModel):
    """Parcela impressa da memória de cálculo.

    `name` é dado, não identificador: chega em português na planilha ("PERÍMETRO").
    """

    name: str = Field(min_length=1, max_length=60)
    value: ExactDecimal
    unit: str | None = Field(default=None, min_length=1, max_length=20)


class CalcBlock(ValuationContractModel):
    """Bloco de cálculo de um item: operandos multiplicados menos deduções.

    O bloco é a parcela que UM elemento da prancha acrescenta à quantidade de UM serviço —
    é a célula da matriz que o [ADR-0053] descreve. `label` continua sendo o texto impresso
    na memória (e relido pelo auditor de round-trip); `source_item_id` é o mesmo vínculo,
    agora conferível por máquina.
    """

    label: str = Field(min_length=1, max_length=120)
    source_item_id: str | None = Field(default=None, pattern=TAKEOFF_ITEM_ID_PATTERN)
    basis: ContributionBasis | None = None
    """`None` significa "não declarado", nunca um valor presumido.

    Bloco escrito antes desta versão não afirmou base nenhuma, e um default afirmaria por
    ele: um `PERIMETER_TIMES_HEIGHT` do M4 é `DERIVED`, não `FULL`.
    """

    derived_from_code: str | None = Field(default=None, min_length=1, max_length=30)
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

    @model_validator(mode="after")
    def validate_contribution(self) -> CalcBlock:
        """Coerência entre a base declarada e os vínculos que ela implica.

        Só o que o bloco sabe sozinho. O teto da parcela `PARTIAL` (nunca maior que a
        quantidade do elemento) depende do `TakeoffItem`, que este modelo não alcança: é
        conferência de builder. A nota obrigatória da `PARTIAL` (ADR-0053, decisão 3) mora no
        lado da autoria (`CalcContribution.note`, `CALC_PARTIAL_NOTE_REQUIRED`): o bloco
        materializado é o render literal e não carrega campo de nota — dar um a ele mudaria o
        digest de orçamento assinado, que a decisão 5 do mesmo ADR existe para preservar.
        """
        if self.basis is ContributionBasis.STANDALONE and self.source_item_id is not None:
            raise ValuationValidationError(
                "CALC_CONTRIBUTION_STANDALONE_WITH_ITEM",
                "parcela de canteiro não nasce de elemento da prancha",
                {"label": self.label, "source_item_id": self.source_item_id},
            )
        if self.basis is ContributionBasis.DEPENDENT:
            if self.derived_from_code is None:
                raise ValuationValidationError(
                    "CALC_CONTRIBUTION_DEPENDENT_WITHOUT_CODE",
                    "parcela derivada precisa dizer de qual serviço ela vem",
                    {"label": self.label},
                )
        elif self.derived_from_code is not None:
            raise ValuationValidationError(
                "CALC_CONTRIBUTION_CODE_WITHOUT_DEPENDENCY",
                "só parcela derivada de outro serviço cita um código de origem",
                {
                    "label": self.label,
                    "basis": self.basis.value if self.basis else None,
                    "derived_from_code": self.derived_from_code,
                },
            )
        # As três bases restantes afirmam que a parcela vem de UM elemento da prancha
        # (`FULL`, `DERIVED`) ou é um recorte medido dele (`PARTIAL`); sem `source_item_id`
        # o bloco afirma a origem e não a nomeia. `DEPENDENT` fica de fora porque a origem
        # dela é outro serviço, não um elemento — se também carrega elemento de origem é
        # decisão do builder (T4, ADR-0053), não deste modelo. `basis is None` fica de fora
        # porque é o bloco pré-matriz, que não afirmou nada.
        if (
            self.basis
            in (ContributionBasis.FULL, ContributionBasis.DERIVED, ContributionBasis.PARTIAL)
            and self.source_item_id is None
        ):
            raise ValuationValidationError(
                "CALC_CONTRIBUTION_WITHOUT_SOURCE_ITEM",
                "parcela com origem em elemento precisa apontar para o elemento",
                {"label": self.label, "basis": self.basis.value},
            )
        # `derived_from_code` é texto livre no schema, mas afirma ser um código de catálogo:
        # sem checar a forma, "codigo com espaco" ou um `ti_...` copiado por engano passam
        # como se fossem origem válida. Mesmo superset estrutural de `haulage.validate_codes`
        # — o contrato real traz código fora do SCO (`IE...`), então não pode exigir SCO puro.
        if self.derived_from_code is not None and (
            re.fullmatch(SCO_CODE_PATTERN, self.derived_from_code) is None
            and re.fullmatch(NON_SCO_CODE_PATTERN, self.derived_from_code) is None
        ):
            raise ValuationValidationError(
                "CALC_CONTRIBUTION_CODE_INVALID",
                "código de origem da parcela não tem formato de código de catálogo",
                {"label": self.label, "derived_from_code": self.derived_from_code},
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


# --------------------------------------------------------------------------------------
# Digest de conteúdo governado pela versão que o artefato declara
# --------------------------------------------------------------------------------------

DigestPruning = Mapping[str, Sequence[tuple[tuple[str, ...], frozenset[str]]]]
"""Campos a podar do payload de digest, por versão de schema.

A chave é a `schema_version` **declarada pelo artefato**. O valor é uma sequência de
podas, cada uma com o caminho até os dicionários afetados (atravessando listas) e as
chaves que aquela versão não conhecia. São várias porque uma versão nova costuma tocar
mais de um nível — um campo no bloco de cálculo e outro no operando dele, por exemplo.
"""


def _prune_versioned_fields(node: object, path: tuple[str, ...], keys: frozenset[str]) -> None:
    """Remove `keys` dos dicionários alcançados por `path`, atravessando listas."""
    if isinstance(node, list):
        for element in node:
            _prune_versioned_fields(element, path, keys)
        return
    if not isinstance(node, dict):
        return
    if not path:
        for key in keys:
            node.pop(key, None)
        return
    head = path[0]
    if head in node:
        _prune_versioned_fields(node[head], path[1:], keys)


def versioned_content_digest(
    payload: dict[str, Any], schema_version: str, pruning: DigestPruning
) -> str:
    """SHA-256 do payload canônico, podando o que a versão declarada não conhecia.

    Existe porque o digest é o que amarra a aprovação nominal ao conteúdo aprovado: um
    campo novo em qualquer modelo aninhado entraria no payload como `null` e mudaria o
    digest de artefatos **já assinados**, que passariam a falhar em
    `APPROVAL_CONTENT_MISMATCH`. Sob o ADR-0048 o orçamento assinado é o consolidado
    contratual da medição, então isso invalidaria um contrato.

    A poda é declarada por versão, nunca inferida: `exclude_none=True` resolveria o caso
    do campo novo e, de quebra, derrubaria `CalcOperand.unit=None` — mudando o digest de
    tudo que se queria preservar.

    Consome `payload`: a poda é feita no lugar, sobre o dicionário recém-criado por
    `model_dump()`.
    """
    for path, keys in pruning.get(schema_version, ()):
        _prune_versioned_fields(payload, path, keys)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


VALUATION_DIGEST_PRUNING: Final[DigestPruning] = {
    "2.0.0": [
        (
            ("calc_sheets", "blocks"),
            frozenset({"source_item_id", "basis", "derived_from_code"}),
        ),
    ],
}
"""Medição escrita antes da matriz não conhecia os vínculos do bloco de cálculo.

Sem esta entrada, o `null` dos três campos entraria no payload e mudaria o digest de toda
medição já aprovada, que passaria a falhar em `APPROVAL_CONTENT_MISMATCH`."""


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

    schema_version: Literal["2.0.0", "3.0.0"] = VALUATION_SCHEMA_VERSION
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
        return versioned_content_digest(
            self.model_dump(mode="json", exclude={"approval"}),
            self.schema_version,
            VALUATION_DIGEST_PRUNING,
        )

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
                # O preço VIGENTE, não o contratado original: é o número que o contrato paga
                # hoje (ADR-0055, decisão 7). Sem reajuste declarado os dois são o mesmo, e o
                # comportamento é idêntico ao de antes da F-039.
                if line.unit_price != contract.current_unit_price(contract_line):
                    errors.append(f"LINE_PRICE_NOT_IN_CONTRACT:{line.code}")
                if line.unit != contract_line.unit:
                    errors.append(f"LINE_UNIT_NOT_IN_CONTRACT:{line.code}")
                measured[line.code] = measured.get(line.code, Decimal("0.00")) + line.quantity

        for code, quantity in measured.items():
            # O saldo VIGENTE, derivado (ADR-0056, decisão 3): contratado + RE-RA - acumulado.
            # Sem RE-RA declarada é idêntico ao contratado menos o acumulado, bit a bit.
            if quantity > contract.current_balance_quantity(contract_lines[code][0]):
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
