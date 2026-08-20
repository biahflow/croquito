# T2 — Consultor na tela: causa em língua de obra, conserto de um clique, re-semeadura

Task Contract derivado do [plano](../plan.md). Autossuficiente. Depende de T1
(campos novos `unapplied_readings`, `contested_spans`, `applied_spans` em
`TraceSolveResponse`).

## Identity

```text
feature_id: F-025
task_id: T2
parent_plan: docs/features/F-025-consultor-do-tracado/plan.md
depends_on: [T1]
```

## Goal

Na etapa de traçado, cada leitura não aplicada aparece com a causa em língua de
obra + código cru, e as causas mecânicas oferecem conserto de um clique que
altera SÓ o rascunho do aceite (revisão humana antes de reenviar). Vãos em
disputa são nomeados par a par. Leituras aplicadas mostram as âncoras em
metros. O rascunho re-semeia o default de `freeform` quando decisões mudam —
nunca para forma cujo flag o revisor alterou à mão.

## Baseline

Branch `f-025-consultor-tracado` com T1 integrada; vitest 697/697 verde antes
de T2 (mais os que T1 tenha somado); `make check` verde.

## Scope

### `apps/web/src/api.ts`

Espelhar o contrato aditivo de T1 em `TraceSolveResponse` (hoje ~linha 268):

```ts
unapplied_readings?: { reading_id: string; cause: string; target_proposal_ids: string[] }[];
contested_spans?: { axis: "x" | "y"; reading_ids: string[]; values_m: number[]; proposal_ids: string[] }[];
applied_spans?: { reading_id: string; axis: "x" | "y"; value_m: number; start_m: number; end_m: number; proposal_id: string; second_proposal_id?: string | null; gap?: boolean }[];
```

Opcionais (`?`) porque respostas antigas persistidas não os têm.

### `apps/web/src/labels.ts`

No molde exato de `traceBlockerLabel` (linhas 434-493 — switch código→frase,
default devolve o cru):

