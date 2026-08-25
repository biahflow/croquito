# Instruções para agentes — infraestrutura

Estas regras estendem o [AGENTS.md](../AGENTS.md). Leia
[AWS Deployment](../docs/architecture/AWS_DEPLOYMENT.md),
[Threat Model](../docs/security/THREAT_MODEL.md),
[Observability](../docs/operations/OBSERVABILITY.md) e
[Deployment and Rollback](../docs/operations/DEPLOYMENT_AND_ROLLBACK.md).

O Terraform deste diretório é o alvo de produção AWS, ainda não aplicado. A
homologação que está de fato no ar roda em GCP (Cloud Run), com infra fora deste
repositório: veja [ADR-0025](../docs/adr/0025-homologacao-em-gcp-cloud-run.md) e
[operações/HML](../docs/operations/HML.md).

## Boundary

Infra contém Terraform, policies, task/state machine definitions e configuração
de deploy. Não contém segredos ou conteúdo de cliente.

## Regras

- Terraform plan é permitido; apply exige aprovação explícita.
- Nunca criar recurso manual para contornar revisão.
- Uma role por workload e least privilege.
- RDS/tasks privados; S3 block public access.
- KMS/TLS obrigatórios para dados de cliente.
- Log groups têm retenção explícita e payload logging do Bedrock fica desabilitado.
- Signed URLs expiram em até 15 minutos.
- Lifecycle de sete dias é policy testada.
- Staging/production não compartilham secrets, buckets ou banco.
- Tags obrigatórias e budget alarms.
- Mudança de região, retenção, provider ou data routing exige ADR/aprovação.

## Validação mínima

- Format/validate/plan.
- Static security/IAM checks.
- Policy tests de public access, encryption, retention e logging.
- Diff de state machine.
- Plano de rollback e impacto de custo.

