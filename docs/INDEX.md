# Índice da documentação

Status: Accepted  
Responsável: Product / Engineering  
Última revisão: 2026-08-17

Este arquivo é o roteador de contexto para humanos e agentes. Leia
[STATUS.md](STATUS.md) em seguida e carregue somente o conjunto relevante.

## Rotas de leitura

### Entender o produto

1. [PRD](product/PRD.md)
2. [FDD](product/FDD.md)
3. [Acceptance Criteria](product/ACCEPTANCE_CRITERIA.md)
4. [Glossary](product/GLOSSARY.md)

### Implementar front-end

1. [FDD](product/FDD.md)
2. [API Contract](architecture/API_CONTRACT.md)
3. [Human in the Loop](ai/HUMAN_IN_THE_LOOP.md)
4. [NFR](product/NFR.md)
5. `apps/web/AGENTS.md`

### Implementar API

1. [Domain Model](architecture/DOMAIN_MODEL.md)
2. [API Contract](architecture/API_CONTRACT.md)
3. [Processing Workflows](architecture/PROCESSING_WORKFLOWS.md)
4. [Security](../SECURITY.md)
5. `services/api/AGENTS.md`

### Alterar o schema do banco

Modelo em `services/api/src/croquito_api/database.py` mudou? A migration correspondente é
obrigatória — o CI compara as duas e reprova divergência.

1. [ADR-0029](adr/0029-runner-de-migrations-revisadas.md) (runner, adoção de banco antigo,
   forward-only)
2. [Domain Model](architecture/DOMAIN_MODEL.md)
3. [Deployment and Rollback](operations/DEPLOYMENT_AND_ROLLBACK.md)
4. [HML (job de banco na esteira)](operations/HML.md)
5. `services/api/AGENTS.md`

### Alterar a superfície da API

Rota `/v1` nova, removida ou alterada em `services/api/src/croquito_api/main.py`? O API
Contract e o snapshot versionado precisam concordar com a aplicação — o teste de
paridade compara as duas fontes e reprova divergência.

1. [API Contract](architecture/API_CONTRACT.md) — seção "Compatibilidade"
2. `tests/api/test_openapi_contract.py` (snapshot + paridade `/v1` × API Contract)
3. `services/api/AGENTS.md`
4. [Testing Strategy](engineering/TESTING_STRATEGY.md) — seção "Contrato"

### Implementar processamento e CAD

1. [Data Flow](architecture/DATA_FLOW.md)
2. [Domain Model](architecture/DOMAIN_MODEL.md)
3. [Consensus Engine](ai/CONSENSUS_ENGINE.md)
4. [Measurement Association](ai/MEASUREMENT_ASSOCIATION.md)
5. [Measurement Review and Solver](ai/MEASUREMENT_REVIEW_AND_SOLVER.md)
6. [Trace Stage](architecture/TRACE_STAGE.md)
7. [DXF Output Spec](architecture/DXF_OUTPUT_SPEC.md)
8. [Failure Modes](ai/FAILURE_MODES_AND_GUARDRAILS.md)
9. `services/worker/AGENTS.md`

### Implementar medição de obra (orçamentista)

1. [Valuation Context](architecture/VALUATION_CONTEXT.md)
2. [FDD](product/FDD.md)
3. [Human in the Loop](ai/HUMAN_IN_THE_LOOP.md)
4. [ADR-0016](adr/0016-valuation-bounded-context.md)
5. [ADR-0018](adr/0018-valuation-consolidation-and-balance-semantics.md)
6. [ADR-0021](adr/0021-hybrid-sco-code-retrieval.md)
7. [ADR-0020](adr/0020-local-homologation-server-for-valuation.md) (UI local + servidor de homologação)
8. [ADR-0027](adr/0027-price-source-provenance-and-bid-boundary.md) (fontes de preço, aditivo e pré-licitação)
9. [ADR-0028](adr/0028-medicao-na-api-v1-autenticada.md) (desenho da migração para `/v1`, decidido e ainda não implementado)
10. `apps/medicao/AGENTS.md`

