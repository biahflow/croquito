"""Layout da planilha descrito como dado, não como código.

O formato do MAPÃO varia por cliente e por ano. Nenhuma posição de célula é constante
no módulo: tudo que o leitor e o escritor precisam saber está neste modelo, e o template
real de cada cliente vive fora do Git. `default_template()` espelha o layout mapeado e é
o que a demonstração sintética usa.
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import Field, model_validator

from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    MAX_DESCRIPTION_LENGTH,
    NON_SCO_CODE_PATTERN,
    ExactDecimal,
    ValuationContractModel,
)
from croquito_valuation.sco import SCO_CODE_PATTERN

COLUMN_LETTER_PATTERN: Final = r"^[A-Z]{1,2}$"
WORKSITE_PLACEHOLDER: Final = "{worksite}"
PERIOD_PLACEHOLDER: Final = "{n}"
MAX_SHEET_NAME_LENGTH: Final = 31
_FORBIDDEN_SHEET_CHARS: Final = set(r"[]:*?/\'")
_SHEET_LABEL_PARTICLES: Final = frozenset({"de", "da", "do", "das", "dos"})
"""Partículas de ligação que o rótulo da aba perde primeiro (`_worksite_sheet_label`)."""
_SHEET_LABEL_STEM: Final = 4
"""Letras que sobram da palavra do meio abreviada, antes do ponto ("SINTETICA" → "SINT.")."""


class SheetColumn(ValuationContractModel):
    """Uma coluna da planilha: onde fica, como se chama e que largura ocupa."""

    letter: str = Field(pattern=COLUMN_LETTER_PATTERN)
    label: str = Field(min_length=1, max_length=40)
    width: int = Field(default=14, ge=4, le=80)


class SheetColumns(ValuationContractModel):
    """As sete colunas do boletim e da memória, na ordem impressa."""

    item: SheetColumn
    code: SheetColumn
    description: SheetColumn
    unit: SheetColumn
    unit_price: SheetColumn
    quantity: SheetColumn
    total: SheetColumn

    @property
    def ordered(self) -> tuple[SheetColumn, ...]:
        """Colunas na ordem impressa."""
        return (
            self.item,
            self.code,
            self.description,
            self.unit,
            self.unit_price,
            self.quantity,
            self.total,
        )

    @model_validator(mode="after")
    def validate_distinct_letters(self) -> SheetColumns:
        letters = [column.letter for column in self.ordered]
        if len(letters) != len(set(letters)):
            raise ValuationValidationError(
                "TEMPLATE_DUPLICATE_COLUMN",
                "duas colunas do template apontam para a mesma letra",
                {"letters": letters},
            )
        return self


class CatalogLayout(ValuationContractModel):
    """Onde ficam os preços na planilha de catálogo (a aba pode estar oculta).

    A hierarquia família/subgrupo tem dois modos, e o template escolhe qual vale:

    - **na coluna de código** (padrão): os cabeçalhos aparecem como `AD` e `AD0405` na
      mesma coluna dos itens, sem `family_column` nem `subgroup_intermediate_column`;
    - **em colunas próprias**: a família fica em `family_column`, o nível intermediário
      em `subgroup_intermediate_column` e o cabeçalho de subgrupo na própria coluna de
      código. É o layout do catálogo publicado, com nome junto do código em cada nível.

    `note_prefixes` declara o texto editorial que o catálogo publicado intercala entre os
    cabeçalhos ("Nota: As marcas indicadas servem apenas para definir o modelo..."). Linha
    de nota é pulada porque o template diz que ela é nota — texto não declarado continua
    sendo linha ilegível, e nenhuma linha com código SCO é pulada por este caminho.

    `unpriced_markers` declara o texto que o catálogo escreve no lugar do preço quando não
    há preço publicado para o item ("sem cotação"). O item fica **fora** do catálogo, e não
    entra com preço zero: preço zero é preço, ausência de preço não é. Medir esse código
    falha depois com `CATALOG_CODE_UNKNOWN`, que é a recusa correta.
    """

    sheet_name: str = Field(min_length=1, max_length=MAX_SHEET_NAME_LENGTH)
    first_row: int = Field(ge=1)
    code_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    description_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    unit_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    price_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    family_column: str | None = Field(default=None, pattern=COLUMN_LETTER_PATTERN)
    subgroup_intermediate_column: str | None = Field(default=None, pattern=COLUMN_LETTER_PATTERN)
    note_prefixes: list[str] = Field(default_factory=list, max_length=10)
    unpriced_markers: list[str] = Field(default_factory=list, max_length=10)

    def is_unpriced(self, raw_price: object) -> bool:
        """`True` quando a célula de preço traz um marcador declarado de item sem cotação."""
        if not self.unpriced_markers or not isinstance(raw_price, str):
            return False
        text = " ".join(raw_price.split()).casefold()
        return any(text == marker.strip().casefold() for marker in self.unpriced_markers)

    @property
    def hierarchy_columns(self) -> tuple[str, str] | None:
        """Par família/intermediário quando a hierarquia vem em colunas próprias."""
        if self.family_column is None or self.subgroup_intermediate_column is None:
            return None
        return (self.family_column, self.subgroup_intermediate_column)

    @property
    def declared_columns(self) -> tuple[str, ...]:
        """Letras de todas as colunas declaradas, na ordem em que a planilha as mostra."""
        declared = [self.family_column, self.subgroup_intermediate_column]
        return (
            *(letter for letter in declared if letter is not None),
            self.code_column,
            self.description_column,
            self.unit_column,
            self.price_column,
        )

    @model_validator(mode="after")
    def validate_declared_texts(self) -> CatalogLayout:
        invalid = [
            text for text in (*self.note_prefixes, *self.unpriced_markers) if len(text.strip()) < 2
        ]
        if invalid:
            raise ValuationValidationError(
                "TEMPLATE_CATALOG_TEXT_INVALID",
                "texto declarado do catálogo é curto demais para distinguir uma linha",
                {"sheet": self.sheet_name, "texts": invalid},
            )
        return self

    @model_validator(mode="after")
    def validate_hierarchy_columns(self) -> CatalogLayout:
        if (self.family_column is None) != (self.subgroup_intermediate_column is None):
            raise ValuationValidationError(
                "TEMPLATE_CATALOG_HIERARCHY_INCOMPLETE",
                "hierarquia por colunas exige coluna de família e de subgrupo intermediário juntas",
                {
                    "sheet": self.sheet_name,
                    "family_column": self.family_column,
                    "subgroup_intermediate_column": self.subgroup_intermediate_column,
                },
            )
        return self

    @model_validator(mode="after")
    def validate_distinct_columns(self) -> CatalogLayout:
        letters = list(self.declared_columns)
        if len(letters) != len(set(letters)):
            raise ValuationValidationError(
                "TEMPLATE_DUPLICATE_COLUMN",
                "duas colunas do template apontam para a mesma letra",
                {"sheet": self.sheet_name, "letters": letters},
            )
        return self


class BulletinLayout(ValuationContractModel):
    """Layout da aba BM: bloco de cabeçalho, linha de títulos e colunas."""

    title: str = Field(min_length=1, max_length=120)
    header_row: int = Field(ge=2)
    columns: SheetColumns
    intervention_label: str = Field(default="INTERVENÇÃO", min_length=1, max_length=40)
    address_label: str = Field(default="ENDEREÇO", min_length=1, max_length=40)
    contract_label: str = Field(default="CONTRATO", min_length=1, max_length=40)
    period_label: str = Field(default="MEDIÇÃO", min_length=1, max_length=40)
    total_label: str = Field(default="TOTAL DA OBRA", min_length=1, max_length=60)
    label_column: str = Field(default="A", pattern=COLUMN_LETTER_PATTERN)
    value_column: str = Field(default="C", pattern=COLUMN_LETTER_PATTERN)
    money_number_format: str = Field(default="#,##0.00", min_length=1, max_length=40)
    quantity_number_format: str = Field(default="#,##0.00", min_length=1, max_length=40)


class MemoryLayout(ValuationContractModel):
    """Layout da aba MEMÓRIA: resumo do item e blocos de cálculo abaixo dele."""

    title: str = Field(min_length=1, max_length=120)
    header_row: int = Field(ge=2)
    columns: SheetColumns
    operand_columns: list[str] = Field(min_length=1)
    block_label_column: str = Field(default="B", pattern=COLUMN_LETTER_PATTERN)
    deduction_label: str = Field(default="DESC. VÃOS", min_length=1, max_length=40)
    subtotal_label: str = Field(default="SUBTOTAL", min_length=1, max_length=40)
    total_label: str = Field(default="TOTAL", min_length=1, max_length=40)
    intervention_label: str = Field(default="INTERVENÇÃO", min_length=1, max_length=40)
    label_column: str = Field(default="A", pattern=COLUMN_LETTER_PATTERN)
    value_column: str = Field(default="C", pattern=COLUMN_LETTER_PATTERN)
    money_number_format: str = Field(default="#,##0.00", min_length=1, max_length=40)
    quantity_number_format: str = Field(default="#,##0.00", min_length=1, max_length=40)

    @property
    def subtotal_column(self) -> str:
        """Os subtotais da memória são quantidades e ficam na coluna de quantidade."""
        return self.columns.quantity.letter

    @model_validator(mode="after")
    def validate_operand_columns(self) -> MemoryLayout:
        pattern = re.compile(r"[A-Z]{1,2}")
        invalid = [letter for letter in self.operand_columns if not pattern.fullmatch(letter)]
        if invalid:
            raise ValuationValidationError(
                "TEMPLATE_INVALID_COLUMN",
                "coluna de operando fora do formato de letra de coluna",
                {"letters": invalid},
            )
        if len(self.operand_columns) != len(set(self.operand_columns)):
            raise ValuationValidationError(
                "TEMPLATE_DUPLICATE_COLUMN",
                "coluna de operando repetida no template",
                {"letters": list(self.operand_columns)},
            )
        if self.subtotal_column in self.operand_columns:
            raise ValuationValidationError(
                "TEMPLATE_COLUMN_CONFLICT",
                "coluna de operando colide com a coluna de subtotal da memória",
                {"subtotal_column": self.subtotal_column},
            )
        return self


class GeneralLayout(ValuationContractModel):
    """Layout da PLANILHA GERAL: colunas fixas e pares por medição em posição derivada.

    Cada medição ocupa duas colunas (QUANTIDADE e VALOR) a partir de
    `first_period_column`, na ordem dos períodos; ACUMULADO e SALDO vêm depois do último
    par. Nenhuma posição de par é constante: o leitor a deriva do cabeçalho.

    A linha de dados é declarada à parte da linha de cabeçalho porque no arquivo do
    cliente há uma linha de sub-rótulos (QUANTIDADE|VALOR) entre as duas.

    Os rótulos das colunas fixas existem para o escritor: o leitor descobre o layout
    pelas posições declaradas e não confere o texto do cabeçalho fixo.

    Duas coisas do arquivo real são declaradas aqui em vez de presumidas pelo código:

    - `amended_quantity_column` é opcional, porque há MAPÃO sem coluna de quantidade
      vigente na GERAL; sem ela o vigente é derivado do contratual mais as RE-RA;
    - `quantity_decimal_scale` é a escala máxima aceita nas colunas de QUANTIDADE
      (dinheiro é sempre duas casas), porque o arquivo real traz quantidade com quatro.
    """

    sheet_name: str = Field(min_length=1, max_length=MAX_SHEET_NAME_LENGTH)
    title: str = Field(min_length=1, max_length=120)
    header_row: int = Field(ge=2)
    pair_sublabel_row: int | None = Field(default=None, ge=2)
    data_first_row: int = Field(ge=2)
    group_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    item_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    code_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    description_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    unit_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    contract_quantity_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    unit_price_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    amended_quantity_column: str | None = Field(default=None, pattern=COLUMN_LETTER_PATTERN)
    first_period_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    quantity_decimal_scale: int = Field(default=2, ge=2, le=6)
    group_label: str = Field(default="GRUPO", min_length=1, max_length=40)
    item_label: str = Field(default="ITEM", min_length=1, max_length=40)
    code_label: str = Field(default="CÓDIGO", min_length=1, max_length=40)
    description_label: str = Field(default="ESPECIFICAÇÃO", min_length=1, max_length=40)
    unit_label: str = Field(default="UN", min_length=1, max_length=40)
    contract_quantity_label: str = Field(default="QUANT CONTRAT", min_length=1, max_length=40)
    unit_price_label: str = Field(default="CUSTO UNIT", min_length=1, max_length=40)
    amended_quantity_label: str = Field(default="QUANT VIGENTE", min_length=1, max_length=40)
    period_label_pattern: str = Field(default="{n}ª MEDIÇÃO", min_length=1, max_length=40)
    quantity_pair_label: str = Field(default="QUANTIDADE", min_length=1, max_length=40)
    amount_pair_label: str = Field(default="VALOR", min_length=1, max_length=40)
    accumulated_label: str = Field(default="ACUMULADO", min_length=1, max_length=40)
    balance_label: str = Field(default="SALDO", min_length=1, max_length=40)
    total_label: str = Field(default="TOTAL GERAL", min_length=1, max_length=60)
    money_number_format: str = Field(default="#,##0.00", min_length=1, max_length=40)
    quantity_number_format: str = Field(default="#,##0.00", min_length=1, max_length=40)

    @property
    def fixed_columns(self) -> tuple[str, ...]:
        """Letras das colunas declaradas que não dependem do número de medições."""
        declared = (
            self.group_column,
            self.item_column,
            self.code_column,
            self.description_column,
            self.unit_column,
            self.contract_quantity_column,
            self.unit_price_column,
            self.amended_quantity_column,
            self.first_period_column,
        )
        return tuple(letter for letter in declared if letter is not None)

    def period_label(self, n: int) -> str:
        """Rótulo do cabeçalho da n-ésima medição, como o escritor o escreve."""
        return self.period_label_pattern.replace(PERIOD_PLACEHOLDER, str(n))

    def parse_period_label(self, text: str) -> int | None:
        """Número da medição escrito no cabeçalho, ou `None` quando o rótulo é outro.

        O arquivo do cliente escreve o rótulo com sufixo livre (`11ª MEDIÇÃO -
        COMPLEMENTAR`, `13ª MEDIÇÃO (COMPLEMENTAR`), então o leitor casa o padrão
        declarado e aceita o que vier depois dele. O número lido é o que vale: a posição
        do par no cabeçalho não determina a numeração da medição.
        """
        prefix, _, suffix = self.period_label_pattern.partition(PERIOD_PLACEHOLDER)
        pattern = re.compile(rf"^{re.escape(prefix)}(\d+){re.escape(suffix)}.*$")
        match = pattern.fullmatch(text)
        if match is None:
            return None
        return int(match.group(1))

    @model_validator(mode="after")
    def validate_row_order(self) -> GeneralLayout:
        above = [("header_row", self.header_row)]
        if self.pair_sublabel_row is not None:
            above.append(("pair_sublabel_row", self.pair_sublabel_row))
        for field_name, row in above:
            if self.data_first_row <= row:
                raise ValuationValidationError(
                    "TEMPLATE_ROW_ORDER_INVALID",
                    "primeira linha de dados precisa vir depois do cabeçalho da planilha",
                    {
                        "sheet": self.sheet_name,
                        "field": field_name,
                        "row": row,
                        "data_first_row": self.data_first_row,
                    },
                )
        return self

    @model_validator(mode="after")
    def validate_general(self) -> GeneralLayout:
        letters = list(self.fixed_columns)
        if len(letters) != len(set(letters)):
            raise ValuationValidationError(
                "TEMPLATE_DUPLICATE_COLUMN",
                "duas colunas da planilha geral apontam para a mesma letra",
                {"letters": letters},
            )
        if PERIOD_PLACEHOLDER not in self.period_label_pattern:
            raise ValuationValidationError(
                "TEMPLATE_PERIOD_PATTERN_INVALID",
                "rótulo de medição precisa conter {n}",
                {"pattern": self.period_label_pattern},
            )
        _validate_sheet_name(self.sheet_name)
        return self


class AmendmentColumns(ValuationContractModel):
    """Bloco de uma RE-RA na aba da prefeitura: reduzida, acrescida e item novo."""

    label: str = Field(min_length=1, max_length=60)
    reduced_column: str | None = Field(default=None, pattern=COLUMN_LETTER_PATTERN)
    added_column: str | None = Field(default=None, pattern=COLUMN_LETTER_PATTERN)
    new_item_column: str | None = Field(default=None, pattern=COLUMN_LETTER_PATTERN)

    @model_validator(mode="after")
    def validate_columns(self) -> AmendmentColumns:
        if not any((self.reduced_column, self.added_column, self.new_item_column)):
            raise ValuationValidationError(
                "TEMPLATE_AMENDMENT_BLOCK_EMPTY",
                "bloco de RE-RA precisa de ao menos uma coluna declarada",
                {"label": self.label},
            )
        return self


class AmendmentLayout(ValuationContractModel):
    """Layout da aba de RE-RA da prefeitura, lida para reconciliar o vigente.

    `section_rows_carry_group_subtotal` declara um layout observado no arquivo real: a
    linha de seção que abre um grupo (nome do grupo na coluna de código, como a GERAL)
    carrega o subtotal do grupo na própria `amended_quantity_column` — não é o vigente de
    um código, é a soma da coluna para todo o grupo. Com a flag ligada, essa coluna sai do
    cheque de "linha sem nenhum valor declarado" que decide se a linha é seção; os blocos
    de RE-RA (reduzida/acrescida/item novo) continuam tendo de estar vazios, porque esses
    sim seriam um delta real sobre um código. O valor ignorado é registrado nas notas da
    importação (`ContractImportNotes.amendment_section_rows`), nunca descartado em
    silêncio. Risco declarado: a flag confia que **nenhuma** linha real de item nesta aba
    tem código ilegível por erro de digitação acompanhado de um vigente genuíno — se isso
    acontecer, a linha some da leitura sem recusa. É por isso que a flag é opt-in e
    default `False`: só o cliente cujo layout foi inspecionado e confirma essa forma a
    liga.
    """

    sheet_name: str = Field(min_length=1, max_length=MAX_SHEET_NAME_LENGTH)
    header_row: int = Field(ge=2)
    data_first_row: int = Field(ge=2)
    code_column: str = Field(pattern=COLUMN_LETTER_PATTERN)
    amended_quantity_column: str | None = Field(default=None, pattern=COLUMN_LETTER_PATTERN)
    code_label: str = Field(default="CÓDIGO", min_length=1, max_length=40)
    amended_quantity_label: str = Field(default="QUANT VIGENTE", min_length=1, max_length=40)
    blocks: list[AmendmentColumns] = Field(min_length=1)
    section_rows_carry_group_subtotal: bool = False

    @model_validator(mode="after")
    def validate_row_order(self) -> AmendmentLayout:
        if self.data_first_row <= self.header_row:
            raise ValuationValidationError(
                "TEMPLATE_ROW_ORDER_INVALID",
                "primeira linha de dados precisa vir depois do cabeçalho da planilha",
                {
                    "sheet": self.sheet_name,
                    "field": "header_row",
                    "row": self.header_row,
                    "data_first_row": self.data_first_row,
                },
            )
        return self

    @model_validator(mode="after")
    def validate_sheet_name(self) -> AmendmentLayout:
        _validate_sheet_name(self.sheet_name)
        return self


class EstimateColumns(ValuationContractModel):
    """As sete colunas do boletim mais FONTE e VALOR UNIT. C/ BDI (ADR-0038, decisão 5).

    Aditivas e opcionais ao layout do boletim: o boletim da medição nunca lê nem escreve
    esta seção, e nada da forma existente do template muda por causa dela.
    """

    item: SheetColumn
    code: SheetColumn
    source: SheetColumn
    description: SheetColumn
    unit: SheetColumn
    unit_price: SheetColumn
    unit_price_with_bdi: SheetColumn
    quantity: SheetColumn
    total: SheetColumn

    @property
    def ordered(self) -> tuple[SheetColumn, ...]:
        """Colunas na ordem impressa."""
        return (
            self.item,
            self.code,
            self.source,
            self.description,
            self.unit,
            self.unit_price,
            self.unit_price_with_bdi,
            self.quantity,
            self.total,
        )

    @model_validator(mode="after")
    def validate_distinct_letters(self) -> EstimateColumns:
        letters = [column.letter for column in self.ordered]
        if len(letters) != len(set(letters)):
            raise ValuationValidationError(
                "TEMPLATE_DUPLICATE_COLUMN",
                "duas colunas do template apontam para a mesma letra",
                {"letters": letters},
            )
        return self


class EstimateLayout(ValuationContractModel):
    """Layout da planilha do orçamento-base (ADR-0038): seção própria, nunca usada pelo
    escritor da medição.

    `header_row` precisa deixar espaço para o bloco de identificação (INTERVENÇÃO,
    ENDEREÇO quando declarado, BDI) — o mesmo desenho de `BulletinLayout`, conferido pelo
    escritor do orçamento na hora de planejar a aba, não aqui.
    """

    sheet_name: str = Field(default="ORÇAMENTO", min_length=1, max_length=MAX_SHEET_NAME_LENGTH)
    title: str = Field(default="ORÇAMENTO-BASE", min_length=1, max_length=120)
    header_row: int = Field(default=6, ge=2)
    columns: EstimateColumns
    intervention_label: str = Field(default="INTERVENÇÃO", min_length=1, max_length=40)
    address_label: str = Field(default="ENDEREÇO", min_length=1, max_length=40)
    bdi_label: str = Field(default="BDI", min_length=1, max_length=40)
    total_without_bdi_label: str = Field(default="TOTAL SEM BDI", min_length=1, max_length=60)
    total_label: str = Field(default="TOTAL GERAL", min_length=1, max_length=60)
    unpriced_section_label: str = Field(
        default="ITENS SEM PREÇO NA CASCATA", min_length=1, max_length=60
    )
    label_column: str = Field(default="A", pattern=COLUMN_LETTER_PATTERN)
    value_column: str = Field(default="C", pattern=COLUMN_LETTER_PATTERN)
    money_number_format: str = Field(default="#,##0.00", min_length=1, max_length=40)
    quantity_number_format: str = Field(default="#,##0.00", min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_sheet_name(self) -> EstimateLayout:
        _validate_sheet_name(self.sheet_name)
        return self


class EstimateTemplateRow(ValuationContractModel):
    """Uma linha do gabarito de ordem fixa da prefeitura, exatamente como ela a publica.

    `group` e `item` são TEXTO e são preservados como escritos — zero à esquerda e a forma
    `GG.N` fazem parte do documento. Nem o modelo nem o escritor recomputam ou renumeram
    coisa alguma: a lacuna de grupo do documento real (5, 15 e 22 no gabarito do cliente)
    existe porque o gabarito simplesmente não declara linha daqueles grupos, e não há
    campo para "grupo ausente" — não há nada a declarar.

    `unit_price` é o preço que o gabarito imprime quando o orçamento não tem a linha
    daquele código. Quando tem, quem manda é o preço do orçamento; os dois nunca são
    comparados (a regra vive na docstring do escritor).
    """

    group: str = Field(min_length=1, max_length=20)
    item: str = Field(min_length=1, max_length=20)
    code: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    unit_price: ExactDecimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_code(self) -> EstimateTemplateRow:
        """Mesmo superset estrutural de `ServiceHaulage.validate_codes` (`haulage.py`).

        O gabarito real mistura código SCO e código de outra origem, então exigir SCO puro
        recusaria o documento do cliente; o que não pode passar é texto que não tem forma
        de código de catálogo nenhum.
        """
        if (
            re.fullmatch(SCO_CODE_PATTERN, self.code) is None
            and re.fullmatch(NON_SCO_CODE_PATTERN, self.code) is None
        ):
            raise ValuationValidationError(
                "TEMPLATE_ESTIMATE_GRID_CODE_INVALID",
                "código do gabarito não tem formato de código de catálogo",
                {"item": self.item, "code": self.code},
            )
        return self


class EstimateTemplateColumns(ValuationContractModel):
    """As oito colunas da planilha orçamentária do gabarito, na ordem impressa."""

    group: SheetColumn
    item: SheetColumn
    code: SheetColumn
    description: SheetColumn
    unit: SheetColumn
    quantity: SheetColumn
    unit_price: SheetColumn
    total: SheetColumn

    @property
    def ordered(self) -> tuple[SheetColumn, ...]:
        """Colunas na ordem impressa."""
        return (
            self.group,
            self.item,
            self.code,
            self.description,
            self.unit,
            self.quantity,
            self.unit_price,
            self.total,
        )

    @model_validator(mode="after")
    def validate_distinct_letters(self) -> EstimateTemplateColumns:
        letters = [column.letter for column in self.ordered]
        if len(letters) != len(set(letters)):
            raise ValuationValidationError(
                "TEMPLATE_DUPLICATE_COLUMN",
                "duas colunas do template apontam para a mesma letra",
                {"letters": letters},
            )
        return self


class EstimateTemplateLayout(ValuationContractModel):
    """Gabarito de ordem fixa da prefeitura: a lista ordenada de linhas é o documento.

    Seção ADITIVA do template (F-043): `EstimateLayout` continua servindo a rodada que não
    declara gabarito, e o boletim da medição nunca lê nem escreve esta seção.

    `revision_label` identifica a revisão do gabarito e é IMPRESSA no arquivo. É o controle
    do risco declarado na feature: a prefeitura revisa o gabarito e um arquivo gerado na
    revisão velha continua parecendo certo — só o arquivo dizer qual revisão usou desfaz
    esse silêncio.

    `rows` é a ordem impressa e nada além dela ordena a planilha: o índice código→linha
    exige unicidade, porque um código repetido faria a quantidade cair numa das duas
    linhas à sorte da iteração. Se o gabarito real trouxer duplicata legítima, isso é
    decisão humana, não remendo do escritor.
    """

    sheet_name: str = Field(min_length=1, max_length=MAX_SHEET_NAME_LENGTH)
    title: str = Field(min_length=1, max_length=120)
    revision_label: str = Field(min_length=1, max_length=120)
    memory_sheet_name: str = Field(min_length=1, max_length=MAX_SHEET_NAME_LENGTH)
    header_row: int = Field(ge=2)
    columns: EstimateTemplateColumns
    rows: list[EstimateTemplateRow] = Field(min_length=1)
    intervention_label: str = Field(default="INTERVENÇÃO", min_length=1, max_length=40)
    address_label: str = Field(default="ENDEREÇO", min_length=1, max_length=40)
    bdi_label: str = Field(default="BDI", min_length=1, max_length=40)
    revision_row_label: str = Field(default="REVISÃO DO GABARITO", min_length=1, max_length=40)
    total_without_bdi_label: str = Field(default="TOTAL SEM BDI", min_length=1, max_length=60)
    total_label: str = Field(default="TOTAL GERAL", min_length=1, max_length=60)
    unpriced_section_label: str = Field(
        default="ITENS SEM PREÇO NA CASCATA", min_length=1, max_length=60
    )
    label_column: str = Field(default="A", pattern=COLUMN_LETTER_PATTERN)
    value_column: str = Field(default="C", pattern=COLUMN_LETTER_PATTERN)
    money_number_format: str = Field(default="#,##0.00", min_length=1, max_length=40)
    quantity_number_format: str = Field(default="#,##0.00", min_length=1, max_length=40)

    @property
    def row_index_by_code(self) -> dict[str, int]:
        """Código → posição na ordem do gabarito; unicidade garantida pelo validador."""
        return {row.code: index for index, row in enumerate(self.rows)}

    @model_validator(mode="after")
    def validate_rows(self) -> EstimateTemplateLayout:
        codes = [row.code for row in self.rows]
        duplicated_codes = sorted({code for code in codes if codes.count(code) > 1})
        if duplicated_codes:
            raise ValuationValidationError(
                "TEMPLATE_ESTIMATE_GRID_DUPLICATE_CODE",
                "o gabarito declara o mesmo código em mais de uma linha",
                {"sheet": self.sheet_name, "codes": duplicated_codes},
            )
        items = [row.item for row in self.rows]
        duplicated_items = sorted({item for item in items if items.count(item) > 1})
        if duplicated_items:
            raise ValuationValidationError(
                "TEMPLATE_ESTIMATE_GRID_DUPLICATE_ITEM",
                "o gabarito declara a mesma numeração de item em mais de uma linha",
                {"sheet": self.sheet_name, "items": duplicated_items},
            )
        return self

    @model_validator(mode="after")
    def validate_sheet_names(self) -> EstimateTemplateLayout:
        _validate_sheet_name(self.sheet_name)
        _validate_sheet_name(self.memory_sheet_name)
        if self.sheet_name == self.memory_sheet_name:
            raise ValuationValidationError(
                "TEMPLATE_SHEET_NAME_CONFLICT",
                "gabarito e memória de cálculo do orçamento usam o mesmo nome de aba",
                {"names": [self.sheet_name, self.memory_sheet_name]},
            )
        return self


class WorkbookTemplate(ValuationContractModel):
    """Descrição completa do layout usado para ler o catálogo e escrever a medição.

    `extra_code_patterns` declara os padrões extras de código contratual fora da tabela
    SCO deste cliente. O contrato real mede item com código nu (`IE00040849`: duas letras
    e oito dígitos, sem variante), ausente do catálogo publicado. Cada padrão é uma regex
    que o leitor casa com `fullmatch` (`matches_extra_code`) contra o texto da célula de
    código; o código aceito ainda precisa ter a estrutura de `CONTRACT_CODE_PATTERN` — o
    leitor revalida isso de qualquer forma, então um padrão frouxo demais aqui não basta
    para injetar identidade fora da estrutura.

    `estimate` é a seção opcional do orçamento-base (ADR-0038): aditiva, nunca lida nem
    escrita pelo boletim da medição. Sem ela, o template continua servindo só o boletim,
    exatamente como antes do ADR.

    `estimate_grid` é a seção opcional do GABARITO da prefeitura (F-043), também aditiva:
    quem a declara publica o orçamento percorrendo a ordem fixa do documento do cliente e
    a memória de cálculo ao lado; quem não a declara continua na rodada de hoje, que
    imprime uma linha por `EstimateLine`. As duas seções podem coexistir no mesmo
    template, desde que em abas de nomes diferentes.
    """

    label: str = Field(min_length=1, max_length=120)
    catalog: CatalogLayout
    bulletin_sheet_pattern: str = Field(min_length=1, max_length=MAX_SHEET_NAME_LENGTH)
    memory_sheet_pattern: str = Field(min_length=1, max_length=MAX_SHEET_NAME_LENGTH)
    bulletin: BulletinLayout
    memory: MemoryLayout
    general: GeneralLayout
    amendment: AmendmentLayout | None = None
    estimate: EstimateLayout | None = None
    estimate_grid: EstimateTemplateLayout | None = None
    extra_code_patterns: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_extra_code_patterns(self) -> WorkbookTemplate:
        for pattern in self.extra_code_patterns:
            try:
                compiled = re.compile(pattern)
            except re.error as error:
                raise ValuationValidationError(
                    "TEMPLATE_EXTRA_CODE_PATTERN_INVALID",
                    "padrão extra de código contratual não compila como expressão regular",
                    {"pattern": pattern, "reason": str(error)},
                ) from error
            if compiled.fullmatch("") is not None:
                raise ValuationValidationError(
                    "TEMPLATE_EXTRA_CODE_PATTERN_INVALID",
                    "padrão extra de código contratual casa a string vazia",
                    {"pattern": pattern},
                )
            if compiled.fullmatch("LAZER / PAISAGISMO") is not None:
                raise ValuationValidationError(
                    "TEMPLATE_EXTRA_CODE_PATTERN_INVALID",
                    "padrão extra de código contratual casa texto de linha de seção "
                    "(espaço/barra), não estrutura de código",
                    {"pattern": pattern},
                )
        return self

    def matches_extra_code(self, text: str) -> bool:
        """`True` quando o texto casa algum padrão extra de código declarado no template."""
        return any(re.fullmatch(pattern, text) is not None for pattern in self.extra_code_patterns)

    @model_validator(mode="after")
    def validate_sheet_names(self) -> WorkbookTemplate:
        names = [self.catalog.sheet_name, self.general.sheet_name]
        if self.amendment is not None:
            names.append(self.amendment.sheet_name)
        if self.estimate is not None:
            names.append(self.estimate.sheet_name)
        if self.estimate_grid is not None:
            names.append(self.estimate_grid.sheet_name)
            names.append(self.estimate_grid.memory_sheet_name)
        if len(names) != len(set(names)):
            raise ValuationValidationError(
                "TEMPLATE_SHEET_NAME_CONFLICT",
                "duas abas declaradas no template usam o mesmo nome",
                {"names": names},
            )
        return self

    @model_validator(mode="after")
    def validate_patterns(self) -> WorkbookTemplate:
        """O padrão precisa de `{worksite}` exatamente uma vez.

        Uma vez porque `worksite_sheet_budget` desconta o padrão inteiro menos o
        marcador para saber quanto sobra para o nome da obra; com dois marcadores a
        conta mediria a metade do que o nome custa, e a aba estouraria o teto que a
        conta jurava respeitar.
        """
        invalid = [
            pattern
            for pattern in (self.bulletin_sheet_pattern, self.memory_sheet_pattern)
            if pattern.count(WORKSITE_PLACEHOLDER) != 1
        ]
        if invalid:
            raise ValuationValidationError(
                "TEMPLATE_SHEET_PATTERN_INVALID",
                "padrão de nome de aba precisa conter {worksite} exatamente uma vez",
                {"patterns": invalid},
            )
        return self

    @property
    def worksite_sheet_budget(self) -> int:
        """Quantos caracteres sobram para o nome da obra dentro do nome da aba.

        É o MENOR orçamento entre as duas abas da obra, e não um por aba, porque BM e
        MEMÓRIA da mesma obra precisam se chamar do mesmo jeito: quem confere abre as
        duas lado a lado. Com o padrão do MAPÃO (`BM {worksite}` e `MEMÓRIA {worksite}`)
        quem manda é a memória, e sobram 23 dos 31 caracteres da planilha.
        """
        return MAX_SHEET_NAME_LENGTH - max(
            len(pattern.replace(WORKSITE_PLACEHOLDER, ""))
            for pattern in (self.bulletin_sheet_pattern, self.memory_sheet_pattern)
        )

    def sheet_worksite_label(self, worksite_name: str) -> str:
        """O nome da obra COMO ELE CABE no nome da aba — inteiro sempre que couber."""
        return _worksite_sheet_label(worksite_name, self.worksite_sheet_budget)

    def bulletin_sheet_name(self, worksite_name: str) -> str:
        """Nome da aba BM da obra, validado contra os limites da planilha."""
        return _sheet_name(self.bulletin_sheet_pattern, self.sheet_worksite_label(worksite_name))

    def memory_sheet_name(self, worksite_name: str) -> str:
        """Nome da aba MEMÓRIA da obra, validado contra os limites da planilha."""
        return _sheet_name(self.memory_sheet_pattern, self.sheet_worksite_label(worksite_name))


def _sheet_name(pattern: str, worksite_name: str) -> str:
    return _validate_sheet_name(pattern.replace(WORKSITE_PLACEHOLDER, worksite_name))


def _worksite_sheet_label(worksite_name: str, budget: int) -> str:
    """A forma curta do nome da obra para o nome da aba, em degraus declarados.

    O teto de 31 caracteres é do FORMATO, não nosso, e praça de nome real não cabe nele:
    "Campo do Morro da Bandeira" tem 26, e `MEMÓRIA ` come 8. Sem esta função a praça de
    nome real simplesmente não exporta. A alternativa — encurtar o `worksite_name` do
    boletim — apagaria o nome de dentro da pasta também; aqui só o RÓTULO da aba encurta,
    e o nome inteiro continua impresso na linha INTERVENÇÃO do BM e no cabeçalho da
    MEMÓRIA, onde não há teto nenhum.

    Os degraus, nesta ordem, parando no primeiro que couber:

    1. **O nome inteiro.** Enquanto couber, a aba é a de hoje, caractere a caractere — é
       isso que mantém a pasta que a prefeitura já recebe exatamente como ela é.
    2. **Sem as partículas de ligação** (`de`, `da`, `do`, `das`, `dos`): a forma que a
       própria orçamentista fala ("Campo Morro Bandeira"). Nenhuma palavra que NOMEIA a
       praça se perde. O `e` fica de fora do conjunto de propósito: em nome de praça ele
       tanto liga dois nomes quanto é inicial de um deles, e abreviar o que não se tem
       certeza de ser ligação é inventar.
    3. **Palavras do MEIO abreviadas** — as quatro primeiras letras e um ponto
       ("SINTETICA" → "SINT.") —, da mais longa para a mais curta, até caber. A primeira
       palavra (o tipo — PRAÇA, CAMPO) e a última (a palavra pela qual a aba é procurada,
       ou o `P2` da folha) ficam inteiras; a redundância mora no meio.
    4. **Recusa.** Não existe degrau que caiba em toda entrada, e truncar às cegas
       produziria duas praças diferentes com a mesma aba. Quem encurta o nome da praça é
       o humano, e a recusa diz o teto para que ele possa.

    Com o padrão do MAPÃO, os nomes reais deste produto cabem com folga; o mais longo
    ("Campo do Morro da Bandeira") cabe pelo degrau 2 até a folha P9 e pelo degrau 3 daí
    em diante.
    """
    if len(worksite_name) <= budget:
        return worksite_name
    words = _without_sheet_label_particles(worksite_name.split())
    candidate = " ".join(words)
    if len(candidate) <= budget:
        return candidate
    candidate = " ".join(_with_abbreviated_middle_words(words, budget))
    if len(candidate) <= budget:
        return candidate
    raise ValuationValidationError(
        "WORKSITE_NAME_DOES_NOT_FIT_SHEET",
        "o nome da obra não cabe no nome da aba nem na forma curta; encurte o nome da "
        f"obra para no máximo {budget} caracteres",
        {
            "worksite_name": worksite_name,
            "shortened": candidate,
            "length": len(candidate),
            "limit": budget,
        },
    )


def _without_sheet_label_particles(words: list[str]) -> list[str]:
    """Degrau 2. Nome só de partículas volta inteiro: aí não há redundância a tirar."""
    kept = [word for word in words if word.casefold() not in _SHEET_LABEL_PARTICLES]
    return kept or words


def _with_abbreviated_middle_words(words: list[str], budget: int) -> list[str]:
    """Degrau 3, determinístico: empate de tamanho abrevia a palavra mais à esquerda."""
    abbreviated = list(words)
    order = sorted(range(1, len(abbreviated) - 1), key=lambda index: (-len(words[index]), index))
    for index in order:
        if len(" ".join(abbreviated)) <= budget:
            break
        stem = f"{abbreviated[index][:_SHEET_LABEL_STEM]}."
        if len(stem) < len(abbreviated[index]):
            abbreviated[index] = stem
    return abbreviated


def _validate_sheet_name(name: str) -> str:
    if len(name) > MAX_SHEET_NAME_LENGTH:
        raise ValuationValidationError(
            "SHEET_NAME_TOO_LONG",
            "nome de aba excede o limite de 31 caracteres da planilha",
            {"name": name, "length": len(name)},
        )
    forbidden = sorted(_FORBIDDEN_SHEET_CHARS.intersection(name))
    if forbidden:
        raise ValuationValidationError(
            "SHEET_NAME_INVALID_CHARS",
            "nome de aba possui caractere não aceito pela planilha",
            {"name": name, "chars": forbidden},
        )
    return name


def default_template() -> WorkbookTemplate:
    """Template padrão do módulo, espelhando o layout MAPÃO mapeado."""
    columns = SheetColumns(
        item=SheetColumn(letter="A", label="ITEM", width=8),
        code=SheetColumn(letter="B", label="COD.", width=18),
        description=SheetColumn(letter="C", label="DESCRIÇÃO", width=56),
        unit=SheetColumn(letter="D", label="UN", width=8),
        unit_price=SheetColumn(letter="E", label="VALOR UNIT", width=14),
        quantity=SheetColumn(letter="F", label="QUANT", width=12),
        total=SheetColumn(letter="G", label="TOTAL", width=16),
    )
    # A memória imprime os operandos de cada bloco à esquerda do subtotal (que fica sob a
    # coluna de QUANT.). A fórmula do produto é uma faixa contígua `PRODUCT(primeiro:último)`,
    # então as colunas de operando precisam ser contíguas e nunca abarcar o subtotal. O
    # Campo do Toca tem blocos de quatro operandos (`0,6 x 0,6 x 0,6 x 58 postes`;
    # `quantidade x densidade x espessura x distância`), então QUANT. e TOTAL recuam para I e
    # J e abrem seis colunas de operando (quatro fatores + dedução + folga).
    memory_columns = SheetColumns(
        item=SheetColumn(letter="A", label="ITEM", width=8),
        code=SheetColumn(letter="B", label="CODIGO", width=18),
        description=SheetColumn(letter="C", label="DESCRIÇÃO", width=56),
        unit=SheetColumn(letter="D", label="UNIDADE", width=12),
        unit_price=SheetColumn(letter="E", label="VALOR UNIT", width=14),
        quantity=SheetColumn(letter="I", label="QUANT.", width=12),
        total=SheetColumn(letter="J", label="TOTAL", width=16),
    )
    return WorkbookTemplate(
        label="MAPÃO padrão (M2)",
        catalog=CatalogLayout(
            sheet_name="CATALOGO",
            first_row=2,
            code_column="A",
            description_column="B",
            unit_column="C",
            price_column="D",
        ),
        bulletin_sheet_pattern="BM {worksite}",
        memory_sheet_pattern="MEMÓRIA {worksite}",
        bulletin=BulletinLayout(
            title="BOLETIM DE MEDIÇÃO",
            header_row=7,
            columns=columns,
        ),
        memory=MemoryLayout(
            title="MEMÓRIA DE CÁLCULO",
            header_row=4,
            columns=memory_columns,
            operand_columns=["C", "D", "E", "F", "G", "H"],
        ),
        general=GeneralLayout(
            sheet_name="PLANILHA GERAL",
            title="PLANILHA GERAL DO CONTRATO",
            header_row=5,
            pair_sublabel_row=6,
            data_first_row=7,
            group_column="A",
            item_column="B",
            code_column="C",
            description_column="D",
            unit_column="E",
            contract_quantity_column="F",
            unit_price_column="G",
            amended_quantity_column="H",
            first_period_column="I",
        ),
        amendment=AmendmentLayout(
            sheet_name="MAPÃO - PREFEITURA",
            header_row=4,
            data_first_row=5,
            code_column="C",
            amended_quantity_column="H",
            blocks=[
                AmendmentColumns(
                    label="1ª RE-RA",
                    reduced_column="I",
                    added_column="J",
                    new_item_column="K",
                )
            ],
        ),
        estimate=EstimateLayout(
            columns=EstimateColumns(
                item=SheetColumn(letter="A", label="ITEM", width=8),
                code=SheetColumn(letter="B", label="COD.", width=18),
                source=SheetColumn(letter="C", label="FONTE", width=18),
                description=SheetColumn(letter="D", label="DESCRIÇÃO", width=56),
                unit=SheetColumn(letter="E", label="UN", width=8),
                unit_price=SheetColumn(letter="F", label="VALOR UNIT", width=14),
                unit_price_with_bdi=SheetColumn(letter="G", label="VALOR UNIT. C/ BDI", width=16),
                quantity=SheetColumn(letter="H", label="QUANT", width=12),
                total=SheetColumn(letter="I", label="TOTAL", width=16),
            ),
        ),
    )
