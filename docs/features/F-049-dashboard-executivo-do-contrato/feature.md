# F-049 — Dashboard executivo do contrato: planejado, realizado e saldo

## Status

`READY_FOR_PLANNING`

> **Unknown 1 respondido e prioridade definida por ato humano em 2026-09-05** (Daniel
> Campos): a tela é do **gestor do contrato na empresa executora** — quem usa o croquito
> todo dia e responde pelo contrato —, e a prioridade é `MEDIUM`. O corte que isso fixa:
> saldo por item, o que dá para medir no próximo período, e onde o acumulado se aproxima do
> contratado. **Não** é a tela do diretor (totais de reunião) nem a do fiscal (que exigiria
> jornada e autorização externas, e vira feature própria se um dia for pedida). Com a
> pergunta respondida, o único gate restante antes do planejamento é o Design Approval
> Package.

> Registrada como candidata em 2026-09-03, da análise de posicionamento da Orvia, e
> **especificada em 2026-09-05** por seleção humana. Continua `READY_FOR_SPEC` — e não
> `READY_FOR_PLANNING` como a [F-048](../F-048-auditoria-de-medicao-de-terceiros/feature.md)
> — por um motivo declarado: a especificação achou uma **pergunta de produto que precede o
> desenho** (unknown 1), e planejar antes dela produziria a tela errada.

## Classification

`INTERFACE_CHANGE` — jornada de leitura nova, sem domínio novo. Exige Design Approval
Package antes do planejamento.

## Priority

`MEDIUM` — **definida por ato humano em 2026-09-05**, abaixo da F-048: esta feature
**apresenta** o que já existe, enquanto a F-048 **acha erro de dinheiro** — e o que se vende
é o segundo.

## Problem

### O dado existe inteiro, e ninguém o vê junto

O consolidado contratual (`croquito_valuation.contract`, via
[F-036](../F-036-vinculo-orcamento-medicao/feature.md)) já guarda, com validação fechada e
recomputação na leitura:

- **contratado** (`unit_price`, `contract_quantity`) e o **vigente** derivado, depois de
  RE-RA ([F-040](../F-040-re-ra-e-medicao-seguinte/feature.md)) e de reajuste
  ([F-039](../F-039-reajuste-entre-medicoes/feature.md));
- **acumulado** por linha (`accumulated_quantity`, `accumulated_amount`), recomputado a
  partir dos períodos e recusado quando não bate (`CONTRACT_ACCUMULATED_MISMATCH`);
- **saldo vigente** (`current_balance_quantity`);
- **o histórico por período** (`PeriodProgress`), com o preço daquele período — que é
  exatamente o que permite comparar medições entre si depois de um reajuste.

E a [F-031](../F-031-value-events/feature.md) publica `GET /v1/metrics/summary` com custo de
IA, ciclo e taxa de correção por tenant e por período.

### O que falta

Nada disso é lido junto. Quem quer saber "quanto da obra já foi medido, quanto sobra e como
o avanço se comportou entre as medições" tem: o boletim de um período por vez, um `.xlsx`
por rodada, e nenhuma visão de contrato. A resposta existe no banco e sai à mão, em planilha
paralela — que é o mesmo padrão que a F-039 existe para não deixar acontecer com o preço.

## Desired Outcome

Uma tela por contrato que responde, sem exportar nada: quanto foi contratado, quanto vigora
hoje, quanto já foi medido, quanto sobra, e como isso andou entre os períodos — com cada
número apontando para a medição que o produziu.

## Scope

1. **Agregado por contrato**, derivado do consolidado — nunca gravado como campo novo
   (mesma disciplina do `current_unit_price`, ADR-0055 D3: um segundo lugar dizendo a mesma
   coisa é onde a discordância mora).
2. **Série por período**: medido e acumulado por medição lançada, com o preço vigente de
   cada uma — a comparação honesta depois de reajuste.
3. **Rota `/v1` de leitura**, sem mutação e sem chamada paga.
4. **Tela**, com cada número rastreável até a rodada que o originou.
5. **Avanço físico × financeiro** lado a lado: quantidade acumulada e dinheiro acumulado
   têm curvas diferentes quando há reajuste, e mostrá-los como um número só esconde
   exatamente o efeito que a F-039 tornou visível.

## Out of Scope

- **Cronograma, linha de base de tempo, SPI e caminho crítico.** A medição do croquito é
  físico-financeira e **não tem noção de tempo planejado** — inventar uma seria criar dado
  que ninguém declarou. Registrado como fora de escopo desde o nascimento da candidata.
- Previsão/projeção de término. Sem linha de base de tempo, projeção é chute com aparência
  de número.
- Consolidar contratos de tenants diferentes na mesma visão.

## Acceptance Criteria

1. Para um contrato com N medições lançadas, o acumulado da tela é **idêntico** ao
   recomputado pelo domínio — e um consolidado que não fecha continua recusando, não vira
   número aproximado na tela.
2. Contrato com reajuste mostra as duas curvas (quantidade e dinheiro) distintas, com o
   preço de cada período visível.
3. Contrato com RE-RA mostra contratado e vigente lado a lado, sem sobrescrever o original.
4. A rota não muda nenhum estado e não dispara nenhuma chamada paga, provado por teste.
5. Nenhum número da tela é gravado: todos derivam do consolidado na leitura.

## Unknowns

1. ~~**Para quem é esta tela.**~~ **Respondido em 2026-09-05**: o **gestor do contrato na
   empresa executora**. O dono da obra e o fiscal da prefeitura ficam de fora — o primeiro
   por querer totais de reunião sobre os mesmos dados (corte próprio, não esta tela), o
   segundo por exigir acesso externo, que é jornada e autorização novas.
2. **Se a visão é por contrato ou por obra.** Um contrato licitado cobre várias praças; o
   croquito organiza por praça. Agregar por contrato é o que o executivo pede, e exige
   decidir o que fazer quando as praças de um contrato estão em estágios diferentes.

## Human Gates

1. ~~**Seleção, prioridade e a resposta do unknown 1**~~ — **cumprido em 2026-09-05**
   (Daniel Campos): `MEDIUM`, e a tela é do gestor do contrato na executora.
2. **Design Approval Package** — único gate restante antes do planejamento.

## References

- `packages/valuation/src/croquito_valuation/contract.py` — `ContractLine`,
  `PeriodProgress`, `current_unit_price`, `current_quantity`, `current_balance_quantity` e
  os validadores de acumulado.
- `services/api/src/croquito_api/main.py` — `GET /v1/metrics/summary`
  (`MetricsSummaryResponse`), da F-031.
- [Roadmap](../../product/ROADMAP.md), registro de nascimento das três candidatas.
