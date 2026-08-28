# F-046 · T3 — Persistência e rotas `/v1` da praça

Feature: [F-046](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Guardar as folhas de uma rodada e o consolidado da praça, e publicar as rotas que acrescentam
folha, leem o consolidado e declaram o vínculo de identidade.

## Escopo

- `services/api/src/croquito_api/database.py` + migração nova (a última hoje é `0022`)
- `services/api/src/croquito_api/main.py`, `valuation_rounds.py`
- `tests/api/`

## Fora de escopo

- Extração das folhas novas (T4) e tela (T5)
- Entidade "obra" persistente (ADR-0028 D8 continua valendo)

## Critérios de aceite

1. As folhas da rodada deixam de ser colunas escalares e passam a tabela filha, com
   `(round_id, plate_id)` único. A migração **preserva** a folha existente como a primeira da
   praça, e é forward-only.
2. Rodada existente, migrada, produz o mesmo consolidado e o mesmo boletim de antes — provado
   por teste sobre dado gravado no formato antigo.
3. Rota para acrescentar folha à rodada; `ROUND_PLATE_ALREADY_PRESENT` deixa de ser recusa de
   segunda folha e passa a recusar apenas folha **repetida** (mesmo digest/página).
4. Rota de leitura da praça: as folhas, seus estados e o consolidado.
5. Rota de declaração do vínculo de identidade, com `Idempotency-Key` e `base_version` como as
   demais mutações; a declaração cria revisão nova, append-only.
6. `tenant_id` sempre do JWT; erro em `application/problem+json` com código estável.
7. Snapshot de OpenAPI aditivo; nenhuma rota existente muda de forma.

## Validação

`uv run pytest tests/api` verde; `make check` verde (inclui o gate de contrato da API).
