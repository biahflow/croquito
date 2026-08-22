# Task Contract — F-032 / T7: contrato `SurveyPacket` gerado + mapeamento no app

- Feature: F-032 — [feature.md](../feature.md)
- Plano pai: [plan-sync.md](../plan-sync.md) (tarefa T7)
- Baseline declarada: branch `f-032-app-levantamento-campo`, HEAD `a086667`,
  `make check` e `make test` verdes em 2026-08-21 (registro em
  [evidence-sync.md](../evidence-sync.md)); nenhuma falha preexistente.

## Goal

Criar o contrato canônico do pacote de levantamento (`SurveyPacket`) no pipeline de
contratos gerados (Pydantic → JSON Schema → TypeScript) e o módulo único de
mapeamento domínio↔contrato em `apps/field`, fechando a incógnita registrada no
Feature Contract. Nenhum transporte, nenhuma rota, nenhuma UI.

## Contexto verificado (ler antes de editar)

- `apps/field/src/domain/types.ts` — modelo de domínio do app (fonte do espelho):
  `SurveyPoint` (x_mm/y_mm inteiros), `Segment`, `Measurement` (value_mm, 8 kinds,
  instrument, status draft/confirmed, justification), `PhotoAnchor`
  (`local_media_ref`), `ObservationNote`, `ElementObject`, `GpsFix`,
  `ArrivalContext` (`access_media_ref`), `SurveyStatus`/`Waiver`, `Survey`
  (unidade de persistência e sincronização), `CommandResult`.
- `apps/field/src/outbox/types.ts:8-21` — `SurveyOperation` (`operation_id`,
  `device_id`, `survey_id`, `seq`, `type`, `payload`, `status`, `created_at`).
- `apps/field/src/storage/SurveyRepository.ts:13-22` — `MediaRecord`
  (`id`, `sha256`, `mime_type`, `byte_size`, `blob`); o blob NUNCA entra no
  contrato — mídia viaja por referência (sha256/mime/byte_size).
- `packages/core/src/croquito_core/schema_export.py` — o registro modelo→schema é
  dado em `packages/contracts/contracts.manifest.json`, resolvido em runtime;
  **gate de camada**: `schema_export.py` não pode citar textualmente o pacote de
  medição — o modelo novo vive em `croquito_core`, então basta a entrada no
  manifesto, sem tocar em `schema_export.py`.
- `packages/contracts/contracts.manifest.json` — exemplos de entrada (SceneRevision,
  TakeoffPacket) com `module`, `model`, `version_attr`, `id`, `title`, `schema`,
  `typescript`.
- `packages/core/src/croquito_core/models.py` — convenções do repositório para
  modelos de contrato (`ContractModel`, enums, docstrings pt-BR, identificadores em
  inglês).
- `tests/core/test_schema_export.py` — vigia dos contratos gerados (padrão de teste
  a seguir para o modelo novo).

## Comportamento exigido

1. Módulo novo `packages/core/src/croquito_core/field.py` com
   `SURVEY_SCHEMA_VERSION = "1.0.0"` e modelos Pydantic (herdando o padrão de
   `ContractModel`) espelhando fielmente o domínio do app:
   - `SurveyPacket` raiz: identificação (`survey_id`, `tenant_hint` NÃO —
     tenant vem do JWT, não do pacote; `name`, `order_id`, `device_id`,
     `created_at`/`updated_at`), coleções `points`, `segments`, `measurements`,
     `media_anchors` (fotos E áudios — âncora carrega `media_ref` com
     `sha256`/`mime_type`/`byte_size` + vínculo opcional a ponto/elemento/nota),
     `elements`, `observations` (nota de texto com `audio_media_ref` opcional —
     preparação para T12), `gps_fixes`, `arrival_context`, `status`, `waivers`,
     e `operations: list[SurveyOperation]` (histórico do outbox).
   - Unidades: **mm inteiros** (`int`, com `ge`/limites sensatos), nunca float;
     `sha256` com pattern `^[a-f0-9]{64}$`; `seq >= 1`; timestamps UTC ISO.
   - `SurveyOperation` no contrato: `operation_id`, `device_id`, `survey_id`,
     `seq`, `type`, `payload` (dict), `created_at` (sem `status` — status é
     estado local do app, não viaja).
2. Entrada nova em `packages/contracts/contracts.manifest.json`:
   `module: croquito_core.field`, `model: SurveyPacket`,
   `version_attr: SURVEY_SCHEMA_VERSION`,
   `id: https://schemas.croquito.local/field/survey-packet/{version}.json`,
   `title: Croquito Survey Packet`, `schema: schemas/survey-packet.schema.json`,
   `typescript: src/survey-packet.generated.ts`. Gerados por `make contracts`,
   nunca editados à mão.
3. Módulo novo `apps/field/src/sync/contract.ts` (único lugar de mapeamento):
   funções puras `toSurveyPacket(survey, operations, mediaIndex)` e validação de
   forma na volta (types importados de `@croquito/contracts`
   `src/survey-packet.generated.ts`). Sem `fetch`, sem Dexie, sem UI — módulo puro.
4. Testes:
   - Python: validações do modelo (mm negativo rejeitado onde fizer sentido,
     sha256 malformado rejeitado, seq 0 rejeitado) + presença no manifesto,
     seguindo o padrão de `tests/core/test_schema_export.py`.
   - TypeScript (vitest em `apps/field`): round-trip de um survey representativo
     (pontos, segmentos, medidas confirmadas e draft, foto ancorada, nota,
     status concluído com waiver, operações) → `toSurveyPacket` produz objeto que
     satisfaz o tipo gerado e preserva todos os mm/sha256.

## Out of scope (não tocar)

- `services/**` (rotas, migração — T8), transporte de rede (T9), UI
  (`apps/field/src/ui/**`), worker, `apps/web/**`.
- Mudar semântica de `apps/field/src/domain/types.ts` (aditivo permitido só se
  indispensável ao mapeamento; registrar no report).
- Editar `scene.schema.json`, `*.generated.ts` ou qualquer gerado à mão.
- Não "consertar" área alheia se um portão reprovar fora do escopo — parar e
  reportar.

## Validação (comandos reais, nesta ordem)

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
make contracts        # gera schema + TS do SurveyPacket
uv run pytest tests/core
npm --workspace @croquito/field run test -- --run
make check            # inclui drift de contratos e check_docs (links!)
make test
```

## Gates nomeados

- COMMIT forbidden (revisão linha a linha e commit são do modelo principal).
- Nenhum gate humano é atravessado por esta tarefa.

## Report

Encerrar com o `BUILD REPORT` completo do contrato de Builder (todos os campos:
Status, Files changed, Validation executed, Validation skipped, Unavailable
capabilities, Assumptions, Remaining risks, Human decisions required).
