# Risco de fornecedores de IA

Status: Accepted baseline  
Responsável: Security / AI / Procurement  
Última revisão: 2026-08-10

## Fornecedores

| Fornecedor | Uso | Dependência crítica |
|---|---|---|
| OpenAI | extração multimodal e escalonamento | qualidade/latência externa |
| AWS Bedrock/Anthropic | leitura independente e escalonamento | modelo e perfil global |
| Amazon Textract | OCR e boxes auxiliares | não bloqueante |

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

