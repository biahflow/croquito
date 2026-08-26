# F-038 — Plano de implementação

Gates cumpridos: [ADR-0053](../../adr/0053-cardinalidade-n-n-elemento-servico.md) aceito em
2026-08-25 e [Design Approval Package](mock/README.md) revisão 1 aprovado em 2026-08-26.

O trabalho está fatiado em doze tarefas, publicadas como issues em `biahflow/croquito`
(#73 a #84). Cinco estão entregues: quatro na branch `feat/f-038-digest-estavel` e a T5 em
`feat/f-038-t5-pacote-de-servicos`.

## A ordem é ditada por um risco, não por conveniência

`Estimate.content_digest()` serializa `calc_sheets` inteiro. Qualquer campo novo em
`CalcBlock` entra no payload como `null` e **muda o digest de artefatos já assinados**, que
passam a falhar em `APPROVAL_CONTENT_MISMATCH`. Pelo
[ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md), o orçamento
assinado é o consolidado contratual da medição: mover esse digest invalida um contrato.

Por isso **T2 (#74) vem antes de tudo** — proteger o digest antes que exista o primeiro
campo novo — e T3 (#75) só depois. O restante segue a dependência natural: o vínculo antes
dos builders, e o layout impresso isolado numa tarefa própria.

## Tarefas

| # | Issue | Tarefa | Estado |
|---|---|---|---|
| T2 | [#74](https://github.com/biahflow/croquito/issues/74) | Digest de aprovação estável por versão | **Entregue** |
| T1 | [#73](https://github.com/biahflow/croquito/issues/73) | Importar a base SCO Out/2023 da planilha | **Entregue** |
| T11 | [#83](https://github.com/biahflow/croquito/issues/83) | Tabela de derivação de transporte como dado | **Entregue** |
| T3 | [#75](https://github.com/biahflow/croquito/issues/75) | `ContributionBasis` e os campos da matriz | **Aceita** |
| T4 | [#76](https://github.com/biahflow/croquito/issues/76) | `CalcMatrix` e dependência sem ciclo | **Entregue** |
| T5 | [#77](https://github.com/biahflow/croquito/issues/77) | Vínculo `(item_id, code)` e fechamento de pacote | **Entregue** |
| T6 | [#78](https://github.com/biahflow/croquito/issues/78) | Builders passam a iterar serviços | Pendente |
| T7 | [#79](https://github.com/biahflow/croquito/issues/79) | Memória comporta quatro operandos | Pendente |
| T8 | [#80](https://github.com/biahflow/croquito/issues/80) | CLI, rotas `/v1` e migração da matriz | Pendente |
| T9 | [#81](https://github.com/biahflow/croquito/issues/81) | Tela: montar o pacote e ver a memória | Pendente |
| T10 | [#82](https://github.com/biahflow/croquito/issues/82) | Gabarito de pacotes como oráculo do golden | Pendente |
| T12 | [#84](https://github.com/biahflow/croquito/issues/84) | Corrigir a premissa refutada no ROADMAP | Pendente |

## O que a execução decidiu diferente do plano

Três desvios, todos porque o arquivo real contradisse a premissa escrita. Ficam registrados
aqui porque são a razão de o resultado não bater com o texto das issues.

### O vocabulário de fórmulas é aberto (T3)

O plano previa cinco receitas novas em `CalcRecipe`, um enum `CalcQuantityKind` com quinze
grandezas e um validador cruzando os dois. A memória real tem **45 formas de fórmula
distintas** e **43 termos de operando, 21 deles de ocorrência única** (`GOLAS x QTD/GOLA`,
`REFLETORES x M/REFLETOR`, `COMP x ALT x TAXA x COEF EMOP`). Cinco receitas deixariam
quarenta de fora.

Entrou **uma** receita, `DECLARED_PRODUCT`, que nomeia o que todas têm em comum e que
`expected_subtotal` já recomputava. `CalcQuantityKind` ficou fora.

### A forma da derivação muda com o destino (T11)

O plano tratava a distância como padrão único da tabela. O extrator recusou com
`HAULAGE_DISTANCE_NOT_UNIFORM`: transporte horizontal tem distância, carga e descarga não,
retirada de entulho usa empolamento. Os fatores passaram a ser lidos **do cabeçalho que a
memória declara**, não por posição — ler por posição teria produzido número errado em
silêncio.

### O item extra-SCO também é transportado (T11)

O contrato traz `IE00040849`, fora do padrão SCO. O validador aceita o mesmo superset
estrutural das demais origens de preço, senão o entulho dele ficaria de fora da conta.

## Verificação

O oráculo é a planilha. Cada tarefa fecha com `make check` e `make test` verdes, e o
critério final é reproduzir os números do arquivo: `478,74` para o saibro somando quatro
parcelas, `418,12` para o pavimento rígido, `365,86 t.dam` de transporte derivados sem
digitação, e o digest de rodada antiga imóvel.
