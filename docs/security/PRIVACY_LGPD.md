# Privacidade e LGPD

Status: Accepted product policy; requer revisão jurídica antes de venda  
Responsável: Product / Security / Legal  
Última revisão: 2026-08-20 (suboperadores da suite hospedada real — ADR-0035/ADR-0037)

Este documento descreve controles de produto e não substitui aconselhamento
jurídico.

## Papéis esperados

No uso B2B, o cliente tende a atuar como controlador e Croquito como operador
dos documentos enviados. Contratos devem confirmar papéis, finalidade,
suboperadores e canal para solicitações.

## Finalidade

Processar o documento para extrair evidências, permitir revisão e gerar artefatos
CAD. Dados não são usados para publicidade, perfil comportamental ou treinamento
automático.

## Categorias de dados

- Identidade e autenticação do usuário.
- Metadados de projeto/job.
- Documento e imagens derivadas.
- Textos, cotas, entidades e decisões.
- Telemetria técnica e custo sem conteúdo.

## Minimização

- Enviar aos modelos somente página/recorte necessário.
- Usar IDs opacos em chamadas e logs.
- Não exigir nome de pessoa no projeto.
- Separar telemetria de conteúdo.
- Expirar payloads em sete dias.

## Transparência

Em contratos B2B, finalidade, provedores externos, processamento global,
retenção, exclusão e limitação de validação técnica são informados e acordados no
contrato e na documentação comercial do tenant. A API registra uma referência
lógica desse acordo e exige autorização contratual ativa antes de qualquer chamada
externa. A tela operacional do engenheiro não repete esse aceite por job.

## Direitos e solicitações

O sistema oferece exclusão imediata por projeto. Exportação de dados pessoais,
correção cadastral e gestão de conta serão atendidas pelo canal contratual até que
haja automação específica.

## Suboperadores do MVP

- AWS, incluindo S3 e RDS (armazenamento de objeto e banco).
- Anthropic API direta (extração de geometria e medida — braço primário).
- OpenAI API direta (contraparte da comparação dupla e reserva; opcional por
  `CROQUITO_OPENAI_ARM_ENABLED`).
- Google Cloud Vision / Document AI (OCR auxiliar; Document AI monta por configuração —
  [ADR-0037](../adr/0037-document-ai-como-braco-de-ocr.md)).

> Histórico: Textract e Bedrock/Anthropic (desenho AWS `sa-east-1` do
> [ADR-0002](../adr/0002-aws-managed-architecture.md)) nunca foram exercidos pela suite
> hospedada ([ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md)) — não são
> suboperadores ativos.

Manter inventário contratual, termos comerciais e política de retenção de cada
fornecedor antes de produção.

## Transferência internacional

O tenant é autorizado contratualmente para processamento global controlado.
Contratos e aviso de privacidade devem documentar mecanismos aplicáveis antes do
uso comercial; revogação bloqueia novas chamadas externas.

## Incidente

Suspeita de exposição segue [Incident Response](../operations/INCIDENT_RESPONSE.md),
preservando evidência mínima e envolvendo jurídico conforme impacto.
