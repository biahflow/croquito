# F-033 T3 — `pricing_regime` na listagem de rodadas

feature_id: F-033
task_id: T3
parent_plan: ../plan.md
role: builder

## Goal

A listagem de rodadas de orçamento passa a dizer em que regime cada uma corre, para a tela
poder distingui-las **antes de abrir**. Acréscimo aditivo à resposta; nada mais muda.

Esta task é a peça 3 da revisão 2 do [pacote de design](../mock/README.md), e é a **única**
das quatro que precisa de servidor.

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz e `services/api/AGENTS.md`.
- [mock/README.md](../mock/README.md), seção **"Revisão 2"** (aprovada em 2026-08-22).
- O escopo 6 do [feature contract](../feature.md).

## Contexto verificado

Não há o que decidir aqui — o dado já existe e já é gravado:

- `EstimateRoundRecord.pricing_regime` existe em `services/api/src/croquito_api/database.py:788`
  (`Mapped[str | None]`, nullable). **Nenhuma migração nesta task.**
- `POST /v1/estimate-rounds` já aceita e grava o campo (`main.py:1366`, `main.py:9415`).
- O que falta é **só ler e expor** na listagem.

## Scope

1. **`EstimateRoundSummary`** (`main.py:1376-1397`) ganha
   `pricing_regime: Literal["pre_bid", "contracted_demand"] | None = None`.

   Siga o molde **exato** de `target_amount`/`target_label`, que estão logo acima: opcional,
   `None` quando ausente. A docstring da classe já explica por que a listagem não deriva
   blocos que exigiriam buscar a cabeça de cada rodada — o regime **não** é um deles, ele
   está na raiz.

2. **`list_estimate_rounds`** (`main.py:9462-9521`) passa `pricing_regime=record.pricing_regime`
   na construção de cada item (o bloco em 9501-9517).

3. **`docs/architecture/API_CONTRACT.md`**, seção `GET /v1/estimate-rounds`: acrescente o
   campo à descrição da resposta. Diga o que a **ausência** significa — rodada em
   pré-licitação —, porque é isso que a tela vai ler.

4. **Snapshot de OpenAPI** regenerado por `make openapi-snapshot`. O diff tem de ser **só de
   adição**; se não for, pare e reporte.

5. **Teste** em `tests/api/test_estimate_round_routes.py`, no molde exato de
   `test_listagem_mostra_teto_cru_sem_consumo` (linha 722): duas rodadas na mesma listagem,
   uma aberta com `pricing_regime="contracted_demand"` e outra sem; a primeira devolve o
   regime, a segunda devolve `None`.

## Out of scope

- **Qualquer arquivo em `apps/web/`** — a tela é a T4.
- Qualquer mudança na criação da rodada (`POST /v1/estimate-rounds`), que já está pronta.
- Qualquer mudança na rota de declaração (`POST .../regime`) ou em
  `ensure_regime_declarable`.
- Migração de banco: o campo já existe.

## Acceptance criteria

1. Rodada aberta declarando o regime aparece na listagem com `pricing_regime` preenchido.
2. Rodada aberta sem declarar aparece com `pricing_regime: null` — **ausência é a
   pré-licitação**, e a listagem não inventa um valor para ela.
3. O diff do snapshot de OpenAPI é só de adição.
4. Baseline: `make check` e `make test` verdes antes e depois. Nenhum teste existente
   enfraquecido.

## Pitfalls

- O snapshot de OpenAPI é ato deliberado: regenere pelo alvo do Makefile, não à mão.
- `pre_bid` **nunca é gravado** — o servidor o aceita no schema da criação só para recusar
  com código estável (`estimate_rounds.py:588`). O `Literal` do campo o inclui por simetria
  com a requisição, mas na prática a listagem só devolve `contracted_demand` ou `None`.
- A listagem não busca a cabeça de cada rodada, e esta task não muda isso: o regime está na
  **raiz** do registro, então não custa consulta nenhuma.
- Testes: reuse `_create_round(**overrides)` e `_headers(key=...)` do próprio arquivo.

## Validation

```bash
make check
make test
uv run pytest tests/api/test_estimate_round_routes.py -q
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
