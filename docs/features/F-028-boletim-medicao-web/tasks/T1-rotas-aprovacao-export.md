# T1 — Rotas `/v1`: aprovação nominal e exportação auditada do boletim

Task Contract derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core
(pinado em `docs/engineering-os/`), este contrato, o [feature contract](../feature.md),
o [Design Approval Package aprovado](../mock/README.md) e o repositório.

## Identity

```text
feature_id: F-028
task_id: T1
parent_plan: docs/features/F-028-boletim-medicao-web/plan.md
depends_on: []
```

## Goal

VAL-05 vira recusa de rota: a medição montada é aprovada nominalmente por ato próprio
(identidade do JWT, digest amarrado) e o boletim `.xlsx` só é exportado com aprovação
válida, pelo gate auditado fail-closed — tudo em `/v1/valuation-rounds*`.

## Baseline

`make check` e `make test` verdes na branch `f-025-boletim-web` (rode `make setup`
antes — worktree novo).

## O mecanismo que você EXERCE (não recria)

- `ValuationApproval` (`packages/valuation/src/croquito_valuation/models.py:381-389`)
  = `ReviewerDecision` (354-378) + `valuation_digest`. `Valuation.approval` (:408).
- `Valuation.content_digest()` (:485-493) — exclui `approval` do digest.
- `Valuation.export_errors(contract)` / `ensure_exportable(contract)` (:495-552) —
  produz `VALUATION_NOT_APPROVED`, `VALUATION_APPROVAL_REJECTED`,
  `APPROVAL_CONTENT_MISMATCH`, códigos de contrato/saldo, e levanta
  `VALUATION_EXPORT_BLOCKED` com a lista em `details.errors`.
- ATENÇÃO: `run_export_valuation` do CLI (cli.py:858-882) NÃO chama
  `ensure_exportable` — "o portão já correu antes daqui". A SUA rota de export chama.

## Scope

### `services/api/src/croquito_api/valuation_rounds.py`

- Helper de aprovação: monta `ReviewerDecision(action="confirm",
  reviewer_id=principal.subject, reviewer_role="orcamentista",
  decided_at=agora UTC)` + `ValuationApproval(valuation_digest=
  content_digest da Valuation da cabeça)`, embute em `valuation.approval` e devolve o
  `model_dump` para a revisão nova. NADA vem do corpo além de `base_version` —
  identidade nunca viaja do cliente (critério 3 da feature).
- `render_valuation_workbook(valuation, catalog, template, contract)` espelhando
  `render_estimate_workbook` (`estimate_rounds.py:803-823`): tempdir →
  `write_valuation_workbook` (`workbook_writer.py:1257`) → `audit_workbook`
  (`canonical.py:555`) → divergente levanta `VALUATION_WORKBOOK_AUDIT_FAILED`
  (RoundRefusal 500, molde `workbook_audit_failed` em `estimate_rounds.py:166-185` —
  NUNCA expected/found no problem+json).
- `bulletin_workbook_key(tenant_id, round_id, valuation_sha256)` por digest
  (molde `estimate_workbook_key`, :826-834) + chaves `BULLETIN_WORKBOOK_REF`/
  `BULLETIN_WORKBOOK_DIGEST` nos mapas `artifact_refs_json`/`artifact_digests_json`
  existentes (SEM migração; padrão F-020).
- `round_state_payload` (704-799) e `_bulletin_payload` (main.py:5325-5342): bloco de
  aprovação `{approved, approved_by, approved_at, approved_digest, current_digest,
  stale}` (`stale` = digest aprovado ≠ `content_digest()` atual — é o estado
  "aprovação caduca" do mock) e `workbook_present`/`workbook_sha256`. URL assinada só
  no GET, montada na hora, nunca persistida.

### `services/api/src/croquito_api/main.py` (rotas ao FINAL do arquivo)

- `POST /v1/valuation-rounds/{round_id}/approve` — corpo `{base_version}` apenas;
  papel na primeira linha, `Depends(_require_idempotency)`, `require_base_version`;
  sem `valuation_json` na cabeça → `ROUND_STAGE_NOT_READY`; revisão nova com
  `valuation_json` reescrito com `approval` (a mutação avança `version` — ato
  humano); `_record_audit` ação `"VALUATION_APPROVED"`.
- `POST /v1/valuation-rounds/{round_id}/bulletin/export` — corpo `{base_version}`;
  mesma disciplina; carrega a `Valuation` da cabeça, o catálogo e o template como o
  `/calc` (6247-6341) e o `GET /bulletin` (6343-6369) já fazem, chama
  `ensure_exportable` com o MESMO contrato que o `/calc` usa (se o fluxo da rodada
  não tem `ContractWorkbook`, passe o que o fluxo tem — NUNCA afrouxe o portão:
  aprovação continua obrigatória e `VALUATION_EXPORT_BLOCKED` → 422 problem+json com
  `details.code` e a lista de erros), depois render+audita+publica na ORDEM exata da
  rota `build_estimate` (main.py:7659-7781): render → write_object → append_revision
  (refs+digests) → idempotência → `_record_audit` `"BULLETIN_EXPORTED"` → commit.
- `GET /v1/valuation-rounds/{round_id}/bulletin` (6343-6369): campos novos
  (aprovação + workbook + `workbook_url` assinada quando publicado). Diff aditivo.

### Snapshot e docs

- `make openapi-snapshot` por ato deliberado; diff só de adição.
- `docs/architecture/API_CONTRACT.md`: as duas rotas novas + campos novos do GET.

### Testes — `tests/api/test_valuation_round_routes.py`

Aprovar feliz (version avança; `valuation_json` da revisão nova valida com
`Valuation.model_validate` e `approval.decision.reviewer_id` = subject do token;
digest aprovado == `content_digest()`); aprovar sem valuation →
`ROUND_STAGE_NOT_READY`; exportar sem aprovação → `VALUATION_EXPORT_BLOCKED` com
`VALUATION_NOT_APPROVED` na lista; recalc depois de aprovar → export recusa com
`APPROVAL_CONTENT_MISMATCH` e o GET expõe `stale: true`; export feliz publica por
digest, grava refs/digests e o GET devolve `workbook_url`; auditoria divergente
(monkeypatch no auditor, molde dos testes do estimate) → 500 sem publicar nada;
403 sem papel, POST sem `Idempotency-Key`, `base_version` velho → 409 — nas DUAS
rotas novas.

## Out of scope

- Web (T2), e2e (T3), CLI, domínio (`models.py` não muda), `/calc`, migrações.
- Rotas do estimate e do croqui.

## Acceptance criteria

1. `make check` e `make test` verdes; snapshot OpenAPI só-adição.
2. O portão é o do domínio (`ensure_exportable`) — nenhuma reimplementação de regra.
3. Identidade exclusivamente do JWT; nenhum nome viaja no corpo.
4. Cobertura de teste nomeada acima completa, com códigos exatos.

## Validation

```bash
make check
make test
uv run pytest tests/api/test_valuation_round_routes.py -x -q
uv run pytest tests/api/test_openapi_contract.py -q
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo em
docs/features/F-028-boletim-medicao-web/tasks/T1-build-report.md.
