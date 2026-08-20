# T7 — Remoção de catálogo da cascata + acabamento do CLI do orçamento

Task Contract no formato do template global (`docs/engineering-os/templates/task.md`),
task de acabamento pós-merge da F-020 (registrada em [evidence.md](../evidence.md) ao
final desta task). O design da remoção JÁ ESTÁ APROVADO: o botão "Remover" faz parte da
cascata desenhada na revisão 1 do [pacote aprovado](../mock/README.md); a rota não
existir foi desvio consciente registrado no [build report de T4](T4-build-report.md).

## Identity

```text
feature_id: F-020
task_id: T7
parent_plan: docs/features/F-020-orcamento-base-web/plan.md (acabamento pós-merge)
depends_on: [] (T1–T6 já estão na main)
```

## Goal

1. A orçamentista remove uma fonte da cascata pela rota e pelo botão, com as mesmas
   guardas das outras mutações da cascata; remover fonte citada por decisão de código
   recusa.
2. O CLI recusa `--bdi` ilegível com mensagem amigável e imprime o BDI no resumo JSON.

## Baseline

`make check` e `make test` verdes na branch `f-020-t7-acabamento` (== main `e618fc8`).

## Scope

### API — `services/api/src/croquito_api/main.py` + `estimate_rounds.py`

- Rota nova `POST /v1/estimate-rounds/{round_id}/catalogs/remove`, espelhando a vizinha
  `POST .../catalogs/order` (mesma faixa do arquivo, ao final): papel
  `_require_valuation_reviewer` na primeira linha, `Depends(_require_idempotency)`,
  `require_base_version`, `problem+json`. Corpo: `{base_version, source_sha256}` — o
  digest da FONTE da entrada a remover (o mesmo que `catalogs/order` usa para citar
  entradas).
- Regras em `estimate_rounds.py`, no padrão das existentes:
  - digest ausente da cascata recusa com código estável (verifique se já existe um
    código para "fonte desconhecida na cascata" usado pela reordenação e reuse-o; só
    crie código novo se não houver);
  - fonte citada por QUALQUER decisão de código registrada recusa
    `ESTIMATE_CASCADE_LOCKED` (mesma guarda da reordenação — hoje ela tranca pela
    cabeça da cascata; a remoção deve trancar quando o `code_assignments_json` da
    cabeça citar o catálogo removido; leia a guarda existente antes e siga a semântica
    dela, não invente outra);
  - remoção é mutação da raiz (`catalog_cascade_json` + `version`), como a reordenação.
- Snapshot OpenAPI regenerado por ato deliberado (`make openapi-snapshot`); diff só de
  adição.
- `docs/architecture/API_CONTRACT.md`: entrada da rota nova, no padrão das vizinhas.

### Web — `apps/web/src/orcamento/`

- Botão "Remover" por entrada da cascata (como desenhado no mock rev. 1), chamando a
  rota nova via função nova em `api.ts` (mesmas invariantes: `base_version`,
  `Idempotency-Key`, nunca redigitar tipo de domínio).
- Recusas traduzidas por tabela em `errors.ts`/`labels.ts` (`ESTIMATE_CASCADE_LOCKED`
  já tem tradução — confira; acrescente a de fonte desconhecida se criar código novo).

### CLI — `services/worker/src/croquito_worker/valuation/cli.py`

- `--bdi` do `build-estimate`: parser deixa de usar `type=Decimal` cru; valor ilegível
  recusa com mensagem argparse amigável em pt-BR (padrão: função conversora que levanta
  `argparse.ArgumentTypeError`). Semântica aceita não muda (decimal exato, `>= 0` segue
  sendo recusado adiante pelo domínio).
- `_estimate_payload` (resumo JSON impresso pelo comando): acrescentar `bdi_percent` e
  `total_amount_without_bdi` como strings.

### Testes

- `tests/api/test_estimate_round_routes.py`: remoção feliz (cascata encolhe, `version`
  avança); 403 sem papel; sem `Idempotency-Key` recusa; `base_version` velho → 409;
  digest desconhecido recusa com o código escolhido; fonte citada por decisão →
  `ESTIMATE_CASCADE_LOCKED`.
- Testes web (vitest) do botão + tradução, no padrão de `cascata.test.ts`.
- Teste do CLI: `--bdi abc` recusa com exit code de argparse e mensagem amigável (sem
  traceback); resumo JSON carrega os campos novos (padrão dos testes de CLI em
  `tests/valuation/test_estimate.py`, `_cli_args`).

## Out of scope

- Reordenação, demais rotas, medição, worker, `providers.py`.
- Qualquer mudança de schema do `Estimate` (nada de `make contracts`).
- Recomputar sugestões automaticamente após remoção (a rota de `recompute` já existe e
  segue sendo ato explícito).

## Acceptance criteria

1. `make check` e `make test` verdes; snapshot OpenAPI com diff só de adição.
2. Recusas cobertas por teste com códigos exatos; goldens intocados.
3. `croquito-valuation build-estimate --bdi abc ...` termina com erro amigável, sem
   traceback.

## Validation

```bash
make check
make test
uv run pytest tests/api/test_estimate_round_routes.py -x -q
npm --workspace @croquito/web run test
make valuation-estimate-demo
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo, gravado em
docs/features/F-020-orcamento-base-web/tasks/T7-build-report.md.
