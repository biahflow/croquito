# F-040 · T4 — A memória mostra contratado → vigente com a RE-RA

Feature: [F-040](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Planejado**

## Objetivo

Fazer a memória e o boletim exibirem o vigente derivado e a declaração que o produziu — quem
declarou, quando e contra qual publicação —, no mesmo lugar em que a F-039 mostra o reajuste.

## Escopo

- `packages/valuation/src/croquito_valuation/workbook_writer.py`,
  `template.py`, `canonical.py` (adaptação ao vigente derivado).
- `services/worker/src/croquito_worker/valuation/` conforme o boletim precise.
- `tests/valuation/test_writer_roundtrip.py`, `test_template.py`.

## Fora de escopo

- Tela web (T5). Layout impresso do MAPÃO/boletim, que segue o modelo da prefeitura.

## Critérios de aceite

1. A memória mostra contratado → vigente por código, com a RE-RA que produziu a diferença
   carimbada (autor, instante, citação); sem RE-RA, contratado e vigente repetem o mesmo
   número de propósito (mock, decisão 4).
2. Não existe campo onde o vigente seja escrito: ele aparece como resultado de uma conta
   visível (mock, decisão 6; ADR-0056, decisão 3).
3. O roundtrip de escrita/leitura preserva a procedência da RE-RA e o schema `4.0.0`.

## Validação

`uv run pytest tests/valuation` verde; `uv run mypy packages` limpo.
