# F-043 T1 — Gabarito de ordem fixa e memória de cálculo do orçamento

- **feature_id**: F-043
- **task_id**: T1
- **role**: builder
- **depends_on**: []
- **required_capabilities**: READ, WRITE (`packages/valuation`, `services/worker/.../valuation/cli.py`, `tests/valuation`), VALIDATE
- **risk**: ALTO — toca `template.py`, `estimate_workbook.py` e `workbook_writer.py`, todos vivos e com golden versionado.
- **relative_effort**: L

## Decisão do dono já tomada

O gabarito entregável é a aba **`PLANILHA ORÇAMENTÁRIA` (433 códigos)**, não a
`PLANILHA PADRÃO ORDENADA` (518). Isso resolve o unknown 3 da feature. O **arquivo real do
cliente não está no repositório** e não estará: esta task entrega o mecanismo e uma fixture
sintética; o gabarito real entra depois como dado JSON declarado, sem tocar código.

## Goal

Fazer a rodada publicar a planilha do orçamento **percorrendo um gabarito declarado de ordem
fixa** — todas as linhas, inclusive as de quantidade zero —, com a aba de memória de cálculo
ao lado, auditada pelo mesmo portão fail-closed que já existe.

## Scope

### 1. `EstimateTemplateLayout` em `packages/valuation/src/croquito_valuation/template.py`

Seção **adicional** do `WorkbookTemplate` (campo novo `estimate_grid: EstimateTemplateLayout | None = None`).
Não altere `EstimateLayout` (`:470-499`), que continua servindo a rodada sem gabarito.

- `EstimateTemplateRow`: `group: str`, `item: str`, `code: str`, `description: str`,
  `unit: str`, `unit_price: ExactDecimal | None = None`.
  - `group` e `item` são **texto**, preservados como escritos (zeros à esquerda e a forma
    `GG.N`); nunca recomputados nem renumerados pelo escritor. As lacunas de grupo (5, 15, 22
    no documento real) existem por o gabarito simplesmente não declarar linhas daqueles
    grupos — não crie campo para "grupo ausente".
  - `code` validado contra `SCO_CODE_PATTERN`/`NON_SCO_CODE_PATTERN` (molde
    `ServiceHaulage.validate_codes`, `haulage.py:78-101`), erro
    `TEMPLATE_ESTIMATE_GRID_CODE_INVALID`.
- `EstimateTemplateColumns`: letras de coluna para `group`, `item`, `code`, `description`,
  `unit`, `quantity`, `unit_price`, `total`; validação de coluna repetida no molde de
  `EstimateColumns` (`:426-467`).
- `EstimateTemplateLayout`: `sheet_name`, `title`, **`revision_label: str`** (identificação da
  revisão do gabarito — é o controle do risco "gabarito envelhecido em silêncio"),
  `memory_sheet_name: str`, `header_row: int (ge=2)`, `columns`, `rows: list[EstimateTemplateRow]`
  (min_length=1), rótulos de total no molde de `EstimateLayout`, e os number formats.
  - Validação: `code` duplicado entre as linhas → `TEMPLATE_ESTIMATE_GRID_DUPLICATE_CODE`
    nomeando o código. O índice código→linha exige unicidade; se o gabarito real tiver
    duplicata legítima, isso vira decisão humana, não remendo silencioso.
  - Validação: `item` duplicado → `TEMPLATE_ESTIMATE_GRID_DUPLICATE_ITEM`.
  - Validação de conflito de nome entre `sheet_name`, `memory_sheet_name` e as demais abas do
    template, no molde de `WorkbookTemplate` (`:502-596`).

### 2. Escritor que percorre o gabarito

Em `estimate_workbook.py`, ao lado do que existe (não substitua `plan_estimate_workbook`):

```python
def plan_estimate_grid_workbook(estimate: Estimate, template: WorkbookTemplate) -> EstimateWorkbookPlan
def write_estimate_grid_workbook(estimate, template, output_path) -> EstimateWriteReport
def audit_estimate_grid_workbook(workbook_path, estimate, template) -> EstimateAuditReport
```

Regras, todas exigidas:

- A ordem das linhas é **a do gabarito**, nunca a de `estimate.lines`. Linha da planilha =
  `header_row + 1 + índice no gabarito`. O cursor sequencial sobre `estimate.lines`
  (`:271-273`) não vale aqui.
- **Toda** linha do gabarito é impressa, inclusive as sem quantidade: `group`, `item`, `code`,
  `description`, `unit` saem do gabarito; quantidade e total saem **zerados**, nunca ausentes.
- Preço unitário: quando o orçamento tem a linha daquele código, manda o preço do orçamento
  (`unit_price_with_bdi`, a mesma base que `plan_estimate_workbook` usa hoje para o total).
  Quando não tem, imprime o `unit_price` declarado no gabarito, se houver; senão deixa a
  célula vazia. Nunca compare os dois preços nem recuse por divergência — declare essa regra
  na docstring.
- **Código no orçamento e ausente do gabarito é recusa** `ESTIMATE_GRID_CODE_ABSENT`,
  nomeando o código, levantada **antes** de qualquer escrita. Jamais acrescente linha ao fim
  do arquivo.
- Fórmula do total da linha: use **a mesma forma** que `plan_estimate_workbook` já emite
  hoje. Não estenda `GRAMMAR_PATTERNS` (`canonical.py:65-72`). Se alguma célula que você
  precisa escrever não couber na gramática fechada, **pare e reporte** — estender a gramática
  exige mexer também no mini-avaliador e é decisão fora desta task.
- Totais e BDI preservam a regra do ADR-0038 exatamente como hoje: o BDI impresso é a
  **diferença entre os totais truncados** (`estimate_workbook.py:390-399`), não o percentual
  aplicado.
