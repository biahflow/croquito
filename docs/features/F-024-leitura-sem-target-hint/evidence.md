# F-024 — Evidência de execução

## Baseline

Main em f802673 (Document AI no ar), árvore limpa. 1641 pytest + 581 vitest +
`make check` verdes. Diagnóstico da V16 medido no raw-store: 27 leituras extraídas,
12 cotas de chão descartadas por falta de `target_hint`, pacote com 8.

## Execução

| Task | Builder | Report (PRIMARY_EXECUTION_EVIDENCE) | Status |
|---|---|---|---|
| T1 funil | Claude Code / implementador-sonnet | [T1-build-report.md](tasks/T1-build-report.md) | BUILD_COMPLETE |

## Revisão (orquestrador, linha a linha)

Funil separado em dois testes na ordem certa (valor fatal antes, hint vira nota
depois); construção do `DimensionReading` condicional sem formatar hint ausente;
campo opcional no padrão já usado por `ReadingDecisionInput`; API tolera `None`
nos dois lados da retificação (`review.py:412`, `main.py:1996`). Nenhuma mudança
fora do escopo.

## Validação integrada (re-executada pelo orquestrador)

`make test` → 1645 pytest (4 novos) + 581 vitest; `make check` exit 0;
`make provider-contract-demo` verde; snapshot OpenAPI com diff só de nullable.

## Riscos remanescentes

- `transcription.py` (caminho de demo/CLI) mantém o descarte próprio por hint —
  desalinhamento consciente, anotado para alinhamento futuro.

## Decisões humanas pendentes

- Commit/push (deploy) e V17 como teste de aceitação real.
