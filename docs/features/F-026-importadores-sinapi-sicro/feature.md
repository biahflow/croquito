# F-026 — Importadores SINAPI e SICRO na cascata do orçamento-base

## Status

`DONE`

> Implementação integrada em 2026-08-20 na branch `f-026-importadores` (T1–T3,
> [plan.md](plan.md)), revisada e com evidência em [evidence.md](evidence.md) e
> **mergeada na `main`** em `b6f253f`. **Deploy e aceitação confirmados por ato
> humano em 2026-08-25** (Daniel Campos). Este flip reconcilia o roadmap, que
> ficara em `READY_FOR_HUMAN_REVIEW` após o merge.

> Selecionada por decisão humana de 2026-08-20, na rodada pós-F-020, junto com F-028 e
> F-027. Fecha o bullet reservado do roadmap ("cascata configurável de fontes de preço
> além do SCO... cada fonte com importador próprio — tabela de preços é dado, não
> código"). A decisão técnica é o
> [ADR-0039](../../adr/0039-sinapi-sicro-como-origens-de-preco.md) (Proposed): SINAPI e
> SICRO entram como valores novos de `PriceOrigin`, um importador por fonte no molde do
> EMOP.

## Classification

`NO_INTERFACE_CHANGE` — nenhuma superfície nova: os catálogos importados entram na
cascata pela jornada web que a F-020 entregou e pelos comandos de CLI novos, cuja saída
segue o padrão dos importadores existentes. O selo de fonte e a coluna `FONTE` já
imprimem `price_origin.value` — as origens novas aparecem neles sem mudança de desenho.

## Priority

`HIGH` — SINAPI e SICRO são as tabelas de referência mais usadas do país; sem elas o
orçamento-base pré-licitação só cobre SCO municipal, EMOP estadual e composição manual.

## Problem

A cascata declara ordem entre fontes, mas só três origens existem. Orçamento fora do
Rio (ou item sem preço no SCO/EMOP) não tem tabela de referência nacional para citar —
e item sem preço declarado é justamente o que a planilha da F-020 imprime como lacuna.

## Desired Outcome

A orçamentista importa o arquivo oficial do SINAPI (Caixa) ou do SICRO (DNIT) pelo CLI,
obtém um `PriceCatalog` com `origin` próprio amarrado por digest e `reference_month`, e
o instala na posição que quiser da cascata pela web — com o selo de fonte, a citação na
decisão de código e a coluna `FONTE` da planilha nomeando a tabela real.

## Scope

1. **`PriceOrigin` ganha `sinapi` e `sicro`** (`packages/valuation/src/croquito_valuation/models.py`),
   com validação estrutural de código condicionada à origem como hoje (padrão real de
   cada fonte é dado do importador; ADR-0039, decisões 1 e 3).
2. **Bump de versão minor de todo schema publicado que embute `PriceOrigin`**, ANTES de
   `make contracts` (ADR-0039, decisão 5). O planejamento inventaria as
   `*_SCHEMA_VERSION` afetadas no manifesto; goldens que mudarem por isso são parada
   declarada no plano, nunca regeneração silenciosa.
3. **Importadores** `sinapi.py` e `sicro.py` em `packages/valuation`, no molde de
   `emop.py`: leitor mínimo interno fail-closed, layout como dado
   (`SinapiCatalogLayout`/`SicroCatalogLayout`: campos, encoding, regex de código,
   data-base), digest + `reference_month` por importação.
4. **Comandos CLI** `import-sinapi` e `import-sicro` em
   `services/worker/src/croquito_worker/valuation/cli.py`, espelhando `import-emop`
   (incluindo fixtures sintéticas geradoras no padrão de `emop_fixture.py`).
5. **Cobertura**: testes de importador (feliz + recusa de layout campo a campo,
   espelhando os do EMOP), guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN` testado
   nomeando as origens novas, e a cadeia do orçamento (CLI e `/v1`) exercitada com uma
   cascata que inclua uma origem nova.

## Out of Scope

- Tela nova ou mudança de desenho na jornada (`apps/web/src/orcamento/` só é tocada se
  alguma tradução/label de origem for literal em vez de derivada — verificar no
  planejamento, não redesenhar).
- Download automático dos arquivos oficiais; o arquivo é insumo local do usuário.
- Versionar arquivo real de SINAPI/SICRO; fixtures são sintéticas.
- Tabelas estaduais além das duas fontes; desoneração/encargos como conceito próprio
  (o preço importado é o da coluna que o layout-como-dado apontar).
- Medição licitada: nada muda além da cobertura do guardrail.

## Acceptance Criteria

1. `make check` e `make test` verdes; schemas afetados com bump minor e sem drift.
2. `import-sinapi`/`import-sicro` geram catálogo válido a partir da fixture sintética,
   com digest, `reference_month` e `origin` corretos; arquivo com layout divergente
   recusa fail-closed com código estável por campo.
3. Cascata com origem nova percorre a cadeia do orçamento inteira (decisão de código
   citando a fonte, linha com proveniência, planilha imprimindo a origem na `FONTE`) —
   coberto por teste que estende os existentes, sem enfraquecê-los.
4. `BULLETIN_PRICE_ORIGIN_FORBIDDEN` coberto por teste com `sinapi` e `sicro`.
5. Goldens existentes intocados, exceto os que o plano declarar como consequência do
   bump de schema — diff só de campos de versão nesses casos.
6. `make valuation-demo` e `make valuation-estimate-demo` seguem verdes e
   determinísticas.

## Constraints

- `packages/valuation` continua sem depender do worker nem do scene graph (ADR-0016).
- Um catálogo é UMA fonte (`CATALOG_ORIGIN_MIXED` permanece); a cascata é o único lugar
  de mistura (ADR-0027).
- Sem dependência nova de parsing: leitores próprios sobre stdlib, como o `.DBF` do
  EMOP (formato real de cada fonte pode exigir decisão no planejamento — se algum
  formato oficial exigir biblioteca, isso é `ARCHITECTURE_DECISION_REQUIRED`, não
  dependência de carona).

## Dependencies

- [ADR-0039](../../adr/0039-sinapi-sicro-como-origens-de-preco.md) — **Accepted por ato
  humano em 2026-08-20**; as decisões 1–5 são a especificação usada pelo plano.
- Arquivos reais do SINAPI/SICRO — insumo do usuário quando quiser; a feature fecha com
  fixture sintética, como o EMOP fechou.
- F-020 mergeada (cascata web) — satisfeita.

## Unknowns

1. **Formato de distribuição real de cada fonte** (SINAPI: planilha da Caixa; SICRO:
   planilhas do DNIT) — qual recorte vira o "arquivo de importação" canônico é decisão
   do plano, com o layout-como-dado absorvendo a variação.
2. **Inventário exato dos schemas que embutem `PriceOrigin`** — sai da exploração do
   planejamento (manifesto + gerados), não de memória.

## Risks

- **Enum estendido quebrar releitura de artefato antigo** — mitigação: enum é aditivo;
  artefatos antigos não carregam os valores novos; goldens são o detector.
- **Layout suposto divergir do arquivo real** — mitigação: layout é dado obrigatório e
  recusa fechada mapeia a lacuna (precedente M2.1/EMOP).
- **Origem nova vazar para a medição** — mitigação: guardrail já recusa por construção
  + critério 4.

## Human Gates

1. Seleção (2026-08-20) — exercida.
2. Aceite do [ADR-0039](../../adr/0039-sinapi-sicro-como-origens-de-preco.md) —
   exercido em 2026-08-20.
3. Merge e deploy.

## References

- [ADR-0039](../../adr/0039-sinapi-sicro-como-origens-de-preco.md)
- [ADR-0027 — proveniência de preço e fronteira licitada × pré-licitação](../../adr/0027-price-source-provenance-and-bid-boundary.md)
- [F-020 — jornada web do orçamento-base](../F-020-orcamento-base-web/feature.md)
- [Roadmap canônico](../../product/ROADMAP.md)
