# F-033 — Demanda sob contrato licitado: cascata restrita à tabela contratual

## Status

`BLOCKED`

> Nasce em 2026-08-21, de uma conversa de operação: mapeando a cadeia real das praças
> (levantamento → DXF → prancha → orçamento → aprovação → empresa executora), ficou
> visível que o fluxo do usuário é um **terceiro estado** que o
> [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md) não representa.
>
> Bloqueada por **dois gates humanos**, nenhum dos quais um agente pode exercer:
> falta a decisão de arquitetura que refina a fronteira binária do ADR-0027 num terceiro
> estado (`ARCHITECTURE_DECISION_REQUIRED` — ADR novo ou emenda, escrito e aceito por
> ato humano); e falta o Design Approval Package da superfície nova
> (`DESIGN_APPROVAL_REQUIRED`), que precede o planejamento por a feature ser
> `INTERFACE_CHANGE`. Exercidos os dois, o estado passa a `READY_FOR_PLANNING`.

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
4. **Cobertura**: rodada sem regime declarado idêntica a hoje; rodada sob contrato
   aceitando `sco` e recusando as quatro outras origens; cadeia inteira sob o regime
   chegando à planilha com todas as linhas citando `sco`.

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
  uma declaração posterior de regime — o que fazer nesse caso é decisão do ADR.

## Dependencies

- **ADR novo (ou emenda ao ADR-0027)** refinando a fronteira binária no terceiro estado
  — `ARCHITECTURE_DECISION_REQUIRED`, ato humano, precede o planejamento.
- **Design Approval Package** aprovado — `DESIGN_APPROVAL_REQUIRED`, ato humano, precede
  o planejamento.
- F-027 (modo teto) já na main — o desenho do dado-da-rodada que esta feature copia.

## Unknowns

1. **Retroatividade**: rodada que já tem fonte não-`sco` instalada e passa a declarar o
   regime — recusa a declaração, exige remover a fonte antes, ou aceita e sinaliza? É
   decisão do ADR, não do plano.
2. **Nome do regime no domínio e na tela** — "sob contrato", "obra licitada", "demanda
   contratada". Sai do Design Approval Package.
3. **Se o regime deveria também restringir a data-base** do catálogo à do contrato. Fora
   do escopo declarado acima, mas o ADR pode querer registrar a posição.

## Risks

- **Falso senso de proteção**: restringir a origem não garante que o catálogo instalado
  seja o do contrato certo. Mitigação: o `Out of Scope` diz isso explicitamente, e o
  documento da cadeia registra a lacuna remanescente.
- **Rodada legada**: rodadas abertas antes desta feature não têm regime. Mitigação:
  ausência é o comportamento atual, então nada muda para elas.
