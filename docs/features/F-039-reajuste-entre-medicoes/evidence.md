# F-039 — Evidência

Feature: [Reajuste de preços entre medições](feature.md)  
Estado: `DONE` — revisão `REVIEW_PASS` e aceite por ato humano em 2026-09-05  
Data: 2026-08-27 · aceite em 2026-09-05

## Gates humanos

| Gate | Estado |
| --- | --- |
| `ARCHITECTURE_DECISION_REQUIRED` | ✅ [ADR-0055](../../adr/0055-reajuste-como-ato-declarado-sobre-o-consolidado.md) **aceito por ato humano em 2026-08-27**, e **emendado na execução** (decisão 6) |
| `DESIGN_APPROVAL_REQUIRED` | ✅ **Aprovado por ato humano em 2026-08-27**, revisão 1 ([mock/README.md](mock/README.md)) |

Antes dos dois gates, três **decisões de domínio** foram tomadas por ato humano na abertura da
feature: duas formas de reajuste declaradas por rodada, fator digitado com o campo preparado
para a tabela de índices futura, e um fator para o contrato inteiro.

## O que foi entregue

| Arquivo | O que é |
| --- | --- |
| `packages/valuation/.../contract.py` | `PriceAdjustment` discriminado por `kind`; `ContractWorkbook.adjustments` e `current_unit_price` derivado; `PeriodProgress.unit_price`; a cobertura por código da versão nova |
| `packages/valuation/.../models.py` | `LINE_PRICE_NOT_IN_CONTRACT` passa a comparar com o preço vigente |
| `tests/valuation/test_price_adjustment.py` | 13 testes: composição, substituição, passado intocável, recusas e o consolidado `2.0.0` |
| `services/api/.../main.py` | `PriceAdjustmentRequest`, a resolução da declaração (inclusive a leitura do catálogo novo) e a aplicação ao consolidado **antes** de gravá-lo |
| `services/api/.../valuation_rounds.py` | `price_adjustments` e `prices` na leitura da rodada |
| `tests/api/test_valuation_round_from_estimate.py` | 5 testes de rota, incluindo o controle sem reajuste |
| `apps/web/src/medicao/reajuste.ts` (+ testes) | A recusa antes da rede e as três opções da abertura |
| `apps/web/src/medicao/MedicaoApp.tsx` | A declaração na abertura e o `ReajusteDeclarado` na leitura da rodada |

## Critérios de aceite

| # | Critério | Como foi verificado |
| --- | --- | --- |
| 1 | `make check` e `make test` verdes; goldens intocados | `make check` = 0, `make test` = 0 (2564 pytest, 1250 vitest web, 261 field) |
| 2 | Rodada sem reajuste se comporta como hoje | `test_sem_reajuste_o_vigente_e_o_contratado_bit_a_bit` e `test_rodada_sem_reajuste_declara_ausencia_em_vez_de_omitir`; a suíte inteira passou sem mudar expectativa de comportamento |
| 3 | Vigente = contratado × fator, truncado | `test_fator_de_indice_produz_o_vigente_com_dinheiro_truncado` — 62,40 × 1,0432 = 65,09, não 65,10 |
| 4 | Versão nova reprecifica e recusa código ausente | `test_versao_nova_da_tabela_substitui_o_preco` e `test_versao_nova_precisa_precificar_todo_codigo_contratado` (`PRICE_ADJUSTMENT_CODE_MISSING`) |
| 5 | O portão compara com o vigente | A comparação em `Valuation.export_errors`; sem reajuste, idêntica à anterior |
| 6 | Período mantém quantidade e valor; acumulado soma bases | `test_o_passado_nao_se_move_com_o_reajuste` — 4.992,00 + 7.810,80 = 12.802,80 |
| 7 | Declaração com autor, instante, índice, período e fator, imutável na rodada | Identidade e relógio vêm do `Principal` e do servidor; a declaração entra **antes** de o consolidado ser gravado, e ele é imutável desde então |
| 8 | A memória mostra contratado, fator e vigente | Ver o **desvio** abaixo: o fator ficou na linha da declaração, não como coluna |
| 9 | Fator ausente, ≤ 0 ou sem índice/período recusa | 4 testes na tela (antes da rede) e 2 de rota |
| 10 | A tela corresponde à revisão aprovada | Comparação entre [`mock/04-memoria-com-a-conta.png`](mock/04-memoria-com-a-conta.png) e a captura do componente real, abaixo |

## Validação de navegador/runtime

Classificação: **`BROWSER_REQUIRED`**.

Evidência do **componente real** com as **folhas reais**, renderizado e capturado em Chromium:

| Captura | Estado |
| --- | --- |
| [`tela-reajustada.png`](evidencia/tela-reajustada.png) | Declaração carimbada e a tabela contratado × vigente |
| [`tela-sem-reajuste.png`](evidencia/tela-sem-reajuste.png) | O controle: sem declaração, a tela não fala de reajuste |

Os números batem com os do pacote aprovado: 62,40 → 65,09 e 118,00 → 123,09.

## Desvios declarados

1. **A emenda do ADR, descoberta na execução.** A decisão 6 dizia que `PeriodProgress` já
   bastava para o passado ser intocável. Não bastava: `ContractLine.validate_periods` exige que
   **cada** período bata com `quantidade × unit_price` da linha, e a linha tem **um** preço — o
   modelo não conseguia representar um contrato reajustado. `PeriodProgress` ganhou
   `unit_price` opcional (ausente = medido pelo contratado), e o ADR foi emendado. Sem isso a
   feature era irrepresentável, não apenas incompleta.
2. **O fator não virou coluna da tabela.** A decisão 5 do pacote de design pede três colunas:
   contratado, fator, vigente. A implementação mostra contratado e vigente na tabela, e o fator
   na **linha da declaração**, logo acima. A razão: o fator é um só para o contrato inteiro, e
   repeti-lo em todas as linhas seria ruído; com dois reajustes compostos, não existe um único
   fator por linha a imprimir. **É desvio de decisão aprovada**, e fica registrado como tal —
   se a coluna for desejada, ela é mudança pequena e o pacote vira revisão 2.
3. **O layout impresso do MAPÃO não foi tocado**, como o pacote de design já excluía.

## Riscos remanescentes

- O fator continua **digitado**: erro de digitação contamina a medição inteira, e o sistema não
  tem como validar o valor. A mitigação implementada é exigir índice e período junto dele.
- Nenhuma medição real com contrato reajustado foi feita: o primeiro uso é o teste de verdade.
- Reajuste **retroativo** não é atendido, por decisão declarada no ADR.

## Decisões humanas pendentes

Todas exercidas:

- ~~Revisão do PR e merge~~ — o merge é o [PR #107](https://github.com/biahflow/croquito/pull/107)
  (ato humano); a rodada de revisão correu em **2026-09-05**, linha a linha sobre o núcleo
  já integrado na `main`, e terminou **`REVIEW_PASS`** sem achado de código.
- ~~Decidir se o fator vira coluna da tabela (desvio 2)~~ — **decidido em 2026-09-05**
  (Daniel Campos): o fator **fica na linha da declaração**; o desvio é aceito como melhoria,
  porque o fator é um só para o contrato inteiro e a composição não tem fator único por
  linha.
- ~~Aceite~~ — **aceita por ato humano em 2026-09-05**, com a dívida declarada de que
  nenhuma medição real com contrato reajustado atravessou: o aceite é sobre o mecanismo, e
  o primeiro uso real é o teste de verdade.
