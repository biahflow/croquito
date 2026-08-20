# F-010 fatia 1 — Evidência de execução

## Baseline

Main em 35bf5fa, árvore com a cerimônia F-010 não commitada. `make check` +
1645 pytest + 581 vitest verdes.

## Execução

| Task | Builder | Report (PRIMARY_EXECUTION_EVIDENCE) | Status |
|---|---|---|---|
| T1 lote | Claude Code / implementador-opus | [T1-build-report.md](tasks/T1-build-report.md) | BUILD_COMPLETE |

Desvios conscientes aceitos na revisão: CSS em `styles.css` (o `index.css` do
contrato não existe); span de mesma largura na linha não elegível (alinhamento);
guard 1..50 vive em `api.ts` como função pura testada. Ajuste do orquestrador na
revisão: plural do toast para lote de 1.

## Revisão (orquestrador, linha a linha)

`readingBatch.ts` filtra seleção envenenada contra as elegíveis; sem
`association_proposal_id`; justificativa aparada replicada por item.
Semeadura por `job:version` com ref — desmarcação do revisor não é sobrescrita;
interseção contra a marcação conta o que o botão promete. Checkbox irmão do
botão (nunca aninhado); painel no padrão `batch-controls` com aria-live.
Fluxo individual, chatPrefill e retificação intocados (conferido no diff).

## Validação integrada (re-executada pelo orquestrador)

`npm --workspace @croquito/web run test` → 591 (10 novos); `make check` exit 0;
pytest 1645 (inalterado — nada em services/).

## Riscos remanescentes

- Sem teste de DOM da linha reestruturada (padrão do repo é SSR sem revisão
  aberta); verificação por leitura de diff + build.
- Acima de 50 sugeridas o envio recusa com frase; nenhum fatiamento automático.

## Decisões humanas pendentes

- Commit/push (deploy) e aceitação real na revisão da V17.
