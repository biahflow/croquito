# T3 — BUILD REPORT

```text
feature_id: F-026
task_id: T3
harness: Claude Code (worktree /Users/danielcampos/workspace/daniel/croquito-specs,
         branch f-026-importadores)
```

## Baseline

Confirmado no início (herdado do estado documentado no `T2-build-report.md`, reconfirmado
ao final com `make check`/`make test` completos, ver abaixo): `git status --short` mostrava
só os diffs não commitados de T1 e T2 (13 modificados + 8 novos, listados no relatório de
T2) — nenhum arquivo de T3 ainda existia. Nenhuma falha pré-existente.

## BUILD REPORT

```text
Status: BUILD_COMPLETE

Files changed:
  - tests/e2e/test_estimate_rounds_v1.py
    -> Cascata da rodada `/v1` ganha uma quarta fonte, o catálogo SINAPI real de T2
       (`read_sinapi_catalog` sobre `write_sinapi_xlsx`/`sinapi_fixture_layout`),
       instalada pela MESMA rota `POST /v1/estimate-rounds/{id}/catalogs` que as outras
       três (upload assinado + PUT no object store, igual SCO/EMOP/composição). A decisão
       de código do banco de concreto (`BANCO DE CONCRETO SINTETICO`), que a fixture do
       orçamentista (`build_demo_estimate_assignments`, fora de escopo desta task) decide
       pela EMOP, é reescrita SÓ neste teste (`assignment.model_copy(update={...})`) para
       citar a SINAPI (código "0009012", unidade "UN", igual à do item) — nenhuma outra
       decisão muda, e a contagem de confirmados/rejeitados no `code-assignments` não se
       altera (mesmo item, fonte diferente). Duas asserções novas no fim do teste: a linha
       do `Estimate` publicado com `price_origin.value == "sinapi"` e código "0009012"
       (`estimate.lines`), e a planilha `.xlsx` publicada, reaberta via
       `canonicalize_workbook`, com `"SINAPI"` na célula `FONTE` daquela linha (localizada
       pelo índice da linha `sinapi`, não por posição fixa). Docstring do módulo
       atualizada (três fontes -> quatro, `import-sinapi` citado) para não divergir do
       teste.
  - tests/e2e/test_valuation_full_chain.py
    -> Teste NOVO (não extensão in-place da fixture `estimate_chain`, ver "Desvios
       conscientes" #1),
       `test_estimate_chain_with_five_sources_including_sinapi_and_sicro`: reaproveita o
       SCO/EMOP/COMPOSIÇÃO já importados pela fixture `estimate_chain` (module-scoped,
       evita repetir a extração cara) e soma `import-sinapi` + `import-sicro` reais do
       CLI (`main(["import-sinapi", ...])`/`main(["import-sicro", ...])`, nunca chamada
       direta ao domínio) sobre uma cascata de cinco catálogos. Redecide o mesmo item
       (banco de concreto, `_BENCH_ITEM_ID` já existente no arquivo) para citar a SINAPI
       (mesmo código "0009012") e roda `confirm-codes` + `build-estimate` reais sobre essa
       cascata. Asserções: ordem de origem da cascata em `estimate.json`
       (`[SCO, EMOP, COMPOSITION, SINAPI, SICRO]`, literal), exatamente uma linha com
       `price_origin == PriceOrigin.SINAPI` / `.value == "sinapi"` e código "0009012". A
       SICRO entra na cascata (citada literalmente na asserção de ordem) mas não precifica
       nenhum item — o Task Contract só pede "cascata de cinco fontes... validando o
       estimate.json resultante" para este arquivo, não que toda origem precifique algo;
       ver "Desvios conscientes" #2.

Files NOT changed (fora de escopo, confirmados por `git status --short` inicial e final —
mesmo conjunto de arquivos de T1/T2, nenhum a mais): todo o resto do diff pendente listado
no `T2-build-report.md` (enum `PriceOrigin`, `sinapi.py`/`sicro.py`, fixtures, `cli.py`,
schemas/contratos gerados, `test_sinapi.py`/`test_sicro.py`, etc.) — nada disso foi tocado
por T3, nem havia necessidade: a cadeia fechou de ponta a ponta sem nenhum achado de
código de produção.

Testes novos:
  - `tests/e2e/test_estimate_rounds_v1.py::test_estimate_round_full_chain_through_v1_api`
    (teste EXISTENTE, estendido, não novo): cascata de 4 fontes pela API `/v1`; 2
    asserções novas no final citando `sinapi`/`SINAPI` literalmente (price_origin da linha
    + célula FONTE da planilha reaberta). Nenhuma asserção anterior foi removida ou
    afrouxada; nenhuma contagem existente mudou (mesmo item, 1 confirmado a menos pela
    EMOP e 1 a mais pela SINAPI, soma igual).
  - `tests/e2e/test_valuation_full_chain.py::test_estimate_chain_with_five_sources_including_sinapi_and_sicro`
    (teste NOVO): cascata de 5 fontes pelo CLI real (`import-sinapi`+`import-sicro`+
    `confirm-codes`+`build-estimate`), cobre a exigência do Task Contract para este
    arquivo. `test_estimate_chain_happy_path` (existente, cascata de 3 fontes) continua
    passando sem nenhuma alteração — a fixture `estimate_chain` module-scoped não foi
    tocada.

Validation executed (todos em foreground, no worktree, na ordem do contrato):
  - make check -> verde. ruff check "All checks passed!"; ruff format --check "428 files
    already formatted"; mypy strict "Success: no issues found in 200 source files"
    (mesma contagem de T2: nenhum arquivo novo de produção, só os dois de teste, já
    cobertos); check_docs "251 arquivos Markdown, paridade de lifecycle verificada" (249
    no fim de T2 -> 251: este T3-build-report.md + o diretório de tasks já existente
    contando 2 a mais, conferido — nenhum link quebrado); schema_export --check-dir sem
    drift; contracts:check sem drift; web:check (tsc -b + vite build) verde; infra-check
    (terraform fmt -check) verde.
  - make test -> verde. pytest: "1736 passed, 13 skipped, 48 warnings in 127.63s" (T2
    terminou em 1735 passed, 13 skipped; +1 = o teste novo em
    test_valuation_full_chain.py — test_estimate_rounds_v1.py não ganhou função nova, só
    estendeu a existente). vitest: "Test Files 40 passed (40)" / "Tests 697 passed (697)"
    (idêntico a T2 — nenhum arquivo web tocado por T3).
  - uv run pytest tests/e2e -q -> verde, 17 passed (17 = 7 arquivos e2e existentes + a
    função nova; contagem de arquivos não mudou, só de testes dentro de
    test_valuation_full_chain.py: 9 -> 10).

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - "Pelo menos um item decidido citando" a SINAPI (critério 3 da feature) foi satisfeito
    redecidindo, só dentro de cada teste, um item que a fixture do orçamentista já decide
    por outra fonte (banco de concreto, antes EMOP) — a fixture de produção
    (`estimate_fixture.py`) é imutável nesta task (fora de escopo: "Código de produção").
    A alternativa seria estender `estimate_fixture.py` com uma decisão própria para
    SINAPI/SICRO, o que o Task Contract não autoriza tocar.
  - Unidade do item (UN, banco de concreto) e da entrada SINAPI escolhida ("0009012",
    "MOBILIARIO SINTETICO SINAPI", UN) batem por escolha deliberada — evita depender do
    caminho `ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE` (que exigiria só uma nota, mas
    testaria um caminho secundário em vez do feliz).

Remaining risks:
  - Nenhum risco novo de produção: T3 não tocou código de produção. O único risco
    herdado é o mesmo já registrado por T1/T2 (pendências de commit/aceite da rodada
    inteira F-026, fora do escopo desta task).

Human decisions required: none para esta task (escopo fechado, portões fecham sozinhos).
```

