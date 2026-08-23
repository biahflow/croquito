# F-035 — Evidência de execução

feature_id: F-035
status: `READY_FOR_HUMAN_REVIEW`
data: 2026-08-23

## 1. Gates humanos

| Gate | Estado |
| --- | --- |
| Seleção | Exercida em 2026-08-22 |
| **ADR-0046** | **Aceito por ato humano em 2026-08-22** ([ADR-0046](../../adr/0046-aprovacao-do-orcamento-base.md), `Accepted`) |
| **Design Approval Package** | **Aprovado por ato humano em 2026-08-22**, revisão 1 ([mock/README.md](mock/README.md)) |
| Papel `aprovador` atribuído em HML | **Pendente** — ato humano |
| Merge e deploy | **Pendente** |
| Ato nominal sobre orçamento real | **Pendente** — ato do usuário, pós-deploy |

A **copy** das telas novas segue fora da aprovação da revisão 1, por declaração do registro.

## 2. Baseline

`make check` e `make test` verdes antes da primeira mudança. Nenhuma falha preexistente.

## 3. Tasks

Quatro tasks. O `BUILD REPORT` de cada uma é a evidência primária da sua execução e foi
preservado na sessão de orquestração; o resumo abaixo não o substitui.

| Task | Entrega | Executor | Status |
| --- | --- | --- | --- |
| T1 | Aprovação no domínio, portão próprio sem contrato, demo assinada, goldens | `implementador-opus` | `BUILD_COMPLETE` |
| T2 | Migração `0015`, três rotas, papel `aprovador`, realms | `implementador-opus` | `BUILD_COMPLETE` |
| T3 | Etapa "Aprovação e despacho" na jornada | `implementador-opus` | `BUILD_COMPLETE` |
| T4 | e2e novo e os dois existentes ajustados | `implementador-opus` | `BUILD_COMPLETE` |

## 4. Validação integrada

Executada pelo revisor no checkout completo, **com a árvore parada** — as três últimas tasks
correram em paralelo e uma delas mediu falhas de árvore em movimento, o que só o
fechamento com tudo quieto resolve:

```text
make check                    → exit 0
make test                     → exit 0  (pytest 2340 passed / 10 skipped;
                                         vitest web 1065; vitest field 261)
make valuation-estimate-demo  → exit 0
```

Durante a revisão de cada task, executados de forma independente do relatório do executor:
`ruff`, `mypy strict`, `tests/valuation/`, `tests/api/`, `tests/e2e/` e a auditoria de
guarda de papel descrita em §6.

A T2 executou o gate de migrations contra **PostgreSQL real** (*skipped* por padrão), 12/12.

## 5. Quebra de contrato declarada

`POST /v1/estimate-rounds/{id}/estimate` **deixou de publicar** a planilha. O snapshot de
OpenAPI tem diff de **mudança**, não só de adição — é a quebra, e ela é visível por
construção. O único consumidor era `apps/web`, entregue na T3.

Consequência para dados já existentes, apurada na revisão e **não** declarada no ADR:

- **`schema_version` subiu para `2.2.0`** (`Literal`), então `estimate_json` gravado antes
  não revalida e a leitura devolve `422`. Precedente: a
  [F-026](../F-026-importadores-sinapi-sicro/feature.md) fez o mesmo bump (`081967a`) e foi
  ao ar assim.
- **`estimate_built_by` fica nulo** em revisões anteriores, e a rota de aprovação recusa
  fechado (`ESTIMATE_APPROVAL_AUTHOR_UNKNOWN`) em vez de assumir quem montou.

**Em conjunto: orçamento montado antes do deploy precisa ser remontado** para voltar a abrir
e para poder ser assinado. Remontar é ato normal da jornada.

## 6. Achados da revisão linha a linha

Feita pelo modelo da sessão, relendo o diff e re-executando os portões.

1. **Auditoria independente da separação de papéis.** O maior risco da feature era afrouxar
   uma mutação ao dar leitura ao papel novo. Percorri as 24 rotas do orçamento no código e
   mapeei a guarda de cada uma: **10 leituras** com os dois papéis, **13 mutações** só
   `orcamentista`, **1** só `aprovador`. Nenhuma mutação com guarda de leitura.

2. **Erro meu no contrato, corrigido pelo executor.** O Task Contract da T2 dizia "11
   leituras e 11 mutações"; a superfície real é 10 e 12 (14 com as rotas novas). O executor
   apurou e reportou em vez de seguir o número errado.

