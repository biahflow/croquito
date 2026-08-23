# ADR-0048: Sob demanda contratada, o orçamento assinado é o consolidado contratual da medição

Status: Accepted  
Data: 2026-08-23 (aceito por ato humano na mesma data)  
Responsável: Product / Engineering

## Contexto

A cadeia da medição na `/v1` confere o boletim contra um consolidado contratual que **ela
mesma fabrica**. `bulletin_export_contract`
(`services/api/src/croquito_api/valuation_rounds.py:890`) monta o `ContractWorkbook` exigido
pelo portão de exportação a partir da própria medição: cada código medido vira uma linha de
contrato cuja quantidade contratada é exatamente a que está sendo medida, acumulado zero e
saldo igual ao medido.

O docstring é honesto sobre a consequência, e ela é grave:

> `PERIOD_NOT_SEQUENTIAL`, `BALANCE_EXCEEDED`, `CODE_NOT_IN_CONTRACT`,
> `CODE_AMBIGUOUS_IN_CONTRACT`, `LINE_PRICE_NOT_IN_CONTRACT` e `LINE_UNIT_NOT_IN_CONTRACT`
> **não podem disparar** por aqui. A rodada não tem o fato que os alimentaria (…). Trazer
> saldo de verdade para `/v1` é importar o consolidado contratual — trabalho de marco
> próprio, com rota, coluna e ADR.

São seis guardrails inertes. Medir código que o contrato não tem, medir acima do saldo,
medir por preço diferente do contratado: nada disso é recusado na cadeia da `/v1` hoje. Quem
confere é o auditor, e ele confere o boletim contra o **catálogo instalado**, não contra o
contrato — o que é outra pergunta.

Não é defeito de implementação. É ausência de fato: até 2026-08-22 o produto não tinha, em
lugar nenhum, o que uma obra tem contratado.

**Isso mudou duas vezes na mesma semana.** A
[F-035](../features/F-035-aprovacao-do-orcamento/feature.md)
([ADR-0046](0046-aprovacao-do-orcamento-base.md)) deu ao orçamento uma assinatura nominal
amarrada por digest ao conteúdo exato aprovado. E a
[F-033](../features/F-033-demanda-sob-contrato-licitado/feature.md)
([ADR-0045](0045-terceiro-estado-demanda-sob-contrato.md)) criou o regime
`contracted_demand`: a demanda orçada dentro de um contrato guarda-chuva **já licitado**,
com a forma do orçamento-base e a regra da obra licitada — cascata restrita a `sco` na
instalação.

Para a primeira medição de uma obra orçada sob esse regime, o orçamento assinado **é** o
consolidado que falta. Não existe MAPÃO anterior a importar: a obra nunca foi medida.

### A fronteira que precisa ser refinada, não contrariada

A decisão 6 do [ADR-0027](0027-price-source-provenance-and-bid-boundary.md) diz que o
orçamento-base é cadeia própria, "sem contrato, sem saldo e sem aprovação de medição". Ela
separa **pré-licitação** de **pós-licitação**, e está certa: entre um orçamento-base e o
contrato assinado existem a licitação e o deságio, e o preço muda. Chamar orçamento de
contrato ali seria mentira.

Sob `contracted_demand` não há licitação no meio. O contrato já foi licitado antes de a
demanda existir, e a demanda é orçada pela tabela dele. A separação que a decisão 6 faz não
tem, neste regime, o que separar.

### O fato de domínio que decide o resto

Decisão humana de 2026-08-23, registrada porque tudo abaixo depende dela: **sob
`contracted_demand`, o catálogo `sco` instalado é a tabela contratual** — o preço que o
contrato paga, já com BDI e já com o desconto do contrato.

Disso decorre um defeito que existe hoje e que este ADR fecha. O
[ADR-0038](0038-bdi-como-conceito-de-pre-licitacao.md) rejeitou BDI na medição com esta
razão: "o preço contratado já embute BDI; aplicá-lo de novo é erro de domínio". Mas a F-033
restringiu a cascata sem tocar no BDI: `bdi_percent` continua obrigatório em
`POST /v1/estimate-rounds/{id}/estimate` (`main.py:1533`) e é aplicado sobre preços que, sob
o regime, já o embutem. **Uma rodada sob demanda contratada aplica BDI duas vezes hoje.**

## Decisão

1. **Sob `contracted_demand`, a medição tem consolidado contratual, e ele nasce do orçamento
   assinado.** O ADR-0027 **não é substituído**: ele continua `Accepted` e correto no que
   decidiu — orçamento de pré-licitação segue sem contrato e sem saldo, e nada montado nele
   alcança um boletim sem passar pela medição. O que este ADR fixa é a distinção que a
   leitura literal da decisão 6 apagava: **ausência de licitação entre o orçamento e o
   contrato não é ausência de contrato**. Fora do regime, nada muda.

