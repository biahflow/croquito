# F-001 — Pacote de evidências

Status: `DONE`
Responsável: Engineering
Última revisão: 2026-08-17 (fechamento, seção 11)

Este documento consolida referências estáveis ao contrato, ao plano, à baseline, à
execução, à validação e à revisão de F-001. Ele não substitui as fontes de evidência
atribuídas a cada Builder e não é aprovação humana.

## 1. Contrato e plano

| Artefato | Fonte |
| --- | --- |
| Feature Contract | [feature.md](feature.md) |
| Feature Execution Plan | [plan.md](plan.md) |
| Entrada no roadmap canônico | [Roadmap](../../product/ROADMAP.md), seção “Trabalho de engenharia em andamento” |
| Convenção de lifecycle e perfis de validação | [Project Context](../../engineering/PROJECT_CONTEXT.md) |

## 2. Autorização humana

**2026-08-17 — rodada R1 (correção documental).** O usuário aprovou uma rodada de correção
com escopo fechado nos quatro arquivos abaixo, **expandindo explicitamente o escopo** para
incluir a criação deste `evidence.md`, que a rodada R0 havia declarado fora de escopo:

- `docs/product/ROADMAP.md`
- `docs/features/F-001-roadmap-clarification/feature.md`
- `docs/features/F-001-roadmap-clarification/plan.md`
- `docs/features/F-001-roadmap-clarification/evidence.md` (novo)

Condições declaradas na autorização: rodar `make check`, **não fazer commit**, encerrar com
`BUILD REPORT` completo, e resolver os achados da revisão **sem reclassificar por
preferência** — apenas por qualificadores do texto original e observações factuais.

**Decisão humana adicional da mesma data:** a evidência de execução da rodada R0 é
**irrecuperável** (o `BUILD REPORT` original nunca foi transmitido). O `BUILD REPORT` da
rodada R1 passa a ser a única evidência primária de execução, cobrindo o estado FINAL.
Nada foi reconstruído em nome do Builder de R0.

Esta autorização é a expansão de escopo exigida pela Definition of Done global. Ela não
aprova o conteúdo do inventário, não altera status de ADR, não autoriza verificação de
estado remoto e não seleciona nenhum item `PLANEJADO`.

## 3. BASELINE

| Fato | Valor |
| --- | --- |
| Commit base | `a92fda7` — `docs(adr): ratify approved architecture decisions` |
| Branch | `main`, sem branch nova, sem stash, sem conteúdo staged |
| Publicação | `main` está 2 commits à frente de `origin/main` (`b62c099`, `a92fda7`) desde antes de F-001 — condição preexistente, não tocada por nenhuma rodada desta feature |
| Worktree antes de R1 | `M docs/product/ROADMAP.md` e o diretório não rastreado `docs/features/F-001-roadmap-clarification/` — ambos saídas de R0 |
| Falhas preexistentes conhecidas | Nenhuma registrada |

Limitação declarada: **a baseline de R0 não foi registrada pelo Builder daquela rodada**,
embora F001-T01 a exigisse. A tabela acima é a leitura feita pelo Reviewer no início da
revisão de R0 e reconfirmada no início de R1; ela é evidência do Reviewer, não do Builder.

## 4. CHANGE

### Rodada R0

| Arquivo | Mudança |
| --- | --- |
| `docs/product/ROADMAP.md` | +58 linhas: entrada F-001, inventário de 34 linhas, reconciliação de ambientes |
| `docs/features/F-001-roadmap-clarification/feature.md` | criado (Feature Contract) |
| `docs/features/F-001-roadmap-clarification/plan.md` | criado (Feature Execution Plan + inventário congelado) |

### Rodada R1

| Arquivo | Mudança |
| --- | --- |
| `docs/product/ROADMAP.md` | vocabulário de classificação novo; tabela reescrita com as 34 chaves verbatim e coluna `#`; evidência e observação atualizadas nos itens 18, 22 e 24 (e detalhadas em 17, 19 e 20); reconciliação de ambientes em três eixos |
| `feature.md` | escopo, critérios de aceite e portões humanos da rodada R1; `evidence.md` retirado de “Out of Scope” com nota da autorização |
| `plan.md` | inventário congelado reproduzido verbatim; tarefa `F001-T04`; `critical_path`, `integration_strategy`, `human_gates` e `planning_findings` atualizados |
| `evidence.md` | criado (este documento) |