3. **Ordem do portão conferida no código**: `require_document` → revalida →
   `ensure_exportable()` → `render_estimate_workbook` → `write_object` → `append_revision`.
   O portão vem antes de qualquer escrita, inclusive do arquivo temporário.

4. **Reconstrução de arquivo verificada.** A T3 rodou `prettier` num repositório que não o
   usa, reformatou trechos alheios e reconstruiu os dois arquivos maiores a partir do
   `HEAD`. Conferi comparando `git diff` com `git diff -w`: as 14 linhas que diferem só em
   espaço são **reindentação legítima** (JSX que ganhou um nível de aninhamento), não
   resíduo. O executor reportou o incidente por conta própria.

5. **Asserções invertidas, não apagadas.** A T4 podia ter removido
   `workbook_present is True` para os testes passarem; inverteu para `is False` na montagem
   e afirmou a publicação depois do despacho, acrescentando a prova de que o digest de
   conteúdo é o mesmo da montagem ao despacho.

6. **Acima do contrato, mantido**: a recusa de auto-aprovação **não devolve quem montou** —
   "devolver o subject de outra pessoa transformaria uma recusa de autorização num diretório
   de usuários do tenant". E a T2 escreveu um **teste de drift de superfície**: o conjunto
   de rotas enumerado pelos testes de papel tem de ser igual ao da aplicação, então rota
   nova que nasça fora deles quebra o build.

## 7. Divergências do pacote de design

Cinco, registradas em [mock/README.md](mock/README.md). Quatro têm a mesma raiz — **o mock
desenhou dado que nenhuma rota devolve**, e a tela mostra o estado sem ele em vez de
inventá-lo: o nome de quem montou (omitido de propósito, por segurança), o instante do
despacho, o progresso parcial dos quatro passos que correm numa chamada só.

A quinta é diferente e vale registro: **a tela 7 desenha o botão de aprovar já desabilitado**,
o que exigiria a SPA decidir autorização — contra o critério 7 do próprio contrato. Era
inconsistência interna do pacote, resolvida do lado da regra: o botão é oferecido, e o `403`
do servidor vira o painel que nomeia o papel que falta.

## 8. Disciplina de mudança

| Documento | O que mudou |
| --- | --- |
| `docs/architecture/API_CONTRACT.md` | Três rotas; **removida** a frase que declarava que aprovação não existe deste lado da fronteira |
| `docs/product/FDD.md` | Seção "O orçamento é assinado antes de sair" |
| `docs/product/ACCEPTANCE_CRITERIA.md` | `VAL-11` |
| `docs/product/CADEIA_OPERACIONAL.md` | **Etapa 9 deixou de ser "ato humano, fora do produto"**; a lacuna 3 passa a nomear só 7, 10, 11 e 14 |
| `docs/engineering/TRACEABILITY.md` | Linha do `VAL-11` |
| `docs/adr/README.md` | ADR-0046 `Accepted` |

## 9. Riscos remanescentes

- **Orçamento antigo precisa ser remontado** (§5).
- **Sem ninguém com `aprovador` em HML, nenhum orçamento é despachável.** O papel entrou nos
  dois realms e o local ganhou um usuário; atribuir em HML é ato humano.
- **Auto-aprovação recusada em operação de uma pessoa só** — consequência aceita no
  ADR-0046. A saída é atribuir o papel a outra pessoa, não afrouxar o código.
- **`apps/web/AGENTS.md` e `FLUXO_DO_SISTEMA.md`** ainda descrevem a etapa "Planilha".
  Apontado pela T3; fica nomeado, não silencioso.

## 10. Decisões humanas pendentes

1. **Confirmar os dois códigos de recusa criados na execução**, que o contrato não fixava:
   `ESTIMATE_SELF_APPROVAL_FORBIDDEN` → `403` e `ESTIMATE_APPROVAL_AUTHOR_UNKNOWN` → `409`.
2. **Confirmar que orçamento montado antes do deploy será remontado** em vez de migrado.
3. **Confirmar as cinco divergências do pacote de design** (§7), em especial se a tela 7
   deve mesmo ficar sem o botão desabilitado — mudar isso exigiria passar os papéis da
   sessão para a jornada e faria a SPA decidir autorização.
4. Atribuir `aprovador` a alguém no realm de HML.
5. Merge, deploy e a migração `0015` no hospedado.