2. **O preço do consolidado é o preço de fonte (`EstimateLine.unit_price`), nunca o preço
   com BDI.** Sob o regime, esse preço é a tabela contratual, e é o mesmo número que o
   boletim imprimirá, porque o boletim precifica pelo catálogo `sco` instalado. Assim
   `BulletinLine.unit_price == ContractLine.unit_price` (`models.py:540`) passa a valer **por
   construção**, e não por coincidência: os dois lados leem o mesmo catálogo.

3. **Sob `contracted_demand`, o BDI do orçamento é zero, e declarar diferente recusa.**
   Novo código estável `ESTIMATE_BDI_FORBIDDEN_UNDER_REGIME` (`422`), na montagem. É a
   aplicação, ao orçamento, da razão que o ADR-0038 já usou para manter o BDI fora da
   medição. Nenhum modelo muda de forma: `Estimate` não ganha campo e
   `ESTIMATE_SCHEMA_VERSION` não sobe por causa disto. Com BDI zero,
   `unit_price_with_bdi` é `money_trunc(unit_price)` — idêntico ao preço de fonte sempre que
   ele já esteja no centavo, que é como preço de contrato chega; catálogo com mais de duas
   casas trunca, e a decisão 2 continua valendo porque o consolidado usa `unit_price`, não o
   truncado.

4. **A tradução agrega por código, e é o regime que a torna segura.**
   `Estimate.validate_lines` recusa `item_number` repetido, **não** código repetido: o mesmo
   serviço em dois trechos da prancha é itemizado duas vezes com o mesmo código SCO. O
   consolidado, ao contrário, tem chave única grupo+código. Então uma linha de consolidado
   por código, com as quantidades **somadas**. Isso só é lícito porque a cascata do regime
   tem uma fonte só: com cascata livre o mesmo código poderia chegar precificado por duas
   origens, e somar quantidades de preços diferentes seria fabricar um número. Preço ou
   unidade divergentes entre linhas do mesmo código recusam a abertura
   (`ESTIMATE_CODE_PRICE_CONFLICT`), em vez de escolher uma delas.

5. **Grupo único, declarado, e a inércia que sobra é escrita.** O orçamento não tem grupo;
   o consolidado nasce com um grupo só, rotulado com a referência da rodada de orçamento.
   Consequência declarada: `CODE_AMBIGUOUS_IN_CONTRACT` **não pode disparar** para
   consolidado desta origem — não há dois grupos entre os quais ambiguar. Fica escrito, como
   o docstring de hoje escreve a inércia dos seis. Um guardrail que nunca dispara é honesto
   quando declarado; o perigoso é o que finge conferir.

6. **O vínculo é pelo digest assinado, não pelo id da rodada de orçamento.** Remontar o
   orçamento depois — que a F-035 permite, tornando a assinatura caduca — não alcança
   medição já aberta. A rodada de medição guarda a rodada de origem **e** o
   `estimate_digest`, e é o digest que responde "o que foi medido contra o quê".

7. **O consolidado é gravado na abertura da rodada de medição e é imutável nela.** Mesma
   disciplina do catálogo instalado, e pela mesma razão: trocá-lo no meio mudaria
   retroativamente o que já foi conferido. Abrir rodada a partir de orçamento sem assinatura
   válida — nunca assinado, rejeitado, ou caduco — recusa fechado.

8. **Da segunda medição em diante, o consolidado nasce do orçamento MAIS os períodos já
   lançados.** Uma rodada de medição é de um período; a seguinte é rodada nova. A vinculada
   deriva acumulado e saldo do orçamento assinado somados às medições **aprovadas** das
   rodadas anteriores vinculadas ao mesmo digest. Sem rodada anterior o caso degenera no
   simples — `periods = []`, acumulado zero, saldo igual ao contratado —, e é por isso que
   `PERIOD_NOT_SEQUENTIAL` e `BALANCE_EXCEEDED` passam a valer de verdade a partir da
   segunda.

9. **A rodada declara sob qual regime de conferência está.** Rodada sem vínculo continua com
   o consolidado fabricado, exatamente como hoje — removê-lo quebraria toda rodada aberta
   sem orçamento de origem. O que este ADR proíbe é as duas parecerem iguais: a leitura da
   rodada diz se o consolidado é de origem assinada ou fabricado, e o boletim diz o mesmo.

## Alternativas