Fidelidade do inventário: as 34 chaves de R1 foram **extraídas por script** de
`git show HEAD:docs/product/ROADMAP.md`, não redigitadas. Quebras de linha do original
foram colapsadas em espaço; em `plan.md` os links relativos foram reancorados ao diretório
do arquivo. Nenhuma outra alteração de texto.

Classificações: **inalteradas em relação a R0** — 21 `PLANEJADO`, 5
`EM OPERAÇÃO/HOMOLOGAÇÃO`, 4 `EXCLUÍDO`, 3 `IMPLEMENTADO`, 1 `UNKNOWN`.

### Conferência do vocabulário contra as 34 linhas

O vocabulário foi escrito depois das classificações e conferido linha a linha. Casos
examinados por estarem na fronteira, nenhum deles alterado:

- itens 1, 2 e 4 (`IMPLEMENTADO`): o `STATUS.md` registra o ciclo humano correspondente
  como concluído (2026-08-13) ou não declara rodada de homologação pendente para o próprio
  item;
- itens 12 a 16 (`EM OPERAÇÃO/HOMOLOGAÇÃO`): o `STATUS.md` declara explicitamente “o que
  resta do M6/M8 não é código”, com a rodada real da Toca ainda aberta.

Nenhuma divergência entre definição e classificação foi encontrada. Se alguma surgir em
rodada futura, a regra registrada é declarar a divergência na observação, não reclassificar.

## 5. Evidência primária de execução

| Rodada | Evidência primária |
| --- | --- |
| R0 | **Irrecuperável.** O `BUILD REPORT` do Builder de R0 nunca foi transmitido e não pode ser reconstruído. Declarado como perda de evidência por decisão humana de 2026-08-17. |
| R1 | `BUILD REPORT` da rodada R1, emitido no encerramento desta rodada, cobrindo o estado FINAL dos quatro arquivos. |

O que é verificável independentemente da evidência ausente de R0 está registrado nas seções
3, 4 e 6 e é atribuído ao Reviewer/R1, nunca ao Builder de R0.

## 6. Validação

| Perfil | Rodada | Resultado |
| --- | --- | --- |
| `scripts/check_docs.py` (read-only) | R0 | Executado pelo Reviewer: `Documentação válida: 102 arquivos Markdown`, exit 0. **Não substitui `make check`.** |
| `make check` | R0 | **Sem evidência.** Exigido por F001-T03; nenhum resultado foi registrado pelo Builder. |
| `make check` | R1 | **Exit 0.** `ruff check`, `ruff format --check`, `mypy` (166 arquivos, sem problemas), `check_docs` (103 arquivos Markdown), `schema_export --check`, `contracts:check`, build de `@croquito/web` e `@croquito/medicao`, `terraform fmt -check`. |
| Conferência verbatim das 34 chaves | R1 | Script de comparação contra `git show HEAD:docs/product/ROADMAP.md`: 34 chaves, únicas, na ordem original, presentes em `plan.md` e na tabela do roadmap; entrada F-001 ausente do inventário. |
| Verificação de estado remoto | R0 e R1 | **Não executada e não autorizada.** Nenhuma chamada externa foi feita. Autorizada na seção 10 e executada no fechamento — ver seção 11. |
| `make check` | Fechamento (2026-08-17) | **Exit 0.** `ruff check`, `ruff format --check`, `mypy` estrito (173 arquivos, sem problemas), `check_docs` (113 arquivos Markdown), `schema_export --check`, `contracts:check`, builds de `@croquito/web` e `@croquito/medicao`, `terraform fmt -check`. **Fecha o achado E3.** |
| Reconferência das 34 chaves | Fechamento (2026-08-17) | Script de comparação contra **dois** alvos: `git show a92fda7:docs/product/ROADMAP.md` (commit base) e o `ROADMAP.md` do HEAD. Zero divergência nos dois; numeração 1–34 única; o roadmap tem exatamente 34 bullets de nível 0 nas seções de conteúdo; distribuição 21 `PLANEJADO` / 5 `EM OPERAÇÃO/HOMOLOGAÇÃO` / 4 `EXCLUÍDO` / 3 `IMPLEMENTADO` / 1 `UNKNOWN`. |

