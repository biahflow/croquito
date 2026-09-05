# F-048 — Auditoria de medição de terceiros: o furo que ninguém procurou

## Status

`READY_FOR_PLANNING`

> Registrada como candidata em 2026-09-03, da análise de posicionamento da Orvia
> (controladoria independente de obra), e **especificada em 2026-09-05** por seleção humana,
> na rodada em que o roadmap de execução zerou.
>
> A escolha dela como primeira das três candidatas tem uma razão medida: **o motor já
> existe e já achou dinheiro errado num arquivo real de cliente**. Em 2026-08-12, a
> conferência de paridade sobre o MAPÃO da obra encontrou **oito erros de um centavo** —
> não hipóteses: linhas em que a fórmula da planilha e o valor em cache discordavam. O que
> falta não é capacidade de achar; é a jornada que deixa alguém de fora trazer o arquivo.

## Classification

`INTERFACE_CHANGE` — cria jornada nova: importar uma medição alheia e ler o relatório de
furos. Exige Design Approval Package antes do planejamento.

## Priority

`HIGH` — **definida por ato humano em 2026-09-05** (Daniel Campos), por três razões
independentes: é a única das três candidatas cujo núcleo está pronto e provado contra
documento real; é a que casa com a estratégia comercial registrada (vender para empresas
de engenharia, não para a prefeitura); e é a que produz valor **sem depender de o cliente
adotar o croquito** — ele traz a planilha que já tem.

## Problem

### O que existe hoje

Dois motores completos, os dois **só como CLI local**:

- **`valuation-parity`** (`make valuation-parity PREVIOUS=<arquivo.xlsx>`): relê a planilha
  do cliente e confere a **fórmula da gramática fechada contra o valor em cache** de cada
  célula. É o que achou os oito erros de centavo.
- **`compare_bulletin`** (`packages/valuation/src/croquito_valuation/bulletin_compare.py`):
  compara boletim gerado contra boletim real **centavo a centavo, sem tolerância**, e
  classifica cada divergência — código ausente de um lado, diferença de quantidade, de
  preço unitário, de total de linha e de total da obra —, com `zero_cent` como veredito
  único.
- De quebra, `diagnose_contract` (`contract_diagnosis.py`) já produz o dossiê de achados
  do consolidado, com as classes que a leitura do MAPÃO real expôs (838
  `BALANCE_MISMATCH`, 548 `BALANCE_NEGATIVE` etc.).

### O que não existe

Rota `/v1` e tela. Hoje, auditar a medição de um terceiro exige um engenheiro com o
repositório clonado, o arquivo no disco e uma linha de comando. Isso não é produto: é
consultoria com o nosso código dentro.

### Por que isso é um produto, e não uma ferramenta interna

A empresa que executa a obra recebe medições de subcontratados; a que contrata recebe do
executor. Em ambos os lados, conferir centavo a centavo é trabalho manual caro que ninguém
faz por inteiro — se faz por amostragem. O croquito já sabe fazer por inteiro, e o
resultado é uma frase curta ("zero centavo" ou "N furos, aqui estão") que se entende sem
saber nada do sistema.

## Desired Outcome

Alguém de fora da obra sobe uma medição — MAPÃO, boletim ou os dois — e recebe o relatório
de furos: o que não fecha, de que classe, em qual linha e por quanto. Sem precisar ter
projeto, prancha ou rodada no croquito.

## Scope

1. **Upload e leitura da medição externa** pelo caminho já existente de presign/confirm,
   com digest, sem exigir projeto nem prancha associados.
2. **Rota `/v1` da auditoria**, que roda os motores existentes sobre o arquivo e devolve o
   relatório estruturado — reusando `compare_bulletin`, a paridade de fórmula e o
   `diagnose_contract` **sem alterá-los**.
3. **Relatório como artefato**, com digest e proveniência do arquivo auditado: quem subiu,
   quando, sobre qual conteúdo. Auditoria que não se pode reconferir não vale nada.
4. **Tela da jornada**: subir, acompanhar, ler o relatório por classe de achado, e exportar
   o relatório (o cliente precisa mandá-lo adiante).
5. **A dupla de veredito**: "fecha centavo a centavo" é resposta legítima e precisa ser tão
   visível quanto a lista de furos — o valor de uma auditoria limpa é dizer que está limpa.

## Out of Scope

- **Corrigir a medição alheia.** A auditoria aponta; corrigir é ato de quem a fez.
- **Inferir intenção do furo** ("isto é fraude", "isto é erro de digitação"). O relatório
  descreve o que não fecha, com o número; classificar intenção é humano.
- Chamada paga de IA: os três motores são determinísticos e assim ficam.
- Vínculo com contrato/saldo do croquito quando o arquivo é externo — auditar não é medir.

## Acceptance Criteria

1. Um MAPÃO real de cliente é auditado pela rota, e o relatório reproduz **exatamente** os
   achados que o CLI produz hoje sobre o mesmo arquivo (inclusive os oito erros de centavo,
   que viram o caso de aceite).
2. Arquivo que fecha centavo a centavo devolve `zero_cent` com a frase por extenso, sem
   lista de furos inventada.
3. O relatório carrega o digest do arquivo auditado, o autor e o instante; reauditar o
   mesmo arquivo produz o mesmo relatório.
4. Nenhum motor existente muda de comportamento: os goldens de `bulletin_compare` e de
   paridade seguem byte-idênticos.
5. Arquivo ilegível ou fora do layout recusa com o motivo por extenso, nunca com relatório
   vazio — silêncio aqui seria pior do que erro.

## Unknowns

1. **Quanto do relatório é compreensível sem contexto da obra.** Os oito erros de centavo
   são óbvios; `BALANCE_NEGATIVE` em 548 linhas exige explicação. A tela precisa de
   hierarquia de gravidade que ainda não existe — é decisão do pacote de design.
2. ~~**Se a auditoria vira produto avulso ou parte da jornada de medição.**~~ **Respondido
   em 2026-09-05** (Daniel Campos): **produto avulso** — jornada própria, sem exigir
   projeto, prancha, contrato ou rodada no croquito. É a escolha que faz a auditoria
   alcançar quem ainda não é cliente, que é o pitch comercial; o custo aceito é a casca
   nova de jornada. Vincular a auditoria a uma rodada existente fica como fatia posterior,
   se e quando fizer sentido.

## Human Gates

1. ~~**Seleção e prioridade**~~ — **cumprido em 2026-09-05** (Daniel Campos): `HIGH`.
2. ~~**Decisão do unknown 2** (avulso × dentro da medição)~~ — **cumprido em 2026-09-05**:
   produto avulso.
3. **Design Approval Package** — `INTERFACE_CHANGE`, jornada nova. **Único gate restante.**
   A [revisão 1 do pacote](mock/README.md) foi produzida em 2026-09-05 e **aguarda
   aprovação**: seis estados e seis decisões, com uma correção de desenho aplicada na
   revisão (a comparação avulsa é entre as **camadas do próprio arquivo** do cliente — MAPÃO
   × BM —, nunca contra uma conferência do croquito, que no modo avulso não existe).

## References

- `packages/valuation/src/croquito_valuation/bulletin_compare.py` — `compare_bulletin` e
  `BulletinComparisonReport`, com as cinco classes de divergência e o `zero_cent`.
- `packages/valuation/src/croquito_valuation/contract_diagnosis.py` — `diagnose_contract`.
- `Makefile:166` — `valuation-parity`, hoje local e nunca em CI (por conter dado de
  cliente).
- [Roadmap](../../product/ROADMAP.md), registro de nascimento das três candidatas.
