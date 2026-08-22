# Task Contract — F-032 / T9: SyncEngine + painel de sincronização (pranchas 6a/6b)

- Feature: F-032 — [feature.md](../feature.md)
- Plano pai: [plan-sync.md](../plan-sync.md) (tarefa T9)
- Depende de: T7 (contrato/mapeamento, `db203bf`) e T8 (rotas `/v1/surveys`,
  integrada quando esta tarefa iniciar). T10 (auth) fornece
  `getFreshAccessToken()`; se T10 já estiver integrada, consumir a interface real —
  senão, consumir uma interface `TokenProvider` injetada (mesma assinatura) e
  registrar no report.
- Superfície de design: prancha 6 do DAP rev.1 (`mock/README.md`, `06-sync.png`) —
  estados 6a (envio: metadados confirmados antes da mídia, progresso por categoria)
  e 6b (conflito campo × escritório com origem/autor/instrumento e decisão
  explícita). O contador "N pendentes" na AppBar já existe como superfície
  reservada. NÃO inventar superfície fora da prancha 6.
- Baseline declarada: portões verdes na branch (registro em
  [evidence-sync.md](../evidence-sync.md)).

## Goal

O transporte real do outbox: enviar operações em lotes idempotentes na ordem `seq`,
marcar `acked` só após resposta, subir mídia (foto/áudio) por presign + confirm com
progresso por categoria, apresentar e resolver conflito (6b) sem nunca apagar dado
local, e fechar a dívida de atomicidade `saveSurvey`+`appendOperation` com transação
Dexie. Isto AUTORIZA transporte de rede — somente dentro de `apps/field/src/sync/`.

## Contexto verificado (ler antes de editar)

- `apps/field/src/outbox/` — `types.ts` (`SurveyOperation.status:
  local|pending|acked`; comentário: `operation_id` casa com `Idempotency-Key`),
  `outbox.ts` (`acknowledgeOperation` idempotente), `applyCommand.ts` (comentário
  das linhas 46-48 sobre seq no histórico completo), `serialQueue.ts` (fila serial
  anti-corrida).
- `apps/field/src/storage/DexieSurveyRepository.ts` — Dexie v2; a transação
  atômica nova (survey+operação) é `db.transaction("rw", ...)` sobre as tabelas
  `surveys` e `operations`; migração de schema NÃO é necessária.
- `apps/field/src/sync/contract.ts` (T7) — `toSurveyPacket(survey, operations,
  mediaIndex)`, `MediaIndex` montado pelo chamador via `SurveyRepository.getMedia`,
  `isSurveyPacketShape` para a volta.
- Rotas e formas EXATAS da T8 (ver
  [T8-backend-v1-surveys.md](T8-backend-v1-surveys.md) e a implementação em
  `services/api/src/croquito_api/main.py` integrada):
  - `POST /v1/surveys/{survey_id}/operations` com
    `{device_id, survey, operations}`, header `Idempotency-Key` (id do lote) →
    `{acked_operation_ids, version, last_seq_by_device}`; 409 `SURVEY_CONFLICT`
    com `{server_version, last_seq_by_device, server_snapshot}`.
  - `POST .../media/presign` `{sha256, mime_type, byte_size}` → presign PUT;
    409 `SURVEY_MEDIA_NOT_REFERENCED` se a operação da âncora ainda não subiu (6a).
  - `POST .../media/{sha256}/confirm` → 409 `SURVEY_MEDIA_DIGEST_MISMATCH`.
  - `POST .../complete` `{base_version}` → 409 `SURVEY_MEDIA_PENDING` /
    `SURVEY_CONFLICT`.
  - Erros em `application/problem+json` com códigos estáveis.
- `apps/field/src/ui/` — shell, AppBar com contador reservado, viewModel.
- `apps/field/AGENTS.md` — regra a ATUALIZAR nesta tarefa: transporte de rede
  passa a ser autorizado exclusivamente em `apps/field/src/sync/`.
- Dívidas desta fatia (`evidence.md:135-137, 229-232`): transação atômica;
  `MediaRecord` órfão de foto de acesso abandonada (ver decisão abaixo).

## Comportamento exigido

