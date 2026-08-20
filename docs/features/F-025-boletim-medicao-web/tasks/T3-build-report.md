# BUILD REPORT — F-025 T3 (e2e: aprovação nominal + export do boletim pelas rotas `/v1`)

```text
Status: BUILD_COMPLETE
Files changed:
  - tests/e2e/test_valuation_v1_chain.py — único arquivo alterado.
    * Refatoração: o corpo de `test_valuation_round_full_chain_through_v1_api`
      (steps 0-9, da prancha até `/calc`+`GET .../bulletin`) foi extraído para uma
      função auxiliar `_build_round_through_calc(tmp_path, monkeypatch, stack) ->
      _ChainThroughCalc` (novo dataclass frozen/slots com client, storage, round_id,
      version, final_packet, final_takeoff). O teste original passou a chamar essa
      função e seguir com os steps 10-11 (dossiê + estado final) exatamente como
      antes — nenhuma asserção do teste original foi removida ou alterada, só movida.
    * Adição: `_assert_route_workbook_matches_cli(...)` — reabre o `.xlsx` publicado
      pela rota, grava um segundo `.xlsx` pelo caminho de exportação do
      domínio/worker (`write_valuation_workbook` + `audit_workbook`, com
      `contract=None`), audita o lado do "CLI" e compara os dois por
      `canonicalize_workbook` (paridade lógica, não bytes).
    * Adição: `test_aprovacao_e_exportacao_do_boletim_fecham_por_v1_sem_cli(...)` —
      o teste novo de T3, cobrindo os 4 pontos do escopo (export bloqueado antes de
      aprovar, aprovação carimbada, export publicado + paridade com o CLI, recálculo
      que caduca a aprovação + reaprovação que destrava).
  - Nenhum outro arquivo tocado. `apps/web/src/medicao/*`,
    `services/api/src/croquito_api/{main,valuation_rounds}.py`,
    `tests/api/test_valuation_round_routes.py` etc. continuam exatamente como T1/T2
    os deixaram (git status confere: só `tests/e2e/test_valuation_v1_chain.py`
    aparece como meu).

Testes novos:
  - test_aprovacao_e_exportacao_do_boletim_fecham_por_v1_sem_cli — cobre:
    1. `POST .../bulletin/export` ANTES de aprovar → 422 DOMAIN_VALIDATION_FAILED,
       details.code=VALUATION_EXPORT_BLOCKED, "VALUATION_NOT_APPROVED" em
       details.errors, e nenhum objeto novo no fake store (portão do domínio, não
       da rota).
    2. `POST .../approve` → version avança; `GET /v1/valuation-rounds/{id}` expõe
       bulletin.approval.approved=true, approved_by=subject do token,
       stale=false.
    3. `POST .../bulletin/export` → 200, workbook publicado; `GET .../bulletin`
       expõe workbook_url; o `.xlsx` é lido de volta do fake object store pela
       chave determinística (`tenants/<tenant>/valuation-rounds/<id>/bulletin/
       <valuation_sha256>.xlsx`) e comparado por canonicalização com o `.xlsx` que
       o caminho de exportação do domínio/worker produziria para a MESMA
       `Valuation` aprovada (relida da resposta da API) e o MESMO catálogo (
       rebuild determinístico dos mesmos bytes enviados no presign) — critérios 5
       e 6 da feature.
    4. `POST .../calc` de novo (sem nenhuma decisão nova) → `GET` expõe
       bulletin.approval.stale=true (Valuation.id é gerado de novo a cada
       `/calc`); `POST .../bulletin/export` recusa com APPROVAL_CONTENT_MISMATCH
       em details.errors; `POST .../approve` de novo → `POST .../bulletin/export`
       volta a 200 com workbook_present=true.
  - test_valuation_round_full_chain_through_v1_api — comportamento idêntico ao
    anterior (mesmas asserções), agora construído sobre a função auxiliar extraída.

Validation executed:
  - uv run pytest tests/e2e/test_valuation_v1_chain.py -q → 2 passed.
  - uv run pytest tests/e2e -q → 17 passed (suíte e2e inteira).
  - make test → uv run pytest: 1709 passed, 13 skipped (0 falhas em Python).
    npm web:test: 2 falhas em apps/web/src/medicao/etapas.test.ts (ver "contexto de
    paralelismo" abaixo — fora do meu escopo, `tests/e2e/` não toca em apps/web/).
  - make check → ruff check: all checks passed; ruff format --check: 421 arquivos
    já formatados (após rodar `ruff format` no meu arquivo para corrigir 3 blocos
    que a formatação padrão do projeto preferia numa linha única); mypy strict
    (packages/core/src packages/valuation/src services/api/src services/worker/src
    tests): "Success: no issues found in 194 source files"; check_docs.py: 250
    arquivos Markdown válidos, paridade de lifecycle ok; schema_export --check-dir:
    ok; contracts:check: ok; web:check FALHOU em
    apps/web/src/medicao/etapas.test.ts (erro de tipo TS2322 em
    RoundStateBulletin.workbook_present) — mesmo contexto de paralelismo do
    make test, não relacionado a este arquivo.
Validation skipped: none.
Unavailable capabilities: none.
Assumptions:
  - `run_export_valuation` (services/worker/src/croquito_worker/valuation/cli.py:
    858-882) foi lido como referência do desenho fail-closed do CLI, mas sua
    assinatura exige `contract: ContractWorkbook` NÃO opcional. A rota de F-025 T1
    publica o `.xlsx` do boletim com `contract=None`
    (`render_valuation_workbook(valuation, catalog, default_template())` em
    main.py, sem consolidado — a rodada de `/v1` não importa contrato). Como
    `plan_workbook` acrescenta a aba PLANILHA GERAL (e RE-RA) sempre que
    `contract is not None` — mesmo com um `ContractWorkbook` vazio —, chamar
    `run_export_valuation` com qualquer contrato produziria um `.xlsx`
    estruturalmente diferente do publicado pela rota, o que quebraria a premissa
    de "mesmas condições, contract=None" do próprio contrato da tarefa. Assumi que
    o objetivo é a paridade REAL de conteúdo, não a paridade de qual função
    Python é chamada, e usei diretamente as duas funções que
    `run_export_valuation` embrulha — `write_valuation_workbook` e
    `audit_workbook` (ambas de `croquito_valuation`, o pacote de domínio que tanto
    o CLI quanto a rota chamam por baixo) — com `contract=None` explícito, dentro
    de `_assert_route_workbook_matches_cli`, importadas só ali dentro (function
    scope), no espírito de "import das funções do worker/CLI só dentro do teste de
    paridade" do contrato.
  - O catálogo do lado "CLI" da comparação é reconstruído chamando `_catalog_bytes()`
    de novo (função determinística já existente no arquivo, sem estado aleatório)
    e reparseando com `PriceCatalog.model_validate_json` — não uma referência ao
    objeto Python que a rota usou internamente, para que a comparação não seja
    trivialmente "o mesmo objeto contra si mesmo".
  - A `Valuation` do lado "CLI" é a relida da resposta de `GET .../bulletin` depois
    do export (`Valuation.model_validate(bulletin_after_export["valuation"])`), não
    um objeto interno da rota — também para evitar comparação trivial.
Remaining risks:
  - `apps/web` está com `make test`/`make check` vermelhos em
    `src/medicao/etapas.test.ts` (2 falhas de teste + 1 erro de tipo TS2322 em
    `RoundStateBulletin.workbook_present`, todos girando em torno da etapa
    "aprovacao"/`ApprovalState.stale`). `git status` confirma que
    `apps/web/src/medicao/*` está modificado por outra mão (T2, rodando em
    paralelo) e que eu não toquei nesses arquivos. Não investiguei nem tentei
    corrigir — fora do meu escopo (T3 é só `tests/e2e/`) e explicitamente marcado
    como "não é falha sua" pelo Task Contract quando a causa é o paralelismo com
    T2. Fica registrado para quem fechar a integração da feature: os portões
    globais (`make check`/`make test`) só ficam verdes de ponta a ponta quando T2
    também estiver com o front consistente com o contrato de T1.
  - A refatoração de `test_valuation_round_full_chain_through_v1_api` move ~260
    linhas para uma função auxiliar não prefixada com `test_` (não é mais
    coletada pelo pytest isoladamente); o comportamento e as asserções do teste
    original são idênticos, só a organização mudou — reconferido rodando
    `tests/e2e/test_valuation_v1_chain.py` isoladamente (2 passed) e a suíte
    `tests/e2e` inteira (17 passed).
Human decisions required: none — nenhum gate de aprovação humana foi alcançado por
  este teste (é validação automatizada, sem deploy/mutação AWS/migração destrutiva/
  chamada paga em massa).
```

## Desvios conscientes do spec e por quê

1. **`run_export_valuation` não foi chamado diretamente** para o lado "CLI" da
   comparação de paridade, apesar de citado no Task Contract
   (`cli.py:858-882`). Motivo técnico, não preferência de estilo: sua assinatura
   exige `contract: ContractWorkbook` sem default/Optional, e QUALQUER
   `ContractWorkbook` não-`None` (mesmo vazio) faz `plan_workbook` acrescentar a
   aba PLANILHA GERAL — o que tornaria o `.xlsx` do "CLI" estruturalmente
   diferente do `.xlsx` que a rota publica (que é escrito com `contract=None`,
   conforme o próprio Task Contract descreve). Chamar `run_export_valuation` com
   um contrato construído ad hoc teria produzido uma comparação que reprovaria
   por um motivo estrutural que nada tem a ver com o conteúdo da medição —
   exatamente o tipo de "correção silenciosa da premissa errada" que a instrução
   de execução veda. Usei as duas funções que `run_export_valuation` embrulha
   (`write_valuation_workbook` + `audit_workbook`, ambas as MESMAS funções de
   produção que a rota e o CLI chamam por baixo) com `contract=None` explícito,
   preservando o espírito de "mesmas condições" do critério de aceite 2. Ficou
   documentado em bloco de docstring dedicado dentro do próprio teste
   (`_assert_route_workbook_matches_cli`), não só neste relatório.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- Não investiguei nem tentei corrigir a falha de `apps/web/src/medicao/etapas.ts`/
  `etapas.test.ts` (tipo `RoundStateBulletin.workbook_present` e a lógica de
  `resumoDaAprovacao`/`stale`) — é território exclusivo de T2 rodando em paralelo,
  e o Task Contract veda tocar `apps/web/`.
- Não criei um teste e2e adicional cobrindo o caminho `reject` de
  `ReviewerDecision` na aprovação (o domínio aceita, mas
  `ApproveValuationRequest`/a rota só escrevem `confirm` — T1 documenta que o
  produto não desenhou o que a recusa destravaria). Fora de escopo: T3 pede a
  cadeia feliz de aprovação+export, e inventar cobertura de um caminho que a
  própria rota não expõe seria escopo não pedido.
- Não toquei `tests/api/test_valuation_round_routes.py` (já tem cobertura de rota
  unitária equivalente, de T1) nem demos/goldens, conforme "fora de escopo" do
  contrato.
