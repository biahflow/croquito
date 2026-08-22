# F-034 T3 — Administrar o entitlement por tenant e jornada

feature_id: F-034
task_id: T3
parent_plan: ../plan.md
role: builder
depends_on: T1

## Goal

Conceder e revogar, por ato nominal e auditável, o acesso de um tenant a uma jornada em
piloto — no molde exato da autorização de IA.

## Design aprovado

A tela **deve corresponder à revisão 1** do Design Approval Package, aprovada por ato humano
em 2026-08-22: [`../mock/README.md`](../mock/README.md) e
[`../mock/disponibilidade.html`](../mock/disponibilidade.html), com as capturas congeladas
dos seis estados. Divergir da revisão aprovada é revisão nova, com registro próprio — não é
decisão do builder.

## Scope

1. **Rotas** sob `/v1/platform/`, no molde de
   `/v1/platform/tenants/{tenant_id}/ai-processing-entitlement` (`main.py:2888-2925`):
   conceder e revogar o entitlement de (tenant, jornada), exigindo `platform_operator`,
   `Idempotency-Key`, e gravando referência de contrato, quem autorizou e quando. Revogar
   **não apaga** o registro: carimba `revoked_at`.
2. **Listagem** por tenant e jornada, no molde de `/v1/platform/tenants`.
3. **Recusa de jornada que não está em `pilot`**, com código estável: autorizar cliente em
   jornada `enabled` ou `disabled` não tem efeito, e o pacote aprovado mostra essa recusa
   com a frase por extenso.
4. **Tela** em `apps/web/src/plataforma/`: a seção nova abaixo da autorização de IA, com os
   estados normal, vazio, carregando, recusa e sem papel, conforme as capturas aprovadas.
   O estado de ambiente de cada jornada é **mostrado e não editável** — o pacote aprovado
   diz isso por escrito na própria tela.
5. **Snapshot de OpenAPI** regenerado (`make openapi-snapshot`).

## Out of scope

- Mudar o estado de uma jornada pela tela: é configuração de ambiente e publicação.
- O bloco **Histórico de autorizações**, desenhado no pacote como **reservado**, com traço
  tracejado: ele é a F-017 e não é construído aqui.
- Qualquer alteração na resolução de disponibilidade entregue pela T1.
- A copy final: a do mock é proposta, e o registro de aprovação diz explicitamente que texto
  não foi aprovado. Use a do mock e sinalize no relatório que segue pendente.

## Acceptance criteria

1. Conceder cria o registro com referência de contrato, autor e data; revogar carimba a
   data e mantém a linha na lista.
2. Conceder em jornada fora de `pilot` recusa com código estável, sem gravar nada.
3. Sem `platform_operator`: `403`, e a tela mostra o motivo por extenso, não tela em branco.
4. Tenant autorizado passa a ver a jornada; revogado deixa de ver — provado ponta a ponta
   contra `GET /v1/me`.
5. A tela corresponde à revisão 1 aprovada.
6. `make check`, `make test` e os portões da web verdes.

## Pitfalls

- `tenant_id` do JWT para quem chama; o tenant **alvo** vem da rota, e só
  `platform_operator` pode agir sobre outro tenant.
- Idempotência no molde do que já existe (`operation = f"platform.…:{tenant_id}"`).
- Nenhuma resposta bruta de banco ou detalhe interno volta ao cliente.

## Validation

```bash
make check
make test
npm --workspace @croquito/web run test
```
