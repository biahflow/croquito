# T1 — Allowlist de digest fora do caminho hospedado

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-012
task_id: T1
parent_plan: docs/features/F-012-operacao-saas-autorizacao-ia/plan.md
depends_on: none
```

## Goal

O worker hospedado deixa de exigir digest allowlistado: o gate de envio a provider
passa a ser integralmente entitlement contratual + consent por job + teto + kill
switch. Decisão ratificada pelo usuário em 2026-08-19 e registrada no ADR-0036 que
esta task escreve.

## Scope

- `services/worker/src/croquito_worker/local_queue.py`: remover o campo
  `ai_extraction_allowed_digests` (~106-108, com o comentário), o parse da env
  (~132-136) e o bloco de checagem completo (~508-522, incluindo os comentários
  internos, que ficariam mentindo). NÃO tocar: early-return de reentrega (~449-452),
  gate de consent (~466-488), construção da suite real (~523-532).
- `tests/worker/test_local_queue.py`: apagar
  `test_extraction_refuses_a_document_outside_the_allowlist` (~242-280); remover o
  kwarg `ai_extraction_allowed_digests` (~312) e imports que ficarem órfãos.
- `.github/workflows/deploy-hml.yml`: remover
  `CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS=` do `--set-env-vars` do worker (~182) e o
  trecho do comentário (~167-170) que a descreve (o resto do comentário — kill
  switch e teto — fica).
- `docs/adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md` (novo,
  `Proposed`, formato dos vizinhos): contexto (SaaS, cliente sobe N PDFs, redeploy
  por documento não escala; ritual descrito no runbook da F-009), decisão (gate =
  entitlement por tenant + consent automático por job + teto por invocação + kill
  switch; a allowlist por digest permanece SÓ no caminho offline de eval
  (`extraction_eval.py`), onde não há tenant nem entitlement), consequências
  (qualquer PDF de tenant com entitlement ativo sai para provider — ratificado pelo
  usuário em 2026-08-19; supersede PARCIALMENTE o D6 do
  [ADR-0035](../../../adr/0035-suite-hospedada-openai-anthropic-direto.md)),
  alternativas (rota de plataforma para gerir digests — rejeitada: continua manual
  por documento).

## Out of Scope

`extraction_eval.py` (allowlist própria, 152-157), `valuation/*`, RUNBOOK_VALUATION,
consent, suite, `HML.md` (é a T4). Qualquer edição em teste de eval offline é
estouro de escopo — pare e reporte.

## Acceptance Criteria

1. `grep -n "ai_extraction_allowed_digests\|AI_EXTRACTION_NOT_ALLOWLISTED" services/worker/src/croquito_worker/local_queue.py`
   vazio (checado).
2. `make check` e `make test` verdes; testes de eval offline
   (`test_extraction_eval.py`, `test_cli.py`, `test_transcription.py`,
   `test_valuation_*`) passam SEM edição (checado por git diff).
3. Teste existente do consent (`AI_PROCESSING_NOT_AUTHORIZED`) continua passando —
   é a proteção que fica.
4. ADR-0036 com links válidos (check_docs).

## Validation

```text
baseline: make check e make test verdes na ponta da branch
          feat/f-012-operacao-saas-autorizacao-ia (base 852f51d)
required: full: make check
          full: make test
```

## Required Capabilities

```text
READ:     o repositório
WRITE:    services/worker/src/croquito_worker/local_queue.py,
          tests/worker/test_local_queue.py, .github/workflows/deploy-hml.yml,
          docs/adr/0036-*.md
VALIDATE: make check; make test
COMMIT:   forbidden — diff na árvore + BUILD REPORT
```

## Context to Read First

`AGENTS.md`, `CLAUDE.md`, `local_queue.py` 440-560 no estado atual,
`docs/adr/0035-*.md` (o D6 que será superseded), `test_local_queue.py` 230-330.

## Known Risks

O bloco removido é vizinho do consent e da suite — o diff não pode encostar neles.

## Human Gates

Aceite do ADR-0036 é ato humano posterior.

## Reporting

`BUILD REPORT` completo do [contrato do Builder](../../../engineering-os/agents/builder.md),
gravado também em `docs/features/F-012-operacao-saas-autorizacao-ia/tasks/T1-build-report.md`.
