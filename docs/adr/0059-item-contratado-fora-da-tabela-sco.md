# ADR-0059: Em demanda contratada a fonte de preço é o contrato, e ele carrega item fora da tabela SCO

Status: Accepted  
Data: 2026-08-28 (aceito por ato humano em 2026-08-28, Daniel Campos — alternativa A)  
Responsável: Product / Engineering

## Contexto

A lista de preços do contrato real (Praça Campo do Toca, aba `PLANILHA GERAL`) tem **823
códigos**, segmentados nos três lotes do contrato — GRUPO 1 implantação, GRUPO 2 manutenção
e revitalização, GRUPO 3 infraestrutura adjacente. Testados contra
`SCO_CODE_PATTERN` (`packages/valuation/src/croquito_valuation/sco.py:33`), **819 casam** e
**4 não**:

| Código | Descrição | Un | Preço |
|---|---|---|---|
| `IE00040849` | Alvenaria de 10cm de espessura em tijolos refratários | m² | R$ 632,09 |
| `IE00040850` | Futmesa modelo OPS SPORTS ou similar | un | R$ 3.495,43 |

(Os quatro são estes dois, repetidos nos lotes 1 e 2.)

Eles são os **dois últimos itens de cada lote** — 327-328 de 328 no GRUPO 1, 382-383 de 383
no GRUPO 2. A posição conta a história: a tabela SCO não tem esses serviços, então na
licitação foram cotados à parte e anexados ao fim da lista de preços do contrato, com código
próprio. **São item contratado, com preço fechado no contrato — não são aditivo**, e a
orçamentista os usa como qualquer outra linha.

O sistema não os aceita. Duas regras se cruzam:

1. `REGIME_ALLOWED_ORIGINS = (PriceOrigin.SCO.value,)`
   (`services/api/src/croquito_api/estimate_rounds.py:129`): sob o regime
   `contracted_demand`, a cascata só admite origem `sco`. É a codificação da regra de
   domínio — obra licitada não busca preço em outra tabela.
2. `PriceCatalogEntry.validate_code_for_origin`
   (`packages/valuation/src/croquito_valuation/models.py:139-148`) aplica o
   `SCO_CODE_PATTERN` **estrito** quando a origem é `sco`.

Consequência medida: **2 linhas em 823 fazem o catálogo inteiro ser recusado no
carregamento**, e a lista de preços do contrato real não entra no orçamento-base.

O repositório já antecipou a **forma** do problema. `CONTRACT_CODE_PATTERN`
(`sco.py:34-40`) existe exatamente para a "forma nua" do código de item contratado fora da
tabela SCO, e cita `IE00040849` na própria docstring; `WorkbookTemplate.extra_code_patterns`
(`template.py:505-511`, `matches_extra_code` `:527-557`) o consome. Mas isso vive no lado da
**medição** — a leitura do MAPÃO. O lado do **orçamento-base** não tem equivalente.

Não confundir com os três mecanismos vizinhos, que resolvem outros problemas e permanecem
como estão:

| Situação | Mecanismo |
|---|---|
| Item **fora do contrato**, obra licitada | `amendment_dossier.py` — RE-RA, e sem campo de preço por construção |
| Pré-licitação, preço cotado | `composition.py` — `CompositionLine.reference` é texto livre; preço declarado, nunca buscado |
| Linha "Sem Cotação" no catálogo publicado | `template.py:unpriced_markers` — a linha é pulada; ausência de preço nunca vira zero |

## Decisão

Sob o regime de demanda contratada, a fonte de preço passa a se chamar o que ela é: o
**contrato**.

1. `PriceOrigin` ganha o valor `CONTRACT = "contract"`. Um catálogo dessa origem é validado
   por `CONTRACT_CODE_PATTERN`, e não pelo `SCO_CODE_PATTERN` estrito — de modo que o código
   derivado do SCO (`PJ24100152(D)`) e o negociado (`IE00040849`) convivem no mesmo catálogo,
   que é como convivem no documento real.
2. `REGIME_ALLOWED_ORIGINS` do regime `contracted_demand` passa a ser `("contract",)`.
3. A regra de domínio **não muda**: continua valendo que obra licitada não busca preço em
   outra tabela. O que muda é o nome correto da tabela única permitida.
