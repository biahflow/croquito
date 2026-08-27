# F-018 — Corrigir a forma da proposta na tela, sem rerodar o provider

## Status

`READY_FOR_REVIEW`

> Registrada em 2026-08-19, por seleção humana, e **especificada em 2026-08-23** por seleção
> humana nova, junto da [F-019](../F-019-preview-da-cena-resolvida/feature.md) — as duas foram
> escolhidas por serem as que melhoram a geometria das cotas, na mesma linha da
> [F-030](../F-030-levantamento-de-campo-na-revisao/feature.md).
>
> **Os dois gates humanos foram cumpridos.** O
> [ADR-0050](../../adr/0050-correcao-humana-de-forma-como-proposta-derivada.md) foi aceito em
> 2026-08-23, e o **Design Approval Package** foi **aprovado por ato humano em 2026-08-27**,
> revisão 1 ([mock/README.md](mock/README.md)).
>
> **Implementada em 2026-08-27**, com portões verdes: domínio, migração `0019`, a rota
> `POST /v1/jobs/{job_id}/review/proposals/corrections` e a tela. A evidência está em
> [evidence.md](evidence.md); o que falta é revisão humana, merge e o aceite numa rodada real.

## Classification

`INTERFACE_CHANGE` — editar forma é interação nova na tela de revisão, com estados próprios.

## Priority

`HIGH` — hoje o único caminho para corrigir uma forma errada é **trocar o prompt e rerodar o
provider pago**. É a correção mais cara possível para o erro mais barato de ver.

## Problem

### O caso real que a originou

Primeira revisão em nuvem do Guaxindiba V3: o muro com recuo **4,80 → 3,30** chegou
**fragmentado** da extração paga — duas `line` retas sob `geometry-extraction@2.0.1`, no lugar
de uma forma com o recuo. A revisora viu o erro na hora e não tinha o que fazer com ele.

As opções que existiam eram todas piores que o problema:

- **rejeitar as duas propostas** e ficar sem a geometria;
- **aceitar como está** e exportar um muro que não tem o recuo;
- **trocar o prompt e rerodar o provider**, que custa dinheiro, leva minutos, e conserta
  aquele caso mudando o comportamento de todos os outros.

### O que a tela permite hoje

`DecideProposalRequest` (`services/api/src/croquito_api/main.py:774`) aceita exatamente duas
ações: `accept` e `reject`, com justificativa. Não há vértice para arrastar, não há como unir
dois fragmentos, não há como declarar um recuo. A proposta é imutável desde que nasce, e a
única coisa que o humano decide sobre ela é **se** ela entra, nunca **qual é a forma dela**.

Isso é coerente com o resto do produto — proposta é observação de máquina, e observação não se
adultera. E é justamente por isso que a saída não pode ser "deixar editar": tem de ser outra
coisa, que preserve a observação original.

## Desired Outcome

A revisora corrige a forma na tela — une os dois fragmentos, move um vértice, declara o recuo
— e o que sai disso é uma proposta **nova**, de origem humana, ao lado da observação original,
que permanece intacta e legível.

Nenhuma chamada paga, nenhum redeploy, nenhum prompt novo. E nenhuma promoção de precisão: uma
forma desenhada à mão continua sendo aproximação até que uma cota confirmada a resolva.

## Scope

### A edição cria proposta nova; não altera a existente

Append-only, como o resto do produto. A proposta da máquina fica onde está, com o seu
`algorithm`, o seu `quality_score` e a sua proveniência; a corrigida nasce com origem humana,
declarando **de quais** propostas ela derivou e **quem** a produziu. É o mesmo princípio do
[ADR-0019](../../adr/0019-proposal-refresh-creates-a-new-review-revision.md), onde refinar
propostas cria revisão de leitura nova em vez de sobrescrever.

Sem isso, a comparação entre o que o modelo viu e o que o humano corrigiu — que é o insumo de
qualquer melhoria de prompt — desaparece na primeira correção.

### Três operações, e a terceira é a que o caso real pedia

```text
mover vértice     ajustar um ponto da forma
inserir/remover   acrescentar ou tirar um vértice
unir fragmentos   duas ou mais propostas viram UMA forma com o recuo entre elas
```

A união é o que resolve o Guaxindiba: duas `line` retas viram uma polilinha com o degrau.

### Precisão não sobe por causa da edição

A forma editada continua `unresolved` em pixels e só chega a `approximate` pelo mesmo caminho
que qualquer outra: calibração. **Nada desenhado à mão vira `exact`** — dimensão exata só
nasce de cota confirmada, e essa regra não tem exceção para vértice arrastado com capricho.

### A origem viaja com a forma

`VisionProposalSet` já declara quem produziu o conjunto — detector OpenCV local ou extração
paga. A proposta de origem humana declara o mesmo, e com o mesmo peso: quem olhar a cena
depois precisa poder distinguir o que a máquina viu do que a pessoa desenhou.

## Out of Scope

- **Editar entidade da cena** (`SceneRevision`). O alvo é a proposta, que é observação em
  pixels. Entidade métrica resolvida é outra coisa e tem outro portão.
