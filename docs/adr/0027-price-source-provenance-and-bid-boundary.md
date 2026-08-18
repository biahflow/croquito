# ADR-0027: Fontes de preço com proveniência e a fronteira licitada × pré-licitação

Status: Accepted
Data: 2026-08-17  
Responsável: Product / Engineering

## Contexto

A primeira rodada real da medição (Campo do Toca, 2026-08-13) fixou, com a orçamentista
do domínio, uma regra que o modelo ainda não sabia expressar — **dois momentos com
regras de preço diferentes**:

- Em obra **licitada** (medição), o contrato manda. Item confirmado no takeoff que não
  tem código no SCO/contrato **não pode** ser precificado por outra tabela: o caminho é
  aditivo de contrato (RE-RA), e o papel do sistema é detectar esses itens e instruir o
  pedido — nunca precificar por fora.
- Em **pré-licitação** (orçamento-base), vale a cadeia SCO → EMOP → composição manual.
  É o coração do "gerador de orçamento" da fase 1 da visão de produto
  ([Roadmap](../product/ROADMAP.md)).

Hoje `PriceCatalog`/`PriceCatalogEntry` representam um único catálogo com o SCO
implícito, sem noção de origem; a lista de "candidatos a aditivo" existe apenas como
seção derivada no cliente da tela de medição; e o catálogo digital oficial da EMOP é
**pago** (assinatura GRE ao tesouro estadual, formato .DBF, sincronização mensal
possível) — a assinatura é ato comercial do usuário e o arquivo real não existe no
repositório.

O ADR-0021 já mediu e descartou um sinal automático de "possível aditivo": aditivo é
condição contratual, não distância de retrieval — a detecção é a decisão humana de
rejeição de código, sempre.

## Decisão

1. **Origem da fonte de preço é dado do modelo.** `PriceOrigin`
   (`sco` | `emop` | `composition`) passa a existir em `PriceCatalogEntry.origin` e
   `PriceCatalog.origin`, com default `sco` para reler todos os artefatos M1–M7 sem
   migração. Um catálogo é **uma** fonte: entrada com origem diferente do catálogo
   recusa (`CATALOG_ORIGIN_MIXED`); mistura de fontes acontece na cascata do
   orçamento-base, nunca dentro de um catálogo. A validação estrutural do código é
   condicionada à origem (`sco` exige o padrão SCO exato; as demais um superset
   estrutural apertado), e o padrão real de cada fonte é dado do importador — cinto e
   suspensório, como no `extra_code_patterns` do M2.1.
2. **A regra da licitada vira guardrail fail-closed.** A cadeia da medição
   (`build_worksite_bulletin` e o escritor da planilha) recusa qualquer catálogo com
   origem diferente de `sco` (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`). O portão de contrato
   existente (`LINE_PRICE_NOT_IN_CONTRACT`) permanece como segunda linha.
3. **O dossiê do aditivo é artefato de domínio.** `build_amendment_dossier` consome as
   rejeições de código humanas cruzadas com os itens confirmados do takeoff e publica
   `amendment-dossier.json` (CLI `build-amendment-dossier`; rotas locais
   `POST /dossier/build` + `GET /dossier`; a tela passa a exibir o dossiê do servidor,
   mantendo a lista do cliente só como prévia). O dossiê é artefato de **fechamento**
   da rodada (item confirmado sem decisão de código recusa), exige justificativa (a
   nota da rejeição), **não tem campo de preço por construção** e não cria nem altera
   `Amendment` — RE-RA segue só leitura
   ([ADR-0018](0018-valuation-consolidation-and-balance-semantics.md)).
4. **EMOP entra como segundo catálogo, offline primeiro.** Importador `.DBF` com leitor
   mínimo interno (stdlib, fail-closed) e layout como dado (`EmopCatalogLayout`: campos,
   encoding, regex do código, data-base). O formato real fecha como dado quando o
   arquivo da GRE existir; cada importação gera catálogo novo amarrado por digest com
   `reference_month` próprio — nunca troca silenciosa de preço.
5. **Composição manual é dado compilado a catálogo.** `CostComposition` com linhas de
   coeficiente (mão de obra, insumo, equipamento) e preço unitário sempre recomputado
   (divergência recusa); a compilação gera um `PriceCatalog` com `origin=composition`,
   cada entrada amarrada por digest à composição de origem — a jusante tudo consome
   catálogo, uniforme.
6. **O orçamento-base é cadeia própria.** `Estimate`/`EstimateLine` com proveniência por
   linha (origem + catálogo + data-base) e cascata de fontes declarada como dado (nunca
   "SCO primeiro" em código); sem contrato, sem saldo e sem aprovação de medição — o
   portão é a auditoria de recomputação e a revalidação na leitura. A saída `.xlsx` do
   orçamento-base fica para quando houver exemplar real do modelo da prefeitura, como
   template (dado).

## Alternativas

- **Precificar item licitado pela EMOP quando falta código no contrato** — rejeitada:
  viola a regra do erário fixada pela orçamentista; o caminho contratual é o aditivo.
- **Sinal automático de "possível aditivo" no retrieval** — rejeitada: já medida e
  descartada no [ADR-0021](0021-hybrid-sco-code-retrieval.md); as distribuições se
  sobrepõem por completo e a decisão é humana.
- **Dependência externa para ler .DBF** — rejeitada: o subconjunto dBASE III usado é
  simples e estável; leitor interno fail-closed dá controle total da recusa e evita
  dependência nova por formato de um único fornecedor.
- **Catálogo único multifonte (entradas de várias origens no mesmo artefato)** —
  rejeitada: esconde a fronteira licitada × pré-licitação dentro do artefato e torna o
  guardrail da medição dependente de varredura por linha; um catálogo por fonte mantém
  a recusa no cabeçalho.

## Consequências

### Positivas

- A regra do erário deixa de ser prosa e vira recusa determinística com código estável.
- Proveniência auditável por linha no orçamento-base; EMOP nunca vaza para a medição.
- O dossiê materializa a conversa do aditivo com justificativa humana rastreável.

### Negativas

- Leitor .DBF próprio para manter (mitigado pelo escopo mínimo e recusa fechada).
- O formato real da EMOP permanece pendente de dado até a assinatura GRE existir.
- A entrada compilada de composição duplica o preço da composição de origem (fonte de
  verdade é a composição, amarrada por digest — mesmo trade-off declarado da pasta
  autocontida do ADR-0016).

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Arquivo EMOP real divergir do layout suposto | Nada é suposto: layout é dado obrigatório e recusa fechada mapeia a lacuna, como no MAPÃO real do M2.1 |
| Catálogo de composição desatualizar ante a composição editada | Amarração por digest da composição na entrada compilada; divergência recusa |
| Golden antigos mudarem com o campo novo | Default `sco` preserva releitura; qualquer golden alterado é parada obrigatória, nunca regeneração silenciosa |

## Rastreabilidade

- Requirements: VAL-08, VAL-09 ([Acceptance Criteria](../product/ACCEPTANCE_CRITERIA.md))
- Supersedes: none
- Superseded by: none
