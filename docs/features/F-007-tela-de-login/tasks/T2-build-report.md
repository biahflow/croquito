# T2 — BUILD REPORT

Evidência primária de execução da [T2](T2-estado-login-e-rebote.md), no formato exigido pelo
[contrato do Builder](../../../engineering-os/agents/builder.md).

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - apps/web/src/route.ts — a porta de entrada ganha representação FORA de `Route`
    (opção (a) do contrato): `LOGIN_PATH`, `isLoginPath`, `normalizeSearch` e a decisão
    pura `entryRedirect(location, hasSession, journeyPath)`, com a exceção de
    `code`+`state` como primeira cláusula. O contrato do módulo ("a rota deriva só da
    query") continua valendo: `Route` não mudou.
  - apps/web/src/App.tsx — `applyEntryRedirect(hasSession)` aplica a decisão com
    `history.replaceState`; é chamado DEPOIS da ordem sagrada do efeito de sessão (e
    também no caminho sem OIDC configurado e no caminho de erro de sessão, onde
    `readSession()` não estabeleceu nada). `telaAnonima` virou `telaLogin`, o estado sem
    sessão da porta de entrada, com texto de PLACEHOLDER declarado em comentário.
  - apps/web/src/App.test.tsx — a asserção "Acesse uma revisão autenticada" foi
    SUBSTITUÍDA por "Entre para continuar" nos dois testes que a usavam; nenhum teste
    removido, nenhuma asserção relaxada. Cinco testes novos no describe "rebote da porta
    de entrada".

Validation executed:
  - baseline (commit base, antes de qualquer edição): `make check` → exit 0;
    `make test` → exit 0 (1438 passed, 10 skipped no pytest; 522 passed no vitest).
  - final: `make check` → exit 0 (ruff, ruff format, mypy strict, check_docs, schema
    export --check, contracts:check, web:check = tsc -b + vite build, terraform fmt).
  - final: `make test` → exit 0 (pytest 1438 passed, 10 skipped, 120s; vitest 28 files,
    527 passed).
  - final: `npm --workspace @croquito/web run test` → 28 files, 527 passed
    (522 do baseline + 5 novos).
  - mutação do critério 1 (a exceção de `code`+`state` removida de `entryRedirect`,
    depois RESTAURADA):
        FAIL src/App.test.tsx > rebote da porta de entrada > nunca rebate o retorno do
        OIDC, mesmo sem sessão
        AssertionError: expected '/login?code=abc123&state=xyz789' to be null
    Restaurado o arquivo, `npm --workspace @croquito/web run test -- src/App.test.tsx` →
    8 passed. O loop de login é reproduzível e o teste o pega.
  - critério 4 (dev server, `npm --workspace @croquito/web run dev` em :5173, base `/`,
    navegação real em Chromium):
        /                                    -> /login                     h1="Entre para continuar"
        /?job=0198f0a1-…-1a2b3c4d5e6f        -> /login?job=0198f0a1-…      h1="Entre para continuar"
        /login                               -> /login                     h1="Entre para continuar"
        /?rodada=                            -> /login?rodada=             h1="Entre para continuar"
        /?job=abc&code=fake123&state=fakestate -> /login?job=abc; nenhuma chamada ao
        provedor OIDC interceptada por rebote: o retorno foi PROCESSADO por
        `readSession()` (que limpou `code`/`state` da URL e preservou o `?job`), e só
        depois o rebote levou para a porta. A URL com `code`+`state` nunca foi reescrita
        pelo rebote.

Validation skipped:
  - `make smoke-local` e `npm --workspace @croquito/web run smoke:headless`: fora do
    escopo desta task (o smoke é T5) e exigem `make dev-services` + `make db-init` +
    Keycloak local; a T5 é quem os atravessa com login real.
  - Verificação de `GET /` e `GET /login` na borda: é a T1, e o rebote desta task não
    depende dela (em desenvolvimento o fallback do Vite serve `/login`).

Unavailable capabilities: none

Assumptions:
  - `/login` é caminho fixo do produto, igual em desenvolvimento e no build servido pelo
    nginx; só o destino da jornada varia, e ele vem de `import.meta.env.BASE_URL`
    (`/` em dev, `/revisao/` no build). Passado como parâmetro para manter `route.ts`
    puro e o destino testável nos dois modos.
  - Sem OIDC configurado não há sessão possível, então esse ambiente também pertence à
    porta de entrada (é lá que o feature contract põe o estado "ambiente indisponível").
    O rebote passou a valer nesse caminho, que antes retornava cedo sem tocar a URL.
  - A query preservada no rebote é a ORIGINAL e inteira, não a canônica da jornada:
    `signIn()` é quem a canoniza ao montar o `state`, e truncá-la antes perderia
    parâmetro que o link entregue carrega.
  - Texto do estado sem sessão ("ENTRADA" / "Entre para continuar") é PLACEHOLDER
    declarado em comentário: o conjunto aprovado por gate humano é da T3, e a T3 declara
    substituir este placeholder.

Remaining risks:
  - O efeito (`applyEntryRedirect` chamando `history.replaceState`) NÃO tem teste
    automatizado: o ambiente de teste do workspace é `node`, `renderToStaticMarkup` não
    roda efeito, e adicionar jsdom seria dependência nova, fora do escopo. Mitigação:
    a decisão inteira é pura e testada; o que ficou sem teste são 3 linhas de efeito,
    exercidas manualmente no dev server (acima) e alvo do smoke headless da T5.
  - A casca das jornadas (topbar, marca, pílula de schema, botão Entrar) ainda é
    renderizada sem sessão. D3 exige que ela desapareça; a retirada é escopo declarado
    da T3, e mexer nela aqui quebraria o teste `href="/revisao/"` que a T3 é quem
    redesenha.
  - Primeiro paint antes da decisão de rebote continua acontecendo (risco conhecido do
    contrato): nesse instante a URL ainda é a da jornada, mas o que se renderiza já é o
    estado sem sessão, não a jornada.

Human decisions required:
  - Commit (COMMIT: forbidden nesta task).
  - Nenhuma decisão de escopo pendente: o unknown da representação de `/login` estava
    delimitado pelo contrato e foi resolvido dentro dos limites — opção (a), a preferida.
```

## Decisão de representação (unknown delimitado pelo contrato)

Escolhida a opção **(a)**: o estado de caminho vive numa camada acima da jornada. `Route`
não ganhou um terceiro `kind`; `route.ts` ganhou uma função pura explícita e comentada
(`entryRedirect`) que a casca executa.

Por quê, registrado também no comentário de cabeçalho de `route.ts`:

- Preserva o contrato declarado do módulo — a rota da jornada continua derivando só da
  query, que é o que o ADR-0028 (D9) e o comentário original do arquivo afirmam.
- `/login` não é jornada: não tem forma canônica de query, não é alternável pelo seletor
  de jornadas e não sobrevive a `routeSearch`. Um terceiro `kind` obrigaria `routeSearch`
  e `readRoute` a responder por algo que não é query, e o round-trip canônico do módulo
  (testado em `route.test.ts`) passaria a ter um caso que não fecha.
- A regra que fecha ou não um loop de login fica verificável sem DOM, que é a condição
  para o critério 5 ser um teste de verdade e não uma inspeção visual.
