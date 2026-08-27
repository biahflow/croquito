# ADR-0056: A RE-RA é declaração, e a medição seguinte nasce da anterior

Status: Proposed  
Data: 2026-08-27  
Responsável: Product / Engineering

## Contexto

A [F-040](../features/F-040-re-ra-e-medicao-seguinte/feature.md) nasce da
[issue #100](https://github.com/biahflow/croquito/issues/100): criar e gerir re-ratificações,
que hoje o sistema apenas lê do MAPÃO para compor saldo.

A issue supunha uma feature grande — abrir, versionar, acompanhar aprovação. O mapeamento do
código mostrou outra coisa.

### O que já está decidido, e não se redecide aqui

O [ADR-0055](0055-reajuste-como-ato-declarado-sobre-o-consolidado.md), aceito em 2026-08-27,
resolveu por antecipação duas das três perguntas da issue:

- **decisão 1** — não existe entidade "contrato" persistente a que pendurar um ato contratual;
  o consolidado é gravado por rodada e imutável nela, e uma rodada é de um período, então
  declarar ali é exatamente dizer "a partir deste período";
- **decisão 6** — o passado é intocável: período já lançado mantém quantidade e valor, e
  medição aprovada não é recalculada nem quando a declaração vem depois;
- **decisão 9** — item novo trazido por RE-RA depois de um reajuste nasce na base **vigente na
  data da RE-RA** e acompanha os reajustes seguintes, sem receber retroativamente os fatores de
  períodos em que não existia.

Este ADR aplica essas decisões à quantidade e resolve o que sobrou.

### O que já existe

O **efeito** da RE-RA está inteiro: `validate_amendments` (`contract.py:456-525`) reconcilia
`amended_quantity` com `contract_quantity + Σ deltas` e recusa resultado negativo, código
ambíguo, item novo sobre linha não zerada e alvo inexistente. O saldo já deriva do vigente, e
`BALANCE_EXCEEDED` já barra medir acima dele.

### O que não existe, e é a descoberta que dimensiona a feature

`build_contract_from_estimate` serve **só a primeira medição**. A docstring diz que somar os
períodos já aprovados "é trabalho de quem a construir — esta função não ganha parâmetro que
nenhum chamador usa hoje" (`contract_from_estimate.py:88-91`), e não há chamador. Na `/v1`,
`contract_workbook_json` é gravado por um único caminho, a abertura a partir do orçamento
assinado.

A decisão 8 do [ADR-0048](0048-consolidado-contratual-do-orcamento-assinado.md) — da segunda
medição em diante o consolidado soma os períodos já lançados — está escrita e **nunca foi
exercida**. Re-ratificação é o que acontece entre medições; sem a medição seguinte, a RE-RA
seria declarável apenas onde ainda não há o que re-ratificar.

### As três decisões de domínio que precederam este ADR

Tomadas por ato humano em 2026-08-27, na abertura da feature:

1. O sistema registra a RE-RA **aprovada**, não o pedido com estado.
2. O vigente passa a ser **derivado**, como o preço.
3. A abertura da **medição seguinte** entra no escopo.

## Decisão

1. **A RE-RA é declaração com procedência, gravada com o consolidado da rodada.** `Amendment`
   ganha `declared_by`, `declared_at` (com fuso), `reference_period` e `note` opcional —
   simétrico a `PriceAdjustment`, e pelo mesmo motivo: fator sem índice não é conferível, e
   RE-RA sem citação da publicação também não. `label` continua, como nome curto que a tela
   mostra.

   Enquanto a RE-RA só era lida do MAPÃO, a procedência era implícita e bastava: veio da
   planilha que a prefeitura assinou. No dia em que ela nasce aqui dentro, a ausência vira
   lacuna de auditoria.

2. **Não há ciclo de vida do pedido no sistema.** Não existe `pendente → aprovado → negado`. O
   pedido já tem artefato — o dossiê do aditivo —, e
   [ADR-0027](0027-price-source-provenance-and-bid-boundary.md) põe a solicitação à prefeitura
   fora do sistema, o que `amendment_dossier.py` repete nas próprias notas de segurança. Modelar
   aqui um estado que se decide lá produziria um registro que envelhece sem ninguém notar: o
   sistema diria "pendente" meses depois de deferido.

3. **O vigente é DERIVADO, nunca gravado.** `ContractWorkbook.current_quantity(line)` vira a
   fonte, espelhando `current_unit_price` e a decisão 3 do ADR-0055. `amended_quantity` passa a
   **opcional**, e sobrevive com outro papel: quando presente, é **asserção externa a
   conferir** — o número que a planilha da prefeitura declarou —, e quem recusa a divergência
   continua sendo `AMENDMENT_APPLICATION_MISMATCH`.

   Essa distinção é o ponto: o mesmo campo era oráculo enquanto vinha de fora e vira duplicata
   quando passa a nascer aqui. Manter os dois papéis num campo obrigatório faria o sistema
   conferir a si mesmo, o que é sempre verdade e não protege nada.

   `balance_quantity` recebe o mesmo tratamento, porque saldo é `vigente − acumulado` e herda a
   mesma duplicação.

4. **A medição seguinte nasce da rodada anterior, e cita a rodada, não o orçamento.** O
   consolidado de `n+1` é construído a partir do consolidado de `n` mais os períodos aprovados
   nele. Citar a rodada anterior — e não o orçamento assinado com o período incrementado — é o
   que preserva a cadeia: o orçamento não conhece reajuste nem RE-RA, e reconstruir a partir
   dele exigiria reaplicar toda a história declarada desde então, com o risco de reaplicá-la
   diferente.

5. **A rodada seguinte exige a anterior aprovada.** O acumulado é a base do saldo, e saldo
   apurado sobre período não aprovado afirma como medido o que ainda pode mudar. Obra que
   precise adiantar o período seguinte tem o caminho de aprovar o anterior — que é um ato que
   já existe (`POST /v1/valuation-rounds/{id}/approve`) — e não o de medir sobre número
   provisório.

6. **RE-RA e reajuste compõem na ordem declarada, e a quantidade não conhece o preço.** Os dois
   atos vivem no mesmo consolidado e não interagem, exceto no caso que o ADR-0055 decisão 9 já
   legislou: item novo nasce na base vigente na data da RE-RA. Quantidade vigente não depende de
   preço, e preço vigente não depende de quantidade — mantê-los independentes evita que um erro
   de fator contamine saldo de quantitativo.

7. **`ContractWorkbook.schema_version` sobe para `4.0.0`, aceitando `2.0.0` e `3.0.0`.** Mesma
   disciplina das duas vezes anteriores. Consolidado gravado antes desta decisão continua
   validando: ele traz `amended_quantity` preenchido e nenhuma RE-RA com procedência, o que é a
   verdade sobre ele — e o vigente derivado devolve exatamente o número que já estava lá.

8. **Nenhum digest assinado se move.** O consolidado não está embutido na medição
   (`export_errors` o recebe por parâmetro) e o `Estimate` assinado não ganha campo — o mesmo
   argumento da decisão 8 do ADR-0055, que continua valendo pela mesma razão estrutural.

## Alternativas

- **Máquina de estados do pedido** — rejeitada pela decisão 2. O ato se decide fora do sistema;
  o estado registrado aqui envelheceria sem sinal.
- **Tabela própria para RE-RA** — rejeitada. Sem entidade "contrato" persistente, a tabela
  precisaria inventar a chave a que se pendurar, e o consolidado por rodada já é o lugar onde o
  ato vale.
- **Manter `amended_quantity` obrigatório e gravado** — rejeitada pela decisão 3. Enquanto a
  RE-RA nascer no sistema, o campo confere o sistema contra ele mesmo.
- **Reconstruir a medição seguinte do orçamento assinado** — rejeitada pela decisão 4:
  exigiria reaplicar toda a história de reajuste e RE-RA a cada rodada, e duas reaplicações
  precisariam concordar para sempre.
- **Permitir rodada seguinte sobre período não aprovado** — rejeitada pela decisão 5: apura
  saldo sobre número que ainda pode mudar.
- **Um `ContractWorkbook` novo por RE-RA** — rejeitada pelo mesmo motivo que o ADR-0055 rejeitou
  para reajuste: duplicaria o histórico de períodos junto, criando duas verdades sobre o mesmo
  acumulado.

## Consequências

### Positivas

- A RE-RA passa a ser conferível: quem declarou, quando, e contra qual publicação.
- A cadeia de medição deixa de saber medir uma vez só; a decisão 8 do ADR-0048 finalmente é
  exercida, e o reajuste da F-039 ganha onde compor.
- Vigente e saldo passam a ter um dono só, e o campo da planilha vira conferência explícita em
  vez de segunda fonte silenciosa.
- Sem RE-RA declarada, todo caminho existente responde bit a bit como hoje.

### Negativas

- **`ContractWorkbook` muda de schema pela segunda vez em dois dias.** É aditivo e compatível,
  mas é contrato publicado, e todo construtor passa a lidar com a versão nova.
- **Vigente derivado custa uma travessia** da lista de RE-RA por linha, como o preço. É barato,
  e um campo gravado seria mais rápido e mentiria eventualmente.
- **A exigência de rodada anterior aprovada pode travar obra** que hoje mediria em paralelo —
  consequência assumida da decisão 5, e o caminho de destravar é aprovar, não contornar.
- **`contract_diagnosis.py` recomputa as mesmas invariantes por fora**, para diagnosticar o
  MAPÃO histórico sem abortar na primeira violação; ele precisa acompanhar o vigente derivado,
  sob pena de dois veredictos sobre a mesma planilha.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Consolidado gravado deixar de validar | Decisão 7: `2.0.0` e `3.0.0` aceitos, e teste sobre dado gravado real |
| Vigente divergir da declaração | Decisão 3: derivado, nunca gravado |
| RE-RA sem procedência entrar pela API | Decisão 1: autor, instante e citação obrigatórios no modelo, não na fronteira |
| Saldo apurado sobre período provisório | Decisão 5: rodada seguinte exige a anterior aprovada |
| História reaplicada diferente a cada rodada | Decisão 4: a rodada seguinte cita a anterior, não o orçamento |
| Item novo receber fator de ano em que não existia | ADR-0055, decisão 9, implementada aqui |
| Registro de pedido envelhecer sem sinal | Decisão 2: o pedido continua sendo o dossiê, fora do sistema |

## Rastreabilidade

- Feature: [F-040](../features/F-040-re-ra-e-medicao-seguinte/feature.md)
- Issue: [#100](https://github.com/biahflow/croquito/issues/100)
- Relacionados: [ADR-0055](0055-reajuste-como-ato-declarado-sobre-o-consolidado.md),
  [ADR-0048](0048-consolidado-contratual-do-orcamento-assinado.md),
  [ADR-0027](0027-price-source-provenance-and-bid-boundary.md),
  [ADR-0018](0018-valuation-consolidation-and-balance-semantics.md)
- Supersedes: none
- Superseded by: none
