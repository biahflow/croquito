# ADR-0038: BDI como conceito de pré-licitação

Status: Proposed  
Data: 2026-08-20  
Responsável: Product / Engineering

## Contexto

O [ADR-0027](0027-price-source-provenance-and-bid-boundary.md) fixou a fronteira
licitada × pré-licitação: na medição o contrato manda (`PriceOrigin.sco` apenas,
guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN`); no orçamento-base vale a cascata
SCO → EMOP → composição, com proveniência por linha. O que aquele ADR não cobriu foi
o **BDI** — que não existe em nenhum arquivo do repositório, como verificou a
conferência do exemplar real da prefeitura em 2026-08-19, e sem o qual um
orçamento-base de pré-licitação não é submissível.

A [F-020](../features/F-020-orcamento-base-web/feature.md) abre a jornada web do
orçamento-base e traz o `.xlsx` no layout da prefeitura. Duas decisões humanas já
foram exercidas: em 2026-08-19, a granularidade do BDI (percentual único por
orçamento, por-grupo reservado); em 2026-08-20, a aprovação da revisão 1 do
[Design Approval Package](../features/F-020-orcamento-base-web/mock/README.md), que
carrega a forma impressa dessas decisões.

## Decisão

1. **BDI é conceito exclusivo de pré-licitação.** Ele vive no `Estimate`
   (`croquito_valuation.estimate`) e nunca alcança a cadeia da medição: o preço
   contratado de obra licitada já o embute. O escritor do boletim não ganha campo,
   coluna nem parâmetro de BDI, e a exportação da medição permanece byte-idêntica —
   coberta por teste. `BULLETIN_PRICE_ORIGIN_FORBIDDEN` segue como está.
2. **Percentual único por orçamento.** O `Estimate` declara um BDI (percentual,
   `ExactDecimal` — `float` recusa) que se aplica a todas as linhas. BDI por grupo é
   espaço reservado para feature futura: só vira real quando o item carregar grupo
   como dado **e** houver ADR aceito; até lá não é renderizado nem modelado.
3. **Por linha, preço sem e com BDI; o total recomputa sobre o preço com BDI.**
   Disciplina de dinheiro do módulo: preço unitário com BDI trunca no centavo, o
   total da linha trunca no centavo, e os `model_validator` recomputam BDI e total
   juntos — a revalidação na leitura continua sendo o portão (VAL-09).
4. **O BDI impresso na planilha é a diferença entre os totais truncados**, nunca o
   percentual aplicado ao total geral. Cada linha trunca antes de somar; a planilha
   imprime a soma. A alternativa faria a planilha discordar dela mesma no centavo.
5. **Layout do `.xlsx`: as sete colunas do boletim mais duas** — `FONTE` (origem +
   data-base numa célula) e `VALOR UNIT. C/ BDI`. As colunas novas entram no modelo
   de layout compartilhado (`template.py`) como **aditivas e opcionais**; o boletim
   não as usa.
6. **`ESTIMATE_SCHEMA_VERSION` sobe antes da publicação no manifesto.** O campo novo
   entra no schema, a versão sobe, e só então `Estimate` é publicado em
   `packages/contracts/contracts.manifest.json` — nunca campo obrigatório novo em
   contrato já publicado.

## Alternativas

- **BDI por linha (percentual repetido em cada linha da planilha)** — rejeitada:
  repetir o mesmo número em toda linha esconde que ele é único por orçamento.
- **BDI por grupo já nesta feature** — rejeitada: o item não carrega grupo como dado;
  modelar agora seria especulação. Fica como espaço reservado nomeado.
- **BDI aplicado ao total geral (percentual sobre a soma)** — rejeitada: divergiria
  no centavo da soma das linhas truncadas; a planilha discordaria dela mesma.
- **Coluna separada de data-base** — rejeitada no pacote aprovado: três colunas novas
  num layout que a prefeitura já valida; origem + data-base compartilham a célula
  `FONTE`.
- **BDI como parâmetro também da medição** — rejeitada: o preço contratado já embute
  BDI; aplicá-lo de novo é erro de domínio, e a fronteira do ADR-0027 existe
  exatamente para impedir esse vazamento.

## Consequências

### Positivas

- O orçamento-base sai submissível (BDI declarado, proveniência por linha impressa)
  sem tocar a garantia da medição.
- A fronteira do ADR-0027 ganha o conceito que faltava do lado da pré-licitação, com
  recusa determinística em vez de convenção.
- Aritmética de dinheiro permanece uniforme: truncar no centavo linha a linha, somar
  o truncado, revalidar na leitura.

### Negativas

- O modelo de layout compartilhado com o boletim ganha colunas opcionais — mais um
  ponto em que uma mudança futura pode quebrar dois documentos; mitigado por teste de
  byte-identidade do boletim.
- `ESTIMATE_SCHEMA_VERSION` sobe e artefatos `estimate.json` antigos deixam de reler
  sem migração explícita — aceito: o artefato é recomputável a partir do takeoff e
  dos catálogos.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| BDI "consertado" na medição por engano futuro | Este ADR registra a fronteira; boletim coberto por teste de byte-identidade e `BULLETIN_PRICE_ORIGIN_FORBIDDEN` segue testado |
| Planilha publicada com BDI divergente do recomputado | Portão de auditoria fail-closed: o `.xlsx` é reaberto e reconferido centavo a centavo antes de publicar; falha não publica |
| Campo obrigatório novo quebrar leitura de artefato publicado | Bump de `ESTIMATE_SCHEMA_VERSION` antes da publicação no manifesto (decisão 6) |

## Rastreabilidade

- Requirements: VAL-09 ([Acceptance Criteria](../product/ACCEPTANCE_CRITERIA.md));
  [F-020](../features/F-020-orcamento-base-web/feature.md)
- Supersedes: none — estende o [ADR-0027](0027-price-source-provenance-and-bid-boundary.md)
  (a fronteira permanece; o BDI entra do lado pré-licitação)
- Superseded by: none
