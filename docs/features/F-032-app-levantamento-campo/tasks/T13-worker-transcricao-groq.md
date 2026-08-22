# Task Contract — F-032 / T13: transcrição de áudio no worker (Groq + braço OpenAI, eval comparativa)

- Feature: F-032 — [feature.md](../feature.md)
- Plano pai: [plan-sync.md](../plan-sync.md) (tarefa T13)
- Gates satisfeitos: DAP rev.2 aprovada (7c define o destino: rascunho, nunca
  substitui o áudio); **fornecedor decidido por ato humano em 2026-08-21: Groq**
  (registro no feature.md). Envio de áudio autorizado por essa decisão; chave
  real é ato do usuário — NENHUM teste chama a Groq.
- Depende de: T8 (`f7b3024` — publica `transcribe_survey_audio` no confirm de
  áudio), T12 (`0767810` — áudio existe no pacote), T14 (integrada — padrão de
  handler de análise a espelhar). Executa SEQUENCIAL a T14 (mesmos arquivos do
  worker).
- Baseline declarada: portões verdes no HEAD corrente (evidence-sync.md).

## Goal

Consumir `transcribe_survey_audio` e produzir a transcrição da nota de voz como
**rascunho** em artefato no storage do tenant — atrás do MESMO gate de
flag/entitlement/consent dos providers pagos, com retry/budget/lineage e resposta
bruta só no raw-store protegido. Nada muta o survey; nada é auto-confirmado; o
áudio original permanece a fonte.

## Contexto verificado (ler antes de editar)

- Corpo da mensagem (T8): `{command: "transcribe_survey_audio", survey_id,
  media_id, tenant_id}` — `media_id` = id de `survey_media_records`; exigir
  status `CONFIRMED` + mime `audio/webm` | `audio/mp4`.
- `services/worker/src/croquito_worker/survey_photo_analysis.py` + handler no
  `local_queue.py` (T14) — o padrão a espelhar: leitura escopada por tenant,
  artefato por sha256, `provider_pass` com estados
  `done|skipped_disabled|skipped_no_entitlement|failed_transient`, erros
  estruturados, log sem conteúdo, idempotência por chave estável.
- `services/worker/src/croquito_worker/providers.py` — `ProviderName` (novo:
  `GROQ`), `ProviderAdapter`, `RetryingProviderAdapter`,
  `BudgetedProviderAdapter`, lineage (`ProviderExecution`), raw-store. A API da
  Groq é compatível com o formato OpenAI (`/openai/v1/audio/transcriptions`,
  multipart com o arquivo + `model`) — espelhar a forma do adapter OpenAI
  existente, com endpoint/env próprios.
- Config: envs novas com prefixo `CROQUITO_` (ex.: `CROQUITO_GROQ_API_KEY`,
  `CROQUITO_GROQ_TRANSCRIPTION_MODEL` default `whisper-large-v3-turbo`) — seguir
  onde os demais providers leem env (worker settings). Sem chave → mesmo
  comportamento de provider desligado.
- Fluxo de áudio: bytes em `tenants/{t}/surveys/{s}/media/{sha256}`; o snapshot
  (`survey_records.snapshot_json`) localiza a nota dona do áudio
  (`observations[].audio_media_ref.sha256`) para gravar o vínculo no artefato.

## Comportamento exigido

1. Módulo novo `services/worker/src/croquito_worker/survey_transcription.py` +
   registro no dispatch (`transcribe_survey_audio`).
2. Adapters de transcrição atrás de UMA interface comum (decisão do usuário em
   2026-08-21: primário/fallback serão decididos por **eval comparativa**, não
   por palpite):
   - `ProviderName.GROQ` — modelos `whisper-large-v3` e `whisper-large-v3-turbo`
     (parametrizável); endpoint compatível com formato OpenAI.
   - Braço OpenAI de transcrição (fornecedor já aprovado no repo) — candidato a
     fallback, mesma interface.
   Saída estrita `{text, language?, duration_s?}`; `language` pedido como `pt`;
   SEM prompt de conteúdo (é transcrição, não geração). Retry só em falha
   transitória; budget contabilizado; lineage com provedor+modelo; resposta
   bruta no raw-store protegido, NUNCA em log. O roteamento primário/fallback é
   CONFIGURAÇÃO (env/routing), com default provisório Groq large-v3-turbo até a
   eval promover o vencedor.
