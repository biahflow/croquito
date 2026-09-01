# F-040 — RE-RA declarada e a medição seguinte

## Status

`READY_FOR_HUMAN_REVIEW`

> **Estado em 2026-09-01.** A condição que o `DONE` de 2026-08-28 deixou pendente — a recaptura
> dos estados que a T6 acrescentou — foi **cumprida**: os seis estados foram capturados contra
> o stack local, já com a T6 e a T7 no código e sobre a `main` de `482fa8e` (F-046 e F-047
> integradas). A T6 e a T7 entraram na `main` pelo PR
> [#129](https://github.com/biahflow/croquito/pull/129).
>
> O que resta é ato humano: a **confirmação** de que o aceite de 2026-08-28 permanece agora que
> o pacote de design está inteiro no código, e o aceite numa medição real com contrato
> re-ratificado — nenhuma foi feita, e o dado de toda a evidência é sintético.
>
> Histórico. Encerrada como `DONE` em 2026-08-28: a evidência de navegador (`BROWSER_REQUIRED`, AC 11) foi capturada
> nessa data contra o stack local — quatro estados da tela real, registrados em
> [evidence.md](evidence.md) — e o **aceite humano** que fecha a
> [issue #100](https://github.com/biahflow/croquito/issues/100) ocorreu em 2026-08-28. O
> código já estava na `main` (PRs #109, #112 e #113).
>
> **Reaberta na prática pela T6, em 2026-08-28.** A captura da evidência de navegador expôs que
> **três decisões do [pacote de design aprovado](mock/README.md)** não estavam no código — as
> decisões 1, 4 e 6 — e que, por causa disso, **não havia como declarar uma RE-RA na medição
> seguinte pela tela**, embora a API sempre a tenha aceitado. A
> [T6](tasks/T6-a-porta-da-medicao-seguinte.md) fecha as três, e a
> [T7](tasks/T7-previa-no-servidor.md) leva a conta da prévia para o servidor. A recaptura que
> faltava foi feita em 2026-09-01 e está em [evidence.md](evidence.md).
>
> **Dívida que fica escrita**: nenhuma medição real com contrato re-ratificado foi feita — o
> aceite de 2026-08-28 é sobre o mecanismo, e a primeira rodada de obra com RE-RA declarada
> segue sendo o teste de verdade. Ficam também os desvios listados em
> [evidence.md](evidence.md): a memória sem RE-RA não imprime contratado e vigente repetidos
> (a repetição de propósito existe na herança da medição seguinte, que é onde a decisão 4 a
> pede), e a autoria da declaração aparece como o `sub` do principal, não como nome legível. A
> prévia, que a T6 tinha só na medição seguinte, existe nas **duas** portas contratadas desde a
> T7.
>
> Registrada em 2026-08-27, por seleção humana, a partir da
> [issue #100](https://github.com/biahflow/croquito/issues/100). Três decisões de domínio
> foram tomadas por ato humano na abertura e estão em **Scope** — elas são o que separa esta
> feature de uma especulação, e duas delas **encolhem** o escopo que a issue supunha.
>
> A issue listava três perguntas "a decidir antes de planejar". Duas já estavam respondidas
> pelo [ADR-0055](../../adr/0055-reajuste-como-ato-declarado-sobre-o-consolidado.md), aceito
> um dia antes: a decisão 1 (ato declarado gravado com o consolidado da rodada) e a decisão 6
> (o passado é intocável). A decisão 9 do mesmo ADR já legislou sobre item novo trazido por
> RE-RA depois de um reajuste, e diz nominalmente que esta issue **respeita** a regra em vez
> de redecidi-la.

## Classification

`INTERFACE_CHANGE` — declarar a RE-RA é ato humano novo na abertura da rodada de medição, e
abrir a medição seguinte é uma jornada que hoje não existe na tela. O vigente e o saldo
mudam de valor à vista do usuário, e a memória precisa mostrar de onde o número novo veio.

## Priority

`HIGH` — sem a medição seguinte, a cadeia de medição só sabe medir uma vez. É a lacuna que
segura o exercício de ponta a ponta de duas features já entregues: o reajuste da
[F-039](../F-039-reajuste-entre-medicoes/feature.md) só compõe entre períodos, e o
acumulado do [ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md)
(decisão 8) nunca é exercido.

## Problem

### O que existe hoje, e é mais do que a issue supõe

O **efeito** da RE-RA sobre a quantidade está inteiro e validado.
`ContractWorkbook.validate_amendments` (`packages/valuation/src/croquito_valuation/contract.py:456-525`)
já exige que `amended_quantity` seja exatamente `contract_quantity + Σ deltas`
(`AMENDMENT_APPLICATION_MISMATCH`), e já recusa resultado negativo
(`AMENDMENT_NEGATIVE_RESULT`), código ambíguo no consolidado
(`CODE_AMBIGUOUS_IN_CONTRACT`), item novo sobre linha que não está zerada
(`AMENDMENT_NEW_ITEM_INVALID`) e alvo inexistente (`AMENDMENT_TARGET_UNKNOWN`). A mesma RE-RA
alterando o código duas vezes já é recusada em `Amendment.validate_unique_codes`
(`contract.py:113-122`).

O saldo já responde à RE-RA: `balance_quantity` deriva do vigente e `BALANCE_EXCEEDED`
(`models.py:738`) já barra medir acima dele. Ler o MAPÃO da prefeitura já popula tudo
(`workbook_reader.py:789-866`). E o **pedido** do aditivo já é artefato de fechamento com
rota e CLI (`amendment_dossier.py`, `POST /v1/valuation-rounds/{id}/amendment-dossier`).

### O que falta, e é outra coisa

**1 · A RE-RA é anônima.** `Amendment` tem `label` e `lines`, e nada mais (`contract.py:107-122`).
Seu gêmeo em preço, `PriceAdjustment`, carrega `declared_by`, `declared_at` e
`reference_period` — a citação que torna a declaração conferível contra a publicação oficial.
Enquanto a RE-RA só era **lida** da planilha, a procedência era implícita e suficiente: "veio
do MAPÃO, que a prefeitura assinou". No dia em que ela nasce aqui dentro, `label` não diz
quem declarou, quando, nem contra qual publicação se confere.

**2 · Não existe caminho de entrada.** Nenhuma rota, nenhum subcomando, nenhuma tela cria um
`Amendment`. Os únicos produtores são `workbook_reader._to_amendments` (leitura de planilha) e
os builders de teste. Fora isso, `Amendment(...)` só aparece na própria definição da classe.

**3 · A medição seguinte não existe.** Esta é a descoberta que muda o tamanho da feature.

Na `/v1`, `contract_workbook_json` é gravado por **um** caminho: a abertura da rodada a partir
do orçamento assinado (`main.py:4147`). E `build_contract_from_estimate` serve **só a primeira
medição** — a própria docstring diz que somar os períodos já aprovados "é trabalho de quem a
construir — esta função não ganha parâmetro que nenhum chamador usa hoje"
(`contract_from_estimate.py:88-91`). Não há chamador. `periods` nasce vazio, o acumulado é
zero e o saldo é o contratado inteiro (`contract_from_estimate.py:117-121`).

Re-ratificação é, por definição, o que acontece **entre** medições. Entregar a declaração de
RE-RA sem a rodada seguinte produziria um campo declarável apenas na abertura do período 1 —
exatamente onde ainda não houve o que re-ratificar.

### A assimetria que a F-039 deixou à vista

O ADR-0055 decidiu, para preço, que **o vigente é derivado, nunca gravado** (decisão 3):
`current_unit_price` é propriedade calculada, porque um campo ao lado da declaração que o
produz seria um segundo lugar dizendo a mesma coisa — e é o campo gravado que acaba
discordando da relação que ele duplica.

Para quantidade, `amended_quantity` é **campo gravado** na linha. Enquanto o número vinha da
planilha da prefeitura, isso não era duplicação: era **oráculo externo**, e a validação
existia para conferir a planilha contra a soma dos deltas. Quando a RE-RA passar a nascer no
sistema, o mesmo campo vira duplicata de uma relação que o próprio modelo calcula.

## Desired Outcome

A obra mede o período 1, o contrato é re-ratificado, e o período 2 abre com o vigente novo, o
acumulado somado e o saldo correto — sem que nada do período 1 seja reescrito.

Observável: uma rodada de medição de período `n > 1` cujo consolidado traz os períodos
anteriores lançados com o dinheiro que valeu em cada um, as RE-RA declaradas com autor e
citação, e um saldo que é `vigente − acumulado` para cada código. O boletim do período 2
recusa quantidade acima do vigente **novo**, e a memória mostra de onde o vigente novo veio.

## Scope

### As três decisões de domínio tomadas na abertura

Tomadas por ato humano em 2026-08-27, e é o que esta feature implementa:

**1 · O sistema registra a RE-RA aprovada, não o pedido com estado.** Não há máquina de
estados `pendente → aprovado/negado`. O pedido já tem artefato — o dossiê do aditivo — e
`amendment_dossier.py` declara nas próprias notas de segurança que "a solicitação do aditivo à
prefeitura é ato contratual humano, fora deste sistema", o que o [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md)
sustenta. A RE-RA entra quando volta deferida, como declaração — espelho exato do reajuste.

**2 · O vigente passa a ser derivado, como o preço.** `ContractWorkbook.current_quantity(line)`
vira a fonte, simétrica a `current_unit_price`. O campo `amended_quantity` sobrevive como
**conferência**: quando presente, precisa bater com o derivado, e quem recusa continua sendo
`AMENDMENT_APPLICATION_MISMATCH`. É a forma que preserva o oráculo da planilha sem manter dois
donos do mesmo número.

**3 · A abertura da medição seguinte entra no escopo.** Sem ela a RE-RA não é exercível.

### O que a feature entrega

- **`Amendment` ganha procedência**: `declared_by`, `declared_at` (com fuso, como o reajuste),
  `reference_period` como citação da publicação oficial, e `note` opcional. Simétrico a
  `PriceAdjustment` (`contract.py:125-215`), pelo mesmo motivo: número que ninguém consegue
  conferir não entra na medição.
- **Vigente derivado**: `current_quantity` como propriedade; `amended_quantity` opcional e
  conferido; `balance_quantity` recebe o mesmo tratamento, porque saldo é `vigente − acumulado`
  e herda a mesma duplicação.
- **Item novo passa a ter de onde nascer.** Achado ao produzir o Design Approval Package:
  `AMENDMENT_NEW_ITEM_INVALID` exige uma linha zerada preexistente, o que a planilha da
  prefeitura fornece e um consolidado vindo do orçamento assinado não tem. `AmendmentLine`
  ganha `description`, `unit` e `unit_price` **só quando `is_new_item`**, resolvidos no
  catálogo contratual e materializados no ato (ADR-0056, decisão 7).
- **Declaração na abertura da rodada**: campo opcional no `POST /v1/valuation-rounds`, espelho
  de `price_adjustment` (`main.py:4192-4212`), aplicado ao consolidado **antes** de ele ser
  gravado — é a imutabilidade na rodada que faz a declaração valer para o período inteiro.
- **Abertura da rodada `n+1`**: consolidado novo a partir da rodada anterior, com os períodos
  aprovados lançados (`PeriodProgress` com o `unit_price` daquele período, quando reajustado),
  o acumulado somado, as RE-RA e os reajustes preservados, e o saldo recomputado.
- **Tela**: declarar a RE-RA na abertura e ver, na memória, contratado → vigente com a RE-RA
  que produziu a diferença; e a jornada de abrir a medição seguinte a partir da anterior.

## Out of Scope

- **Workflow de aprovação da RE-RA** (protocolo, deferimento, negativa). Decisão 1 acima.
- **Tabela SQLAlchemy própria para RE-RA.** Continua JSON dentro de `contract_workbook_json`,
  pelo mesmo argumento do ADR-0055 decisão 1: não existe entidade "contrato" persistente a que
  pendurá-la.
- **RE-RA retroativa que reescreve período já lançado.** O ADR-0055 decisão 6 já decidiu que
  isso, se existir um dia, será acerto lançado como período próprio.
- **Base de preço de item novo trazido por RE-RA.** Já decidida — ADR-0055, decisão 9: nasce na
  base vigente na data da RE-RA e acompanha os reajustes seguintes, sem receber
  retroativamente os fatores de períodos em que não existia. Esta feature **implementa** a
  regra; não a redecide.
- **Importar RE-RA de planilha.** Já existe (`workbook_reader.py:789-866`) e não é tocado, além
  da adaptação ao vigente derivado.
- **Fórmula paramétrica / escopo por item no reajuste.** ADR-0055, decisão 10.

## Acceptance Criteria

1. `Amendment` recusa declaração sem autor, sem instante com fuso ou sem período de
   referência, com código de erro estável e mensagem em língua de obra.
2. `current_quantity(line)` devolve `contract_quantity + Σ deltas` das RE-RA que citam o
   código; sem RE-RA declarada, devolve `contract_quantity` **bit a bit**.
3. Consolidado gravado antes desta feature (`schema_version` `2.0.0` e `3.0.0`) continua
   validando, e responde com vigente igual ao `amended_quantity` que ele já trazia.
4. Item novo declarado sobre código ausente do consolidado cria a linha com `contract_quantity`
   zero, descrição, unidade e preço materializados do catálogo; código ausente **também** do
   catálogo recusa.
5. `amended_quantity` presente e divergente do derivado recusa com
   `AMENDMENT_APPLICATION_MISMATCH` — o comportamento de hoje, preservado.
6. Declarar RE-RA na abertura da rodada grava o consolidado já re-ratificado; a rodada
   permanece imutável depois disso.
7. Abrir a rodada `n+1` produz consolidado com `period_numbers` = os períodos anteriores,
   `periods` lançados com quantidade e valor de cada um, `accumulated_quantity` e
   `accumulated_amount` conferindo com a soma, e saldo `vigente − acumulado`.
8. Medir no período `n+1` acima do vigente **novo** recusa com `BALANCE_EXCEEDED`; abaixo,
   exporta.
9. Nenhum digest assinado se move: o `Estimate` assinado não ganha campo e o consolidado
   continua chegando a `Valuation.export_errors` por parâmetro.
10. Portões verdes: `make check` e `make test`.
11. Evidência renderizada da tela real: a classificação de validação é `BROWSER_REQUIRED`,
    conforme o `browser-runtime-validation` do EngineeringOS.

## Constraints

- **Compatibilidade de schema.** `ContractWorkbook.schema_version` sobe para `4.0.0` aceitando
  `2.0.0` e `3.0.0`, como já faz hoje. Consolidado gravado em rodada existente precisa
  continuar legível — há rodadas com consolidado em `contract_workbook_json`.
- **`Decimal` exato.** Quantidade é `ExactDecimal`; o truncamento de dinheiro é do fim da
  cadeia, nunca a cada passo (mesma disciplina do `current_unit_price`).
- **Não tocar a leitura do MAPÃO** além do necessário para o vigente derivado: ela é o
  caminho de obra que já vem medindo, e tem oráculo de teste próprio.
- **Uma tarefa, uma branch, uma worktree**, e a revisão linha a linha antes do commit.

## Dependencies

- **F-039 / ADR-0055** — dura, não opcional. `current_unit_price`, `ContractWorkbook.adjustments`,
  `PeriodProgress.unit_price` e o `schema_version` `3.0.0` são a base sobre a qual esta feature
  se apoia, e a decisão 9 do ADR já legisla sobre a interação entre RE-RA e reajuste. A branch
  `feat/f-040-re-ra-e-medicao-seguinte` parte de `feat/f-039-reajuste-entre-medicoes`, que
  **ainda não está na `main`**.
- **ADR-0048** — decisão 7 (consolidado imutável na rodada) e decisão 8 (da segunda medição em
  diante o consolidado soma os períodos já lançados). A decisão 8 é o que esta feature
  finalmente exerce.
- **ADR-0027** — a fronteira licitada, que põe o pedido do aditivo fora do sistema.

## Unknowns

- **Como a rodada `n+1` se liga à anterior**: ela cita a rodada de medição anterior, ou o
  mesmo orçamento assinado com o período incrementado? As duas formas sustentam o acumulado;
  a escolha decide o que acontece quando a rodada anterior é cancelada ou reaberta. Decisão do
  ADR desta feature.
- **Se a rodada `n+1` exige a anterior aprovada.** O acumulado só é confiável sobre períodos
  aprovados, mas exigir aprovação pode travar obra que mede em paralelo. Não inventar: levar
  ao gate.
- **Se o vigente derivado deve valer também para a leitura do MAPÃO histórico**, onde a
  planilha às vezes declara um vigente que não bate com os deltas — hoje isso é diagnóstico
  (`contract_diagnosis.py`), não recusa.

## Risks

- **Tornar derivado um campo persistido.** Rodadas existentes têm `amended_quantity` gravado.
  A migração é de leitura (campo vira opcional), mas um consolidado gravado com
  `amended_quantity` divergente dos deltas passaria a recusar onde antes recusava igual — é o
  mesmo erro, e por isso o risco é baixo, mas precisa de teste sobre dado gravado real.
- **Escopo duplo.** RE-RA e medição seguinte são dois mecanismos; o plano deve cortá-los em
  tarefas separadas com a rodada `n+1` primeiro, porque é ela que dá onde exercer a RE-RA.
- **`contract_diagnosis.py` recomputa as mesmas invariantes** por fora, para diagnosticar o
  MAPÃO histórico sem abortar na primeira violação. Mudar o vigente para derivado sem olhar
  esse caminho paralelo produziria dois veredictos sobre a mesma planilha.

## Human Gates

- **ADR** — `ARCHITECTURE_DECISION_REQUIRED`. O [ADR-0056](../../adr/0056-re-ra-declarada-e-o-consolidado-da-medicao-seguinte.md)
  precisa de aceite humano antes do planejamento: ele decide o vigente derivado e a forma da
  continuidade entre medições.
- **Design Approval** — `INTERFACE_CHANGE` exige Design Approval Package aprovado **antes** de
  planejar a superfície. O pacote está em [mock/README.md](mock/README.md), revisão 1,
  aguardando ato humano.
- **Merge e aceite** — merge da `main` e o aceite que fecha a issue #100 são atos humanos, e o
  merge da F-039 precede o desta feature.

## References

- [issue #100](https://github.com/biahflow/croquito/issues/100) — origem.
- [ADR-0055](../../adr/0055-reajuste-como-ato-declarado-sobre-o-consolidado.md) — reajuste como
  ato declarado; decisões 1, 3, 6 e 9 são pressupostos desta feature.
- [ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md) — decisões 7 e 8.
- [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md) — fronteira licitada e
  o dossiê do aditivo.
- [ADR-0018](../../adr/0018-valuation-consolidation-and-balance-semantics.md) — semântica de
  consolidação e saldo; é o ADR que declarou a RE-RA como leitura apenas.
- [F-039](../F-039-reajuste-entre-medicoes/feature.md) — o gêmeo em preço.
- [ROADMAP](../../product/ROADMAP.md), item 20.
