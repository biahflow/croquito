# F-012 — Evidência de execução

feature_id: F-012

status: `DONE` (entrega aceita por ato humano em 2026-08-23)

data: 2026-08-23

## Round

```text
round: 1
reviewed_commit_or_state: main@5ae7a13 antes do fechamento documental
authorization: aceite explícito do ADR-0036 e da entrega pelo usuário em 2026-08-23
```

## 1. Contrato e plano

- [Feature Contract](feature.md)
- [Plano de execução](plan.md)
- Task Contracts e respectivos `BUILD REPORTS` em [tasks/](tasks/)
- [ADR-0036](../../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md), aceito
  por ato humano em 2026-08-23

## 2. Baseline

A F-009 havia ligado os providers reais, mas ativar um tenant dependia de `curl` com token
obtido no DevTools e cada documento exigia digest em variável de ambiente mais redeploy.
Esses dois rituais impediam a operação SaaS do fluxo.

## 3. Mudança

| Task | Entrega | Evidência primária |
| --- | --- | --- |
| T1 | Allowlist removida do worker hospedado; entitlement, consent, teto e kill switch viram o gate completo | [Build Report](tasks/T1-build-report.md) |
| T2 | `GET /v1/me`, listagem e leitura de entitlement de tenants, com autorização e contrato OpenAPI | [Build Report](tasks/T2-build-report.md) |
| T3 | Jornada Plataforma na SPA, com papel, ativação/revogação e `Idempotency-Key` | [Build Report](tasks/T3-build-report.md) |
| T4 | Runbook, FDD, roadmap e inventário SaaS reconciliados | [Build Report](tasks/T4-build-report.md) |

## 4. Validação e integração

- A implementação foi integrada na `main` pelo PR #20, merge `345fd2c`, depois do merge da
  F-009 (`8333956`).
- Os Build Reports registram `make check`, `make test`, snapshot OpenAPI e testes da API/SPA
  verdes: 403 sem `platform_operator`, tenant nunca ativado, ciclo ativar/revogar, round-trip
  de `?plataforma=` e `Idempotency-Key` nas mutações.
- O workflow hospedado não lê mais `CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS`; a variável segue
  apenas nos caminhos offline de eval.
- A infraestrutura e os providers foram exercitados no HML nas rodadas V12 e V14–V17. A
  jornada Plataforma permaneceu como superfície operacional e foi posteriormente ampliada
  pela F-034 sem substituir o contrato de autorização de IA entregue aqui.

## 5. Revisão e decisão humana

O pacote implementado, integrado e exercitado foi aceito pelo usuário em 2026-08-23. Na mesma
decisão, o ADR-0036 passou de `Proposed` para `Accepted` e a feature de
`READY_FOR_REVIEW` para `DONE`.

## 6. Fechamento documental

Em 2026-08-23, `scripts/check_docs.py` confirmou 385 documentos Markdown válidos e a paridade
de lifecycle. Depois de instalar as dependências que faltavam no ambiente local, `make check`
passou integralmente e `make test` concluiu com 2.378 testes Python aprovados (13 skips
condicionais), 1.075 testes da web e 261 testes do app de campo aprovados.

## 7. Desvios, riscos e pendências

- Sem allowlist hospedada, qualquer PDF de tenant com entitlement ativo pode sair para o
  provider; teto por invocação e kill switch permanecem as barreiras adicionais aceitas.
- A allowlist offline de `extraction_eval.py` permanece deliberadamente intacta.
- F-013 a F-017 continuam features próprias; este fechamento não altera seus estados.
