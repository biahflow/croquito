# Risco de fornecedores de IA

Status: Accepted baseline  
Responsável: Security / AI / Procurement  
Última revisão: 2026-08-20 (suite hospedada real — ADR-0035/ADR-0037; AWS Bedrock/Textract
saem da tabela ativa)

## Fornecedores

Suite hospedada real ([ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md)):

| Fornecedor | Uso | Dependência crítica |
|---|---|---|
| Anthropic (API direta) | extração de geometria e medida — braço primário | qualidade/latência externa |
| OpenAI (API direta, opcional por `CROQUITO_OPENAI_ARM_ENABLED`) | contraparte da comparação dupla de medida e reserva de fallback | qualidade/latência externa |
| Google Cloud Vision / Document AI | OCR auxiliar (braço `ocr`; Document AI monta por `CROQUITO_DOCAI_PROCESSOR` — [ADR-0037](../adr/0037-document-ai-como-braco-de-ocr.md)) | não bloqueante |

> Histórico: AWS Bedrock (Anthropic) e Amazon Textract foram o desenho original do
> [ADR-0002](../adr/0002-aws-managed-architecture.md), nunca exercido pela suite hospedada —
> nenhuma chamada real saiu deste repositório por esse caminho. O
> [ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md) descontinuou os dois
> fornecedores para a suite real; as classes de adapter permanecem no código só para a via de
> eval por linha de comando.

## Riscos

- Mudança/depreciação de model ID.
- Indisponibilidade ou rate limit.
- Mudança de preço/quotas.
- Processamento em região não esperada.
- Comportamento regressivo sem mudança de schema.
- Termos incompatíveis com uso comercial/dados.
- SDK ou endpoint incompatível.

## Controles

- Adapters internos e schema comum.
- Model IDs efetivos e prompts versionados.
- Evals antes de troca.
- Timeout/retry limitados e circuit breaker operacional.
- Sem auto-confirmação quando um provider falta.
- Minimização de payload.
- Revisão periódica de termos, DPA e disponibilidade.
- Métricas de erro, custo e latência por provider.

## Saída de fornecedor

Para substituir um fornecedor:

1. Implementar adapter sem alterar domain model.
2. Rodar schema/evals/golden cases.
3. Documentar residência, termos e custo.
4. Fazer canary autorizado.
5. Manter rollback até estabilidade.

Nenhum fornecedor é considerado fonte de verdade ou requisito do formato DXF.