## 7. Revisão da rodada R0

Revisão independente conduzida sob o contrato global do Reviewer, em modo somente leitura.
Resultado: **`REVIEW_EVIDENCE_INCOMPLETE`** — estado que tem precedência sobre conclusão
final de revisão de código quando falta evidência mínima. Preservada aqui com atribuição;
o desfecho de cada achado em R1 é declarado na última coluna.

### Achados de evidência

| ID | Severidade | Achado | Desfecho em R1 |
| --- | --- | --- | --- |
| E1 | BLOCKER | `BUILD REPORT` de R0 ausente: nenhum `PRIMARY_EXECUTION_EVIDENCE` para F001-T01/T02/T03 | **Fechado por decisão humana**: R0 declarado irrecuperável; o `BUILD REPORT` de R1 é a evidência primária |
| E2 | HIGH | `evidence.md` inexistente, contrariando [docs/features/README.md](../README.md) e o Project Context | **Fechado**: criado nesta rodada por autorização humana explícita |
| E3 | MEDIUM | `make check` de F001-T03 sem resultado registrado | **Fechado para R1**; permanece sem evidência para R0, e assim registrado |
| E4 | MEDIUM | Aprovações humanas afirmadas no `plan.md` sem registro acessível no repositório | **Fechado a partir de R1**: a autorização de 2026-08-17 está na seção 2 |

### Achados de código

| ID | Severidade | Achado | Desfecho em R1 |
| --- | --- | --- | --- |
| C1 | MEDIUM | Item 18 (`Composição própria…`) classificado `PLANEJADO` com evidência auto-referente, contradizendo ADR-0027 e o M8 citados na mesma tabela; a chave truncada suprimira “como caminho de escrita” | **Fechado**: chave verbatim restaurada; evidência passa a citar ADR-0027 e `STATUS.md`; a observação declara o que o M8 entregou e por que o escopo do bullet completo segue não entregue |
| C2 | MEDIUM | Item 24 (`Cascata configurável…`) no mesmo padrão; a chave suprimira “cada fonte com importador próprio” | **Fechado**: chave verbatim restaurada; a observação declara a cascata e o importador EMOP entregues no M8 e registra que SINAPI, SICRO e demais fontes seguem sem importador |
| C3 | LOW | Item 22 (`UI web de revisão da medição`) `PLANEJADO` sem distinguir o `apps/medicao` entregue no M6 | **Parcialmente fechado**: chave verbatim restaurada e observação factual acrescentada (ponte descartável, ADR-0020/ADR-0026, migração para `/v1`). Se o M6 já satisfaz o bullet é **decisão humana pendente** — ver seção 9 |
| C4 | MEDIUM | Reconciliação GCP não registrava a afirmação documental de `HML.md` (“O que está no ar”) | **Fechado**: reconciliação reescrita em três eixos, com a afirmação documental citada nominalmente e o estado remoto declarado não verificado |
| C5 | LOW | Vocabulário de classificação sem definição publicada | **Fechado**: seção “Vocabulário de classificação” no roadmap, conferida contra as 34 linhas sem reclassificar |
| C6 | LOW | Itens 12–16 usavam a chave abreviada “Medição de obra /” | **Fechado**: título exato `Agora — medição de obra (contexto valuation, v1 em marcos)` restaurado |

### Causa raiz registrada

O truncamento dos bullets no inventário congelado de R0 foi a causa comum de C1, C2, C3 e
C6: o qualificador suprimido era exatamente o que delimitava o escopo classificado. Regra
derivada, registrada em `plan.md`: **o congelamento só é válido verbatim.**

