# Controle de custos

Status: Accepted for MVP  
Responsável: Product / Platform / AI  
Última revisão: 2026-08-21

## Unidade econômica

Medir por página e por DXF aprovado:

- Render/CV compute.
- Textract.
- OpenAI input/output.
- Bedrock input/output.
- Escalonamentos.
- Storage/egress.
- Fargate/Step Functions/Lambda.

## Métricas

- `estimated_cost_usd{provider,model,stage}`.
- custo médio/p95 por página.
- escalations por página.
- custo por golden case.
- custo por aprovação e por minuto economizado quando medido.

## Reserva de teto: pessimista antes, devolvida quando nada saiu

`CostBudget` reserva o custo estimado **antes** de cada chamada — é a reserva que barra o
estouro antes de o dinheiro sair, e inverter para "cobrar depois" perderia o portão. Cada
TENTATIVA reserva, inclusive as que o `RetryingProviderAdapter` refaz.

Desde 2026-08-21 a reserva é **devolvida** quando a falha prova que a chamada nunca saiu da
máquina: TLS que não valida, DNS que não resolve, conexão recusada. O critério é do
transporte (`ProviderExecutionError.reached_provider`), não do código de falha, e é
conservador — `TIMEOUT` ambíguo (timeout de leitura, em que o fornecedor pode ter
processado e cobrado sem a resposta chegar) conta como **gasto**.

Por que isso é load-bearing e não detalhe: `BUDGET_EXCEEDED` nunca aciona braço de reserva
— o teto é do job, não do braço. Sem a devolução, uma cadeia longa de retentativas do
primário consumia o teto e a chamada do fallback era recusada por orçamento. Ou seja,
insistir mais no primário custava a testemunha seguinte, mesmo quando nenhuma tentativa
tinha gastado um centavo. O sintoma real está no runbook da Toca: falha de CA do Python do
`uv` virando `TIMEOUT` e comendo o teto sem uma única chamada paga.

Dimensionamento: o teto da rodada precisa comportar
`reserva por chamada x (tentativas do primário + chamadas do reserva)`. Com
`CROQUITO_AI_ESTIMATED_COST_PER_LLM_CALL_USD` alto demais, a devolução ajuda mas não salva
uma cadeia que gaste de verdade.

## Guardrails

- Limites de arquivo/páginas/pixels.
- Rate limit por tenant.
- Deduplicação por digest/model/prompt.
- Reanálise somente de crop.
- Máximo de tentativas fixo.
- Sem chamada paga em background não vinculada a job.
- AWS Budget e alarme diário.

## Ordem de otimização

1. Estabelecer baseline de qualidade.
2. Remover chamadas duplicadas.
3. Melhorar crops e roteamento.
4. Avaliar modelo mais econômico somente com eval.
5. Otimizar compute/infra sem enfraquecer auditabilidade.

## Resposta a anomalia

- Pausar reanálise/escalonamento antes de bloquear acesso aos resultados existentes.
- Identificar tenant/stage por IDs opacos.
- Revogar chave se houver abuso/comprometimento.
- Registrar incidente quando impacto for material.

## Proibições

- Reduzir resolução sem eval.
- Remover segundo provider silenciosamente.
- Desabilitar auditoria DXF para economizar.
- Usar dados do cliente para compensar custo via treinamento/monetização.

