# T2 — Escritor `.xlsx` do orçamento-base e auditor de recomputação próprios

Task Contract no formato do template global (`docs/engineering-os/templates/task.md`),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core, este
contrato, o [ADR-0038](../../../adr/0038-bdi-como-conceito-de-pre-licitacao.md), o
[Design Approval Package aprovado](../mock/README.md) e o repositório.

## Identity

```text
feature_id: F-020
task_id: T2
parent_plan: docs/features/F-020-orcamento-base-web/plan.md
depends_on: [T1]
```

## Goal

O `Estimate` (já com BDI, schema v2 — entregue por T1) vira planilha `.xlsx` no
layout da prefeitura: as sete colunas do boletim mais `FONTE` (origem + data-base
numa célula) e `VALOR UNIT. C/ BDI`, bloco de itens sem preço, BDI declarado e o
valor do BDI impresso como diferença dos totais truncados. Um auditor próprio
reabre o arquivo e reconfere centavo a centavo; falha do auditor não publica nada.

## Baseline

T1 integrado na branch; `make check`, `make test`, `make valuation-demo` e
`make valuation-estimate-demo` verdes. Goldens da medição
(`tests/valuation/golden/valuation-demo.canonical.json`,
`valuation-demo-m4.canonical.json`) são o detector de regressão do boletim: se
qualquer um mudar, você quebrou o critério 8 da feature — PARE e reporte.

## Scope

Em `packages/valuation/src/croquito_valuation/template.py`:

- Seção nova OPCIONAL do `WorkbookTemplate` (linha 426) para o orçamento
  (ex.: `estimate: EstimateLayout | None = None`), com colunas = as do boletim
  mais duas novas: `FONTE` e `VALOR UNIT. C/ BDI` (nomes impressos exatamente
  assim — [pacote aprovado](../mock/README.md), "Decisões que este pacote
  carrega"). `default_template()` (linha 536) passa a preenchê-la. NADA da parte
  existente do template muda de forma ou valor — colunas aditivas e opcionais.

Módulo novo `packages/valuation/src/croquito_valuation/estimate_workbook.py`
(adaptador, NÃO generalização do escritor — decisão do plano; Unknown 1 do
feature.md resolvido aqui):

- `write_estimate_workbook(estimate, template, output_path) -> WriteReport` —
  siga o desenho de `workbook_writer.py`: plano célula a célula, `openpyxl`,
  gravação atômica (`_atomic_save`, linha 1234) e digest. Conteúdo, por decisão
  do pacote aprovado:
  - uma linha por `EstimateLine`, com `FONTE` = `price_origin` + `reference_month`
    numa célula e as colunas de preço sem e com BDI;
  - bloco próprio "itens sem preço na cascata" (`unpriced_item_ids`) — declarado,
    nunca precificado;
  - BDI percentual declarado uma vez (não repetido por linha);
  - o valor do BDI = `total_amount - total_amount_without_bdi` (diferença dos
    totais truncados; os dois campos vêm prontos do T1 — não recompute
    percentual sobre total).
- `audit_estimate_workbook(workbook_path, estimate, template) -> AuditReport` —
  Unknown 2 resolvido: auditor PRÓPRIO, reusando o mini-avaliador de fórmulas de
  `canonical.py` (`GRAMMAR_PATTERNS`, linha 65-78; `audit_workbook`, 555-593)
  como biblioteca — não estenda `audit_workbook` da medição. Reabre com
  `openpyxl.load_workbook`, recomputa em `Decimal`, `status: ok|divergent` com
  findings por célula. Fórmula fora da gramática fechada é recusa, nunca "pula".

Em `services/worker/src/croquito_worker/valuation/cli.py`:

- `estimate-demo` (`run_estimate_demo`, linha 1585-1678) passa a também exportar
  a planilha com o portão fail-closed no desenho EXATO de `run_export_valuation`
  (843-867): grava em nome pendente, audita, `os.replace` só com `audit.status
  == "ok"`, remove o pendente no `finally`.

Em testes:

- `tests/valuation/test_estimate_workbook.py` (novo): caso feliz (colunas novas
  presentes, FONTE por linha, BDI = diferença dos totais truncados — use valores
  em que a ordem de truncamento importa); auditoria reprova quando uma célula é
  adulterada e nada é publicado; item sem preço aparece no bloco e não recebe
  preço.
- `tests/valuation/test_canonical_golden.py`: golden canônico novo para a
  planilha do orçamento (mesmo mecanismo `canonicalize_workbook` dos existentes)
  + asserção de idempotência de conteúdo lógico, espelhando
  `test_synthetic_workbook_is_idempotent_in_logical_content` (linha 82-86).

## Out of scope

- `write_valuation_workbook`/`audit_workbook` (medição): nenhuma mudança de
  comportamento; só o modelo de layout ganha a seção opcional.
- `calc.py` e o guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN` (levantado em
  `calc.py:187` e `workbook_writer.py:230`) — intocados.
- API, web, persistência.

## Acceptance criteria

1. `make check` e `make test` verdes; `make valuation-demo` e
   `make valuation-estimate-demo` verdes.
2. Goldens da medição inalterados (byte-idêntico no sentido do repositório:
   conteúdo lógico canônico) — provado pelo diff.
3. Auditoria fail-closed coberta por teste: divergência → nada publicado.
4. Nenhuma cor/fonte nova: a planilha usa o modelo de layout como dado.

## Validation

```bash
make check
make test
uv run pytest tests/valuation/test_estimate_workbook.py tests/valuation/test_canonical_golden.py tests/valuation/test_writer_roundtrip.py -x -q
make valuation-demo
make valuation-estimate-demo
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo, gravado em
docs/features/F-020-orcamento-base-web/tasks/T2-build-report.md.
