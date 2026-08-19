# T5 — Deploy e infra preparados: workflow + Terraform (sem apply)

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core (pinado em
`docs/engineering-os/`), este contrato e os dois repositórios — nada mais.

## Identity

```text
feature_id: F-009
task_id: T5
parent_plan: docs/features/F-009-suite-hospedada-sem-aws/plan.md
depends_on: none
```

## Goal

O workflow de deploy do HML e o Terraform de `biahflow/infra` ficam PRONTOS para a
ativação dos providers reais — flag, envs, secrets, API do Cloud Vision e retenção —
sem nenhum `apply` executado e sem nenhum valor de segredo em lugar algum.

## Scope

Em `/Users/danielcampos/workspace/daniel/croquito` (este repo),
`.github/workflows/deploy-hml.yml`:

- Bloco da API `croquito-scene-hml` (linhas ~139-153): acrescentar
  `CROQUITO_REAL_PROVIDERS_ENABLED=true` ao `--set-env-vars`. A API não recebe chave
  nenhuma.
- Bloco do worker `croquito-jobs-hml` (linhas ~162-175):
  - `--set-secrets`: acrescentar
    `CROQUITO_OPENAI_API_KEY=croquito-hml-openai-api-key:latest,CROQUITO_ANTHROPIC_API_KEY=croquito-hml-anthropic-api-key:latest`.
  - `--set-env-vars`: acrescentar `CROQUITO_REAL_PROVIDERS_ENABLED=true`,
    `CROQUITO_AI_MAX_ESTIMATED_COST_USD=5.00`,
    `CROQUITO_OPENAI_MODEL=gpt-5.6-terra`, `CROQUITO_ANTHROPIC_MODEL=claude-opus-5`,
    `CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS=` (VAZIO de propósito, com comentário no
    workflow: digest do documento autorizado entra por ato humano antes do primeiro
    upload; allowlist vazia = nenhum documento sai para provider — fail closed).
- Comentário curto no bloco do worker explicando o kill switch (flag=false) e que o
  teto é por invocação (reentrega multiplica).

Em `/Users/danielcampos/workspace/daniel/infra` (repo irmão, branch nova
`feat/croquito-hml-providers` a partir de `main`), stack `envs/hml/croquito`:

- Ler o stack inteiro primeiro (main.tf, variables.tf, outputs.tf) e seguir os
  padrões existentes — NADA de padrão novo.
- Dois secrets novos no mapa do módulo de segredos, SEM valor no state, no padrão
  exato do `croquito-hml-kc-bootstrap-admin-password` (~linhas 476-484): casca + IAM,
  valor por ato humano (`gcloud secrets versions add`). Acessor: somente a service
  account do worker (`croquito-jobs`). Comentário no mesmo estilo do KC bootstrap.
- Habilitar `vision.googleapis.com` seguindo o padrão de APIs habilitadas do stack
  (procure `google_project_service`); nenhum role adicional é esperado para chamar o
  Cloud Vision com ADC, mas se o stack tiver padrão de roles por SA, siga-o e anote.
- VERIFICAR se o bucket `croquito-hml-artifacts` tem regra de lifecycle de expiração
  de 7 dias (retenção prometida para respostas brutas de provider). Se não tiver,
  adicionar seguindo o padrão do bucket no próprio stack (ou, se o bucket vier de
  módulo, no ponto certo do módulo). Se a regra existir com outro prazo, NÃO alterar:
  reportar a divergência.

## Out of Scope

- `terraform apply`, `gcloud` mutável, criação de segredo por CLI — PROIBIDOS
  (guardrail global de infraestrutura).
- Valores de segredo, entitlement, Keycloak — atos humanos do runbook (T4).
- Qualquer outro serviço/stack dos dois repositórios.
- Commit no repo irmão: deixar o diff na árvore; o humano revisa e commita.

## Acceptance Criteria

1. Neste repo: `make check` verde (o check roda `terraform fmt -check` no infra/
   local, que não é tocado; e valida links de docs) (checado pela execução).
2. Repo irmão: `terraform -chdir=envs/hml/croquito fmt -check` e
   `terraform -chdir=envs/hml/croquito init -backend=false` +
   `terraform -chdir=envs/hml/croquito validate` verdes (checado pela execução).
   NÃO rode `plan` se ele exigir backend/credencial; nesse caso registre no
   relatório que o plan fica para o humano.
3. `grep` no diff dos dois repos por qualquer coisa parecida com chave/token: nada
   além de NOMES de secret (checado).
4. Diff do repo irmão mostra somente: 2 secrets + IAM, 1 project service, e (se
   ausente) a regra de lifecycle — nada mais (checado por git diff --stat).

## Validation

```text
baseline: make check verde no commit base deste contrato; estado do repo irmão em
          main limpo (git status)
required: full: make check (repo croquito)
          infra: terraform fmt -check + init -backend=false + validate (repo irmão,
                 stack envs/hml/croquito)
```

## Required Capabilities

```text
READ:     os dois repositórios
WRITE:    .github/workflows/deploy-hml.yml (croquito);
          envs/hml/croquito/*.tf (repo irmão, em branch nova)
VALIDATE: make check; terraform fmt/validate (NUNCA apply)
COMMIT:   forbidden nos dois repos — a entrega é o diff mais o BUILD REPORT
```

## Context to Read First

1. `AGENTS.md` e `CLAUDE.md` do croquito; `README`/docs do repo irmão se existirem.
2. `.github/workflows/deploy-hml.yml` por inteiro (282 linhas).
3. `docs/adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md` (padrões D1-D6).
4. Stack `envs/hml/croquito` inteiro no repo irmão.
5. [Feature Contract](../feature.md).

## Known Risks

- Segredo com valor no state por engano — o padrão correto aqui é a casca sem valor
  (chave de terceiro não tem data source que a reconcilie).
- Mexer no bucket errado ou em stack de outro ambiente do repo irmão.
- `terraform validate` pode exigir providers baixados — `init -backend=false` cobre.

## Human Gates

- `terraform plan`/`apply` e os valores dos segredos são atos humanos, fora deste
  contrato (runbook da T4).

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) — todos os campos,
`none` onde vazio — e grave o mesmo conteúdo em
`docs/features/F-009-suite-hospedada-sem-aws/tasks/T5-build-report.md`.
