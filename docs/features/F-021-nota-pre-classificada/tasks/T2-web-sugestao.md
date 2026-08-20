# T2 — Web: sugestão de anotação pré-preenchida na decisão

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core (pinado em
`docs/engineering-os/`), este contrato e o repositório — nada mais.

## Identity

```text
feature_id: F-021
task_id: T2
parent_plan: docs/features/F-021-nota-pre-classificada/plan.md
depends_on: []
```

## Goal

Leitura que o pipeline reconhece como recado chega à decisão com "Anotação da folha —
não mede um elemento" pré-selecionada e uma frase dizendo POR QUÊ. Dois sinais, duas
frases:

- `annotation_suggested === true` (campo novo do backend, T1):
  "sugestão: anotação da folha (o modelo leu como recado, não como cota)"
- padrão de elevação no `raw_text` (heurística client-side desta task):
  "sugestão: anotação da folha (o texto declara altura de elemento)"

O portão humano é invariante: nada é confirmado sozinho; justificativa continua
obrigatória; trocar a seleção manualmente vale mais que a sugestão.

## Baseline

ATENÇÃO: `apps/web/src/CroquiApp.tsx` tem mudanças NÃO COMMITADAS na árvore (rótulo e
abertura automática do painel de traçado, desta sessão). Elas são parte da baseline:
preserve-as, construa por cima, NUNCA as reverta. `git diff` antes de começar para
saber o que é seu e o que já estava lá. `npm --workspace @croquito/web run test`
verde (576 testes) e `make check` verde nessa árvore.

## Scope

Em `apps/web/src/api.ts`:

- `ReviewReading` (linhas 46-60) ganha `annotation_suggested?: boolean`.

Em `apps/web/src/labels.ts`:

- Função nova `suggestedAnnotationHint(reading): string | null`, no molde de
  `suggestedAxisHint` (linhas 275-292 — leia o padrão de comentário e siga):
  - `reading.annotation_suggested === true` → frase do modelo;
  - senão, `raw_text` casando padrão de elevação → frase do texto. Padrão: `h` (ou
    `H`) seguido de `=` com espaços opcionais (`h=`, `h =`, `H=`) em qualquer posição
    ("muro Vizinho h=3,80"), OU o texto começando com palavra de elemento vertical
    seguida de número puro é FORA de escopo (não adivinhe "mureta 1,54" — só o
    padrão `h=` é inequívoco; o resto fica para o sinal do modelo).
  - senão `null`.
- Exporte e teste em `apps/web/src/labels.test.ts` (padrão dos testes de
  `suggestedAxisHint`, linhas 504-559): com campo, com `h=`, com `H =`, sem nada
  (`25,90` → null), campo falso + `h=` no meio do texto → frase do texto.

Em `apps/web/src/CroquiApp.tsx`:

- No efeito de troca de leitura (o que hoje faz
  `setSelectedProposalId(firstCandidate?.proposal_id ?? "")` — em `loadReview`,
  linha ~1009, e no efeito de seleção ~1195-1210): quando a leitura selecionada NÃO
  tem decisão registrada e `suggestedAnnotationHint(reading) !== null`, a seleção
  inicial é `ANNOTATION_OPTION` (constante existente, linha 174) em vez do primeiro
  candidato.
- A frase da sugestão aparece junto ao select "Associação explícita" (bloco
  2869-2891), com a MESMA apresentação do `suggestedAxisHint` no campo de tipo
  (texto, sem cor como único indicador).
- Precedências (nesta ordem, e cubra com a leitura do código antes de mexer):
  1. Decisão registrada → nada muda (o painel registrado já é outro bloco).
  2. Rascunho da conversa (efeito do `chatPrefill`, declarado DEPOIS do reset de
     propósito — leia o comentário nas linhas ~1206-1211) → continua vencendo.
  3. Sugestão de anotação → pré-seleciona.
  4. Sem sugestão → primeiro candidato, como hoje.
- O payload de decisão NÃO muda: a pré-seleção de `ANNOTATION_OPTION` já produz
  `annotation: true` pelo caminho existente (linhas 1500-1520). Não toque no submit.

Em `docs/architecture/API_CONTRACT.md`: documente `annotation_suggested` no shape da
leitura do pacote (seção da rota de review; hoje só há exemplo com `"kind": "width"`,
linha ~257).

## Out of scope

- Etapa de traçado, `capture.ts` (que tem um `kind: "note"` de OUTRO conceito — não
  encoste), `chat.ts`, `trace.ts`.
- Backend (T1 corre em paralelo; o nome e a semântica do campo estão fixados no
  plano — não coordene com a outra task, obedeça ao plano).
- Auto-confirmar, auto-justificar, esconder candidatos.

## Acceptance criteria

1. `make check` verde (inclui tsc + vite build) e
   `npm --workspace @croquito/web run test` verde.
2. Testes novos de `suggestedAnnotationHint` cobrindo os cinco casos do Scope.
3. Leitura `h=3,80` sem campo novo nasce com ANNOTATION_OPTION selecionada (heurística
   funciona para pacote antigo SEM reprocessar) — demonstrado por teste de labels +
   inspeção do fluxo; leitura `25,90` nasce com o primeiro candidato, como hoje.
4. As mudanças pré-existentes não commitadas de CroquiApp.tsx permanecem intactas no
   diff final.

## Validation

```bash
make check
npm --workspace @croquito/web run test
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo do contrato do Builder, gravado em
docs/features/F-021-nota-pre-classificada/tasks/T2-build-report.md.
