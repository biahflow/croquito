# F-036 — A medição do orçamento aprovado: consolidado contratual de origem

## Status

`BLOCKED`

> Selecionada por decisão humana de 2026-08-23, saindo de `READY_FOR_SPEC`, logo depois de a
> [F-035](../F-035-aprovacao-do-orcamento/feature.md) trazer a aprovação do orçamento para
> dentro do produto — sem assinatura não haveria o que a medição herdasse.
>
> Dois gates humanos precedem o planejamento e são o que a mantém `BLOCKED`:
> `ARCHITECTURE_DECISION_REQUIRED`, porque a feature atravessa a fronteira que o
> [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md) decisão 6 desenhou,
> e `DESIGN_APPROVAL_REQUIRED`, porque abre superfície nova na tela de abertura da medição.
> Ver **Human Gates**.
>
> Duas escolhas humanas de 2026-08-23 já fixaram o recorte e estão em `Scope`: o vínculo
> entrega **consolidado contratual**, não só referência de auditoria; e vale **apenas** para
> rodada sob o regime `contracted_demand`.

## Classification

`INTERFACE_CHANGE` — abrir a medição a partir de um orçamento assinado é escolha nova na
seção "Abrir rodada nova" (`apps/web/src/medicao/MedicaoApp.tsx`), percebida por humano.

## Priority

`HIGH` — é o elo que falta na cadeia que a F-035 fechou do lado do orçamento. Enquanto não
existir, a medição de uma obra orçada aqui dentro continua conferindo contra um consolidado
que ela mesma inventou.

## Problem

### O consolidado da medição na `/v1` é fabricado, e o código diz isso por escrito

`bulletin_export_contract` (`services/api/src/croquito_api/valuation_rounds.py:890`) monta o
`ContractWorkbook` que o portão de exportação exige **a partir da própria medição**: cada
código medido vira uma linha de contrato cuja quantidade contratada é exatamente a que está
sendo medida, com acumulado zero e saldo igual ao medido. O docstring é honesto sobre a
consequência, e vale citá-la:

> `PERIOD_NOT_SEQUENTIAL`, `BALANCE_EXCEEDED`, `CODE_NOT_IN_CONTRACT`,
> `CODE_AMBIGUOUS_IN_CONTRACT`, `LINE_PRICE_NOT_IN_CONTRACT` e `LINE_UNIT_NOT_IN_CONTRACT`
> **não podem disparar** por aqui. A rodada não tem o fato que os alimentaria (…). Trazer
> saldo de verdade para `/v1` é importar o consolidado contratual — trabalho de marco
> próprio, com rota, coluna e ADR.

São **seis guardrails inertes**. Não é defeito de implementação: é ausência de fato. Medir
um código que o contrato não tem, medir acima do saldo, medir por preço diferente do
contratado — nada disso é recusado hoje na cadeia da `/v1`. Quem confere é o auditor, e ele
confere o boletim contra o **catálogo instalado**, não contra o contrato.

### O fato existe agora, e é o orçamento assinado

Desde a [F-035](../F-035-aprovacao-do-orcamento/feature.md)
([ADR-0046](../../adr/0046-aprovacao-do-orcamento-base.md)), o orçamento-base tem
`EstimateApproval`: decisão nominal de um `aprovador` que não é quem montou, amarrada por
digest ao conteúdo exato assinado. E `EstimateLine` carrega, por código, exatamente o que
uma linha de consolidado precisa — descrição, unidade, quantidade, preço e proveniência.

Para a **primeira** medição de uma obra orçada aqui dentro, o orçamento assinado **é** o
consolidado contratual. Não existe MAPÃO anterior a importar: a obra nunca foi medida.

### E nada liga uma coisa à outra

`ValuationRoundRecord` não referencia rodada de orçamento nenhuma. `contract_label` é texto
livre. A rodada de medição é aberta do zero, com outro catálogo por upload, e o produto não
sabe que aquela medição mede aquele orçamento — nem para conferir, nem para auditar.

## Desired Outcome

Uma rodada de medição aberta a partir de um orçamento assinado nasce com um consolidado
contratual **de origem declarada**, e os seis guardrails passam a poder disparar. Medir
código fora do orçamento, acima do saldo ou por preço diferente do assinado deixa de ser
possível em silêncio.

