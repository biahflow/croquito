# F-009 — Evidência de execução

feature_id: F-009

status: `DONE` (entrega aceita por ato humano em 2026-08-23)

data: 2026-08-23

## Round

```text
round: 1
reviewed_commit_or_state: main@5ae7a13 antes do fechamento documental
authorization: aceite explícito do ADR-0035 e da entrega pelo usuário em 2026-08-23
```

## 1. Contrato e plano

- [Feature Contract](feature.md)
- [Plano de execução](plan.md)
- Task Contracts e respectivos `BUILD REPORTS` em [tasks/](tasks/)
- [ADR-0035](../../adr/0035-suite-hospedada-openai-anthropic-direto.md), aceito por ato
  humano em 2026-08-23

## 2. Baseline

Antes da F-009, o upload real no HML terminava em `REVIEW_REQUIRED` sem pacote de revisão:
a suite hospedada tentava montar Bedrock/Textract sem credencial AWS válida no ambiente GCP,
a chamada de Textract era descartada e não existia fallback entre provedores.

## 3. Mudança

| Task | Entrega | Evidência primária |
| --- | --- | --- |
| T1 | Suite hospedada OpenAI + Anthropic direto, sem `boto3`, com lineage e falha de credencial honestos | [Build Report](tasks/T1-build-report.md) |
| T2 | Fallback por tarefa, degradação declarada e `BUDGET_EXCEEDED` sem fallback | [Build Report](tasks/T2-build-report.md) |
| T3 | Braço OCR Cloud Vision com corroboração por leitura e eval sintética | [Build Report](tasks/T3-build-report.md) |
| T4 | ADR, roteamento, runbook e roadmap reconciliados | [Build Report](tasks/T4-build-report.md) |
| T5 | Deploy e infraestrutura preparados; PRs de infra posteriormente aplicados | [Build Report](tasks/T5-build-report.md) |

## 4. Validação e integração

- A implementação foi integrada na `main` pelo PR #19, merge `8333956`.
- Os Build Reports registram `make check`, `make test`, testes de fallback/lineage e
  `make ocr-eval` verdes nas respectivas tasks.
- A infraestrutura foi aplicada pelos PRs `biahflow/infra#14` e `#15`: secrets com valor
  write-only, Vision API habilitada e retenção de sete dias no bucket de artefatos.
- O caminho real foi exercitado no HML. A V12 usou o pareamento OpenAI + Anthropic; depois,
  a série V14–V17 produziu pacotes reais com Anthropic e OCR. A V17, já sob a escalada
  posterior para Document AI, extraiu 29 leituras.
- O braço OpenAI foi desligado por configuração depois da V12 porque o pareamento espacial
  associou caixas de extensões diferentes. A capacidade de dois braços e fallback continua
  implementada; o modo de braço único é explícito, gera
  `PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC` e mantém as leituras ambíguas.

## 5. Revisão e decisão humana

O pacote implementado, integrado, aplicado e exercitado no HML foi aceito pelo usuário em
2026-08-23. Na mesma decisão, o ADR-0035 passou de `Proposed` para `Accepted` e a feature de
`READY_FOR_REVIEW` para `DONE`.

## 6. Fechamento documental

Em 2026-08-23, `scripts/check_docs.py` confirmou 385 documentos Markdown válidos e a paridade
de lifecycle. Depois de instalar as dependências que faltavam no ambiente local, `make check`
passou integralmente e `make test` concluiu com 2.378 testes Python aprovados (13 skips
condicionais), 1.075 testes da web e 261 testes do app de campo aprovados.

## 7. Desvios, riscos e pendências

- A allowlist por digest descrita originalmente no D6 do ADR-0035 foi removida do caminho
  hospedado pela F-012/ADR-0036. Ela permanece apenas no caminho offline de eval.
- Document AI como braço alternativo de OCR pertence à F-022/ADR-0037 e não é aceito por
  este fechamento; o ADR-0037 permanece `Proposed`.
- Multi-página, pacote só-CV e UX de `JOB_NOT_READY` continuam fora do escopo original.
