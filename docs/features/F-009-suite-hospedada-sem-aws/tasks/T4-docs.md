# T4 — Docs: ADR-0035, Model Routing, runbook do HML, ROADMAP (F-010)

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core (pinado em
`docs/engineering-os/`), este contrato e o repositório — nada mais.

## Identity

```text
feature_id: F-009
task_id: T4
parent_plan: docs/features/F-009-suite-hospedada-sem-aws/plan.md
depends_on: [T1, T2, T3]
```

## Goal

A documentação passa a dizer a verdade nova: ADR-0035 registra a decisão (suite
hospedada sem AWS), o Model Routing descreve as rotas e falhas reais, o HML.md ganha
o runbook de ativação com os atos humanos, e o ROADMAP ganha a F-010 aprovada.

## Scope

- **`docs/adr/0035-suite-hospedada-openai-anthropic-direto.md`** (novo, status
  `Proposed` — aceitação é ato humano; siga o formato dos ADRs vizinhos):
  - Contexto: HML em GCP (ADR-0025); credenciais disponíveis são OpenAI e Anthropic
    diretas; ADR-0002 escolheu Bedrock/Textract num desenho AWS que não é o ambiente
    publicado; o caminho AWS nunca rodou; a chamada de OCR do Textract era código
    morto e o fallback `OCR_EVIDENCE_MISSING` documentado nunca fora implementado
    (divergência doc×código resolvida a favor da realidade).
  - Decisão (espelhe o que o código pós-T1/T2/T3 FAZ — leia os diffs e os build
    reports das tasks antes de escrever): suite `openai`+`anthropic`+`ocr` (Cloud
    Vision), Anthropic primário/OpenAI fallback com notas `PROVIDER_FALLBACK_*` e
    degradação para `AMBIGUOUS`, corroboração de OCR por leitura, rótulos honestos
    (`dataset_id`, `created_by`, `providers_json`), 401/403 não-retryável, teto
    US$ 5/rodada, allowlist por env var, kill switch pela flag.
  - Consequências: revisita parcialmente o ADR-0002 (a suite HOSPEDADA deixa de
    depender de AWS; se produção um dia for AWS, religar Bedrock é decisão nova com
    eval); custo de reentrega (teto é por invocação; DLQ em 5 entregas ⇒ pior caso
    5×teto); respostas brutas retidas 7 dias no bucket.
  - Alternativas consideradas: Vertex AI (preço por token igual, ganhos só
    enterprise), Document AI (registrado como ESCALADA do OCR se o eval de recall
    reprovar na prancha real — decisão do usuário 2026-08-19), manter Bedrock.
  - Pendências registradas: rota de plataforma para allowlist; multi-página;
    pacote só-CV; UX do JOB_NOT_READY; roteamento por tarefa no braço Anthropic;
    eval do braço OpenAI de geometria; default `bedrock:` do extraction-eval; F-010.
- **`docs/ai/MODEL_ROUTING.md`**: rotas padrão novas (braço primário Anthropic
  direto `claude-opus-5`, contraparte/fallback OpenAI `gpt-5.6-terra`, OCR Cloud
  Vision; sem Textract/Bedrock na suite hospedada), seção de falhas com a semântica
  real (notas `PROVIDER_FALLBACK_*`, `OCR_EVIDENCE_MISSING`/`OCR_UNAVAILABLE`,
  BUDGET_EXCEEDED sem fallback), fechar a pendência das linhas ~29-35 (lista de
  providers do consent atualizada), atualizar o estado de implementação.
- **`docs/operations/HML.md`**: seção "Providers de IA" com envs/segredos e o
  runbook de ativação (na ordem): 1) criar os dois GitHub Actions secrets no repo
  biahflow/infra (`gh secret set CROQUITO_OPENAI_API_KEY --repo biahflow/infra` e o
  equivalente Anthropic) — a esteira os transforma em `TF_VAR_*` e o Terraform grava
  casca E valor; sem eles o plan falha fail-closed; 2) commitar a branch
  `feat/croquito-hml-providers` e abrir PR — o `plan` do stack `envs/hml/croquito`
  roda NO PR (resumo do job) e é ali que se revisa; o merge na main APLICA via
  esteira (`apply.yml`) — não existe apply manual nem `gcloud secrets versions add`; 3) Keycloak: role `platform_operator` + `tenant_id`
  (HML_KEYCLOAK.md); 4) `PUT /api/v1/platform/tenants/<tenant_id>/ai-processing-entitlement`
  com `agreement_reference` (comando curl pronto); 5) `shasum -a 256 <pdf>` → digest
  em `CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS` no workflow; 6) merge (= deploy);
  7) re-upload do PDF (o job antigo nasceu sem consent); 8) rollback = flag `false`.
  Inclua o aviso de custo (teto por invocação × reentrega).
- **`ROADMAP.md`** (ou o índice canônico que o repo usar — confira): entrada F-009
  (IN_PROGRESS→READY_FOR_REVIEW conforme o estado real na sua execução) e entrada
  nova **F-010 — revisão assistida em lote** (BACKLOG/READY_FOR_SPEC, prioridade a
  definir, aprovada por ato humano de 2026-08-19): leitura com tripla concordância
  (LLMs concordam + OCR confirma + associação única + solver fecha na tolerância)
  nasce pré-aceita em lote; revisor faz uma conferência e um ato de aprovação; gate
  humano e portão de exportação intocados; calibração depende dos dados desta
  entrega.
- **`docs/STATUS.md`**: atualizar se o marco mudou (leia o arquivo e decida; se não
  mudar, diga por quê no relatório).
- **`docs/features/F-009-suite-hospedada-sem-aws/feature.md`**: atualizar Status
  para o estado real ao fim da sua execução.

## Out of Scope

- Código. Mudar qualquer decisão — você REGISTRA o que foi decidido e implementado.
- `evidence.md` da F-009 (montado na integração, fora deste contrato).

## Acceptance Criteria

1. `make check` verde — em particular `scripts/check_docs.py`, que valida TODO link
   relativo de Markdown do repositório (checado pela execução).
2. ADR-0035 espelha o comportamento implementado (confira contra os diffs reais, não
   contra o plano).
3. Runbook executável por um humano sem contexto da conversa.
4. F-010 presente no ROADMAP com a aprovação datada.

## Validation

```text
baseline: make check verde após T1/T2/T3 na branch
required: full: make check
```

## Required Capabilities

```text
READ:     o repositório (inclusive git diff das tasks anteriores)
WRITE:    docs/ e ROADMAP.md somente
VALIDATE: make check
COMMIT:   forbidden — a entrega é o diff na árvore mais o BUILD REPORT
```

## Context to Read First

1. `AGENTS.md` (seção "Disciplina de mudança") e `CLAUDE.md`.
2. Os build reports T1/T2/T3 em `docs/features/F-009-suite-hospedada-sem-aws/tasks/`
   e o `git diff` acumulado da branch.
3. `docs/adr/0031-*.md` e `docs/adr/0032-*.md` como referência de formato.
4. `docs/ai/MODEL_ROUTING.md` e `docs/operations/HML.md` inteiros.
5. [Feature Contract](../feature.md) e [plano](../plan.md).

## Known Risks

- Link relativo quebrado reprova o CI — rode `make check` antes de encerrar.
- Registrar intenção em vez de realidade: o ADR descreve o que o código FAZ.

## Human Gates

- Aceitação do ADR-0035 é ato humano posterior (status nasce `Proposed`).

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) e grave o mesmo
conteúdo em `docs/features/F-009-suite-hospedada-sem-aws/tasks/T4-build-report.md`.
