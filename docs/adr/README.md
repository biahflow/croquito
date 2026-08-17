# Architecture Decision Records

Status: Active index  
Responsável: Architecture  
Última revisão: 2026-08-10

ADRs registram decisões transversais, difíceis de reverter ou que afetam contratos
e NFRs. Um ADR aceito é imutável; correção material exige novo ADR com
`Supersedes`.

## Estados

`Proposed`, `Accepted`, `Deprecated`, `Superseded`, `Rejected`.

## Índice

| ADR | Decisão | Status |
|---|---|---|
| [0001](0001-monorepo-and-service-boundaries.md) | Monorepo e boundaries | Accepted |
| [0002](0002-aws-managed-architecture.md) | AWS gerenciada | Accepted |
| [0003](0003-step-functions-over-celery.md) | Step Functions no lugar de Celery | Accepted |
| [0004](0004-dual-model-provider-strategy.md) | Dois provedores multimodais | Accepted |
| [0005](0005-canonical-scene-graph.md) | Scene graph canônico | Accepted |
| [0006](0006-human-review-and-provenance.md) | HITL e provenance | Accepted |
| [0007](0007-dxf-primary-output.md) | DXF como saída do MVP | Accepted |
| [0008](0008-global-ai-processing-and-retention.md) | Processamento global e retenção | Accepted |
| [0009](0009-golden-dataset-and-evaluation-gates.md) | Golden dataset e gates | Accepted |
| [0010](0010-versioned-prompts-models-and-responses.md) | Versionamento de IA | Accepted |
| [0011](0011-oidc-portable-identity.md) | OIDC portável com Keycloak inicial | Accepted |
| [0012](0012-contractual-ai-processing-entitlements.md) | Autorização contratual de IA por tenant | Accepted |
| [0013](0013-export-worker-and-artifact-registry.md) | Export no worker e registro de artefatos | Proposed |
| [0014](0014-scope-criteria-acknowledgement-at-approval.md) | Reconhecimento de critério de escopo na aprovação | Proposed |
| [0015](0015-trace-solve-worker-and-registry.md) | Traçado em lote no worker e registro de solves | Proposed |
| [0016](0016-valuation-bounded-context.md) | Medição de obra como contexto delimitado próprio | Proposed |
| [0017](0017-per-criterion-coverage-declaration-and-trace-parity.md) | Declaração por critério (coberto × pendente) e paridade do traçado | Accepted |
| [0018](0018-valuation-consolidation-and-balance-semantics.md) | Semântica de consolidação e saldo da medição de obra | Proposed |
| [0019](0019-proposal-refresh-creates-a-new-review-revision.md) | Refino de propostas cria nova revisão de leitura | Accepted |
| [0020](0020-local-homologation-server-for-valuation.md) | Servidor local de homologação para o contexto de medição | Proposed |
| [0021](0021-hybrid-sco-code-retrieval.md) | Retrieval híbrido local para sugestão de código SCO | Accepted |
| [0022](0022-declared-rectification-of-review-decisions.md) | Correção declarada de decisão de revisão | Accepted |
| [0023](0023-review-chat-as-an-observational-agent.md) | Conversa da revisão como agente observacional com rascunhos tipados | Proposed |
| [0024](0024-rebranding-to-croquito.md) | Rebranding do produto para croquito | Accepted |
| [0025](0025-homologacao-em-gcp-cloud-run.md) | Homologação hospedada em GCP (Cloud Run) | Accepted |
| [0026](0026-medicao-hospedada-sessao-autenticada-minima.md) | Medição hospedada com sessão autenticada mínima | Accepted |
| [0027](0027-price-source-provenance-and-bid-boundary.md) | Fontes de preço com proveniência e a fronteira licitada × pré-licitação | Proposed |

## Processo

1. Use o [template](../templates/ADR_TEMPLATE.md).
2. Descreva problema e alternativas reais.
3. Relacione requisitos e NFRs afetados.
4. Obtenha aprovação antes da implementação irreversível.
5. Atualize este índice e a [matriz de rastreabilidade](../engineering/TRACEABILITY.md).
