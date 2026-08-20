# T7 — BUILD REPORT

feature_id: F-020
task_id: T7
harness: Claude Code (implementador delegado)
branch: f-020-t7-acabamento (worktree `/Users/danielcampos/workspace/daniel/croquito-r2`)

## Baseline

`make setup` (worktree novo, sem `.venv`/`node_modules`) seguido de `make check` e
`make test`, ambos executados ANTES de qualquer edição:

- `make check`: verde (ruff check, ruff format --check, mypy strict, check_docs, drift de
  contratos, `web:check` — tsc + vite build, `infra-check`).
- `make test`: verde — `uv run pytest` **1695 passed, 13 skipped**; `npm run web:test`
  **693 passed** (39 arquivos).

Nenhuma falha preexistente identificada nesta árvore.

## BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
- `services/api/src/croquito_api/estimate_rounds.py` — funções de domínio da remoção:
  `removed_cascade` (permutação menos uma fonte, reusa `cascade_order_invalid` /
  `ESTIMATE_CASCADE_ORDER_INVALID` para digest desconhecido) e
  `require_cascade_source_unlocked` (trava `ESTIMATE_CASCADE_LOCKED` por FONTE citada em
  `CodeAssignment.catalog_sha256`, não pela cascata inteira como a reordenação).
- `services/api/src/croquito_api/main.py` — modelo `RemoveEstimateCascadeSourceRequest`
  (`base_version` + `source_sha256` validado por `SHA256_HEX_PATTERN`) e rota nova
  `POST /v1/estimate-rounds/{round_id}/catalogs/remove`, espelhando
  `reorder_estimate_cascade` (papel, idempotência, `base_version`, auditoria
  `ESTIMATE_CASCADE_SOURCE_REMOVED`).
- `services/worker/src/croquito_worker/valuation/cli.py` — `_bdi_percent_type` (conversor
  `argparse` que troca `decimal.InvalidOperation` cru por `ArgumentTypeError` amigável em
  pt-BR); `--bdi` do `build-estimate` passa a usar esse conversor em vez de `type=Decimal`;
  `_estimate_payload` ganha `bdi_percent` e `total_amount_without_bdi` (strings) no resumo
  JSON impresso pelos comandos `build-estimate` e `estimate-demo`.
- `apps/web/src/orcamento/api.ts` — tipo `CascadeRemoveDraft` e função `removeCascadeSource`
  (`POST .../catalogs/remove`), mesmas invariantes de `reorderCascade`
  (`base_version`, `Idempotency-Key`).
- `apps/web/src/orcamento/requests.ts` — `cascadeRemoveBody` (corpo mínimo: `base_version` +
  `source_sha256`).
- `apps/web/src/orcamento/OrcamentoApp.tsx` — handler `removerFonte` e botão "Remover" por
  entrada da cascata, ao lado de "Subir"/"Descer"; desabilitado por `submitting` e pela
  mesma flag `cascataTravada` (`assignments_present`) que já desabilita a reordenação — uma
  simplificação consciente (ver Desvios).
- `docs/architecture/API_CONTRACT.md` — entrada da rota nova, no padrão das vizinhas
  (`catalogs/order`, `plate`).
- `tests/api/test_estimate_round_routes.py` — 6 testes novos da rota de remoção + 1 entrada
  na lista de rotas do teste `test_sem_o_papel_toda_rota_recusa_antes_do_lookup` (403 sem
  papel).
- `tests/valuation/test_estimate.py` — 1 teste novo de CLI (`--bdi abc`) + asserts novos no
  teste feliz existente (`bdi_percent`/`total_amount_without_bdi` no payload).
- `apps/web/src/orcamento/api.test.ts` — 1 teste novo (`removeCascadeSource`: URL, corpo,
  `Idempotency-Key`).
- `apps/web/src/orcamento/requests.test.ts` — 1 teste novo (`cascadeRemoveBody`).
- `tests/api/openapi.snapshot.json` — regenerado por `make openapi-snapshot`; diff só de
  adição (97 inserções, 0 remoções): schema `RemoveEstimateCascadeSourceRequest` e path
  `/v1/estimate-rounds/{round_id}/catalogs/remove`.

Testes novos e o que cobrem:
- `test_remocao_encolhe_a_cascata_e_avanca_a_versao` — caminho feliz: cascata encolhe,
  `version` avança, posição da fonte restante recalculada.
