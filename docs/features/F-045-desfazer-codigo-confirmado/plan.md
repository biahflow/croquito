# F-045 — Plano de implementação

Gates cumpridos em 2026-08-28, por ato humano (Daniel Campos):
[ADR-0061](../../adr/0061-revogacao-de-codigo-confirmado.md) **aceito** e
[Design Approval Package](mock/README.md) revisão 1 **aprovado** — os dois no mesmo dia da
execução, e depois dela: a implementação foi autorizada primeiro ("registra como F-045 no
roadmap e codar ela"), correu sobre o que os dois artefatos propunham, e o aceite veio sobre
o que estava escrito neles. Nada aqui era irreversível: rota nova, campo do conjunto com
default vazio, nenhuma migração.

## Por que a fatia é única

A feature tem uma superfície pequena e um invariante grande. Quebrá-la em três entregas —
domínio, API, tela — deixaria o meio do caminho num estado pior que o de hoje: uma rota capaz
de tirar o par do conjunto sem a compensação do índice ensinaria à praça seguinte um código
desfeito, com a autoridade do precedente. As três tarefas abaixo foram executadas na mesma
rodada, e a ordem entre elas é de leitura, não de entrega.

## Tarefas

| # | Tarefa | Estado |
|---|---|---|
| T1 | Domínio: `apply_code_revocation`, o registro em `revocations` e a reabertura do pacote | **Entregue** |
| T2 | API: as duas rotas irmãs e a compensação do índice de precedentes | **Entregue** |
| T3 | Tela: desfazer no cartão, o efeito à vista e a lista de desfeitos | **Entregue** |
| T4 | [A mesma superfície na jornada de medição](tasks/T4-tela-da-medicao.md) | **Entregue** — sob a revisão 2 do pacote |

## O que a execução decidiu, e o ADR não decidia

1. **`revocations` é registro, não estado de assignment.** O par sai da lista; o registro fica
   ao lado. Marcar como revogado dentro de `assignments` obrigaria todo consumidor — boletim,
   exportação, precedente, contagens — a lembrar de filtrar, e o esquecido imprimiria linha
   revogada.
2. **O par reconfirmado some da lista de desfeitos da tela**, mas o registro continua no
   conjunto. A lista responde "por que este elemento não tem mais aquele código?"; um código
   que voltou não tem essa pergunta.
3. **A fonte de preço da compensação é lida do assignment**, antes de ele sair do conjunto, e
   não pedida ao cliente: é o servidor que sabe de qual tabela aquele par veio.
4. **A recusa depois da aprovação nasceu na execução**, e não do desenho: a leitura do
   ADR-0046 mostrou que a aprovação amarra o digest do ORÇAMENTO, e que a revogação passaria
   por baixo dele sem que o portão de exportação notasse. Virou a D7 do ADR-0061.
5. **`_ensure_same_plate` foi extraída** de `_ensure_batch_decidable` para valer também na
   revogação. A checagem não podia continuar existindo só no caminho que a descobriu primeiro.

## A T4 veio depois, e por quê

A rota da medição nasceu junto com a do orçamento (T2) e ficou sem tela, registrada como
questão aberta do pacote. O dono pediu o fechamento em 2026-08-28, e a **revisão 2** do pacote
desenhou a forma: ali o pacote era uma frase com os códigos entre parênteses, sem onde
pendurar um ato por código.

A T4 também **moveu o módulo puro** para `apps/web/src/codeRevocation.ts`. As duas jornadas
não se importam entre si por decisão (ADR-0028 D9), e duplicar aquelas funções criaria duas
verdades para regras que precisam ser uma só — em especial a de que um par reconfirmado sai
da lista de desfeitos. O que continua de cada jornada é a copy, o transporte e os componentes.

## Integração

Branch `feat/f-042-f-043-f-044-integracao`, a mesma da rodada. Nenhuma migração: o campo novo
do conjunto vive no JSON da revisão, com default vazio, e conjunto gravado antes relê sem
nada a converter.

## Human Gates

1. ~~**[ADR-0061](../../adr/0061-revogacao-de-codigo-confirmado.md)**~~ — **aceito em
   2026-08-28**.
2. ~~**[Design Approval Package](mock/README.md) revisão 1**~~ — **aprovado em 2026-08-28**.
3. **Unknown 1 da feature** — o único que continua aberto: o que fazer quando o orçamento já
   foi aprovado. A execução
   **não** o decidiu: aplicou a recusa provisória do ADR-0061 D7
   (`ASSIGNMENT_REVOCATION_AFTER_APPROVAL`), que é o lado reversível. Liberar é apagar uma
   checagem; o contrário — assinatura apontando para um conjunto que mudou — não tem volta.
