# Roteiro da sessão da orçamentista

Status: pronto para exercer
Preparado em: 2026-09-05
Fecha as dívidas declaradas de quatro aceites: **F-038** (o pacote de serviços),
**F-042** (o acervo de canteiro), **F-045** (desfazer um código) e **F-039**
(reajuste entre medições).

Todas as quatro features foram aceitas em 2026-09-05 **sobre o mecanismo**, provado
por bancada contra o documento real. O que nenhuma delas tem é o **uso pelo ofício**:
a orçamentista montando a praça dela, do jeito dela. É isso que esta sessão exerce —
e é a única coisa que separa cada uma de "provada" para "usada".

Não é um teste roteirizado passo a passo: é a lista do que precisa ACONTECER, na
ordem natural do trabalho dela. Quanto menos eu disser como fazer, mais a sessão vale.

## O que preparar antes (eu faço, ~10 min)

| Item | Como |
| --- | --- |
| Stack local de pé | `make dev-services` — PostgreSQL, floci e Keycloak |
| Banco da sessão | banco próprio, migrado, sem estado de bancada |
| Catálogo real | o SCO-Rio Out/2023 (4.964 itens) publicado no acervo da plataforma |
| Prancha da praça | a praça que ela escolher — pode ser uma real que ela já orçou, para comparar |
| API e SPA | `?orcamento=<id>` aberto na etapa Códigos, sessão dela no Keycloak |

**Providers pagos**: desligados por padrão. Se ela quiser exercer a extração de legenda
por IA (o caminho normal dela), isso é chamada paga e precisa da sua autorização — o
teto por rodada é US$ 5,00 e o gasto real de uma legenda fica na casa de centavos.

## O que a sessão precisa produzir

### 1 · O pacote de serviços de um elemento (F-038)

O ato central: pegar **um elemento da legenda** e montar o pacote de códigos SCO que
ele dispara — não um código, quantos forem.

- Ela busca os códigos como quiser (shortlist ou busca por código/descrição).
- Confirma um a um, e **fecha o pacote** quando não vem mais nada.
- O que quero saber depois: **quantos cliques** custou o pacote, se a shortlist ajudou
  ou atrapalhou, e se faltou algum caminho que ela usaria (colar uma lista? copiar de
  outro elemento?).

### 2 · O acervo de canteiro (F-042)

- Ela declara as parcelas de canteiro **da praça dela** (as que não vêm da prancha:
  placa, container, vigia, WC, transporte de alambrado…).
- **Guarda como acervo**, escolhendo o nome e — o ponto que só ela decide — **quais
  números viram parâmetro** (o prazo em meses? o semiperímetro? a distância?) e quais
  ficam constantes.
- Numa segunda praça, **aplica** o acervo declarando os parâmetros novos.
- O que quero saber: se a distinção parâmetro × constante ficou óbvia na hora, e se o
  acervo que ela criou serviria de verdade para a próxima praça — ou se ela criaria um
  acervo por tipo de obra.

### 3 · Desfazer um código confirmado (F-045)

- Depois de confirmar, ela **desfaz** um código de propósito, com o motivo escrito.
- Confere se o elemento voltou a "incompleto" e se o código voltou a ser escolhível.
- O que quero saber: se o motivo obrigatório incomoda, e se a lista de desfeitos é
  informação útil ou ruído.

### 4 · Reajuste entre medições (F-039) — se houver contrato reajustado

Só se ela tiver uma obra real com reajuste. Na abertura da rodada de medição, ela
declara o reajuste (índice + período + fator, ou versão nova da tabela) e confere se a
memória e o boletim mostram contratado × vigente do jeito que a prefeitura espera.

Se não houver caso real hoje, esta parte fica para quando houver — e a dívida da F-039
permanece declarada, o que é honesto.

## O que EU registro depois

Cada ato dela vira evidência real (não sintética) nos `evidence.md` das quatro
features, e o que ela reclamar vira issue ou candidata a feature — inclusive as
reclamações "pequenas" de copy e de número de cliques, que são o material que falta.

## O que esta sessão NÃO é

- Não é validação de que o software "funciona": isso já está provado por teste,
  bancada e as capturas de cada feature.
- Não é treinamento: se algo só funciona depois de explicado, **isso é o achado**.
- Não é o gate de nenhuma feature: as quatro já estão `DONE`. Aqui se fecha a dívida
  declarada, e o que aparecer de errado vira trabalho novo com nome próprio.