- `test_remocao_sem_idempotency_key_recusa` — `400 IDEMPOTENCY_KEY_REQUIRED`.
- `test_remocao_com_base_version_velha_recusa` — `409 REVISION_CONFLICT`.
- `test_remocao_de_digest_desconhecido_recusa` — `422 ESTIMATE_CASCADE_ORDER_INVALID`
  (código reusado da reordenação).
- `test_remocao_de_fonte_citada_por_decisao_recusa` — `409 ESTIMATE_CASCADE_LOCKED` quando a
  fonte removida foi citada por uma decisão de código registrada; cascata intocada.
- `test_remocao_de_fonte_nao_citada_e_permitida_mesmo_com_decisao_registrada` — prova que a
  trava é por FONTE, e não pela cascata inteira: remover uma fonte que nenhuma decisão citou
  é permitido mesmo com decisão registrada em outra fonte da mesma rodada.
- `test_cli_build_estimate_refuses_an_unreadable_bdi_without_traceback` — `--bdi abc` termina
  com `SystemExit(2)`, mensagem amigável no stderr, sem `Traceback`.
- Asserts novos em `test_cli_build_estimate_publishes_the_estimate` — `bdi_percent` e
  `total_amount_without_bdi` presentes e corretos no resumo JSON.
- `removeCascadeSource` em `api.test.ts` — URL, corpo mínimo, `Idempotency-Key` presente.
- `cascadeRemoveBody` em `requests.test.ts` — corpo é só `base_version` + `source_sha256`.

Validation executed (todos verdes, saída resumida):
- `make check` — ruff check/format, mypy strict (194 arquivos), `check_docs.py` (241
  Markdown após a entrada nova no API_CONTRACT), drift de contratos (`schema_export
  --check-dir`, `contracts:check`), `web:check` (tsc -b + vite build), `infra-check`
  (`terraform fmt -check`).
- `make test` — `uv run pytest`: **1702 passed, 13 skipped** (era 1695/13; +7 testes
  Python); `npm run web:test`: **695 passed** em 39 arquivos (era 693; +2 testes web).
- `uv run pytest tests/api/test_estimate_round_routes.py -x -q` — **32 passed** (era 26;
  +6 da remoção).
- `npm --workspace @croquito/web run test` — **695 passed** (mesmo total do `make test`).
- `make valuation-estimate-demo` — `exit 0`; resumo JSON confere `bdi_percent="25.00"` e
  `total_amount_without_bdi="57221.26"` publicados.
- `make openapi-snapshot` — diff em `tests/api/openapi.snapshot.json` é só de ADIÇÃO (97
  inserções, 0 remoções): schema `RemoveEstimateCascadeSourceRequest` + path
  `/v1/estimate-rounds/{round_id}/catalogs/remove`.
- Verificação manual: `croquito-valuation build-estimate ... --bdi abc ...` → stderr
  `error: argument --bdi: 'abc' não é um número decimal exato; escreva o BDI como 25.00`,
  `exit=2`, sem traceback.

Validation skipped: none.

Unavailable capabilities: none.

Assumptions:
- "Fonte citada por QUALQUER decisão de código registrada" foi interpretado como
  `CodeAssignment.catalog_sha256` (a citação POR ITEM que `build_worksite_estimate_codes`
  grava em cada assignment confirmado), não o `catalog_sha256` de CABEÇA de
  `CodeAssignmentSet` (que é sempre `cascade[0].source_sha256`, fixo, e não identifica qual
  fonte cada linha usou). Essa leitura é a única que torna a trava por FONTE (e não pela
  cascata inteira) fisicamente possível — confirmado lendo `assignment.py`
  (`ASSIGNMENT_CATALOG_REQUIRED`/`ASSIGNMENT_CATALOG_UNKNOWN`, onde cada assignment
  confirmado é obrigado a citar a fonte específica quando há mais de uma na cascata).
- Código de "fonte desconhecida na cascata" na remoção reusa
  `ESTIMATE_CASCADE_ORDER_INVALID` (via o helper já existente `cascade_order_invalid`): não
  existe, no módulo, um código dedicado a "digest não está entre as fontes instaladas"
  separado de "corpo não é a permutação esperada" — a própria reordenação usa o mesmo código
  para as duas causas (repetição e digest desconhecido). Por isso nenhum código novo foi
  criado e nenhuma tradução nova foi acrescentada em `labels.ts` (a tradução de
  `ESTIMATE_CASCADE_ORDER_INVALID` já existe e é reusada).
