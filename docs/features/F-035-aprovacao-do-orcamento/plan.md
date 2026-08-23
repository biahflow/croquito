# F-035 — Plano de execução

feature_id: F-035
goal: o orçamento montado passa a ser um artefato **assinável e ainda não despachado** — uma
pessoa que não o montou o assume como está, a assinatura fica amarrada ao conteúdo exato, e
só então a planilha é publicada, atrás de portão fail-closed.

assumptions:
- **A migração é a `0015`.** A `0014` é da F-037, entregue hoje. Se outra branch entrar
  antes, é rebase de integração; o encadeamento relativo entre as tasks é que precisa
  sobreviver.
- Recusa é `403`/`409`/`422` com código estável em `application/problem+json`.
- O papel `aprovador` entra no realm nesta entrega, mas **atribuí-lo a alguém em HML é ato
  humano** — está nos gates do contrato.

risks:
- **Quebra de contrato de rota existente.** `POST .../estimate` deixa de publicar. O
  snapshot de OpenAPI e o teste de paridade tornam a mudança visível, não silenciosa; o
  único consumidor é `apps/web`, entregue na mesma feature (T3).
- **Dar leitura ao `aprovador` pode afrouxar uma mutação por engano.** São 22 rotas, 11 de
  cada lado. Mitigação nomeada abaixo, e é a mais importante do plano.
- **`main.py` tem ~10.9k linhas** e `OrcamentoApp.tsx` ~3.2k. Mitigação: T2 e T3 entram por
  seams que já existem (`round_state_payload`, `derivarEtapas`), e a tela é conferida
  renderizando com a folha real — foi assim que a F-034 achou três divergências que o
  recorte de CSS escondia.

## O que o levantamento mudou, e que o contrato subestimava

**Três arquivos de e2e tocam a cadeia do orçamento**, não um: `test_estimate_rounds_v1.py`
(assere `workbook_url is not None`, linha 477), `test_reference_catalog_chain.py` (idem,
687 — escrito hoje na F-037) e `test_valuation_full_chain.py` (pelo CLI).

**O CLI quebra em dois lugares**: `run_export_estimate_workbook` (`cli.py:1021`) é chamado
por `run_estimate_demo` (`cli.py:1865`) **e** por `tests/valuation/test_estimate_workbook.py:285`.
A armadilha registrada no contrato falava só da demo.

**Registrar "quem montou" exige uma categoria nova de coluna.** `append_revision`
(`estimate_rounds.py:363-409`) carrega adiante JSON-documento (default `None`) e JSON-mapa
(default `{}`); um escalar `str | None` não cabe em nenhuma. As três alternativas foram
recusadas com razão escrita: dentro do `estimate_json` contaminaria digest e goldens e poria
identidade no domínio; em `artifact_refs_json` seria abusar de um campo cuja docstring diz
que ele guarda chave de objeto; e comparar revisão com a pai é a arqueologia que a decisão 6
do ADR-0046 recusou.

**A salvaguarda do maior risco já existe.**
`test_sem_o_papel_toda_rota_recusa_antes_do_lookup`
(`tests/api/test_estimate_round_routes.py:513`) já enumera as 22 rotas. O teste irmão que a
T2 precisa escrever — com só `aprovador`, leituras passam e mutações recusam — nasce dele.

**Há precedente de papel no código sem estar no realm**: `architect`, `domain_reviewer` e
`field_technician` não estão em nenhum dos dois realms. Acrescentar `aprovador` continua
certo, mas não é bloqueio de entrega.

tasks:
  - id: T1
    role: builder
    goal: o Estimate ganha aprovação e portão próprio, e a cadeia offline continua fechando
    scope: `packages/valuation/src/croquito_valuation/estimate.py` (tipo de decisão próprio,
      `approval`, `content_digest`, `export_errors`/`ensure_exportable`, `schema_version`),
      aprovação sintética no CLI, `tests/valuation/`, goldens regravados.
    out_of_scope: qualquer arquivo de `services/api`; qualquer arquivo de `apps/web`;
      `_ESTIMATE_SAFETY_NOTES`, cuja frase continua verdadeira.
    depends_on: []
    validation: make check, make test, make valuation-estimate-demo
    relative_effort: M
  - id: T2
    role: builder
    goal: montar deixa de publicar, e a assinatura passa a ser a condição do despacho
    scope: migração `0015` e a categoria nova de coluna em `append_revision`; as três rotas;
      bloco `approval` no estado da rodada; papel `aprovador` em `journeys.py` e nos realms;
      snapshot de OpenAPI; API Contract; testes de rota.
    out_of_scope: qualquer arquivo de `apps/web`; qualquer mudança na cadeia de medição.
    depends_on: [T1]
    validation: make check, make test
    relative_effort: L
  - id: T3
    role: builder
    goal: a etapa "Aprovação e despacho" na jornada, conforme a revisão aprovada
    scope: `apps/web/src/orcamento/` — etapa, ato em dois passos, registro, caducidade,
      despacho, rótulos e testes.
    out_of_scope: qualquer arquivo de `services/`; o bloco reservado do mock (envio por
      e-mail/Drive).
    depends_on: [T2]
    validation: npm --workspace @croquito/web run test, npm run web:check, make check
    relative_effort: M
  - id: T4
    role: builder
    goal: e2e da cadeia com aprovação e despacho, e os dois e2e existentes ajustados
    scope: `tests/e2e/` — cadeia nova; ajuste de `test_estimate_rounds_v1.py` e
      `test_reference_catalog_chain.py`, que hoje esperam planilha publicada na montagem.
    out_of_scope: qualquer arquivo de produção; qualquer arquivo de `apps/web`.
    depends_on: [T2]
    validation: uv run pytest tests/e2e/, make test
    relative_effort: S

parallel_groups:
- [T3, T4] — as duas dependem só de T2 e não dividem arquivo: T3 é `apps/web/src/orcamento/`,
  T4 é `tests/e2e/`.
critical_path: T1 → T2 → T3. T2 é a de maior esforço: carrega a migração, a quebra de
  contrato de rota e a separação de papel em 22 rotas.
integration_strategy: commits separados por task, com revisão linha a linha entre eles.
  Nenhuma task encerra com portão vermelho. T1 e T2 rodam em sequência — T2 usa o domínio
  que T1 entrega.
human_gates: nenhum aberto para o código. ADR-0046 `Accepted` e Design Approval Package
  revisão 1 aprovado, ambos por ato humano em 2026-08-22. Seguem fora desta aprovação, por
  declaração do registro: a **copy** das telas novas. E permanecem como atos humanos: atribuir
  o papel `aprovador` a alguém em HML, o merge/deploy, e o ato nominal sobre um orçamento
  real.
planning_findings:
- **O unknown 1 do contrato está fechado pela aprovação do pacote.** A barra de etapas do
  mock tem seis, e "Planilha" não está entre elas: a etapa é **substituída** por "Aprovação e
  despacho", não acrescentada. Uma etapa sobre um arquivo que ainda não existe não teria o
  que mostrar.
- **A recusa de auto-aprovação não tem molde na medição.** Ela não segrega montar de assinar
  — mesmo papel faz as duas coisas —, então o teste do critério 3 nasce novo, sem espelho.
- **`_ESTIMATE_SAFETY_NOTES` não muda.** A nota diz que o orçamento não passa pelo portão de
  exportação **da medição**, e isso continua verdadeiro: o portão novo é próprio e não recebe
  `ContractWorkbook`. A frase está no golden; mexer nela trocaria uma verdade por um erro.
