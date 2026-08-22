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

### Mudou o tema do Keycloak? Confira o que o AR está servindo

O Keycloak serve os estáticos do login em `/auth/resources/<versão>/...`, e aquele número
acompanha a versão do **servidor**, não a do tema. Enquanto ele seguir na mesma versão, a
URL do `croquito.css` é **idêntica** entre deploys — e um cache de borda que a considere
imutável nunca volta a perguntar. Foi assim que o tema com o olho de senha dentro do campo
ficou publicado por quase quatro dias sem chegar ao ar (2026-08-22).

A fumaça **não pega** isso: ela prova que o login funciona, não como ele está pintado.

`deploy/nginx.conf` limita esse cache a 5 minutos, mas a mitigação só vale a partir do
deploy que a levar — e uma cópia já guardada na borda continua até expirar. Depois de um
deploy que mexa no tema, confira:

```bash
curl -sSI https://croquito-hml.biahflow.ai/auth/resources/<versão>/login/croquito/css/croquito.css \
  | grep -iE 'cache-control|age|last-modified|cf-cache-status'
```

`last-modified` anterior à sua mudança, ou `age` alto com `cf-cache-status: HIT`, significa
cópia velha na borda: purgue o caminho no CDN. A versão em uso sai do `href` do CSS na
página de login.

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
