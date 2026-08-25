# Infraestrutura

Este diretório materializa a **fundação AWS**, que é o alvo de produção do sistema
([ADR-0002](../docs/adr/0002-aws-managed-architecture.md)). Atenção: esse desenho
**ainda não foi aplicado** — não há recursos AWS reais no ar. A homologação hospedada
que está de fato em operação roda em **GCP (Cloud Run)**, com a infraestrutura mantida
fora deste repositório (ver [ADR-0025](../docs/adr/0025-homologacao-em-gcp-cloud-run.md)
e [operações/HML](../docs/operations/HML.md)).

O Terraform aqui provê somente a fundação segura do primeiro marco:

- bucket S3 privado, SSE-KMS e expiração automática;
- fila de processamento, DLQ e redrive limitado;
- chave KMS com rotação;
- grupo de logs com retenção definida.

Validação local, sem acessar uma conta:

```bash
terraform -chdir=infra fmt -check
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate
```

`terraform plan` é permitido para revisão. `terraform apply` exige aprovação
explícita do responsável pela conta e um plano revisado, conforme `infra/AGENTS.md`.