### Alterar IA

1. [AI First Principles](ai/AI_FIRST_PRINCIPLES.md)
2. [Model Routing](ai/MODEL_ROUTING.md)
3. [Prompt Contracts](ai/PROMPT_CONTRACTS.md)
4. [Evaluation Strategy](ai/EVALUATION_STRATEGY.md)
5. [Prompt Change Protocol](ai/PROMPT_CHANGE_PROTOCOL.md)

### Alterar infraestrutura ou operação

A homologação hospedada roda em **GCP** ([ADR-0025](adr/0025-homologacao-em-gcp-cloud-run.md));
o desenho AWS é o alvo de produção e não descreve o que está no ar.

1. [HML (ambiente hospedado)](operations/HML.md)
2. [HML Keycloak](operations/HML_KEYCLOAK.md)
3. [AWS Deployment](architecture/AWS_DEPLOYMENT.md)
4. [Processing Workflows](architecture/PROCESSING_WORKFLOWS.md)
5. [Observability](operations/OBSERVABILITY.md)
6. [Deployment and Rollback](operations/DEPLOYMENT_AND_ROLLBACK.md)
7. [ADR-0029](adr/0029-runner-de-migrations-revisadas.md) (runner de migrations do job de banco)
8. `infra/AGENTS.md`

### Revisar segurança e privacidade

1. [Threat Model](security/THREAT_MODEL.md)
2. [Privacy and LGPD](security/PRIVACY_LGPD.md)
3. [Data Retention](security/DATA_RETENTION.md)
4. [AI Vendor Risk](security/AI_VENDOR_RISK.md)

## Fontes canônicas

| Assunto | Documento |
|---|---|
| Visão, escopo e KPIs | [PRD](product/PRD.md) |
| Comportamento e UX | [FDD](product/FDD.md) |
| Requisitos não funcionais | [NFR](product/NFR.md) |
| Interfaces HTTP | [API Contract](architecture/API_CONTRACT.md) |
| Entidades e invariantes | [Domain Model](architecture/DOMAIN_MODEL.md) |
| Processamento assíncrono | [Processing Workflows](architecture/PROCESSING_WORKFLOWS.md) |
| Formato CAD | [DXF Output Spec](architecture/DXF_OUTPUT_SPEC.md) |
| Modelos e fallback | [Model Routing](ai/MODEL_ROUTING.md) |
| Avaliação de IA | [Evaluation Strategy](ai/EVALUATION_STRATEGY.md) |
| Decisões aceitas | [ADR Index](adr/README.md) |
| Marco e riscos atuais | [STATUS](STATUS.md) |

## Catálogo completo

### Produto

- [PRD](product/PRD.md)
- [FDD](product/FDD.md)
- [NFR/NFC](product/NFR.md)
- [Acceptance Criteria](product/ACCEPTANCE_CRITERIA.md)
- [Roadmap](product/ROADMAP.md)
- [Glossary](product/GLOSSARY.md)

### Arquitetura

- [System Architecture](architecture/SYSTEM_ARCHITECTURE.md)
- [Data Flow](architecture/DATA_FLOW.md)
- [Domain Model](architecture/DOMAIN_MODEL.md)
- [API Contract](architecture/API_CONTRACT.md)
- [Processing Workflows](architecture/PROCESSING_WORKFLOWS.md)
- [DXF Output Spec](architecture/DXF_OUTPUT_SPEC.md)
- [Valuation Context](architecture/VALUATION_CONTEXT.md)
- [AWS Deployment](architecture/AWS_DEPLOYMENT.md)

### AI First

