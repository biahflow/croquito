# T1 — BUILD REPORT

```text
feature_id: F-027
task_id: T1
harness: Claude Code (subagent)
```

## Status

`BUILD_COMPLETE`

Revisado pelo coordenador em uma rodada intermediária: núcleo aprovado (parse,
`target_state`, migração `0004`, estreitamento de `test_banco_anterior_ao_runner_e_carimbado`);
dois complementos pedidos e entregues nesta rodada — teto na listagem e correção
declarada da falha pré-existente de `test_migrations.py`. Este relatório já reflete o
estado final, com as três rodadas de validação consolidadas.

## Files changed

| Arquivo | Por quê |
| --- | --- |
| `services/api/src/croquito_api/database.py` | `EstimateRoundRecord` ganha `target_amount: Mapped[str \| None]` (`String(32)`, `Decimal` exato como texto) e `target_label: Mapped[str \| None]` (`String(120)`), com docstrings citando ADR-0040 — o teto é dado da rodada, nunca do `Estimate`. |
| `services/api/src/croquito_api/migrations/versions/0004_estimate_round_target.py` | **Novo.** Primeira migração incremental do repositório (`0001`-`0003` só criam tabela); dois `op.add_column` NULLABLE sobre `estimate_rounds`, escrita à mão porque `make db-revision` exige Postgres vivo, docstring no padrão da `0003` explicando o motivo e citando o gate do ADR-0029. |
| `services/api/src/croquito_api/estimate_rounds.py` | `ESTIMATE_TARGET_INVALID` (código estável); `parse_target_amount` (decimal exato, finito, **> 0**, mesmo padrão de `parse_bdi_percent`); `target_state(round_record, revision)` — o bloco `{target, consumed, remaining, over}` derivado na leitura, NUNCA persistido, NUNCA recomputando `total_amount`; splice do bloco em `round_state_payload`. |
| `services/api/src/croquito_api/main.py` | `CreateEstimateRoundRequest` ganha `target_amount`/`target_label` opcionais (validados e persistidos na criação); `SetEstimateTargetRequest` (novo modelo); rota nova `POST /v1/estimate-rounds/{round_id}/target` (papel na 1ª linha, `Idempotency-Key`, `require_base_version`, versão avança, **sem** rota de remoção); `_estimate_payload` ganha o mesmo bloco derivado via `estimate_rounds.target_state`. **Complemento desta rodada**: `EstimateRoundSummary` ganha `target_amount`/`target_label` (os dois textos crus da raiz, sem `consumed`/`over`) e `list_estimate_rounds` os popula a partir do `EstimateRoundRecord` — sem buscar a cabeça de cada rodada. |
| `docs/architecture/API_CONTRACT.md` | Documenta os campos novos de `POST /v1/estimate-rounds`, a rota nova `POST .../target`, o bloco `target`/`consumed`/`remaining`/`over` em `GET /v1/estimate-rounds/{round_id}` e nas duas rotas de `/estimate`, e (**complemento**) os dois campos crus em `GET /v1/estimate-rounds`. |
| `tests/api/openapi.snapshot.json` | Regenerado por ato deliberado (`make openapi-snapshot`) duas vezes — uma para a rota/campos originais, outra para os dois campos novos de `EstimateRoundSummary` — com diff revisado linha a linha nas duas rodadas. Só-adição nos dois casos; nenhum schema existente mudou de forma. |
| `tests/api/test_estimate_round_routes.py` | 9 testes novos (ver abaixo) + 2 testes genéricos existentes estendidos para cobrir a rota nova (403 sem papel; `POST` sem `Idempotency-Key`). |
| `tests/api/test_migrations.py` | **Dois ajustes, ambos com evidência real de Postgres, ver seção "Desvios e correções" abaixo.** (1) Assertiva de `test_banco_anterior_ao_runner_e_carimbado` estreitada para checar a tabela ALVO do `ALTER`/`DROP` contra `BASELINE_TABLES`, em vez de proibir os verbos por inteiro. (2) **Complemento desta rodada** — `test_medicao_nasce_depois_da_baseline_com_o_indice_da_listagem` corrigido: o conjunto de tabelas pós-baseline esperado passou a incluir `estimate_rounds`/`estimate_round_revisions` (criadas pela `0003`, F-020, já mergeada antes desta tarefa), e a checagem de índice da listagem passou a cobrir as duas tabelas (`ix_valuation_rounds_tenant_created` e `ix_estimate_rounds_tenant_created`), não só a da medição. |
| `docs/features/F-027-modo-teto-orcamento-invertido/tasks/T1-build-report.md` | Este relatório. |

