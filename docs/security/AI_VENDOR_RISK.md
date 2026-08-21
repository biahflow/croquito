# Risco de fornecedores de IA

Status: Accepted baseline  
Responsável: Security / AI / Procurement  
Última revisão: 2026-08-21 (Groq entra como fornecedor de transcrição de voz de campo —
F-032 T13, decisão humana de fornecedor; termos pendentes de confirmação na abertura da conta)

## Fornecedores

Suite hospedada real ([ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md)):

| Fornecedor | Uso | Dependência crítica |
|---|---|---|
| Anthropic (API direta) | extração de geometria e medida — braço primário | qualidade/latência externa |
| OpenAI (API direta, opcional por `CROQUITO_OPENAI_ARM_ENABLED`) | contraparte da comparação dupla de medida e reserva de fallback | qualidade/latência externa |
| Google Cloud Vision / Document AI | OCR auxiliar (braço `ocr`; Document AI monta por `CROQUITO_DOCAI_PROCESSOR` — [ADR-0037](../adr/0037-document-ai-como-braco-de-ocr.md)) | não bloqueante |
| Groq (API compatível com o formato OpenAI) | transcrição de nota de voz de campo (`audio-transcription`, F-032) — braço primário provisório, `whisper-large-v3-turbo` | não bloqueante: sem chave ou sem entitlement o áudio continua íntegro no pacote e a transcrição é PULADA |

> Histórico: AWS Bedrock (Anthropic) e Amazon Textract foram o desenho original do
> [ADR-0002](../adr/0002-aws-managed-architecture.md), nunca exercido pela suite hospedada —
> nenhuma chamada real saiu deste repositório por esse caminho. O
> [ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md) descontinuou os dois
> fornecedores para a suite real; as classes de adapter permanecem no código só para a via de
> eval por linha de comando.

### Groq — transcrição de voz de campo (F-032)

**Dado enviado.** O arquivo de áudio da nota de voz gravada pelo técnico na praça
(`webm/opus` no Android, `mp4/aac` no iPhone), inteiro, sem transcodificação. É o dado mais
sensível que este repositório envia a um fornecedor: fala espontânea pode conter voz
identificável, nome de pessoa, telefone, endereço e comentário sobre terceiros — PII que
ninguém digitou num formulário e que o técnico não escolheu campo a campo. Nada mais viaja
junto: sem `prompt` de conteúdo, sem metadados do levantamento, sem identificador de tenant,
projeto, ordem ou pessoa no corpo da chamada.

**Termos.** Fornecedor decidido por ato humano em 2026-08-21; a conta e a chave são atos do
usuário e **ainda não existem** nesta data. A política pública a pinar na abertura da conta é
<https://groq.com/privacy-policy/> (retenção e uso para treinamento nos termos de API), e essa
confirmação é pré-requisito operacional da primeira chamada real — inclusive da rodada paga da
eval comparativa. Enquanto ela não for registrada aqui com data e URL conferidas, o braço
permanece sem chave, que é o mesmo que desligado.

**Mitigações em vigor no código.** Entitlement contratual ATIVO do tenant por chamada (a suíte
injetada de teste/demo **não** dispensa o portão); flag global `CROQUITO_REAL_PROVIDERS_ENABLED`
como kill switch; ausência de chave = braço desligado, com o artefato registrando
`skipped_disabled`; teto de gasto compartilhado da rodada, com reserva pessimista por chamada;
resposta bruta apenas no raw-store protegido sob o prefixo privado do tenant, com retenção de
sete dias; log sem texto transcrito (só ids opacos, desfecho, contagens e duração); transcrição
publicada sempre como rascunho (`status: "draft"`), nunca substituindo o áudio nem virando
medida.

**Risco residual declarado.** Uma vez enviado, o áudio está sujeito à política do fornecedor —
nenhuma mitigação nossa alcança o que acontece do outro lado. Por isso o envio depende de
entitlement contratual por tenant, e por isso a confirmação dos termos de retenção/treinamento
é gate humano antes da primeira chamada real, não depois dela.

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