- [AI First Principles](ai/AI_FIRST_PRINCIPLES.md)
- [Vision Proposals](ai/VISION_PROPOSALS.md)
- [Measurement Association](ai/MEASUREMENT_ASSOCIATION.md)
- [Measurement Review and Solver](ai/MEASUREMENT_REVIEW_AND_SOLVER.md)
- [Model Routing](ai/MODEL_ROUTING.md)
- [Prompt Contracts](ai/PROMPT_CONTRACTS.md)
- [Consensus Engine](ai/CONSENSUS_ENGINE.md)
- [Evaluation Strategy](ai/EVALUATION_STRATEGY.md)
- [Golden Dataset](ai/GOLDEN_DATASET.md)
- [Human in the Loop](ai/HUMAN_IN_THE_LOOP.md)
- [Failure Modes and Guardrails](ai/FAILURE_MODES_AND_GUARDRAILS.md)
- [Prompt Change Protocol](ai/PROMPT_CHANGE_PROTOCOL.md)

### Segurança

- [Threat Model](security/THREAT_MODEL.md)
- [Privacy and LGPD](security/PRIVACY_LGPD.md)
- [Data Retention](security/DATA_RETENTION.md)
- [AI Vendor Risk](security/AI_VENDOR_RISK.md)

### Engenharia

- [Project Context](engineering/PROJECT_CONTEXT.md)
- [Local Development](engineering/LOCAL_DEVELOPMENT.md)
- [Coding Standards](engineering/CODING_STANDARDS.md)
- [Testing Strategy](engineering/TESTING_STRATEGY.md)
- [Definition of Done](engineering/DEFINITION_OF_DONE.md)
- [Traceability](engineering/TRACEABILITY.md)
- [Dependency Policy](engineering/DEPENDENCY_POLICY.md)
- [Review Checklist](engineering/REVIEW_CHECKLIST.md)

### Operação

- [HML (ambiente hospedado em GCP)](operations/HML.md)
- [HML Keycloak](operations/HML_KEYCLOAK.md)
- [Observability](operations/OBSERVABILITY.md)
- [Deployment and Rollback](operations/DEPLOYMENT_AND_ROLLBACK.md)
- [Incident Response](operations/INCIDENT_RESPONSE.md)
- [Processing Failures Runbook](operations/RUNBOOK_PROCESSING_FAILURES.md)
- [Guaxindiba Domain Review Runbook](operations/RUNBOOK_DOMAIN_REVIEW_GUAXINDIBA.md)
- [Toca Valuation Acceptance Runbook](operations/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md)
- [Cost Control](operations/COST_CONTROL.md)
- [Disaster Recovery](operations/DISASTER_RECOVERY.md)

### Decisões e templates

- [ADR Index](adr/README.md)
- [ADR Template](templates/ADR_TEMPLATE.md)
- [RFC Template](templates/RFC_TEMPLATE.md)
- [RFC-0001 Upload autenticado](rfc/0001-authenticated-upload-integrity.md)
- [Eval Case Template](templates/EVAL_CASE_TEMPLATE.md)
- [Prompt Spec Template](templates/PROMPT_SPEC_TEMPLATE.md)
- [Incident Template](templates/INCIDENT_TEMPLATE.md)
- [Runbook Template](templates/RUNBOOK_TEMPLATE.md)

### Instruções para agentes

- [Root AGENTS](../AGENTS.md)
- [Web AGENTS](../apps/web/AGENTS.md)
- [Medição AGENTS](../apps/medicao/AGENTS.md)
- [API AGENTS](../services/api/AGENTS.md)
- [Worker AGENTS](../services/worker/AGENTS.md)
- [Infrastructure AGENTS](../infra/AGENTS.md)

### Políticas da raiz

- [README](../README.md)
- [Contributing](../CONTRIBUTING.md)
- [Security](../SECURITY.md)

## Governança

- ADR aceito é imutável; substitua por novo ADR.
- Documento canônico deve ser atualizado junto com a implementação.
- Requisitos usam IDs estáveis e são mapeados em
  [TRACEABILITY.md](engineering/TRACEABILITY.md).
- Templates ficam em [templates](templates/ADR_TEMPLATE.md).
