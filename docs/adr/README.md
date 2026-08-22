# Architecture Decision Records

Status: Active index  
Responsável: Architecture  
Última revisão: 2026-08-18

ADRs registram decisões com **impacto durável em arquitetura, operação, segurança ou
custo** — o que cobre decisões transversais, difíceis de reverter ou que afetam
contratos e NFRs. Um ADR aceito é imutável; correção material exige novo ADR com
`Supersedes`.

Este documento é a única formulação do processo de ADR do repositório; `AGENTS.md` e
`CONTRIBUTING.md` remetem para cá e não reformulam o critério.

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
| [0013](0013-export-worker-and-artifact-registry.md) | Export no worker e registro de artefatos | Accepted |
| [0014](0014-scope-criteria-acknowledgement-at-approval.md) | Reconhecimento de critério de escopo na aprovação | Accepted |
| [0015](0015-trace-solve-worker-and-registry.md) | Traçado em lote no worker e registro de solves | Accepted |
| [0016](0016-valuation-bounded-context.md) | Medição de obra como contexto delimitado próprio | Accepted |
| [0017](0017-per-criterion-coverage-declaration-and-trace-parity.md) | Declaração por critério (coberto × pendente) e paridade do traçado | Accepted |
| [0018](0018-valuation-consolidation-and-balance-semantics.md) | Semântica de consolidação e saldo da medição de obra | Accepted |
| [0019](0019-proposal-refresh-creates-a-new-review-revision.md) | Refino de propostas cria nova revisão de leitura | Accepted |
| [0020](0020-local-homologation-server-for-valuation.md) | Servidor local de homologação para o contexto de medição | Accepted |
| [0021](0021-hybrid-sco-code-retrieval.md) | Retrieval híbrido local para sugestão de código SCO | Accepted |
| [0022](0022-declared-rectification-of-review-decisions.md) | Correção declarada de decisão de revisão | Accepted |
| [0023](0023-review-chat-as-an-observational-agent.md) | Conversa da revisão como agente observacional com rascunhos tipados | Accepted |
| [0024](0024-rebranding-to-croquito.md) | Rebranding do produto para croquito | Accepted |
| [0025](0025-homologacao-em-gcp-cloud-run.md) | Homologação hospedada em GCP (Cloud Run) | Accepted |
| [0026](0026-medicao-hospedada-sessao-autenticada-minima.md) | Medição hospedada com sessão autenticada mínima | Accepted |
| [0027](0027-price-source-provenance-and-bid-boundary.md) | Fontes de preço com proveniência e a fronteira licitada × pré-licitação | Accepted |
| [0028](0028-medicao-na-api-v1-autenticada.md) | Medição de obra na API `/v1` autenticada | Accepted |
| [0029](0029-runner-de-migrations-revisadas.md) | Runner de migrations revisadas com Alembic | Accepted |
| [0030](0030-overlay-do-takeoff-reconstruido-na-fila.md) | Overlay do takeoff reconstruído na fila | Accepted |
| [0031](0031-segredo-de-homologacao-gerenciado-por-terraform.md) | Segredo de homologação gerenciado por Terraform | Accepted |
| [0032](0032-porta-de-entrada-e-estado-sem-sessao.md) | Porta de entrada própria e estado sem sessão | Accepted |
| [0033](0033-conta-por-convite-e-login-federado.md) | Conta por convite e login federado que vincula | Accepted |
| [0034](0034-camada-global-vendorizada-e-pinada.md) | Camada global da Engineering OS vendorizada e pinada | Accepted |
| [0035](0035-suite-hospedada-openai-anthropic-direto.md) | Suite hospedada de providers: OpenAI e Anthropic diretos, sem AWS | Proposed |
| [0036](0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md) | Autorização de IA contratual, sem allowlist documental por digest | Proposed |
| [0037](0037-document-ai-como-braco-de-ocr.md) | Document AI como braço de OCR da suite hospedada | Proposed |
| [0038](0038-bdi-como-conceito-de-pre-licitacao.md) | BDI como conceito de pré-licitação | Accepted |
| [0039](0039-sinapi-sicro-como-origens-de-preco.md) | SINAPI e SICRO como origens de preço da pré-licitação | Accepted |
| [0040](0040-teto-de-verba-do-orcamento-base.md) | Teto de verba do orçamento-base — declarado, visível, nunca tesoura | Accepted |
| [0041](0041-decisao-de-ator-maquina-atras-de-flag-local.md) | Decisão de ator-máquina na revisão, atrás de flag local | Accepted |
| [0042](0042-eventos-de-dominio-outbox-pubsub.md) | Eventos de domínio por outbox transacional com publicação em Pub/Sub | Accepted |
| [0043](0043-app-de-campo-pwa-offline-first.md) | App de levantamento de campo como PWA offline-first no monorepo | Accepted |
| [0044](0044-triagem-por-testemunha-anotacao-automatica.md) | Triagem por custo do erro: anotação automática | Accepted |
| [0045](0045-terceiro-estado-demanda-sob-contrato.md) | Demanda sob contrato: o terceiro estado entre pré-licitação e medição | Accepted |
| [0046](0046-aprovacao-do-orcamento-base.md) | O orçamento tem aprovação nominal própria, e publicar deixa de ser parte de montar | Accepted |
| [0047](0047-acervo-de-catalogos-da-plataforma.md) | Catálogo de referência é dado da plataforma, sem dono e endereçado por digest | Accepted |

## Processo

1. Quem identifica a necessidade registra `ARCHITECTURE_DECISION_REQUIRED` e para.
   Um agente não cria a decisão por conta própria; redige o ADR quando um humano pedir.
2. Havendo mais de uma solução materialmente diferente, uma
   [RFC](../templates/RFC_TEMPLATE.md) pode explorar as alternativas antes do ADR
   (ver [CONTRIBUTING.md](../../CONTRIBUTING.md)).
3. Redija com o [template](../templates/ADR_TEMPLATE.md), como `Proposed`: problema,
   alternativas reais, requisitos e NFRs afetados.
4. **Somente um humano muda o status** de `Proposed` para `Accepted` ou `Rejected` —
   inclusive de ADR redigido por agente. Agente transcreve a decisão humana; não a exerce.
5. Nenhuma implementação irreversível antes do aceite.
6. Atualize este índice e a [matriz de rastreabilidade](../engineering/TRACEABILITY.md).