- **Consolidado com o preço com BDI** — rejeitada pelo fato de domínio registrado no
  contexto: sob o regime o `sco` já é a tabela contratual. O consolidado com BDI faria
  **toda** linha do boletim disparar `LINE_PRICE_NOT_IN_CONTRACT`, transformando um portão
  novo em ruído no primeiro uso.
- **Manter o BDI livre sob o regime e só documentar o risco** — rejeitada: a duplicação já
  acontece, e documentar um erro de dinheiro que o código comete não o impede. O ADR-0038 já
  havia chamado isto de erro de domínio noutro lugar da mesma cadeia.
- **Valer para qualquer orçamento aprovado, com o humano declarando contrato e deságio na
  abertura** — rejeitada: poria um número digitado por humano dentro do consolidado, que é
  justamente o objeto que confere os outros. Consolidado é oráculo, não formulário.
- **Modelar `Contract` como entidade agora** — rejeitada por tamanho, não por mérito: é a
  resposta certa a longo prazo e fecha a lacuna 4 do ADR-0045. Fazê-la aqui trocaria uma
  feature entregável por um marco.
- **Uma linha de consolidado por linha de orçamento** — rejeitada: viola a unicidade
  grupo+código na primeira prancha que itemize o mesmo serviço em dois trechos, que é o caso
  comum e não a exceção.
- **Exigir que o orçamento carregue grupo** — rejeitada nesta rodada: mudaria o modelo do
  orçamento e a tela do takeoff para resolver uma ambiguidade que, com fonte única, não
  existe. Fica como espaço reservado, junto do BDI por grupo do ADR-0038.

## Consequências

### Positivas

- Seis guardrails saem da inércia para o regime em que há fato que os alimente. A classe de
  erro "medi o que o contrato não tem" deixa de ser possível em silêncio.
- A igualdade de preço entre boletim e contrato passa a valer por construção: os dois lados
  leem o mesmo catálogo, em vez de dois números coincidirem por sorte.
- Um erro de dinheiro que existe hoje — BDI aplicado sobre preço que já o embute — é fechado
  no ato, com código estável.
- A cadeia orçamento → obra → medição fica ligada por digest e legível de ponta a ponta, que
  é o que a F-035 começou.

### Negativas

- **Rodada sob `contracted_demand` já montada com BDI > 0 tem total inflado.** Depois desta
  decisão ela deixa de montar, e remontar com BDI zero é ato normal da jornada — mas o número
  antigo existiu e pode ter circulado.
- **Duas semânticas de consolidado convivem**: a de origem assinada e a fabricada. É custo
  aceito para não quebrar rodada existente, e a decisão 9 é o que impede que ele vire
  confusão.
- **`CODE_AMBIGUOUS_IN_CONTRACT` continua inerte** para esta origem, por construção. Fica
  declarado em vez de esquecido.
- A lacuna 4 do ADR-0045 **permanece**: nada aqui confere que o orçamento assinado é do
  contrato certo, só que ele foi assinado e que o regime é o contratado.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Consolidado nascido torto vira seis carimbos, e ninguém olha para portão que já passou | Nenhum número do consolidado é informado por humano; tudo deriva do conteúdo assinado, e preço ou unidade em conflito recusam a abertura em vez de escolher |
| A premissa de domínio (o `sco` do regime é a tabela contratual) estar errada em algum contrato | A decisão 3 torna o desvio visível: uma rodada que precise de BDI sob o regime passa a recusar, e a recusa expõe o caso em vez de o esconder num total |
| Rodada vinculada e rodada fabricada confundidas na operação | Decisão 9: a rodada declara o regime de conferência, e isso é critério de aceite da feature, não detalhe de tela |
| Medição da segunda em diante derivar acumulado errado | Só medição **aprovada** de rodada vinculada ao mesmo digest entra no acumulado; rodada em aberto não conta |
| Assinatura caduca depois de a medição abrir | O consolidado gravado é imutável (decisão 7) e a rodada mostra contra qual digest confere (decisão 6) |

## Rastreabilidade

- Feature: [F-036](../features/F-036-vinculo-orcamento-medicao/feature.md)
- Requirements: VAL-05 (aprovação), VAL-11 (assinatura do orçamento)
- Relacionados: [ADR-0018](0018-valuation-consolidation-and-balance-semantics.md),
  [ADR-0027](0027-price-source-provenance-and-bid-boundary.md),
  [ADR-0038](0038-bdi-como-conceito-de-pre-licitacao.md),
  [ADR-0045](0045-terceiro-estado-demanda-sob-contrato.md),
  [ADR-0046](0046-aprovacao-do-orcamento-base.md)
- Supersedes: none
- Superseded by: none
