# Infraestrutura AWS

Este diretório materializa somente a fundação segura do primeiro marco:

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

