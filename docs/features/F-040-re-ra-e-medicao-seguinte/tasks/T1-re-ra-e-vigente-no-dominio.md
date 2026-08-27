# F-040 · T1 — A RE-RA com procedência e o vigente derivado no domínio

Feature: [F-040](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

Dar procedência à RE-RA e tornar a quantidade vigente **derivada**, espelhando o que a F-039
fez com o preço, sem afrouxar invariante nenhum e sem mover número já lançado.

## Escopo

- `packages/valuation/src/croquito_valuation/contract.py`
- `packages/valuation/src/croquito_valuation/contract_diagnosis.py` (acompanhar o vigente
  derivado, sob pena de dois veredictos sobre a mesma planilha)
- `tests/valuation/` (novo `test_amendment.py` + ajuste dos oráculos existentes)

## Fora de escopo

- Rota, planilha, tela e medição seguinte — nenhuma escrita nova de dado aqui.
- Base de preço de item novo trazido por RE-RA: já decidida (ADR-0055, decisão 9); esta
  tarefa apenas materializa descrição, unidade e preço da linha nova (ADR-0056, decisão 7).

## Critérios de aceite

1. `Amendment` ganha `declared_by`, `declared_at` (com fuso), `reference_period` e `note`
   opcional, com validador que recusa instante ingênuo — espelho de `PriceAdjustment`
   (ADR-0056, decisão 1). Código de erro estável, mensagem em língua de obra.
2. `ContractWorkbook.current_quantity(line)` devolve `contract_quantity + Σ deltas` das RE-RA
   que citam o código; sem RE-RA, devolve `contract_quantity` **bit a bit** (decisão 3).
3. `amended_quantity` e `balance_quantity` viram **opcionais**; quando presentes, são
   conferência contra o derivado, e a divergência recusa com `AMENDMENT_APPLICATION_MISMATCH`
   (preservado) e `CONTRACT_BALANCE_MISMATCH`.
4. Item novo sobre código ausente do consolidado cria a linha com `contract_quantity` zero,
   descrição, unidade e preço materializados do catálogo contratual; ausente **também** do
   catálogo recusa (decisão 7).
5. `schema_version` sobe para `4.0.0`, aceitando `2.0.0` e `3.0.0`; consolidado gravado antes
   da feature continua validando, com vigente igual ao `amended_quantity` que ele trazia
   (decisão 8).
6. `contract_diagnosis.py` recomputa o vigente pela mesma derivação, sem segundo veredicto.

## Validação

`uv run pytest tests/valuation` verde; `uv run mypy packages` limpo.
