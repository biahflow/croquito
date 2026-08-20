# F-021 — Evidência de execução

Pacote de evidência no formato do processo (`BASELINE → CHANGE → FINAL`). As fontes
primárias são os BUILD REPORTs por task, preservados com atribuição — este documento
referencia, não substitui.

## Baseline

Árvore de 2026-08-20 sobre `main` (6aaf632), com o conserto de UX da etapa de traçado
já presente e não commitado (rótulo "Traçado do desenho", aviso de opcional no aceite
em lote, abertura automática do painel). `make check` e `make test` verdes nessa
baseline (1602 pytest + 576 vitest antes das tasks).

## Execução

| Task | Builder (harness/modelo) | Report (PRIMARY_EXECUTION_EVIDENCE) | Status |
|---|---|---|---|
| T1 worker | Claude Code / implementador-sonnet | [T1-build-report.md](tasks/T1-build-report.md) | BUILD_COMPLETE |
| T2 web | Claude Code / implementador-opus | [T2-build-report.md](tasks/T2-build-report.md) | BUILD_COMPLETE |

Desvio consciente aceito na revisão (T1): regeneração mecânica de
`tests/api/openapi.snapshot.json` (5 linhas, só o campo `annotation_suggested` com
`default: false`), consequência determinística do campo pedido pelo contrato.

## Revisão (orquestrador da sessão, linha a linha)

- T1: laço de leituras conferido no diff — `note` completo → `LENGTH` +
  `annotation_suggested=True`; `note` sem valor → `READING_{n}_NOTE_WITHOUT_VALUE`;
  `count`/`unknown` intactos; notas de divergência/abstenção alcançam `note` por
  comparação de string bruta, sem regra nova.
- T2: precedência do rascunho da conversa sobre a sugestão conferida na ordem dos
  efeitos; decisão registrada intocada; heurística `\bh\s*=` deliberadamente estreita
  ("mureta 1,54" não sugere — caso do sinal do modelo); baseline de `CroquiApp.tsx`
  preservada byte a byte.
- Disciplina de mudança: FDD atualizado pelo orquestrador (seção da decisão de
  leitura); `docs/ai/PROMPT_CONTRACTS.md` e `docs/architecture/API_CONTRACT.md`
  atualizados pelas tasks.

## Validação integrada (FINAL, re-executada pelo orquestrador)

- `uv run pytest tests/` → 1641 passed, 10 skipped (inclui os 4 testes novos da T1;
  contagem final já com F-022-T1 na árvore)
- `npm --workspace @croquito/web run test` → 581 passed (5 novos)
- `make check` → exit 0 (mypy strict, ruff, check_docs, drift de contratos, build web)
- `make provider-contract-demo` → verde, saída estável

## Riscos remanescentes

- Leitura `note` com unidade fora de `m`/`mm` morre em `_unit` antes da sugestão —
  comportamento pré-existente para todo kind, não introduzido aqui; o braço âncora
  (Anthropic) infere `m` da convenção de obra. Fica como dado para a rodada seguinte.
- A pré-seleção não tem teste de componente (CroquiApp.test.tsx é SSR estático sem
  revisão fabricada); a cobertura é dos testes puros de `suggestedAnnotationHint`.

## Decisões humanas pendentes

- Commit dos diffs da árvore (nenhum commit foi feito pelas tasks, por instrução).
- Aceitação real na próxima revisão do Guaxindiba (upload novo) — teste de aceitação
  natural da feature.
