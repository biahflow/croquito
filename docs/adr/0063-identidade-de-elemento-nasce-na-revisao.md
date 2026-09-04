# ADR-0063: A identidade de elemento nasce na revisão, sobre propostas — e o traçado a transporta

Status: Accepted  
Data: 2026-09-04 (caminho escolhido e ADR aceito por ato humano na mesma data, Daniel
Campos, pelo chat)  
Responsável: Product / Engineering

## Contexto

A primeira revisão completa de croqui real (Campo da Toca, 2026-09-03) expôs um limite de
desenho do funil de associação, registrado na issue
[#139](https://github.com/biahflow/croquito/issues/139). O técnico usa **cota-balão**: a
medida escrita longe do elemento, ligada a ele por letra (`(B) → C=56m, h=4,40`). O funil
(`services/worker/src/croquito_worker/association.py`, `pixel-proximity-associator-v1`)
gera candidatas **só por proximidade de pixel** — para cota-balão isso não é impreciso, é
**impossível por construção**: as candidatas são os riscos vizinhos da nota, nunca o
referente a ~2000px.

O caminho honesto disponível hoje é `annotation=true` — que dispensa a associação sem
afrouxar a regra, mas ao custo de a medida confirmada **não constranger geometria**: no
traçado em lote, `note_associations` é um dicionário separado de `span_targets`
(`tracing.py:1459-1476`) e nunca vira constraint. O `C=56m` do fecho, cota de verdade
confirmada por humano, ficou fora do solver na rodada real.

Três fatos do código tornam o problema resolúvel:

1. **A extração já entrega a identidade**: `TargetHint.entity_label` chega estruturado do
   provider ("A", "B", "arquibancada 1" — sem ninguém pedir, na rodada real), mas é
   **achatado para string** em `provider_review.py:777-780` e nunca consumido; o comentário
   do código diz de propósito que "hint é dica de leitura, não amarração".
2. **As propostas de geometria chegam rotuladas**: a chamada de geometria do Toca devolveu
   11 elementos, 100% rotulados (grade A/C/D, arquibancadas 1/2).
3. **A identidade de elemento existe no produto, mas só DEPOIS do solver**: `element_ref`
   ([ADR-0058](0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md)) é campo de `Entity` dentro de
   `SceneRevision` (`croquito_core/models.py:219`), cunhado pelo sistema no ato humano de
   declaração (`POST /v1/jobs/{id}/elements`), nunca inferido. Não há identidade em
   leitura, proposta ou candidata — grep confirma zero ocorrências de `element_ref` em
   `vision.py`, `association.py`, `review.py`, `rectangle_solver.py`, `tracing.py`.

A pergunta de arquitetura: **onde a identidade nasce para que a cota-balão alcance seu
elemento antes de a cena existir?** Três caminhos foram apresentados ao dono em 2026-09-04
(ver Alternativas); ele escolheu o desenho completo.

## Decisão

1. **A identidade de elemento pode ser declarada na REVISÃO, sobre um conjunto de
   propostas.** O ato é o mesmo do ADR-0058, uma etapa antes: humano declara, o sistema
   cunha `EL-NNN` sequencial (nunca digitado, nunca reaproveitado), o rótulo legível ("B")
   entra no mesmo ato. Modelo e CV continuam sem autoridade: os rótulos que a extração de
   geometria devolve viram **sugestão assistida** (molde da proposta de agrupamento da
   F-047 T6), que o humano confirma ou rejeita — nada é declarado sozinho.
2. **O namespace de `element_ref` é um só por job.** O contador é compartilhado entre a
   declaração da revisão e a da cena; o **traçado transporta a identidade**: entidade
   criada a partir de proposta identificada nasce com o `element_ref` e o rótulo
   (`SceneRevision.element_labels`), respeitando os invariantes existentes do modelo. O
   ato pós-cena (F-047 T2) continua valendo para o que a revisão não identificou.
3. **O funil ganha candidata por identidade.** Leitura cujo `target_hint.entity_label`
   casa com o rótulo de um elemento declarado vira candidata de **todas as propostas
   daquele elemento**, com `relation="element_identity"`, independente de distância.
   Observacional como sempre: ranqueia, nunca confirma; nasce `unresolved`/`export=false`;
   o portão "a associação selecionada precisa ser candidata da leitura" continua sendo o
   único caminho de confirmação.
4. **`target_hint` deixa de ser achatado.** `entity_label` sobrevive como campo próprio da
   leitura até a revisão (a forma legível continua existindo para exibição); é ele que o
   casamento do item 3 consome, e é ele que o revisor corrige quando o modelo leu a letra
   errada — corrigir o hint já é ato previsto na decisão de revisão.
5. **A assimetria do traçado em lote fica declarada como desenho.** As associações de
   `POST /v1/jobs/{id}/trace-solves` são declaração humana de vão e validam existência da
   proposta, não pertencimento a candidatas (`main.py:12138-12168`); o portão de
   candidatas governa o ato de confirmação da revisão. Estava implícito; passa a estar
   escrito.

## Consequências

- A cota-balão confirmada passa a constranger o solver **pelo caminho que já existe**
  (associação confirmada → `span_targets`); o `C=56m` do Toca entra na geometria em vez de
  morrer como anotação.
- Balão cujo referente **não tem proposta** continua no caminho de hoje (`annotation=true`).
  O complemento — ligar anotação confirmada a elemento da cena e re-resolver (caminho C da
  discussão) — fica registrado como evolução possível, **não decidida aqui**.
- Contratos mudam: leitura com `entity_label` estruturado, candidata com relação nova, o
  ato de declaração na revisão e o transporte pelo traçado. `make contracts` e versões de
  schema acompanham; a fatia exata é da feature
  ([F-051](../features/F-051-cota-balao-encontra-seu-elemento/feature.md)).
- A superfície é a revisão (worker + API + web) e o transporte no traçado; os internos do
  solver não mudam.

## Alternativas consideradas

- **Casamento de rótulo sem identidade pré-cena** (candidata observacional
  `entity_label` × rótulo da proposta, sem ato novo): a menor mudança que resolvia o caso
  observado, mas deixa a identidade não-durável (a letra nunca vira `element_ref` e o elo
  croqui→cena→quantitativo se perde). Preterida pelo dono em 2026-09-04 em favor do
  desenho completo.
- **Segundo passe pós-traçado** (anotação confirmada vira constraint ligada ao elemento já
  identificado na cena, com re-solve): não mexe no funil e é o único caminho para balão sem
  proposta, mas a medida chega tarde — o primeiro solve roda sem ela. Fica como
  complemento futuro, não como fundação.
- **Não fazer nada** (annotation=true para sempre): mantém medida confirmada por humano
  fora da geometria — exatamente o custo que a rodada real mediu.
