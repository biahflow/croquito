# Requisitos não funcionais — NFC/NFR

Status: Accepted for MVP  
Responsável: Engineering / Security / Product  
Última revisão: 2026-08-10

## Desempenho e capacidade

| ID | Requisito | Verificação |
|---|---|---|
| NFR-PERF-001 | Primeiro rascunho em até 3 min/página nos três casos dourados. | E2E cronometrado |
| NFR-PERF-002 | Cinco jobs simultâneos sem perda de estado. | Teste de carga |
| NFR-PERF-003 | UI responde a pan/zoom/edição a 30 FPS em cenas de até 2.000 entidades. | Teste de browser |
| NFR-PERF-004 | Upload usa S3 assinado e não atravessa o processo da API. | Teste de integração |

## Confiabilidade

| ID | Requisito | Verificação |
|---|---|---|
| NFR-REL-001 | Etapas assíncronas são idempotentes por `job_id`, `page_id` e versão. | Integração |
| NFR-REL-002 | Retry transitório: até 3 tentativas com backoff e jitter. | Teste de falha |
| NFR-REL-003 | Nenhum DXF é publicado antes de reabertura e auditoria. | Teste CAD |
| NFR-REL-004 | Falha de Textract ou de um LLM degrada com issue, sem corrupção de estado. | Fault injection |
| NFR-REL-005 | Meta de disponibilidade da demo privada: 99% mensal, sem SLA contratual. | CloudWatch |

## Segurança e privacidade

| ID | Requisito | Verificação |
|---|---|---|
| NFR-SEC-001 | Autenticação por convite e isolamento por tenant. | Testes de autorização |
| NFR-SEC-002 | TLS em trânsito e KMS em repouso. | Infra checks |
| NFR-SEC-003 | URLs assinadas expiram em até 15 minutos. | Teste de integração |
| NFR-SEC-004 | Artefatos expiram em 7 dias e podem ser excluídos imediatamente. | Lifecycle test |
| NFR-SEC-005 | Logs não contêm imagens, cotas completas, tokens ou URLs assinadas. | Log scan |
| NFR-SEC-006 | Uploads são validados e processados sem privilégios. | Security test |

## Qualidade e auditabilidade

| ID | Requisito | Verificação |
|---|---|---|
| NFR-QUAL-001 | 100% das cotas confirmadas são preservadas no DXF. | Golden tests |
| NFR-QUAL-002 | Toda entidade exportada tem precisão e provenance. | Scene validation |
| NFR-QUAL-003 | Toda chamada registra provedor, modelo e versão de prompt. | Contract test |
| NFR-QUAL-004 | Mudanças de IA não avançam sem eval comparativa. | CI gate |
| NFR-QUAL-005 | Nenhuma geometria subdeterminada é marcada como exata. | Invariant test |

## Operação e custo

| ID | Requisito | Verificação |
|---|---|---|
| NFR-OPS-001 | Métricas por etapa, página e provedor. | Dashboard review |
| NFR-OPS-002 | Custo estimado por página e alerta de budget. | FinOps report |
| NFR-OPS-003 | Deploy possui smoke test e rollback documentado. | Release drill |
| NFR-OPS-004 | Incidente crítico gera registro e post-mortem. | Process audit |

## Compatibilidade

- Browsers: duas versões estáveis mais recentes de Chrome, Edge e Safari.
- DXF: R2018, UTF-8 e `$INSUNITS = 6` para metros.
- AutoCAD: abertura manual nos golden tests; `ezdxf` é o gate automatizado.
- API: `/v1`; mudanças incompatíveis exigem versão nova ou migração explícita.

## Acessibilidade

- Alvo WCAG 2.1 AA para fluxos não relacionados ao canvas.
- Canvas oferece equivalente textual de seleção, precisão e issues.

