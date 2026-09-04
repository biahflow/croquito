# F-042 — Plano de implementação

Gates cumpridos em 2026-08-28, por ato humano (Daniel Campos):
[ADR-0059](../../adr/0059-item-contratado-fora-da-tabela-sco.md) aceito,
[ADR-0060](../../adr/0060-onde-vive-o-acervo-de-parcelas-de-canteiro.md) **aceito** (onde o
acervo vive — unknown 1), e o [Design Approval Package](mock/README.md) revisão 1 **aprovado**.
A revisão 2 do pacote, produzida durante a execução, foi **aprovada na mesma data**.

## A ordem é ditada pelo que pode ser provado sozinho

O motor vem primeiro e sozinho porque é onde mora a única regra que não pode falhar: **falha
fechada**. Enquanto aplicar o acervo com parâmetro faltante não recusar nomeando todos os
faltantes, sem materializar nada, não adianta ter rota nem tela — uma planilha parcial com
aparência de completa é o modo de falha mais caro desta feature.

A persistência vem em seguida porque depende de uma decisão de arquitetura (ADR-0060) que o
motor não precisa conhecer: `apply_site_setup_kit` é puro e não sabe onde o acervo mora. A tela
correu em paralelo com a persistência, contra um contrato de API fixado por escrito — as duas
tocam arquivos disjuntos, e o que uma supôs da outra está registrado nos relatórios.

As duas últimas tarefas não estavam no plano original: nasceram de defeitos que a própria
execução expôs, e ambas foram autorizadas pelo dono antes de começarem.

## Tarefas

| # | Tarefa | Estado |
|---|---|---|
| T1 | [Domínio do acervo de parcelas de canteiro](tasks/T1-dominio-do-acervo.md) | **Entregue** |
| T2 | [Persistência do acervo e as rotas da rodada](tasks/T2-persistencia-e-rotas.md) | **Entregue** |
| T3 | [A tela: escolher, declarar, pré-visualizar, aplicar](tasks/T3-tela-do-acervo.md) | **Entregue** |
| T4 | [A pré-visualização marca o bloqueado em vez de recusar](tasks/T4-previa-tolerante.md) | **Entregue** |
| T5 | [A tela mostra o bloqueado e recupera o que já está gravado](tasks/T5-hidratacao-e-bloqueio.md) | **Entregue** |
| T6 | [Autoria de acervo na tela (estado 09 do pacote)](tasks/T6-autoria-na-tela.md) | **Entregue** (2026-09-04) |

## Os três defeitos que a execução expôs

**O beco sem saída da recusa (T4).** O pacote aprovado prometia "declare, ou remova na
pré-visualização as parcelas que os citam" — mas a recusa acontecia antes de a pré-visualização
existir. Um acervo de 24 parcelas em que só 2 citam um parâmetro indisponível ficava
inteiramente inaplicável. A emenda separou as duas metades: **prever é ler** e marca o
bloqueado; **aplicar** continua recusando fechado. A assimetria é provada por testes lado a
lado, com o mesmo estado.

**A matriz com dois donos (T5).** O `apply` grava a matriz no servidor; a tela monta o rascunho
e manda a matriz inteira no `build`. Enquanto a sessão vive, os dois concordam — depois de um
recarregamento, montar o orçamento apagaria do banco o que o acervo aplicou. A raiz é anterior
a esta feature (a matriz nunca foi lida de volta desde a F-038), e a correção é a tela
**hidratar** o rascunho a partir do que está gravado, pela rota nova `GET .../calc-matrix`.

**A tela em branco da hidratação (achado na T6).** A hidratação da T5 testava a proveniência
com `kit_origin !== undefined`, e o servidor manda `kit_origin: null` para a parcela autorada
à mão — `model_dump` do Pydantic serializa o opcional ausente como `null`. O `null` entrava no
ramo e era desreferenciado: `TypeError` que derrubava o `OrcamentoApp` inteiro, **em branco**,
em qualquer rodada com contribuição autorada à mão na matriz gravada. Nenhum teste pegava
porque as fixturas montam a matriz com o campo AUSENTE, que é a forma que a tela **produz** —
não a que ela **recebe**. Achado pela evidência de navegador da T6 e corrigido nela, com
regressão em `matrix.test.ts`.

## Integração

Uma branch por tarefa, todas reunidas em `feat/f-042-f-043-f-044-integracao` junto com a F-043
e a F-044. As cinco primeiras juntaram sem conflito, e os portões completos rodaram na base
reunida, não só por worktree.

## Riscos que ficam declarados

- O merge do apply é por `kit_version`: **dois acervos diferentes que declarem a mesma versão
  são indistinguíveis na matriz**. Corrigir exige `kit_id` em `SiteSetupOrigin`, o que toca o
  domínio e provavelmente uma emenda ao ADR-0060.
- A pré-visualização mostra os operandos, mas **não as deduções** da parcela. A quantidade já
  as considera, então uma parcela com dedução mostraria uma conta que não fecha com o número.
  Nenhum acervo real conhecido usa dedução; a dívida está declarada.
- O acervo real do Campo do Toca é **menor que as 24 parcelas** que a feature supôs — ver
  [`evidence.md`](evidence.md).
- A autoria recorta o acervo da matriz **gravada**, e o índice de cada binding é a posição da
  parcela na enumeração do servidor. A tela lê a matriz e a `base_version` na MESMA resposta e
  grava contra ela, então a rodada que andar no meio devolve `409` em vez de um acervo com
  índice deslocado. O que fica declarado é a consequência: **parcela de canteiro autorada na
  sessão e ainda não montada não entra no acervo** — a tela diz isso por extenso, e não a
  monta sozinha.

## Human Gates que continuam abertos

1. **Autoria do primeiro acervo**, que é ato da orçamentista. Desde a T6 ele tem caminho na
   tela, exercido de ponta a ponta contra uma praça sintética
   ([`evidence.md`](evidence.md)); o que falta é o ato dela sobre uma praça real. As cinco
   parcelas que o documento real sustenta estão em [`evidence.md`](evidence.md).
