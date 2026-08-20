# T1 — BUILD REPORT

Evidência primária de execução da task T1 do [plano](../plan.md), contra o
[Task Contract](T1-lote-anotacoes.md).

## Baseline

`main` em `35bf5fa`, árvore com uma única modificação preexistente e alheia a esta task
(`docs/product/ROADMAP.md`, do orquestrador). Baseline de validação declarado no
contrato e reconfirmado ao final: `make check` verde, 1645 pytest (10 skipped), 581
vitest.

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - apps/web/src/api.ts — `submitReviewDecision` vira `submitReviewDecisions` (lista,
    mesmo endpoint/envelope) + guard local 1..50 exposto como função pura
    (`reviewDecisionBatchIssue`, `REVIEW_DECISION_BATCH_MAX`).
  - apps/web/src/readingBatch.ts (novo) — módulo puro: elegibilidade ao lote
    (`suggestedAnnotationIds`) e montagem das decisões individuais
    (`buildAnnotationBatch`), com filtragem de seleção envenenada.
  - apps/web/src/readingBatch.test.ts (novo) — 10 testes do módulo puro e do guard.
  - apps/web/src/CroquiApp.tsx — estados do lote, semeadura por job+versão, linha da
    lista reestruturada com checkbox irmão do botão, painel do lote acima da
    `review-list`, `submitAnnotationBatch`; chamador individual passa `[decision]`.
  - apps/web/src/styles.css — `.review-row-wrap` / `.review-row-check` (flex + vão
    reservado). Contrato citava `index.css`; o arquivo não existe neste repo.
  - docs/product/FDD.md — parágrafo do lote logo após o da F-021.

Validation executed:
  - `make check` — ruff check/format (387 arquivos), mypy strict (187 fontes, 0 erro),
    check_docs (223 Markdown, paridade de lifecycle), schema_export --check,
    contracts:check, `tsc -b && vite build` (67 módulos, build ok), terraform fmt.
    Resultado: PASS.
  - `npm --workspace @croquito/web run test` — 33 arquivos, 591 testes, PASS
    (581 do baseline + 10 novos).
  - `make test` — 1645 pytest passed, 10 skipped (idêntico ao baseline) + 591 vitest.
    Resultado: PASS.

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - `ReviewReading["decision"]` ausente/nulo é o critério de "ainda não decidida" usado
    pela elegibilidade, como o contrato determina; status textual não é consultado.
  - O contrato do servidor foi conferido em leitura (não alterado):
    `SubmitReviewDecisionsRequest` aceita 1..50 decisões atômicas
    (`services/api/src/croquito_api/main.py`), e confirmação com `annotation=true` mais
    `association_proposal_id` é recusada — por isso o lote nunca envia associação.

Remaining risks:
  - Sem teste de DOM: a estrutura da linha (checkbox irmão do botão, nunca aninhado) e o
    painel foram verificados por leitura do diff e pelo build, não por render em jsdom —
    o repositório não tem jsdom e o padrão vizinho é SSR estático sem revisão aberta.
  - Lote acima de 50 sugeridas numa mesma folha depende do revisor dividir o envio: o
    guard explica o limite em texto, mas nenhum botão fatia o lote automaticamente.

Human decisions required:
  - Nenhuma para concluir a task. A aceitação real na revisão da V17 continua sendo o
    gate humano da feature, e nada foi commitado (COMMIT não concedido).
```

## Desvios conscientes do contrato

1. **`index.css` → `styles.css`.** O contrato previa CSS mínimo em
   `apps/web/src/index.css`; esse arquivo não existe. A folha da jornada é
   `apps/web/src/styles.css`, onde `.review-row` já morava, e foi lá que as duas regras
   novas entraram.
2. **Vão reservado na linha sem sugestão.** O contrato pede o checkbox apenas na leitura
   elegível. Implementado assim; para o texto das leituras não desalinhar em duas
   colunas, a linha não elegível ganha um `<span aria-hidden>` da mesma largura — puro
   espaçamento, sem papel, sem foco e invisível ao leitor de tela.
3. **Guard 1..50 mora em `api.ts`, testado em `readingBatch.test.ts`.** O contrato
   autoriza expor função pura de validação; ela ficou ao lado do transporte que a usa, e
   o teste ficou junto do resto do lote em vez de criar um segundo arquivo.

## Fora de escopo — visto e não implementado

- Não há teste que prove, no DOM, que o checkbox é irmão do botão. Um `MedicaoApp`-style
  SSR com revisão sintética cobriria isso, mas exigiria uma fixture de `Review` inteira,
  fora do escopo desta task.
- O painel de lote não oferece rejeição em lote nem lote de cotas — deliberadamente fora
  de escopo pelo contrato.
- `review.packet.readings` é varrido três vezes por render (candidatos, conjunto,
  interseção). Irrelevante na ordem de grandeza atual; não foi otimizado para não mexer
  em área alheia.
