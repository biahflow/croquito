# ADR-0018: Semântica de consolidação e saldo da medição de obra

Status: Accepted
Data: 2026-08-12  
Responsável: Engineering

## Contexto

O M2 do contexto `valuation` fechou o trecho `import-workbook` → `export-valuation`: o
MAPÃO anterior da prefeitura é importado, a medição do período seguinte é consolidada numa
PLANILHA GERAL nova e a pasta só é publicada depois da auditoria de round-trip
([ADR-0016](0016-valuation-bounded-context.md),
[Valuation Context](../architecture/VALUATION_CONTEXT.md)).

Escrever esse trecho obrigou a responder três perguntas que a planilha do cliente **não**
responde sozinha, e que valem centavos contra o erário:

- **De onde vem o saldo.** A planilha traz contratado, vigente, o par QUANTIDADE|VALOR de
  cada medição já lançada, o acumulado e o saldo — todos declarados, nenhum provado. As
  revisões contratuais (RE-RA) alteram quantidade item a item e vivem numa aba separada,
  a do MAPÃO da prefeitura.
- **O que fazer quando as duas abas discordam.** A quantidade vigente aparece na PLANILHA
  GERAL e também na aba da prefeitura. Nada garante que sejam iguais: são duas células
  digitadas por pessoas diferentes em momentos diferentes.
- **Quanto vale, em dinheiro, um código medido em mais de uma obra no mesmo período.** O
  boletim de cada obra trunca o valor da sua linha; a PLANILHA GERAL tem uma linha só por
  código. `TRUNC(Σ qᵢ × preço)` e `Σ TRUNC(qᵢ × preço)` podem diferir em um centavo, e
  não existe decisão registrada do orçamentista sobre qual dos dois a prefeitura aceita.

O contexto já decidiu que dinheiro trunca e que nenhum total informado vale sem recomputo.
Falta decidir **o que é recomputado contra o quê** quando o consolidado entra na conta.

## Decisão

**(a) Vigente é derivado das RE-RA; saldo é derivado do vigente.** Para cada código,
`quantidade vigente = quantidade contratual + Σ deltas das RE-RA` e
`saldo = quantidade vigente − acumulado`. Os dois são recomputados na importação e a
divergência contra o que a planilha declara falha fechado
(`AMENDMENT_APPLICATION_MISMATCH`, `CONTRACT_BALANCE_MISMATCH`,
`CONTRACT_ACCUMULATED_MISMATCH`, `CONTRACT_BALANCE_NEGATIVE`). Saldo excedido pela medição
corrente bloqueia a exportação (`BALANCE_EXCEEDED`).

RE-RA é **só leitura no v1**: o sistema reconcilia o efeito declarado de cada revisão sobre
o código correspondente, e não cria, altera nem propõe aditivo. A aba de RE-RA importada é
carregada adiante na pasta gerada, com os mesmos deltas, para que a pasta que circula
continue explicando de onde veio o vigente.

**(b) GERAL e MAPÃO-PREFEITURA discordando é recusa de importação.** Quando a quantidade
vigente de um código difere entre as duas abas, a importação falha com
`GENERAL_AMENDED_DIVERGENT` apontando código, valor da GERAL e valor declarado. Não há
precedência entre as abas e não há correção automática: quem sabe qual das duas está certa
é o orçamentista, e o dado dele entra corrigindo o arquivo, não o sistema.

**(c) O valor consolidado do período é `TRUNC(Σ quantidade × preço)`, e deriva de centavo
recusa a geração.** A linha da PLANILHA GERAL soma a quantidade do código em todas as obras
e trunca o produto uma vez só. Quando esse total não fecha com a soma dos totais dos
boletins, o escritor recusa com `GENERAL_CONSOLIDATION_MISMATCH`, informando o código, os
dois valores e a razão (`TRUNC_CONSOLIDATION_DRIFT`), e **nenhuma pasta é gerada**.

