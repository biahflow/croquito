# F-042 T1 — Domínio do acervo de parcelas de canteiro

- **feature_id**: F-042
- **task_id**: T1
- **role**: builder
- **depends_on**: []
- **required_capabilities**: READ, WRITE (apenas `packages/valuation` e `tests/valuation`), VALIDATE
- **risk**: MÉDIO — toca `calc_matrix.py`, arquivo vivo do regime de cálculo da F-038.
- **relative_effort**: M

## Goal

Dar ao repositório o **motor** do acervo de parcelas de canteiro: um artefato versionado de
contribuições `STANDALONE` parametrizadas, e a função pura que o aplica produzindo
contribuições materializáveis na `CalcMatrix` existente — com proveniência e falha fechada.

Esta task é **domínio puro**. Não cria rota, não cria tela, não cria migração.

## Scope

1. **Módulo novo** `packages/valuation/src/croquito_valuation/site_setup.py`, no molde
   estrutural de `haulage.py` (dado + conferência + cálculo de uma unidade; o módulo não
   percorre a rodada nem persiste nada).

   Modelos (`ValuationContractModel`, como os vizinhos):

   - `SiteSetupOperand` — operando que é **ou** constante **ou** referência a parâmetro:
     - `name: str` (min 1, max 60) — nome que sai impresso na memória, em português;
     - `value: ExactDecimal | None`;
     - `parameter: str | None` (min 1, max 60) — nome do parâmetro de obra citado;
     - `unit: str | None` (min 1, max 20).
     - Validação: exatamente um de `value`/`parameter` preenchido. Código de erro
       `SITE_SETUP_OPERAND_AMBIGUOUS` quando ambos, `SITE_SETUP_OPERAND_EMPTY` quando nenhum.
   - `SiteSetupParcel` — uma parcela do acervo:
     - `id: str` — identidade estável **dentro do acervo**; escolha um `pattern` no molde dos
       identificadores já usados no repo (ver `TAKEOFF_ITEM_ID_PATTERN`) e documente a escolha
       na docstring;
     - `code: str` (min 1, max 30) — código do catálogo, validado contra
       `SCO_CODE_PATTERN`/`NON_SCO_CODE_PATTERN` como `ServiceHaulage.validate_codes`
       (`haulage.py:78-101`) faz, com código de erro `SITE_SETUP_CODE_INVALID`;
     - `label: str` (min 1, max 120);
     - `recipe: CalcRecipe`;
     - `operands: list[SiteSetupOperand]` (min_length=1);
     - `deductions: list[SiteSetupOperand]` (default vazio);
     - `note: str | None` (max 500).
   - `SiteSetupKit` — o acervo:
     - `version: str` — identificação estável e versionada do acervo (molde
       `HAULAGE_SEED_VERSION`, `haulage.py:53`);
     - `source_label: str` — de onde o acervo foi autorado;
     - `parcels: list[SiteSetupParcel]` (min_length=1);
     - validação de `id` duplicado → `SITE_SETUP_DUPLICATE_PARCEL`;
     - propriedade/método `parameter_names() -> tuple[str, ...]` devolvendo, **em ordem
       estável e sem repetição**, todo parâmetro citado por qualquer operando ou dedução.

2. **Proveniência na contribuição** — estender `CalcContribution`
   (`packages/valuation/src/croquito_valuation/calc_matrix.py:56-124`) com campo **opcional**:

   - `kit_origin: SiteSetupOrigin | None = None`, onde `SiteSetupOrigin` carrega
     `kit_version: str`, `parcel_id: str`.
   - Validação nova: `kit_origin` presente com `basis` diferente de `STANDALONE` é recusa
     `CALC_CONTRIBUTION_KIT_ORIGIN_NOT_STANDALONE`. Encaixe a checagem na ordem existente de
     `validate_contribution` sem reordenar as que já existem.
   - O campo é opcional e tem default: **nenhuma** matriz hoje válida pode passar a ser
     inválida. Confirme isso rodando a suíte existente.
   - Onde `SiteSetupOrigin` mora é sua decisão (`models.py` ou `site_setup.py`); resolva o
     ciclo de import da forma menos invasiva e escreva o motivo na docstring.

3. **Aplicação** — função pura, em `site_setup.py`:

   ```python
   def apply_site_setup_kit(
       kit: SiteSetupKit,
       parameters: Mapping[str, Decimal],
       *,
       excluded_parcel_ids: Collection[str] = (),
       available_codes: Collection[str] | None = None,
   ) -> list[ServiceContributions]:
   ```

   Comportamento exigido:

   - **Falha fechada por parâmetro faltante**: se o acervo cita parâmetro não presente em
     `parameters` (considerando apenas as parcelas **não** excluídas), levanta
     `ValuationValidationError` com código `SITE_SETUP_PARAMETER_MISSING` cujos detalhes
     **nomeiam todos** os parâmetros faltantes, em ordem estável. Nada é devolvido
     parcialmente.
   - **Falha fechada por código ausente**: quando `available_codes` é fornecido e uma parcela
     não excluída cita código fora dele, recusa `SITE_SETUP_CODE_ABSENT` nomeando o código.
     Nunca pular a parcela em silêncio.
   - Parcela em `excluded_parcel_ids` não gera contribuição, **não** exige seus parâmetros e
     **não** altera nenhuma outra parcela.
   - `excluded_parcel_ids` com id que não existe no acervo é recusa
     `SITE_SETUP_UNKNOWN_PARCEL` (erro de chamador, não silêncio).
   - Cada parcela vira uma `CalcContribution` com `basis=STANDALONE`, `source_item_id=None`,
     `kit_origin` preenchida, operandos com `value` já resolvido (constante ou valor do
     parâmetro) e `name` preservado.
   - Saída agrupada em `ServiceContributions` por `code`, na **ordem de primeira aparição** da
     parcela no acervo — mesma convenção de `assembleCalcMatrix`
     (`apps/web/src/orcamento/matrix.ts:348-369`). Duas parcelas do mesmo código entram como
     duas contribuições do mesmo `ServiceContributions`.
   - **Pura e idempotente**: mesma entrada, mesma saída, sem estado global, sem I/O.

