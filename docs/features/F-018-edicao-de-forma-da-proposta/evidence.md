# F-018 — Evidência

Feature: [Corrigir a forma da proposta na tela, sem rerodar o provider](feature.md)  
Estado: `DONE`  
Data: 2026-08-27

## Gates humanos

| Gate | Estado |
| --- | --- |
| `ARCHITECTURE_DECISION_REQUIRED` | ✅ [ADR-0050](../../adr/0050-correcao-humana-de-forma-como-proposta-derivada.md) **aceito por ato humano em 2026-08-23** |
| `DESIGN_APPROVAL_REQUIRED` | ✅ **Aprovado por ato humano em 2026-08-27**, revisão 1 ([mock/README.md](mock/README.md)) |

## O que foi entregue

### Domínio

| Arquivo | Mudança |
| --- | --- |
| `services/worker/src/croquito_worker/vision.py` | `detector_version` ganha `human-correction-v1`; `quality_score` vira `float \| None`; `derived_from` nasce como campo aditivo com validação de formato e de repetição; o **conjunto** valida que correção humana tem origem e que proposta de máquina não tem |

O invariante das duas metades mora no conjunto porque é ele que declara quem o produziu:
correção sem origem seria desenho livre (decisão 3 do ADR), e proposta de máquina com
origem seria uma observação afirmando derivar de outra.

`precision` e `export` continuam `Literal` — a tentativa de deixar uma correção virar
`exact` não compila (decisão 5 do ADR, e a mitigação que a tabela de riscos dele nomeia).

### Persistência

| Arquivo | Mudança |
| --- | --- |
| `services/api/src/croquito_api/migrations/versions/0019_review_shape_corrections.py` | Coluna `shape_corrections_json`, aditiva e nullable, forward-only |
| `services/api/src/croquito_api/database.py` | A coluna e o porquê de ela ser separada de `proposals_json` |
| `services/api/src/croquito_api/main.py` | `_carried_field_review_context` virou `_carried_review_context` e passou a carregar as correções — os **dez** caminhos que criam revisão nova preservam o trabalho humano |

### API

`POST /v1/jobs/{job_id}/review/proposals/corrections`, documentada no
[API Contract](../../architecture/API_CONTRACT.md). Exige papel de revisão,
`Idempotency-Key`, `base_review_version` **e** `base_scene_version`. O id da correção é
determinístico para que o replay idempotente não divirja da primeira execução.

### Tela

| Arquivo | O que é |
| --- | --- |
| `apps/web/src/shapeCorrection.ts` | Rascunho puro: iniciar, unir fragmento pela ponta mais próxima, mover/inserir/remover vértice, recusa antes da rede e o derivado `propostasSuperadas` |
| `apps/web/src/shapeCorrection.test.ts` | 14 testes, incluindo o caso Guaxindiba e o fragmento declarado ao contrário |
| `apps/web/src/CroquiApp.tsx` | O terceiro ato ao lado de aceitar/rejeitar, o painel da correção, as alças no overlay e o recolhimento das superadas |
| `apps/web/src/api.ts` | `correctProposalShape`, `ShapeCorrectionDraft`, `derived_from` e `shape_corrections` no tipo da revisão |
| `apps/web/src/styles.css` | Traço próprio da correção, alça, ponto de inserção, fantasma e superada |

## Critérios de aceite

