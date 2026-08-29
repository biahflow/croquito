# F-047 · T3 — `quantitativos.csv` com identidade e agrupamento por elemento

Feature: [F-047](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Fazer o CSV do export carregar a identidade do elemento e agrupar por ela quando existir, sem
mudar o que sai para o croqui sem identidade.

## Escopo

- `services/worker/src/croquito_worker/dxf.py` (`_write_quantities`, linhas 482-539)
- `docs/architecture/DXF_OUTPUT_SPEC.md`
- `tests/worker/test_dxf.py`

## Fora de escopo

- Mudar o cálculo geométrico: comprimento, perímetro e área continuam como estão
- Mudar as exclusões existentes (`TEXTOS`, `COTAS`, `summary_code` de detalhe)

## Critérios de aceite

1. Coluna `element_ref` **aditiva**, ao lado de `entity_id` — nunca no lugar dele.
2. Quando várias entidades compartilham identidade, o agrupamento é o decidido aqui e
   **escrito** no `DXF_OUTPUT_SPEC` (o `Unknown` do contrato), com as parcelas rastreáveis até
   as entidades de origem.
3. A precisão da linha agrupada é a **pior** das entidades que a compõem — agrupar nunca
   promove precisão.
4. Croqui sem identidade produz CSV byte a byte igual ao de hoje.
5. O CSV continua saindo só depois de `ensure_exportable` e da auditoria do DXF.

## Validação

`uv run pytest tests/worker` verde; `make check` verde (inclui `check_docs`).
