# ADR-0037: Document AI como braço de OCR da suite hospedada

Status: Proposed  
Data: 2026-08-20  
Responsável: Engineering

## Contexto

O [ADR-0035](0035-suite-hospedada-openai-anthropic-direto.md) decidiu em D3 que o braço
`ocr` da suite hospedada é o Cloud Vision (`document text detection`), corroborando cada
leitura dos LLMs por texto normalizado e interseção de bbox. O mesmo ADR registrou o
Google Document AI como **escalada nomeada**, condicionada à reprovação de
`make ocr-eval` contra prancha real — condição escrita quando ainda não havia prancha
real processada.

A condição materializou-se antes do eval formal: na segunda revisão real do Guaxindiba
(2026-08-20), o pacote chegou com 10 leituras onde a folha escreve ~16 números —
`9,55`, `3,86`, `12,40`, `6,60`, `14,50` e `24,55` não viraram leitura, e são
justamente cotas de chão de que o solver precisa. O usuário decidiu, em 2026-08-20,
exercer a escalada já registrada: Document AI no lugar do Cloud Vision no braço de OCR.

Restrições herdadas que continuam valendo: o braço OCR é suporte determinístico, não
item consentível (`providers_json` não o lista, D4 do ADR-0035); resposta bruta vai ao
raw-store com retenção de 7 dias; nenhum log carrega imagem, texto integral ou
credencial; o custo entra no mesmo `CostBudget` da rodada.

## Decisão

O braço `ocr` de `build_real_provider_suite` passa a ser um adapter REST do Document AI
(`projects/*/locations/*/processors/*:process`, processador de OCR), no mesmo desenho do
adapter atual: sem SDK do produto (só `google-auth` para o token ADC), schema estrito,
`RetryingProviderAdapter` + `BudgetedProviderAdapter`, raw-store e lineage por documento.

A seleção é por configuração: com `CROQUITO_DOCAI_PROCESSOR` definido (nome completo do
processador, que embute projeto e região), a suite monta Document AI; sem ele, monta o
Cloud Vision como hoje. O deploy da configuração é ato humano separado do merge — o
código chega antes de o processador existir e nada quebra.

`GcpVisionOcrAdapter` permanece no módulo, testado, seguindo o precedente
Bedrock/Textract do ADR-0035 D1: classe fica, suite deixa de montá-la quando a
configuração aponta o substituto.

## Alternativas

- **Manter Cloud Vision e aguardar `make ocr-eval` contra prancha real.** Rejeitada por
  decisão do usuário: a prancha real já demonstrou a perda (6 de ~16 números) no uso, e
  o eval sintético mede 100% justamente porque a fixture não tem letra manuscrita.
- **Rodar eval comparativo pago antes de trocar.** Não rejeitada — adiada: o adapter
  novo atrás de configuração permite comparar os dois braços contra a mesma prancha
  quando o processador existir, com o eval decidindo a promoção em HML.
- **SDK oficial do Document AI.** Rejeitada: o padrão do módulo é REST + `google-auth`
  puro (docstring do adapter atual), e o SDK adicionaria dependência pesada para uma
  chamada única.

## Consequências

### Positivas

- OCR especializado em documento (letra manuscrita incluída) alimentando a corroboração
  e, por consequência, mais leituras alcançando o pacote de revisão.
- Troca reversível por configuração, sem redeploy de código.
- O contrato `OcrOutput`/`OcrLineOutput` não muda: consumo em `provider_review.py`
  permanece intacto.

### Negativas

- Mais uma API GCP a habilitar e um processador a provisionar (repositório
  `biahflow/infra`, ato humano).
- Preço por página maior que o do Cloud Vision; o default de
  `CROQUITO_AI_ESTIMATED_COST_PER_OCR_CALL_USD` precisa refletir o processador
  escolhido.
- Granularidade de "linha" muda de parágrafo (Vision) para linha do layout (DocAI);
  a corroboração por interseção de bbox tolera, mas o eval comparativo deve confirmar.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Processador inexistente/rota errada em runtime | Falha permanente já degrada para `OCR_UNAVAILABLE` sem derrubar a revisão (comportamento existente) |
| Resposta do DocAI sem `normalizedVertices` em algum layout | Adapter recusa a linha sem bbox em vez de inventar coordenada; contrato exige área positiva |
| Regressão silenciosa de corroboração na troca | Braço antigo permanece montável por configuração; eval comparativo contra a mesma prancha antes de promover em HML |
| Custo por página subestimado no budget | Env var de custo por chamada é dado de deploy; ADR exige revisão do valor junto do provisionamento |

## Rastreabilidade

- Requirements: NFR-REL-004 (falha de OCR não bloqueia revisão), decisões D3/D4 do ADR-0035
- Supersedes: revisa a decisão D3 do [ADR-0035](0035-suite-hospedada-openai-anthropic-direto.md) (o restante permanece)
- Superseded by: none