## Testes novos

Todos em `tests/api/test_estimate_round_routes.py`, seção `# --- teto de verba (ADR-0040) ---`:

1. `test_criar_rodada_com_teto_o_estado_devolve_o_bloco` — criar com teto: `GET` do estado devolve `target: {amount, label}`; sem `estimate_json` ainda, `consumed`/`remaining`/`over` ficam ausentes.
2. `test_listagem_mostra_teto_cru_sem_consumo` — **complemento desta rodada.** Duas rodadas (uma com teto, uma sem) na mesma listagem: a com teto devolve `target_amount`/`target_label` crus e NUNCA `consumed`/`over`; a sem teto devolve os dois campos `None`.
3. `test_criar_rodada_sem_teto_o_bloco_fica_ausente_mesmo_com_orcamento_montado` — criar sem teto, montar o orçamento inteiro (fluxo `_round_ready_for_estimate` + `POST .../estimate`): nenhuma das quatro chaves aparece nem na resposta da montagem nem no `GET` do estado — cobre a decisão 6 mesmo com `estimate_json` presente.
4. `test_declarar_teto_depois_da_criacao` — `POST .../target` numa rodada sem teto; `version` avança de 1 para 2; coluna gravada.
5. `test_editar_teto_ja_declarado` — rodada criada já com teto; edita valor e rótulo pela mesma rota; nova coluna reflete a edição.
6. `test_teto_com_base_version_velho_recusa_sem_gravar_nada` — segunda chamada com `base_version` reutilizado devolve `409 REVISION_CONFLICT`; a coluna não muda.
7. `test_teto_invalido_recusa_com_o_codigo_unico` — `0.00`, `-10.00` e texto ilegível recusam `422 ESTIMATE_TARGET_INVALID`; `version`/`target_amount` continuam intocados (a recusa acontece antes de qualquer mutação).
8. `test_criar_rodada_com_teto_invalido_recusa_na_criacao` — `0.00` na criação recusa `422 ESTIMATE_TARGET_INVALID` e nenhuma rodada é gravada.
9. `test_bloco_derivado_nos_tres_estados_do_teto` — o teste mais importante do lote: um único orçamento montado (`total_amount == "1125.00"`, cenário determinístico de `_round_ready_for_estimate` com BDI 25%) recebe três tetos sucessivos (edições pela mesma rota, thread do `base_version`): `2000.00` (dentro: `remaining == "875.00"`, `over: false`), `1125.00` (**limite exato**: `remaining == "0.00"`, `over: false` — a asserção mais sensível a erro de ponto flutuante), `1124.99` (um centavo acima: `remaining == "-0.01"`, `over: true`). Confirma também que `GET .../estimate` deriva o MESMO bloco.

Testes existentes estendidos (não recontados no total de "novos" acima):

- `test_sem_o_papel_toda_rota_recusa_antes_do_lookup` — adicionada a entrada `POST .../target` à lista de escritas que devem recusar `403 FORBIDDEN` antes do lookup.
- `test_post_sem_idempotency_key_recusa` — adicionada a chamada a `POST .../target` sem `Idempotency-Key`, mesma recusa `400 IDEMPOTENCY_KEY_REQUIRED`.

## Validação (rodada final, pós-complementos)

```text
BASELINE → CHANGE → FINAL
```

