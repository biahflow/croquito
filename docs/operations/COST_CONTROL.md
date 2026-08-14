# Controle de custos

Status: Accepted for MVP  
Responsável: Product / Platform / AI  
Última revisão: 2026-08-10

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

