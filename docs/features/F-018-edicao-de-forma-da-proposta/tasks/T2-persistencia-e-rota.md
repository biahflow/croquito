# F-018 · T2 — Coluna própria e a rota de correção

Feature: [F-018](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

Gravar a correção num conjunto separado e publicá-la em `/v1`, sem tocar a observação.

## Escopo

- Migração `0019`, `database.py`, `main.py` (contrato de entrada, rota, resposta e o carregar
  de contexto entre revisões), `tests/api/test_api.py`, snapshot de OpenAPI e API Contract.

## Fora de escopo

- Aceitar a correção no mesmo ato (reservado no pacote de design).
- Qualquer caminho que promova precisão.

## Critérios de aceite

1. Correção cria revisão nova e **não** altera `proposals_json`.
2. `derived_from` vazio, fora do snapshot, ou apontando para proposta já decidida é recusado.
3. Concorrência recusa por `base_review_version`/`base_scene_version`.
4. A correção sobrevive a **qualquer** ato posterior da revisão.
5. Idempotência: mesma chave devolve a mesma revisão, sem duplicar a forma.

## Validação

`uv run pytest tests/api` verde, incluindo os sete testes novos de correção; `make check` = 0
com o snapshot regenerado e o API Contract atualizado.

## Resultado

Entregue. O helper que carrega contexto entre revisões foi ampliado para não deixar nenhum dos
dez caminhos de escrita esquecer a correção — era o defeito mais provável desta tarefa.
