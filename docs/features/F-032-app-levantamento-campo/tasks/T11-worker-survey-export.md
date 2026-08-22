# Task Contract — F-032 / T11: handler `export_survey` no worker (pacote → observações)

- Feature: F-032 — [feature.md](../feature.md)
- Plano pai: [plan-sync.md](../plan-sync.md) (tarefa T11)
- Depende de: T7 (contrato, `db203bf`) e T8 (rotas + tabelas + comando
  `export_survey` publicado no `complete`, integrada quando esta tarefa iniciar).
- Baseline declarada: portões verdes na branch (registro em
  [evidence-sync.md](../evidence-sync.md)).

## Goal

Consumir a mensagem `export_survey` e transformar o levantamento sincronizado em
**observações do pipeline**: um artefato `SceneRevision` (contrato canônico do
scene graph) com entidades `approximate`/`unresolved` e `Provenance` de campo,
persistido no object storage — provando com teste que os portões do scene graph
seguram o artefato (export CAD bloqueado). NENHUM `JobRecord`/`RevisionRecord` é
criado: a integração das observações na jornada do escritório é fatia futura
(decisão registrada no plano; relação com F-030).

## Contexto verificado (ler antes de editar)

- `services/worker/src/croquito_worker/local_queue.py` — `LocalQueueWorker.run_once`
  (~672), `dispatch` por `command` (~687), handlers existentes como referência de
  forma (`_handle_upload` ~759, `_handle_export` ~1041). Seguir o padrão de
  settings/fronteiras do worker (boto3/object store injetável — ver como os
  handlers atuais leem/escrevem objetos e tocam o banco).
- Tabelas da T8: `survey_records` (snapshot_json = `SurveyPacket` sem operations,
  status `COMPLETED` no export), `survey_operation_records`,
  `survey_media_records` (sha256/status). A mensagem `export_survey` publicada
  pela T8 carrega `survey_id` + `tenant_id` (conferir o corpo exato na
  implementação da T8 antes de escrever o handler).
- `packages/core/src/croquito_core/field.py` (T7) — `SurveyPacket` valida o
  snapshot lido do banco.
- `packages/core/src/croquito_core/models.py` — alvos do mapeamento:
  `Entity` (~178: kind/layer/precision/geometry/provenance/export),
  `Provenance` (~172: source_type, source_ids, summary_code `^[A-Z0-9_]{3,64}$`),
  `Measurement` (~205: value_si Decimal, confirmed exige valor+provenance),
  `Issue`, `SceneRevision` (~263: job_id UUID, approved=False default,
  export_errors()). Enums em ~31-95 (Precision, EntityKind, LayerName,
  MeasurementKind, UnitCode).
- `services/worker/src/croquito_worker/tracing.py` — convenção de eixo do
  pipeline ("cota manda", **Y espelhado**): o levantamento usa coordenadas de
  tela (y cresce para baixo); a cena métrica espelha Y. Seguir a MESMA convenção
  e documentar no módulo.
- `tests/worker/` + `tests/fakes.py` — padrão de teste dos handlers
  (FakeObjectStore/FakeQueue compartilhados, banco SQLite in-process).

## Comportamento exigido

1. Módulo novo `services/worker/src/croquito_worker/survey_export.py` + registro
   no `dispatch` do `local_queue.py` (`command: export_survey`, mesmo formato dos
   demais).
2. Fluxo do handler:
   - Carrega `survey_records` do tenant/survey da mensagem; valida
     `snapshot_json` com `SurveyPacket` (Pydantic) — snapshot inválido é erro
     estruturado, não silêncio.
   - Exige status `COMPLETED` e toda mídia referenciada `CONFIRMED`; caso
     contrário, erro estruturado (a API só enfileira depois disso — a checagem é
     defesa em profundidade).
   - Monta uma `SceneRevision` de observações:
     - `job_id` = UUID do survey (namespace de cena de campo — artefato apenas;
       documentar no módulo que NÃO existe `JobRecord` correspondente).
     - Pontos/segmentos → entidades `line`/`polyline` na layer apropriada,
       coordenadas mm→m (float na geometria), **Y espelhado**;
       `precision=approximate` quando coberto por medida confirmada em campo,
       `unresolved` caso contrário; `export=False` em TODAS (observações);
       `Provenance(source_type="field_survey", source_ids=[survey_id, device_id,
       operation_id da origem quando houver], summary_code="FIELD_SURVEY")`.
     - Medidas do levantamento → `Measurement` do scene graph: `value_si` =
       Decimal(mm)/1000 (nunca float→Decimal por str de float binário — usar
       `Decimal(value_mm) / Decimal(1000)`), `unit` metro (ângulo: usar o kind
       correspondente se existir no enum; senão registrar como Issue INFO e
       preservar no raw_text), `raw_text` com o valor de campo, `confirmed=True`
       APENAS para medida confirmada pelo técnico (com provenance
       `summary_code="FIELD_CONFIRMED"`); draft → `confirmed=False`.
     - Fotos/áudios ancorados e notas → `Issue`/metadados informativos NÃO;
       eles não viram entidade: viajam no artefato de anexos (ver 3) — a cena só
       carrega geometria/medida/issue. Waivers de conclusão → `Issue` com
       severity não crítica, status OPEN, code do achado (`^[A-Z0-9_]`).
     - Dimensão EXATA nunca nasce aqui (Precision.EXACT proibido no módulo).
   - Persiste no object storage do worker:
     `tenants/{tenant_id}/surveys/{survey_id}/export/scene.json` (a
     `SceneRevision` serializada pelo contrato) e
     `.../export/attachments.json` (índice: âncoras de mídia com sha256/mime,
     notas, contexto de chegada, GPS — o que não é geometria). Reprocessar a
     mesma mensagem sobrescreve os mesmos keys (idempotência por chave estável).
   - Log no padrão do worker: IDs opacos, stage, contagens, duração — sem
     coordenadas, sem nomes, sem texto de nota.
3. Fail-closed provado: teste que chama `export_errors()` na cena produzida e
   afirma que ela NÃO é exportável (SCENE_NOT_APPROVED + approximate sem aceite),
   e que `survey_export` nunca marca `approved=True` nem `export=True`.
4. Testes (`tests/worker/test_survey_export.py`, padrão do pacote): fluxo feliz
   (fixture sintética de snapshot com pontos/segmentos/medidas
   confirmada+draft/waiver/foto) valida artefatos gravados e formas; snapshot
   inválido → erro estruturado; survey não-COMPLETED → erro; mídia PRESIGNED →
   erro; idempotência (reprocessar não duplica); mapeamento mm→m e Y espelhado
   com valores exatos; `Decimal` sem contaminação de float.

## Out of scope (não tocar)

- `services/api/**` (T8), `apps/**`, transcrição (T13), análise de fotos (T14).
- Criar `JobRecord`/`RevisionRecord`/migração — NENHUMA mudança de schema de
  banco nesta tarefa.
- Renderização/DXF (o artefato é observação, não prancha).
- Não "consertar" área alheia se um portão reprovar fora do escopo.

## Validação (comandos reais, nesta ordem)

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
uv run pytest tests/worker
make check
make test
```

## Gates nomeados

- COMMIT forbidden (revisão e commit são do modelo principal).
- A decisão "artefato sem JobRecord; integração no escritório é fatia futura"
  está registrada no plano — se durante a execução parecer necessário criar
  Job/Revision, PARE e reporte (decisão humana/arquitetural).

## Report

`BUILD REPORT` completo, incluindo o corpo exato da mensagem consumida, os object
keys gravados e o resultado de `export_errors()` na cena de exemplo.
