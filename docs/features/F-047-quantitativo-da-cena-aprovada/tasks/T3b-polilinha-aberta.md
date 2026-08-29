# F-047 · T3b — Polilinha aberta tem comprimento

Feature: [F-047](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Por que existe

`_entity_quantities` (`services/worker/src/croquito_worker/dxf.py`) devolvia
`(None, None, None)` para `PolylineGeometry` com `closed=False`: só linha, polilinha
**fechada** e círculo produziam grandeza. Um muro ou alambrado traçado como polilinha aberta
tem comprimento real e saía do `quantitativos.csv` sem número nenhum.

A lacuna é anterior à feature, e ficou visível quando a T4 fez a quantidade da cena atravessar
para a medição: um elemento assim resolveria como `QUANTITY_ABSENT` e continuaria exigindo
digitação — a F-047 cobriria menos do que aparenta.

**Decisão humana de 2026-08-29** (Daniel Campos): consertar agora, aceitando que o
`quantitativos.csv` de croqui com polilinha aberta passe a trazer número onde antes saía vazio.

## Critérios de aceite

1. Polilinha aberta contribui `length_m` = soma euclidiana dos segmentos, e **nenhum** perímetro
   ou área — aberta não fecha região, e inventar área seria geometria fabricada.
2. Polilinha fechada continua exatamente como está.
3. O agrupamento por `element_ref` da T3 continua valendo, com a precisão da linha agrupada
   sendo a **pior** do grupo.
4. Âncoras de digest são **reancoradas com explicação**, nunca apagadas nem afrouxadas.
5. `DXF_OUTPUT_SPEC` diz qual grandeza cada tipo de geometria contribui.

## Resultado

Entregue em 2026-08-29. Nenhuma âncora precisou ser reancorada: a fixture sintética não tem
polilinha nenhuma (verificado antes da implementação), então o critério 4 não teve o que
exercer. Spline e arco seguem sem produzir grandeza — mudar isso é outra decisão.