1. `SyncEngine` (`apps/field/src/sync/engine.ts` + módulos auxiliares):
   - Estado por survey: operações `local` → lote → `pending` → resposta →
     `acked` (via `acknowledgeOperation`); NUNCA remove operação nem mídia local
     (ADR-0043 D2). Envio usa `serialQueue` (um sync por vez).
   - Lote = todas as operações não-acked em ordem `seq`; `Idempotency-Key` = id do
     lote (UUID v4 do navegador é aceitável aqui — id de transporte, não de
     domínio) reutilizado no retry do MESMO lote.
   - Retry com backoff exponencial + jitter (limites nomeados como constantes),
     apenas para falha de rede/5xx; 4xx não faz retry cego.
   - Depois do ack dos metadados: mídia por categoria (fotos ancoradas, foto do
     acesso, áudios — categorias da 6a), na ordem presign → PUT → confirm,
     com progresso observável (callback/estado) por categoria. Blob sai de
     `SurveyRepository.getMedia`; mídia órfã (não referenciada pelo survey) NÃO é
     enviada — continua local, registrada como pendência silenciosa não (mostrar
     contagem "não referenciadas" no painel é permitido pela prancha 6a se couber
     discretamente; caso contrário, apenas não enviar).
   - 409 `SURVEY_CONFLICT` → estado de conflito exposto ao painel com
     `server_snapshot`/`last_seq_by_device`; a decisão do técnico (manter local /
     aceitar servidor) vira operação `conflict_resolution` com justificativa no
     payload e reenvio; aceitar servidor NUNCA apaga dados locais — marca as
     operações locais preteridas como superseded localmente (campo novo de status
     local é permitido; migração Dexie se necessária, testada como a v1→v2).
   - `complete` só quando o survey está concluído no domínio e toda mídia
     confirmada; sucesso atualiza o painel.
   - Token: `getFreshAccessToken()`; `AUTH_REAUTH_REQUIRED` → sync para com
     estado "reautenticação necessária" (6c), coleta segue intocada.
2. Transação Dexie: `applyCommand` passa a gravar survey + operação numa transação
   `rw` única (fecha a dívida da revisão T3); teste prova que falha no meio não
   deixa survey sem operação.
3. Painel de sincronização real (prancha 6): estados 6a (progresso por categoria,
   metadados → mídia), 6b (conflito com origem/autor/instrumento e botões de
   decisão explícita com justificativa), integração do contador "N pendentes" da
   AppBar com o estado real do outbox. Texto em português; cor nunca é o único
   indicador; funciona offline (painel mostra "aguardando conexão").
4. Config: base URL da API via env Vite (`VITE_CROQUITO_API_BASE_URL`); sem env →
   painel exibe modo local (sem transporte), nada quebra.
5. Testes (vitest, com `fetch` fake — NENHUMA rede real): lote em ordem com
   `Idempotency-Key` estável no retry; ack marca operações; 409 abre estado de
   conflito e `conflict_resolution` reenvia; mídia segue metadados (6a) e respeita
   presign/confirm; digest mismatch aparece como erro acionável; token expirado
   para o envio sem tocar a coleta; transação atômica; painel deriva estados do
   engine (teste de viewModel, sem DOM real além do padrão dos testes existentes).

## Out of scope (não tocar)

- `services/**` (T8 já integrada; se a forma da API não bater com o contrato T8,
  PARE e reporte — não "adapte" o backend).
- Voz/captura (T12), qualidade de foto (T15), transcrição (T13).
- `apps/web/**`, `packages/**` (contrato T7 é dependência).
- Não implementar `deleteMedia`/limpeza de mídia órfã (decisão registrada: dado
  local nunca é apagado nesta fatia).

## Validação (comandos reais, nesta ordem)

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
npm --workspace @croquito/field run test -- --run
npm --workspace @croquito/field run check
make check
make test
```

## Gates nomeados

- COMMIT forbidden (revisão e commit são do modelo principal).
- Nenhum gate humano cruzado (o painel 6a/6b está coberto pelo DAP rev.1).

## Report

`BUILD REPORT` completo, incluindo: envs novas, decisões dentro da prancha 6,
qualquer campo/status local novo no Dexie (e a migração), e o que ficou para o
painel quando T12/T13 existirem (áudio/transcrição).
