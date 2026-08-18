# T5 — A rede de smoke atravessa o desenho novo, sem afrouxar

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente. A regra desta task é uma frase: **o
teste se adapta ao desenho novo; a garantia não afrouxa**. Se algo não passar, a task para e
reporta — consertar app, borda ou tema é escopo de outra task.

## Identity

```text
feature_id: F-007
task_id: T5
parent_plan: docs/features/F-007-tela-de-login/plan.md
depends_on: [T1, T2, T3, T4]
```

## Goal

O smoke de borda cobre a porta nova (`/` → 302 `/login`; `/login` → SPA) e o e2e headless
atravessa o fluxo completo novo — tela de login → Keycloak com tema → volta com `?job`
preservado — mantendo cada seletor e asserção de hoje. Critérios 1 (parte remota) e 6 do
[Feature Contract](../feature.md).

## Scope

- `scripts/smoke_hml.py` — em `montar_verificacoes()` (linhas 201–224), duas verificações
  novas, no padrão das existentes:
  1. `GET /` com `seguir_redirect=False` → `302` com `Location` `/login` (espelhar o check
     de `/medicao/`, linhas 208–213).
  2. `GET /login` → `200` servindo a SPA (espelhar a asserção de conteúdo usada para
     `/revisao/`).
  Os quatro checks existentes **não mudam**.
- `apps/web/e2e/smoke-headless.mjs` — o fluxo se adapta: a partida continua sendo
  `${WEB_URL}/?job=…` (linhas 145–147); com o desenho novo, o que aparece sem sessão é a
  tela de login (o clique passa do botão da topbar para o CTA "Entrar" da tela); o resto da
  cadeia permanece intacto: espera de `#kc-form-login, input[name='username']` (linha 169 —
  o tema mantém os nomes padrão), submit, espera de `"Sessão:"`, asserção de que `code` saiu
  da URL e de que `?job` sobreviveu (linhas 174–189). **Nenhum seletor genérico novo,
  nenhuma asserção removida ou enfraquecida, nenhum timeout inflado para mascarar problema.**

## Out of Scope

- Qualquer arquivo de app, borda, tema ou realm — se o fluxo não fecha, é achado, não
  conserto seu.
- Os quatro checks existentes do `smoke_hml.py` (SPA, medição, API, OIDC discovery).
- `make smoke-local` e a cadeia de CI — não mudam nesta task.

## Acceptance Criteria

1. `smoke_hml.py` com os dois checks novos passa contra o stack local completo (checado
   pela execução); o diff mostra os quatro checks antigos intactos (checado por
   `git diff scripts/smoke_hml.py`).
2. `smoke-headless.mjs` verde contra o stack local partindo de `?job=<uuid>`, terminando no
   job, com `code` fora da URL final (critério 6; checado pela execução com a saída colada
   no relatório).
3. Prova de não afrouxamento: `git diff apps/web/e2e/smoke-headless.mjs` não remove nenhuma
   das esperas/asserções listadas no Scope (checado por leitura do diff, citado no
   relatório).
4. `make check` e `make test` verdes.

## Validation

```text
baseline: T1–T4 integradas na branch; make check e make test verdes; stack local sobe com
          make dev-services && make db-init && make dev-api (+ web dev server)
required: full:  make check
          test:  make test
          smoke: CROQUITO_ALLOW_TEST_TOKENS=true make smoke-local
          e2e:   execução do apps/web/e2e/smoke-headless.mjs contra o stack local
```

Se o stack local completo não puder subir no seu ambiente, encerre
`BUILDER_VALIDATION_BLOCKED` nomeando o que faltou — não declare completo sem a execução
real dos dois smokes.

## Required Capabilities

```text
READ:     o repositório
WRITE:    scripts/smoke_hml.py e apps/web/e2e/smoke-headless.mjs, somente
VALIDATE: make check/test; stack local completo (docker); navegador headless do e2e
COMMIT:   forbidden
```

## Context to Read First

1. `AGENTS.md` (raiz) e `CLAUDE.md` (seção do ambiente local completo).
2. `scripts/smoke_hml.py` por inteiro — o padrão de verificação e o porquê da asserção de
   issuer.
3. `apps/web/e2e/smoke-headless.mjs` por inteiro — cada espera existente é uma garantia com
   história; o comentário da linha 169 explica o acoplamento com o tema.
4. [Feature Contract](../feature.md), critérios 1 e 6 e o risco "o smoke é a única rede".

## Known Risks

- O anti-padrão desta task tem nome no contrato da feature: afrouxar o smoke para caber no
  desenho novo — a feature entregaria a tela e perderia a garantia.
- O CTA novo e o botão antigo da topbar podem coexistir por um instante da migração; o e2e
  deve clicar no CTA da tela, não num seletor frouxo que ache "qualquer botão Entrar".

## Human Gates

- Nenhum dentro do escopo.

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) e grave o mesmo conteúdo em
`docs/features/F-007-tela-de-login/tasks/T5-build-report.md`.
