# Task Contract — F-032 / T8: backend `/v1/surveys` (tabelas, migração, rotas)

- Feature: F-032 — [feature.md](../feature.md)
- Plano pai: [plan-sync.md](../plan-sync.md) (tarefa T8)
- Depende de: T7 (contrato `SurveyPacket` em `croquito_core.field`, já integrado à
  branch quando esta tarefa iniciar).
- Baseline declarada: portões verdes na branch após o commit da T7 (registro em
  [evidence-sync.md](../evidence-sync.md)); nenhuma falha preexistente.

## Goal

Estender a `croquito_api` com a família `/v1/surveys`: persistência (tabelas +
migração aditiva), recepção idempotente de operações do outbox, presign/confirm de
mídia (foto e áudio) com digest, conclusão que enfileira o export, e o contrato de
conflito da prancha 6b. Nenhum handler de worker (T11/T13/T14 — planejados no mesmo
plano; publicar comando sem consumidor aqui NÃO é lacuna, é sequência declarada).

## Contexto verificado (ler antes de editar)

- `services/api/src/croquito_api/main.py` — rotas como closures em `create_app()`
  (~linha 2731). Padrões a espelhar EXATAMENTE:
  - Presign: `POST /v1/uploads/presign` (linhas ~3001-3068) — `PresignUploadRequest`
    (~254-258), `object_key` por tenant, `artifact_store.presign_upload`, auditoria.
  - Conferência de digest no consumo: `create_job` (~3070-3144) com
    `artifact_store.head_upload` e `checksum_deferred` para GCS (~3123-3139).
  - Idempotência: `_require_idempotency` (~2719-2728), `_request_hash`,
    `_idempotent_response`, `_store_idempotent_response` (~1540-1584); operação
    parametrizada por recurso (ex.: `f"review.decisions:{job_id}"`, ~3305).
  - Concorrência otimista + 409 estável: `POST /v1/jobs/{id}/review/decisions`
    (~3285-3470), incluindo `IntegrityError` → 409.
  - Papel: `_require_platform_operator` (~1910-1915) como modelo de checagem de
    papel dedicado.
- `services/api/src/croquito_api/database.py` — convenções: `tenant_id` indexado em
  toda tabela, ids `String(36)` UUIDv7, `DateTime(timezone=True)` UTC,
  `IdempotencyRecord` (~448-462), `ReviewRevisionRecord` com UniqueConstraint por
  versão.
- `services/api/src/croquito_api/migrations/versions/` — última migração da branch é
  a `0006`; conferir o `revision` id real dela para o `down_revision`. Padrão de
  migração aditiva com `server_default` documentado na própria `0006` (deploy
  rolante, expand/contract — `services/api/AGENTS.md`).
- `services/api/src/croquito_api/pubsub_queue.py` — um método `enqueue_*` por
  comando (~79-166); seguir o padrão para os comandos novos.
- `packages/core/src/croquito_core/field.py` — contrato `SurveyPacket` (T7): o
  snapshot recebido é validado por este modelo, nunca por schema manual.
- `services/api/src/croquito_api/auth.py` — `Principal.has_role`; test tokens
  `test:{tenant}:{subject}:{role1,role2}`.
- `tests/api/test_api.py` (~73-80) — app in-process com `TestClient`, `Database`
  SQLite, fakes de `tests/fakes.py` (`FakeObjectStore`, `FakeQueue` com
  `commands()`).
- `tests/api/openapi.snapshot.json` — regenerado por `make openapi-snapshot`.

## Comportamento exigido

### Persistência (migração `0007_surveys`, aditiva, forward-only)

1. `survey_records`: `id` (pk, uuid str), `tenant_id` (indexado), `name`,
   `order_ref` (nullable), `status` (`OPEN` | `COMPLETED`, default `OPEN`),
   `version` (int, default 1), `snapshot_json` (JSON — último `SurveyPacket`
   consolidado, sem `operations`), `created_at`, `updated_at`.
2. `survey_operation_records`: `id` = `operation_id` (pk — unicidade natural),
   `tenant_id` (indexado), `survey_id` (FK), `device_id`, `seq` (int), `type`,
   `payload_json` (JSON), `created_at`;
   `UniqueConstraint(survey_id, device_id, seq)`.
3. `survey_media_records`: `id` (pk), `tenant_id` (indexado), `survey_id` (FK),
   `sha256`, `mime_type`, `byte_size`, `object_key` (unique), `status`
   (`PRESIGNED` | `CONFIRMED`), `created_at`;
   `UniqueConstraint(survey_id, sha256)`.
4. Docstring da migração no padrão da `0006` (aditiva, rollback = ADR/aprovação
   humana, deploy rolante). `down_revision` aponta o id real da `0006` da branch. A
   colisão futura com a `0007` da F-029 (não commitada na main) está registrada no
   plano como etapa de integração — NÃO tentar resolvê-la aqui.

### Rotas (closures em `create_app`, problem+json com códigos estáveis)

Papel: constante `FIELD_TECHNICIAN_ROLE = "field_technician"`. Mutações exigem esse
papel; `GET` aceita também os papéis de revisão existentes (`engineer`,
`architect`, `domain_reviewer`) — o escritório lê o levantamento, não o edita.
`tenant_id` SEMPRE do JWT.

