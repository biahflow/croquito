# Task Contract — F-032 / T14: handler `analyze_survey_photo` (IA/CV sobre fotos de campo)

- Feature: F-032 — [feature.md](../feature.md)
- Plano pai: [plan-sync.md](../plan-sync.md) (tarefa T14)
- Depende de: T8 (`f7b3024` — publica `analyze_survey_photo` no confirm de mídia de
  imagem) e T11 (`370cfd7` — padrão de handler de survey no worker).
- Baseline declarada: portões verdes em `370cfd7` (evidence-sync.md). A T9 roda em
  paralelo tocando SOMENTE `apps/field/**` — sem interseção; reprovação de portão
  em área do field é dela: reporte, não conserte.

## Goal

Consumir `analyze_survey_photo` e produzir ANÁLISE da foto de campo em duas
camadas: (a) **passe offline sempre** (sem provider): métricas de qualidade
(nitidez por variância de Laplaciano, exposição por histograma — mesmas noções da
checagem no aparelho, T15) + metadados seguros; (b) **passe pago condicional**
(mesmo gate de entitlement/consent do pipeline): leitura por provider de visão
existente extraindo texto e medidas VISÍVEIS (placas, anotações a mão, visor de
trena) como leituras a revisar, com lineage completo. O resultado é artefato de
análise no storage do tenant — NUNCA muta o survey, NUNCA confirma nada.

## Contexto verificado (ler antes de editar)

- `services/worker/src/croquito_worker/survey_export.py` + o handler
  `_handle_survey_export` em `local_queue.py` (T11) — o padrão de handler de
  survey a seguir: leitura escopada por tenant (PKs compostas `(tenant_id, id)`),
  erro estruturado com código, log com stage/contagens/duração sem conteúdo,
  chave de artefato estável (idempotência por sobrescrita).
- Corpo da mensagem (T8): `{command: "analyze_survey_photo", survey_id, media_id,
  tenant_id}` — `media_id` é o id do `survey_media_records` (servidor), não o
  sha256; carregue o registro e valide status `CONFIRMED` + mime de imagem.
- `services/worker/src/croquito_worker/providers.py` — `PromptTask` (enum),
  `PromptSpec`/`_prompt_template`, modelos `ProviderContractModel` de saída com
  schema estrito, `ProviderAdapter`, `RetryingProviderAdapter`,
  `BudgetedProviderAdapter`, lineage (`ProviderExecution`), raw-store protegido.
  Siga o padrão EXATO de uma task existente (ex.: `MEASUREMENT_EXTRACTION`) para
  criar a task nova.
- Gate de entitlement/consent: `local_queue.py` ~800 (join
  `tenant_ai_processing_entitlements` + consent ATIVO) e
  `CROQUITO_REAL_PROVIDERS_ENABLED=false` por padrão — copie o mecanismo usado
  pelos handlers pagos existentes; SEM entitlement/flag o passe pago é PULADO
  com registro no artefato (`provider_pass: "skipped_no_entitlement"` etc.),
  nunca erro.
- `services/worker/src/croquito_worker/vision.py` — referência de DISCIPLINA de
  saída (proposta candidata, nunca confirmação). NÃO rode o detector de pranchas
  em foto de campo: linhas OpenCV de prancha não fazem sentido em foto de praça —
  o passe offline desta tarefa é qualidade/metadados, não geometria.
- Fotos: bytes em `tenants/{t}/surveys/{s}/media/{sha256}` (object storage);
  `tests/fakes.py` (`FakeObjectStore`) serve os bytes no teste.

## Comportamento exigido

1. Módulo novo `services/worker/src/croquito_worker/survey_photo_analysis.py` +
   registro no dispatch (`analyze_survey_photo`).
2. Passe offline (sempre): decodifica a imagem (OpenCV/numpy já disponíveis no
   worker), calcula nitidez (variância do Laplaciano), exposição (fração de
   pixels estourados/esmagados via histograma), dimensões; NENHUM conteúdo da
   imagem em log. Constantes de limiar nomeadas e documentadas como heurística
   (não regra de negócio).
3. Passe pago (condicional a flag + entitlement/consent, como os handlers pagos
   existentes): `PromptTask` nova (ex.: `FIELD_PHOTO_READING`) com saída estrita:
   lista de leituras `{raw_text, kind_hint?, value_hint?, unit_hint?,
   target_hint?, confidence}` + `notes` — SEM coordenada geométrica inventada;
   prompt em português instruindo a transcrever APENAS o que está visível
   (placa, anotação, visor de instrumento) e a abster-se quando ilegível.
   Provider de visão primário/fallback conforme o roteamento vigente; retry e
   budget pelos wrappers existentes; lineage gravado como nos demais; resposta
   bruta só no raw-store protegido.
4. Artefato: `tenants/{tenant_id}/surveys/{survey_id}/analysis/{sha256}.json`
   com `{schema: "survey-photo-analysis/1", media: {sha256, mime_type},
   quality: {...}, provider_pass: "done" | "skipped_disabled" |
   "skipped_no_entitlement" | "failed_transient", readings: [...], lineage:
   {...} | null}`. Reprocessar sobrescreve a mesma chave. Leituras são RASCUNHO
   a revisar — nada toca `survey_records`, nada vira medida, nada confirma.
5. Erros estruturados (código estável) para: mídia inexistente/de outro tenant,
   mídia não confirmada, mime não-imagem, bytes ausentes no storage, imagem
   indecodificável. Falha TRANSITÓRIA de provider não derruba o handler: o passe
   offline persiste e `provider_pass: "failed_transient"` fica registrado
   (retry natural virá de reprocessamento; documente).
6. Testes (`tests/worker/test_survey_photo_analysis.py`): passe offline com
   imagem sintética nítida × borrada × estourada (gerar via numpy, sem fixture
   binária de cliente); artefato completo e idempotente; entitlement ausente →
   `skipped_no_entitlement` sem chamada de provider (adapter fake conta
   chamadas); com adapter fake entitled → leituras no artefato + lineage; falha
   transitória → offline persiste; erros estruturados; consumo real por
   `run_once`; log sem conteúdo. NENHUMA chamada paga em teste.

## Out of scope (não tocar)

- `services/api/**`, `apps/**`, `packages/**`, transcrição (T13), export (T11 —
  não altere `survey_export.py`).
- Rodar detector de pranchas (`vision.py`) sobre foto de campo; gerar geometria.
- Mudança de schema de banco; consumo das análises no escritório (fatia futura).
- Não "consertar" área alheia se um portão reprovar fora do escopo (em especial
  `apps/field/**`, onde a T9 trabalha agora).

## Validação (comandos reais, nesta ordem)

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
uv run pytest tests/worker
make check
make test
```

## Gates nomeados

- COMMIT forbidden (revisão e commit são do modelo principal).
- Chamada paga em massa continua exigindo aprovação humana por rodada — esta
  tarefa não dispara nenhuma (providers desligados por padrão; testes com fakes).
- `docs/ai/MODEL_ROUTING.md`: acrescente a task nova à tabela de roteamento
  (visão primário/fallback), marcando que a calibração de prompt/limiar é
  trabalho de eval futuro.

## Report

`BUILD REPORT` completo, incluindo o nome final da `PromptTask`, o schema do
artefato de análise e a contagem de chamadas de provider nos testes (deve ser
zero fora dos fakes).
