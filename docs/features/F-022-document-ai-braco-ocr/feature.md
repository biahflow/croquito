# F-022 — Document AI como braço de OCR

## Status

`DONE`

> **Aceite humano em 2026-08-28.** O [ADR-0037](../../adr/0037-document-ai-como-braco-de-ocr.md)
> passou a `Accepted` na mesma data, por ato humano. Dívida declarada, não exercida:
> provisionamento GCP e definição do env em HML; eval comparativo pago antes de promover o
> braço em HML.

> Selecionada por decisão humana de 2026-08-20, na mesma sessão da F-021: a segunda
> revisão real do Guaxindiba chegou com 10 leituras onde a folha escreve ~16 números.
> O usuário exerceu a escalada que o ADR-0035 já registrava nominalmente
> ([ADR-0037](../../adr/0037-document-ai-como-braco-de-ocr.md), Accepted).

> Executada em 2026-08-20 (T1 adapter + T2 docs, builds completos, revisão do
> orquestrador, portões integrados verdes).

## Classification

Não é `INTERFACE_CHANGE` — troca de fornecedor atrás do mesmo contrato interno
(`OcrOutput`). É mudança de suboperador de dados: os documentos de vendor risk e LGPD
acompanham (ver Scope).

## Priority

`HIGH` — cada número que o OCR alcança é uma cota a mais corroborada e, com a F-021,
menos gesto manual na revisão.

## Problem

O braço de OCR (Cloud Vision `document text detection`) perdeu 6 de ~16 números da
prancha real manuscrita. `make ocr-eval` mede 100% na fixture sintética porque ela não
tem letra manuscrita — o gate não enxerga o problema real.

## Desired Outcome

Suite hospedada montando Document AI como braço de OCR quando configurado, com o mesmo
contrato, retry, budget, raw-store e lineage de hoje; Cloud Vision permanece montável
sem o env novo, e a promoção em HML é decidida por eval comparativo contra a prancha
real.

## Scope

1. **Adapter** — `GcpDocumentAiOcrAdapter` em
   `services/worker/src/croquito_worker/providers.py`, espelhando o desenho de
   `GcpVisionOcrAdapter` (linhas 1945-2065): REST puro + token ADC via `google-auth`,
   `ProviderName` novo, `model_id` próprio, parse de
   `document.pages[].lines[].layout` com `normalizedVertices` → `OcrLineOutput`,
   erro-em-200 e status HTTP mapeados como os demais adapters REST, raw-store por
   digest do documento.
2. **Montagem por configuração** — `build_real_provider_suite` monta Document AI
   quando `CROQUITO_DOCAI_PROCESSOR` está definido; sem ele, Cloud Vision como hoje.
   Custo por chamada continua em `CROQUITO_AI_ESTIMATED_COST_PER_OCR_CALL_USD`.
3. **Logs do braço** — `_ocr_failure` deixa de fixar `gcp_vision` no nome e loga o
   provider do adapter que falhou.
4. **Testes** — espelho da bateria do adapter atual (`tests/worker/test_providers.py`):
   parse de resposta real-shaped, bbox normalizada, erro-em-200, mapeamento HTTP,
   token, montagem da suite com e sem o env novo.
5. **Docs** — [ADR-0037](../../adr/0037-document-ai-como-braco-de-ocr.md) referenciado
   pelo índice; `docs/ai/MODEL_ROUTING.md` (tabela de rotas e estado de implementação);
   `docs/operations/HML.md` (API `documentai.googleapis.com` + processador como atos de
   infra no repositório externo); `docs/security/AI_VENDOR_RISK.md` e
   `docs/security/PRIVACY_LGPD.md` atualizados para a suite REAL atual (hoje ainda
   listam AWS/Textract e nem citam Google — defasagem preexistente que esta feature
   fecha porque toca as mesmas tabelas); `docs/operations/RUNBOOK_PROCESSING_FAILURES.md`
   seção de OCR reescrita para o comportamento real (`OCR_UNAVAILABLE` por braço,
   nota por leitura) — hoje descreve Textract e semântica antiga.

## Out of Scope

- Provisionar o processador/habilitar API (repositório `biahflow/infra`, ato humano).
- Rodar o eval comparativo pago (depende do processador existir; gate de promoção).
- Remover `GcpVisionOcrAdapter` (precedente ADR-0035 D1: classe fica).
- Mudar `OcrOutput`/corroboração em `provider_review.py`.
- Colocar OCR em `providers_json` (D4 do ADR-0035 permanece).

## Acceptance Criteria

1. `make check` e `make test` verdes; `make provider-contract-demo` e `make ocr-eval`
   continuam verdes sem credencial.
2. Suite real com `CROQUITO_DOCAI_PROCESSOR` monta Document AI; sem ele, Cloud Vision —
   ambos cobertos por teste com `google.auth.default` monkeypatchado.
3. O hash congelado do prompt `ocr` em `test_prompt_hashes_of_existing_tasks_are_frozen`
   NÃO muda (o template é da tarefa, não do vendor).
4. Nenhum log do adapter novo carrega imagem, texto integral, token ou URL assinada.
5. Todos os documentos do item 5 do Scope atualizados; `make check` (check_docs) verde.

## Constraints

- REST + `google-auth` puro; sem SDK do Document AI (padrão do módulo).
- Linha sem bbox utilizável é recusada, nunca inventada.
- `BUDGET_EXCEEDED` propaga; falha permanente degrada para `OCR_UNAVAILABLE`.

## Dependencies

- ~~[ADR-0037](../../adr/0037-document-ai-como-braco-de-ocr.md) — Proposed nesta data;
  aceite é ato humano.~~ — **`Accepted` por ato humano em 2026-08-28.**
- Processador Document AI provisionado (ato externo; não bloqueia o código).

## Human Gates

- ~~Aceite do ADR-0037.~~ — **satisfeito em 2026-08-28.**
- Provisionamento GCP e definição do env em HML (deploy é ato humano).
- Eval comparativo pago antes de promover o braço em HML.
