# T6 — Classificação visual por IA sob demanda

## Identity

```text
feature_id: F-030
task_id: T6
parent_plan: docs/features/F-030-levantamento-de-campo-na-revisao/plan.md
depends_on: T2
```

## Goal

Uma foto confirmada pode receber, por pedido explícito, uma proposta visual fechada, auditável
e incapaz de produzir medida, geometria ou decisão humana.

## Scope

- `PromptTask.FIELD_PHOTO_CLASSIFICATION`, schema/prompt versionados e adapter multimodal.
- Categorias `MURO | ALAMBRADO | PORTAO | PATAMAR | EQUIPAMENTOS | DETALHES | UNKNOWN`,
  descrição curta, observações topológicas não geométricas e confiança ordinal.
- Rota de solicitação, comando de fila/worker, artefato/estado e lineage completos.
- Gates existentes de provider, entitlement, consentimento, kill switch e custo.
- Eval offline determinística e harness da rodada real com orçamento compartilhado de US$ 5.

## Out of Scope

Web, observação humana, chamada automática, rodada paga sem corpus, OpenAI ligado, medida ou
geometria inferida.

## Acceptance Criteria

1. Upload/vínculo não enfileira classificação; só a rota explícita o faz.
2. Saída fora do schema falha fechada e lineage inclui prompt/schema/provider/modelo.
3. O candidato é Anthropic `claude-opus-5`; OpenAI continua desabilitado.
4. O schema não possui campo de medida, dimensão, coordenada ou precisão probabilística.
5. A eval offline adicionada à suíte e todos os testes determinísticos passam antes de
   qualquer chamada paga.
6. O harness reserva US$ 0,75 por chamada, limita seis execuções e aplica teto absoluto
   `CROQUITO_AI_MAX_ESTIMATED_COST_USD=5.00`, sem rerun seletivo.

## Validation

```text
baseline: T2 BUILD_COMPLETE e gates verdes
required: make check
required: make test
```

## Required Capabilities

```text
READ:     packages/core, services/api, services/worker, evals, tests, docs
WRITE:    packages/core, services/api, services/worker, evals, tests, docs
VALIDATE: comandos de Validation
COMMIT:   allowed
```

## Context to Read First

ADR-0009, ADR-0012, ADR-0035, ADR-0036, ADR-0049; `services/worker/AGENTS.md`; Model Routing;
adapters Anthropic e `survey_photo_analysis.py`; T2/report.

## Known Risks

Prompt medir a cena, confiança numérica inventada, chamada duplicada, custo fora do teto ou
lineage incompleto.

## Human Gates

Após gates offline verdes, parar e receber seis fotos próprias com rótulos fora do Git. A
rodada paga autorizada só pode executar cada item uma vez, no mesmo candidato, até US$ 5.

## Reporting

Criar `T6-build-report.md` com o `BUILD REPORT` completo; separar a evidência offline da rodada
real, que só entra após o gate humano de corpus.
