# F-033 — Evidência de execução

feature_id: F-033
status: `READY_FOR_HUMAN_REVIEW`
data: 2026-08-22

## 1. Gates humanos, ambos cumpridos antes do planejamento

| Gate | Como foi cumprido |
| --- | --- |
| `ARCHITECTURE_DECISION_REQUIRED` | [ADR-0045](../../adr/0045-terceiro-estado-demanda-sob-contrato.md), `Accepted` por ato humano em 2026-08-22 |
| `DESIGN_APPROVAL_REQUIRED` | [Design Approval Package](mock/README.md), revisão 1, aprovado por ato humano em 2026-08-22 |

A **copy** foi aprovada em ato separado e posterior, depois de a tela existir — o registro de
aprovação da revisão 1 a excluía explicitamente. As divergências entre a revisão 1 e o que foi
construído estão registradas em [mock/README.md](mock/README.md), inclusive a mais importante:
a dica da tela 2 prometia trocar de regime, ato que a decisão de **mão única** — tomada
**depois** da aprovação — tornou impossível.

## 2. Baseline

Árvore limpa na `main` antes de cada task. Portões verdes antes e depois; nenhuma falha
preexistente foi atribuída a esta feature, e nenhuma foi introduzida.

## 3. Execução

| Task | Executor | Resultado |
| --- | --- | --- |
| T1 — regime no servidor | `implementador-opus` | `BUILD_COMPLETE`; revisão linha a linha **sem defeito encontrado** |
| T2 — selo e candidato na tela | `implementador-opus` | `BUILD_COMPLETE`; revisão confirmou o achado do próprio executor (texto invisível) |
| e2e da cadeia sob o regime | `implementador-sonnet` | `BUILD_COMPLETE`; asserção conferida linha a linha |

### O que a revisão do modelo principal apurou

- **T1**: nenhum defeito. Confirmei a ordem das recusas (o valor antes da cascata, senão a
  mesma tentativa devolveria códigos diferentes conforme o que estivesse instalado), a
  migração aditiva e forward-only, e que o único chamador de `ensure_source_installable`
  recebe o regime por parâmetro **sem default** — para chamador novo não herdar cascata livre
  em silêncio.
- **T2**: o executor relatou que o status da decisão de código era invisível. **Verifiquei em
  vez de aceitar**: `.topbar-meta` é `rgba(242,244,247,.72)` e `.painel` é `#ffffff` —
  contraste de ~1,05:1. Defeito preexistente, e é justamente o texto que passa a dizer
  "candidato a aditivo": sem corrigir, o sinal central da feature nasceria invisível. A
  correção muda a veste também na rodada **sem** regime, desvio consciente do critério "tela
  idêntica à de hoje", aprovado por ato humano.

## 4. Verificação

| Portão | Resultado |
| --- | --- |
| `make check` | verde (ruff, mypy strict, check_docs, drift de contratos, build web, terraform fmt) |
| `make test` | verde — pytest completo e vitest |
| `npm --workspace @croquito/web run test` | 947 passed |
| `uv run pytest tests/e2e/test_estimate_rounds_v1.py` | 3 passed, incluindo a cadeia sob o regime |
| `tests/api/test_migrations.py` com PostgreSQL real | 12 passed, incluindo o drift `migração × Base.metadata` com a `0009` |

### Verificação fora dos testes

- **Contra a API no ar**: rodada criada sob o regime traz o bloco no estado; voltar para
  pré-licitação recusa com `409 ESTIMATE_REGIME_IRREVERSIBLE`.
- **Contra o produto no ar, com login real** (`orcamentista.local` pelo Keycloak): o seletor
  de jornadas mostra só Medição e Orçamento, e a rodada sob o regime abre com o selo e o
  aviso. Captura conferida contra a revisão 1 aprovada.

## 5. Critérios de aceite

| # | Critério | Onde |
| --- | --- | --- |
| 1 | `make check` e `make test` verdes; goldens intocados | seção 4 |
| 2 | Rodada sem regime idêntica a hoje | testes de rota + `OrcamentoApp.test.tsx` |
| 3 | Sob o regime, `sco` instala e as quatro outras recusam sem mudar a cascata | `test_sob_o_regime_so_a_tabela_contratual_instala` |
| 4 | Declarável na abertura e depois, com `base_version` e `Idempotency-Key` | testes de rota |
| 5 | Cadeia inteira sob o regime chegando à planilha com todas as linhas citando `sco` | `test_estimate_round_contracted_demand_regime_through_v1_api` |
| — | Tela corresponde à revisão aprovada | conferida com a folha real e com login real |

## 6. Desvios de plano

`PLAN_DEVIATION` do escopo: o plano previa "reusar `build_amendment_dossier`". O
levantamento apurou que **chamá-lo seria errado** — ele exige decisão de código em todo item
confirmado, por ser artefato de fechamento, e o sinal apareceria só no fim, que é o atraso que
a feature combate. Reusou-se a **regra**: item rejeitado já é o candidato, e o estado já
contava `codes.rejected`. Nenhum artefato, tabela ou builder novo. O `feature.md` foi
corrigido para não induzir ao erro.

## 7. Riscos remanescentes e decisões humanas pendentes

- **A lacuna que permanece, por decisão**: restringir a origem não confere o contrato. Nada
  garante que o catálogo `sco` instalado é o da data-base e do desconto daquele contrato.
  Nomeada na decisão 6 do ADR-0045, desenhada como bloco **reservado** no pacote, e agora
  registrada como item 4 das lacunas em [CADEIA_OPERACIONAL](../../product/CADEIA_OPERACIONAL.md).
  Fechá-la exige o orçamento modelar contrato como entidade — feature própria.
- **Duas questões do pacote de design seguem em aberto** e não foram decididas pelo código:
  contador de candidatos a aditivo no cabeçalho (o número existe no estado, e a tela não o
  usa), e o resumo da etapa Códigos citar o regime.
- **Migração `0009` não aplicada em ambiente hospedado.** É ato de deploy: o job de banco a
  aplica sozinho no push, antes da API.
- **Nada publicado.** Os commits desta feature estão só na `main` local.
