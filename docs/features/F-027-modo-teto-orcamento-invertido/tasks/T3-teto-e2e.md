# T3 — e2e: teto declarado, estouro e limite exato pela cadeia `/v1`

Task Contract derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core,
este contrato e o repositório.

## Identity

```text
feature_id: F-027
task_id: T3
parent_plan: docs/features/F-027-modo-teto-orcamento-invertido/plan.md
depends_on: [T1]
```

## Goal

Critérios 2–4 da feature pela cadeia real: teto declarado na criação, consumo
derivado com valores exatos, estouro `over: true`, limite exato `over: false`, e a
rodada sem teto intacta.

## Baseline

T1 integrado; `make check` e `make test` verdes. T2 corre em paralelo em
`apps/web/src/orcamento/` — não toque lá; se um portão global reprovar ali no meio,
é o paralelismo: re-rode ao final e reporte como contexto.

## Scope

Em `tests/e2e/test_estimate_rounds_v1.py`, cenário ADITIVO (teste novo; a cadeia
existente segue sem teto e sem bloco — asserção explícita de retrocompatibilidade):

1. Criar rodada COM teto menor que o total conhecido do cenário → percorrer a cadeia
   e montar → bloco derivado com `over: true`, `consumed` igual ao `total_amount` do
   estimate (string exata) e `remaining` negativo exato.
2. `POST .../target` editando o teto para EXATAMENTE o `total_amount` →
   `over: false`, `remaining == "0.00"` (limite exato não é estouro).
3. Editar com `base_version` velho → 409 `REVISION_CONFLICT`.
4. `0,00` → 422 `ESTIMATE_TARGET_INVALID`.
5. No teste EXISTENTE da cadeia (sem teto): asserção de que o bloco está ausente.

## Out of scope

- Código de produção (achado ⇒ PARE e reporte); web; demos/goldens.

## Acceptance criteria

1. `make check` e `make test` verdes; asserções com valores exatos truncados.
2. Teste existente não enfraquecido (diff dele = só a asserção nova de ausência).

## Validation

```bash
make check
make test
uv run pytest tests/e2e -q
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo em
docs/features/F-027-modo-teto-orcamento-invertido/tasks/T3-build-report.md.