O vínculo é auditável nos dois sentidos: a medição diz de qual orçamento veio, e diz de qual
**conteúdo assinado** veio — pelo digest, não pelo id da rodada, porque remontar o orçamento
depois não pode reescrever o que já foi medido contra ele.

## Scope

### Restrito ao regime `contracted_demand` (decisão humana de 2026-08-23)

Só rodada de orçamento com `pricing_regime = "contracted_demand"`, o terceiro estado que a
[F-033](../F-033-demanda-sob-contrato-licitado/feature.md) criou sobre o
[ADR-0045](../../adr/0045-terceiro-estado-demanda-sob-contrato.md), pode originar o
consolidado.

O porquê é a fronteira do ADR-0027: entre um orçamento-base de pré-licitação e o contrato
assinado existem a licitação e o deságio, e o preço muda. Chamar o orçamento de contrato ali
seria mentira. Sob `contracted_demand` **não há licitação no meio** — a demanda é orçada
dentro de um contrato guarda-chuva já licitado, a cascata está restrita a `sco` na
instalação, e o preço do orçamento é o preço da tabela contratual. É o único regime em que
a igualdade se sustenta, e é por isso que a feature nasce aqui em vez de nascer para todos.

### A tradução `Estimate` → `ContractWorkbook`

Uma linha de consolidado **por código**, com as quantidades somadas, e nenhum número
informado por humano:

```text
unit_price          = EstimateLine.unit_price      (nunca o preço com BDI)
contract_quantity   = soma das quantidades assinadas daquele código
amended_quantity    = a mesma (não há RE-RA antes da primeira medição)
periods             = []           (nenhuma medição lançada; ver ADR-0048 decisão 8)
accumulated_*       = 0
balance_quantity    = contract_quantity
source_sha256       = estimate_digest da aprovação
group_label         = referência da rodada de orçamento (grupo único)
```

**Agregar por código não é detalhe.** `Estimate.validate_lines` recusa `item_number`
repetido, **não** código repetido: o mesmo serviço em dois trechos da prancha é itemizado
duas vezes com o mesmo código SCO, e o consolidado tem chave única grupo+código. Copiar
linha a linha quebraria na primeira prancha assim, que é o caso comum. Somar só é lícito
porque a cascata do regime tem **uma fonte só** — preço ou unidade divergentes entre linhas
do mesmo código recusam a abertura em vez de escolher uma delas.

`source_sha256` deixa de ser o digest da própria medição — que é o que a fabricação usa hoje
— e passa a ser o do conteúdo assinado. Quem encontrar o consolidado consegue dizer de onde
ele veio.

### O consolidado é dado da rodada de medição, gravado uma vez

Nasce na criação da rodada e é imutável nela, pela mesma razão que o catálogo é: trocar o
consolidado no meio da rodada mudaria retroativamente o que já foi conferido. Remontar o
orçamento depois — que a F-035 torna possível, tornando a assinatura **caduca** — não
alcança rodada de medição já aberta.

### O vínculo é declarado e legível

A rodada de medição referencia a rodada de orçamento e o digest assinado. A leitura da
rodada devolve os dois, e a origem do consolidado aparece por escrito para quem estiver
lendo o boletim.

### `bulletin_export_contract` deixa de fabricar quando há consolidado real

Com vínculo, o portão recebe o consolidado gravado. **Sem** vínculo, a rodada segue
exatamente como hoje — a fabricação continua existindo, porque removê-la quebraria toda
rodada aberta sem orçamento de origem. O que não pode continuar é as duas parecerem iguais:
a rodada precisa dizer sob qual dos dois regimes de conferência ela está.

## Out of Scope

- **Modelar `Contract` como entidade.** É a lacuna 4 da
  [cadeia operacional](../../product/CADEIA_OPERACIONAL.md), nomeada na decisão 6 do
  ADR-0045, e continua aberta depois desta feature: o consolidado passa a vir de um
  orçamento assinado, e ainda assim ninguém confere que aquele orçamento é do contrato certo.
- **Orçamento fora do regime `contracted_demand`** — licitação e deságio ficam de fora por
  decisão humana registrada em `Scope`.
- **Criar ou alterar aditivo/RE-RA a partir do orçamento.** RE-RA segue só leitura
  ([ADR-0018](../../adr/0018-valuation-consolidation-and-balance-semantics.md)).
- **Substituir a importação do MAPÃO** para quem tem histórico: a obra já medida continua
  trazendo o consolidado de fora.
