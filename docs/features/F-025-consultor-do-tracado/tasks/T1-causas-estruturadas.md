# T1 — Causas estruturadas, vão em disputa nomeado e âncoras aplicadas

Task Contract derivado do [plano](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-025
task_id: T1
parent_plan: docs/features/F-025-consultor-do-tracado/plan.md
depends_on: []
```

## Goal

O resultado do trace-solve passa a contar POR QUE cada leitura confirmada não
virou vão (causa estruturada, não só o ID), a nomear par a par as cotas que
disputam o mesmo vão, e a expor as âncoras em metros de cada leitura aplicada.
Tudo aditivo: `unapplied_reading_ids` e `blockers` continuam idênticos.

## Baseline

Branch `f-025-consultor-tracado` a partir de `60e574d`, árvore limpa.
`uv run pytest tests/worker/test_tracing.py tests/worker/test_geometry_solver.py`
verde (91 testes) e vitest 697/697 verdes em 2026-08-20.

## Scope

### `services/worker/src/croquito_worker/tracing.py`

**1. Modelos novos (Pydantic, junto de `TraceSolveResult` ~linha 258):**

```python
class UnappliedReadingReport(TraceModel):
    reading_id: str
    cause: str            # código estável, regex ^[A-Z0-9_]{3,64}$ como Issue.code
    target_proposal_ids: list[str] = Field(default_factory=list)

class ContestedSpan(TraceModel):
    axis: Literal["x", "y"]
    reading_ids: list[str] = Field(min_length=2)   # ordenados
    values_m: list[Decimal] = Field(min_length=2)  # mesma ordem de reading_ids
    proposal_ids: list[str] = Field(default_factory=list)

class AppliedSpanReport(TraceModel):
    reading_id: str
    axis: Literal["x", "y"]
    value_m: Decimal
    start_m: float        # coordenada CAD (metros) da junção near ao longo do eixo
    end_m: float          # idem, far — frame CAD (origem canto inferior esquerdo)
    proposal_id: str
    second_proposal_id: str | None = None
    gap: bool = False
```

`TraceSolveResult` ganha (com default para não quebrar construções antigas):
`unapplied_readings: list[UnappliedReadingReport] = Field(default_factory=list)`,
`contested_spans: list[ContestedSpan] = Field(default_factory=list)`,
`applied_spans: list[AppliedSpanReport] = Field(default_factory=list)`.

**2. Causa no ponto do descarte.** `_span_from_reading` (linhas 579-775) hoje
retorna `list[tuple[SpanConstraint, _AppliedSpan]] | None`. Troque o `None`
seco por causa: retorne `list[...] | str` (o `str` é o código da causa) OU um
pequeno tipo `_SpanFailure` — escolha a forma que ficar limpa no mypy strict,
mas TODO retorno de falha carrega um código destes:

- `TRACE_SPAN_VALUE_OR_DECISION_MISSING` — `_value_m is None or decision is None`
  (linha ~606; defensivo, não deve ocorrer para confirmada).
- `TRACE_SPAN_AXIS_UNDECLARED` — `required_axis is None` nos caminhos de vão
  declarado (linha ~617) e de dois elementos (linha ~674).
- `TRACE_SPAN_EDGE_NOT_FOUND` — `_gap_edge` devolveu `None` para alguma âncora
  (linhas ~629 e ~688).
- `TRACE_SPAN_SAME_BAND` — as duas âncoras/arestas caíram na mesma faixa
  (`edge_a[1] == edge_b[1]` / `first_edge[1] == second_edge[1]`).
- `TRACE_TARGET_AS_DRAWN` — caminho de elemento único (linha ~725 em diante)
  quando `proposal.id in freeform_ids`: cota de elemento único nunca aplica em
  forma "como desenhada" (faixas por vértice) — é a causa 1 da V17. Cheque
  ANTES do loop de segmentos, explícito.
- `TRACE_SPAN_NOT_ORTHOGONAL` — elemento único não-freeform sem segmento
  ortogonal compatível (o `chosen is None` da linha ~744, e também
  `not junctions` na ~727).

**3. Acúmulo com causa.** `_solve_group_geometry` (linhas 1160-1250): o local
`unapplied: list[str]` vira `list[UnappliedReadingReport]` — no
`if not outcomes` (linha ~1213) guarde `reading_id`, o código retornado e
`target_proposal_ids=targets`. A assinatura de retorno muda
(`tuple[_GroupState | None, list[SpanConstraint], list[_AppliedSpan], list[UnappliedReadingReport]]`);
ajuste TODOS os usos em `solve_trace` (agregação da planta ~1403, detail groups
~1445-1465, early returns `review_required` ~1415/1467 — nesses early returns
preencha os DOIS campos: `unapplied_reading_ids=[r.reading_id for r in ...]` e
`unapplied_readings=...`). Os `unapplied.append(reading_id)` da fase de notas
(linhas ~2077 com `TRACE_NOTE_ZERO_LENGTH` e ~2101 com
`TRACE_NOTE_UNSUPPORTED_GEOMETRY`) entram na mesma lista estruturada. Grep
`unapplied` no arquivo para não deixar site órfão.

**4. Detecção de vão em disputa (causa 3).** Função nova em tracing.py (o LSQ
em `geometry_solver.py` fica INTOCADO), chamada dentro de
`_solve_group_geometry` após o loop de constraints (~linha 1220), com retorno
agregado por `solve_trace` no resultado:

- agrupar `SpanConstraint` por `(axis, first_band, second_band)` — campos em
  `geometry_solver.py:93-121`; `first_band` já vem em ordem traçada, o par é
  estável;
- grupo com ≥2 `source_id` distintos cujo spread de `value_m`
  (`max - min`) excede a MAIOR tolerância dos spans envolvidos
  (`_span_tolerance_m` sobre os `_AppliedSpan` correspondentes) vira
  `ContestedSpan` com `reading_ids` ordenados, `values_m` (Decimal dos
  `_AppliedSpan.value_m`, mesma ordem) e `proposal_ids` (união ordenada de
  `proposal_id`/`second_proposal_id` dos spans);
- NÃO cria blocker novo nem muda status: os resíduos existentes continuam
  decidindo (`NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE`); isto é diagnóstico.

**5. Âncoras aplicadas.** No loop de resíduos (~linha 1680), onde `first` e
`second` (Point2D CAD) já são calculados por span, produza também o
`AppliedSpanReport`: `start_m`/`end_m` = coordenada ao longo de `span.axis`
(`.x` para eixo x, `.y` para eixo y) de `first`/`second` com
`start_m <= end_m`. Inclua gap e não-gap. Agregue em
`TraceSolveResult.applied_spans`.

**6. Issue com causa.** No loop de issues (~linha 2204): a mensagem de
`CONFIRMED_READING_NOT_APPLIED` incorpora a frase da causa por leitura (uma
frase curta em português por código — ex.: para `TRACE_TARGET_AS_DRAWN`,
"o alvo está aceito como desenhado; cota de elemento único não amarra em forma
livre"). Código da Issue NÃO muda; só a mensagem deixa de ser fixa.

### `services/worker/src/croquito_worker/local_queue.py`

- `outcome` (~linha 1340): acrescente `unapplied_readings`
  (`[r.model_dump(mode="json") for r in result.unapplied_readings]`),
  `contested_spans`, `applied_spans` (idem).
- `_write_trace_solve_result` (~linha 1043): três parâmetros novos e três
  colunas novas no UPDATE, pelo mesmo molde `_json_parameter`
  (`unapplied_readings_json`, `contested_spans_json`, `applied_spans_json`).

### `services/api/src/croquito_api/database.py`

`TraceSolveRecord` (linha 286): três colunas novas ao lado de
`unapplied_reading_ids_json` (linha 314):

```python
unapplied_readings_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
contested_spans_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
applied_spans_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
```

### Migração Alembic (nova)

`services/api/src/croquito_api/migrations/versions/0004_trace_solve_diagnostics.py`
no molde da 0003: `ALTER TABLE trace_solves ADD COLUMN` das três colunas JSON,
aditiva, forward-only (downgrade remove as colunas). `tests/api/test_migrations.py`
precisa continuar verde.

### `services/api/src/croquito_api/main.py`

- Modelos de resposta (~linha 588): `UnappliedReadingOut`, `ContestedSpanOut`,
  `AppliedSpanOut` (espelhos ApiModel dos modelos do worker; `value_m`/`values_m`
  como float na resposta, padrão do `TraceResidualSummary`) e três campos novos
  em `TraceSolveResponse` com `default_factory=list`.
- `_trace_solve_response` (~linha 1950): mapear as três colunas novas
  (`list(record.<coluna> or [])`).

### `tests/worker/test_tracing.py`

- Cenários existentes ganham asserção da causa (não crie fixtures novas para
  isso): `test_vao_sem_eixo_declarado_fica_como_nao_aplicado` (~642) →
  `TRACE_SPAN_AXIS_UNDECLARED`; `test_leitura_diagonal_fica_declarada_como_nao_aplicada`
  (~1674) → `TRACE_SPAN_NOT_ORTHOGONAL`;
  `test_sem_keep_apart_o_recuo_do_degrau_fica_como_nao_aplicado` (~1338) →
  causa do cenário (conferir no teste qual retorno dispara; provavelmente
  `TRACE_SPAN_SAME_BAND`).
- Teste novo: cota de elemento único mirando proposta em
  `freeform_proposal_ids` → `TRACE_TARGET_AS_DRAWN` (é a assinatura da V17).
- Teste novo: duas leituras confirmadas com valores divergentes amarrando o
  MESMO par de faixas (molde do cenário de
  `test_duas_cotas_inconsistentes_no_mesmo_elemento_invertem_a_ordem_e_bloqueiam`,
  ~2401, ou um sintético mínimo) → `contested_spans` com os dois `reading_ids`
  e os dois valores; blockers inalterados em relação ao comportamento atual.
- Teste novo ou asserção em cenário resolvido existente: `applied_spans` traz
  âncoras coerentes (start < end, eixo certo, value_m da leitura); e
  `unapplied_reading_ids == [r.reading_id for r in unapplied_readings]` em
  todo cenário com não aplicada.
- A mensagem da Issue `CONFIRMED_READING_NOT_APPLIED` agora varia por causa —
  se algum teste asserta a mensagem fixa, atualize-o para a nova frase.

### OpenAPI + docs

- `make openapi-snapshot` (ato deliberado; a superfície `/v1` mudou de forma
  aditiva) e `tests/api/test_openapi_contract.py` verde.
- `docs/architecture/API_CONTRACT.md`: os três campos novos na seção de
  trace-solves, com a tabela de códigos de causa e a semântica
  (aditivo; `unapplied_reading_ids` preservado).
- `docs/architecture/TRACE_STAGE.md`: parágrafo do diagnóstico (causas,
  disputa, âncoras) no estágio de traçado.

## Out of Scope

- `geometry_solver.py` (LSQ, regularise, band order) — leitura permitida,
  edição proibida.
- `rectangle_solver.py`, export/dxf, `export_errors()`, chat, apps/web.
- Blocker novo ou mudança de `solve_status` — diagnóstico não muda gate.
- Qualquer renomeação/remoção de campo existente.

## Acceptance Criteria

1. `make check` verde (ruff, mypy strict, check_docs, drift, build web).
2. `uv run pytest tests/worker/test_tracing.py tests/api -q` e `make test`
   verdes; `make solver-eval` verde.
3. Payload antigo byte-compatível fora dos campos novos: blockers,
   `unapplied_reading_ids`, residual_summary e contagens idênticos aos de hoje
   nos cenários existentes.
4. Todo `unapplied_reading_ids[i]` tem exatamente um
   `unapplied_readings[j].reading_id` correspondente, com `cause` não vazio.
5. Nenhum log novo com conteúdo de leitura (raw_text etc.) — códigos e IDs
   apenas (a Issue vive na cena, não em log).

## Validation

```bash
make check
uv run pytest tests/worker/test_tracing.py tests/api -q
make test
make solver-eval
make openapi-snapshot   # e conferir o diff do snapshot no commit
```

## Report

Responda com o `BUILD REPORT` completo do contrato do Builder (status, files
changed, validation executed/skipped, unavailable capabilities, assumptions,
remaining risks, human decisions required). Se um portão reprovar em área não
tocada, pare e reporte em vez de consertar área alheia.
