# F-038 — Evidência

Feature: [O item de legenda é um pacote de serviços, não um código](feature.md)
Estado: `DONE` — aceita por ato humano em 2026-09-05
Data: consolidado escrito em 2026-09-05; a execução é de 2026-08-25 a 2026-08-26

Esta feature correu por **issues** (#71 epic, #73–#84 as doze tarefas, #96 o
desdobramento da decisão 6), antes da convenção de consolidar a evidência num arquivo
por feature. Este documento não reescreve os relatórios das issues: ele aponta para
elas e registra o que só aconteceu depois — o exercício contra o dado real e o aceite.

## Human Gates

| Gate | Estado |
| --- | --- |
| [ADR-0053](../../adr/0053-cardinalidade-n-n-elemento-servico.md) — cardinalidade N:N | ✅ **Aceito em 2026-08-25** (Daniel Campos) |
| [Design Approval Package](mock/README.md) | ✅ Revisão 1 **aprovada em 2026-08-26**; [revisão 2](mock/rev2/README.md) (autoria de matriz e declaração `PARTIAL`) **aprovada em 2026-08-26** (Daniel Campos) |
| Extração e aceite contra o documento real | ✅ **Cumprido em 2026-09-05** (Daniel Campos, pelo chat) — seção abaixo |

## O que foi entregue

As doze tarefas do [plano](plan.md), todas mergeadas na `main` até 2026-08-26, com os
portões verdes por tarefa — a tabela do plano carrega issue e estado de cada uma. Os
três desvios conscientes (vocabulário de fórmulas aberto com `DECLARED_PRODUCT`; fatores
da derivação lidos do cabeçalho da memória; e a premissa do ROADMAP corrigida pela #84)
estão registrados no plano, com o porquê.

## O aceite contra o documento real (2026-09-05)

**Aceita por ato humano em 2026-09-05** (Daniel Campos, pelo chat). O que faltava não era
código: era a extração e o aceite reais do pacote do Campo do Toca, com a planilha como
oráculo. O dono delegou a execução à bancada e exerceu o veredito.

A bancada (banco próprio `croquito_f038f042`, API em `127.0.0.1:8010`, sessão OIDC real
como `orcamentista.local`) montou a praça-bancada pelo caminho de produção: catálogo
SCO-Rio Out/2023 **real** (4.964 entradas) instalado por upload, takeoff com os elementos
e quantidades da memória real, e a matriz transcrita parcela a parcela do documento.

O ato central foi **na tela**: o pacote do PISO EM CONCRETO montado pela busca da cascata,
seis "Confirmar código" um a um e o "Fechar pacote de serviços" como ato próprio — tudo
gravado até o banco, com o item aparecendo como **pendente** até o fechamento.

Os critérios de aceite do contrato, com o arquivo como oráculo:

| Critério | Resultado |
| --- | --- |
| `PISO EM CONCRETO` gera **seis** linhas de orçamento | ✅ as 6 folhas de cálculo com parcela do PISO, nas linhas `MT14150050(A)`, `BP04050350(/)`, `ET39050109(/)`, `BP09100050(B)`, `SC34150200(/)`, `SC29100100(A)` |
| `BP04050350(/)` fecha em **478,74 m²** somando quatro parcelas rotuladas | ✅ CAMPO DE FUTEBOL (zerada, mantida como no documento) + PISO 418,12 + INTERTRAVADO 59,34 + FORRAÇÃO 1,28 |
| `BP09100050(B)` fecha em **418,12 m²** | ✅ |
| `TC04100050(/)` produz **365,86 t.dam** sem digitação | ✅ já verde por teste desde a #83 |
| Rodada anterior relê byte-idêntica; digest de aprovação não se move | ✅ já verde por teste desde a #74 |
| Item com pacote aberto aparece como **pendente**, nunca como pronto | ✅ capturado antes do fechamento |

A mesma praça-bancada serviu de "praça já feita" para o gate 4 da
[F-042](../F-042-acervo-de-parcelas-de-canteiro/evidence.md), cuja seção registra também
o achado da rodada (serviço `STANDALONE` imprecificável, reparado) e a
[issue #177](https://github.com/biahflow/croquito/issues/177) (chave React duplicada na
etapa Códigos).

Capturas e scripts em `output/f038-f042-fecho/` — retenção local de 7 dias, porque as
quantidades e rótulos vêm do documento real do cliente e não são versionados.

## Dívida declarada

- **A extração e o aceite reais pela orçamentista.** O aceite é sobre o mecanismo provado
  contra o documento; o uso pelo ofício — ela montando os pacotes da praça dela — é o
  teste de verdade pendente, no padrão dos aceites de 2026-09-02.
