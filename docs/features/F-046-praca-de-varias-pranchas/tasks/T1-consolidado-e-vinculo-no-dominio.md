# F-046 · T1 — O consolidado da praça e o vínculo de identidade no domínio

Feature: [F-046](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Criar o consolidado de praça como artefato que **referencia** pacotes de prancha sem
absorvê-los, e o vínculo de identidade declarado que funde duas leituras de folhas diferentes.
Nada de rota, nada de tela, nada de escrita de dado.

## Escopo

- `packages/valuation/src/croquito_valuation/` — módulo novo do consolidado (`WorksiteTakeoff`)
  e o vínculo de identidade
- `tests/valuation/` — arquivo novo de testes do consolidado e do vínculo

## Fora de escopo

- `TakeoffPacket` e `CodeAssignmentSet` não ganham campo (ADR-0057, decisão 8)
- Boletim, planilha, persistência, rotas e tela (T2 em diante)

## Critérios de aceite

1. `WorksiteTakeoff` lista os pacotes da praça por `plate_id` **e digest do pacote**, com
   `schema_version` próprio, e **não** contém itens — só referências (decisão 2).
2. Referência a pacote cujo digest não confere é recusada com erro nomeado; `plate_id`
   repetido no mesmo consolidado também.
3. Todo item é endereçado pelo par `(plate_id, item_id)` (decisão 5). Teste com dois pacotes
   que cunham o **mesmo** `item_id` prova que nada se confunde.
4. O vínculo de identidade é tipo próprio, entre **dois pares** `(plate_id, item_id)`, com
   `declared_by`, `declared_at` (com fuso), `note` obrigatória e o campo **"a parcela que
   fica"** — a leitura que governa a quantidade (decisão 9 do pacote de design).
5. Vínculo entre itens da **mesma** folha recusa (`WORKSITE_LINK_SAME_PLATE`); sem autor,
   instante ou nota recusa (`WORKSITE_LINK_INCOMPLETE`); apontando para item inexistente
   recusa. Os três nomes ficam fixados aqui.
6. Vínculo em cadeia (A≡B e B≡C) é recusado ou reduzido a um grupo explícito — a escolha é
   registrada no código com o motivo; o que **não** pode é o total depender da ordem de
   avaliação.
7. Nada funde por rótulo, unidade, quantidade ou proximidade. Teste que oferece dois itens
   idênticos em folhas diferentes prova que eles seguem contando **dois**.

## Validação

`uv run pytest tests/valuation` verde; `uv run mypy packages` limpo.
