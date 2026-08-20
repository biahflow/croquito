# F-026 — Evidência de execução

Consolidação no formato do template global. Este documento REFERENCIA os Build Reports
por task; cada `tasks/T*-build-report.md` é `PRIMARY_EXECUTION_EVIDENCE` da sua task.

## Contexto

- Feature Contract: [feature.md](feature.md) (`NO_INTERFACE_CHANGE` — sem design gate).
- ADR: [ADR-0039](../../adr/0039-sinapi-sicro-como-origens-de-preco.md), **Accepted por
  ato humano em 2026-08-20**.
- Plano: [plan.md](plan.md), congelado com T1→T2→T3 lineares.
- Execução: 2026-08-20, branch `f-026-importadores` (base: `especificacao-f025-f027`),
  worktree `croquito-specs`. Merge REPRESADO por decisão humana da mesma data.

## Baseline

Árvore da branch com `make check` e `make test` verdes antes de T1 (herdada do fim da
rodada F-020; reconfirmada pelo Builder de T1: pytest 1695/13, vitest 693→697 ao longo
das tasks).

## Tasks e Build Reports

| Task | Contrato | Build Report | Status | Executor |
|---|---|---|---|---|
| T1 — enum + bumps + labels + guardrail | [T1](tasks/T1-enum-contratos-labels.md) | [report](tasks/T1-build-report.md) | BUILD_COMPLETE | implementador-sonnet |
| T2 — importadores SINAPI/SICRO + CLI | [T2](tasks/T2-importadores.md) | [report](tasks/T2-build-report.md) | BUILD_COMPLETE | implementador-sonnet |
| T3 — cadeia e2e (/v1 e CLI) | [T3](tasks/T3-cadeia.md) | [report](tasks/T3-build-report.md) | BUILD_COMPLETE | implementador-sonnet |

Estado final integrado na branch: `make check` exit 0; pytest **1736 passed / 13
skipped**; vitest **697 passed**; `uv run pytest tests/e2e -q` 17 passed;
`make valuation-estimate-demo` determinística.

## Revisão (modelo principal da sessão)

- T1: linha a linha (bump de schema publicado) — enum + docstring, `Literal`
  acompanhando os dois bumps (`1.2.0`/`2.1.0`), golden restrito à `schema_version`,
  labels aditivos. Aprovado.
- T2: linha a linha no caminho do dinheiro — célula float/bool RECUSA a linha
  (`bool|float` antes do ramo `int`, ordem correta), preço viaja como texto na fixture
  (`format(price, "f")`), `Decimal` direto de string. Molde EMOP intocado. Aprovado.
- T3: spot-check — remoções são docstring/imports; asserções novas concretas
  (`price_origin`, código, digest do catálogo, célula `FONTE`). Aprovado.
- Incidente de processo (T1): o primeiro turno do Builder encerrou aguardando um
  monitor inexistente, sem BUILD REPORT; retomado por mensagem e concluído em
  foreground. Registrado aqui como contexto de execução, não como defeito de código.

## Plan deviations

Nenhum no nível do plano. Desvios conscientes por task (todos nos Build Reports):
família/subgrupo preenchidos com constante por fonte (layout de 4 colunas), "campo
ausente" como coluna fora da extensão real da planilha, cenário e2e aditivo em vez de
estender a fixture compartilhada.

## Decisão de dado registrada

Os leitores SINAPI/SICRO exigem preço como TEXTO na célula; célula numérica (float)
recusa a linha — coerente com `ExactDecimal` e com o fail-closed do ADR-0039. Arquivo
real com células numéricas vai recusar e forçar decisão explícita de layout quando
chegar (nunca conversão silenciosa de float binário de dinheiro).

## Riscos remanescentes

- Formato real dos arquivos oficiais pendente de dado (layout absorve; recusa mapeia).
- Selo visual das origens novas cai em `selo-neutro` por decisão declarada (cor nova
  exige design; texto do selo já nomeia a fonte).

## Gates humanos

1. Seleção (2026-08-20) — exercida. 2. ADR-0039 — **aceito em 2026-08-20**.
3. **Merge — represado por decisão humana de 2026-08-20; pendente.** Deploy segue a
   esteira da rodada após o merge.