- **Acervo de catálogos na medição.** A rodada de medição ainda só aceita
  `catalog_upload_id`; a F-037 abriu o acervo apenas para o orçamento. Fica **nomeado**
  aqui porque toca esta feature (ver Unknown 2), e não resolvido nela.
- Despacho, e-mail ou Drive — como na F-035.

## Acceptance Criteria

1. `make check` e `make test` verdes; goldens intocados.
2. Rodada de medição aberta **sem** vínculo se comporta exatamente como hoje, com teste que
   estende os existentes sem enfraquecê-los.
3. Abrir medição a partir de rodada de orçamento **sem** regime `contracted_demand` recusa
   com código estável, e não grava nada.
4. Abrir medição a partir de orçamento **sem aprovação válida** — nunca assinado, assinatura
   rejeitada, ou assinatura caduca por remontagem — recusa com código estável e não grava.
5. Com vínculo, os seis guardrails **disparam de verdade**, cada um com teste próprio:
   código fora do orçamento, quantidade acima do saldo, preço divergente, unidade
   divergente, código ambíguo e período fora de sequência.
6. O consolidado gravado é imutável na rodada: remontar ou reaprovar o orçamento depois não
   o altera, e há teste que prova isso.
7. A leitura da rodada de medição devolve a rodada de orçamento de origem e o digest
   assinado; o boletim declara a origem do consolidado.
8. A tela corresponde à revisão aprovada do Design Approval Package.

## Constraints

- `tenant_id` vem sempre do JWT; a rodada de orçamento de origem tem de ser do mesmo tenant.
- **Fail-closed**: qualquer dúvida sobre a origem recusa a abertura, em vez de abrir uma
  rodada que confere contra um consolidado parcial.
- **Nenhum número do consolidado é informado por humano na abertura.** Consolidado é o que
  confere os outros; um valor digitado ali transformaria o portão em carimbo.
- Preço, unidade e quantidade saem do conteúdo **assinado**, nunca do estado corrente da
  rodada de orçamento.
- A medição continua exigindo `sco` (`BULLETIN_PRICE_ORIGIN_FORBIDDEN`) — esta feature não
  afrouxa nada.
- Nada de reescrever `Amendment`: o consolidado nasce sem RE-RA.

## Dependencies

- [F-035](../F-035-aprovacao-do-orcamento/feature.md) e o
  [ADR-0046](../../adr/0046-aprovacao-do-orcamento-base.md) — a assinatura é o fato que esta
  feature herda. Entregue, em `READY_FOR_HUMAN_REVIEW`.
- [F-033](../F-033-demanda-sob-contrato-licitado/feature.md) e o
  [ADR-0045](../../adr/0045-terceiro-estado-demanda-sob-contrato.md) — o regime
  `contracted_demand` é a condição de existência do recorte. Entregue.
- [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md) decisão 6 — é a
  fronteira que o ADR novo precisa refinar, e não contradizer em silêncio.
- [ADR-0018](../../adr/0018-valuation-consolidation-and-balance-semantics.md) — a semântica
  de consolidado e saldo que esta feature passa a alimentar de verdade.

## Unknowns

Os quatro primeiros foram levados ao
[ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md), escrito em
2026-08-23 e ainda `Proposed`: enquanto ele não for aceito por ato humano, seguem sendo
desconhecidos deste contrato. O que o ADR **propõe** para cada um está anotado abaixo.

1. **O preço do consolidado é `unit_price` ou `unit_price_with_bdi`?** O portão exige
   `BulletinLine.unit_price == ContractLine.unit_price`
   (`packages/valuation/src/croquito_valuation/models.py:540`), e o boletim precifica pelo
   catálogo `sco` instalado. Se o consolidado nascer com BDI, **toda** linha dispara
   `LINE_PRICE_NOT_IN_CONTRACT` e o portão vira ruído no primeiro uso. Era a decisão mais
   consequente da feature.
   → *ADR-0048 decisões 2 e 3*: `unit_price`, apoiado no fato de domínio declarado por ato
   humano em 2026-08-23 — sob o regime, o `sco` instalado **é** a tabela contratual, com BDI
   e desconto já embutidos. Daí decorre que declarar BDI numa rodada sob o regime é o erro
   que o [ADR-0038](../../adr/0038-bdi-como-conceito-de-pre-licitacao.md) já nomeara noutro
   lugar da cadeia, e passa a recusar.
