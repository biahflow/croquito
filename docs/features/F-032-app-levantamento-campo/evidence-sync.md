# F-032 — Evidência da fatia de sincronização (plano [plan-sync.md](plan-sync.md))

Review Evidence Package incremental da fatia de sincronização ampliada (T7–T16).
Consolidado por tarefa conforme cada BUILD REPORT chega; a evidência do MVP local
(T1–T6) permanece em [evidence.md](evidence.md).

## Baseline

- Data: 2026-08-21, branch `f-032-app-levantamento-campo`, HEAD `a086667`, working
  tree limpa (worktree `../croquito-f032`).
- `make check` → exit 0 (ruff, mypy strict, check_docs, contratos sem drift,
  build web+field, terraform fmt).
- `make test` → exit 0 — inclui os 128 testes de `apps/field` (11 arquivos) e as
  suítes Python.
- Falhas preexistentes conhecidas: nenhuma.

## Tarefas

### T7 — contrato `SurveyPacket` + mapeamento no app

- Executor: `implementador-sonnet` (harness Claude Code; degrau registrado no
  método de delegação do usuário). BUILD REPORT: `BUILD_COMPLETE`.
- Entrega: `packages/core/src/croquito_core/field.py` (SurveyPacket + submodelos,
  `SURVEY_SCHEMA_VERSION 1.0.0`, sem `tenant_id`, validador cruzado de
  `survey_id` nas operações); entrada nova no `contracts.manifest.json` →
  `schemas/survey-packet.schema.json` + `src/survey-packet.generated.ts` gerados;
  `apps/field/src/sync/contract.ts` (mapeamento puro + `isSurveyPacketShape` +
  `MissingMediaError`); testes `tests/core/test_field.py` (18) e
  `apps/field/src/sync/contract.test.ts` (7).
- Assunções do builder aceitas na revisão: `device_id` derivado da primeira
  operação do outbox (erro se vazio); mídia sempre por identidade de conteúdo
  (sha256/mime/byte_size), inclusive `access_media_ref`; `audio_media_ref`/
  `note_id` aditivos para T12; limite declarado de ±1 km em mm.
- Validação do builder: `make contracts` ok; `pytest tests/core` ok; field 135
  testes ok; `make test` completo ok (1808 passed / 13 skipped Python; 853 web);
  `make check` reprovou APENAS na linha de status do `feature.md` editada pelo
  modelo principal (formato do `check_docs`) — corrigida na revisão; `make check`
  exit 0 após a correção.
- Revisão linha a linha (modelo principal): 2 achados LOW — `isOperationShape`
  sem checagem de `created_at` (corrigido na revisão, 135 testes verdes) e
  `gps_fixes` sempre vazio (provisão de contrato aceita; o GPS real viaja em
  `arrival_context`). Nenhum achado HIGH.

### T10 — login OIDC no app com tolerância offline

- Executor: `implementador-sonnet`. BUILD REPORT: `BUILD_COMPLETE`.
- Entrega: `apps/field/src/auth/` (máquina de estados pura `signed_out | active |
  expired_offline | reauth_required`; `oidcClient.ts` com fábrica testável
  `createAuthClient`, sessão em `localStorage` — diferença deliberada e documentada
  de `apps/web` —, `getFreshAccessToken()` devolvendo estado tipado
  `AUTH_REAUTH_REQUIRED`, nunca exceção); `silent-renew.html` próprio (lição do
  incidente de 2026-08-19 preservada); indicador de identidade no `AppBar` com
  estado sempre escrito; aviso não bloqueante de papel `field_technician` ausente.
  26 testes novos (10 da máquina + 16 do cliente com UserManager fake); suíte do
  field em 161 testes verdes.
- Desvios conscientes aceitos na revisão: fábrica `createAuthClient` (necessária ao
  teste sem rede); `vite-env.d.ts` novo (tipos de env — primeiro uso de env no
  app); implementou o indicador no shell conforme o texto do contrato, mais
  restrito que a tela cheia da prancha 6c (divergência documentada); recomputação
  do estado a cada 60s (necessária para a 6c ser verdadeira com o app aberto).
- Reprovações de `make check`/`make test` vistas pelo builder eram o trabalho NÃO
  commitado da T8 em paralelo no mesmo worktree (ruff/openapi de
  `services/api/**`) — fora do escopo da T10, corretamente reportadas em vez de
  "consertadas"; portões completos serão re-rodados no fechamento da onda 2.
