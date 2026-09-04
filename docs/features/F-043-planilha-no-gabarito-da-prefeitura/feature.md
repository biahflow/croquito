# F-043 — A planilha sai no gabarito da prefeitura, com memória de cálculo

## Status

`DONE`

> **Aceita por ato humano em 2026-09-04** (Daniel Campos, pelo chat: "sim ficou muito bom"),
> contra o **documento real** do Campo do Toca — diferente dos aceites de 2026-09-02, este
> não é sobre evidência sintética: o arquivo gerado espelha o real linha por linha
> (454/454 nas linhas 10..463, 433 códigos + 21 grupos), auditoria 0 findings, total
> 648.956,63. A bancada do aceite e os números estão em [evidence.md](evidence.md).
>
> O aceite exerceu também as duas decisões que estavam registradas: **o rodapé segue o
> ADR-0038 por agora** (três linhas, BDI como diferença), e **o preço do contrato NÃO
> embute BDI** — o `TOTAL S/BDI` do documento do cliente divide por 1,18 um valor que
> nunca teve BDI, erro do arquivo dele, não do nosso raciocínio (corrige o unknown 2).
>
> A revisão da bancada achou e fechou um defeito antes do aceite: o escritor da T1 não
> imprimia a **linha de grupo** (aprovada no pacote de design rev. 2/3) e emitia o grupo
> como oitava coluna — consertado pelo PR #143, cujo merge conclui esta feature.
>
> **Gabarito real publicado como artefato de plataforma em 2026-09-04** (mesma data do
> aceite, ato operacional no ambiente local): id `01a06c0c-c56b-7c96-96e3-8254edd2a698`,
> nome "PLANILHA ORÇAMENTÁRIA (SMH/Rio)", revisão `REV SEAC — OUT/23`, 433 linhas, digest
> `94e6f6fd97cf…`, imutável. **Dívida que segue declarada**: o unknown 1 (gabarito por
> lote?) continua aberto, com evidência a favor de um só.

> Histórico: **as três tarefas entregues em 2026-09-01.** A T1 (o escritor do gabarito,
> provado contra o documento real sem um finding do auditor) entrou pelo PR #115; a T2 (o
> gabarito como artefato de plataforma) e a T3 (a escolha na jornada web), pelo #131.
>
> Os gates: [ADR-0059](../../adr/0059-item-contratado-fora-da-tabela-sco.md) aceito em
> 2026-08-28, e o [Design Approval Package](mock/README.md) nas revisões 1 e 2 na mesma data e
> na **revisão 3 em 2026-09-01** — as três por ato humano (Daniel Campos).
> `BROWSER_REQUIRED` cumprido: três estados capturados contra o stack local, e a captura achou
> dois defeitos que a suíte não achava ([evidence.md](evidence.md)).
>
> Nasce em 2026-08-28, da mesma medição de ROI que originou a
> [F-042](../F-042-acervo-de-parcelas-de-canteiro/feature.md): o dono do produto perguntou o
> que o sistema pode fazer para acelerar a entrega do documento, e a resposta expôs que a
> saída atual não é o documento que o cliente recebe.
>
> Esta é a feature que **converte** as outras duas em tempo entregue. Enquanto a saída não
> for o gabarito do cliente, a orçamentista redigita tudo no Excel dela, e o acervo de
> canteiro e o precedente de código economizam raciocínio, não entrega.

## Classification

`INTERFACE_CHANGE` — muda o artefato que a jornada publica e o que a tela promete sobre ele.

## Priority

`HIGH` — sem ela o ganho das outras duas features não chega ao cliente.

## Problem

O documento que a prefeitura recebe (aba `PLANILHA ORÇAMENTÁRIA` do arquivo real) é um
**gabarito de ordem fixa**: 433 linhas de código em 21 grupos, numeração `GG.N` dentro do
grupo, com os grupos 5, 15 e 22 ausentes por convenção do próprio documento. Nesta praça,
**43 linhas** têm quantidade; as outras 390 são impressas com zero e fazem parte da entrega.
Ao lado dele vai a memória de cálculo, com um bloco por código e parcelas nomeadas.

O que o sistema publica hoje é outra coisa. `write_estimate_workbook`
(`packages/valuation/src/croquito_valuation/estimate_workbook.py:473`) faz `Workbook()` e
cria **uma aba do zero**, chamada `ORÇAMENTO`, com **uma linha por `EstimateLine`
precificada**. As linhas saem de cursor sequencial (`first_line_row = layout.header_row + 1`,
`row = first_line_row + index`, `:271-273`).

Três lacunas concretas, todas verificadas:

1. **Não existe escrita em gabarito de ordem fixa.** Não há mapa código→linha em lugar
   nenhum do repositório; o único índice por código é da ferramenta de comparação
   (`bulletin_compare.py:323-336`), e `workbook_writer.py` também escreve por cursor
   sequencial a partir de `data_first_row`.
