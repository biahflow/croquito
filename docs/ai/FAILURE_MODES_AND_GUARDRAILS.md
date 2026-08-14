# Modos de falha e guardrails

Status: Accepted for MVP  
Responsável: AI / Geometry / Security  
Última revisão: 2026-08-10

| Falha | Detecção | Guardrail | Resultado seguro |
|---|---|---|---|
| Dígito inventado | divergência/gabarito | `null` quando ilegível; dois provedores | issue critical |
| Vírgula decimal errada | normalizador | preservar raw text e written precision | revisão |
| Unidade inferida | schema/normalizador | `unknown` sem marca/contexto confirmado | revisão |
| Cota associada ao lado errado | bbox/target conflict | consenso de alvo + UI | reassociação |
| Proporção visual usada como escala | invariant | pixels nunca definem medida exata | approximate/unresolved |
| 90° forçado | constraint provenance | somente user/domain confirmed | não aplicar |
| Círculo falso | fit residual + evidence | Hough é proposal; solver exige parâmetros | spline/revisão |
| Curva serrilhada | complexity check | limite de control points e preview | ajustar spline |
| Página esparsa descartada | regression | nenhum filtro final por ink coverage | classificação humana |
| Detalhe misturado à planta | region roles | sistemas espaciais separados | issue/reclassify |
| Dois modelos erram igual | rules/golden | deterministic checks + HITL | bloquear |
| Prompt injection no desenho | schema/prompt | documento é data; sem tool autonomy | ignorar instrução |
| Provider timeout | telemetry | retry limitado | degradar/falhar |
| Retry produz duplicata | idempotency | digest + stage token | mesma saída lógica |
| DXF corrompido | reopen/audit | publicação atômica pós-audit | export failed |
| Cross-tenant access | auth tests | tenant filter obrigatório | 403 + incident |
| Custo abusivo | quota/metrics | page/region limits e rate limit | 429 |

## Invariantes de segurança geométrica

- Medida confirmada nunca é alterada pelo solver.
- Exact exige solução única e provenance.
- Approximate nunca é promovida por “alta confiança”.
- Unresolved relevante bloqueia export.
- Constraint conflitante não é removida silenciosamente.
- Quantitativo usa somente geometria válida e informa precision.

## Respostas incompletas

Schema parcialmente preenchido não é sucesso parcial implícito. O parser registra
campos ausentes, conserva readings válidas somente quando independentes e cria
issue para a região.

## Fail closed vs fail open

- Autorização, tenant, export e auditoria: fail closed.
- Textract auxiliar: fail open com warning.
- Um LLM: continuar para revisão, sem auto-confirmação.
- Preview não crítico: permitir revisão textual, bloquear export até regenerar.

## Testes obrigatórios

Cada modo de falha crítico possui fixture sintética ou fault injection descrita em
[Testing Strategy](../engineering/TESTING_STRATEGY.md).