4. `EstimateLine.price_origin` de uma obra licitada passa a dizer `contract`. A proveniência
   continua carregando `catalog_sha256`, `reference_month` e `source_label`, então o auditor
   sabe **qual** contrato, e não só que é um contrato.
5. Rodada já gravada com origem `sco` sob demanda contratada continua legível: a leitura
   aceita a forma antiga sem reescrevê-la, porque revisão passada é registro do que foi
   decidido, não do que passaríamos a decidir.

## Alternativas

- **Afrouxar o `SCO_CODE_PATTERN` sob origem `sco`.** É a mudança mais barata — uma linha em
  `validate_code_for_origin`. Recusada porque passaria a rotular como "SCO" um código que
  não está na tabela SCO. A origem por linha existe para o auditor saber de onde veio o
  preço; um rótulo que mente sobre isso destrói justamente o que o campo protege, e o erro
  ficaria gravado em todo `EstimateLine` daí em diante.
- **Carregar os `IE` como segunda fonte da cascata, com origem `composition`.** Recusada por
  dois motivos independentes: `REGIME_ALLOWED_ORIGINS` proíbe composição sob demanda
  contratada — e proíbe **certo**, é a regra da orçamentista —, e chamar de composição um
  preço que veio fechado do contrato é a mentira oposta à da alternativa anterior. Composição
  é preço que **nós** montamos; este veio da licitação.
- **Tratar `IE` como item sem preço (`unpriced_item_ids`).** Recusada: o item tem preço
  contratado e é medível. Declará-lo sem preço empurraria para o dossiê de aditivo um serviço
  que o contrato já cobre, produzindo RE-RA indevida.
- **Manter o catálogo só com os 819 e ignorar os 4.** Recusada: um catálogo que silencia
  linhas do contrato é um catálogo que mente por omissão, e a futmesa é item real de praça.

## Consequências

### Positivas

- A lista de preços do contrato real carrega inteira, que é a precondição de qualquer
  orçamento sobre obra licitada.
- A proveniência fica verdadeira: `price_origin = contract` mais o digest do contrato diz
  exatamente de onde o preço veio.
- O `CONTRACT_CODE_PATTERN`, hoje exercido só na medição, passa a valer nas duas jornadas —
  o mesmo código contratual significa a mesma coisa dos dois lados.

### Negativas

- Mais um valor em `PriceOrigin`, que é enum de domínio lido em vários pontos.
- Convivência temporária de duas formas: rodadas antigas com `sco` sob demanda contratada e
  novas com `contract`. A leitura fica com dois caminhos até que não haja rodada antiga viva.
- O `CONTRACT_CODE_PATTERN` é mais permissivo que o estrito; um erro de digitação em código
  que antes seria recusado na fronteira passa a entrar e só falhar no `entry_for`
  (`CATALOG_CODE_UNKNOWN`), mais tarde.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Rodada gravada com `sco` sob demanda contratada deixar de ser legível | Decisão 5: a leitura aceita a forma antiga sem reescrever; teste de retrocompatibilidade guarda a condição |
| A origem nova ser usada em pré-licitação, contornando a cascata SCO → EMOP → SINAPI → SICRO | `origin_allowed_under_regime` (`estimate_rounds.py:683-691`) continua sendo o portão: `contract` só é admitida sob `contracted_demand` |
| Código malformado entrar por causa do padrão mais permissivo | O padrão continua exigindo duas letras e oito dígitos; o que fica opcional é só o sufixo `(X)`. Erro remanescente falha em `entry_for` com `CATALOG_CODE_UNKNOWN` |
| Confundir item contratado fora do SCO com item fora do contrato | O dossiê de aditivo (`amendment_dossier.py`) continua sendo o único caminho para item **sem** código no contrato, e segue sem campo de preço por construção |

## Rastreabilidade

- Feature: [F-043](../features/F-043-planilha-no-gabarito-da-prefeitura/feature.md)
- Relacionados: [ADR-0027](0027-price-source-provenance-and-bid-boundary.md) — a
  proveniência de preço e a fronteira da licitação, que esta decisão precisa e não afrouxa;
  [ADR-0045](0045-terceiro-estado-demanda-sob-contrato.md) — o regime de demanda sob
  contrato, cujo `REGIME_ALLOWED_ORIGINS` esta decisão altera;
  [ADR-0053](0053-cardinalidade-n-n-elemento-servico.md)
- Supersedes: none
- Superseded by: none
