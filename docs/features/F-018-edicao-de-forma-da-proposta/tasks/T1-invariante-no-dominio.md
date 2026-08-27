# F-018 · T1 — O invariante no domínio

Feature: [F-018](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

Ensinar `VisionProposal`/`VisionProposalSet` a representar correção humana **sem afrouxar
invariante nenhum**, conforme as decisões 1, 2, 3 e 5 do
[ADR-0050](../../../adr/0050-correcao-humana-de-forma-como-proposta-derivada.md).

## Escopo

- `services/worker/src/croquito_worker/vision.py` e os consumidores de `quality_score`.

## Fora de escopo

- Rota, coluna, tela. Nenhuma escrita nova de dado nesta tarefa.
- Tipo paralelo para a correção — rejeitado pelo ADR (decisão 1).

## Critérios de aceite

1. `detector_version` aceita `human-correction-v1`.
2. `quality_score` vira `float | None`; nenhum consumidor trata ausência como zero medido nem
   como qualidade máxima.
3. `derived_from` valida formato e repetição; o **conjunto** exige origem na correção e a
   proíbe na proposta de máquina.
4. `precision` e `export` continuam `Literal` — a tentativa de promover não compila.

## Validação

`uv run mypy services packages` e `uv run pytest tests/worker` verdes.

## Resultado

Entregue. Desvio declarado no plano: quatro consumidores de `quality_score`, e não um.