## 8. FINAL

Ao fim de R1, `git status --short --branch` sobre o commit `a92fda7` mostra apenas:

- `docs/product/ROADMAP.md` (modificado; `git diff --stat` acumulado de R0 e R1:
  83 inserções, nenhuma remoção);
- `docs/features/F-001-roadmap-clarification/feature.md`, `plan.md` e `evidence.md`
  (não rastreados).

Nenhum commit, nenhuma mudança em `docs/STATUS.md`, ADRs, código, `infra/` ou workflows.
F-001 permanece `IN_PROGRESS`, aguardando aprovação humana.

> Esta seção é o registro do estado **ao fim de R1**, preservado como executado. O estado atual
> da feature é o do topo deste documento; a linha do roadmap que ainda dizia `IN_PROGRESS` foi
> corrigida no fechamento (seção 11).

## 9. Desvios, riscos e decisões humanas pendentes

### Desvios do plano original

- `evidence.md` estava fora de escopo em R0 e passou a estar em escopo em R1 — desvio
  autorizado, registrado na seção 2.
- A tarefa `F001-T04` não existia no plano aprovado em R0; foi acrescentada nesta rodada
  para descrever a correção autorizada.

### Riscos remanescentes

- A evidência de execução de R0 é definitivamente perdida; a rastreabilidade daquela rodada
  depende do `git diff` e da revisão preservada aqui.
- As chaves dos itens 12 a 16 são longas por serem verbatim; futuras edições no roadmap
  precisam atualizar bullet e chave juntos, ou o inventário deixa de refletir a fonte.
- O inventário é um retrato de 2026-08-17 sobre o commit `a92fda7`; entrega nova em
  qualquer marco envelhece as observações.

### Decisões humanas pendentes

1. Aprovar ou rejeitar o inventário corrigido e a reconciliação de ambientes.
2. Decidir se o `apps/medicao` entregue no M6 satisfaz o item 22 do inventário (C3).
3. Decidir o próximo estado de F-001 (`IN_PROGRESS` → `READY_FOR_REVIEW` ou `DONE`).
4. Selecionar, se for o caso, qualquer item `PLANEJADO` para um Feature Contract próprio —
   nenhum agente pode fazê-lo.
5. Autorizar, se desejado, uma verificação de estado remoto do ambiente GCP pelos comandos
   de smoke de [HML](../../operations/HML.md); sem ela, o eixo “estado remoto verificado”
   permanece vazio por construção.

## 10. Decisão humana de 2026-08-17

O responsável pelo produto decidiu, nesta data, as cinco pendências registradas na seção 9.
As decisões abaixo são o ato humano que a seção 9 aguardava; elas não alteram o conteúdo das
rodadas R0 e R1, que permanecem preservadas acima como executadas.

| # | Pendência da seção 9 | Decisão |
| --- | --- | --- |
| 1 | Aprovar ou rejeitar o inventário corrigido e a reconciliação de ambientes | **Aprovados.** |
| 2 | O `apps/medicao` entregue no M6 satisfaz o item 22 do inventário (achado C3) | **Não satisfaz.** O item 22 permanece `PLANEJADO`. Fundamento declarado: o [ADR-0026](../../adr/0026-medicao-hospedada-sessao-autenticada-minima.md) trata o modo hospedado como dívida com data e o `AGENTS.md` de `apps/medicao` declara o client descartável. A UI definitiva pertence a [F-003](../F-003-medicao-v1-migration/feature.md). |
| 3 | Próximo estado de F-001 | **`DONE` após o registro da validação.** Ver "Condição restante" abaixo. |
| 4 | Selecionar item `PLANEJADO` para Feature Contract próprio | **Selecionada** a migração da medição para a API `/v1`, decomposta em [F-002](../F-002-medicao-v1-contract/feature.md) e [F-003](../F-003-medicao-v1-migration/feature.md). O piloto do primeiro ciclo Planner → Builder → Reviewer é [F-005](../F-005-openapi-contract-test/feature.md). |
| 5 | Autorizar verificação de estado remoto do ambiente GCP | **Autorizada**, a ser executada em trabalho próprio pelos comandos de smoke de [HML](../../operations/HML.md). Não é pré-requisito de F-001: enquanto não ocorrer, o eixo "estado remoto verificado" da reconciliação permanece vazio por construção, e assim declarado. |