- Revisão linha a linha (modelo principal): nenhum achado bloqueante; risco
  registrado pelo builder (decode de JWT sem verificação de assinatura, só
  exibição) documentado no próprio código.
- Envs novas: `VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID` (sem elas o app opera
  em modo local). Ato humano pendente: client `croquito-field` + papel
  `field_technician` no realm.

### T8 — backend `/v1/surveys` (tabelas, migração, rotas)

- Executor: `implementador-opus`. BUILD REPORT: `BUILD_COMPLETE` (rodada inicial +
  rodada de correção da revisão).
- Entrega: 5 rotas (`operations` em lote idempotente com conflito 6b carregando
  `server_snapshot`/`last_seq_by_device`; `GET` de estado; `media/presign` com a
  regra 6a "metadados antes da mídia"; `media/{sha256}/confirm` com digest
  (GCS adiado ao worker, auditado) publicando exatamente uma mensagem por
  transição com caminho de volta (fila recusou → volta a PRESIGNED + 503);
  `complete` com `base_version` + mídia toda confirmada → `export_survey`);
  migração `0007_survey_field_sync` aditiva; papel `field_technician` (403 antes
  de lookup) + papéis de leitura do escritório; códigos novos `SURVEY_CONFLICT`,
  `SURVEY_MEDIA_NOT_REFERENCED`, `SURVEY_MEDIA_DIGEST_MISMATCH`,
  `SURVEY_MEDIA_PENDING`, `SURVEY_NOT_CONCLUDED`, `SURVEY_PACKET_INVALID`;
  comandos de fila `export_survey` / `transcribe_survey_audio` /
  `analyze_survey_photo`; 25+ testes novos em `tests/api/test_surveys.py`;
  `API_CONTRACT.md` e snapshot OpenAPI atualizados (portão de rota documentada).
- Revisão linha a linha (modelo principal) exigiu rodada de correção, aplicada
  pelo mesmo builder: (1) comandos de fila renomeados para a convenção do repo
  (verbo snake_case — o Task Contract tinha ditado kebab-case, erro do
  planejador); (2) chaves com id gerado no cliente escopadas por tenant — PK
  composta `(tenant_id, id)` em `survey_records`/`survey_operation_records`, FKs e
  uniques compostas — fechando o vazamento de existência/ocupação de UUID entre
  tenants que o próprio builder havia reportado; a migração 0007 (nunca aplicada)
  foi editada em vez de criar 0008. O builder ainda corrigiu uma falha da
  instrução de revisão (unique de seq sem tenant reabriria o defeito) — aceito.
- Validação: `pytest tests/api` 316 passed/11 skipped; `make check` e `make test`
  EXIT 0; testes de migração executados contra PostgreSQL 17 real (12 passed,
  incluindo gate de drift e proibição de DDL destrutivo).
- Riscos remanescentes declarados: mensagem de fila pode se perder entre commit e
  publish (sem tabela de outbox no servidor; retry do cliente cobre o `complete`,
  o `confirm` devolve cedo ao ver CONFIRMED — aceito e documentado); colisão de
  numeração com a 0007 da F-029 fica para a integração (PLAN_DEVIATION prevista).

### T11 — handler `export_survey` no worker (pacote → observações)

- Executor: `implementador-opus`. BUILD REPORT: `BUILD_COMPLETE`.
- Entrega: `services/worker/src/croquito_worker/survey_export.py` (mapeamento puro
  e determinístico → `SceneRevision` de campo + `attachments.json`; chaves
  estáveis `tenants/{t}/surveys/{s}/export/{scene,attachments}.json`), roteamento
  `export_survey` no dispatch do `local_queue.py`, 16 testes novos. Fail-closed
  provado: artefato gravado dá `['SCENE_NOT_APPROVED']` em `export_errors()`;
  contrafactual com approved/export forçados dá
  `APPROXIMATION_NOT_ACCEPTED`/`UNRESOLVED_ENTITY`; medida confirmada divergente
  da geometria dá `MEASUREMENT_MISMATCH`.