| # | Critério | Como foi verificado |
| --- | --- | --- |
| 1 | `make check` e `make test` verdes; goldens intocados | `make check` = 0, `make test` = 0 (2546 pytest, 1236 vitest web, 261 field) |
| 2 | Revisão sem edição se comporta como hoje | Nenhum caminho existente mudou de forma; a suíte inteira passa sem alteração de expectativa, exceto onde `quality_score` opcional exigiu tratar ausência |
| 3 | Editar cria proposta **nova**; a original permanece legível | `test_shape_correction_creates_new_proposal_and_preserves_the_observation` lê as duas depois da correção e confere `algorithm`, `quality_score` e `derived_from` vazio da original |
| 4 | A correção declara origem humana, autor e as propostas de que derivou | Conjunto com `detector_version = "human-correction-v1"`, `derived_from` da correção e auditoria `PROPOSAL_SHAPE_CORRECTED` |
| 5 | Unir dois fragmentos produz **uma** forma, com o caso do Guaxindiba coberto | Mesmo teste de rota (duas `line` → polilinha de 3 vértices) e `shapeCorrection.test.ts`, que cobre a costura pela ponta mais próxima |
| 6 | A forma nasce `unresolved`/`export=false` — teste **negativo** explícito | `test_shape_correction_never_promotes_precision`, que também afirma `quality_score is None` |
| 7 | Edição concorrente recusa por versão-base | `test_shape_correction_respects_optimistic_concurrency` (409 `REVISION_CONFLICT`) |
| 8 | A tela corresponde à revisão aprovada do pacote de design | Os nove estados do pacote foram implementados; ver "Limitações" para o que ficou fora |

Além dos critérios: `test_shape_corrections_accumulate_and_survive_the_next_revision`
prova que um ato qualquer da revisão (rejeitar outra proposta) **não** apaga as correções —
era o risco real de esquecer um dos dez caminhos de escrita.

## Validação de navegador/runtime

Classificação: **`BROWSER_REQUIRED`**.

O pacote de design aprovado ([mock/](mock/)) é a referência visual, e a implementação foi
escrita contra ela. A verificação renderizada do fluxo completo de arrasto **depende de uma
revisão real com propostas** e não foi executada nesta sessão: o rascunho vive sobre a
prancha de um job, e fabricar um para a captura produziria evidência de fixture, não do
fluxo. Fica declarado como pendência de aceite, não como verificado.

## Limitações e desvios declarados

- **Círculo não é corrigível.** Corrigir um círculo seria mexer em centro e raio, que não
  são vértices; a tela recusa com o motivo escrito, em vez de inventar quatro pontos.
- **A união costura pela ponta mais próxima.** É ordem de partida, não geometria decidida:
  a pessoa continua movendo os vértices depois.
- **Nenhum limiar de "vértice movido demais"** foi aplicado (Unknown 3 do contrato). O
  pacote de design registra a ausência: não existe número calibrado para separar ajuste de
  forma nova, e inventar um seria decidir sem dado.
- **A correção não é aceita no mesmo ato.** Aceitar continua exigindo calibração
  confirmada, pelo fluxo que já existe — foi desenhado como reservado no pacote.
- `quality_score` opcional é **mudança de contrato publicado**, como o ADR previu: aparece
  no diff do snapshot de OpenAPI, e os consumidores que ordenavam por ele passaram a tratar
  ausência (ordenação do detector, overlay, eval de extração e delta de refino).

## Riscos remanescentes

- O fluxo de arrasto ainda não foi exercido por uma pessoa numa revisão real; é o que o
  aceite precisa cobrir.
- Correção sobre prancha com muitas formas não teve desempenho medido.

## Integração

| Fato | Referência |
| --- | --- |
| PR mergeado na `main` | [#105](https://github.com/biahflow/croquito/pull/105), commit `80d251d` |
| `deploy-hml` da revisão | `success` em 2026-08-27, o que **aplicou a migração `0019`** no banco de homologação |
| Aceite | **ato humano de Daniel Campos, 2026-08-27** |

O PR #104 havia sido aberto contra a branch do #103, e ao ser mergeado entregou o trabalho
naquela branch em vez da `main`. O conserto foi recolher o commit a partir da `main` já com o
#103 dentro, rodar os portões de novo nessa árvore e abrir o #105. Fica registrado porque o
sintoma — dois PRs marcados `MERGED` e os arquivos ausentes da `main` — não é óbvio.

## O que o aceite NÃO cobre

- **O fluxo de arrasto nunca foi exercido numa revisão real com propostas.** Ele é o primeiro
  uso, e continua declarado como tal: nenhuma captura de tela deste repositório mostra uma
  correção feita sobre um job de verdade.
- Correção sobre prancha com muitas formas não teve desempenho medido.