## Desvios conscientes do spec

1. **`test_valuation_full_chain.py`: teste NOVO em vez de extensão in-place da fixture
   `estimate_chain`.** O Task Contract oferece as duas formas ("teste novo (ou extensão
   da fixture `estimate_chain`)"). A fixture é `scope="module"` e alimenta DOIS testes
   existentes: `test_estimate_chain_happy_path` (que afirma
   `[catalog.origin for catalog in estimate_chain.cascade] ==
   [PriceOrigin.SCO, PriceOrigin.EMOP, PriceOrigin.COMPOSITION]` e
   `{line.price_origin for line in estimate.lines} == set(digests)` — esta segunda
   quebraria se a cascata ganhasse SINAPI/SICRO sem que alguma linha os citasse, porque
   o `set` de origens dos catálogos deixaria de bater com o `set` de origens das linhas)
   e `test_build_estimate_refuses_a_cited_source_missing_from_the_cascade`. Estender a
   fixture compartilhada exigiria reescrever a asserção do primeiro teste — tecnicamente
   permitido pelo contrato ("mudam se forem consequência direta e declarada"), mas o
   contrato também PREFERE cenário aditivo ("prefira cenário aditivo a alterar o
   existente"). Escrevi um teste novo que reaproveita os artefatos caros da fixture
   (`estimate_chain.catalog_paths`, evitando reimportar EMOP/composição) e roda só os
   dois `import-*` novos + `confirm-codes`/`build-estimate` frescos — zero alteração em
   `test_estimate_chain_happy_path`, que continua provando a cascata de três fontes
   original sem tocar em nada.
2. **`test_valuation_full_chain.py`: nenhum item cita a SICRO.** O Task Contract pede
   "cascata de cinco fontes no `build-estimate`, validando o `estimate.json` resultante"
   para este arquivo — sem exigir que toda origem precifique um item (diferente do
   critério de `test_estimate_rounds_v1.py`, que pede explicitamente "pelo menos um item
   decidido citando" a fonte nova, mas só menciona SINAPI ali). A SICRO entra na cascata,
   é importada pelo CLI real e é conferida por nome literal na ordem de
   `estimate.cascade`; nenhuma linha a cita porque nenhuma decisão da fixture do
   orçamentista mede um item nessa unidade/família sem forçar uma segunda redecisão
   artificial. Julguei que redecidir DOIS itens (um para SINAPI, outro para SICRO) só
   para ter uma linha de cada correria o risco de esvaziar de sentido a redecisão do
   banco (que já prova "linha com proveniência nova" no critério 3 da feature via
   `test_estimate_rounds_v1.py`) sem que o contrato deste segundo arquivo pedisse isso.
   Registrando aqui como decisão consciente, não como lacuna esquecida.
3. **`assignment.model_copy(update={...})` em vez de reconstruir `CodeAssignmentInput`
   do zero.** `CodeAssignmentInput` é um `ValuationContractModel`; `model_copy` não
   revalida o modelo (comportamento padrão do Pydantic), mas os campos atualizados
   (`code`, `catalog_sha256`, `note`) continuam satisfazendo os invariantes do modelo
   (`action="confirm"` com `code` não nulo, `note` dentro do tamanho) — e a validação
   REAL de negócio (código pertence ao catálogo citado, unidade compatível) acontece
   depois, no domínio (`apply_code_assignments_over_cascade`), que É exercitado pelos
   comandos `confirm-codes`/rota `code-assignments/decisions` reais em ambos os testes.
   Nenhuma validação de contrato foi contornada, só a validação sintática de campo (que
   os valores literais já satisfazem por construção).

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- Decisão própria de SICRO em `estimate_fixture.py` (ou um item da legenda sintética
  dedicado a uma fonte só de tabela pública nova) — melhoraria a simetria SINAPI/SICRO
  nos dois arquivos e2e, mas exigiria tocar código de produção (`estimate_fixture.py`,
  `plate.py`), fora de escopo desta task ("Código de produção: se a cadeia não fechar, é
  achado de T1/T2 — PARE e reporte" — aqui a cadeia fechou, então não há achado a
  reportar, só uma melhoria de cobertura que o Task Contract não pediu).
- Extensão da fixture `estimate_chain` para cinco fontes por padrão (em vez do teste novo
  em paralelo) — descartada conscientemente, ver "Desvios conscientes" #1; deixaria a
  suíte mais simples de ler à custa de reescrever uma asserção de teste que já passava.
- Nenhum ajuste em `docs/STATUS.md`: o marco atual não mudou por esta task (T3 fecha o
  critério 3 da feature F-026 nos testes, mas o aceite/commit da rodada inteira segue
  pendente, como já registrado nos relatórios de T1/T2).