1. `POST /v1/surveys/{survey_id}/operations` — corpo:
   `{device_id, survey: <SurveyPacket sem operations>, operations: [SurveyOperation, ...]}`
   (modelos do request validam `survey` com `croquito_core.field.SurveyPacket`).
   `Idempotency-Key` obrigatório (operação `f"surveys.operations:{survey_id}"`).
   Semântica:
   - Cria `survey_records` na primeira chamada (criação idempotente).
   - `operations` deve ser contíguo por `(device_id, seq)`: o primeiro `seq` do
     lote = último `seq` armazenado do device + 1. Operação com `operation_id` já
     armazenado é ack idempotente (não regrava, não falha).
   - Lote válido: grava operações, substitui `snapshot_json`, incrementa
     `version`; resposta `{acked_operation_ids, version, last_seq_by_device}`.
   - Gap/regressão de seq, ou survey `COMPLETED`: 409 `SURVEY_CONFLICT` com
     `{server_version, last_seq_by_device, server_snapshot}` no detail — alimenta a
     tela de conflito (prancha 6b). Corrida de escrita: `IntegrityError` → 409.
   - Resolução de conflito é operação normal do outbox (`type:
     "conflict_resolution"` com justificativa no payload) — o servidor não decide
     nada sozinho; nada é apagado.
2. `GET /v1/surveys/{survey_id}` —
   `{survey: snapshot, version, status, last_seq_by_device, media:
   [{sha256, mime_type, status}]}`. 404 problem+json se não existir no tenant.
3. `POST /v1/surveys/{survey_id}/media/presign` — corpo `{sha256, mime_type,
   byte_size}`; `mime_type` permitido: `image/jpeg`, `image/png`, `image/webp`,
   `audio/webm`, `audio/mp4`; `Idempotency-Key` obrigatório. Regra da prancha 6a
   (metadados antes da mídia): o `sha256` precisa estar referenciado no
   `snapshot_json` corrente (âncora de mídia/nota) — senão 409
   `SURVEY_MEDIA_NOT_REFERENCED`. `object_key =
   tenants/{tenant_id}/surveys/{survey_id}/media/{sha256}`. Cria/atualiza
   `survey_media_records` (`PRESIGNED`) e devolve o padrão do presign existente.
4. `POST /v1/surveys/{survey_id}/media/{sha256}/confirm` — `head_upload` confere
   `byte_size` e, no flavor `s3`, o checksum (GCS: `checksum_deferred`, como no
   `create_job`); divergência → 409 `SURVEY_MEDIA_DIGEST_MISMATCH`. Marca
   `CONFIRMED` e enfileira: mime de imagem → `analyze_survey_photo`; mime de
   áudio → `transcribe_survey_audio` (handlers chegam em T13/T14; aqui só publica,
   padrão `enqueue_*` novo em `pubsub_queue.py`). Idempotente (confirmar duas
   vezes não duplica mensagem: só enfileira na transição PRESIGNED→CONFIRMED).
5. `POST /v1/surveys/{survey_id}/complete` — corpo `{base_version}`; exige toda
   mídia referenciada `CONFIRMED` (senão 409 `SURVEY_MEDIA_PENDING`), snapshot com
   status de conclusão presente; `base_version` divergente → 409
   `SURVEY_CONFLICT`. Marca `COMPLETED` e enfileira `export_survey` (handler em
   T11). Idempotente via `Idempotency-Key`.

### Auditoria e logs

- `_record_audit` nas mutações, como o presign existente.
- Logs sem coordenadas, sem nomes de arquivo de mídia, sem payload — IDs opacos,
  contagens e códigos apenas (convenção vigente).

### Testes (novo `tests/api/test_surveys.py`, padrão do pacote `tests`)

Cobrir no mínimo: criação idempotente + ack de lote; reenvio do mesmo lote (mesma
`Idempotency-Key` e mesmos `operation_id`s) sem duplicar; gap de seq → 409 com
`last_seq_by_device`; presign recusado para sha256 não referenciado (6a); confirm
com digest divergente → 409; confirm idempotente publica UMA mensagem; complete com
mídia pendente → 409; complete feliz publica `export_survey` (assert em
`FakeQueue.commands()`); papel errado → 403; tenant errado → 404; GET com papel de
revisão funciona. Snapshot OpenAPI regenerado (`make openapi-snapshot`) e commitado.

## Out of scope (não tocar)

- `services/worker/**` (handlers são T11/T13/T14), `apps/field/**`, `apps/web/**`,
  `packages/**` (o contrato da T7 é dependência, não escopo).
- Entitlement de IA (checagem fica no worker, padrão vigente).
- Resolver a colisão de numeração com a `0007` da F-029.
- Não "consertar" área alheia se um portão reprovar fora do escopo — parar e
  reportar.

## Validação (comandos reais, nesta ordem)

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
uv run pytest tests/api
make openapi-snapshot && git diff --stat tests/api/openapi.snapshot.json
make check
make test
```

## Gates nomeados

- COMMIT forbidden (revisão linha a linha e commit são do modelo principal).
- Migração é aditiva; qualquer coisa destrutiva exigiria aprovação humana — não há.
- Papel `field_technician` no realm Keycloak é ato humano futuro; testes usam
  test tokens.

## Report

Encerrar com o `BUILD REPORT` completo (todos os campos), incluindo a lista exata
de códigos de erro novos e os comandos de fila publicados.