2. **O catálogo da medição precisa ser o mesmo objeto que precificou o orçamento?** Exigir o
   mesmo digest fecha a última folga — hoje nada impede medir com um catálogo `sco` diferente
   daquele que orçou.
   → *ADR-0048 decisão 2*: não é exigido como regra separada, porque a igualdade de preço
   passa a valer por construção; um catálogo diferente aparece como
   `LINE_PRICE_NOT_IN_CONTRACT`, que é recusa tardia mas honesta e agora **pode** disparar.
3. **Qual `group_label`?** A chave de unicidade do consolidado é **grupo + código**
   (`contract.py`), e o orçamento não tem grupo.
   → *ADR-0048 decisões 4 e 5*: grupo único rotulado com a referência da rodada, e a tradução
   **agrega por código** — `Estimate` permite código repetido em itens diferentes. A inércia
   que sobra (`CODE_AMBIGUOUS_IN_CONTRACT` não dispara nesta origem) fica declarada.
4. **Quantas medições um orçamento sustenta?** A segunda precisa do acumulado da primeira.
   → *ADR-0048 decisão 8*: o consolidado da rodada vinculada deriva do orçamento assinado
   **mais** as medições aprovadas das rodadas anteriores ligadas ao mesmo digest. Sem rodada
   anterior o caso degenera no simples.
5. **Onde o consolidado é gravado** — coluna na raiz da rodada ou na revisão. Forma, não
   comportamento; sai no plano. O ADR não o decide de propósito.

## Risks

- **Consolidado errado é pior que consolidado ausente.** Hoje o produto declara que não
  confere; depois desta feature ele afirma que confere. Um consolidado nascido torto
  transforma seis portões em seis carimbos, e ninguém olha para um portão que já passou.
- **Dois regimes de conferência convivendo.** Rodada com vínculo e rodada sem vínculo terão
  a mesma cara na listagem e garantias diferentes. Mitigação escrita em `Scope`: a rodada
  precisa declarar sob qual regime está, e isso é critério de aceite 7, não detalhe de tela.
- **A lacuna que permanece.** Nada aqui confere que o orçamento assinado é do contrato
  certo — só que ele foi assinado e que o regime é o contratado. Fica nomeada, como a
  F-033 nomeou a sua.
- **Assinatura caduca no meio do caminho.** A F-035 permite remontar depois de assinar, o
  que caduca a assinatura. Se a medição já abriu, o consolidado gravado continua valendo — e
  isso precisa ser evidente para quem lê a rodada, senão parece que a medição confere contra
  algo que não existe mais.

## Human Gates

1. **`ARCHITECTURE_DECISION_REQUIRED`** — **artefato produzido, gate aberto**. O
   [ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md) foi escrito em
   2026-08-23 e está `Proposed`: ele refina a fronteira do ADR-0027 decisão 6 ("sem contrato,
   sem saldo") para o caso `contracted_demand` e propõe os Unknowns 1 a 4. **Aceitá-lo é ato
   humano**, e nenhuma implementação irreversível o precede.
2. **`DESIGN_APPROVAL_REQUIRED`** — **pacote produzido, gate aberto**. O
   [Design Approval Package](mock/README.md) da superfície nova na abertura da medição está
   na revisão 1, **pendente de aprovação humana**, conforme
   [design-approval](../../engineering-os/workflows/design-approval.md).

Produzir o artefato não é cumprir o gate. Nenhum agente aceita ADR nem aprova design,
inclusive o que os escreveu. Enquanto os dois não forem exercidos por ato humano, a feature
permanece `BLOCKED`.

## References

- [ADR-0027 — fontes de preço com proveniência e a fronteira licitada × pré-licitação](../../adr/0027-price-source-provenance-and-bid-boundary.md)
- [ADR-0045 — terceiro estado: demanda sob contrato](../../adr/0045-terceiro-estado-demanda-sob-contrato.md)
- [ADR-0046 — aprovação do orçamento-base](../../adr/0046-aprovacao-do-orcamento-base.md)
- [ADR-0018 — consolidação da medição e semântica de saldo](../../adr/0018-valuation-consolidation-and-balance-semantics.md)
- [Cadeia operacional](../../product/CADEIA_OPERACIONAL.md) — lacuna 4
- [Valuation Context](../../architecture/VALUATION_CONTEXT.md)