2. **Não existe memória de cálculo do orçamento em planilha.** Ela existe só na web
   (`apps/web/src/orcamento/OrcamentoApp.tsx:732`, `MemoriaDeCalculo`);
   `estimate_workbook.py` não imprime memória nenhuma.
3. **Não existe importador que infira um gabarito de arquivo real.** Nenhum ponto do repo
   constrói um `WorkbookTemplate` além de `default_template()` (`template.py:645`); o
   template real entra como JSON escrito à mão (`cli.py:574-578`).

## Desired Outcome

A rodada publica o arquivo no gabarito da prefeitura — mesma ordem, mesma numeração, linhas
de quantidade zero incluídas — com a aba de memória ao lado, auditado pelo mesmo portão
fail-closed que já protege a medição.

## Scope

1. **`EstimateTemplateLayout`** novo em `template.py`, no molde de `GeneralLayout`
   (`:232`) — o único layout do repositório com posições de arquivo real. O gabarito é
   declarado como **lista ordenada de (grupo, item, código, descrição, unidade)**,
   preservando a numeração `GG.N` e as lacunas de grupo.
2. **Escritor que percorre o gabarito** e preenche quantidade e total **por código**,
   imprimindo todas as linhas — inclusive as de quantidade zero.
3. **Aba de memória de cálculo do orçamento**, **reusando** `_plan_memory` (`:502-613`) e
   `_plan_block` (`:421-499`) de `workbook_writer.py`, que já imprimem rótulo do bloco,
   operandos nomeados, dedução e subtotal com fórmula. Escrever um segundo render seria
   duplicar a única peça que já está no formato certo.
4. **Auditoria pelo caminho existente**: `canonicalize_workbook` (`canonical.py:325`) mais a
   gramática fechada `GRAMMAR_PATTERNS` (`:65-72`), como
   `audit_estimate_workbook` (`estimate_workbook.py:553`) já faz. Erro do auditor não
   publica.

## Out of Scope

- **Inferir o gabarito automaticamente de um `.xlsx` real.** O gabarito entra como JSON
  declarado, no mesmo desenho do `--template` de hoje. Inferência é feature própria, se
  algum dia valer o risco de adivinhar layout de arquivo de cliente.
- **Trocar o layout `EstimateLayout` atual** (`template.py:470`). Ele continua servindo a
  rodada que não tem gabarito declarado; o novo é seção adicional, não substituição.
- **A aba `PLANILHA GERAL`** (lista de preços do contrato). Ela é **entrada** — o catálogo —,
  e não saída desta feature.

## Acceptance Criteria

1. O arquivo gerado para o Campo do Toca tem as **mesmas 433 linhas**, na mesma ordem, com a
   mesma numeração `GG.N` e as mesmas lacunas de grupo do documento do cliente.
2. As **43 quantidades** batem com as do cliente, e as 390 restantes saem zeradas em vez de
   ausentes.
3. Código presente no orçamento e **ausente do gabarito** é recusa declarada, nomeando o
   código — nunca linha inventada no fim do arquivo.
4. A memória impressa tem um bloco por código com **parcelas nomeadas**, como a do cliente.
5. O auditor reabre o arquivo e recomputa cada fórmula em `Decimal`; divergência não publica.
6. **Métrica**: o arquivo publicado é o documento entregável, sem redigitação — verificado
   abrindo o gerado ao lado do real.

## Constraints

- Toda fórmula escrita precisa caber na gramática fechada de `canonical.py`; forma nova exige
  estender a gramática **e** o mini-avaliador, nunca só o escritor.
- O gabarito é dado, não código (`template.py:1-7`): nenhuma posição de célula pode ser
  embutida em Python.
- Dinheiro continua truncado, não arredondado, onde o documento trunca.

## Dependencies

- [ADR-0038](../../adr/0038-bdi-como-conceito-de-pre-licitacao.md) — é o ADR que a planilha
  do orçamento-base cita (`estimate_workbook.py:1`, `template.py:471`); dele vem a regra do
  BDI impresso como diferença entre totais truncados, que o gabarito precisa preservar.
- [ADR-0059](../../adr/0059-item-contratado-fora-da-tabela-sco.md) — **`Accepted` em
  2026-08-28**, alternativa A. É o ADR cuja feature de rastreabilidade é esta.
- [F-042](../F-042-acervo-de-parcelas-de-canteiro/feature.md) e
  [F-044](../F-044-precedente-de-codigo/feature.md) — as duas features cujo ganho esta aqui
  converte em documento. Nenhuma das duas é pré-requisito técnico: o gabarito depende do
  gabarito declarado, não delas.

## Unknowns

1. **O gabarito é por lote do contrato ou único para todas as praças?** Os três lotes têm
   listas diferentes (328/383/112 códigos). Se for por lote, a rodada precisa declarar em
   qual lote a praça entra, e isso muda o modelo.