- Desvios conscientes ACEITOS na revisão (todos são invariantes do pipeline
  aplicadas, não lacunas): (1) `APPROXIMATION_NOT_ACCEPTED` não aparece no
  artefato como gravado porque `export_errors()` pula entidade `export=False` — o
  Task Contract errou; a intenção é provada por contrafactual em teste;
  (2) elemento não vira polyline (ordem de ligação não declarada = topologia
  inventada — viaja em anexo); (3) `angle`/`height`/`level`/`drop` não ganham
  unidade/semântica inventada — viram Issue INFO + entrada em
  `measurements_without_scene_entry` no anexo; (4) medida sem segmento observado
  não é amarrada por proximidade. Decisões de domínio registradas para a fatia de
  integração no escritório consumir.
- Validação: `pytest tests/worker` 936 passed/1 skipped (baseline 920);
  `tests/worker+api+e2e` 1261 passed; `make check` e `make test` exit 0
  (pytest 1849; web 853; field 204 — já com a T9 em andamento na árvore).
- Riscos declarados: `attachments.json` carrega texto de cliente no bucket do
  tenant (conferir política de ciclo de vida do prefixo `export/` na operação);
  artefatos ainda sem consumidor no escritório (fatia futura, relação F-030).

### T9 — SyncEngine + painel de sincronização (pranchas 6a/6b)

- Executor: `implementador-opus`. BUILD REPORT: `BUILD_COMPLETE` (rodada inicial
  + rodada de correção da revisão).
- Entrega: `apps/field/src/sync/` (config por `VITE_CROQUITO_API_BASE_URL` —
  ausente = modo local sem rede; `apiClient.ts` como único módulo com `fetch`;
  backoff exponencial com limites nomeados; engine com lote em ordem `seq` →
  ack → mídia por categoria 6a → complete com chave idempotente por versão);
  painel `SyncScreen` + `syncViewModel` puros; transação Dexie única
  `saveSurveyWithOperation` (fecha a dívida da revisão T3); status local novo
  `superseded` (dado, não schema — sem migração); `apps/field/AGENTS.md`
  atualizado (rede só em `src/sync/`, e só em `apiClient.ts`). Field: 210
  testes (era 161).
- **CODE_FINDING HIGH da revisão linha a linha, corrigido em rodada**: após
  `accept_server`, as operações preteridas mantinham seq antigo e `nextSeq`
  contava sobre elas — cada edição seguinte nasceria acima do que o servidor
  espera e reabriria a prancha 6b em loop. Correção: `nextSeq` exclui
  `superseded` (mantendo `acked` — regressão da T1 preservada) e
  `accept_server` preterí a UNIÃO {não reconhecidas} ∪ {acked acima do head do
  servidor} — o builder ampliou o critério proposto pela revisão, que deixava
  escapar a operação recusada com seq abaixo do head. Cada metade da correção
  provada por mutação (reverter → teste falha com o sintoma exato). Servidor
  fake dos testes passou a cobrar a MESMA contiguidade da rota T8.
- Desvios conscientes aceitos: `accept_server` não reescreve o Survey local
  (não existe `fromSurveyPacket`; reenvia o pacote do SERVIDOR com a resolução —
  registrado como oportunidade futura); justificativa de conflito por extenso
  fixa (prancha 6b não tem campo livre); autor do servidor exibido como
  "escritório" (a API não devolve autor); entrada do painel pela pílula
  "N pendentes" já aprovada (nenhuma superfície nova).
- Validação: field 210 verdes; `make check` e `make test` exit 0.
- Limitações conhecidas registradas: confirmação de mídia não persistida no
  aparelho (painel conservador mostra "0 de N" até ler o servidor); envio é
  sempre ato do técnico (sem gatilho automático ao voltar online — fácil de
  acrescentar); `keep_local` com `acked` local acima do head do servidor
  (cenário exige perda de dados do servidor) não reoferece essas operações —
  LOW, o fluxo de conflito reaparece e `accept_server` resolve.

## PLAN_DEVIATION

(nenhum até o momento)

## Decisões humanas pendentes

- ~~DAP rev.2 antes de T12/T15~~ — aprovada por Daniel Campos em 2026-08-21
  (com os ajustes de marca e endereço; T17 criada).
- Papel `field_technician` + path do app no realm Keycloak (teste real).
- Fornecedor de speech-to-text antes de T13 (envio de áudio a serviço externo).
- Decisão de merge/push da branch (inalterada).