- **Promover precisão pela edição** — ver `Scope`.
- **Desenhar forma do zero, sem proposta de origem.** Uma forma sem observação por trás não é
  correção, é desenho — e o produto tem um lugar para desenho, que é o CAD.
- **Mudar prompt, modelo ou roteamento.** A feature existe justamente para não precisar.
- **O achado do portão de exportação**, registrado na linha da F-018 no roadmap e repetido
  aqui para não se perder: quando uma leitura confirmada **não é aplicada**, a issue
  correspondente nasce apenas `warning` e a cena permanece exportável com a entidade `exact`
  que ela contradiz. É candidato a trabalho em `SceneRevision.export_errors()`, e virar
  bloqueio é **decisão humana pendente** — não desta feature.

## Acceptance Criteria

1. `make check` e `make test` verdes; goldens intocados.
2. Revisão sem edição se comporta exatamente como hoje.
3. Editar cria proposta **nova**; a original permanece legível e inalterada — coberto por
   teste que lê as duas depois da edição.
4. A proposta editada declara origem humana, autor e as propostas de que derivou.
5. Unir dois fragmentos produz **uma** forma, e o caso do Guaxindiba (duas `line` → polilinha
   com recuo) tem teste próprio com a fixture real.
6. A forma editada nasce `unresolved` e `export=false`, como qualquer proposta — teste
   negativo explícito de que ela não vira `exact`.
7. Edição concorrente recusa por `base_review_version`/`base_scene_version`, como as demais
   mutações da revisão.
8. A tela corresponde à revisão aprovada do Design Approval Package.

## Constraints

- `tenant_id` do JWT; edição de proposta de outro tenant é `404`.
- Operações allowlisted com `base_version`, como toda edição da SPA já é.
- A SPA não resolve geometria: ela envia a operação, e o servidor valida a forma resultante.
- Justificativa obrigatória, como em `accept`/`reject` — corrigir forma é decisão de domínio.
- Cor nunca é o único indicador da origem da forma.

## Dependencies

- [ADR-0019](../../adr/0019-proposal-refresh-creates-a-new-review-revision.md) — o precedente
  de "refino cria revisão nova em vez de sobrescrever".
- [ADR-0005](../../adr/0005-canonical-scene-graph.md) e
  [ADR-0006](../../adr/0006-human-review-and-provenance.md) — precisão e proveniência.

## Unknowns

Os dois primeiros são decisão do ADR.

1. **A proposta de origem humana é um `VisionProposal` com origem nova, ou um tipo próprio?**
   `VisionProposal.precision` é `Literal["unresolved"]` e `algorithm` é string livre; caberia.
   Mas chamar de "visão" o que ninguém viu é dívida de nome, e o campo `quality_score` não tem
   significado para forma desenhada por pessoa.
2. **A união preserva os fragmentos como propostas próprias, ou os consome?** Preservar mantém
   a trilha completa e polui a lista com formas que ninguém quer mais ver; consumir limpa a
   tela e apaga o que o modelo entregou. Provavelmente preservar e ocultar — mas ocultar é
   estado novo, e estado novo é decisão.
3. **Qual a tolerância de "vértice movido demais"?** Arrastar um ponto 2 px é ajuste; arrastar
   40 cm de escala é outra forma. Se houver limite, ele é nomeado e declarado; se não houver,
   isso é dito por escrito.
4. **A edição entra na etapa Decisões ou numa etapa própria?** A jornada guiada da
   [F-011](../F-011-jornada-guiada-da-revisao/feature.md) tem quatro etapas, e a correção de
   forma não é decisão de leitura. Sai no pacote de design.

## Risks

- **Adulterar a observação.** O risco central: se a edição sobrescrever a proposta da máquina,
  o produto perde a única medida objetiva de quanto o modelo erra — e é dela que sai a próxima
  melhoria de prompt.
- **Forma bonita e errada.** Um vértice arrastado até "ficar certo" parece mais confiável que
  uma proposta bruta, e não é. Daí a precisão não subir e a origem viajar visível.
- **Substituir revisão por desenho.** Se editar for mais fácil que decidir, a revisão vira
  edição de CAD dentro do navegador. Mitigação: a edição parte sempre de uma proposta e exige
  justificativa.
- **Concorrência.** Duas pessoas corrigindo a mesma forma é o caso que `base_version` já cobre
  no resto da revisão, e precisa cobrir aqui.

## Human Gates

1. **`ARCHITECTURE_DECISION_REQUIRED`** — ✅ **cumprido em 2026-08-23**. O
   [ADR-0050](../../adr/0050-correcao-humana-de-forma-como-proposta-derivada.md) foi **aceito
   por ato humano**: decide os Unknowns 1 e 2.
2. **`DESIGN_APPROVAL_REQUIRED`** — Design Approval Package da interação de edição, com os
   estados de arrasto, união, erro e concorrência, conforme
   [design-approval](../../engineering-os/workflows/design-approval.md).

Nenhum agente cumpre nenhum dos dois.

## References

- [Roadmap](../../product/ROADMAP.md) — a linha da F-018 e o caso do Guaxindiba V3
- [ADR-0019](../../adr/0019-proposal-refresh-creates-a-new-review-revision.md)
- `services/worker/src/croquito_worker/vision.py` — `VisionProposal`, `VisionProposalSet`
