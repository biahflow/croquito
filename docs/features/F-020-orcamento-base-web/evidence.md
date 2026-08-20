# F-020 — Evidência de execução

Consolidação no formato do template global (`docs/engineering-os/templates/evidence.md`).
Este documento REFERENCIA os Build Reports por task — ele não os substitui; cada
`tasks/T*-build-report.md` é `PRIMARY_EXECUTION_EVIDENCE` da sua task.

## Contexto

- Feature Contract: [feature.md](feature.md) (classificação `INTERFACE_CHANGE`).
- Design Approval Package: [mock/README.md](mock/README.md) — revisão 1 **aprovada por
  Daniel Campos em 2026-08-20**. Permanecem fora da aprovação: copy final e conferência
  contra o exemplar real da prefeitura.
- ADR: [ADR-0038 — BDI como conceito de pré-licitação](../../adr/0038-bdi-como-conceito-de-pre-licitacao.md),
  **Proposed** (aceite é gate humano pendente).
- Plano: [plan.md](plan.md) — congelado com T1–T5; T6 acrescentada por
  `PLAN_DEVIATION` registrado no próprio plano (o lado consumidor da fila não
  estava planejado).
- Execução: worktree isolado `croquito-f020`, branch `f-020-orcamento-web`, criada de
  `f802673`. Sessão paralela de traçado trabalhou na main durante toda a execução.

## Baseline

`make setup` + `make check` + `make test` verdes no worktree em `f802673`
(pytest 1643 passed / 13 skipped; vitest 581) antes de qualquer edição de código.
Nenhuma falha preexistente.

## Tasks e Build Reports

| Task | Contrato | Build Report | Status | Executor |
|---|---|---|---|---|
| T1 — domínio BDI + contrato gerado | [T1](tasks/T1-dominio-bdi-contrato.md) | [report](tasks/T1-build-report.md) | BUILD_COMPLETE | implementador-sonnet |
| T2 — escritor `.xlsx` + auditor | [T2](tasks/T2-escritor-auditor-estimate.md) | [report](tasks/T2-build-report.md) | BUILD_COMPLETE | implementador-sonnet |
| T3 — persistência + rotas `/v1` | [T3](tasks/T3-persistencia-rotas-v1.md) | [report](tasks/T3-build-report.md) | BUILD_COMPLETE | implementador-opus |
| T4 — jornada na SPA | [T4](tasks/T4-jornada-web.md) | [report](tasks/T4-build-report.md) | BUILD_COMPLETE | implementador-opus |
| T5 — e2e `/v1` sem CLI | [T5](tasks/T5-e2e-v1.md) | [report](tasks/T5-build-report.md) | BUILD_COMPLETE | implementador-sonnet |
| T6 — worker consome a fila | [T6](tasks/T6-worker-consumo.md) | [report](tasks/T6-build-report.md) | BUILD_COMPLETE | implementador-opus |

Cada task rodou os comandos da própria seção Validation com resultado verde; os números
por task estão nos Build Reports. Estado final integrado antes do rebase:
`make check` exit 0; pytest **1691 passed / 13 skipped**; vitest **683 passed**;
`make valuation-demo` e `make valuation-estimate-demo` verdes e determinísticos.

## Revisão (modelo principal da sessão)

- T1, T2, T3: revisão linha a linha do diff (dinheiro, contrato, API) — aprovados.
  Conferências manuais registradas na sessão: aritmética de truncamento do golden
  (160,4375→160,43; 35,93×1234,5→44355,58), teste que prova a ordem
  truncar-antes-de-somar, disciplina papel/idempotência/`base_version` nas 18 rotas,
  gate fail-closed dentro do request, `.xlsx` endereçado por conteúdo.
- T4, T5: spot-check + portões (route.ts/App.tsx compartilhados, invariantes do cliente
  HTTP, cobertura nomeada do e2e).
- T6: revisão do desenho `RoundChain` (colunas por cadeia conferidas contra
  `database.py`) + testes da medição intocados passando + 2 mutações detectadas.
- Achado da revisão que virou task: comandos de fila publicados sem consumidor → T6
  (`PLAN_DEVIATION` no plano). Correção aplicada pelo orquestrador: docstring defasada em
  `main.py` (apontada pelo Build Report de T6).

## Plan deviations

1. **T6 criada pós-congelamento** — registrada em [plan.md](plan.md), seção
   `plan_deviations`, com impacto e resolução.
2. Desvios conscientes por task (todos dentro de escopo autorizado ou parada correta)
   estão nos Build Reports; os de maior relevo: dois digests por fonte da cascata (T3),
   recusa nova `ESTIMATE_CASCADE_LOCKED` (T3), `test_canonical_golden.py` ajustado por
   consequência do golden autorizado (T1), `@import` de uma linha em `styles.css` (T4).

## Validação não exercida (declarada)

- Gate de drift do ADR-0029 (`tests/api/test_migrations.py::test_baseline_nao_diverge_dos_modelos`)
  exige PostgreSQL; o Docker local travou durante a tentativa (resíduo possível:
  container `croquito-f020-t3-pg`, limpar com `docker rm -f` quando o daemon voltar).
  **Fica para o CI.**
- Nenhuma execução contra API real hospedada (só in-process). O e2e T5 é a evidência da
  cadeia; fumaça em HML é ato de deploy.

## Riscos remanescentes

- Montagem renderiza e audita a planilha dentro do request path (tensão declarada com a
  fronteira de `services/api/AGENTS.md`; decisão do plano, documentada na rota).
- `.xlsx` órfão no bucket se o commit perder a corrida otimista depois do PUT — inerte
  por construção (chave derivada do digest; nada o referencia sem revisão).
- Copy da jornada é rascunho (gate humano aberto por declaração do pacote aprovado).
- Layout impresso ainda não conferido contra o exemplar real da prefeitura.

## Gates humanos pendentes

1. Aceite do [ADR-0038](../../adr/0038-bdi-como-conceito-de-pre-licitacao.md).
2. Copy final e conferência contra o exemplar real (declarados no pacote aprovado).
3. `.DBF` real da EMOP (assinatura GRE) — a jornada roda com fixture sintética até lá.
4. Merge na main (coordenado com a sessão de traçado) e deploy.
