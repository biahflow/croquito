# T2 — O estado /login na SPA e a regra de rebote sem loop

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente. **É a task de maior risco da
feature: o loop de login mora aqui.**

## Identity

```text
feature_id: F-007
task_id: T2
parent_plan: docs/features/F-007-tela-de-login/plan.md
depends_on: none
```

## Goal

A SPA reconhece `/login` como estado próprio e aplica D3/D4 do
[ADR-0032](../../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md): sem sessão,
`/revisao/` leva a `/login` preservando a query — **exceto quando a URL carrega `code` e
`state`**, que é o retorno do OIDC e é processado onde chega; com sessão, `/login` leva a
`/revisao/`. Tudo coberto por teste automatizado que falharia com a regra ingênua.

## Scope

- `apps/web/src/route.ts` — decisão de representação **delimitada** (é o unknown do
  contrato, resolvido aqui dentro destes limites): ou (a) o estado de path fica numa camada
  acima da jornada (App decide por `window.location.pathname`; `route.ts` continua puro de
  query, no máximo ganhando um helper explícito e comentado), ou (b) `Route` ganha um
  terceiro `kind`. Preferir (a) — preserva o contrato declarado do módulo ("rota deriva só
  da query"). A escolha e o porquê ficam em comentário no código e no relatório.
- `apps/web/src/App.tsx` — a ordem do efeito de sessão é sagrada e já está comentada
  (linhas 41–64: `readSession()` consome o código de uso único ANTES de ler a rota); o
  rebote entra DEPOIS dessa ordem: sem sessão, fora de `/login`, e **sem** `code`+`state` na
  URL → `history.replaceState` para `/login` com a query original preservada; com sessão em
  `/login` → `/revisao/` com a query preservada. `telaAnonima` (linhas 110–117) deixa de ser
  o estado sem sessão (o visual novo é T3 — aqui basta o estado existir e o rebote
  funcionar; um placeholder mínimo sem casca é aceitável nesta task).
- `apps/web/src/App.test.tsx` — o teste que afirma `"Acesse uma revisão autenticada"` é
  **substituído** pela asserção equivalente do desenho novo (critério 10: substituído, não
  apagado); testes novos: (i) `/revisao/?code=…&state=…` **nunca** rebate — falharia com a
  regra ingênua (critério 5); (ii) sem sessão, `/revisao/?job=<uuid>` rebate para `/login`
  preservando `?job` (critério 4); (iii) com sessão, `/login` leva a `/revisao/`
  (critério 3).

## Out of Scope

- `apps/web/src/auth.ts` — **intocado**. O mecanismo de `state`/`redirect_uri` está correto
  (Feature Contract, linha 55). Se este contrato parecer exigir mudança ali, pare e reporte.
- `redirectUris` de qualquer realm — D5: `/login` **não** entra neles; aparecer ali é sinal
  de desenho errado.
- `apps/web/src/styles.css` e o visual da tela (T3).
- Lib de router, estado global novo, UI kit — proibidos pelo `apps/web/AGENTS.md`.

## Acceptance Criteria

1. Os três testes novos existem, passam, e o do critério 5 comprovadamente falha se a
   exceção de `code`+`state` for removida (mostre a falha no relatório: comente a exceção,
   rode, cole o erro, restaure).
2. A asserção antiga foi substituída, nenhum teste removido ou relaxado
   (`git diff apps/web/src/App.test.tsx` como evidência).
3. `make check` e `make test` verdes.
4. Em `npm --workspace @croquito/web run dev`, navegar manualmente confirma: raiz sem
   sessão mostra o estado `/login`; com `?job=` a query sobrevive ao rebote.

## Validation

```text
baseline: make check e make test → verdes no commit base deste contrato
required: full:  make check
          test:  make test
          web:   npm --workspace @croquito/web run test
```

## Required Capabilities

```text
READ:     o repositório (apps/web em particular; ADR-0032; feature.md)
WRITE:    apps/web/src/route.ts, apps/web/src/App.tsx, apps/web/src/App.test.tsx, somente
VALIDATE: make check; make test; npm workspace test; dev server
COMMIT:   forbidden
```

## Context to Read First

1. `AGENTS.md` (raiz), `apps/web/AGENTS.md`, `CLAUDE.md`.
2. [ADR-0032](../../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md) por inteiro — a
   armadilha do retorno OIDC está no Contexto e em D4.
3. `apps/web/src/auth.ts` (leitura, não escrita): `readSession()` linhas 103–127 é quem
   consome `code`+`state`; `signIn()` 162–172 carrega a query no `state`.
4. `apps/web/src/route.ts` e `apps/web/src/App.tsx` por inteiro.
5. `apps/web/src/App.test.tsx` — o padrão de teste e mock existente.

## Known Risks

- **Loop de login**: a regra de rebote interceptando `/revisao/?code=…&state=…` antes de
  `readSession()` fechar a sessão tranca todos para fora. É o critério 1 deste contrato e o
  risco nº 1 da feature — a exceção não é otimização, é a diferença entre produto e
  produto inacessível.
- Primeiro paint antes da decisão de rebote: o que aparece nesse instante não pode ser a
  casca da jornada (D3). Um estado neutro mínimo é aceitável nesta task; T3 o veste.
- Rebote via `history.replaceState` (padrão do app) — redirecionar com reload jogaria fora
  o estado do OIDC em memória.

## Human Gates

- Nenhum dentro do escopo. Commit é humano.

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) e grave o mesmo conteúdo em
`docs/features/F-007-tela-de-login/tasks/T2-build-report.md`.
