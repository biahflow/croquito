# F-013 — Ver e administrar quem tem acesso, sem abrir o Keycloak

## Status

`READY_FOR_SPEC`

> Nasce em 2026-08-19, no inventário SaaS da
> [F-012](../F-012-operacao-saas-autorizacao-ia/feature.md), e **ganha Feature Contract em
> 2026-09-05** por seleção humana. Ela ficou parada por depender do convite da
> [F-008](../F-008-ciclo-de-vida-de-conta/feature.md) — que **saiu de `BLOCKED` na mesma
> data**, quando a decisão de e-mail foi tomada.

## Classification

`INTERFACE_CHANGE` — tela nova de administração dentro do tenant. Exige Design Approval
Package antes do planejamento.

## Priority

A definir pelo dono. A recomendação é `MEDIUM`, **depois** da F-008 entregue: sem convite
funcionando, esta tela lista pessoas e não consegue acrescentar nenhuma — meia feature.

## Problem

Quem administra um escritório não sabe quem tem acesso ao próprio tenant. A lista de
pessoas existe **só no console do Keycloak**, que é ferramenta de operador de plataforma —
não de cliente. Hoje, "quem da minha equipe consegue entrar?" é pergunta que só nós
respondemos, e "tire o acesso de fulano, ele saiu" é chamado de suporte.

Isso é o mesmo padrão que a F-012 recusou para o entitlement (curl com token pescado do
DevTools) e que a F-014 recusa para o tenant (SQL para criar cliente): **ato de
administração que exige alguém de dentro da plataforma não é produto SaaS**.

## Desired Outcome

O `tenant_admin` vê quem tem acesso ao tenant dele, com que papel, convida alguém novo
(F-008) e revoga o acesso de quem saiu — sem que ninguém da plataforma participe.

## Scope

1. **Listar membros do tenant** com papel e estado, sob o papel `tenant_admin`.
2. **Convidar** — reusa o fluxo da F-008, sem inventar segundo caminho de criação de conta.
3. **Revogar acesso** de um membro, com o cuidado óbvio: um tenant não pode ficar sem
   nenhum `tenant_admin`.
4. **Tela** na jornada do produto (não na de Plataforma): quem usa é o cliente.

## Out of Scope

- Criar papéis novos ou editar permissões de papel: o conjunto de papéis é decisão de
  arquitetura, não de administração de tenant.
- Administrar tenants alheios — isso é a jornada de Plataforma (F-014).
- Autocadastro, recusado pelo ADR-0011.

## Acceptance Criteria

1. O `tenant_admin` vê **só** os membros do próprio tenant; um membro de outro tenant é
   indistinguível de inexistente.
2. Convidar dispara o fluxo da F-008 e o convidado aparece na lista como pendente.
3. Revogar o último `tenant_admin` é recusado por extenso — nunca deixa o tenant órfão.
4. Quem não é `tenant_admin` não vê a tela nem alcança as rotas.

## Unknowns

1. **Onde o vínculo usuário↔tenant vive** — é o unknown 2 da
   [F-014](../F-014-tenant-e-onboarding/feature.md), e a resposta dele decide se esta tela
   escreve no Keycloak, no produto, ou nos dois. **A F-014 precede esta feature.**
2. **Se o produto administra papéis do Keycloak ou só reflete**. Administrar exige
   credencial de administração do realm no servidor, o que é superfície de segurança nova.

## Human Gates

1. **Seleção e prioridade** — decisão do dono.
2. **F-008 entregue** e **F-014 com o unknown 2 respondido** — as duas precedem.
3. **Design Approval Package**.

## References

- [F-008](../F-008-ciclo-de-vida-de-conta/feature.md) — o convite, agora destravado.
- [F-014](../F-014-tenant-e-onboarding/feature.md) — o tenant como entidade.
- [ADR-0011](../../adr/0011-oidc-portable-identity.md) — identidade portável e o `tenant_id`
  no token.
