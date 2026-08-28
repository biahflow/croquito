# F-043 — Plano de implementação

Gates cumpridos em 2026-08-28, por ato humano (Daniel Campos):
[ADR-0059](../../adr/0059-item-contratado-fora-da-tabela-sco.md) aceito,
[Design Approval Package](mock/README.md) revisão 1 **aprovado**, e duas decisões do dono — o
gabarito entregável é a aba `PLANILHA ORÇAMENTÁRIA` (433 códigos), e ele vive como **artefato
de plataforma**, no molde do acervo de catálogos da
[F-037](../F-037-acervo-de-catalogos/feature.md). A revisão 2 do pacote, produzida quando o
documento real chegou, **aguarda aprovação**.

## A ordem é ditada pelo que o auditor consegue provar

O escritor vem primeiro e inteiro porque o risco central não é escrever errado — é escrever
errado **e parecer certo**. Com 433 linhas e 390 zeros, um erro de mapeamento código→linha põe
a quantidade na linha errada sem que nada aparente estar quebrado. Por isso a auditoria
célula a célula anda junto com o escritor, na mesma tarefa, e não depois.

A publicação do gabarito como artefato de plataforma vem em seguida, e a escolha na tela por
último — o gabarito é **dado**, e o mecanismo tinha de existir antes de haver onde guardá-lo.

## Tarefas

| # | Tarefa | Estado |
|---|---|---|
| T1 | [Gabarito de ordem fixa e memória de cálculo](tasks/T1-gabarito-e-memoria.md) | **Entregue** |
| T2 | Publicar o gabarito como artefato de plataforma | Não iniciada |
| T3 | Escolher o gabarito na jornada web | Não iniciada |

## O que a T1 provou contra o documento real

O gabarito de 433 linhas foi transcrito do arquivo do cliente e publicado pelo escritor novo:
as 433 linhas saíram na ordem do gabarito, com as **43 quantidades idênticas** às do cliente e
as 390 restantes zeradas e presentes, e as duas abas passaram pelo auditor **sem um único
finding**. Toda fórmula coube na gramática fechada de `canonical.py` — nada foi estendido. Ver
[`evidence.md`](evidence.md).

## Reuso, não generalização

A memória do orçamento reusa `plan_calc_block` — o `_plan_block` da medição, promovido a
público. `_plan_memory` continua privada e específica: ela exige `Valuation`/`WorksiteBulletin`,
e generalizá-la seria outra coisa. O golden da medição não mudou um byte, e é o oráculo disso.

## Integração

Branch `feat/f-043-gabarito-planilha`, reunida em `feat/f-042-f-043-f-044-integracao` junto com
a F-042 e a F-044, sem conflito.

## Human Gates que continuam abertos

1. **Revisão 2 do Design Approval Package.**
2. **Qual forma de rodapé vale**: o documento do cliente imprime `TOTAL` e `TOTAL S/BDI` e não
   imprime linha de BDI, enquanto o [ADR-0038](../../adr/0038-bdi-como-conceito-de-pre-licitacao.md)
   manda imprimir o BDI como diferença entre totais truncados. As duas dão o mesmo dinheiro.
3. **Aceite do arquivo gerado** contra o real, por quem entrega à prefeitura.