### Condição restante para `DONE`

O achado E3 da seção 7 continua sem resultado registrado: `make check` não foi executado com
registro nesta feature. A [Definition of Done global](../../../AGENTS.md) não permite declarar
conclusão sem evidência determinística, e a decisão humana não substitui essa evidência.

F-001 passa a `DONE` quando `make check` for executado sobre o estado desta rodada e seu
resultado for registrado aqui, com a baseline aplicável. Até então o estado é
`READY_FOR_HUMAN_REVIEW` com a decisão humana já registrada.

### Consequência para o roadmap

A decisão 4 autoriza a criação de entradas de backlog com ID estável no roadmap canônico. Essa
alteração é trabalho subsequente e **não** entra no diff de F-001, para não misturar escopos no
mesmo commit de `docs/product/ROADMAP.md`.

## 11. Fechamento em 2026-08-17

### Condição restante cumprida

`make check` foi executado e registrado na seção 6, com exit 0. Isso fecha o achado E3, que era a
única condição declarada para `DONE`.

A execução é sobre o commit `cbb1fab`, e não sobre o worktree de R1 — a diferença está declarada
porque importa. O que a torna aplicável a F-001 é verificável: `git diff beb59db..HEAD` sobre
`docs/features/F-001-roadmap-clarification/` é **vazio** (os três artefatos estão intocados desde
o commit da feature), e no `ROADMAP.md` a única alteração posterior está na seção "Trabalho de
engenharia em andamento", que o inventário declara explicitamente fora do congelamento. A
reconferência das 34 chaves contra o roadmap do HEAD, registrada na seção 6, prova isso de forma
independente.

### `SOURCE_OF_TRUTH_CONFLICT` resolvido

`docs/product/ROADMAP.md` declarava F-001 como `IN_PROGRESS` enquanto o `feature.md` declarava
`READY_FOR_HUMAN_REVIEW` — conflito entre as duas fontes que o
[Project Context](../../engineering/PROJECT_CONTEXT.md) manda resolver por decisão humana. A
decisão 3 da seção 10 já continha a resposta; o roadmap passa a `DONE` junto com o contrato.

### Verificação de estado remoto executada (decisão 5)

A "Fumaça manual" de [HML](../../operations/HML.md) foi executada em **2026-08-17T20:40Z**, contra a
borda pública, sem credencial e sem `gcloud`. Só código HTTP é registrado — nenhum corpo de
resposta, nenhum token, nenhuma URL assinada:

| Rota | Resultado |
| --- | --- |
| `GET /api/healthz` | **404** |
| `GET /auth/realms/croquito/.well-known/openid-configuration` | **503** |
| `GET /revisao/` | 200 |
| `GET /medicao/` | 200 |

As duas falhas foram reexecutadas com timeout maior e se repetiram, então não são partida a frio.

**Alcance do que isso prova.** O smoke observa a borda pública, que é o nginx. Rota que responde
200 prova que o proxy e a SPA correspondente estão de pé; ela não prova estado interno de Cloud
Run, buckets, Pub/Sub ou PostgreSQL, que continuam **não verificados**. O `croquito-jobs-hml` não
tem fumaça externa por construção.

**Divergência registrada, não corrigida.** A seção "O que está no ar" do
[HML](../../operations/HML.md) afirma no presente que a API e o Keycloak estão em operação. O
estado verificado contradiz a afirmação em dois pontos: `/api/healthz` responde 404 — comportamento
compatível com o problema de borda já conhecido do ambiente — e o endpoint de descoberta OIDC
responde 503, o que significa que **a sessão autenticada de homologação não sobe hoje**. Corrigir o
ambiente ou o documento é trabalho próprio, com decisão humana: F-001 registra o fato e não o
resolve, exatamente como seu contrato exige.
