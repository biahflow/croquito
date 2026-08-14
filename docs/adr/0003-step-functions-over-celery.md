# ADR-0003: Step Functions no lugar de Celery/Redis

Status: Accepted  
Data: 2026-08-10  
Responsável: Architecture / Platform

## Contexto

O pipeline possui fan-out por página, chamadas paralelas, retries distintos,
tarefas Fargate e pausa entre extração e revisão humana.

## Decisão

Usar Step Functions Standard para orquestração, Fargate para trabalho pesado,
Lambda para tarefas leves e SQS DLQ/EventBridge para falhas terminais. Não usar
Celery, Redis ou ElastiCache no MVP.

## Alternativas

- Celery/Redis: flexível, mas transfere persistência, monitoramento e retry à equipe.
- SQS puro: bom dispatch, insuficiente como histórico/orquestração do pipeline.

## Consequências

- Estado e falhas são visíveis por execução.
- Workers permanecem stateless e idempotentes.
- State machine vira artefato versionado e testável.

## Riscos e mitigação

Vendor lock-in: domínio não depende do Step Functions; workflows chamam comandos
de aplicação com contratos explícitos.

