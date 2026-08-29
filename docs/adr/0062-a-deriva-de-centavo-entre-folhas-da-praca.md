# ADR-0062: A GERAL governa o centavo, e a deriva entre folhas é declarada

Status: Accepted  
Data: 2026-08-29 (decidido por ato humano em 2026-08-29, Daniel Campos)  
Responsável: Product / Engineering

## Contexto

O [ADR-0018](0018-valuation-consolidation-and-balance-semantics.md), decisão (c), já decidiu
que o valor consolidado do período é `TRUNC(Σ quantidade × preço)` — soma as quantidades do
código e trunca o produto **uma vez só**. E deixou um caso explicitamente em aberto: quando
esse total não fecha com a soma dos totais das linhas de boletim, a diferença de um centavo
não tem dono, então `_check_consolidated_total`
(`packages/valuation/src/croquito_valuation/workbook_writer.py:677`) recusa com
`TRUNC_CONSOLIDATION_DRIFT` e **nenhuma pasta é gerada**. O próprio ADR-0018 registra, nas
consequências, que "o caso ambíguo não vira" decisão ali.

Recusar era o certo enquanto o caso era raro. Ele só aparecia com o mesmo código medido em
**mais de uma obra**, que é situação de exceção no produto.

A [F-046](../features/F-046-praca-de-varias-pranchas/feature.md) muda essa frequência. A praça
de várias folhas produz **um boletim por folha** (T2), e o mesmo serviço em duas folhas passa a
ser o caso **normal**, não a exceção: uma praça com alambrado na planta geral e no detalhe já
soma dois boletins do mesmo código. O guardrail continuaria correto e passaria a travar a
jornada com frequência, sem caminho de saída dentro do sistema — a orçamentista veria "a pasta
não gera" e não teria o que fazer.

## Decisão

1. **O valor consolidado do código é `TRUNC(Σ quantidade × preço)`, e ele governa.** É a
   decisão (c) do ADR-0018, agora com o caso ambíguo resolvido: quando os dois números
   divergem, o da PLANILHA GERAL é o que vale. O motivo é a fórmula da própria prefeitura — a
   célula da GERAL é `=TRUNC(quantidade × preço, 2)` sobre a quantidade consolidada da linha,
   e é esse arquivo que é entregue e conferido.

2. **A deriva deixa de recusar a pasta e passa a ser declarada.** `TRUNC_CONSOLIDATION_DRIFT`
   deixa de ser erro fatal e vira registro visível: o valor da GERAL, a soma dos boletins, a
   diferença e os códigos em que ela ocorreu. Quem confere vê o centavo e de onde ele vem,
   em vez de ver um arquivo que não nasce.

3. **O boletim de cada folha continua truncando a sua própria linha.** Ele não é reescrito para
   fechar com a GERAL: a linha do boletim é o produto truncado da quantidade **daquela folha**,
   e mexer nisso publicaria na folha um número que a folha não mede. A folha é vista parcial;
   a GERAL é o consolidado.

4. **Nenhum total informado passa a valer sem recomputo.** O que muda é o desempate entre dois
   números recomputados, nunca a regra de que o total declarado por terceiro não é aceito.

## Alternativas

- **Consolidar por soma dos `TRUNC` de cada folha** — rejeitada pelo mesmo argumento da
  alternativa já rejeitada no ADR-0018: a célula da GERAL deixaria de ser `=TRUNC(q × preço,2)`
  sobre a própria linha, e a planilha entregue passaria a mostrar uma conta que ela mesma não
  refaz.
- **Manter a recusa** — rejeitada pela decisão 2. Era proporcional enquanto o caso era de
  exceção; com a praça de várias folhas ela vira parede na jornada normal, e a saída seria
  fora do sistema, que é onde os erros moram.
- **Ajustar a última linha de boletim para absorver a diferença** — rejeitada: publicaria numa
  folha um valor que aquela folha não mede, e o ajuste ficaria invisível na conferência.

## Consequências

### Positivas

- A praça de várias folhas gera pasta sem depender de sorte de arredondamento.
- O centavo passa a ter dono declarado, e a diferença fica auditável em vez de fatal.
- A decisão (c) do ADR-0018 fica completa: o que era regra com buraco vira regra inteira.

### Negativas

- **A soma dos boletins pode não bater com a GERAL em alguns centavos**, e quem confere folha a
  folha vai encontrar isso. É consequência assumida da decisão 3, e é por isso que a decisão 2
  exige que a diferença seja mostrada, não escondida.
- Um erro real de quantidade que hoje aparecia como recusa passará a aparecer como deriva
  declarada. A mitigação é o tamanho: deriva de truncamento é de centavos por código, e
  qualquer diferença acima disso continua sendo sinal de outro problema.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Deriva grande passar como se fosse de arredondamento | O registro traz o valor dos dois lados e a diferença por código; deriva de truncamento é de centavos por linha |
| Boletim de folha e GERAL divergirem sem aviso | Decisão 2: a diferença é declarada no artefato, não deduzida por quem confere |
| Regra silenciosamente aplicada a rodada de uma folha | Praça de uma folha não tem duas parcelas do mesmo código; o caminho responde como hoje |

## Rastreabilidade

- Feature: [F-046](../features/F-046-praca-de-varias-pranchas/feature.md)
- Issue: [#101](https://github.com/biahflow/croquito/issues/101)
- Relacionados: [ADR-0018](0018-valuation-consolidation-and-balance-semantics.md) (decisão (c),
  que este ADR completa), [ADR-0057](0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md)
- Supersedes: none
- Superseded by: none
