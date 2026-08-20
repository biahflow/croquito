# T1 — Domínio: BDI no `Estimate` (schema v2) e publicação no manifesto de contratos

Task Contract no formato do template global (`docs/engineering-os/templates/task.md`),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core (pinado em
`docs/engineering-os/`), este contrato, o [ADR-0038](../../../adr/0038-bdi-como-conceito-de-pre-licitacao.md)
e o repositório — nada mais.

## Identity

```text
feature_id: F-020
task_id: T1
parent_plan: docs/features/F-020-orcamento-base-web/plan.md
depends_on: []
```

## Goal

O `Estimate` (orçamento-base de pré-licitação) ganha BDI com a semântica exata do
ADR-0038 e é publicado no manifesto de contratos gerados. O CLI (`build-estimate`,
`estimate-demo`) passa a declarar o BDI. A medição não é tocada.

## Baseline

`make check` e `make test` verdes na branch `f-020-orcamento-web`. O golden
`tests/valuation/golden/estimate-demo.canonical.json` muda NESTA task por decisão
declarada no plano (schema v2) — os demais goldens não podem mudar.

## Scope

Em `packages/valuation/src/croquito_valuation/estimate.py`:

- `ESTIMATE_SCHEMA_VERSION` (linha 59): `"1.0.0"` → `"2.0.0"`.
- `EstimateLine` (linhas 97-149) ganha `unit_price_with_bdi: ExactDecimal`
  (obrigatório). O validator `validate_total` (136-149) passa a exigir
  `total == money_trunc(unit_price_with_bdi * quantity)`; divergência recusa com o
  código existente `ESTIMATE_LINE_TOTAL_MISMATCH`. `expected_total` (117-120)
  acompanha. `money_trunc` vem de `croquito_valuation.rounding` (linha 19-21);
  `ExactDecimal` de `croquito_valuation.models:72`.
- `Estimate` (linhas 152-297) ganha:
  - `bdi_percent: ExactDecimal` (obrigatório, `>= 0`; percentual, ex.: `25.00`);
  - `total_amount_without_bdi: ExactDecimal` (obrigatório).
  Validators novos no padrão dos existentes (`ValuationValidationError` de
  `croquito_valuation/errors.py:8-20`, mensagens em pt-BR):
  - por linha: `unit_price_with_bdi == money_trunc(unit_price * (1 + bdi_percent/100))`
    → recusa `ESTIMATE_LINE_BDI_MISMATCH`;
  - `total_amount_without_bdi == soma de money_trunc(unit_price * quantity)` das
    linhas → recusa `ESTIMATE_TOTAL_WITHOUT_BDI_MISMATCH`;
  - `validate_total_amount` (247-260) permanece: `total_amount` é a soma dos
    `total` (que agora embutem BDI). O valor de BDI impresso é
    `total_amount - total_amount_without_bdi` — diferença de totais truncados,
    NUNCA percentual aplicado ao total (ADR-0038, decisão 4). Não crie campo para
    esse valor derivado: quem imprime calcula a diferença (T2).
- `build_worksite_estimate` (linha 314-512) ganha o parâmetro keyword obrigatório
  `bdi_percent: Decimal` e monta os campos novos. Nenhuma outra mudança de
  comportamento: todos os códigos de recusa existentes (349, 370, 377, 393, 403,
  416, 433, 448, 456, 466) permanecem intactos.

Em `packages/contracts/contracts.manifest.json`:

- Entrada nova no formato exato das seis existentes:
  `module="croquito_valuation.estimate"`, `model="Estimate"`,
  `version_attr="ESTIMATE_SCHEMA_VERSION"`, `schema="schemas/estimate.schema.json"`,
  `typescript="src/estimate.generated.ts"`, `id` e `title` no padrão das entradas
  vizinhas. Depois rode `make contracts` (Makefile linhas 56-58) e commite os
  gerados. NUNCA edite `.schema.json`/`.generated.ts` à mão.

Em `services/worker/src/croquito_worker/valuation/cli.py`:

- `build-estimate` (parser 2867-2891, `run_build_estimate` 1543-1582): argumento
  novo obrigatório `--bdi` (string decimal, ex.: `25.00`), repassado como
  `bdi_percent`.
- `estimate-demo` (parser 2893-2905, `run_estimate_demo` 1585-1678) e
  `estimate_fixture.py`: BDI fixo e determinístico `Decimal("25.00")`.

Em testes:

- `tests/valuation/test_estimate.py`: testes novos nomeando — linha com
  `unit_price_with_bdi` divergente recusa `ESTIMATE_LINE_BDI_MISMATCH`;
  `total_amount_without_bdi` divergente recusa `ESTIMATE_TOTAL_WITHOUT_BDI_MISMATCH`;
  caso feliz com BDI `25.00` confere truncamento por linha (escolha valores em que
  truncar-antes-de-somar ≠ somar-antes-de-truncar, para o teste provar a ordem).
- `tests/valuation/golden/estimate-demo.canonical.json`: regenerado UMA vez pelo
  caminho oficial do golden (veja como `tests/valuation/test_canonical_golden.py`
  o produz); o diff deve mostrar só os campos novos e a versão de schema.
- `tests/e2e/test_valuation_full_chain.py`, fixture `estimate_chain` (785-908) e
  testes 912+: acrescente `--bdi` à chamada do `build-estimate` e asserte os
  campos novos no `Estimate.model_validate_json` da leitura.

## Out of scope

- Escritor/auditor de planilha (T2). `template.py`, `workbook_writer.py`,
  `canonical.py` não são seus.
- API, web, medição (`Valuation`, boletim, `calc.py`) — nada disso muda.
- Qualquer golden além de `estimate-demo.canonical.json`. Se outro golden mudar,
  PARE e reporte em vez de regenerar.

## Acceptance criteria

1. `make check` e `make test` verdes (inclui drift de contratos: schema/TS gerados
   e commitados).
2. `make valuation-estimate-demo` verde e determinístico com o BDI fixo.
3. Recusas novas cobertas por teste com os códigos exatos deste contrato.
4. `grep -r "bdi" packages/valuation/src/croquito_valuation/calc.py
   packages/valuation/src/croquito_valuation/workbook_writer.py` vazio — BDI não
   alcança a medição (ADR-0038, decisão 1).

## Validation

```bash
make check
make test
uv run pytest tests/valuation/test_estimate.py tests/valuation/test_canonical_golden.py -x -q
uv run pytest tests/e2e/test_valuation_full_chain.py -q
make valuation-estimate-demo
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo do contrato do Builder (docs/engineering-os/agents/builder.md),
gravado em docs/features/F-020-orcamento-base-web/tasks/T1-build-report.md.
