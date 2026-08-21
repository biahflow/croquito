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

### T12 — nota de voz offline no app (prancha 7a)

- Executor: `implementador-opus`. BUILD REPORT: `BUILD_COMPLETE` + rodada de
  correção de contrato concluída pelo modelo principal (ver abaixo).
- Entrega: `apps/field/src/voice/` (recorder com matriz de codecs
  webm/opus→mp4/aac por `isTypeSupported`, mime REAL no `MediaRecord` — nunca
  `;codecs=`, nunca transcodifica; cancelar não grava nada; erros estruturados),
  `VoiceNoteScreen` (7a: abre gravando, âncora escrita, Parar/Cancelar, banner
  do destino da transcrição), domínio aditivo (`ObservationNote.audio_media_ref`;
  nota texto OU voz, vazia continua `EMPTY_TEXT`), áudio na categoria `audio` do
  SyncEngine (por último, ordem 6a) e resolvido no `toSurveyPacket`. Field: 236
  testes (era 210).
- **BLOCKER de integração achado pelo builder e resolvido na revisão**: o
  contrato canônico da T7 exigia `text` com `min_length=1` (escrito quando voz
  estava fora do MVP) — nota só-de-voz derrubaria o lote inteiro com 422. O
  builder PAROU corretamente (escopo proibia `packages/core`); a rodada de
  correção travou por permissão no harness do subagente e foi aplicada pelo
  modelo principal, dentro do escopo aprovado pela DAP rev.2: `ObservationNote`
  aceita `text` vazio COM `audio_media_ref` (validador espelha `EMPTY_TEXT`),
  contratos regenerados (`make contracts`), snapshot OpenAPI atualizado, 3
  testes novos em `tests/core/test_field.py`, dívida declarada removida do
  `contract.ts`.
- Decisões dentro da 7a aceitas: âncora em ponto quando houver (espelho da
  foto), no levantamento quando não houver — escrito na tela; tela abre já
  gravando (a prancha não tem botão iniciar); sem player nesta fatia (a 7a não
  o mostra — registrado como reserva).
- Validação: field 236 verdes; `tests/core` e `tests/api` completos verdes após
  a correção; `make check`/`make test` completos ficam para o fechamento da
  onda (T14 em execução paralela no worker). Riscos declarados: MediaRecorder
  real não exercitável em vitest — matriz de codecs precisa da passada em
  aparelho no piloto.

### T15 — checagem de qualidade de foto no aparelho (prancha 7b)

- Executor: `implementador-sonnet`. BUILD REPORT: `BUILD_COMPLETE`.
- Entrega: `photos/quality.ts` (puro: luma Rec.601 → Laplaciano 3×3 → variância;
  frações estourado/esmagado; veredito `ok|blurry|under|over` com prioridade
  blurry>over>under e `reasons[]` completo), `decodeReduced.ts` (lado maior
  ≤512px), `evaluateCapturedPhoto.ts` (falha de decodificação → `available:
  false`, nunca lança), `photoQualityGate.ts` (máquina pura; avaliação obsoleta
  descartada; "indisponível" = `clear`, sem fricção — não há evidência para
  avisar), `PhotoQualityCard` (7b com classes existentes, zero CSS novo),
  integração nas DUAS capturas (âncora e acesso; no acesso o caminho "ok"
  auto-persiste sem toque extra, preservando a UX da T4/T6). 19 testes novos
  (field 255); custo medido ~1ms em 512×384 (Node; folga de 2-3 ordens sobre o
  orçamento). Limiares nomeados como heurística a calibrar no piloto
  (BLUR_VARIANCE 1024; luma 250/8; frações 0,35).
- Achado do builder FORA do escopo dele, corretamente reportado: ruff/mypy
  reprovavam em `tests/core/test_field.py` — sujeira introduzida pelo MODELO
  PRINCIPAL na rodada de correção da T12 (import fora de ordem + helper
  `_media_ref` duplicado, sem rodar lint). Corrigida pelo modelo principal
  nesta revisão (helper existente reutilizado, import ordenado, ruff format);
  `pytest tests/core` verde. Lição registrada: edição direta do principal
  também passa pelos portões estáticos antes de commitar.
- Validação do builder: field 255 verdes; `make test` completo verde (pytest
  1876/13 skip, web 853); `make check` passo a passo verde exceto o achado
  acima (agora corrigido). `make check` oficial completo roda no fechamento da
  onda (T14 ainda em execução no worker).

### T14 — IA/CV pós-sync sobre fotos de campo (`analyze_survey_photo`)

- Executor: `implementador-opus`. BUILD REPORT: `BUILD_COMPLETE`.
- Entrega: `survey_photo_analysis.py` (passe offline sempre — Laplaciano,
  histograma, resolução, com limiares gravados no próprio artefato para
  recalibração; passe pago condicional com `PromptTask.FIELD_PHOTO_READING@1.0.0`
  — transcrever só o VISÍVEL, abster-se do ilegível, prompt em português com
  razão documentada), handler com dois portões na ordem de custo (flag/suíte →
  entitlement ATIVO do tenant; suíte injetada NÃO dispensa entitlement — foto é
  de cliente), artefato `analysis/{sha256}.json` idempotente, raw-store
  generalizado (`scope`/`scope_id`, chaves antigas idênticas), linha nova no
  `MODEL_ROUTING.md`. 21 testes novos (worker 960); zero chamadas reais de
  provider (contadas).
