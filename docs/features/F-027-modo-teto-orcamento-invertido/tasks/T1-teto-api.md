# T1 — Teto como dado da rodada: persistência, rotas e payload derivado

Task Contract derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core
(pinado em `docs/engineering-os/`), este contrato, o
[ADR-0040](../../../adr/0040-teto-de-verba-do-orcamento-base.md) (Accepted — as 6
decisões são a especificação), o [mock aprovado](../mock/README.md) (o payload que você
expõe é o que as telas consomem) e o repositório.

## Identity

```text
feature_id: F-027
task_id: T1
parent_plan: docs/features/F-027-modo-teto-orcamento-invertido/plan.md
depends_on: []
```

## Goal

A rodada de orçamento declara e edita um teto de verba (valor exato + rótulo da
demanda), e toda leitura deriva o consumo contra ele a partir do `total_amount` (com
BDI) do orçamento montado — sem recomputar dinheiro, sem tocar schema publicado.

## Baseline

`make check` e `make test` verdes na branch `f-027-especificacao` (worktree
`croquito-specs` — já tem .venv/node_modules; confirme com `make setup` rápido).

## Scope

### `services/api/src/croquito_api/database.py`

- `EstimateRoundRecord` ganha `target_amount: Mapped[str | None]` (String, valor
  decimal como TEXTO exato — a disciplina Decimal-como-texto do repositório) e
  `target_label: Mapped[str | None]` (String(120)). Docstrings citando o ADR-0040.

### `migrations/versions/0004_*.py` (nova, escrita à MÃO)

- Primeira migração incremental do repo: `op.add_column` × 2 sobre
  `estimate_rounds`, forward-only, docstring no padrão da 0003 explicando por que à
  mão (`make db-revision` exige banco) e que o gate do ADR-0029 confere no CI.

### `services/api/src/croquito_api/estimate_rounds.py`

- Parse/validação do teto: decimal exato (`Decimal(texto)`; `InvalidOperation`
  recusa), finito e **> 0** — zero ou negativo recusam. Recusa única
  `ESTIMATE_TARGET_INVALID` (RoundRefusal 422). "Sem teto" é ausência (None), nunca
  zero — o mock recusa `0,00` na tela e o servidor recusa aqui.
- Bloco derivado no `round_state_payload` (e no payload do estimate): quando a
  rodada TEM teto, `target: {amount, label}`; quando também há `estimate_json` na
  cabeça, `consumed` (= `total_amount` do documento, string como está), `remaining`
  (= teto − consumido, Decimal exato, pode ser negativo) e `over`
  (= consumido > teto, **estrito** — limite exato é `over: false`). NUNCA recompute
  `total_amount`; leia do documento. Sem teto → bloco AUSENTE (decisão 6).

### `services/api/src/croquito_api/main.py`

- `POST /v1/estimate-rounds` (criação): corpo ganha `target_amount`/`target_label`
  OPCIONAIS (string/string).
- Rota nova `POST /v1/estimate-rounds/{round_id}/target`: declarar ou editar
  (`{base_version, target_amount, target_label?}`), disciplina integral (papel na
  primeira linha, `Depends(_require_idempotency)`, `require_base_version`, versão
  avança). **SEM rota/ato de remoção** — o mock lista remoção como não aprovada.
- Snapshot OpenAPI por ato deliberado; `docs/architecture/API_CONTRACT.md`.

### Testes — `tests/api/test_estimate_round_routes.py`

Criar com teto (payload devolve o bloco); criar sem (bloco ausente); declarar
depois; editar; `base_version` velho → 409; 403 sem papel; POST sem
`Idempotency-Key` recusa; `0,00`, negativo e texto ilegível → 422
`ESTIMATE_TARGET_INVALID`; bloco derivado nos TRÊS estados — dentro, **limite
EXATO** (monte um estimate cujo `total_amount` seja igual ao teto: declare o teto
igual ao total conhecido do cenário; `over: false`, `remaining == "0.00"`), e um
centavo acima (`over: true`).

## Out of scope

- Web (T2); e2e (T3); `packages/valuation` (nada muda no domínio); schemas
  publicados e goldens (NENHUM muda); remoção de teto; rotas existentes além do
  corpo de criação.

## Acceptance criteria

1. `make check` e `make test` verdes; snapshot OpenAPI só-adição; nenhum golden nem
   schema gerado muda.
2. Comparação nunca recomputa dinheiro (leitura do `total_amount` como está).
3. Cobertura de teste nomeada acima completa, incluindo o limite exato.

## Validation

```bash
make check
make test
uv run pytest tests/api/test_estimate_round_routes.py -x -q
uv run pytest tests/api/test_migrations.py tests/api/test_openapi_contract.py -q
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo em
docs/features/F-027-modo-teto-orcamento-invertido/tasks/T1-build-report.md.
