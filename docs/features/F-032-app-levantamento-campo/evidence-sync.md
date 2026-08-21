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

## PLAN_DEVIATION

(nenhum até o momento)

## Decisões humanas pendentes

- DAP rev.2 (voz, aviso de qualidade, estado de transcrição) antes de T12/T15.
- Papel `field_technician` + path do app no realm Keycloak (teste real).
- Fornecedor de speech-to-text antes de T13 (envio de áudio a serviço externo).
- Decisão de merge/push da branch (inalterada).
