# F-051 — A cota-balão encontra seu elemento: identidade declarada na revisão

## Status

`READY_FOR_BUILD`

> **ADR-0063 aceito em 2026-09-04** (Daniel Campos, pelo chat) — gate 1 cumprido.
>
> **DAP revisão 1 aprovado por ato humano em 2026-09-04** (Daniel Campos, pelo chat, após o
> merge do PR #157 — [mock/README.md](mock/README.md)), com as duas leituras do pacote
> confirmadas: rótulo de elemento único por job na revisão, e revogação que não desfaz
> associação já confirmada. **Os dois gates que precedem o planejamento estão cumpridos.**
>
> **Plano congelado em 2026-09-04** ([plan.md](plan.md), `PLAN_VALID`): 7 tarefas,
> `(T1 ∥ T2) → (T3 ∥ T5) → T4 → T6 → T7`, contratos em [tasks/](tasks/). Os Unknowns 1 e 2
> foram resolvidos ou designados no plano (achados 1 e da T4).
>
> Nasce em 2026-09-04 da issue
> [#139](https://github.com/biahflow/croquito/issues/139), aberta pela primeira revisão
> completa de croqui real (Campo da Toca): 3 das 37 leituras eram cotas-balão — medidas
> confirmadas por humano que ficaram **fora do solver** porque o funil por proximidade não
> alcança o referente por construção, e `annotation=true` não constrange geometria. O dono
> escolheu o desenho completo (identidade nasce na revisão) entre os três caminhos
> apresentados; a decisão de arquitetura está no ADR-0063.

## Classification

`INTERFACE_CHANGE` — a tela de revisão ganha o ato de declarar elemento sobre propostas e
a associação por identidade; o pacote de revisão e a cena mudam de contrato.

## Priority

`HIGH` — é a ponte que faltava na cadeia croqui→cena→quantitativo (F-047): sem ela, cota
de verdade confirmada por humano não vira constraint quando o técnico escreve longe do
elemento — e o corpus real mostra que ele escreve (balões A/B/C/D em todas as folhas).

## Problem

Verificado em código e em rodada real:

1. `association.py` (`pixel-proximity-associator-v1`) gera candidatas só por distância de
   pixel (`associate_readings`, ranking por `(pixel_distance, -visual_quality_score)`);
   cota-balão a ~2000px do referente nunca vira candidata.
2. O escape honesto, `annotation=true`, dispensa a associação mas não constrange: no
   traçado em lote, `note_associations` é separado de `span_targets`
   (`tracing.py:1459-1476`) e não gera `Constraint`.
3. A identidade já chega da extração (`TargetHint.entity_label` — "A", "B",
   "arquibancada 1" na rodada real) e é achatada para string informativa em
   `provider_review.py:777-780`; nunca é consumida.
4. `element_ref` (ADR-0058) só existe pós-solve, em `Entity`/`SceneRevision`
   (`croquito_core/models.py:219`, `:308`), cunhado por `POST /v1/jobs/{id}/elements`.

## Desired Outcome

O revisor declara, na revisão, que um conjunto de propostas É o elemento "B" (com o
sistema cunhando o `element_ref`, sugestões assistidas vindas dos rótulos do modelo); a
leitura com hint "B" ganha candidatas por identidade; a confirmação humana segue pelo
portão de sempre; o solver recebe a constraint pelo caminho existente; e o traçado
transporta a identidade para a cena — a letra do balão vira o `element_ref` da entidade,
fechando o elo croqui→cena→quantitativo.

## Scope

1. **`entity_label` estruturado na leitura**: `DimensionReading` ganha o campo (a string
   legível continua para exibição); `provider_review.py` deixa de achatar; decisão/
   retificação continuam podendo corrigi-lo (ato já previsto).
2. **Ato de declaração na revisão**: `ElementDeclaration` no nível da revisão (conjunto de
   `proposal_ids` + rótulo), ref cunhado pelo sistema no namespace único do job (mesmo
   contador de `_next_element_ref`); revogação/renomeação no molde da F-047 T2; sugestões
   assistidas a partir dos rótulos das propostas de geometria (molde F-047 T6) — nunca
   auto-declaradas.
3. **Candidata por identidade** em `association.py`: `relation="element_identity"` para
   toda proposta do elemento cujo rótulo casa com o `entity_label` da leitura,
   independente de distância; `unresolved`/`export=false` como as demais; o portão
   `_apply_association_rules` (API) permanece o único caminho de confirmação.
4. **Transporte no traçado**: entidade criada de proposta identificada nasce com
   `element_ref`/rótulo (`tracing.py` → `SceneRevision.element_labels`), respeitando os
   invariantes do modelo (camada única por ref etc.).
5. **Tela da revisão**: declarar/desfazer identidade sobre propostas, ver o hint da
   leitura, e as candidatas por identidade distinguidas das de proximidade no seletor de
   associação.
6. **Contratos**: `make contracts` (scene) e versões de schema dos pacotes tocados.

## Out of Scope

- **Balão sem proposta** (referente que o CV/modelo nunca propôs): continua
  `annotation=true`. O segundo passe pós-traçado (caminho C) fica como evolução futura,
  registrado no ADR-0063 — não entra aqui.
- **Auto-confirmação de qualquer espécie**: rótulo do modelo é sugestão; identidade e
  associação continuam atos humanos.
- **Mudar o ranking de proximidade** existente ou o portão do traçado em lote (a
  assimetria vira texto no ADR, não código aqui).
- **O resíduo de leitura a 180°** da #138 (prompt) — outra frente.

## Acceptance Criteria

1. No caso real do Toca (job de referência), a leitura `C=56m` com hint "B" ganha
   candidata por identidade para a(s) proposta(s) do elemento B declarado, é confirmável
   pelo portão de sempre, e **entra no solver** como constraint — medida no traçado, não
   mais anotação.
2. Leitura com hint que não casa com elemento declarado: comportamento de hoje, sem
   candidata nova.
3. Declaração é humana: nenhuma identidade nasce sem ato, e a sugestão assistida
   rejeitada não reaparece confirmada em lugar nenhum.
4. A entidade criada pelo traçado a partir de proposta identificada carrega o
   `element_ref` e o rótulo na cena aprovada; o quantitativo da F-047 agrupa por ele.
5. Contratos regenerados sem drift; `make check`/`make test` verdes; evidência de
   navegador da tela nova (`BROWSER_REQUIRED`).

## Constraints

- `element_ref` nunca digitado, nunca inferido, nunca reaproveitado (ADR-0058, preservado
  pelo ADR-0063).
- Candidata é observação: `precision="unresolved"`, `export=false`, nunca confirma nada.
- Namespace único por job entre revisão e cena — colisão de contador é defeito, não caso.

## Dependencies

- [ADR-0063](../../adr/0063-identidade-de-elemento-nasce-na-revisao.md) — **Accepted em
  2026-09-04** (gate 1 cumprido).
- [ADR-0058](../../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md)
  — Accepted; esta feature estende o ato para a revisão sem mudar o princípio.
- F-047 (DONE) — o ato de identidade na cena, a proposta assistida (T6) e o quantitativo
  por elemento que esta feature alimenta.

## Unknowns

1. **Casamento de rótulo é exato ou normalizado?** "B" × "grade B" × "alambrado B" — a
   rodada real sugere que o modelo varia a forma. Decidir na fatia 1 com o dado do job de
   referência (normalização mínima e declarada, nunca fuzzy silencioso).
2. **Onde a `ElementDeclaration` persiste** (revisão versionada como decisões/associações,
   com `base_version`): a resposta natural é o mesmo lugar dos demais atos da revisão —
   confirmar no planejamento contra `insert_review_revision_v1`.

## Risks

- **Duas identidades divergindo** (revisão × cena) se o transporte falhar em algum caminho
  de re-solve: o invariante "namespace único + transporte no traçado" precisa de teste de
  round-trip, não só de caminho feliz.
- **Sugestão assistida virando confirmação de fato** por UX apressada — o mock do DAP
  precisa mostrar a fronteira sugerido/declarado com a mesma dureza que a F-047 T6 usou.
- **Rótulo errado do modelo** guiando o revisor: a candidata por identidade aparece AO
  LADO das de proximidade, nunca no lugar — quem decide continua vendo a folha.

## Human Gates

1. ~~**Aceite do ADR-0063**~~ — **cumprido em 2026-09-04** (Daniel Campos, pelo chat).
2. ~~**Design Approval Package** da tela~~ — **cumprido em 2026-09-04** (Daniel Campos,
   pelo chat): revisão 1 aprovada com as duas leituras confirmadas — rótulo único por job e
   revogação que não desfaz associação confirmada ([mock/README.md](mock/README.md)).
3. Aceite final contra o caso real do Toca (critério 1).

## References

- `services/worker/src/croquito_worker/association.py` — funil e candidatas.
- `services/worker/src/croquito_worker/provider_review.py:777-780` — achatamento do hint.
- `services/api/src/croquito_api/main.py:6611-6652` — portão de candidatas; `:5772` —
  `_next_element_ref`; `:11258-11567` — atos de identidade na cena (F-047 T2).
- `services/worker/src/croquito_worker/tracing.py:1430-1476` — `span_targets` ×
  `note_associations`.
- `packages/core/src/croquito_core/models.py:211-357` — `element_ref`/`element_labels` e
  invariantes.
