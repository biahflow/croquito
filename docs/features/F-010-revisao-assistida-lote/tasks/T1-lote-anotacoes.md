# T1 — Lote de confirmação das anotações sugeridas

Task Contract derivado do [plano](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-010
task_id: T1
parent_plan: docs/features/F-010-revisao-assistida-lote/plan.md
depends_on: []
```

## Goal

Na etapa de decisões, leituras sugeridas como anotação (F-021) chegam
pré-marcadas num painel de lote; uma justificativa do revisor, um clique,
N `HumanDecision` individuais gravadas com essa palavra pela rota EXISTENTE
(`POST /v1/jobs/{id}/review/decisions`, que já aceita 1..50 itens atômicos).
Nenhuma mudança em services/.

## Baseline

Main em 35bf5fa, árvore limpa, `make check` + 1645 pytest + 581 vitest verdes.

## Scope

### `apps/web/src/api.ts`

- `submitReviewDecision(accessToken, jobId, baseVersion, decision)` vira
  `submitReviewDecisions(accessToken, jobId, baseVersion, decisions: ReviewDecision[])`
  — mesmo endpoint, headers e envelope (`decisions` já é lista no body). Guard:
  lista vazia ou >50 lança erro local antes da rede (50 é o max_length do
  contrato do servidor). Atualize o único chamador individual para `[decision]`.

### `apps/web/src/readingBatch.ts` (novo, módulo puro)

- `suggestedAnnotationIds(readings: ReviewReading[]): string[]` — leitura sem
  `decision` e com `suggestedAnnotationHint(reading) !== null` (import de
  `./labels`). Ordem da lista de entrada preservada.
- `buildAnnotationBatch(readings, selectedIds: Set<string>, justification):
  ReviewDecision[]` — só ids presentes em `suggestedAnnotationIds` (seleção
  envenenada com id decidido/nao-sugerido é FILTRADA, não enviada); por item:
  `{reading_id, action: "confirm", annotation: true, justification: justification.trim()}`.
  Sem `association_proposal_id` (a API recusa anotação com associação —
  main.py:1941-1946).
- Docstrings no padrão do repo (português, dizendo o porquê): a justificativa
  única replicada por item é o espelho cliente do que o lote de propostas faz no
  servidor (main.py:3671-3674).

### `apps/web/src/readingBatch.test.ts` (novo)

Padrão dos testes puros vizinhos (vitest, node): sugerida sem decisão entra;
decidida não; sem sugestão não; lote replica justificativa com trim; seleção com
id inválido é filtrada; lote vazio permitido no builder (o guard de envio é da
UI/api). Teste do guard 1..50 de `submitReviewDecisions` se você o expuser
testável (função pura de validação exportada é aceitável).

### `apps/web/src/CroquiApp.tsx`

- Estados: `readingBatchIds: Set<string>`, `readingBatchJustification: string`.
- Pré-marcação: efeito que semeia `readingBatchIds` com
  `suggestedAnnotationIds(review.packet.readings)` UMA vez por `review.version`
  (ref no molde de `openedTraceStepRef`, ~linha 2337) — desmarcação do revisor
  não é sobrescrita no mesmo version; versão nova (pós-lote, pós-decisão) re-semeia
  com o que restou.
- Linha da lista (2763-2784): reestruturar em wrapper (`div.review-row-wrap`)
  com `<input type="checkbox">` à esquerda APENAS quando a leitura não tem
  decisão e tem sugestão; o `<button>` existente fica intacto ao lado (nunca
  aninhe interativo em interativo). Checkbox com
  `aria-label={"Incluir " + readingLabel(reading) + " no lote de anotações"}`.
  CSS mínimo em index.css se precisar (flex no wrapper); siga as classes e o
  visual das linhas atuais.
- Painel do lote: renderizado acima da `review-list` quando
  `suggestedAnnotationIds(...).length > 0`, `section` com aria-label, no padrão
  visual de `batch-controls` (3168-3253):
  - `<p aria-live="polite">N de M sugeridas selecionadas</p>`
  - botões "Selecionar todas" / "Limpar"
  - label "Justificativa do lote" (input; validação `justificationIssue` no
    envio, mensagem no padrão `setMessage`)
  - botão "Confirmar N como anotação" (`disabled` com submitting ou N=0):
    monta com `buildAnnotationBatch`, envia com `submitReviewDecisions`,
    sucesso → `setReview(next)`, limpa justificativa (a seleção re-semeia pelo
    efeito de versão), `setConflict(false)`, toast
    `"N leituras confirmadas como anotação — cada uma com a sua decisão gravada."`;
    erro → mesmo padrão do `submitBatch` (1782-1789): `setConflict` por
    REVISION_CONFLICT, `setMessage`.
  - hint fixo (texto, cor só reforço): "O lote confirma só as leituras
    sugeridas como anotação. Cota de chão se decide uma a uma: cada uma declara
    a sua associação e o seu eixo."
- NÃO tocar: formulário individual, chatPrefill, retificação, etapa de traçado,
  capture/trace/chat modules.

### `docs/product/FDD.md`

Parágrafo após o da F-021 (seção da decisão de leitura): o lote existe só para
as sugeridas; a justificativa é UMA, escrita pelo revisor, e vale para cada
decisão individual gravada; nada é confirmado sem o ato humano.

## Out of scope

services/**, labels.ts (além de import), lote de rejeição/cotas, auto-pass,
mudanças de contrato.

## Acceptance criteria

1. `make check` e `npm --workspace @croquito/web run test` verdes (todos os
   testes novos incluídos).
2. Payload por item idêntico ao da confirmação individual de anotação.
3. Conflito de revisão recarrega e preserva o rumo (a re-semeadura pós-versão
   cobre o reenvio).
4. Fluxo individual intocado (conferir por leitura do diff, não só testes).

## Validation

```bash
make check
npm --workspace @croquito/web run test
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT.

## Report

BUILD REPORT completo em tasks/T1-build-report.md E na resposta final.
