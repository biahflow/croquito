# Disaster recovery

Status: Accepted baseline  
Responsável: Platform / Security  
Última revisão: 2026-08-10

## Objetivos do MVP

- RPO alvo: até 24 horas para metadata persistente.
- RTO alvo: até 8 horas para restaurar a demo privada.
- Documentos efêmeros podem precisar ser reenviados após desastre.

Estes objetivos não são SLA contratual.

## Fonte de recuperação

- Infraestrutura: Terraform e imagens ECR.
- Banco: backups automáticos RDS criptografados.
- Front-end: bundle versionado.
- Prompts/config: repositório e release metadata.
- Objetos S3 efêmeros: não possuem backup/versionamento dedicado.

## Cenários

### Falha de serviço/provider

Degradar ou pausar novos jobs; resultados existentes permanecem disponíveis na
retenção. Não migrar provider sem eval.

### Perda de task/worker

Step Functions retry/idempotency reconstrói artefato pelo input digest.

### Corrupção/perda do RDS

1. Conter writes.
2. Restaurar backup em instância isolada.
3. Validar schema e tenants.
4. Reexecutar cleanup de projetos expirados.
5. Reconciliar S3/DB.
6. Trocar endpoint após smoke tests.

### Região indisponível

O MVP não mantém warm standby. Restaurar em região aprovada por Terraform e
revalidar dependências de Bedrock/Textract. Comunicar indisponibilidade.

## Exercício

Antes da demonstração comercial e depois semestralmente:

- Restaurar backup em ambiente isolado.
- Confirmar login, listagem autorizada e export de fixture sintética.
- Medir RPO/RTO.
- Registrar gaps e owners.

