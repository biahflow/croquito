# Instruções para agentes — worker

Estas regras estendem o [AGENTS.md](../../AGENTS.md). Leia
[Data Flow](../../docs/architecture/DATA_FLOW.md),
[Model Routing](../../docs/ai/MODEL_ROUTING.md),
[Consensus Engine](../../docs/ai/CONSENSUS_ENGINE.md),
[Domain Model](../../docs/architecture/DOMAIN_MODEL.md) e
[DXF Output Spec](../../docs/architecture/DXF_OUTPUT_SPEC.md).

## Boundary

Worker executa PDF, visão, providers, consenso, solver e export por comandos
idempotentes. Não decide autorização de usuário nem publica antes da auditoria.

## Regras de processamento

- Separar adapters probabilísticos de funções determinísticas.
- Preservar raw evidence e transforms.
- Nunca derivar dimensão exata de pixels.
- Nunca remover constraint conflitante silenciosamente.
- Model/provider fallback é explícito e registrado.
- Retry só para falha transitória, não para obter resposta conveniente.
- Filesystem temporário por task e sem privilégio.
- Output de stage é validado antes de persistir.

## Geometria

- Metros/radianos internamente.
- Tolerâncias nomeadas e testadas.
- Finite values e topology checks obrigatórios.
- RDP/simplificação não substitui fitting de reta/arco.
- Hough/contour são proposals.
- Approximate permanece approximate até o DXF.

## DXF

- Export somente de revisão aprovada.
- Gerar em temporary key, reabrir, auditar, renderizar e publicar atomicamente.
- Confirmed dimensions devem ser verificadas contra entidades.

## Testes mínimos

- Normalização/consenso e schema failures.
- Solver: exato, derivado, aproximado, subdeterminado e conflito.
- Provider timeouts/429/invalid schema.
- CAD reopen/audit/topology.
- Golden/regression conforme autorização.

