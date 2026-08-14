# Deploy e rollback

Status: Accepted baseline  
Responsável: Platform / Engineering  
Última revisão: 2026-08-10

## Ambientes

- Local: providers stubados por padrão.
- Staging: dados sintéticos/golden autorizados, recursos isolados.
- Production: acesso por convite, secrets e storage próprios.

## Artefatos

- Imagens de API e worker versionadas por commit digest.
- Front-end bundle imutável.
- Terraform plan revisado.
- Prompt/model routing versionado separadamente, mas ligado ao release.
- Migrações numeradas e compatíveis com rolling deploy quando possível.

## Processo

1. CI passa lint, types, tests e policy checks.
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
- Banco: preferir expand/contract; rollback de código não depende de remover coluna.
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
