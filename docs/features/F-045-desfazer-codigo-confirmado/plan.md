# F-045 — Plano de implementação

Gates **abertos** no momento da execução, e é preciso lê-los antes do diff:
[ADR-0061](../../adr/0061-revogacao-de-codigo-confirmado.md) está `Proposed` e o
[Design Approval Package](mock/README.md) revisão 1 aguarda aprovação. A implementação foi
autorizada pelo dono em 2026-08-28 ("registra como F-045 no roadmap e codar ela") e segue
exatamente o que os dois artefatos propõem; se algum deles mudar no aceite, o código muda com
ele. Nada aqui é irreversível: a rota é nova, o campo do conjunto nasce vazio e nenhuma
migração foi criada.

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

## Integração

Branch `feat/f-042-f-043-f-044-integracao`, a mesma da rodada. Nenhuma migração: o campo novo
do conjunto vive no JSON da revisão, com default vazio, e conjunto gravado antes relê sem
nada a converter.

## Human Gates que continuam abertos

1. **[ADR-0061](../../adr/0061-revogacao-de-codigo-confirmado.md)** — aceite da semântica.
2. **[Design Approval Package](mock/README.md) revisão 1** — aprovação da forma.
3. **Unknown 1 da feature** — o que fazer quando o orçamento já foi aprovado. A execução
   **não** o decidiu: aplicou a recusa provisória do ADR-0061 D7
   (`ASSIGNMENT_REVOCATION_AFTER_APPROVAL`), que é o lado reversível. Liberar é apagar uma
   checagem; o contrário — assinatura apontando para um conjunto que mudou — não tem volta.
