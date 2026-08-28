# F-047 — O quantitativo nasce da cena aprovada

## Status

`READY_FOR_PLANNING`

> Registrada em 2026-08-28, por seleção humana, a partir da
> [issue #102](https://github.com/biahflow/croquito/issues/102). O
> [ADR-0058](../../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md)
> foi **aceito por ato humano em 2026-08-28**, com uma emenda: só `exact` e `derived` alimentam
> a medição — `approximate` não entra, nem sob aceite explícito. A tolerância da divergência
> ficou nomeada no mesmo ato: o maior entre 1% do valor da legenda e 0,01 na unidade do item.
>
> Falta o `DESIGN_APPROVAL_REQUIRED` antes do plano — atribuir identidade de elemento é ato
> humano novo na revisão, e a divergência é tela nova na medição.

## Classification

`INTERFACE_CHANGE` — a revisão do croqui ganha um ato que não existe (declarar que estes traços
são um elemento, e qual), e a medição passa a mostrar dois números para a mesma coisa quando
eles divergem.

## Priority

`HIGH` — é a ligação que fecha as duas jornadas do produto. Hoje o croqui vira DXF auditado e a
medição lê a legenda; a área que o solver resolveu com precisão declarada é **redigitada** por
uma pessoa, e a redigitação é onde o erro entra.

## Problem

### O bloqueio real, e ele não é de esforço

A `Entity` não tem identidade de elemento. Ela tem `id` (UUIDv7, identidade de **linha**),
`kind`, `layer`, `precision`, `geometry`, `provenance`, `export` e `fill`
(`packages/core/src/croquito_core/models.py:178-202`). O que chamamos de "rótulo" é uma entidade
`TextGeometry` separada, com `text` livre de até 500 caracteres (`:131-136`), colocada na layer
`TEXTOS` — sem nenhum vínculo estruturado com a geometria que ela rotula.

`layer` é vocabulário fechado de 13 valores (`:49-63`), mas é camada de CAD, não identidade:
uma cena tem vários elementos em `MURO`.

Sem identidade, ligar "este polígono" a "o item da legenda que diz 418,12 m²" só sobraria
proximidade — que é justamente o que o produto recusa em toda parte.

### O que existe, e o que não existe

- **Existe** o cálculo: `_write_quantities`
  (`services/worker/src/croquito_worker/dxf.py:482-539`) calcula comprimento, perímetro e área
  por entidade e escreve `quantitativos.csv` com `entity_id, layer, kind, precision, length_m,
  perimeter_m, area_m2` (`:489-497`), uma linha por entidade exportável, pulando `TEXTOS`,
  `COTAS` e os `summary_code` de detalhe (`:500-513`).
- **Existe** o portão: o CSV só é escrito depois de `ensure_exportable`
  (`packages/core/src/croquito_core/models.py:294-336`) e da reabertura/auditoria do DXF.
- **Existe** a porta reservada: `TakeoffItem.source`
  (`packages/valuation/src/croquito_valuation/takeoff.py:99`), hoje
  `Literal["legend_extraction", "manual"]`.
- **Não existe** `QuantitySource`: a busca no repositório só o encontra em documentação
  (ROADMAP e o próprio ADR-0058). A porta que o roadmap cita nunca foi aberta.
- **Não existe** quantidade concorrente: hoje só há a digitada por decisão humana
  (`TakeoffItem.quantity`, `takeoff.py:97`), enviada por
  `POST /v1/valuation-rounds/{round_id}/takeoff/decisions` (`main.py:11610`) a partir do campo da
  tela (`apps/web/src/medicao/MedicaoApp.tsx:3521-3536`).

Nota estrutural que o ADR usa: a aprovação cria revisão nova com `id` novo e `version + 1`
(`main.py:10069-10094`), preservando os `id` das entidades — mas identidade de elemento precisa
sobreviver a **qualquer** revisão, não só a essa, e `Entity.id` não é feito para isso.

## Desired Outcome

Um elemento da cena aprovada tem identidade declarada; o item da legenda cita a mesma
identidade; e a quantidade que o solver já resolveu chega à medição sem ninguém redigitar. Onde
os dois números discordam, o sistema mostra os dois e abre uma issue — nunca escolhe sozinho.

## Scope

1. **`Entity.element_ref`**, campo novo e opcional, ao lado do texto livre e do `id` — nunca no
   lugar deles (ADR-0058, decisão 1). Sobrevive à criação de revisão nova. Muda
   `SceneRevision`, portanto exige `make contracts` (JSON Schema + tipos TS) e passa pelo drift
   check.
2. **Atribuição por ato humano na revisão** (decisão 2, confirmada no aceite). O sistema pode
   **propor** agrupamento — por camada, rótulo próximo, mesma `provenance` —, mas a proposta
   nasce `unresolved` e não vira identidade sem decisão registrada. Agrupamento inferido e não
   confirmado nunca alimenta quantidade.
3. **`quantitativos.csv` passa a carregar `element_ref`**, ao lado de `entity_id`, e agrupa por
   elemento quando a identidade existe. Coluna aditiva: croqui sem identidade sai como hoje.
4. **`QuantitySource`**, adaptador novo que lê o CSV do export e resolve a quantidade **por
   `element_ref`, nunca por posição, número ou proximidade** (decisão 5). Sem identidade dos dois
   lados, ele não resolve e diz isso — a ausência de par é estado legível.
5. **`TakeoffItem` ganha `element_ref` e o terceiro valor `scene_graph` em `source`**, de forma
   aditiva, com a subida de versão do contrato de takeoff.
6. **Só `exact` e `derived` alimentam** (decisão 4, emendada no aceite): entidade `approximate`
   ou `unresolved` não produz quantidade de medição, e nesses casos a legenda segue sendo a
   fonte, lida por decisão humana como hoje.
7. **Divergência é issue, com tolerância nomeada** (decisão 6): quando o mesmo elemento tem
   quantidade da cena **e** da legenda e a diferença passa do **maior entre 1% do valor da
   legenda e 0,01 na unidade do item**, abre-se issue com as duas origens à vista. Nenhuma
   sobrescreve a outra; o item não fecha enquanto a issue estiver aberta. A tolerância é
   constante nomeada, não número solto.
8. **A quantidade automática só existe a partir da cena aprovada** (decisão 7), herdando o
   portão de exportação que já existe — sem caminho novo que o contorne.
9. **Tela**: a atribuição de identidade na revisão do croqui, e na medição as duas quantidades
   com a origem de cada uma quando divergirem.

## Out of Scope

- **Casamento por proximidade, por número igual ou por rótulo** — é a rejeição central do ADR.
- **Sobrescrever** legenda com cena, ou cena com legenda.
- **`approximate` alimentando a medição**, inclusive sob aceite explícito — recusado na emenda
  do aceite humano.
- Identidade de elemento inferida automaticamente de camada + rótulo.
- Reconciliação retroativa de croquis já exportados sem identidade.
- Mudar o cálculo geométrico em si (`_write_quantities` continua calculando o que calcula).

## Acceptance Criteria

1. `Entity.element_ref` existe, é opcional, sobrevive à revisão criada na aprovação e está no
   JSON Schema e nos tipos TS gerados; `make check` verde no drift.
2. Cena **sem** `element_ref` produz `quantitativos.csv` e DXF byte a byte iguais aos de hoje
   (teste de não-regressão sobre fixture existente).
3. Identidade proposta pelo sistema nasce `unresolved` e não alimenta quantidade nenhuma
   enquanto não houver decisão humana registrada com autor e instante.
4. `QuantitySource` resolve pela identidade; sem `element_ref` em algum dos lados, **não
   resolve** e devolve o motivo — provado por teste que oferece número idêntico dos dois lados e
   verifica que ele **não** casa.
5. Entidade `approximate` ou `unresolved` nunca vira quantidade de `TakeoffItem`, mesmo com
   aceite de aproximação registrado na cena.
6. `TakeoffItem` com `source = scene_graph` carrega a precisão de origem e o `element_ref`, e o
   contrato de takeoff sobe de versão aceitando as anteriores.
7. Divergência dentro da tolerância não abre issue; fora dela abre, com os dois números, as duas
   origens e a diferença. O item não fecha com a issue aberta, e resolvê-la é decisão humana
   registrada.
8. A tolerância é constante nomeada e testada nas bordas: exatamente 1%, exatamente 0,01 e o
   caso em que 0,01 é maior que 1%.
9. Cena não aprovada, entidade `unresolved`, aproximação sem aceite ou issue crítica aberta
   continuam barrando o export — e, com ele, a quantidade.
10. `make check` e `make test` verdes; snapshot de OpenAPI aditivo.
11. Evidência renderizada (`BROWSER_REQUIRED`): a atribuição de identidade na revisão, a
    quantidade chegando à medição sem digitação, e a divergência com os dois números à vista.

## Constraints

- Precisão nunca sobe: `approximate` continua `approximate`, e agora sequer atravessa a
  fronteira para a medição.
- Nenhum caminho novo até o DXF ou até o `TakeoffItem` contorna o portão de exportação.
- Divergência recusa e explica; não concilia sozinha.
- `SceneRevision` é a única fonte geométrica; nada vira geometria fora dela.

## Dependencies

- [ADR-0058](../../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md) —
  `Accepted` em 2026-08-28, com emenda.
- [ADR-0053](../../adr/0053-cardinalidade-n-n-elemento-servico.md) — a cadeia elemento → item de
  legenda → N serviços; a `ContributionBasis` `DERIVED` finalmente tem de onde derivar.
- **[F-046](../F-046-praca-de-varias-pranchas/feature.md)** — a identidade do item de takeoff
  passa a ser `(plate_id, item_id)`. Construir o elo antes disso obrigaria a refazê-lo depois.
- Design Approval Package aprovado (gate humano, abaixo).

## Unknowns

- Que forma tem `element_ref` (string declarada pelo humano? id opaco cunhado no ato? escopo da
  unicidade — cena, job ou praça?) — decisão do plano, dentro da forma já escolhida no aceite.
- Se a proposta de agrupamento entra nesta feature ou numa fatia posterior — a feature funciona
  sem ela, e ela é o que torna o ato barato.
- Como o `quantitativos.csv` agrupa quando um elemento tem várias entidades (soma de áreas? uma
  linha por elemento com as parcelas?) — decisão do plano, com o
  [DXF_OUTPUT_SPEC](../../architecture/DXF_OUTPUT_SPEC.md) atualizado junto.

## Risks

| Risco | Mitigação |
|---|---|
| Casamento silencioso por proximidade voltar por alguma porta | AC 4: teste que oferece número idêntico e exige que **não** case |
| Aproximação virar linha de R$ no boletim | Emenda do aceite + AC 5 |
| Divergência ser resolvida por sobrescrita | Decisão 6 + AC 7: issue aberta bloqueia o fechamento |
| Croqui existente mudar de digest | AC 2: byte a byte sem identidade declarada |
| Ato de identidade ficar caro demais e ninguém usar | Proposta do sistema (decisão 2) como fatia seguinte; a feature não depende dela para estar correta |
| Chave nova conflitar com a chave da praça | Dependência declarada de F-046 |

## Human Gates

- ~~Aceite do ADR-0058~~ — **satisfeito em 2026-08-28** (Daniel Campos), com a emenda da
  decisão 4 e a tolerância da decisão 6 fixada.
- `DESIGN_APPROVAL_REQUIRED`: pacote de design da atribuição de identidade na revisão e da
  divergência na medição, **pendente**.
- Merge do PR e o aceite que fecha a [issue #102](https://github.com/biahflow/croquito/issues/102),
  num croqui real cuja quantidade chega à medição sem redigitação.

## References

- [ADR-0058](../../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md)
- [Issue #102](https://github.com/biahflow/croquito/issues/102)
- [ROADMAP](../../product/ROADMAP.md), "Próximo — medição além do v1"
