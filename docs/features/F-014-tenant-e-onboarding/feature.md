# F-014 — O tenant existe como entidade, e um cliente novo entra sem SQL

## Status

`READY_FOR_SPEC`

> Nasce em 2026-08-19, no inventário de gargalos SaaS que a
> [F-012](../F-012-operacao-saas-autorizacao-ia/feature.md) abriu, e **ganha Feature
> Contract em 2026-09-05** por seleção humana — escolhida como a primeira das cinco porque
> é a base que as outras pressupõem.
>
> Fica em `READY_FOR_SPEC` de propósito: a especificação achou uma decisão de arquitetura
> que precede tudo (unknown 1), e ela é ADR, não escolha de implementação.

## Classification

`INTERFACE_CHANGE` — cria superfície de administração de tenant na jornada de Plataforma.
Exige Design Approval Package antes do planejamento.

## Priority

A definir pelo dono. A recomendação é `HIGH` **se** houver cliente novo no horizonte, e
`MEDIUM` enquanto não houver: hoje o produto opera com os tenants que já existem, e o custo
da ausência só aparece quando alguém entra.

## Problem

### O tenant não existe como coisa

`tenant_id` é `string` em 36 colunas do banco e um atributo do usuário no Keycloak, levado
ao token pelo protocol mapper `tenant-id`. **Não existe tabela `tenants`.** As consequências
são todas do mesmo tipo — não há onde pendurar o que é do cliente:

- **nome do cliente não existe.** A tela mostra `tenant-local`, `tenant-a`: o identificador
  técnico, porque não há outro;
- **um cliente novo nasce por ato manual** no console do Keycloak, com alguém digitando o
  `tenant_id` certo no atributo do usuário. Errar a digitação cria um tenant fantasma que
  autentica e não vê nada — e ninguém percebe até o suporte;
- **não há inventário.** `GET /v1/platform/tenants` existe (F-012) e lista o que ela
  consegue: os tenants **que já apareceram** em alguma tabela de domínio. Tenant sem dado
  ainda é invisível;
- **nada tem dono declarado**: entitlement de IA (F-012), disponibilidade de jornada
  (F-034) e acervo autorado (F-042) já são por tenant, e todos referenciam uma string.

### Por que isso trava as outras

A [F-013](../F-013-ui-de-membros-do-tenant/feature.md) precisa de um lugar para listar
membros; a [F-017](../F-017-trilha-de-auditoria-do-entitlement/feature.md), de um lugar para
a trilha. As duas hoje penduram numa string.

## Desired Outcome

Tenant é entidade de primeira classe: tem id, nome, estado e histórico. Um cliente novo
entra por um ato administrado — com o `tenant_id` gerado, não digitado — e aparece na
lista antes de ter qualquer dado.

## Scope

1. **Tabela `tenants` e migração**, com id, nome de exibição, estado (ativo/suspenso) e
   proveniência (quem criou, quando).
2. **Rotas de plataforma** sob `platform_operator`, no molde das que a F-012 e a F-037 já
   estabeleceram: criar, listar, renomear, suspender.
3. **`GET /v1/platform/tenants` passa a ler a tabela**, não a inferir das tabelas de
   domínio — e o tenant recém-criado aparece imediatamente.
4. **Compatibilidade com o que existe**: nenhum `tenant_id` de dado atual muda. Os tenants
   de hoje entram na tabela como estão, pelo mesmo ato que os cria.
5. **Tela** na jornada de Plataforma, irmã da lista de entitlement.

## Out of Scope

- **Autocadastro**: recusado pelo ADR-0011 e pela decisão de 2026-08-18 (convite, não
  autocadastro). Cliente novo continua nascendo de ato administrado.
- Faturamento, plano ou limite de uso por tenant.
- Migrar `tenant_id` para chave estrangeira em 36 tabelas — ver unknown 1.

## Acceptance Criteria

1. Criar um tenant pela rota faz com que ele apareça na lista **antes** de ter qualquer
   dado de domínio.
2. Os tenants existentes continuam funcionando sem nenhuma alteração de dado.
3. O `tenant_id` é **gerado**, nunca digitado — e a criação devolve o valor que o operador
   precisa configurar no Keycloak.
4. Suspender um tenant impede sessão nova sem apagar nada.
5. Nenhuma rota de domínio muda de contrato.

## Unknowns

1. **Se `tenant_id` vira chave estrangeira.** Hoje é string livre em 36 colunas. Virar FK
   dá integridade referencial de verdade, mas é migração grande em tabelas com dado de
   cliente, e o ADR-0047 já estabeleceu que **acervo e índice não têm tenant** — a FK teria
   exceções. Manter string e ter a tabela ao lado é mais barato e mais fraco. **É decisão
   de arquitetura: exige ADR antes do planejamento.**
2. **Onde o vínculo usuário↔tenant vive** depois desta feature. Hoje é atributo do Keycloak.
   Mantê-lo lá é uma fonte de verdade fora do produto; trazê-lo para cá cria duas. A F-013
   depende desta resposta.

## Human Gates

1. **Seleção e prioridade** — decisão do dono.
2. **ADR do unknown 1** (FK ou string) — precede o planejamento.
3. **Design Approval Package**.

## References

- `services/api/src/croquito_api/database.py` — as 36 colunas `tenant_id` e a
  `TenantJourneyEntitlementRecord`, que já é por tenant.
- `services/api/src/croquito_api/main.py` — `_require_platform_operator` e as rotas de
  plataforma da F-012.
- [ADR-0011](../../adr/0011-oidc-portable-identity.md) e
  [ADR-0033](../../adr/0033-conta-por-convite-e-login-federado.md) — identidade e convite.