- O botão "Remover" na web usa a MESMA flag grosseira `cascataTravada`
  (`state.codes.assignments_present`) que já desabilita "Subir"/"Descer", em vez de replicar
  no cliente a checagem fina por fonte que a API faz. `round_state_payload` não expõe, hoje,
  qual fonte cada assignment citou — só a presença agregada — então o cliente não tem como
  calcular a checagem fina sem um campo novo no estado da rodada (fora do escopo do
  contrato, que não pede mudança de schema). Consequência: a UI desabilita "Remover" em TODA
  fonte quando QUALQUER decisão existe, mesmo quando a fonte específica não foi citada — mais
  conservador que a API (que permitiria remover uma fonte não citada mesmo com decisões
  registradas, como o teste `test_remocao_de_fonte_nao_citada_e_permitida_mesmo_com_decisao_registrada`
  prova). A API continua sendo a autoridade final; a UI só é mais cautelosa no que oferece
  clicar.

Remaining risks:
- A simplificação acima (botão desabilitado por `cascataTravada` agregado) significa que uma
  orçamentista não consegue remover, pela tela, uma fonte não citada depois de a primeira
  decisão de código ser registrada — mesmo sendo uma operação que a API aceitaria. Não é
  regressão (nenhuma tela antes oferecia remoção), mas é uma limitação de UX que só um campo
  novo no estado da rodada resolveria; registrado como oportunidade não implementada abaixo.
- Mensagem de erro que a tela mostra quando a API recusa por `ESTIMATE_CASCADE_LOCKED` na
  remoção reaproveita o texto genérico já existente ("reordenar a cascata invalidaria...");
  como `errorMessage()` acrescenta o `detail` do servidor entre parênteses quando ele diverge
  do texto conhecido, o resultado prático é a frase de reordenação seguida do detail correto
  da remoção entre parênteses — funcional, mas levemente redundante. Não alterado por estar
  fora do escopo do contrato (que só pediu "confira" a tradução existente).

Human decisions required: none — mudança é aditiva, comportamento novo coberto por teste,
nenhum guardrail de produção/infra/dados tocado.

## Desvios conscientes do spec

1. Guarda de bloqueio da remoção implementada por FONTE citada (via
   `CodeAssignment.catalog_sha256` por item), não como cópia literal de
   `require_cascade_unlocked` (que bloqueia pela mera EXISTÊNCIA de qualquer decisão). Isso é
   exatamente o que o contrato pediu explicitamente ("a remoção deve trancar quando o
   `code_assignments_json` da cabeça citar o catálogo removido"), documentado para deixar
   claro que não é um desvio silencioso da semântica de `require_cascade_unlocked` — é uma
   nova função (`require_cascade_source_unlocked`) desenhada para essa semântica mais fina,
   com teste dedicado provando os dois lados (trava quando citada, não trava quando não
   citada).
2. Nenhum código de erro novo foi criado (nem em `estimate_rounds.py` nem em `labels.ts`):
   `ESTIMATE_CASCADE_ORDER_INVALID` foi reusado para "digest desconhecido", seguindo à risca
   a instrução do contrato de verificar reuso antes de criar.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- Expor no `round_state_payload`/`EstimateState` qual fonte cada `CodeAssignment` confirmado
  citou (ou ao menos o conjunto de `catalog_sha256` citados), permitindo à web calcular a
  trava fina por fonte no cliente e habilitar "Remover" de fontes não citadas mesmo com
  decisões registradas em outras. Envolveria mudar o contrato/schema do estado da rodada —
  explicitamente fora de escopo ("Qualquer mudança de schema do `Estimate`... nada de `make
  contracts`" e o contrato não pede mudança em `round_state_payload`).
- Ajustar o texto de `ESTIMATE_CASCADE_LOCKED` em `labels.ts` para ser neutro entre
  "reordenar" e "remover" (hoje menciona só "reordenar"). O contrato pediu apenas "confira"
  a tradução existente, não pediu editá-la; o `detail` do servidor já complementa a frase
  entre parênteses quando diverge.
- Recomputar a shortlist automaticamente após uma remoção — explicitamente fora de escopo no
  contrato ("a rota de recompute já existe e segue sendo ato explícito").
