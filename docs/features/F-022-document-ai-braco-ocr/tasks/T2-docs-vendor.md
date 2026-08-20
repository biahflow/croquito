# T2 — Docs de vendor e operação atualizados para a suite real

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente. **Depende de T1 aplicada na
árvore** — descreva o que existe, nunca o que ainda não existe.

## Identity

```text
feature_id: F-022
task_id: T2
parent_plan: docs/features/F-022-document-ai-braco-ocr/plan.md
depends_on: [T1]
```

## Goal

Os documentos de vendor, privacidade e operação passam a descrever a suite REAL
(Anthropic + OpenAI direto, OCR Cloud Vision com escalada Document AI por
configuração), fechando defasagens preexistentes mapeadas em 2026-08-20. Regra única:
**cada afirmação nova aponta código, ADR ou feature** — nada de estado desejado.

## Scope

- `docs/ai/MODEL_ROUTING.md`: tabela de rotas (linha ~19) e "Estado de implementação
  local" (85-99) ganham o braço Document AI condicionado a `CROQUITO_DOCAI_PROCESSOR`,
  citando ADR-0037; a seção de falhas (138-145) continua correta — confira e ajuste só
  se T1 mudou algo observável.
- `docs/operations/HML.md`: seção de providers (263-293) ganha os dois atos de infra
  pendentes como PENDENTES (habilitar `documentai.googleapis.com` e provisionar o
  processador no repositório `biahflow/infra`; definir o env no serviço) — sem afirmar
  que existem.
- `docs/operations/RUNBOOK_PROCESSING_FAILURES.md` (28-32): a seção "Textract failure"
  vira a seção real do braço OCR: `OCR_UNAVAILABLE` (braço ausente/falha permanente),
  nota por leitura `READING_{n}_OCR_EVIDENCE_MISSING`, `BUDGET_EXCEEDED` propaga.
  Vendor citado: Cloud Vision hoje, Document AI por configuração (ADR-0037).
- `docs/security/AI_VENDOR_RISK.md`: tabela (7-13) reflete a suite real — Anthropic
  direto, OpenAI direto, Google Cloud Vision / Document AI (OCR auxiliar); Bedrock e
  Textract saem da tabela ativa para uma linha de histórico apontando ADR-0035.
  Atualize a data de revisão.
- `docs/security/PRIVACY_LGPD.md` (linha ~54, suboperadores): Google (Cloud Vision /
  Document AI) entra; AWS/Bedrock/Textract qualificados como desenho histórico
  (ADR-0002) não exercido pela suite hospedada (ADR-0035). Cuidado com afirmações
  legais: liste suboperadores, não invente cláusula.
- `AGENTS.md` raiz (linha ~90): "Textract ajuda a localizar e transcrever" vira a
  frase equivalente com o braço real ("o OCR auxiliar corrobora, não determina
  geometria"), sem vendor fixo.
- `docs/STATUS.md`: linhas 89-93 e 762 ("Textract como OCR auxiliar") atualizadas para
  o estado real com ponteiro a ADR-0035/0037 — o registro histórico das seções de
  época NÃO é reescrito; corrija só onde o texto afirma presente.

## Out of scope

- ADRs aceitos (0002, 0004): imutáveis.
- `docs/product/ROADMAP.md` linhas 89/93 (registro de época).
- Código, testes, Makefile.

## Acceptance criteria

1. `make check` verde (check_docs valida todos os links).
2. Nenhuma frase nova afirma infra provisionada ou eval executado — pendências
   escritas como pendências.
3. Datas de "última revisão" atualizadas onde o documento as carrega.

## Validation

```bash
make check
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT.

## Report

`BUILD REPORT` completo, em
docs/features/F-022-document-ai-braco-ocr/tasks/T2-build-report.md.