- Desvios conscientes ACEITOS: quinto estado `provider_pass: failed_permanent` +
  `provider_failure_code` (BUDGET_EXCEEDED/REFUSED/INVALid_SCHEMA não podem
  mandar reprocessar — mesma razão do `_handle_upload`); campos aditivos no
  artefato; portão sem consentimento por levantamento (a tabela de consents é
  por `job_id` e survey não tem job) — **decisão humana aberta registrada**:
  criar consentimento por levantamento (schema novo) ou aceitar entitlement por
  tenant como portão único do campo.
- Validação: `pytest tests/worker` 960 passed/1 skipped; `make check` exit 0
  (mypy strict 211 arquivos) e `make test` exit 0 sobre o HEAD com T12/T15 —
  portões oficiais completos da onda VERDES.
- Riscos declarados: prompt/limiares sem eval (rodada paga futura, aprovação por
  rodada); artefato sem consumidor no escritório (fatia futura); erro permanente
  não dá ack (mesmo comportamento do export).

### T17 — marca na barra, endereço na chegada, ícone PWA (ajustes da rev.2)

- Executor: `implementador-sonnet`. BUILD REPORT: `BUILD_COMPLETE`.
- Entrega: marca do croquito (`aria-hidden`) no AppBar de todas as telas;
  `Order` ganha `address`/`address_location` aditivos (fixture cobre os 3
  estados: com distância, sem distância calculável, legada sem endereço);
  `arrivalLocation.ts` puro (Haversine local, NUNCA geocodificação/rede,
  distância omitida sem os dois pontos, coordenada nunca impressa) substitui os
  3 estados de GPS da chegada; `icon.svg` + manifest + `theme-color` saem do
  placeholder azul para a marca real (#0e1116/#00e389). 6 testes novos (field
  261). `GpsFix`/domínio/outbox intocados.
- Desvios aceitos: `index.html` theme-color incluído (mesmo placeholder, mesmo
  motivo); item "ajustar testes de UI" resolvido pelo padrão do repo (lógica de
  texto extraída para função pura testada — não existe infra de render).
- Validação: field 261; `make check` e `make test` completos EXIT 0 (nenhuma
  reprovação da T13 paralela a reportar).

### T13 — transcrição de áudio (`transcribe_survey_audio`) + eval comparativa

- Executor: `implementador-opus`. BUILD REPORT: `BUILD_COMPLETE`.
- Entrega: `survey_transcription.py` (handler com os dois portões da T14;
  artefato `transcripts/{sha256}.json` schema `survey-transcript/1`, `status`
  SEMPRE `draft`, nota dona localizada no snapshot); adapters Groq + OpenAI de
  transcrição atrás de UMA interface (`ProviderName.GROQ`,
  `PromptTask.AUDIO_TRANSCRIPTION`, multipart, transporte injetado); roteamento
  por env (`CROQUITO_TRANSCRIPTION_PRIMARY=groq` default
  `whisper-large-v3-turbo`, `FALLBACK=none`); harness `make transcription-eval`
  (`transcription_eval.py` + subcomando CLI) com corpus sintético
  webm×mp4 e braços gravados — métricas na ordem de peso decidida pelo usuário:
  fidelidade de medidas ESCRITAS (string preservando precisão; "12,40"≠"12,4")
  → WER/CER pt-BR → por container; gate offline prova que as métricas
  discriminam (`passed=true`, `pending_paid_round=true`). 50 testes novos
  (worker 22+11+17); zero chamadas de rede em toda a entrega (contadas).
  `MODEL_ROUTING.md` (rota + protocolo PENDENTE DE RODADA PAGA) e
  `AI_VENDOR_RISK.md` (entrada Groq com termos a pinar) atualizados.
- Desvios conscientes ACEITOS: `duration_s` no transcript (metadado, não
  conteúdo); **fallback desligado por default** — ligar o segundo fornecedor
  pago por conta própria decidiria o que a eval existe para medir (promover é
  uma env); `ProviderPass` importado da T14 (vocabulário único, sem cópia);
  aviso extra `TRANSCRIPT_SNAPSHOT_UNREADABLE`.
- Validação: `pytest tests/worker` exit 0; `make check` exit 0 (mypy strict 213
  arquivos); `make test` exit 0 — **pytest 1931 passed/13 skipped**, web 853,
  field 261; `make transcription-eval` exit 0.
- Pendências humanas registradas: conta/chave Groq + termos pinados; 10-15
  clipes reais com verdade escrita; aprovação da rodada paga; promoção de
  primário/reserva pós-eval.

## PLAN_DEVIATION

(nenhum até o momento)

## Decisões humanas pendentes

- ~~DAP rev.2 antes de T12/T15~~ — aprovada por Daniel Campos em 2026-08-21
  (com os ajustes de marca e endereço; T17 criada).
- Papel `field_technician` + path do app no realm Keycloak (teste real).
- ~~Fornecedor de speech-to-text~~ — decidido por Daniel Campos em 2026-08-21:
  **Groq** (Whisper); T13 liberada. Pendente do usuário: conta/chave Groq antes
  de ligar em produção (testes usam fakes).
- Decisão de merge/push da branch (inalterada).