A recusa é deliberadamente conservadora: a semântica correta da consolidação nesse caso —
qual dos dois números a prefeitura reconhece como valor do período — está **pendente de
confirmação com o orçamentista responsável**. Até essa confirmação, publicar qualquer um
dos dois seria escolher em silêncio um total que a medição não declara.

## Alternativas

- **Consolidar por soma dos TRUNC de cada linha de boletim.** Rejeitada por ora: a célula
  de valor da GERAL deixaria de ser `=TRUNC(quantidade × preço,2)` sobre a própria linha,
  e a planilha gerada não passaria mais na sua própria reimportação — `PERIOD_AMOUNT_MISMATCH`
  exige que o valor lançado no período seja o produto truncado da quantidade lançada. O
  consolidado deixaria de ser reimportável como base da medição seguinte, que é a
  propriedade que sustenta a cadeia inteira.
- **Aceitar tolerância de um centavo entre o consolidado e a soma dos boletins.**
  Rejeitada: tolerância monetária é dívida silenciosa com o erário. Um centavo por código
  por medição, multiplicado por milhares de linhas e dezenas de períodos, é exatamente o
  erro que este contexto existe para tornar impossível.
- **Escolher a GERAL como verdade e ajustar o boletim da obra.** Rejeitada: o boletim é o
  documento que o fiscal assina por obra. Mexer no total de uma obra para fechar o
  consolidado inverte a ordem da evidência.
- **Deixar a RE-RA editável no v1.** Rejeitada: criar ou alterar aditivo é ato contratual
  da prefeitura, não do sistema. Ler, reconciliar e carregar adiante cobre o que a medição
  precisa sem assumir autoridade que o produto não tem.
- **Corrigir automaticamente a aba divergente na importação.** Rejeitada pela mesma razão
  do ADR-0006: divergência entre duas fontes é assunto de revisão humana, não de
  precedência codificada.

## Consequências

### Positivas

- Saldo e vigente deixam de ser número digitado e passam a ser conta conferida a cada
  importação, com código de erro estável apontando a linha.
- A PLANILHA GERAL gerada é reimportável como consolidado da medição seguinte, o que fecha
  o ciclo `import → export → import` sem intervenção manual.
- O caso ambíguo (mesmo código em mais de uma obra com deriva de truncamento) não vira
  decisão implícita de um agente ou de um desenvolvedor: vira recusa visível com os dois
  números na mão do orçamentista.

### Negativas

- Existe uma classe de medição legítima que o M2 **não** consegue exportar: a que tem
  deriva de centavo entre a consolidação e os boletins. Enquanto a semântica não for
  confirmada, o desbloqueio é redistribuir a quantidade entre as obras ou medir o código
  numa obra só.
- A fixture sintética precisa escolher quantidades sem deriva para exercitar o caminho
  feliz, o que torna o caso ambíguo visível apenas por teste negativo.
- RE-RA só leitura obriga o orçamentista a manter a aba da prefeitura atualizada fora do
  sistema; o sistema recusa a importação quando ela discorda da GERAL, mas não a conserta.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Deriva de centavo publicada em silêncio | `GENERAL_CONSOLIDATION_MISMATCH` recusa a geração da pasta com os dois totais em `details` |
| Vigente divergente entre as duas abas | `GENERAL_AMENDED_DIVERGENT` falha a importação apontando código e valores |
| Saldo estourado por medição nova | `BALANCE_EXCEEDED` bloqueia a exportação por código, no mesmo portão da aprovação |
| Acumulado ou saldo digitado errado no arquivo do cliente | Recomputo na importação, com aba e linha no erro |
| Semântica de consolidação decidida por conveniência de código | Registrada aqui como pendência explícita de confirmação com o orçamentista responsável |
| RE-RA perdida na pasta gerada | A aba de revisões é carregada adiante com os deltas importados e auditada célula a célula |

## Rastreabilidade

- Requirements: VAL-01, VAL-04, VAL-05
- Supersedes: none
- Superseded by: none
