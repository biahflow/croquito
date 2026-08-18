# Deploy e rollback

Status: Accepted baseline  
Responsável: Platform / Engineering  
Última revisão: 2026-08-17

## Ambientes

- Local: providers stubados por padrão.
- Staging: dados sintéticos/golden autorizados, recursos isolados.
- Production: acesso por convite, secrets e storage próprios.

## Artefatos

- Imagens de API e worker versionadas por commit digest.
- Front-end bundle imutável.
- Terraform plan revisado.
- Prompt/model routing versionado separadamente, mas ligado ao release.
- Migrações numeradas e compatíveis com rolling deploy quando possível. O runner é o
  Alembic ([ADR-0029](../adr/0029-runner-de-migrations-revisadas.md)), com as revisões
  dentro do pacote `croquito_api` e distribuídas na mesma imagem da API.

## Processo

1. CI passa lint, types, tests e policy checks — inclusive o gate de drift, que aplica as
   migrations em PostgreSQL limpo e reprova modelo alterado sem a migration correspondente.
2. Imagens são criadas, escaneadas e publicadas no ECR.
3. Terraform plan é revisado; apply exige aprovação.
4. Migração backward-compatible é aplicada.
5. Deploy staging e smoke tests.
6. Golden smoke sem chamadas pagas repetidas indevidas.
7. Deploy production por rolling/canary conforme componente.
8. Verificar dashboards e alarmes.

## Smoke tests

- Auth e tenant isolation.
- Presign/upload sintético.
- Job com providers stub/health autorizado.
- Entitlement contratual ativo/revogado para tenant sintético; worker bloqueia
  chamada externa sem autorização ativa.
- Scene retrieval e revision conflict.
- DXF mínimo reaberto/auditado.
- Delete e lifecycle marker.

## Rollback

- Aplicação: reverter task definition/bundle.
- Prompt/model: retornar config anterior.
- State machine: novas execuções usam versão anterior; execuções existentes seguem
  versão iniciada ou são tratadas pelo runbook.
- Banco: migrations são forward-only e **não** têm `downgrade` (ADR-0029). Preferir
  expand/contract; rollback de código é apontar a imagem anterior e nunca depende de
  remover coluna. Remoção é trabalho próprio, com aprovação humana explícita.
- Terraform: aplicar plano de reversão revisado, nunca editar console como padrão.

## Gatilhos

- Cross-tenant/security incident.
- Export audit failure.
- Aumento de false-confident errors.
- Falha/latência significativamente acima do baseline.
- Custo descontrolado.
- Migração incompatível.

## Evidência

Cada release registra versões, migrações, prompt/model config, smoke result,
approver e rollback target.
