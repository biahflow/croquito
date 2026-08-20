# T6 — Worker: consumo dos comandos da rodada de orçamento-base

Task Contract no formato do template global (`docs/engineering-os/templates/task.md`),
derivado do [plano válido](../plan.md) (registrada como `PLAN_DEVIATION` — o plano
congelado não cobria o lado consumidor da fila). Autossuficiente: assuma o Core, este
contrato e o repositório.

## Identity

```text
feature_id: F-020
task_id: T6
parent_plan: docs/features/F-020-orcamento-base-web/plan.md
depends_on: [T3]
```

## Goal

T3 publicou dois comandos de fila que hoje ninguém consome:
`extract_estimate_plate` e `rerender_estimate_takeoff_overlay`
(`services/api/src/croquito_api/pubsub_queue.py`, métodos
`enqueue_estimate_plate_extraction`/`enqueue_estimate_takeoff_overlay_rerender`).
Depois desta task, o worker os trata exatamente como trata os equivalentes da
medição, mas sobre as tabelas `estimate_rounds`/`estimate_round_revisions`.

## Baseline

T1–T3 integrados na branch; `make check` e `make test` verdes na árvore atual.

## Scope

Em `services/worker/src/croquito_worker/local_queue.py` (1953 linhas — arquivo
grande vivo; leia o `dispatch` e os handlers da medição por inteiro antes de
editar):

- `dispatch` (linhas 495-530): dois roteamentos novos ANTES da guarda de
  `job_id`, no padrão exato e pelo mesmo motivo comentado dos da medição
  (`extract_valuation_plate` linha 507, `rerender_takeoff_overlay` linha 519):
  - `extract_estimate_plate` → handler novo, corpo `{round_id, extraction_id,
    tenant_id}`;
  - `rerender_estimate_takeoff_overlay` → handler novo, corpo `{round_id,
    tenant_id, packet_sha256}`.
  Corpo malformado levanta `UnroutableMessageError`, como os vizinhos.
- Handlers novos espelhando `_handle_valuation_extraction` (linha 1721, que
  chama `_extract_valuation_plate`) e `_handle_takeoff_overlay_rerender`
  (linha 1888), com as diferenças estritamente necessárias:
  - tabela raiz `estimate_rounds` no lugar de `valuation_rounds` (mesmas
    colunas de prancha/extração — o espelho é 1:1 nesses campos);
  - revisões em `estimate_round_revisions` (append-only; SEM incremento de
    `version` quando o artefato é derivado sem decisão humana — siga o que o
    handler da medição faz nesse ponto, o desenho é o mesmo);
  - o restante (ingestão da página, adapter de extração via
    `extraction_arm_spec`, overlay, escrita sob `tenants/{tenant_id}/`,
    transições `queued → running → done|failed`, `extraction_failure_code`)
    é reuso: extraia função compartilhada quando a diferença for só a tabela,
    em vez de duplicar blocos longos — mas NÃO mude o comportamento dos
    handlers da medição (os testes deles são o detector).

Em `tests/worker/test_estimate_extraction_worker.py` (novo):

- Espelhe `tests/worker/test_valuation_extraction_worker.py` na estrutura e nas
  fixtures. Cobertura mínima: caminho feliz (comando → revisão nova com
  `takeoff_packet_json` e refs/digests preenchidos, status `done`); falha do
  adapter → `failed` com `extraction_failure_code` e SEM revisão nova; corpo
  malformado → `UnroutableMessageError`; comando da medição continua roteando
  para o handler da medição (não regressão do dispatch).

## Out of scope

- API (`services/api/`), web, CLI, `providers.py`.
- Qualquer mudança de comportamento nos handlers do croqui e da medição.
- e2e (T5 consome esta task; se o espelho não fechar, reporte em vez de
  contornar).

## Acceptance criteria

1. `make check` e `make test` verdes.
2. Os testes novos passam; os testes existentes do worker da medição passam sem
   nenhuma alteração neles.
3. `git diff` de `local_queue.py` não altera linha dos handlers existentes além
   de extração de função compartilhada (se houver), com comportamento provado
   idêntico pelos testes existentes.

## Validation

```bash
make check
make test
uv run pytest tests/worker/test_estimate_extraction_worker.py tests/worker/test_valuation_extraction_worker.py -x -q
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo, gravado em
docs/features/F-020-orcamento-base-web/tasks/T6-build-report.md.