4. **Pré-visualização** — função que responde "o que vai nascer" **sem** materializar na
   matriz, para a tela e o CLI consumirem depois:

   ```python
   def preview_site_setup_kit(kit, parameters, *, excluded_parcel_ids=(), available_codes=None)
       -> list[SiteSetupPreviewRow]
   ```

   Cada linha traz `parcel_id`, `code`, `label`, os operandos resolvidos e a **quantidade
   calculada**, obtida pelo mesmo caminho que a matriz usa para materializar
   (`calc_matrix._materialize` / `quantity_round` / `product_of` — reuse, não reimplemente a
   aritmética). A pré-visualização usa a mesma falha fechada do item 3.

5. **Carregamento de acervo declarado**: `load_site_setup_kit(payload: str) -> SiteSetupKit`
   via `model_validate_json`, no molde de `default_haulage_table()` (`haulage.py:141-148`).
   **Não** crie seed empacotado em `data/` nesta task — ver "Out of scope".

6. **Testes** em `tests/valuation/test_site_setup.py`, seguindo o padrão de helpers locais de
   `tests/valuation/test_haulage.py` e `tests/valuation/test_calc_matrix.py`. Cobrir no
   mínimo:

   - parcela com operando constante e parcela com operando de parâmetro, ambas materializando
     a quantidade esperada (use as formas reais citadas na feature: `1 × 2 meses`;
     `23 dias × 12 h` + `8 dias × 24 h`; `2,00 × 1,40`; `132,21 × 3`);
   - parâmetro faltante → recusa que nomeia **todos** os faltantes, e nada materializado;
   - parâmetro faltante citado **só** por parcela excluída → **não** é recusa;
   - código ausente de `available_codes` → recusa nomeando o código;
   - exclusão de uma parcela não altera as demais;
   - aplicar duas vezes com os mesmos parâmetros devolve resultado igual;
   - operando ambíguo/vazio recusado;
   - `kit_origin` em contribuição não-`STANDALONE` recusada;
   - a saída de `apply_site_setup_kit` entra numa `CalcMatrix` válida e é resolvida por
     `resolve_calc_matrix` sem erro (o portão `CALC_CONTRIBUTION_STANDALONE_WITH_ITEM`
     continua valendo e não é contornado).

## Out of Scope

- **Seed empacotado com o acervo real** (`data/sco-site-setup-v1.json`). O primeiro acervo é
  ato humano da orçamentista (Human Gate 4 da feature) e depende da planilha real, que não
  está no repositório. Esta task entrega o formato e o carregador; o dado vem depois.
- **Rota, migração, persistência e tela.** Nada em `services/`, `apps/web/` ou
  `migrations/`.
- **Alterar o regime legado** de `resolve_calc_matrix` ou qualquer validação existente de
  `CalcContribution`/`CalcMatrix` além do acréscimo do item 2.
- **A tabela de transporte** de `haulage.py`.
- Inferir acervo de planilha antiga.

## Acceptance Criteria

1. `apply_site_setup_kit` produz contribuições `STANDALONE` que passam pelas validações
   existentes de `calc_matrix.py` sem que nenhuma delas seja afrouxada.
2. Parâmetro citado e não declarado → recusa que nomeia todos os faltantes; nada materializado.
3. Parcela excluída não nasce, não exige parâmetro e não altera as demais.
4. Duas aplicações com a mesma entrada dão saída igual.
5. Código fora de `available_codes` → recusa nomeando o código, nunca omissão silenciosa.
6. Nenhuma chamada paga, nenhum I/O de rede, nenhuma leitura de arquivo fora de `load_*`.
7. A suíte existente de `tests/valuation/` continua verde sem edição de teste antigo. Se
   precisar editar um teste existente, **pare e reporte** em vez de editar.

## Validation

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f042
uv run pytest tests/valuation -q
make check
make test
```

Registre a saída dos portões no BUILD REPORT. `make check` roda ruff, mypy strict,
`check_docs.py` (valida **todo link relativo de Markdown**, inclusive deste arquivo) e drift
de contratos.

## Armadilhas verificadas

- `CalcContribution` **não tem** `id`, chave nem versão hoje (`calc_matrix.py:56-124`); a
  identidade que esta task introduz vive na parcela do acervo e chega à contribuição só como
  proveniência.
- `ContributionBasis.STANDALONE` (`models.py:250-252`) proíbe `source_item_id` por validação
  já existente (`calc_matrix.py:79-84`). Não contorne: gere com `source_item_id=None`.
- Subtotal é sempre **computado**, nunca declarado (`calc_matrix.py:259-262`).
- `CalcRecipe.DECLARED_PRODUCT` (`models.py:214`) é a receita aberta — produto genérico dos
  operandos. As parcelas de canteiro reais usam `QTY_TIMES_MONTHS`, `DAYS_TIMES_HOURS` e
  `DECLARED_PRODUCT`; não invente receita nova.
- `Decimal` onde a precisão escrita importa; float só no solver.
- Mensagens de domínio em português, identificadores em inglês.
