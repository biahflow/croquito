# ADR-0039: SINAPI e SICRO como origens de preço da pré-licitação

Status: Accepted  
Data: 2026-08-20 (aceito por ato humano na mesma data)  
Responsável: Product / Engineering

## Contexto

O [ADR-0027](0027-price-source-provenance-and-bid-boundary.md) fixou que origem de
fonte de preço é dado do modelo (`PriceOrigin`: `sco` | `emop` | `composition`), que um
catálogo é UMA fonte, e que a mistura acontece só na cascata do orçamento-base — nunca
na medição, protegida por `BULLETIN_PRICE_ORIGIN_FORBIDDEN`. O roadmap reserva desde o
v1 a "cascata configurável de fontes de preço além do SCO (SINAPI, SICRO, tabelas
estaduais), cada fonte com importador próprio — tabela de preços é dado, não código".

Com a F-020 mergeada, a cascata tem superfície web e a reserva virou a próxima lacuna
prática: a orçamentista monta cascata com SCO, EMOP e composição, mas as duas tabelas
de referência mais usadas do país ficam de fora. A seleção humana de 2026-08-20 (rodada
pós-F-020) escolheu fechá-la ([F-026](../features/F-026-importadores-sinapi-sicro/feature.md)).

A dúvida que este ADR decide: SINAPI e SICRO entram como **valores novos de
`PriceOrigin`** ou como catálogos de uma origem "referência" genérica?

## Decisão

1. **`PriceOrigin` ganha `sinapi` e `sicro`.** Origem genérica é rejeitada: a
   proveniência por linha (VAL-09) e o selo de fonte na decisão de código existem para
   dizer DE ONDE o preço veio; "referência" esconderia exatamente isso. O selo, a
   coluna `FONTE` da planilha e a citação da decisão passam a nomear a fonte real.
2. **Um importador por fonte, layout como dado, fail-closed** — o desenho do importador
   EMOP (ADR-0027, decisão 4) é o molde: leitor mínimo interno, layout obrigatório como
   dado (`SinapiCatalogLayout`/`SicroCatalogLayout`: campos, encoding, regex do código,
   data-base), cada importação gera catálogo novo amarrado por digest com
   `reference_month` próprio. O formato real de cada fonte fecha como dado quando o
   arquivo real for lido; fixtures versionadas são sintéticas.
3. **Validação estrutural do código condicionada à origem**, como hoje: cada origem
   nova declara seu padrão de código no importador (cinto e suspensório sobre a
   validação do domínio), sem afrouxar o padrão das origens existentes.
4. **A medição não muda.** `BULLETIN_PRICE_ORIGIN_FORBIDDEN` já recusa qualquer origem
   diferente de `sco` por construção — origens novas ficam automaticamente proibidas na
   obra licitada. O guardrail ganha cobertura de teste nomeando as origens novas.
5. **Schemas publicados que embutem `PriceOrigin` sobem versão minor ANTES do
   `make contracts`.** Estender enum publicado é mudança de schema; o bump precede a
   publicação, como no precedente do `Estimate` (ADR-0038, decisão 6). O planejamento
   da F-026 inventaria quais contratos do manifesto embutem o enum e lista cada
   `*_SCHEMA_VERSION` afetada.

## Alternativas

- **Origem genérica `reference` com o nome da tabela em rótulo livre** — rejeitada:
  rótulo livre não é proveniência; a recusa estrutural por origem e o guardrail da
  medição passariam a depender de string não tipada.
- **Um importador único multi-formato** — rejeitada: cada fonte tem formato, encoding e
  ciclo de publicação próprios; um leitor único acumularia os modos de falha de todos.
  O padrão um-importador-por-fonte já foi pago no EMOP.
- **Adiar até haver arquivo real de cada fonte** — rejeitada: o EMOP provou o caminho
  (importador + layout como dado antes do arquivo real, que depende de ato externo);
  SINAPI e SICRO são publicamente distribuídos e o arquivo real entra como dado quando
  baixado, sem mudar código.

## Consequências

### Positivas

- Cascata cobre as tabelas de referência nacionais mantendo proveniência nomeada por
  linha, sem tela nova (a jornada da F-020 instala qualquer catálogo).
- A fronteira licitada × pré-licitação permanece intacta por construção.

### Negativas

- Dois leitores próprios a mais para manter (mitigado pelo escopo mínimo fail-closed).
- Bump de versão em todo schema publicado que embute `PriceOrigin` — custo de releitura
  de artefatos antigos onde a versão é `Literal` (inventário no planejamento da F-026).

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Arquivo real divergir do layout suposto | Nada é suposto: layout é dado obrigatório e a recusa fechada mapeia a lacuna (precedente M2.1/EMOP) |
| Origem nova vazar para a medição | `BULLETIN_PRICE_ORIGIN_FORBIDDEN` já recusa por construção; teste novo nomeia `sinapi`/`sicro` |
| Golden antigo mudar com o enum novo | Enum estendido não altera artefato existente; qualquer golden alterado é parada obrigatória |

## Rastreabilidade

- Requirements: VAL-09; roadmap "Próximo — medição além do v1", bullet da cascata
  configurável; [F-026](../features/F-026-importadores-sinapi-sicro/feature.md)
- Supersedes: none — estende o [ADR-0027](0027-price-source-provenance-and-bid-boundary.md)
  (decisões 1 e 4) com duas origens novas
- Superseded by: none
