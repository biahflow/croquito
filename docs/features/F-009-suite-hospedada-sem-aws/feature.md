# F-009 — Suite hospedada de providers: OpenAI + Anthropic direto, sem AWS

## Status

`DONE`

> Selecionada, especificada e autorizada por decisões humanas de 2026-08-19, na mesma
> conversa que diagnosticou o upload real parado em `JOB_NOT_READY` no HML. O usuário
> aprovou explicitamente: chamada paga de provider, envio do documento a serviço
> externo, suite sem AWS (Anthropic primário, OpenAI fallback), braço de OCR
> determinístico via Cloud Vision, teto de US$ 5 por rodada e allowlist por env var.
>
> Implementação integrada na `main` pelo merge `8333956`, infraestrutura aplicada e caminho
> real exercitado no HML nas rodadas V12 e V14–V17. A allowlist hospedada original foi
> removida pela F-012; o braço OpenAI foi desligado depois da V12 por decisão operacional,
> sem remover a capacidade de fallback. O ADR-0035 e a entrega foram aceitos por ato humano
> em 2026-08-23. Evidência em [evidence.md](evidence.md).

## Priority

`HIGH` — definida por ato humano em 2026-08-19. É o desbloqueio do produto no HML:
sem ela, todo upload real termina validado porém sem pacote de revisão, e a jornada
completa (revisão → solver → aprovação → DXF) só existe localmente com fixtures.

## Problem

Um PDF real subido no HML termina em `REVIEW_REQUIRED` sem pacote de revisão — a UI
mostra `JOB_NOT_READY` para sempre. O worker hospedado
(`services/worker/src/croquito_worker/local_queue.py`, `_handle_upload`) só cria
pacote quando existe provider suite, e o HML roda com
`CROQUITO_REAL_PROVIDERS_ENABLED` desligado. A cadeia OpenCV sozinha nunca produz
cotas; quem monta o pacote é `build_provider_review_snapshot`.

Três defeitos latentes agravam o quadro, todos verificados em 2026-08-19:

- `build_real_provider_suite` monta Bedrock/Textract via boto3 **sem credencial
  explícita** — no HML, `AWS_ACCESS_KEY_ID/SECRET` são as chaves HMAC do GCS. O
  caminho AWS nunca rodou neste projeto; as evals pagas reais usaram OpenAI e
  Anthropic por API direta.
- A chamada de OCR do Textract no snapshot é **código morto**: executa, valida o
  schema e descarta o resultado (`provider_review.py:184-190`). O fallback
  `OCR_EVIDENCE_MISSING` documentado em MODEL_ROUTING.md nunca foi implementado.
- Não existe fallback provider→provider: falha permanente de um braço derruba o job
  inteiro para reentrega.

## Desired Outcome

Upload de PDF real no HML atravessa a cadeia inteira: providers reais (Anthropic
primário + OpenAI comparado/fallback) extraem cotas e geometria, um OCR
determinístico (Cloud Vision) corrobora o texto de cada leitura, o pacote de revisão
nasce completo, e a revisão humana → solver → aprovação → DXF funcionam como no
local. Degradação é transparente (notas de segurança, leituras `AMBIGUOUS`), nunca
silenciosa. Nada vira exportável sem decisão humana — invariantes intactos.

## Scope

- `ProviderSuite` com braços honestos `openai` + `anthropic` (+ `ocr` opcional);
  `build_real_provider_suite` sem boto3/AWS; suite sintética espelhada.
- Fallback por tarefa com notas de segurança (Anthropic primário, OpenAI fallback);
  `BUDGET_EXCEEDED` nunca aciona fallback.
- Braço OCR Cloud Vision (document text detection) autenticado pela service account,
  com corroboração real por leitura e portão de eval de recall.
- Rótulos honestos: `dataset_id` derivado do job, `created_by` por origem da suite,
  `providers_json` refletindo a suite nova; 401/403 não-retryável.
- Deploy HML: flag na API e no worker, secrets das duas chaves via Terraform
  (`biahflow/infra`), teto, modelos, allowlist por digest.
- ADR-0035, MODEL_ROUTING.md, runbook em HML.md, F-010 registrada no ROADMAP.

## Out of Scope

Rota de plataforma para allowlist; multi-página além da 1ª; pacote só-CV; UX do
`JOB_NOT_READY`; roteamento por tarefa dentro do braço Anthropic; Claude via Vertex
AI; Document AI (registrado como escalada do OCR se o eval reprovar); default
`bedrock:` do `make extraction-eval`; fluxos `build_extraction_arm`/valuation
(intocados); F-010 — revisão assistida em lote (feature própria, aprovada
2026-08-19, especificação futura).

## Acceptance Criteria

1. `make check` e `make test` verdes; nenhum drift de contrato TS.
2. Nenhuma referência a `suite.textract`/`suite.bedrock_anthropic` no código; nenhum
   boto3 no caminho hospedado da suite real.
3. Fallback coberto por testes: survey/extração/geometria degradam com as notas
   `PROVIDER_FALLBACK_*`, extração em braço único nasce toda `AMBIGUOUS`,
   `BUDGET_EXCEEDED` propaga sem chamar o segundo braço, dupla falha propaga, nenhum
   caminho degradado produz leitura `proposed` nem pacote exportável.
4. OCR: leitura confirmada registra a confirmação; não confirmada ganha
   `OCR_EVIDENCE_MISSING`; OCR indisponível degrada com nota sem derrubar o job;
   eval de recall de confirmação verde na prancha sintética.
5. Deploy preparado (workflow + Terraform com plan limpo) sem nenhum apply executado
   por agente; runbook dos atos humanos completo em HML.md.
6. Pós-ativação (atos humanos): upload real no HML → `GET /v1/jobs/{id}/review` 200
   com leituras de lineage `[anthropic, openai]` e propostas associadas.

## Human Gates

Todos os gates da feature foram exercidos: ADR-0035 aceito, PRs de infraestrutura aplicados,
segredos configurados, merge/deploy concluído e uploads reais processados no HML. O
entitlement passou a ser operado pela F-012 e a allowlist hospedada deixou de existir.

## References

- [Plano de execução](plan.md)
- [Evidência de execução](evidence.md)
- [ADR-0002 — arquitetura AWS gerenciada](../../adr/0002-aws-managed-architecture.md)
  (revisitado parcialmente pelo ADR-0035)
- [ADR-0025 — homologação em GCP Cloud Run](../../adr/0025-homologacao-em-gcp-cloud-run.md)
- [ADR-0031 — segredo de homologação por Terraform](../../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md)
- [Model Routing](../../ai/MODEL_ROUTING.md)
- [Operação do HML](../../operations/HML.md)
