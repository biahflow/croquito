# F-032 — Evidence (fatia 0)

Consolidação da execução da fatia 0 (T1 — scaffold do `apps/field`). Handoff de
revisão para o gate humano; não substitui os artefatos-fonte.

## Baseline

`make check && make test` na worktree `../croquito-f032`, branch
`f-032-app-levantamento-campo` (base `main@5148f80`, docs da F-032 já commitados em
`809aed4`), em 2026-08-21: **verdes** — ruff/format/mypy (203 arquivos), check_docs
(288 md), contratos sem drift, web build, pytest **1785 passed / 13 skipped**, vitest
web **853 passed**. Nenhuma falha preexistente conhecida.

## Execução — T1 (Builder: implementador-sonnet, harness Claude Code)

`PRIMARY_EXECUTION_EVIDENCE`: BUILD REPORT completo entregue pelo Builder em
2026-08-21 com `Status: BUILD_COMPLETE`; transcrito em resumo aqui, com atribuição
preservada — Builder implementador-sonnet, tarefa
[T1](tasks/T1-scaffold-apps-field.md):

- Files changed: `package.json` raiz (workspace + scripts `field:*`), `Makefile`
  (`field:check` no `check`, `field:test` no `test`), `package-lock.json`, e
  `apps/field/**` novo (package.json, tsconfig, vite.config com VitePWA+Tailwind,
  index.html, icon.svg, `src/domain/types.ts`, `src/storage/{SurveyRepository,
  DexieSurveyRepository}.ts` + testes, `src/outbox/{types,outbox}.ts` + testes,
  `src/ui/FieldShell.tsx`, `src/main.tsx`, `styles.css`, `testSetup.ts`, AGENTS.md).
- Validation executed (pelo Builder): `npm run field:check` (dist com `sw.js` e
  `manifest.webmanifest`), `npm run field:test` (9 testes novos), `make check` e
  `make test` completos, grep de pureza do domínio, `git status` dentro do escopo.
- Validation skipped: none. Unavailable capabilities: none.
- Assumptions relevantes: versões novas fixadas nas atuais do registry (dexie ^4.4.5,
  vite-plugin-pwa ^1.3.0, tailwindcss ^4.3.3, fake-indexeddb ^6.2.5); porta dev 5174;
  `FieldShell` usa survey fixo `survey-scaffold` (shell descartável).
- Remaining risks declarados: `FieldShell` sem teste automatizado de interação (padrão
  igual ao de `apps/web`); matriz de aparelhos/iOS fora desta fatia.
- Human decisions required: none. Nenhum commit pelo Builder (COMMIT forbidden).

## Revisão (modelo principal da sessão, linha a linha do diff)

- `REVIEW_FINDINGS` → corrigido na própria rodada, antes do commit:
  - **CODE_FINDING (HIGH)**: `FieldShell.recordOperation` calculava o próximo `seq`
    sobre `getPendingOperations` (que exclui `acked`) — depois de um ack a sequência
    regrediria e reutilizaria `seq` já emitidos, quebrando a semântica "crescente por
    device" de que a sincronização futura depende. Condição: qualquer ack seguido de
    nova operação. Correção: método `listOperations` (histórico completo, ordenado)
    na interface e na implementação Dexie; `FieldShell` calcula `nextSeq` sobre o
    histórico completo filtrado por `device_id`; teste de regressão novo em
    `outbox.test.ts` ("não regride depois de um ack").
- Demais achados: nenhum. Makefile/package.json mínimos; `.gitignore` já cobre
  `dist/` e `*.tsbuildinfo`; testes de storage com reabertura real do banco e
  inspeção interna no ack; AGENTS.md consistente com ADR-0043.

## Validação final (pós-correção, 2026-08-21)

- `npm run field:test`: **10 passed** (9 do Builder + 1 da correção).
- `npm run field:check`: verde, `dist/` com service worker e manifest.
- `make check`/`make test` completos: verdes na árvore final (a correção toca somente
  TypeScript de `apps/field`, invisível a ruff/mypy/pytest/check_docs; os perfis do
  app novo foram reexecutados sobre o código corrigido).

## Desvios de plano

- Renumeração F-031→F-032 / ADR-0042→ADR-0043 antes do congelamento do plano
  (colisão com `feat/f-031-value-events`), registrada em [plan.md](plan.md).

## Pendências e gates humanos

1. ~~Aceite do ADR-0043~~ — satisfeito por ato humano de Daniel Campos em 2026-08-21.
2. Design Approval Package antes do planejamento das fatias 2+ (`INTERFACE_CHANGE`).
3. Decisão de merge da branch `f-032-app-levantamento-campo` (merge na main dispara a
   esteira `deploy-hml`).
