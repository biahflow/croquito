# T2 — ⚠ segunda testemunha: corroboração do OCR na leitura

Task Contract derivado do [plano](../plan.md). Autossuficiente.

## Identity

```text
feature_id: F-010
task_id: T2
parent_plan: docs/features/F-010-revisao-assistida-lote/plan.md
depends_on: [T1]
```

## Goal

A corroboração do braço de OCR deixa de ser nota posicional invisível e vira campo
da própria leitura + aviso na tela. Caso fundador no feature.md (24,75 vs 19,75 da
V17): o pacote sabia (`OCR_EVIDENCE_MISSING`) e ninguém viu.

## Baseline

Main limpa (conferir `git branch --show-current` — OUTRA SESSÃO trabalha em
paralelo na parte de orçamento; se aparecer no `git status` qualquer arquivo de
valuation/orçamento que você não tocou, PARE e reporte, e JAMAIS use `git add -A`).
`make check` + `make test` (1645 pytest + 591 vitest) verdes.

## Scope

### Worker

`services/worker/src/croquito_worker/review.py` (DimensionReading, ~116+):
- `ocr_corroborated: bool | None = None`, comentário no molde de
  `annotation_suggested`: True = o OCR leu o mesmo texto na mesma região; False =
  OCR rodou e NÃO leu; None = braço ausente/falhou. Registro de NASCIMENTO da
  observação — retificação não reescreve. Default None preserva pacote antigo.

`services/worker/src/croquito_worker/provider_review.py` (laço, ~608-621):
- Hoje: `if ocr_ran:` chama `_reading_confirmed_by_ocr` inline na nota. Passe a
  calcular UMA vez (`confirmed = _reading_confirmed_by_ocr(...) if ocr_ran else
  None`) e use nas duas saídas: a nota posicional EXISTENTE (byte-idêntica — é
  história e telemetria) e o campo novo no construtor do DimensionReading (~617+).

`tests/worker/test_providers.py`:
- linha de OCR casando → leitura com `ocr_corroborated is True`;
- sem casar (decoy/ausente da lista) → `False`;
- suite sem braço OCR → `None`;
- notas posicionais `READING_{n}_OCR_*` continuam exatamente como antes (asserção
  explícita num dos testes existentes ou novo).

### Web

`apps/web/src/api.ts`: `ReviewReading.ocr_corroborated?: boolean | null`.

`apps/web/src/labels.ts`: `ocrWitnessHint(reading): string | null` no molde
documentado de `suggestedAnnotationHint`:
- `=== false` → "sem segunda testemunha: o OCR leu a folha e não encontrou este
  texto — confira o recorte (leitura trocada é o caso clássico: 1↔2, 9↔4)"
- qualquer outro valor → null (confirmação e ausência de braço ficam em
  silêncio; ✓ em toda linha viraria ruído).
`labels.test.ts`: 4 casos (false, true, null, campo ausente).

`apps/web/src/CroquiApp.tsx`:
- Linha da lista (o `review-row-wrap` da fatia 1): quando
  `reading.ocr_corroborated === false`, `<small className="ocr-warning">⚠ sem 2ª
  testemunha</small>` junto ao rótulo de status. Texto é o indicador; cor só
  reforço.
- Painel de decisão: a frase de `ocrWitnessHint(selectedReading)` no mesmo bloco
  dos hints existentes (junto ao `suggestedAnnotationHint`).
- NADA em payload, lote, precedências, retificação.

`apps/web/src/styles.css`: `.ocr-warning` mínimo se necessário.

### Docs e snapshot

- `tests/api/openapi.snapshot.json`: regenerar (`make openapi-snapshot`); diff
  aditivo apenas.
- `docs/architecture/API_CONTRACT.md`: campo, tri-estado, semântica de nascimento.
- `docs/ai/MODEL_ROUTING.md`: uma frase — a corroboração por leitura agora chega
  ao revisor no pacote.
- `docs/product/FDD.md`: uma frase na seção da decisão (aviso de segunda
  testemunha; não bloqueia, informa).

## Out of scope

Rebaixar status por corroboração; lote (T1); re-corroborar valor corrigido;
tracing/valuation; sugerir o valor lido pelo OCR (fatia 3 candidata).

## Acceptance criteria

1. `make check`, `make test`, vitest e `make provider-contract-demo` verdes.
2. `_reading_confirmed_by_ocr` chamado UMA vez por leitura (conferível no diff).
3. Notas posicionais byte-idênticas às de hoje.
4. Chip aparece SÓ com `false`; painel mostra a frase completa; `true`/`None`
   silenciosos.
5. Snapshot OpenAPI: diff aditivo.

## Validation

```bash
make check && make test
uv run pytest tests/worker/test_providers.py -x -q
npm --workspace @croquito/web run test
make provider-contract-demo
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT (o orquestrador commita com lista explícita de
arquivos — sessão paralela no repositório).

## Report

BUILD REPORT completo em tasks/T2-build-report.md E na resposta final.
