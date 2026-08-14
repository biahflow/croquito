# ADR-0002: Arquitetura AWS gerenciada

Status: Accepted  
Data: 2026-08-10  
Responsável: Architecture / Platform

## Contexto

O MVP precisa de upload privado, jobs longos, modelos Claude, OCR, auditoria e URL
de demonstração privada. AWS integra Bedrock, Textract e orquestração gerenciada.

## Decisão

Usar AWS `sa-east-1` como região principal com S3, CloudFront, Cognito, WAF, ALB,
ECS Fargate, Step Functions, Lambda, RDS, Textract, Bedrock, EventBridge, SQS,
CloudWatch, X-Ray, KMS e Secrets Manager. Infraestrutura será Terraform.

## Alternativas

- GCP: OCR rico e Cloud Run simples, mas menos alinhado ao Bedrock escolhido.
- VM única: rápida, porém fraca em isolamento, retry e auditabilidade.

## Consequências

- Melhor integração operacional e IAM.
- Maior quantidade de serviços e custo mínimo de rede/observabilidade.
- OpenAI continua externo via NAT.

## Riscos e mitigação

Complexidade precoce: dois workflows claros, módulos Terraform pequenos e nenhuma
abstração multi-cloud no MVP.

