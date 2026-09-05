# Design Approval Package — F-049, dashboard executivo do contrato

Classification: INTERFACE_CHANGE
Revision: 1
Status: **Approved — revisão 1 (2026-09-05)**
Date: 2026-09-05
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**

## O gate que vem antes deste

A F-049 **não introduz semântica nova**. O consolidado contratual
(`packages/valuation/src/croquito_valuation/contract.py`) já valida e recomputa, na leitura:
consolidação e saldo (**ADR-0018**, `Accepted`), reajuste declarado (**ADR-0055**, F-039,
`Accepted`) e RE-RA declarada (**ADR-0056**, F-040, `Accepted`). Este pacote decide a **forma**
de mostrar o que esses três ADRs já governam. Se um deles mudar, o pacote muda com ele.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | a composição dos seis estados e as seis decisões abaixo |
| Aprovado por | Daniel Campos |
| Data | 2026-09-05 |
| Revisão | 1 |

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`dashboard-do-contrato.html`](dashboard-do-contrato.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os seis estados numa imagem |
| [`01.png`](01.png) | Contrato sem medição lançada: só contratado e vigente, ditos por extenso |
| [`02.png`](02.png) | A visão principal: cabeçalho de quatro números e a lista por item ordenada por risco de teto |
| [`03.png`](03.png) | A série por período de um item, com o preço vigente em cada um |
| [`04.png`](04.png) | Com reajuste declarado: as duas curvas (física e financeira) divergindo, e o carimbo do reajuste |
| [`05.png`](05.png) | Com RE-RA declarada: contratado e vigente lado a lado, com a citação |
| [`06.png`](06.png) | Consolidado que não fecha: a recusa nomeada, não um número aproximado |

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Dashboard do contrato | sem nenhuma medição lançada | sim (01) |
| Dashboard do contrato | visão principal, com histórico e itens ordenados por saldo | sim (02) |
| Item do dashboard | série por período, sem reajuste | sim (03) |
| Item do dashboard | série por período, com reajuste no meio da série | sim (04) |
| Item do dashboard | com RE-RA declarada sobre a quantidade contratada | sim (05) |
| Dashboard do contrato | consolidado que recusa (`CONTRACT_ACCUMULATED_MISMATCH`) | sim (06) |
| Dashboard do contrato | carregando | **não** — leitura sem mutação, sem chamada paga; a demora esperada é a de qualquer rota de leitura, sem estado próprio |
| Dashboard do contrato | com mais de um `group_label` (praça) sob o mesmo contrato, em estágios diferentes | **não** — ver questão aberta (Unknown 2 da feature) |

## Proveniência dos valores visuais

| Valor | Origem | Novo? |
| --- | --- | --- |
| Tokens de superfície, tinta, linha e o verde de marca | `apps/web/src/styles.css` | não |
| `--atencao`, `--atencao-line`, `--atencao-soft` | `apps/web/src/medicao/styles.css` (`.aviso-atencao`) | não |
| `--recusa` (`#a33d32`) e o trio do banner de recusa (`#7d2f26`/`#fbeeec`/`#e0b4ad`) | `apps/web/src/styles.css` (borda de issue crítica; `.app-alert`/`.login-alert`) | não |
| Roxo do reajuste (`--reajuste*`) | `apps/web/src/medicao/styles.css`, `.reajuste-do-contrato`/`.selo-reajuste` (F-039) — o mesmo roxo que já significa "reajustado" na medição | não |
| Petróleo da RE-RA (`--rera*`) | `apps/web/src/medicao/styles.css`, `.selo-rera` (F-040) — o mesmo petróleo que já significa "re-ratificada" | não |
| **Cor nova** | — | **nenhuma** |

Nenhuma cor nova é introduzida por este pacote. O estado 4 (reajuste) e o estado 5 (RE-RA)
reutilizam propositalmente as cores de domínio que **já** significam essas duas coisas em
`apps/web/src/medicao/styles.css` — inventar uma paleta própria para o dashboard criaria um
segundo vocabulário para o que a tela de medição já nomeou.

### Proveniência dos números (contrato sintético)

Todo número que aparece nas capturas existe em `contract.py` ou deriva dele por operação
declarada; nenhum é digitado à mão sem lastro no modelo. O contrato de demonstração ("Contrato
de execução 014/2025 — Praça Vista Alegre", cinco itens: escavação, playground, piso
intertravado, grama e drenagem) é inteiramente sintético.

| Número na tela | Campo/derivação de `contract.py` |
| --- | --- |
| Contratado (R$) | Σ `ContractLine.contract_quantity × ContractLine.unit_price`, truncado por linha e somado — mesma operação que `validate_periods` já aplica a quantidade×preço |
| Vigente (R$) | Σ `ContractWorkbook.current_quantity(line) × ContractWorkbook.current_unit_price(line)`, truncado por linha e somado |
| Medido acumulado (R$) | Σ `ContractLine.accumulated_amount` — campo já validado por `validate_accumulated` |
| Saldo (R$) | Σ `ContractWorkbook.current_balance_quantity(line) × ContractWorkbook.current_unit_price(line)`, truncado por linha e somado |
| Saldo por item, quantidade e % restante | `ContractWorkbook.current_balance_quantity(line)` ÷ `ContractWorkbook.current_quantity(line)` |
| Próxima medição (1ª/4ª) | `ContractWorkbook.next_period_number` |
| Série por período (estados 3 e 4) | `ContractLine.periods` (`PeriodProgress.quantity`/`.amount`/`.unit_price`) |
| "Preço vigente (contratado)" quando `unit_price` do período está ausente | Leitura literal do docstring de `PeriodProgress.unit_price`: ausente significa medido pelo preço contratado |
| Carimbo do reajuste (estado 4) | `PriceAdjustment` (`kind="index_factor"`, `index_label`, `factor`, `reference_period`, `declared_by`, `declared_at`) |
| Curva física vs. financeira (estado 4) | quantidade acumulada ÷ `current_quantity`, e dinheiro acumulado ÷ (quantidade contratada × preço contratado) — nunca um percentual só |
| Contratado/vigente/delta da RE-RA (estado 5) | `AmendmentLine.quantity_delta` sobre `ContractLine.contract_quantity`, e `Amendment.label`/`.note`/`.reference_period`/`.declared_by` para a citação |
| Painel de recusa (estado 6) | `ValuationValidationError` literal levantada por `ContractLine.validate_accumulated` — `code`, `message` e `details` (`item_number`, `code`, `field`, `expected`, `declared`) copiados do texto-fonte |

## Decisões que este pacote carrega

1. **O corte é do gestor do contrato: saldo por item primeiro, totais depois.** O cabeçalho
   com os quatro números vem ANTES da lista por item na ordem de leitura da página, mas dentro
   da lista o que manda é o item com menor saldo relativo ao contratado — é onde a obra vai
   bater no teto. A tela do diretor seria o inverso (totais primeiro, sem descer ao item), e
   por isso não é esta.

2. **Nada é gravado.** Os quatro números do cabeçalho, o saldo por item e as duas curvas do
   estado 4 são todos derivados do consolidado na leitura — nenhum tem campo próprio, pela
   mesma disciplina de `current_unit_price` (ADR-0055, decisão 3): um segundo lugar dizendo a
   mesma coisa é onde a discordância mora, e aqui a discordância é dinheiro.

3. **Físico e financeiro nunca se fundem num número só.** O estado 4 mostra duas barras
   distintas — quantidade acumulada e dinheiro acumulado — com os dois percentuais escritos
   ao lado. Um "percentual de avanço" único escolheria uma das duas leituras em silêncio, e a
   diferença entre elas (75,0% físico contra 76,6% financeiro no exemplo) é exatamente o
   efeito que a F-039 tornou visível.

4. **Cada número aponta a medição que o produziu.** O item mais crítico da lista (estado 2)
   linka para a série por período (estado 3); toda linha de período mostra o número da
   medição; o carimbo do reajuste e a citação da RE-RA trazem quem declarou, quando e sob qual
   ato administrativo. Um dashboard que não deixa descer ao documento vira planilha paralela.

5. **Sem cronograma, projeção ou percentual de tempo.** Nenhuma data de planejamento, linha
   do tempo ou "% do prazo decorrido" aparece em nenhum estado. A medição do croquito é
   físico-financeira e não tem linha de base de tempo; projetar seria inventar dado que
   ninguém declarou.

6. **A recusa é estado de primeira classe.** O estado 6 usa o mesmo vermelho do banner de erro
   já em uso no app (`.app-alert`/`.login-alert`) e reproduz literalmente `code`, `message` e
   `details` do erro de domínio — inclusive o formato cru dos números (ponto decimal). Nenhum
   outro número daquele item aparece enquanto a linha não fechar: não há saldo aproximado nem
   "quase certo" para preencher o lugar.

## Questões abertas

- **A copy final** de todos os textos, inclusive as mensagens de recusa e as notas de
  implementador.
- **Os números das capturas são sintéticos** ("Praça Vista Alegre", contrato 014/2025 e todos
  os códigos/valores) e não correspondem a nenhum contrato real.
- **Se o dashboard é por contrato ou por obra/praça** — Unknown 2 do [Feature Contract](../feature.md), ainda **não
  resolvido**: um contrato licitado pode cobrir várias praças (`ContractLine.group_label`
  distingue grupos dentro do mesmo consolidado), e este pacote não decide o que fazer quando
  as praças de um contrato estão em estágios diferentes. O mock renderiza um único
  `ContractWorkbook` com cinco itens em grupos distintos (Terraplenagem, Playground,
  Pavimentação, Paisagismo, Drenagem) como ilustração de UM contrato — não resolve se a tela
  deveria filtrar/agrupar por praça quando o consolidado tiver mais de uma.
- **O limiar que viraria a barra de saldo em alerta âmbar** (ou se deve virar) não está
  definido por produto. A ordenação por saldo relativo já resolve a pergunta do gestor ("o que
  olho primeiro?") sem precisar de um limiar de cor — mas se um dia um limiar for desejado
  (ex.: destacar itens abaixo de 10% de saldo), é decisão de produto nova, não implícita neste
  pacote.
- **O que acontece quando o mesmo código aparece em mais de um grupo** (`CODE_AMBIGUOUS_IN_CONTRACT`)
  na leitura do dashboard — o pacote não desenha esse caso; a rota de leitura precisará decidir
  se agrega por grupo+código ou recusa a visão consolidada.

## Notas para quem implementar

- **Intencional e a preservar**: a ordem de leitura (saldo por item antes de totais dentro da
  lista, mas totais no topo da página); as duas barras nunca combinadas em uma; o link do item
  mais crítico para a série por período; o carimbo do reajuste fora da tabela; o painel de
  recusa reproduzindo os campos literais do erro de domínio.
- **Ilustrativo, e não é especificação**: nome do contrato, códigos, descrições, grupos,
  valores, datas e nomes de quem declarou reajuste/RE-RA.
- **O que o artefato não mostra**: paginação/filtro para contrato com muitos itens, ordem de
  foco, comportamento de teclado, leitura por leitor de tela, o texto de erro vindo da API tal
  como o backend o serializaria em `application/problem+json`, e o estado de carregamento da
  rota `GET`.
- A rota de leitura não muda nenhum estado e não dispara chamada paga (Acceptance Criteria 4
  da feature); nenhuma ação de escrita aparece em nenhum dos seis estados — é dashboard de
  leitura, sem botão de exportar, editar ou aprovar.
