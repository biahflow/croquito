# T1 — Funil: valor é fatal, target_hint é nota

Task Contract derivado do [plano](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-024
task_id: T1
parent_plan: docs/features/F-024-leitura-sem-target-hint/plan.md
depends_on: []
```

## Goal

Leitura com `normalized_value` e sem `target_hint` deixa de morrer como
`READING_{n}_INCOMPLETE`: entra no pacote (status ambíguo normal) com
`target_hint=None` e a nota `READING_{n}_WITHOUT_TARGET_HINT`. Sem valor,
comportamento atual intacto (INCOMPLETE, ou NOTE_WITHOUT_VALUE quando kind=note,
da F-021).

Motivação medida na V16 (2026-08-20): 12 de 13 cotas de chão claras descartadas
só por falta do hint — que é dica, não amarração (a associação explícita do
revisor usa candidatos por proximidade, `association.py`, e não lê o hint).

## Scope

Em `services/worker/src/croquito_worker/review.py`:
- `DimensionReading.target_hint: str | None = None` (hoje
  `Field(min_length=1, max_length=120)`). Manter o max_length quando presente
  (use o padrão Pydantic do repo para opcional com limite).

Em `services/worker/src/croquito_worker/provider_review.py`:
- Separar o teste da linha ~562:
  - `normalized_value is None` → como hoje (INCOMPLETE / NOTE_WITHOUT_VALUE).
  - valor presente e `target_hint is None` → NÃO descartar: nota
    `READING_{position}_WITHOUT_TARGET_HINT`, e o `DimensionReading` nasce com
    `target_hint=None` (atenção à linha ~618, que hoje monta
    `f"{...entity_label}: {...feature}"` — só quando o hint existe).
- O resto do laço (unit, kind, F-021, corroboração OCR) intocado.

Em `tests/worker/test_providers.py`:
- leitura `length`+valor+sem hint → entra, `target_hint is None`, nota nova.
- leitura sem valor → fora, nota atual (INCOMPLETE).
- leitura `note` completa sem hint → entra com `annotation_suggested=True` E a
  nota de hint (os dois sinais coexistem).
- pacote antigo com hint → continua validando.

Snapshot OpenAPI: regenerar (`make openapi-snapshot`), conferir que o diff é só
nullable do campo.

Docs: `docs/ai/PROMPT_CONTRACTS.md` (destino de leitura sem hint) e
`docs/architecture/API_CONTRACT.md` (campo nullable, com uma frase do porquê).

## Out of scope

`transcription.py`, `apps/web` (o tipo já é opcional), prompts, association.py.

## Baseline

Árvore limpa sobre main (f802673+); `make check`/`make test` verdes
(1641 pytest + 581 vitest).

## Acceptance criteria

1. `make check`, `make test`, `make provider-contract-demo` verdes.
2. Os quatro testes novos passam.
3. Diff do snapshot só de nullable.

## Validation

```bash
make check && make test
uv run pytest tests/worker/test_providers.py -x -q
make provider-contract-demo
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT.

## Report

BUILD REPORT completo em tasks/T1-build-report.md E na resposta final.
