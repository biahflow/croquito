# BUILD REPORT — F-020 T5

```text
Status: BUILD_COMPLETE
Files changed:
  - tests/e2e/test_estimate_rounds_v1.py (novo) — e2e da cadeia inteira do orçamento-base
    pelas rotas /v1 (F-020 T5, critério de aceite 3 da feature), espelhando
    tests/e2e/test_valuation_v1_chain.py; nenhum outro arquivo foi tocado.

Validation executed:
  - uv run pytest tests/e2e/test_estimate_rounds_v1.py -x -q
    -> 1 passed
  - make check (ruff check, ruff format --check, mypy strict sobre
    packages/core/src packages/valuation/src services/api/src services/worker/src tests,
    check_docs.py, schema_export --check-dir, contracts:check, web:check
    [tsc -b + vite build], terraform fmt -check -recursive)
    -> todos os passos verdes; um achado de ruff (E501, linha 461) e uma reformatação de
       ruff format foram corrigidos no próprio arquivo novo antes do check final.
  - make test (uv run pytest completo + npm --workspace @croquito/web run test)
    -> pytest: 1691 passed, 13 skipped, 48 warnings (baseline 1690 passed/13 skipped + o
       1 teste novo = 1691; nenhuma regressão)
    -> vitest: 38 arquivos, 683 passed (idêntico ao baseline; T5 não toca apps/web)

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - Não reconferi o baseline (T1+T2+T3+T4+T6 integrados, make check/make test verdes,
    pytest 1690 passed/13 skipped, vitest 683) rodando make check/make test na árvore ANTES
    de escrever o arquivo novo — o contrato já o declara verificado. A evidência de "sem
    regressão" vem da comparação do total PÓS-mudança (1691 = 1690 + 1 teste novo) com o
    baseline declarado, e do make check completo (que já varre a árvore inteira, incluindo
    os diffs não commitados de T1-T4/T6) ter passado sem nenhum achado fora do arquivo
    novo.
  - Os três catálogos da cascata (SCO, EMOP, composição) são construídos chamando
    diretamente as funções de domínio que os comandos `import-emop`/`import-compositions`
    do CLI usam por baixo (`croquito_valuation.catalog.read_price_catalog`,
    `croquito_valuation.emop.read_emop_catalog_with_report`,
    `croquito_valuation.composition.compile_compositions`) — nunca o módulo
    `croquito_worker.valuation.cli`, que embrulha essas mesmas funções. Confirmado que
    nenhuma dessas três funções mora em `cli.py` antes de as usar.
  - O digest de origem do catálogo de composição (`source_sha256` que
    `compile_compositions` exige) é o sha256 dos bytes do `CompositionSet` serializado em
    memória (`hashlib.sha256(...).hexdigest()`), em vez do `file_sha256` de um arquivo
    gravado em disco como o comando `import-compositions` faz — o valor não precisa
    coincidir com o da fixture do CLI (o teste não compara os dois), só ser um sha256
    hexadecimal válido e estável dentro do próprio teste; simplificação deliberada que
    evita escrever um arquivo extra sem alterar a cadeia provada.
  - "Auditoria ok" (passo 8 do contrato, `GET .../estimate`) é verificado de duas formas
    complementares: implicitamente pelo `200` do `POST .../estimate` (a rota é fail-closed
    por ADR-0038 — auditoria reprovada nunca publica) e explicitamente re-executando
    `audit_estimate_workbook` sobre a MESMA planilha publicada, relida do object store
    (`audit.status == "ok"`, `audit.findings == []`).
  - A URL assinada devolvida pelo `GET .../estimate` (`workbook_url`) é a fixture
    `https://storage.invalid/...` de `FakeObjectStore` e não é buscável por HTTP; a
    reabertura da planilha publicada lê os bytes direto do object store
    (`storage.body(object_key)`), com `object_key` reconstruído pela mesma função pura que
    a rota usa (`estimate_rounds.estimate_workbook_key`) e o digest conferido contra
    `workbook_sha256` antes de abrir o arquivo — o teste nunca inventa o caminho do blob.
  - Para ler o valor computado das células de fórmula da planilha (BDI impresso, total com
    BDi), usei `croquito_valuation.canonical.canonicalize_workbook` — que recomputa fórmula
    por fórmula reabrindo o arquivo com `openpyxl.load_workbook` por dentro — em vez de ler
    `cell.value` cru: células de fórmula gravadas por `write_estimate_workbook` carregam a
    string da fórmula (ex. `=C12-C10`), não um valor em cache, então `openpyxl` puro sem o
    avaliador canônico devolveria a fórmula, não o número. Para as duas colunas de texto do
    critério de aceite (FONTE e VALOR UNIT. C/ BDI) e o bloco de itens sem preço, o mesmo
    dicionário canônico é lido pela chave `["value"]`, que para célula de texto é o valor
    literal — nenhum comportamento novo, só a mesma via de leitura.

