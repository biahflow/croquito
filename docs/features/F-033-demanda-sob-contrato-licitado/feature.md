# F-033 — Demanda sob contrato licitado: cascata restrita à tabela contratual

## Status

`DONE`

> Código completo na `main` (T1–T4, incluindo a ampliação da revisão 2 "regime na
> abertura" em `a5b5d35`, com e2e em `36b512c`). **Deploy e aceitação confirmados por ato
> humano em 2026-08-25** (Daniel Campos). Este flip reconcilia o roadmap, que ficara em
> `READY_FOR_HUMAN_REVIEW` após o merge.

> Nasce em 2026-08-21, de uma conversa de operação: mapeando a cadeia real das praças
> (levantamento → DXF → prancha → orçamento → aprovação → empresa executora), ficou
> visível que o fluxo do usuário é um **terceiro estado** que o
> [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md) não representa.
>
> Eram **dois gates humanos**. O primeiro foi cumprido: o
> [ADR-0045](../../adr/0045-terceiro-estado-demanda-sob-contrato.md) refina a fronteira
> binária do ADR-0027 num terceiro estado e foi **aceito por ato humano em 2026-08-22**,
> fixando as três decisões que este contrato marcava como "decisão do ADR, não do plano".
>
> O segundo também: o **Design Approval Package** (`DESIGN_APPROVAL_REQUIRED`) foi
> **aprovado por ato humano em 2026-08-22**, revisão 1, registro em
> [mock/README.md](mock/README.md). Com os dois gates cumpridos, a feature está
> `READY_FOR_PLANNING`. A implementação deve corresponder à revisão aprovada; divergir dela
> é revisão nova, com registro próprio.
>
> **Revisão 2 do pacote, aberta e APROVADA em 2026-08-22**: a tela construída afirma um
> regime onde não há rodada, e obriga a abrir em pré-licitação para declarar depois. O
> escopo 6 registra a ampliação, e o gate de design dela está cumprido — implementada em
> `a5b5d35` (T3+T4).

## Classification

`INTERFACE_CHANGE` — cria superfície nova percebida por humano: o selo de "rodada sob
contrato" no cabeçalho e na aba Cascata, e a recusa de fonte fora da tabela contratual no
momento da instalação. Exige Design Approval Package aprovado antes do planejamento,
conforme [design-approval](../../engineering-os/workflows/design-approval.md).

## Priority

`HIGH` — o defeito que ela previne nasce silencioso e só se manifesta no pagamento, meses
depois, sobre serviço já executado.

## Problem

O [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md) fixou uma
fronteira **binária** entre dois momentos com regras de preço opostas:

- **pré-licitação** → orçamento-base, cascata livre de fontes (`sco`, `emop`, `sinapi`,
  `sicro`, `composition`), proveniência impressa por linha;
- **obra licitada** → medição, só `PriceOrigin.sco`, guardrail
  `BULLETIN_PRICE_ORIGIN_FORBIDDEN` fail-closed.

A operação real tem **três** momentos, não dois. Quando existe contrato guarda-chuva já
licitado, cada demanda (uma praça) é orçada **depois** da licitação e **antes** da
execução. Esse orçamento tem a **forma** do orçamento-base — previsão, teto de verba
vindo da Relação de Praças, planilha orçamentária como entregável — mas está sob a
**regra** da obra licitada: o preço já está fixado pelo contrato, e só a tabela
contratual vale.

Hoje nada expressa isso. `estimate_rounds.ensure_source_installable`
(`services/api/src/croquito_api/estimate_rounds.py`) só recusa origem **duplicada** na
cascata; a rodada de orçamento não tem como declarar que corre sob contrato.

A falha que isso permite, em sequência:

1. a orçamentista instala EMOP ou SINAPI na cascata de uma demanda contratada;
2. confirma um código daquela fonte para um item;
3. o orçamento monta, imprime a fonte na coluna `FONTE` e passa na aprovação;
4. a empresa executa o serviço;
5. na medição, `BULLETIN_PRICE_ORIGIN_FORBIDDEN` recusa aquele código;
6. o serviço já executado não pode ser medido pelo caminho normal e vira pedido de
   aditivo.

**O defeito nasce no orçamento e só se manifesta no pagamento**, quando já não há o que
corrigir sem aditivo. É exatamente a distância que o resto do módulo trabalha para
eliminar — a mesma razão pela qual `ESTIMATE_CASCADE_ORIGIN_DUPLICATE` recusa na
instalação e não na montagem.

## Desired Outcome

A orçamentista declara, ao abrir a rodada, que aquela demanda corre sob contrato
licitado. A partir daí a cascata só aceita a tabela do contrato, a recusa acontece no
momento da instalação — quando ainda há o que corrigir —, e a jornada mostra em que
regime a rodada está, para ela não descobrir pelo erro.

## Scope

1. **Regime como dado da RODADA**, no molde do teto da
   [F-027](../F-027-modo-teto-orcamento-invertido/feature.md): declarado na abertura ou
   editado depois, sempre com `base_version` + `Idempotency-Key`. Ausência é o
   comportamento de hoje (pré-licitação, cascata livre) — ausência não é um valor, é a
   falta dele.
2. **Cascata restrita quando declarado**: instalar catálogo com `origin != sco` numa
   rodada sob contrato recusa em `ensure_source_installable`, com código de erro estável,
   na instalação e não na montagem.
3. **Selo na jornada**: cabeçalho e aba Cascata dizem o regime da rodada, conforme o
   Design Approval Package aprovado.
4. **Candidato a aditivo no orçamento** (ampliação de escopo por decisão humana de
   2026-08-22, fixada no ADR-0045): sob o regime, item confirmado no takeoff cuja
   confirmação de código foi **rejeitada** pela orçamentista é sinalizado como candidato a
   aditivo. O sinal vem do julgamento humano, **nunca** de uma conferência contra um
   contrato que o orçamento não modela.

   Reusa a **regra** do `amendment_dossier.py` da medição, não a função: o planejamento
   (2026-08-22) apurou que `build_amendment_dossier` exige decisão de código em TODO item
   confirmado, por ser artefato de fechamento — chamá-lo faria o sinal aparecer só no fim,
   que é o atraso que esta feature combate. O dado já existe: item rejeitado produz
   `CodeAssignment(status="rejected")` e o estado da rodada já conta `codes.rejected`.
5. **Cobertura**: rodada sem regime declarado idêntica a hoje; rodada sob contrato
   aceitando `sco` e recusando as quatro outras origens; declaração recusada com cascata
   suja; cadeia inteira sob o regime chegando à planilha com todas as linhas citando `sco`.

6. **Ampliação de 2026-08-22 — o regime na abertura e o rótulo que não mente** (decisão
   humana, revisão 2 do [pacote de design](mock/README.md)). A implementação da revisão 1
   deixou a tela afirmando um regime onde não há rodada: as três telas sem rodada
   (`OrcamentoApp.tsx:1551`, `1568`, `1587`) dizem `ORÇAMENTO-BASE · PRÉ-LICITAÇÃO`, e a
   faixa âmbar fala de pré-licitação — sobre nada. E orçar uma demanda que já está sob
   contrato obriga a abrir a rodada em pré-licitação para só então declarar o regime.

   Quatro mudanças, três delas só de tela:

   - rótulo neutro `ORÇAMENTO-BASE` e faixa que não afirma momento nas telas sem rodada;
   - campo **Regime** no formulário de abertura, com o mesmo peso do teto — o servidor já
     aceita `pricing_regime` em `POST /v1/estimate-rounds` desde a revisão 1, e só a tela
     não oferecia;
   - selo do regime no card da lista, o que exige `pricing_regime` na resposta de
     `GET /v1/estimate-rounds` — acréscimo aditivo;
   - o painel de declarar depois **permanece**, como caminho de correção.

   Isto não contradiz a decisão 4 da revisão 1: ela recusou "caixa de marcar **escondida**
   no formulário de abertura", e o campo proposto é o oposto de esconder. Efeito colateral
   desejado: com a rodada nascendo declarada, `ESTIMATE_REGIME_CASCADE_DIRTY` deixa de ser
   alcançável pelo caminho normal — a recusa continua implementada e testada, porque a
   rodada aberta sem regime ainda chega nela.

## Out of Scope

- Amarrar a rodada a um `Contract`/RE-RA real do contexto valuation — hoje o orçamento
  não conhece contrato como entidade, e criar esse vínculo é feature própria.
- Conferir se o catálogo instalado é *o* catálogo daquele contrato (data-base, desconto
  contratual). O escopo aqui é a **origem**, não a identidade do contrato.
- Qualquer mudança na cadeia de medição.
- Mudança em `Estimate`, na planilha `.xlsx` ou em schema publicado.

## Acceptance Criteria

1. `make check` e `make test` verdes; goldens intocados.
2. Rodada sem regime declarado percorre a jornada exatamente como hoje — coberto por
   teste que estende os existentes de `tests/api/test_estimate_round_routes.py` sem
   enfraquecê-los.
3. Rodada sob contrato: `origin=sco` instala; `emop`, `sinapi`, `sicro` e `composition`
   recusam com código estável e a cascata não muda.
4. O regime é declarável na abertura e editável depois, com `base_version` e
   `Idempotency-Key`, como o teto da F-027.
5. A tela corresponde à revisão aprovada do Design Approval Package.

## Constraints

- Sem alterar a regra da medição: o guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN` continua
  sendo a última linha, não a primeira.
- `packages/valuation` segue sem depender do worker nem do scene graph (ADR-0016).
- A recusa é da instalação; nenhuma cascata já instalada é reescrita retroativamente por
  uma declaração posterior de regime. Pelo ADR-0045, a declaração **recusa** enquanto
  houver fonte proibida instalada — nada é reescrito sem ato humano.

## Dependencies

- **ADR** refinando a fronteira binária no terceiro estado —
  `ARCHITECTURE_DECISION_REQUIRED`, **satisfeito em 2026-08-22** pelo
  [ADR-0045](../../adr/0045-terceiro-estado-demanda-sob-contrato.md) (`Accepted`).
- **Design Approval Package** — `DESIGN_APPROVAL_REQUIRED`, **satisfeito em 2026-08-22**
  (revisão 1, [mock/README.md](mock/README.md)).
- F-027 (modo teto) já na main — o desenho do dado-da-rodada que esta feature copia.

## Unknowns

As três que estavam abertas foram **decididas pelo
[ADR-0045](../../adr/0045-terceiro-estado-demanda-sob-contrato.md)** (`Accepted`,
2026-08-22) e ficam aqui como registro do que era pergunta:

1. ~~**Retroatividade**~~ → declarar o regime numa rodada que já tem fonte não-`sco`
   **recusa**, com código estável próprio, até a fonte ser removida pelo caminho existente.
   Rodada sob contrato nunca contém fonte proibida.
2. ~~**Nome do regime**~~ → "demanda sob contrato" no domínio; selo "Sob contrato licitado"
   na tela.
3. ~~**Data-base do catálogo**~~ → segue **fora de escopo**, e o ADR registra a posição: o
   regime garante a origem, não a identidade do contrato. Fechar isso é feature própria.

## Risks

- **Falso senso de proteção**: restringir a origem não garante que o catálogo instalado
  seja o do contrato certo. Mitigação: o `Out of Scope` diz isso explicitamente, e o
  documento da cadeia registra a lacuna remanescente.
- **Rodada legada**: rodadas abertas antes desta feature não têm regime. Mitigação:
  ausência é o comportamento atual, então nada muda para elas.
