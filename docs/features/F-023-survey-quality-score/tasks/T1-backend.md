# T1 — Cadeias de cotas no backend: sugestão, declaração, supersessão e CLI

Task Contract derivado do [plano](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-023
task_id: T1
parent_plan: docs/features/F-023-survey-quality-score/plan.md
depends_on: []
```

## Goal

Ligar o motor órfão `croquito_worker.dimension_closure` (completo e testado;
NÃO alterá-lo) ao produto: a resposta de review passa a trazer as cadeias que
fecham (`suggested_chains`, on-the-fly) e as cadeias declaradas pelo humano
(`declared_chains`, persistidas e re-conferidas a cada leitura); nasce a rota
de declaração/retração e o subcomando `check-chains` do CLI. Mismatch é aviso,
nunca blocker.

## Baseline

`main` em `88a717b`, árvore limpa. Antes de editar, rode e registre:
`uv run pytest tests/api tests/worker/test_cli.py tests/worker/test_dimension_closure.py -q`
(esperado verde; qualquer falha preexistente é baseline, não é sua).

## Mapa verificado (leia antes de editar)

- Motor: `services/worker/src/croquito_worker/dimension_closure.py` —
  `verify_chain(packet, *, total_id, part_ids) -> DimensionChain` (l.148;
  levanta `ChainVerificationError` para malformada/não-CONFIRMED; mismatch NÃO
  é erro, volta `DimensionChain` com `residual_m`/`closes`/`issue()`),
  `suggest_chains(packet, max_terms=4, limit=12)` (l.185), `DimensionChain`
  (l.67, `issue()` → `Issue(DIMENSION_CHAIN_MISMATCH, WARNING)`).
- API: `services/api/src/croquito_api/main.py` — imports do worker l.169-176;
  `ReviewResponse` l.512 (validator de `required_criteria` l.528-537 é o
  precedente de replay); `_review_response` l.2145 (ponto único de
  serialização); precedente de supersessão `READING_DECISION_SUPERSEDED`
  l.2222; portão de blockers l.2180-2185 (só CRITICAL+OPEN — não tocar);
  rotas de mutação de review criam `ReviewRevisionRecord` novo em 7 pontos:
  l.3130, 3394, 3572, 3760, 3992, 4148, 4275.
- Persistência: `services/api/src/croquito_api/database.py` —
  `ReviewRevisionRecord` l.145; `selected_associations_json` l.164 é o molde.
- Migrações: `services/api/src/croquito_api/migrations/versions/` — lineares
  `0001…0005`; a sua é `0006`, `down_revision="0005"`; siga o estilo da 0005.
- CLI: `services/worker/src/croquito_worker/cli.py` — parsers ~l.14-256,
  dispatch com import local ~l.738; `associate-review` usa o marcador
  `safety_status: observational_only` (siga-o).

## Scope (comportamento)

### 1. Persistência

`ReviewRevisionRecord.declared_chains_json: Mapped[list[dict[str, Any]]] =
mapped_column(JSON, default=list)` + migração `0006_review_declared_chains.py`
aditiva com `server_default` de lista vazia (forward-only; rollback = drop
column, descreva no docstring). Item persistido:
`{chain_id, total_id, part_ids, declared_by, declared_role, declared_at}` —
`chain_id = "ch_" + hex de 16` (siga o estilo de mint dos ids `rd_…` do repo).

**CRÍTICO — carregar adiante:** toda rota de mutação que cria
`ReviewRevisionRecord` novo (os 7 pontos listados + a sua rota nova) deve
copiar `declared_chains_json` da revisão anterior; sem isso a cadeia declarada
evapora na próxima decisão. Grep por `ReviewRevisionRecord(` em todo o repo e
confira cada sítio (criações iniciais sem o campo são cobertas pelo default).

### 2. Resposta de review (`_review_response`)

`ReviewResponse` ganha (ambos `Field(default_factory=list)` — replay de
respostas idempotentes gravadas antes do campo não pode quebrar):

- `suggested_chains: list[DimensionChain]` — `suggest_chains(packet)` direto.
- `declared_chains: list[DeclaredChainResponse]` — modelo novo na API:
  `{chain_id: str, declared_by: str, declared_at: datetime,
  chain: DimensionChain | None, status: Literal["closes","mismatch","stale"],
  issue: Issue | None}`. Para cada item persistido, re-rode `verify_chain`
  contra o packet corrente: sucesso e `closes` → `"closes"` sem issue;
  sucesso sem `closes` → `"mismatch"` com `chain.issue()`; e
  `ChainVerificationError` (leitura retificada/rejeitada/inexistente) →
  `"stale"`, `chain=None`, issue WARNING com código estável
  `CHAIN_READING_SUPERSEDED` e mensagem em português de domínio. Nada disso
  entra em `blockers`.

### 3. Rota `POST /v1/jobs/{job_id}/review/chains`

Closure em `create_app()` como as vizinhas (`submit_review_decisions` l.3020 é
o molde: `Idempotency-Key` obrigatória, `tenant_id` do JWT, concorrência
otimista por `base_version` com o mesmo erro-padrão de conflito, cria
`ReviewRevisionRecord` novo carregando todos os campos). Payload:
`{base_version: int, action: "declare" | "retract", total_id?: str,
part_ids?: list[str], chain_id?: str}`.

- `declare`: exige `total_id` + `part_ids` (≥2). Rode `verify_chain` para
  validar; `ChainVerificationError` → 422 problem+json código `CHAIN_INVALID`
  (mensagem do erro; sem parsing de string). Cadeia válida que NÃO fecha é
  declarável — mismatch é exatamente o sinal desejado. Registre autoria do
  token (mesma fonte de reviewer das decisões). Devolva `ReviewResponse` da
  revisão nova (padrão das vizinhas).
- `retract`: exige `chain_id`; remove o item (funciona também para cadeia
  `stale`); inexistente → 404 problem+json `CHAIN_NOT_FOUND`.

### 4. CLI `check-chains`

`croquito-demo check-chains --packet reviewed-packet.json [--output f.json]
[--total rd_x --part rd_a --part rd_b ...] [--max-terms 4] [--limit 12]`.
Sem `--total`: `suggest_chains` → stdout JSON
`{"suggestions": N, "chains": [...model_dump(mode="json")],
"safety_status": "observational_only"}`; `--output` grava o mesmo JSON.
Com `--total` + `--part` (≥2): `verify_chain` → `{"closes", "residual_m",
"tolerance_m", "issue"}`. Exit codes: 0 inclusive com mismatch (o comando não
é mais duro que o produto); 1 para `ChainVerificationError` (mensagem em
stderr); 2 fica com o argparse. Help em português de domínio.

### 5. Snapshot OpenAPI

`make openapi-snapshot` deliberado; revise o diff (deve conter só a rota nova
e os campos novos de `ReviewResponse`). `tests/api/test_openapi_contract.py`
é o gate.

## Out of Scope

`dimension_closure.py` e `tests/worker/test_dimension_closure.py` (imutáveis);
`apps/web/**` (T2); `croquito_core.models`/`make contracts`; `tracing.py` e a
conferência LSQ; `export_errors()`; qualquer promoção de cadeia a `Constraint`;
`docs/**` (a sessão principal atualiza). Não conserte falha preexistente fora
do escopo — pare e reporte.

## Acceptance Criteria

1. Review com 3 confirmadas que somam → `suggested_chains` não-vazio,
   `residual_m`/`tolerance_m` serializados como string; sem confirmadas → `[]`.
2. Declare que fecha → `declared_chains[0].status == "closes"`; declare com
   mismatch → `"mismatch"` + issue WARNING `DIMENSION_CHAIN_MISMATCH` e
   `blockers` idêntico ao de antes da declaração; declare malformada → 422
   `CHAIN_INVALID`; retract remove (e 404 `CHAIN_NOT_FOUND` para id inválido).
3. Retificar uma leitura participante (rota de rectifications existente) →
   a cadeia vira `"stale"` com `CHAIN_READING_SUPERSEDED`, sem sumir; uma
   decisão qualquer subsequente NÃO apaga cadeias declaradas (teste do
   carry-forward).
4. Replay idempotente de resposta gravada sem os campos novos não quebra
   (teste no padrão do replay de `required_criteria`); `base_version`
   divergente → conflito otimista padrão.
5. `check-chains`: sugestão exit 0; declarada com mismatch exit 0 + issue no
   JSON; malformada exit 1. Testes em `tests/worker/test_cli.py`.
6. Asserção mínima em `tests/e2e/test_full_flow.py`: a resposta de review
   contém as chaves `suggested_chains` e `declared_chains` (não dependa de
   `output/pdf/...` — dado local skipif).
7. Portões: `make check` e `make test` verdes; teste de migração da baseline
   (`tests/api/test_migrations.py`) verde com a 0006.

## Validation

```bash
uv run pytest tests/api tests/worker/test_cli.py tests/e2e -q
make openapi-snapshot   # deliberado, revisar diff
make check
make test
```

## Report

Termine com o `BUILD REPORT` completo do contrato do Builder (status, files
changed, validation executed/skipped, unavailable capabilities, assumptions,
remaining risks, human decisions required — `none` explícito onde vazio).