2b. Harness de eval comparativa OFFLINE (`make transcription-eval`, padrão dos
   evals existentes): roda os braços sobre fixtures de áudio com
   transcrição-verdade e mede, nesta ordem de peso: fidelidade de números e
   medidas faladas (extração normalizada "12,40" etc.), WER/CER pt-BR, e o par
   webm/opus × mp4/aac. No CI/offline roda com adapters FAKE (prova o harness e
   as métricas com áudio sintético/registro de respostas); a RODADA PAGA
   comparativa é ato humano separado (chaves + fixtures gravadas pelo usuário —
   10-15 clipes Android/iPhone com verdade escrita — + aprovação de custo),
   com o resultado promovendo primário/fallback em `docs/ai/MODEL_ROUTING.md`
   (mesmo protocolo de promoção das evals anteriores).
3. Gate: mesmo mecanismo de flag global + entitlement/consent por tenant da
   T14. Sem gate → `provider_pass: "skipped_*"`, artefato ainda é gravado com
   os metadados (idempotente; reprocessar quando ligar).
4. Artefato: `tenants/{t}/surveys/{s}/transcripts/{sha256}.json` com
   `{schema: "survey-transcript/1", media: {sha256, mime_type}, note_id (da
   observação dona, se localizada no snapshot), provider_pass, transcript:
   {text, language, model} | null, lineage | null, status: "draft"}` —
   `status` é SEMPRE `draft`: confirmação é humana, em superfície futura
   (prancha 7c mostra só "em processamento"; o rascunho volta ao app/escritório
   em fatia posterior). Reprocessar sobrescreve a mesma chave.
5. Erros estruturados: mídia inexistente/outro tenant/não confirmada/mime não
   suportado/bytes ausentes; falha transitória do provider →
   `failed_transient` gravado, handler não explode.
6. Docs (obrigatório nesta tarefa): `docs/ai/MODEL_ROUTING.md` — linha da task
   de transcrição com os braços candidatos (Groq large-v3, Groq large-v3-turbo,
   OpenAI), o default provisório e o protocolo da eval que promove
   primário/fallback (marcado como PENDENTE DE RODADA PAGA);
   `docs/security/AI_VENDOR_RISK.md` — entrada da Groq (dado enviado: áudio de
   campo com possível PII falada; termos de retenção/treinamento pinados na
   data com a URL da política; mitigação: entitlement por tenant, flag global,
   budget, raw-store protegido).
7. Testes (`tests/worker/test_survey_transcription.py`, padrão T14): adapter
   fake conta chamadas (zero sem entitlement); fluxo feliz com fake → artefato
   completo com note_id e lineage; áudio órfão (sha256 sem nota no snapshot) →
   artefato sem note_id, com aviso estruturado; erros; idempotência; consumo
   real por `run_once`; log sem texto transcrito.

## Out of scope (não tocar)

- `services/api/**`, `apps/**`, `packages/**`; export (T11) e análise de fotos
  (T14) — não alterar os módulos deles além do dispatch compartilhado.
- Superfície do rascunho no app/escritório (fatia futura); confirmação da
  transcrição; diarização/tradução.
- Chamada real à Groq (sem chave em teste; NENHUMA rede real).

## Validação (comandos reais, nesta ordem)

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
uv run pytest tests/worker
make check
make test
```

## Gates nomeados

- COMMIT forbidden. Chamadas pagas em massa seguem exigindo aprovação por
  rodada. Conta/chave Groq = ato do usuário, fora desta tarefa.

## Report

`BUILD REPORT` completo, incluindo o nome do modelo default, as envs novas, o
schema do artefato e a contagem de chamadas de provider nos testes.
