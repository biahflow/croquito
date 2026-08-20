# T5 — e2e: cadeia inteira do orçamento pelas rotas `/v1`, sem CLI

Task Contract no formato do template global (`docs/engineering-os/templates/task.md`),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core, este
contrato e o repositório.

## Identity

```text
feature_id: F-020
task_id: T5
parent_plan: docs/features/F-020-orcamento-base-web/plan.md
depends_on: [T1, T2, T3, T6]
```

## Goal

Critério de aceite 3 da feature: a cadeia inteira do orçamento-base roda pelas
rotas `/v1` num teste e2e novo, espelhando o que a fixture `estimate_chain` do
e2e do CLI prova (`tests/e2e/test_valuation_full_chain.py:785-908`), sem passar
pelo CLI em nenhum passo.

## Baseline

T1–T3 integrados na branch; `make check` e `make test` verdes, incluindo
`tests/api/test_estimate_round_routes.py` (T3) e o e2e do CLI.

## Scope

Arquivo novo `tests/e2e/test_estimate_rounds_v1.py`:

- Infraestrutura in-process no padrão do precedente DIRETO:
  `tests/e2e/test_valuation_v1_chain.py` (cadeia da medição pelas rotas `/v1`,
  incluindo como ele dispara o worker da fila para a etapa de extração —
  handlers de orçamento entregues por T6). Fixtures compartilhadas de
  `tests/fakes.py`. Autentique como ele autentica; papel `orcamentista`.
- Dados: os mesmos insumos sintéticos da `estimate_chain` do CLI — catálogo SCO
  sintético, catálogo EMOP produzido pelo importador `.DBF` real com fixture
  sintética, composição compilada — carregados por upload/presign via rota,
  nunca por chamada de função do CLI.
- Cadeia coberta numa fixture cara de módulo (padrão `chain` do e2e vizinho):
  1. `POST /v1/estimate-rounds` → abre;
  2. instala as três fontes na cascata (ordem declarada) e prova a recusa de
     origem repetida (`ESTIMATE_CASCADE_ORIGIN_DUPLICATE`);
  3. associa prancha e dispara extração (caminho offline/fixture — sem provider
     pago; siga como o e2e da medição resolve a extração sem rede);
  4. decide takeoff; confirma códigos citando a fonte da cascata;
  5. `POST .../estimate` com `bdi_percent="25.00"` e `base_version`;
  6. `GET .../estimate`: auditoria ok, planilha publicada.
- Asserções finais, além do caminho feliz:
  - `estimate_json` da revisão valida com `Estimate.model_validate` (schema v2)
    e `total_amount - total_amount_without_bdi` bate com o BDI impresso;
  - a planilha publicada, reaberta com `openpyxl`, tem as colunas `FONTE` e
    `VALOR UNIT. C/ BDI` e o bloco de itens sem preço quando houver;
  - `base_version` velho no passo 5 → 409 `REVISION_CONFLICT`;
  - nenhum passo importa `croquito_worker.valuation.cli` (o teste é a prova de
    que a jornada não depende do CLI).

## Out of scope

- Alterar qualquer código de produção: se a cadeia não fecha por rota, isso é
  achado de T3 — PARE e reporte em vez de consertar a API.
- Web; e2e do CLI (permanece como está, já ajustado por T1).

## Acceptance criteria

1. `make check` e `make test` verdes com o arquivo novo incluído.
2. O e2e roda determinístico e offline (sem rede, sem provider pago).
3. As asserções nomeadas acima existem e nomeiam os códigos exatos.

## Validation

```bash
make check
make test
uv run pytest tests/e2e/test_estimate_rounds_v1.py -x -q
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo, gravado em
docs/features/F-020-orcamento-base-web/tasks/T5-build-report.md.