Remaining risks:
  - Nenhum risco novo identificado na superfície testada. A cadeia inteira (cascata,
    prancha, extração, takeoff, código, montagem, planilha) fechou pela rota sem exigir
    nenhum ajuste de código de produção — T3/T6 já cobriam o que T5 precisava provar.

Human decisions required: none
```

## Escopo e execução

Arquivo novo: `tests/e2e/test_estimate_rounds_v1.py`. Nenhum outro arquivo foi editado —
todos os demais diffs presentes na árvore (`git status`) pertencem a T1/T2/T3/T4/T6 e a
docs, já revisados e aprovados antes desta task, e não foram tocados.

### O que o teste cobre

1. `POST /v1/estimate-rounds` abre a rodada sem fonte de preço.
2. As três fontes da cascata (SCO, EMOP, composição) são instaladas na ordem declarada via
   `POST .../catalogs`, cada uma por presign + PUT real contra o `FakeObjectStore`; o
   catálogo SCO nasce de `read_price_catalog` sobre o MAPÃO anterior sintético
   (`build_synthetic_previous_mapao`), o EMOP de `read_emop_catalog_with_report` sobre o
   `.DBF` sintético (`write_emop_dbf` + `emop_fixture_layout`), e a composição de
   `compile_compositions` sobre `build_synthetic_composition_set()` — nenhuma das três
   passa pelo CLI.
3. Reinstalar o catálogo SCO (mesmo conteúdo, novo upload) recusa com
   `409 ESTIMATE_CASCADE_ORIGIN_DUPLICATE` e não avança a versão da rodada.
4. Prancha associada por presign + PUT; extração enfileirada (`202`), drenada pelo
   `LocalQueueWorker` com `legend_fixture_adapter` sobre a MESMA prancha sintética
   (`render_synthetic_plate`) — nenhuma chamada de provider real acontece — e o comando
   publicado confere (`extract_estimate_plate`).
5. Decisão de takeoff item a item (`build_demo_takeoff_decisions`), drenando o re-render do
   overlay a cada rodada (`rerender_estimate_takeoff_overlay`) até `review_status ==
   "complete"` e overlay não mais vencido.
6. Decisão de código por item confirmado, CITANDO a fonte da cascata
   (`build_demo_estimate_assignments(final_packet, cascade)`, que resolve `catalog_sha256`
   pela origem declarada de cada decisão sintética) — pavimento e alambrado no SCO, banco e
   piso emborrachado na EMOP, gramado na composição, luminária rejeitada (nenhuma fonte a
   precifica).
7. `base_version` velho no `POST .../estimate` recusa com `409 REVISION_CONFLICT`, sem
   publicar orçamento nem planilha (`estimate.present == False` na leitura seguinte).
8. `POST .../estimate` com `bdi_percent="25.00"` e o `base_version` correto monta, audita e
   publica; `estimate_json` da resposta valida com `Estimate.model_validate` (schema v2);
   `total_amount - total_amount_without_bdi` bate com o valor impresso na célula de BDI da
   planilha (lida via `canonicalize_workbook`); `unpriced_item_ids` é exatamente o item da
   luminária.
9. `GET .../estimate` confere o mesmo `estimate_sha256`, `workbook_present`, `workbook_url`
   presente, e a planilha publicada — relida do object store pelo `object_key` derivado do
   digest do orçamento — tem as colunas `FONTE` e `VALOR UNIT. C/ BDI` no cabeçalho e o
   bloco `ITENS SEM PREÇO NA CASCATA` com o id da luminária, sem nenhum campo de preço
   junto (só o id é impresso, como o domínio já garante).
10. Nenhuma linha do arquivo importa `croquito_worker.valuation.cli` — conferido pela
    própria lista de imports do arquivo.

## Desvios conscientes do spec

Nenhum. A cadeia fechou inteiramente pela rota, como o contrato previa; não foi necessário
alterar código de produção nem revisar premissa do spec.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- O teste não exercita `POST .../catalogs/order` (reordenação da cascata) nem
  `GET .../catalog/search` / `code-suggestions` — cobertos por `tests/api/test_estimate_round_routes.py`
  (T3) e fora do critério de aceite 3 da feature, que pede a cadeia feliz completa até a
  planilha publicada, não cada rota isolada.
- Não recomputei `total_amount`/linha a partir de quantidade × preço para conferir o
  boletim centavo a centavo pela SEGUNDA vez — isso já é o que `audit_estimate_workbook`
  faz (e o teste chama essa auditoria explicitamente); duplicar o cálculo no teste
  adicionaria uma segunda implementação da mesma regra sem cobrir um risco novo.
