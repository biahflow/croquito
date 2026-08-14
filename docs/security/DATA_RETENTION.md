# Retenção e exclusão de dados

Status: Accepted for MVP  
Responsável: Security / Platform  
Última revisão: 2026-08-10

## Política padrão

Projetos e conteúdo expiram sete dias após upload. O usuário pode solicitar
exclusão imediata a qualquer momento.

## Matriz

| Dado | Storage | Retenção | Exclusão |
|---|---|---|---|
| PDF original | S3 | 7 dias | imediata/lifecycle |
| Páginas e crops | S3 | 7 dias | imediata/lifecycle |
| Provider raw responses | PostgreSQL/S3 protegido | 7 dias | imediata/cleanup |
| Scene revisions | PostgreSQL | 7 dias | imediata/cleanup |
| DXF e pacote | S3 | 7 dias | imediata/lifecycle |
| Auth/account | provedor OIDC | enquanto conta ativa | processo de conta |
| Telemetria sem conteúdo | CloudWatch/metrics | política operacional definida no ambiente | expiração por log group |
| Audit administrativo | CloudTrail | política de segurança | lifecycle protegido |
| Backup RDS | AWS backup | janela operacional curta | expiração automática |

## Exclusão imediata

1. Marcar projeto `DELETING` e revogar acesso/download.
2. Parar/invalidar novas execuções quando seguro.
3. Excluir objetos S3 por prefixo interno resolvido pelo servidor.
4. Excluir dados filhos em transação/cleanup idempotente.
5. Registrar conclusão sem conteúdo.
6. Reconciliar órfãos por job programado.

O endpoint retorna `202`; UI mostra estado até conclusão.

## Backups

Dados removidos podem permanecer criptografados em backup até a expiração da
janela. Não são restaurados seletivamente para uso normal. Restauração de desastre
reexecuta cleanup de projetos expirados antes de liberar o sistema.

## Provedores

Enviar dados via APIs comerciais e configurar retenção/logging mínimo disponível.
O sistema não depende de provider file storage permanente.

## Verificação

- Teste periódico cria projeto sintético, exclui e verifica todos os storages.
- Métrica de objetos/rows órfãos deve permanecer zero.
- Lifecycle e log retention são verificados por Terraform policy tests.
