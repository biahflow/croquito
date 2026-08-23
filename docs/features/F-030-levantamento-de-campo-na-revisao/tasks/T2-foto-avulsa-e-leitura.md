# T2 — Foto avulsa e leitura textual sob demanda

## Identity

```text
feature_id: F-030
task_id: T2
parent_plan: docs/features/F-030-levantamento-de-campo-na-revisao/plan.md
depends_on: T1
```

## Goal

O revisor adiciona ao job uma foto avulsa JPEG, PNG ou WebP, confirma seus bytes por digest
e, quando pedir explicitamente, solicita a leitura textual já contratada pela F-032.

## Scope

- Registros de foto avulsa e estado de análise/classificação previstos pela migration `0017`.
- Presign e confirmação com digest, MIME permitido e âncora textual declarada.
- Foto avulsa na composição de `field-evidence`, indistinguível na apresentação mas com origem.
- Solicitação explícita de `FIELD_PHOTO_READING`, fila/worker e estado honesto de execução.
- Testes de mídia inválida, digest divergente, confirmação ausente, papel e tenant.

## Out of Scope

PDF, inferência de âncora, chamada automática no upload/vínculo, classificação visual, web.

## Acceptance Criteria

1. Só `image/jpeg`, `image/png` e `image/webp` recebem presign; tamanho e digest são validados.
2. Apenas mídia confirmada aparece e pode ser analisada; digest divergente é recusado.
3. Upload, confirmação e vínculo fazem zero chamada paga.
4. A leitura reutiliza `PromptTask.FIELD_PHOTO_READING` e só nasce por solicitação explícita.
5. Tenant/papel incorreto não recebe metadado nem URL e as mutações são idempotentes/versionadas.
6. `make test` passa com cobertura da API e do worker criada pela task.

## Validation

```text
baseline: T1 BUILD_COMPLETE e gates verdes
required: make check
required: make test
```

## Required Capabilities

```text
READ:     packages/core, services/api, services/worker, tests, docs
WRITE:    packages/core, services/api, services/worker, tests, docs
VALIDATE: comandos de Validation
COMMIT:   allowed
```

## Context to Read First

ADR-0049 decisões 8, 12–14; T1 e seu report; `services/api/AGENTS.md`;
`services/worker/AGENTS.md`; upload de prancha; `survey_photo_analysis.py`.

## Known Risks

Disparar custo sem ato humano, aceitar tipo pelo nome do arquivo, persistir URL assinada ou
confundir texto escrito com medida confirmada.

## Human Gates

Nenhum. A rodada paga é explicitamente proibida nesta task.

## Reporting

Criar `T2-build-report.md` com o `BUILD REPORT` completo.
