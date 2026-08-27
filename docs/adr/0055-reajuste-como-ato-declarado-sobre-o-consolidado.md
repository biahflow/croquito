# ADR-0055: Reajuste é ato declarado sobre o consolidado, e o passado é intocável

Status: Accepted  
Data: 2026-08-27 (aceito por ato humano na mesma data; **emendado na execução**, ver a decisão 6)  
Responsável: Product / Engineering

## Contexto

A [F-039](../features/F-039-reajuste-entre-medicoes/feature.md) nasce da
[issue #99](https://github.com/biahflow/croquito/issues/99): obra longa reajusta, e o produto
não sabe disso. `grep -r reajuste packages services` não devolve nada — não é implementação
parcial, é ausência inteira.

O preço da medição vem do catálogo instalado na rodada e, sob `contracted_demand`, esse
catálogo **é a tabela contratual** ([ADR-0048](0048-consolidado-contratual-do-orcamento-assinado.md)).
O consolidado é gravado na abertura e é imutável na rodada (decisão 7); da segunda medição em
diante ele nasce do orçamento assinado somado aos períodos já lançados (decisão 8). Nada disso
conhece a passagem do tempo.

No dia em que o contrato reajusta, `Valuation.export_errors` compara o preço do boletim com o
do consolidado (`LINE_PRICE_NOT_IN_CONTRACT`) e recusa — com razão. Sobram três saídas, todas
ruins: medir pelo preço velho, ser recusado, ou reajustar por fora e digitar o resultado.

### O que já existe e decide metade do problema

`PeriodProgress` (`contract.py:77`) guarda **quantidade e valor** de cada período já lançado.
O histórico já é à prova de mudança de preço: `accumulated_amount` é a soma dos períodos, cada
um com o dinheiro que valeu quando foi medido.

E `Valuation.export_errors(contract)` recebe o consolidado **por parâmetro** — ele não está
embutido na medição. Acrescentar campo ao consolidado, portanto, **não move**
`Valuation.content_digest()`, e o orçamento assinado da F-035 não é tocado por nada aqui.

### As três decisões de domínio que precederam este ADR

Tomadas por ato humano em 2026-08-27, na abertura da feature:

1. Reajuste pode ser **fator de índice** sobre o preço contratado **ou** **nova versão da
   tabela contratual** — contratos reais fazem as duas coisas.
2. O fator é **digitado**, com índice e período declarados; a tabela de índices importada é
   extensão prevista, não escopo.
3. **Um fator para o contrato inteiro**; fórmula paramétrica por item é extensão.

## Decisão

1. **O reajuste é um ato declarado, gravado com o consolidado da rodada de medição.** Não
   existe hoje entidade "contrato" persistente à qual pendurá-lo: o consolidado é gravado por
   rodada e imutável nela. E uma rodada é de **um período** — declarar ali é exatamente dizer
   "a partir deste período", que é o que um reajuste diz.

2. **Um tipo só, discriminado por `kind`.** `PriceAdjustment` com `kind`
   (`index_factor` | `catalog_version`), autor, instante, índice, período de referência e o
   dado do mecanismo. Não são dois caminhos separados porque o consumidor — boletim, guardrail
   de exportação e memória — precisa de **uma** noção de preço vigente; dois caminhos
   duplicariam essa regra em dois lugares, e o dia em que discordassem produziria dois preços
   para a mesma linha.

3. **O preço vigente é DERIVADO, nunca gravado na linha.** `ContractLine.current_unit_price` é
   propriedade calculada a partir de `unit_price` (o contratado, que não muda) e da cadeia de
   reajustes. Gravar o preço reajustado ao lado da declaração que o produz cria dois lugares
   dizendo a mesma coisa — e é o campo gravado que acaba discordando da relação que ele
   duplica. É o mesmo raciocínio da decisão 4 do
   [ADR-0050](0050-correcao-humana-de-forma-como-proposta-derivada.md).

4. **Reajuste de tipo `catalog_version` carrega o preço resolvido por código.** A tabela nova
   não está dentro do consolidado, então a declaração materializa, no ato, o preço de cada
   código contratado — com o digest da versão de onde saiu. Assim o consolidado continua
   autocontido e auditável meses depois, sem depender de o catálogo daquela data ainda estar
   instalado em algum lugar. Código contratado ausente da versão nova **recusa a declaração**;
   reprecificar metade seria pior que não reprecificar.

5. **Fatores COMPÕEM, e a cadeia inteira fica gravada.** Reajuste anual incide sobre o preço já
   reajustado, não sobre o contratado original: preço vigente = `unit_price × Π fatores`, com
   truncamento de dinheiro no fim, nunca a cada passo. A lista de declarações é preservada
   inteira — a segunda medição precisa poder mostrar de onde veio o preço da primeira.

6. **O passado é intocável, e para isso o período declara o preço dele.** Reajuste vale do
   período desta rodada em diante. Período já lançado mantém quantidade e valor; medição
   aprovada não é recalculada, nem quando o reajuste é declarado depois com efeito retroativo
   em contrato. Se um dia existir reajuste retroativo de verdade, ele será um **acerto lançado
   como período próprio**, e não uma reescrita — mas isso é decisão futura, e este ADR não a
   toma.

   **Emenda de 2026-08-27, descoberta na execução.** A redação original desta decisão dizia
   que `PeriodProgress` já bastava, por guardar quantidade e valor. Não bastava:
   `ContractLine.validate_periods` exige que o valor de **cada** período bata com
   `quantidade × unit_price` da linha (`PERIOD_AMOUNT_MISMATCH`), e a linha tem **um** preço.
   O modelo, como estava, não conseguia representar um contrato reajustado — o período medido
   na base nova era recusado pelo próprio consolidado.

   Por isso `PeriodProgress` ganha `unit_price` **opcional**: o preço daquele período, presente
   só quando difere do contratado. Ausente significa "medido pelo preço contratado", que é a
   verdade sobre todo período anterior a esta feature e sobre todo contrato que nunca
   reajustou. A validação passa a conferir cada período contra o preço dele.

   A emenda não muda o que foi decidido — ela fornece o mecanismo sem o qual a decisão 6 era
   irrepresentável. É aditiva, não move digest assinado (o consolidado não está embutido na
   medição) e consolidado `2.0.0` continua validando.

7. **`LINE_PRICE_NOT_IN_CONTRACT` passa a comparar com o preço VIGENTE.** É o mesmo guardrail,
   sobre o número que o contrato paga hoje. Sem reajuste declarado, vigente é igual a
   contratado e o comportamento é idêntico ao de hoje — bit a bit.

8. **Nenhum digest assinado se move.** O consolidado não está embutido na medição
   (`export_errors` o recebe por parâmetro) e o `Estimate` assinado não ganha campo nenhum.
   `ContractWorkbook.schema_version` sobe para `3.0.0` aceitando `2.0.0`, como
   `Valuation.schema_version` já faz: consolidado gravado antes desta feature continua
   validando, sem reajuste — que é a verdade sobre ele.

9. **Item novo trazido por RE-RA depois de um reajuste nasce na base VIGENTE na data da
   RE-RA**, e acompanha os reajustes seguintes. Ele não recebe retroativamente os fatores dos
   períodos em que não existia: aplicar-lhe um índice de um ano em que ele não estava
   contratado inventaria história. A [issue #100](https://github.com/biahflow/croquito/issues/100)
   respeita esta regra em vez de redecidi-la.

10. **Fórmula paramétrica é extensão, e o modelo já a comporta.** `PriceAdjustment` nasce em
    **lista**, e um campo de escopo opcional (família, grupo, código) cabe depois sem quebrar
    contrato publicado. Enquanto não existir, a ausência de escopo significa "contrato
    inteiro" — que é o que o campo ausente já diz.

## Alternativas

- **Gravar o preço reajustado na linha** — rejeitada pela decisão 3: dois lugares dizendo a
  mesma coisa acabam discordando, e aqui a discordância é dinheiro.
- **Reajustar o catálogo instalado** — rejeitada. Sob `contracted_demand` o catálogo é a tabela
  contratual, mas o reajuste é do **contrato**, não da tabela: dois contratos assinados em datas
  diferentes sobre a mesma tabela reajustam em datas diferentes. Mover a tabela moveria os dois.
- **Recalcular medições anteriores** — rejeitada pela decisão 6. Muda dinheiro já pago.
- **Buscar o índice em fonte externa** — rejeitada por ora: introduziria dependência de rede e
  de disponibilidade de terceiro num caminho que precisa ser determinístico e auditável. A
  tabela importada é a extensão prevista, no mesmo idioma da tabela de preços.
- **Aplicar o fator sobre o contratado original a cada reajuste** (em vez de compor) —
  rejeitada: contraria como reajuste anual funciona e produziria, no terceiro ano, um preço
  menor que o devido.
- **Um `ContractWorkbook` novo por reajuste** — rejeitada: o consolidado carrega os períodos
  lançados, e duplicá-lo por reajuste duplicaria o histórico junto, criando duas verdades sobre
  o mesmo acumulado.

## Consequências

### Positivas

- O reajuste passa a ser conferível: índice, período, fator e a conta ao lado do preço.
- Nenhum artefato assinado muda de digest, e nenhum caminho existente muda de comportamento
  quando não há reajuste declarado.
- O consolidado continua autocontido: meses depois, ele explica o próprio preço sem depender de
  catálogo instalado nem de fonte externa.
- A cadeia de fatores preservada responde "por que este preço" sem instrumentação nova.

### Negativas

- **`ContractWorkbook` muda de schema**, e todo caminho que o constrói passa a lidar com a
  versão nova — aditivo, mas é contrato publicado.
- **Preço vigente derivado custa uma travessia** da lista de reajustes a cada linha. É barato e
  é correto; um campo gravado seria mais rápido e mentiria eventualmente.
- **O fator é digitado**, então um erro de digitação contamina a medição inteira. Mitigado pela
  exigência de índice e período junto do fator — que é o que torna a declaração conferível
  contra a publicação oficial —, não por validação que o sistema não tem como fazer.
- **Reajuste retroativo não é atendido** nesta decisão, e isso fica escrito em vez de
  silencioso.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Reescrever medição já aprovada | Decisão 6: o passado é intocável, e `PeriodProgress` já guarda o valor de cada período |
| Preço vigente divergir da declaração | Decisão 3: derivado, nunca gravado |
| Consolidado deixar de explicar o próprio preço | Decisão 4: `catalog_version` materializa preço por código com o digest da origem |
| Fator digitado errado | Índice e período obrigatórios: a declaração é conferível por quem revisa |
| Reprecificação parcial numa versão nova de tabela | Decisão 4: código ausente recusa a declaração inteira |
| Confundir reajuste com reequilíbrio | Fora de escopo, declarado no Feature Contract |

## Rastreabilidade

- Feature: [F-039](../features/F-039-reajuste-entre-medicoes/feature.md)
- Issue: [#99](https://github.com/biahflow/croquito/issues/99)
- Relacionados: [ADR-0048](0048-consolidado-contratual-do-orcamento-assinado.md),
  [ADR-0027](0027-price-source-provenance-and-bid-boundary.md),
  [ADR-0045](0045-terceiro-estado-demanda-sob-contrato.md),
  [ADR-0050](0050-correcao-humana-de-forma-como-proposta-derivada.md)
- Supersedes: none
- Superseded by: none
