# BUILD REPORT — F-021-T1

```text
Status: BUILD_COMPLETE
Files changed:
  - services/worker/src/croquito_worker/review.py — DimensionReading ganha
    annotation_suggested: bool = False (entre provider_lineage e status); default
    False preserva pacotes persistidos antigos no ReviewPacket.model_validate.
  - services/worker/src/croquito_worker/provider_review.py — laço de leituras
    (build_provider_review_snapshot): note completo (normalized_value + target_hint)
    monta DimensionReading com kind=MeasurementKind.LENGTH (neutro) e
    annotation_suggested=True; note sem valor gera READING_{n}_NOTE_WITHOUT_VALUE em
    vez de READING_{n}_INCOMPLETE; count/unknown seguem idênticos
    (READING_{n}_UNSUPPORTED_UNIT_OR_KIND via _measurement_kind). Nenhuma mudança em
    _readings_agree, na nota KIND_DIVERGENCE (577-581) nem em UNIT_ABSTENTION: elas
    comparam observation.kind/counterpart.kind como string bruta e passam a alcançar
    note automaticamente, sem regra nova.
  - tests/worker/test_providers.py — 2 helpers (_note_reading, _count_reading) + 4
    testes novos (ver seção de testes abaixo), reformatado por `ruff format` (só o
    trecho novo).
  - docs/ai/PROMPT_CONTRACTS.md — bullet novo na seção "Regras" de
    measurement-extraction@1.1.1 documentando o destino de note completo/sem
    valor/count/unknown. Sem bump de versão do prompt.
  - tests/api/openapi.snapshot.json — DESVIO CONSCIENTE, ver seção 4 abaixo.

Validation executed:
  - uv run pytest tests/worker/test_providers.py -x -q → 230 passed
  - make check → ruff check, ruff format --check, mypy strict (187 arquivos),
    check_docs.py (210 md), schema_export --check-dir (sem drift), contracts:check,
    web:check (tsc -b + vite build), infra-check (terraform fmt) — todos verdes
  - make test → uv run pytest: 1602 passed, 10 skipped (baseline já tinha skips) +
    npm --workspace @croquito/web run test: 32 arquivos, 581 testes passed
  - make provider-contract-demo → status human_review_required, 3 readings, ZIP não
    exportado (esperado, fixture sintética não aprovada) — comando terminou com saída
    JSON válida, sem erro
  - Demonstração ad hoc (critério de aceite 3): DimensionReading.model_validate() com
    payload SEM annotation_suggested valida e default vira False (ver transcript —
    comando `uv run python -c "..."` com asserts, saída "OK: pacote antigo sem
    annotation_suggested valida, default = False")

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - Mantidas as duas premissas do plano da feature (verificadas de novo nesta task):
    ReviewPacket não está no manifesto de contratos gerados (make contracts não
    necessário) e tipos do web (fora de escopo desta task) não quebram com campo
    opcional novo.
  - Unidade de leitura note nos testes usa "m" (não "unitless") para isolar
    exatamente o comportamento sob teste (roteamento por kind), já que _unit()
    rejeitaria "unitless" antes mesmo de chegar à checagem de kind — não é premissa
    sobre o que o provider realmente envia em produção, é escolha de fixture de
    teste.

Remaining risks:
  - Não investigado nesta task: qual unidade o provider realmente emite para
    kind="note" em produção. Se vier "unitless" ou "unknown", a leitura cairá em
    READING_{n}_UNSUPPORTED_UNIT_OR_KIND em vez de virar sugestão de anotação — o
    contrato da task não pediu tratamento desse caso e eu não inventei regra nova
    (ver seção de desvios). Se isso se confirmar um problema real, é um achado para
    a próxima rodada (fora do escopo desta task, que era só sobre note COMPLETO com
    normalized_value+target_hint).
  - T2 (apps/web) roda em paralelo na mesma árvore; validei make test com os dois
    diffs presentes e web:test/web:check passaram, mas não revisei o diff de T2.

Human decisions required: none
```

## Desvios conscientes do contrato

1. **`tests/api/openapi.snapshot.json` regenerado — arquivo fora da lista de escopo
   do contrato.** `make test` reprovou em
   `tests/api/test_openapi_contract.py::test_o_snapshot_versionado_descreve_a_superficie_atual`
   depois da mudança em `review.py`: `DimensionReading` é serializado pela rota
   `GET /v1/jobs/{id}/review`, então o campo novo `annotation_suggested` mudou o
   componente OpenAPI gerado (`components.schemas.DimensionReading`), e o snapshot
   versionado (`tests/api/openapi.snapshot.json`) ficou desatualizado.
   - **Verificação de baseline**: com `git stash` dos 4 arquivos desta task, o mesmo
     teste passa na árvore limpa — confirma que a falha nasceu desta mudança, não é
     preexistente.
   - **Ação**: rodei `make openapi-snapshot` (comando documentado no próprio Makefile
     e cobrado pelo próprio teste: "regenere com `make openapi-snapshot` e revise o
     diff produzido"). Revisei o diff: 5 linhas adicionadas, exatamente o campo
     `annotation_suggested` (`"type": "boolean", "default": false`) dentro de
     `DimensionReading` — nenhuma outra mudança, nenhuma diferença de operação (rota).
   - **Por que não é "área alheia"**: é consequência mecânica e determinística do
     campo pedido explicitamente pelo contrato (item 1 do Scope), do mesmo tipo que
     `make contracts` seria se `ReviewPacket` estivesse no manifesto — só que o
     mecanismo aqui é o snapshot de OpenAPI, não os contratos TS. Regenerar não exigiu
     nenhuma decisão de design; é о script `croquito_api.openapi_export` lendo o
     schema Pydantic atual. Sem essa regeneração, `make test` (portão explícito do
     contrato) ficaria vermelho por causa do próprio campo que o contrato pediu.
   - Não toquei `docs/architecture/API_CONTRACT.md` (esse é escopo do T2, e a segunda
     checagem do mesmo teste — paridade de rota com o Contract — não acusou nada;
     só a checagem de schema/`components` disparou).

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- `transcription.py` tem `_map_kind` próprio e provavelmente já descarta `note` do
  mesmo jeito que `provider_review.py` descartava antes desta task — não toquei
  (explicitamente fora de escopo no contrato).
- Não investiguei se o prompt `measurement-extraction@1.1.1` deveria orientar o
  modelo a sempre emitir `unit="unitless"` (ou outra convenção) para `kind="note"` —
  o contrato disse explicitamente "o contrato do prompt NÃO muda", então não mexi.
- O `target_hint` de uma nota (recado) muitas vezes não vai apontar para uma
  entidade geométrica real (ex.: "ver detalhe A" não tem `entity_label`/`feature`
  geométricos óbvios) — o `DimensionReading.target_hint` continua sendo texto livre
  `f"{entity_label}: {feature}"`, herdado do fluxo padrão; não inventei tratamento
  especial para isso porque não estava no contrato.
