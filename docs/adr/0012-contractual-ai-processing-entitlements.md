# ADR-0012: Autorização contratual por tenant para processamento de IA

Status: Accepted  
Data: 2026-08-10  
Responsável: Security / Product / Platform

## Contexto

O aceite por job exposto ao engenheiro repete uma autorização já definida no
contrato B2B e não comprova que o tenant está habilitado comercialmente. O browser
não é fonte de autorização e provedores externos só podem receber dados de tenants
com acordo vigente.

## Decisão

Manter um entitlement contratual por tenant, ativado ou revogado somente por um
`platform_operator`. A criação de job com providers reais exige entitlement ativo,
gera snapshot imutável da autorização no job e o worker revalida o entitlement
antes da chamada externa. A tela de revisão não mostra checkbox nem aviso de
aceite por job.

## Alternativas

- Flag global de ambiente: rejeitada porque libera tenants sem distinção contratual.
- Aceite pelo engenheiro a cada job: rejeitado porque é redundante, frágil e não
  substitui controle comercial.

## Consequências

### Positivas

- Autorização é auditável, tenant-scoped e independente do browser.
- Fluxo operacional não expõe detalhes contratuais nem UUIDs internos.

### Negativas

- Plataforma precisa provisionar o entitlement antes de ativar providers reais.
- Revogação interrompe jobs ainda não processados por providers externos.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Entitlement liberado indevidamente | papel OIDC separado, idempotência e audit event no tenant alvo |
| Job enfileirado após revogação | worker revalida entitlement ativo antes de ler o upload |

## Rastreabilidade

- Requirements: FR-001, NFR-SEC-001, NFR-SEC-005
- Supersedes: ADR-0008
- Superseded by: none