- **Baseline declarado pelo contrato**: `make check` e `make test` verdes na branch `f-027-especificacao` antes desta tarefa.
- **`make check`**: verde — `ruff check`, `ruff format --check` (424 arquivos), `mypy --strict` (195 arquivos-fonte, 0 issues), `check_docs.py` (**252** Markdown, paridade de lifecycle), `schema_export --check-dir` (sem drift de contrato), `contracts:check`, `web:check` (tsc + vite build), `infra-check` (terraform fmt).
- **`make test`** (foreground; o harness moveu para background automaticamente por exceder 120s — não foi escolha deliberada, o processo rodou e terminou antes de eu prosseguir): verde — `uv run pytest`: **1704 passed, 13 skipped** (os 13 skips são os testes de `test_migrations.py` que exigem `CROQUITO_TEST_POSTGRES_URL`, ausente por padrão local; o CI define a variável). `npm run web:test` (vitest): **693 passed** em 39 arquivos.
- **`uv run pytest tests/api/test_estimate_round_routes.py -x -q`**: **35 passed** (todos os testes do arquivo, incluindo os 9 novos desta task).
- **`uv run pytest tests/api/test_migrations.py tests/api/test_openapi_contract.py -q`**: verde localmente (13 skipped em `test_migrations.py` sem Postgres; `test_openapi_contract.py` 100% verde após regenerar o snapshot pela segunda vez).
- **Verificação extra, com Postgres efêmero via Docker, rodada final** (subi `postgres:17-alpine`, defini `CROQUITO_TEST_POSTGRES_URL`, rodei `tests/api/test_migrations.py` completo, derrubei o container **sempre**, inclusive nas rodadas intermediárias que ainda falhavam):
  - **Antes de qualquer mudança minha** (com `git stash`, medido na rodada anterior): 12 tests, 1 failed — `test_medicao_nasce_depois_da_baseline_com_o_indice_da_listagem` já quebrado na branch-base, sem relação com esta tarefa.
  - **Depois da minha mudança original, antes do ajuste no teste de adoção**: 2 failed (a falha pré-existente + `test_banco_anterior_ao_runner_e_carimbado`, causada pelo `ALTER TABLE` da `0004`).
  - **Depois do primeiro ajuste (estreitar a checagem de `ALTER`/`DROP` por tabela ALVO)**: de volta a 1 failed — só a pré-existente.
  - **Depois do segundo ajuste desta rodada (corrigir `criadas == {...}` e cobrir o índice de `estimate_rounds`)**: **12 passed, 0 failed** — confirmado agora, com `pytest -v`: `collected 12 items`, `12 passed`. Todos os testes de `test_migrations.py` verdes pela primeira vez nesta árvore.
  - Container Postgres criado com `--rm` e `docker stop` explícito ao final de CADA rodada (inclusive as que ainda falhavam); `docker ps -a` confirmou ausência de container residual ao término.
- **OpenAPI**: `make openapi-snapshot` rodado por ato deliberado duas vezes (rota/criação originais; depois os dois campos de `EstimateRoundSummary`); diff revisado linha a linha nas duas — só adição. Nenhum schema existente mudou de forma.
- **Contratos/goldens**: `git status` confirma que nada em `packages/contracts/`, `packages/valuation` nem golden algum foi tocado.

## Desvios e correções conscientes do spec, e por quê

1. **`tests/api/test_migrations.py::test_banco_anterior_ao_runner_e_carimbado`** — fora do mapa de arquivos do Task Contract original, mas consequência DIRETA e inevitável de implementar a migração `0004` (a primeira `ALTER`-based do repositório).
   - **Evidência**: o teste afirmava "nenhum `ALTER`/`DROP`" sem qualificação, mas seu PRÓPRIO docstring descreve a invariante real como "a adoção não recria nem altera **o que já existia**" — tabelas da BASELINE (`0001`). Como `0001`-`0003` só faziam `CREATE TABLE`, a asserção ampla e a invariante estreita coincidiam por acaso; a `0004` é a primeira a fazer `ALTER` numa tabela PÓS-baseline (`estimate_rounds`, da `0003`) dentro do mesmo `upgrade` de adoção — comportamento correto e esperado.
   - **Ação**: estreitei a asserção para checar a tabela ALVO de cada `ALTER`/`DROP` contra `BASELINE_TABLES`. Confirmado com Postgres real (ver Validação) que isso resolve exatamente a falha introduzida e nenhuma outra.