- Dinheiro truncado, não arredondado, onde o documento trunca.

### 3. Aba de memória de cálculo — reuso obrigatório

A memória do orçamento **reusa o render de bloco da medição**. Duplicar é proibido pelo
contrato da feature (é o terceiro risco declarado).

- `workbook_writer._plan_block` (`:421-499`) já consome `CalcBlock` genérico + `template.memory`
  e **não** depende de `Valuation`/`WorksiteBulletin`. Promova-o a função pública
  (`plan_calc_block`), mantendo o comportamento byte-idêntico para a medição — o golden de
  `test_writer_roundtrip.py`/`test_canonical_golden.py` é o oráculo disso.
- `workbook_writer._plan_memory` (`:502-613`) **é** específico de medição (exige `Valuation`,
  `WorksiteBulletin`, `bulletin.lines`). **Não** tente generalizá-la. A memória do orçamento
  itera `Estimate.calc_sheets` (`estimate.py:251`) diretamente.
- `estimate_workbook.py` usa tipos de plano próprios (`EstimatePlannedCell`) enquanto
  `_plan_block` produz `PlannedCell`. Escreva **um** conversor explícito e testado entre os
  dois; não reimplemente o layout do bloco.
- A memória impressa tem um bloco por código, com rótulo, **operandos nomeados**, dedução e
  subtotal — que é o que `_plan_block` já faz.

### 4. Auditoria

- `canonicalize_workbook` (`canonical.py:325`) ignora **apenas** a aba do catálogo: as duas
  abas novas entram na canonicalização e portanto **precisam estar no plano**, senão viram
  `SHEET_UNEXPECTED`/`CELL_UNEXPECTED`.
- O auditor reabre o arquivo e recomputa cada fórmula em `Decimal`; divergência **não
  publica**. Espelhe o portão que `test_estimate_workbook.py:259` já exerce.

### 5. Caminho de uso fora dos testes

Hoje o caminho de export do orçamento chama `default_template()` **hardcoded**
(`cli.py:1028-1054`, `:1072`, `:1853`, `:1912`) e nenhum subcomando exporta a planilha de um
`Estimate` real aceitando `--template`.

- Acrescente o subcomando `export-estimate` ao CLI `croquito-valuation`, com
  `--estimate <estimate.json>`, `--template <template.json>` (via `_add_template_option`,
  `cli.py:2937-2943`) e `--output <dir>`; ele grava **e audita**, e falha fechado.
- Quando o template declarar `estimate_grid`, o comando usa o escritor de gabarito; sem ele,
  usa o escritor atual. Nenhuma mudança de comportamento para quem não declara gabarito.

### 6. Testes

- Fixture **sintética** de gabarito: pequena mas com as três propriedades que importam —
  mais de um grupo, **lacuna de grupo** (ex.: 01, 02, 04) e numeração `GG.N` com mais linhas
  do que o orçamento preenche.
- Golden canônico novo (molde `tests/valuation/golden/estimate-workbook.canonical.json`),
  gerado pelo mesmo caminho dos existentes.
- Testes exigidos: ordem e numeração preservadas; linha sem quantidade sai zerada e presente;
  código do orçamento fora do gabarito recusado por nome e **sem** arquivo escrito; memória
  com bloco por código e operandos nomeados; auditoria limpa; célula adulterada reprovando;
  fórmulas dentro da gramática fechada; a medição continua byte-idêntica ao golden dela
  depois da promoção de `_plan_block`.

## Out of Scope

- **Inferir gabarito de `.xlsx` real.** O gabarito entra como JSON declarado.
- **Trocar `EstimateLayout`** ou o escritor atual: o novo é seção adicional.
- **A aba `PLANILHA GERAL`** (lista de preços do contrato) — é entrada, não saída.
- **Estender `GRAMMAR_PATTERNS`** ou o mini-avaliador.
- `services/api`, `apps/web`, migrações.

## Acceptance Criteria

1. O arquivo gerado tem as linhas do gabarito, na ordem do gabarito, com a numeração `GG.N`
   e as lacunas de grupo preservadas como declaradas.
2. Linha sem quantidade sai zerada e presente, nunca ausente.
3. Código do orçamento ausente do gabarito → recusa nomeando o código, sem arquivo escrito.
4. A memória tem um bloco por código com parcelas nomeadas, renderizado pelo **mesmo**
   `plan_calc_block` da medição.
5. O auditor reabre e recomputa em `Decimal`; divergência não publica.
6. O golden da medição continua idêntico (a promoção de `_plan_block` não muda um byte).
7. `revision_label` do gabarito é impresso no arquivo, para que o arquivo diga qual revisão
   usou.

## Validation

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f043
uv run pytest tests/valuation -q
make check
make test
make valuation-estimate-demo
```

## Armadilhas verificadas

- `estimate_workbook.py:1-32` declara que é **adaptador**, não generalização do escritor da
  medição, e que `_text`/`_number`/`_formula` são cópias deliberadas. Isso continua valendo:
  o reuso exigido aqui é **só** o do render de bloco da memória.
- `audit_estimate_workbook` usa `canonicalize_workbook` como biblioteca, não `audit_workbook`
  (que exige `Valuation`/`WorksiteBulletin`). Mantenha esse desenho.
- `TEMPLATE_HEADER_ROW_TOO_SMALL` é levantado em `estimate_workbook.py:255-260`, não em
  `template.py`.
- Códigos de erro são estáveis e em `application/problem+json` do lado da API; aqui use
  `ValuationValidationError` com código, no molde dos vizinhos.
- `make check` roda `scripts/check_docs.py`, que valida todo link relativo de Markdown do
  repositório — inclusive deste arquivo.
