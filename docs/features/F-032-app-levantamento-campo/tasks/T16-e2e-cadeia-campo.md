# Task Contract — F-032 / T16: e2e in-process da cadeia de campo

- Feature: F-032 — [feature.md](../feature.md)
- Plano pai: [plan-sync.md](../plan-sync.md) (tarefa T16, última da fatia)
- Depende de: T7–T15 e T17, TODAS integradas (HEAD `b82d876`).
- Baseline declarada: `make check` e `make test` exit 0 em `b82d876`
  (pytest 1931/13 skip; web 853; field 261); `make transcription-eval` exit 0.

## Goal

Provar em UM teste de ponta a ponta, in-process e com fakes, a cadeia inteira da
fatia de sincronização: dispositivo (simulado) → `/v1/surveys` (operações
idempotentes, conflito 6b resolvido, mídia foto+áudio por presign/confirm,
complete) → fila → worker (`export_survey` + `analyze_survey_photo` +
`transcribe_survey_audio`) → artefatos de observação/análise/transcrição — com o
portão do scene graph segurando o export (fail-closed) e NENHUMA chamada de
rede/provider real.

## Contexto verificado (ler antes de editar)

- `tests/e2e/test_full_flow.py` — o padrão vigente de e2e in-process (como a API
  e o worker são montados juntos com `tests/fakes.py`).
- `tests/fakes.py` — `FakeObjectStore` (serve API e worker sobre o MESMO
  dicionário) e `FakeQueue` (`commands()`).
- `tests/api/test_surveys.py` — semântica exata das rotas (formas de request,
  idempotência, 409 `SURVEY_CONFLICT` com `last_seq_by_device`,
  `SURVEY_MEDIA_NOT_REFERENCED`, complete). Test tokens
  `test:{tenant}:{subject}:field_technician`.
- `packages/core/src/croquito_core/field.py` — montar o `SurveyPacket` do
  "dispositivo" em Python (pontos mm, segmentos, medida confirmada + draft,
  foto ancorada, nota SÓ-de-voz com `audio_media_ref`, contexto de chegada,
  status concluído com waiver, operações por device/seq).
- Handlers do worker: `survey_export.py` (+ `export_errors()` fail-closed),
  `survey_photo_analysis.py` e `survey_transcription.py` (portões: suíte
  injetada de transcrição/visão FAKE + entitlement ATIVO do tenant — ver como
  `tests/worker/test_survey_photo_analysis.py` e `test_survey_transcription.py`
  criam entitlement e injetam adapters contadores; reusar esses helpers ou
  extrair fábrica comum SEM duplicar).
- `local_queue.py` — `run_once`/dispatch consumindo as mensagens publicadas.

## Comportamento exigido (um fluxo, com asserções nomeadas)

`tests/e2e/test_field_flow.py` (novo), cobrindo em sequência:

1. **Lote 1** de operações (device A) cria o survey; ack completo; reenvio do
   MESMO lote (mesma Idempotency-Key) não duplica nada.
2. **Conflito e resolução**: lote com gap de seq → 409 `SURVEY_CONFLICT` com
   estado do servidor; reenvio reancorado com operação `conflict_resolution`
   fecha sem conflito (espelha o protocolo do app provado em
   `apps/field/src/sync/engine.test.ts`, agora contra a API REAL).
3. **Regra 6a**: presign de sha256 ainda não referenciado → 409; após o lote
   que referencia foto E áudio, presign + PUT (bytes no FakeObjectStore) +
   confirm dos dois; confirm publica `analyze_survey_photo` (foto) e
   `transcribe_survey_audio` (áudio) exatamente uma vez cada (reconfirmar não
   duplica).
4. **Complete**: recusado com mídia pendente (`SURVEY_MEDIA_PENDING` antes dos
   confirms — exercitar); aceito depois; publica `export_survey`.
5. **Worker consome as três mensagens** via `run_once` (suítes fake injetadas +
   entitlement ATIVO): artefatos existem nos object keys estáveis
   (`export/scene.json`, `export/attachments.json`, `analysis/{sha256}.json`,
   `transcripts/{sha256}.json`); a transcrição está `status: draft` com
   `note_id` da nota de voz; a análise tem `quality` e leituras do adapter
   fake.
6. **Fail-closed provado no e2e**: a cena exportada revalidada com
   `SceneRevision.model_validate` dá `export_errors()` não-vazio
   (`SCENE_NOT_APPROVED`), nenhuma entidade `exact`, nenhuma `export=True`.
7. **Sem entitlement** (segundo tenant no mesmo teste ou teste irmão): as
   mensagens de análise/transcrição processam com `provider_pass:
   skipped_no_entitlement` e ZERO chamadas nos adapters contadores; o export
   (que não é pago) funciona normalmente.
8. Contagem final: adapters contadores com o número exato de chamadas
   esperadas; nenhum `fetch`/rede real (garantido por construção — fakes).

## Out of scope (não tocar)

- `services/**`, `apps/**`, `packages/**` — NENHUMA mudança de produção; se o
  e2e expuser um defeito real, PARE e reporte (não conserte produção nesta
  tarefa).
- `tests/fakes.py`: extensão aditiva permitida só se indispensável; registrar.
- Consolidação do `evidence-sync.md` (fica com o modelo principal).

## Validação (comandos reais, nesta ordem)

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
uv run pytest tests/e2e -x
uv run pytest tests/e2e tests/api tests/worker
make check
make test
```

## Gates nomeados

- COMMIT forbidden. Nenhum gate humano cruzado.

## Report

`BUILD REPORT` completo, incluindo a lista das asserções-chave (1–8) com o
resultado de cada uma e as contagens finais dos adapters.
