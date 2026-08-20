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
from croquito_valuation.models import ValuationContractModel

COLUMN_LETTER_PATTERN: Final = r"^[A-Z]{1,2}$"
WORKSITE_PLACEHOLDER: Final = "{worksite}"
PERIOD_PLACEHOLDER: Final = "{n}"
MAX_SHEET_NAME_LENGTH: Final = 31
_FORBIDDEN_SHEET_CHARS: Final = set(r"[]:*?/\'")


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
        if len(names) != len(set(names)):
            raise ValuationValidationError(
                "TEMPLATE_SHEET_NAME_CONFLICT",
                "duas abas declaradas no template usam o mesmo nome",
                {"names": names},
            )
        return self

    @model_validator(mode="after")
    def validate_patterns(self) -> WorkbookTemplate:
        missing = [
            pattern
            for pattern in (self.bulletin_sheet_pattern, self.memory_sheet_pattern)
            if WORKSITE_PLACEHOLDER not in pattern
        ]
        if missing:
            raise ValuationValidationError(
                "TEMPLATE_SHEET_PATTERN_INVALID",
                "padrão de nome de aba precisa conter {worksite}",
                {"patterns": missing},
            )
        return self

    def bulletin_sheet_name(self, worksite_name: str) -> str:
        """Nome da aba BM da obra, validado contra os limites da planilha."""
        return _sheet_name(self.bulletin_sheet_pattern, worksite_name)

    def memory_sheet_name(self, worksite_name: str) -> str:
        """Nome da aba MEMÓRIA da obra, validado contra os limites da planilha."""
        return _sheet_name(self.memory_sheet_pattern, worksite_name)


def _sheet_name(pattern: str, worksite_name: str) -> str:
    return _validate_sheet_name(pattern.replace(WORKSITE_PLACEHOLDER, worksite_name))


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
    memory_columns = SheetColumns(
        item=SheetColumn(letter="A", label="ITEM", width=8),
        code=SheetColumn(letter="B", label="CODIGO", width=18),
        description=SheetColumn(letter="C", label="DESCRIÇÃO", width=56),
        unit=SheetColumn(letter="D", label="UNIDADE", width=12),
        unit_price=SheetColumn(letter="E", label="VALOR UNIT", width=14),
        quantity=SheetColumn(letter="F", label="QUANT.", width=12),
        total=SheetColumn(letter="G", label="TOTAL", width=16),
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
            operand_columns=["C", "D", "E"],
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