2. ~~**De onde sai o preço impresso.**~~ ~~Resolvido em 2026-08-28: a coluna
   `VALOR UNIT (OUT/23)` traz o preço **com BDI**, porque o rodapé deriva o total sem BDI
   dividindo por 1,18.~~ **CORRIGIDO em 2026-09-04 por oráculo humano** (Daniel Campos):
   o preço do contrato **NÃO embute BDI** — é o custo de tabela SCO com desconto de
   licitação (~0,15%), como a comparação com a FGV06 já sugeria. A dedução de 2026-08-28
   confiou no rodapé do cliente, e é o rodapé que está errado: `TRUNC(G465/1.18,2)` divide
   por 1,18 um valor que nunca teve BDI. Palavras do dono: "Nossos cálculos, raciocínio
   estão certos, a planilha deles errou no cálculo." Consequência: `bdi_percent = 0` com o
   preço do contrato como preço final é a semântica correta do documento, não uma
   aproximação. Ver [`evidence.md`](evidence.md).
3. ~~**O gabarito real é o da aba `PLANILHA PADRÃO ORDENADA`** (518 códigos) **ou o da
   `PLANILHA ORÇAMENTÁRIA`** (433)?~~ **Decidido em 2026-08-28** (Daniel Campos): a
   `PLANILHA ORÇAMENTÁRIA`, de 433 códigos, conferida linha a linha em
   [`evidence.md`](evidence.md). Texto original: Os dois divergem em conteúdo e numeração — na padrão,
   `01.8` é "Caminhoneta de serviço"; na orçamentária, "Veículo de serviço". Isso indica
   revisões diferentes do mesmo gabarito, e a entrega precisa dizer qual vale.

## Risks

- **Gabarito envelhecido em silêncio**: a prefeitura revisa o gabarito, e um arquivo gerado
  na revisão velha parece certo. O gabarito declarado precisa carregar identificação de
  revisão, e o arquivo publicado precisa dizer qual usou.
- **433 linhas com 390 zeros**: um erro de mapeamento código→linha coloca a quantidade na
  linha errada e o arquivo continua parecendo válido. É exatamente o que o auditor precisa
  pegar, e por isso a conferência não pode ser só de totais.
- **Duplicar o render de memória** por parecer mais fácil que reusar o da medição. O reuso é
  escopo, não sugestão: dois renders divergem no primeiro ajuste.

## Human Gates

1. **Design Approval Package** — `INTERFACE_CHANGE`: o arquivo publicado muda de forma.
   Revisão 1 **aprovada em 2026-08-28** (Daniel Campos). Com o documento real em mãos no mesmo
   dia, quatro pontos de forma da rendição se mostraram diferentes do documento e produziram a
   **revisão 2**, ~~também **aprovada em 2026-08-28**~~ (Daniel Campos) — ela preserva as sete
   decisões da revisão 1 e corrige só a fidelidade: [`mock/README.md`](mock/README.md).
   **Gate cumprido.**

   Na mesma data o dono decidiu **onde o gabarito vive**: artefato de plataforma, no molde do
   acervo de catálogos da [F-037](../F-037-acervo-de-catalogos/feature.md) — publicado uma
   vez, versionado e imutável, escolhido por cada rodada de uma lista. É aplicação do molde
   já aceito no [ADR-0047](../../adr/0047-acervo-de-catalogos-da-plataforma.md) e reafirmado
   no [ADR-0060](../../adr/0060-onde-vive-o-acervo-de-parcelas-de-canteiro.md), e por isso
   não abre ADR próprio. O gabarito da prefeitura é um só para todas as praças, então ele
   não tem a metade "de tenant" que o acervo de canteiro tem.
2. ~~Aceite do [ADR-0059](../../adr/0059-item-contratado-fora-da-tabela-sco.md)~~ —
   **cumprido em 2026-08-28** (Daniel Campos), alternativa A.
3. ~~**Fornecer o gabarito real** e dizer qual revisão vale~~ — **cumprido**: qual aba vale
   foi decidido em 2026-08-28 (a `PLANILHA ORÇAMENTÁRIA`, de 433 códigos), e o gabarito
   declarado foi transcrito do documento real na bancada do aceite
   (`output/f043-aceite/gabarito-rev-seac.json`, local — a publicação como artefato de
   plataforma é dívida declarada no Status).
4. ~~**Aceite do arquivo gerado** contra o real~~ — **cumprido em 2026-09-04** (Daniel
   Campos), com o arquivo espelhando o documento real linha por linha; as duas decisões
   embutidas (rodapé pelo ADR-0038 por agora; preço do contrato sem BDI) registradas no
   Status e no unknown 2.

## References

- `packages/valuation/src/croquito_valuation/template.py:232` — `GeneralLayout`, o molde;
  `:470` — `EstimateLayout`, o layout atual.
- `packages/valuation/src/croquito_valuation/estimate_workbook.py:242-273` —
  `plan_estimate_workbook` e o cursor sequencial que esta feature substitui por índice de
  gabarito.
- `packages/valuation/src/croquito_valuation/workbook_writer.py:421-613` — `_plan_block` e
  `_plan_memory`, a memória a reusar.
- `packages/valuation/src/croquito_valuation/canonical.py:65-72, 325` — gramática fechada e
  reabertura auditada.