2. **`tests/api/test_migrations.py::test_medicao_nasce_depois_da_baseline_com_o_indice_da_listagem`** — **correção declarada de uma falha PRÉ-EXISTENTE**, pedida explicitamente pelo coordenador nesta rodada, com evidência confirmada por mim antes de qualquer mudança (`git stash` + Postgres real: 1 failed, idêntica, na branch-base).
   - **Causa raiz**: a asserção `criadas == {"valuation_rounds", "valuation_round_revisions"}` ficou defasada quando a `0003` (F-020, mergeada antes desta tarefa) criou `estimate_rounds`/`estimate_round_revisions` — tabelas pós-baseline que a `command.upgrade(..., "head")` do teste também cria, mas que a asserção nunca previu.
   - **Ação**: o conjunto esperado agora enumera as quatro tabelas pós-baseline (`valuation_rounds`, `valuation_round_revisions`, `estimate_rounds`, `estimate_round_revisions`), e a checagem de índice — que dá nome ao teste — passou a cobrir as DUAS listagens com cursor opaco (`ix_valuation_rounds_tenant_created` e `ix_estimate_rounds_tenant_created`), não só a da medição. Não existe constante central para "tabelas pós-baseline" no repositório (`BASELINE_TABLES`, em `bootstrap.py`, descreve deliberadamente só a `0001`); documentei em comentário no teste que a lista é literal e precisa crescer a cada migração pós-baseline futura que criar tabela nova, porque nem o gate de drift nem `BASELINE_TABLES` avisam este teste.
   - **Confirmado com Postgres real**: `test_migrations.py` inteiro passou de 1 failed para **12 passed, 0 failed**.

3. **`estimated_cost_usd` usa `String(24)` no precedente do repositório; usei `String(32)` para `target_amount`.** O contrato disse apenas "String" sem tamanho. Verbas municipais podem ter mais dígitos que custo de IA; escolhi um teto generoso e documentei no docstring da coluna. Nenhum teste depende do limite exato — divergência de baixo risco.

## Achados fora de escopo (não implementados)

- Não toquei em `EstimateRoundResponse` (resposta de `POST /v1/estimate-rounds`): ela continua devolvendo só `round_id`/`version`/`status`/`created_at`, sem o teto — o bloco derivado só existe nos payloads que o contrato citou explicitamente (`round_state_payload`, o payload do estimate e, agora, `EstimateRoundSummary`). Se a UI de criação precisar do bloco imediatamente após criar, ela pode chamar `GET /v1/estimate-rounds/{round_id}` em seguida.
- Nenhuma tentativa de tornar `target_label` obrigatório quando `target_amount` está ausente na criação nem o inverso — o contrato não pediu essa validação cruzada e um `target_label` sem `target_amount` simplesmente não produz bloco nenhum (comportamento inofensivo, não testado explicitamente).
- `EstimateRoundSummary`/`GET /v1/estimate-rounds` agora expõe o teto cru (complemento desta rodada), mas eu não adicionei `stage`/ordenação/filtro por presença de teto na listagem — o pedido do coordenador foi só os dois campos crus, e não estendi além disso.

## Assumptions

- `total_amount` dentro de `estimate_json` sempre serializa como string decimal (`Estimate.model_dump(mode="json")`), confirmado empiricamente antes de implementar (`Decimal` → `str` em modo JSON do Pydantic v2).
- O cenário determinístico de `_round_ready_for_estimate` + BDI `25.00` sempre produz `total_amount == "1125.00"` — já usado por teste pré-existente (`test_o_caminho_feliz_publica_orcamento_e_planilha_auditada`), reaproveitado sem alterar a fixture.

## Remaining risks

- A migração `0004` e os dois ajustes de `test_migrations.py` só foram exercitados contra Postgres real por mim, fora do comando padrão do contrato (que roda sem `CROQUITO_TEST_POSTGRES_URL` localmente e portanto pula esses testes). Recomendo observar a primeira execução real desta branch no CI (que define a variável), embora a evidência local com Postgres descartável já cubra os 12 testes do arquivo, 12/12 verdes.
- A lista literal de tabelas pós-baseline em `test_medicao_nasce_depois_da_baseline_com_o_indice_da_listagem` precisa de manutenção manual a cada migração futura que criar tabela nova — documentei isso no próprio teste, mas não há gate automático que force a atualização.

## Human decisions required

- Confirmar que os dois ajustes em `tests/api/test_migrations.py` são aceitáveis (o segundo foi pedido explicitamente pelo coordenador nesta rodada; o primeiro é reafirmado aqui com a mesma evidência já apresentada).
- Merge represado desta feature/branch segue como gate humano, conforme `plan.md`.