- `traceUnappliedCauseLabel(cause, reading, proposals)` — frases em língua de
  obra para: `TRACE_TARGET_AS_DRAWN` ("a forma está aceita como desenhada;
  cota de elemento único não amarra em forma livre — trate a forma como
  retangular ou amarre a cota a um vão"), `TRACE_SPAN_AXIS_UNDECLARED`,
  `TRACE_SPAN_EDGE_NOT_FOUND`, `TRACE_SPAN_SAME_BAND`,
  `TRACE_SPAN_NOT_ORTHOGONAL`, `TRACE_NOTE_ZERO_LENGTH`,
  `TRACE_NOTE_UNSUPPORTED_GEOMETRY`, `TRACE_SPAN_VALUE_OR_DECISION_MISSING`.
  Cite a forma pelo nome/balão que o revisor reconhece (padrão das frases de
  `traceDraftIssues`, trace.ts:380-388).
- `traceAppliedAnchorsLabel(span)` — "19,75 amarra 42,85 m → 23,10 m" (valores
  com vírgula decimal, padrão pt-BR já usado nas labels).
- `traceContestedSpanLabel(contested, readings)` — "1,50 m e 8,60 m disputam o
  mesmo vão (eixo X)" com os textos crus das leituras.

### `apps/web/src/traceAdvisor.ts` (novo, módulo puro, sem DOM)

Produtor determinístico dos consertos — o espelho sem IA dos rascunhos do chat
(`applyDraftToTraceDraft`, chat.ts:304-396, é o precedente do gesto):

```ts
export type AdvisorFix =
  | { kind: "treat_rectangular"; proposalId: string }
  | { kind: "reassociate"; readingId: string; proposalId: string; label: string }
  | { kind: "declare_axis"; readingId: string }          // foca o controle existente
  | { kind: "keep_apart"; first: string; second: string }
  | { kind: "rectify"; readingId: string };              // abre o prefill de decisão
export type AdvisorFinding = {
  readingId?: string;
  message: string;      // via labels
  rawCode: string;      // código cru exibido em <code>
  fixes: AdvisorFix[];
};
export function adviseTrace(
  solve: TraceSolveResponse, review: Review, draft: TraceDraft,
): AdvisorFinding[];
```

Regras (todas conferidas contra o estado ATUAL — proteção do padrão
`readingBatch.ts:42-55`: id fora da revisão, leitura já decidida de outro modo
ou proposta fora do aceite não gera fix):

- `TRACE_TARGET_AS_DRAWN` → `treat_rectangular` para cada
  `target_proposal_ids` presente em `draft.freeform`.
- `TRACE_SPAN_EDGE_NOT_FOUND` / `TRACE_SPAN_SAME_BAND` /
  `TRACE_SPAN_NOT_ORTHOGONAL` → um `reassociate` por candidato alternativo de
  `review.associations.candidates` (filtro por `reading_id`, excluindo o alvo
  atual; máx. 3, ordem da lista — ela já vem ranqueada) + `rectify`.
- `TRACE_SPAN_AXIS_UNDECLARED` → `declare_axis`.
- Cada `contested_spans[i]` vira um finding próprio (sem `readingId` único):
  `reassociate`/`rectify` por leitura do par + `keep_apart` do par de
  `proposal_ids` quando há exatamente 2 (dedup contra
  `draft.keepApartPairs`, molde do chat.ts).
- Notas (`TRACE_NOTE_*`) → finding sem fix (diagnóstico honesto; o conserto é
  reposicionar a nota, controle que já existe).

### `apps/web/src/trace.ts`

- `TraceDraft` ganha `manualFreeformIds: Set<string>` (com `emptyTraceDraft`
  atualizado).
- `reseedProposalFlags(draft, context: ProposalFlagContext): TraceDraft` —
  recalcula `defaultFlagsForProposal` (linhas 327-345) para TODA forma de
  `draft.proposalIds` que NÃO está em `manualFreeformIds`, adicionando E
  removendo de `draft.freeform` conforme o default; formas em
  `manualFreeformIds` intocadas. Devolve o mesmo objeto se nada mudou (para
  não disparar render/persistência à toa).
- `withDefaultProposalFlags` continua como está (semente na entrada).

### `apps/web/src/traceStorage.ts`

- Serializar/restaurar `manualFreeformIds` (lista de strings). Rascunho antigo
  sem o campo carrega com conjunto vazio — sem erro (molde das funções
  `stringList`/tolerância já existentes).

### `apps/web/src/CroquiApp.tsx`

- `toggleTraceFlag` (linha ~1888): quando `field === "freeform"`, registrar o
  `proposalId` em `manualFreeformIds` (nunca remover — toque é para sempre na
  sessão).
- Re-semeadura: efeito disparado quando `review` muda de versão (molde dos
  efeitos guardados por ref, como a semeadura do lote F-010) aplicando
  `reseedProposalFlags` com o contexto atual (`readings`,
  `selected_associations`, `associations` do rascunho).
- Painel do consultor: a lista "Cotas não aplicadas ao traçado" (linhas
  4169-4190) passa a renderizar `adviseTrace(...)` quando o `traceSolve`
  corrente tem diagnóstico: frase + `<code>{rawCode}</code>` (padrão visual do
  `blocker-list`, linhas 4151-4168) + botões de conserto. Sem diagnóstico
  (resposta antiga), comportamento atual preservado.
- Aplicação dos fixes (nunca envia; toast existente "…revise antes de enviar",
  molde de `applyChatDraft` linhas 2258-2301):
  - `treat_rectangular` → remove de `freeform` E adiciona a
    `manualFreeformIds` (clique é ato humano);
  - `reassociate` → `associations[readingId] = proposalId` no rascunho;
  - `declare_axis` → abre/foca o controle de eixo existente da leitura
    (mesmo caminho de seleção de leitura já usado);
  - `keep_apart` → adiciona a `keepApartPairs` com dedup;
  - `rectify` → reusa o prefill de retificação existente
    (`rectificationPrefill`, uso nas linhas 1670-1680) e navega para a etapa
    de decisões (`openStep("decisions")`, molde do `applyChatDraft`).
- Âncoras: por leitura aplicada (`applied_spans`), frase de
  `traceAppliedAnchorsLabel` na seção `trace-status` (lista compacta, sem
  novo painel).

### Testes

- `apps/web/src/traceAdvisor.test.ts` (novo): um caso por causa; candidato
  alternativo excluí o alvo atual e respeita máx. 3; leitura decidida/id
  desconhecido não gera fix; contested com 2 propostas gera keep_apart e com
  1 não; dedup de keep_apart.
- `apps/web/src/trace.test.ts`: `reseedProposalFlags` — não tocado re-semeia
  nos dois sentidos (entra e sai de freeform); tocado nunca muda; retorno
  idêntico quando nada muda.
- `apps/web/src/traceStorage.test.ts`: ida e volta com `manualFreeformIds`;
  rascunho antigo sem o campo restaura com conjunto vazio.
- `apps/web/src/labels.test.ts`: frases das causas novas + âncoras + disputa;
  código desconhecido devolve cru.

### `docs/product/FDD.md`

Parágrafo do consultor na seção do traçado (causas, consertos de um clique,
âncoras, re-semeadura) — mesma altitude dos parágrafos da F-010.

## Out of Scope

- `services/**` (contrato vem pronto de T1), `chat.ts` (só ler como molde).
- Etiqueta "pendente" da lista de propostas do caminho de aproximação (F-011).
- Submeter qualquer conserto automaticamente; mudar o fluxo do botão
  "Aceitar traçado"; mexer no polling.
- Novo componente extraído de CroquiApp (padrão do arquivo é seção inline).

## Acceptance Criteria

1. `make check` e `npm --workspace @croquito/web run test` verdes.
2. Com resposta SEM os campos novos (job antigo), a tela se comporta como hoje.
3. Cada fix altera exclusivamente `traceDeclarations`/prefill local; o envio
   continua sendo o clique em "Aceitar traçado".
4. Flag tocado à mão nunca re-semeado; não tocado re-semeia quando a leitura é
   confirmada depois; storage antigo carrega sem erro.
5. Nenhuma cor como único indicador; códigos crus visíveis junto das frases.

## Validation

```bash
make check
npm --workspace @croquito/web run test
```

## Report

Responda com o `BUILD REPORT` completo do contrato do Builder. Se um portão
reprovar em área não tocada, pare e reporte.
