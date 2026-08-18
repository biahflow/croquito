# T3 — BUILD REPORT

Evidência primária de execução da [T3](T3-tela-de-login.md), no formato exigido pelo
[contrato do Builder](../../../engineering-os/agents/builder.md).

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - apps/web/src/App.tsx — o estado sem sessão deixou de ser um placeholder dentro da
    casca e virou RETORNO ANTECIPADO: `if (session === null)` devolve a porta de entrada
    inteira, e nenhuma peça da casca das jornadas chega a ser construída antes da sessão
    (ADR-0032, D3). O texto aprovado está em constantes nomeadas no topo do módulo, junto,
    com comentário dizendo que editá-las reabre o gate humano. Entraram: o mecanismo da
    pílula (`HOMOLOGATION_HOST` + `isHomologationHost`, exportada para teste), a condição
    do login federado (`identityProvidersConfigured`), e um efeito que troca o título da
    aba entre "Entrar — Croquito" e "Croquito". Saíram da topbar o botão `button-quiet`
    "Entrar" e as condicionais `session ? … : null` que só existiam para o estado sem
    sessão; saiu do topo da casca o `<p className="session-error">` do OIDC não
    configurado, que virou estado da própria porta.
  - apps/web/src/styles.css — `min-width: 1180px` saiu do `body` e passou para
    `.app-shell`. A exceção de responsividade fica declarada em comentário e é estrutural,
    não uma media query a manter em duas folhas: `.app-shell` só é renderizada com sessão,
    então o piso continua valendo INTEIRO para as jornadas e não alcança a porta.
    Acrescentado o bloco `.login-*` (painel de marca, croqui, card, CTA, alerta, pílula,
    convite, slot do login federado e a media query de 900px), com o cabeçalho declarando
    de onde vem cada classe de valor: cor só da tabela de tokens; tamanho, espaçamento e
    raio como valores APROVADOS NA REVISÃO 2 do mock, não como citação de escala.
  - apps/web/src/App.test.tsx — asserções da tela nova; nenhum teste removido, nenhuma
    asserção relaxada. Detalhe em "Tests added".

Tests added:
  - "na rota do croqui sem sessão, nenhuma jornada é exposta" (SUBSTITUÍDO, não apagado):
    "Entre para continuar" → "Do croqui ao orçamento."; "OIDC não está configurado" → a
    mensagem aprovada de ambiente indisponível. As sete asserções de ausência das jornadas
    ficaram intactas, inclusive `not.toContain("HOMOLOGAÇÃO")`, que agora prova também que
    a pílula não aparece fora do host de homologação.
  - "sem sessão, nenhuma peça da casca das jornadas é renderizada" (SUBSTITUI "sem sessão,
    não oferece a alternância de jornada", ampliando-o): `app-shell`, `topbar`,
    `schema-pill`, `identity-pill`, `aria-label="Jornadas"` e `>Medição<` ausentes. Cada
    asserção nomeia uma peça citada no D3 do ADR-0032. É o critério 3 do contrato.
  - "sem identity provider no realm, o botão do Google não existe no DOM" (NOVO):
    "Entrar com Google", `login-federated` e `login-button-federated` ausentes do markup,
    com `login-cta` presente — ausência do DOM, não `display: none`. É o critério 4.
  - "a pílula de ambiente é derivada do host de homologação" (NOVO): `isHomologationHost`
    verdadeiro só para `croquito-hml.biahflow.ai`; falso para produção, `localhost`,
    string vazia e para `evil-croquito-hml.biahflow.ai` (sufixo não compra passagem). É o
    critério 5, exercendo o mecanismo escolhido.
  - "não linka uma segunda origem" (SUBSTITUÍDO): a marca deixou de ser link porque a
    topbar saiu do estado sem sessão, então `toContain('href="/revisao/"')` foi trocado
    por uma afirmação mais forte — nenhuma âncora (`<a `) no render, e o único `href`
    (o `<link rel="preload">` que o React emite para o wordmark) resolvendo sob a base
    desta SPA. `not.toContain('href="/medicao/"')` intacto.

Validation executed:
  - baseline (antes de qualquer edição, working tree limpo sobre e06342c):
    `make check` → exit 0; `make test` → exit 0 (pytest 1438 passed, 10 skipped;
    vitest 28 arquivos, 527 passed).
  - final: `make check` → exit 0 (ruff check, ruff format, mypy strict, check_docs,
    schema_export --check, contracts:check, web:check = `tsc -b` + `vite build`,
    terraform fmt). Build web: 61 módulos, CSS 43,65 kB (era 39,96 kB), JS 443,72 kB.
  - final: `make test` → exit 0 (pytest 1438 passed, 10 skipped, 120,52 s; vitest 28
    arquivos, 529 passed — os 527 do baseline mais 2 testes novos, com 3 substituídos).
  - final: `npm --workspace @croquito/web run test` → 28 arquivos, 529 passed.
  - conferência visual no dev server (`npx vite`, Chromium via Playwright, DPR 2), em três
    viewports e nos dois estados. Números medidos no próprio DOM:

        estado "porta no ar" (VITE_OIDC_* definidos)
          1440x900  scrollWidth 1440 = clientWidth  · CTA bottom 455 / 900  · sem rolagem
           390x844  scrollWidth  390 = clientWidth  · CTA bottom 710 / 844  · sem rolagem
           360x780  scrollWidth  360 = clientWidth  · CTA bottom 646 / 780  · sem rolagem
        estado "ambiente indisponível" (VITE_OIDC_* vazios)
          1440x900  scrollWidth 1440 = clientWidth  · CTA bottom 499 / 900  · desabilitado
           390x844  scrollWidth  390 = clientWidth  · CTA bottom 710 / 844  · desabilitado
           360x780  scrollWidth  360 = clientWidth  · CTA bottom 646 / 780  · desabilitado

    Em todos: `document.title` = "Entrar — Croquito"; `Entrar com Google` ausente do
    `innerHTML`; nenhum `.topbar`, `.app-shell` ou `.schema-pill` no DOM. É o critério 1.
  - capturas arquivadas em `output/f-007-t3/` (diretório ignorado pelo Git, retenção local
    de 7 dias, fixture sintética — nenhum dado de cliente):
        01-porta-desktop-1440.png
        02-porta-celular-390.png
        03-ambiente-indisponivel-desktop-1440.png
        04-ambiente-indisponivel-celular-390.png
        05-porta-celular-360.png
    Conferidas contra `mock/01-login-desktop.png` e `mock/02-login-celular.png`:
    composição (painel de marca à esquerda com wordmark no topo, promessa ao meio e croqui
    embaixo; card à direita, centrado no desktop e com o CTA ancorado embaixo no celular),
    hierarquia (a promessa em Georgia é o maior peso tipográfico; o CTA é o maior peso
    cromático) e peso do CTA (preenchimento `--accent` com `--accent-ink`, 48px de altura,
    largura inteira do card, sombra do mock). É o critério 2.
  - a pílula de ambiente foi conferida VISUALMENTE apontando `HOMOLOGATION_HOST` para
    `localhost` durante a captura e RESTAURANDO em seguida (o valor final no arquivo é
    `croquito-hml.biahflow.ai`; `git diff` confirma). As capturas 01, 02 e 05 mostram a
    pílula por causa desse desvio temporário; o comportamento real é o do teste
    automatizado.
  - critério 6: `make check` e `make test` verdes, nenhum teste removido ou relaxado.

Validation skipped:
  - conferência contra o ambiente de homologação real (a pílula renderizada sob o hostname
    verdadeiro, e a tela servida em `/login` pelo nginx da borda). Depende do deploy, que é
    ato de produção com aprovação humana e está fora do escopo desta task; o mecanismo está
    coberto por teste automatizado e por conferência local com o host apontado.
  - `e2e/smoke-headless.mjs` (critério 6 da FEATURE, não desta task): exige
    `make dev-services && make db-init && make dev` e login real no Keycloak local; não é
    portão desta task e a T3 não tocou em `auth.ts`, `route.ts` nem no seletor que ele
    persegue.

Unavailable capabilities: none

Assumptions:
  - O CONJUNTO APROVADO DE TEXTO É EXAUSTIVO. O contrato lista cinco cadeias e põe em
    "Out of Scope" qualquer texto fora delas; o mock traz copy adicional (eyebrow "ACESSO
    RESTRITO", título "Entrar no Croquito", parágrafos de apoio, "Sua senha é digitada no
    provedor…", rodapé "Acesso nominal · …"). Duas evidências fecham a questão a favor do
    contrato: (a) as próprias notas do mock declaram "Todo o texto" como decisão ABERTA,
    "só 'Do croqui ao orçamento.' não é proposta minha"; (b) as versões do mock para o
    convite e para o ambiente indisponível DIFEREM das cadeias aprovadas — ou seja, a
    aprovação humana reescreveu o mock, não o ratificou. Implementei só as cinco cadeias.
    Consequência visível e aceita: a tela é mais esparsa que o mock, sobretudo no painel
    claro. A composição, a hierarquia e o peso do CTA — que é o que o critério 2 nomeia —
    foram preservados.
  - "HOMOLOGAÇÃO" (rótulo da pílula) e o rótulo do slot federado são os únicos textos fora
    das cinco cadeias, e entram porque o próprio contrato manda a pílula existir e o
    rótulo é o nome factual do ambiente, do mock aprovado. Nenhuma frase de produto foi
    inventada.
  - A pílula deriva do hostname, não de env var nova. `apps/web` só lê `VITE_OIDC_*` e
    `VITE_API_BASE_URL`; criar `VITE_ENVIRONMENT` obrigaria a mexer em build, imagem e
    serviço para exibir um rótulo. A escolha está comentada em `App.tsx`.

Deliberate deviations:
  - O DIVISOR ACOMPANHA O BOTÃO. O contrato diz que "o card nasce com o divisor e a posição
    do botão … mas o botão não é renderizado". Renderizar o divisor sozinho deixaria um
    traço separando uma opção de nenhuma outra — e, com o rótulo "ou" do mock, texto fora
    do conjunto aprovado. Divisor e botão ficam no MESMO slot, gated pela mesma condição.
    O mock sustenta o par: no quadro de ambiente indisponível (02, telefone da direita) não
    há divisor nem Google. O slot existe em markup (`.login-federated`) e em CSS
    (`.login-divider`, `.login-button-federated`, reservada e ainda sem uso), como o
    contrato pede; o critério 9 fica mais forte, não mais fraco.
  - O PISO DE 1180px MUDOU DE SELETOR, de `body` para `.app-shell`. O contrato pedia a
    exceção "declarada em comentário"; uma media query ou um `body:has(.login)` deixaria a
    porta refém de suporte a `:has()` — e uma falha aí seria silenciosa exatamente no
    critério 1. Como `.app-shell` só existe com sessão, a regra passa a viver onde ela vale.
    Diferença de comportamento: abaixo de 1180px COM sessão, o `body` deixa de ser esticado
    e é `.app-shell` que transborda — a rolagem horizontal das jornadas é idêntica, muda só
    a caixa do gradiente do `body` num estado já declarado como não suportado.
  - O ALERTA USA AS CORES DE `.app-alert`, e não os vermelhos novos do mock (#fdf3f2 /
    #f2cfcb / #5c2521 / #a3322a). O contrato manda usar só a tabela de tokens, e a tabela
    não tem vermelho; erro é cor de domínio (regra 4 do Design System) e a folha — que é a
    fonte de verdade em runtime — já tem uma paleta de erro. Reusar #fbeeec / #e0b4ad /
    #7d2f26 não cria uma segunda paleta de erro no produto.
  - A PÍLULA USA `--accent-text`, NÃO `--accent`, e não tem o ponto verde do mock em
    `--accent`. A regra 2 do Design System nomeia "ponto" entre os indicadores que, sobre
    superfície clara, precisam de `--accent-text`. Era o risco nº 1 listado no contrato.
  - O CTA DESABILITADO segue `--muted` sobre `--line`, como `.button:disabled` já faz nesta
    folha e como o mock desenhou. A regra 3 do Design System dá a `--muted` exatamente o
    papel de desabilitado, e o motivo do estado está escrito por extenso no alerta acima do
    botão — cor não é o portador do significado.

Remaining risks:
  - A tela não foi vista sob o hostname de homologação real nem servida pelo nginx em
    `/login`; a pílula em produção depende do deploy da F-007 (critério 1 da FEATURE, T5).
  - `sessionNotice` é dinâmico (ex.: "Não foi possível validar a sessão OIDC: <mensagem do
    oidc-client-ts>") e agora aparece dentro do card da porta. É texto pré-existente, fora
    do conjunto aprovado e fora do escopo desta task — mas ele É exibido ao usuário e pode
    carregar mensagem de biblioteca. Fica registrado como dívida, não corrigido aqui.
  - Nenhum teste renderiza `<App />` COM sessão, então a casca reestruturada (topbar sem as
    condicionais de sessão) é verificada por `tsc` e pelos testes das jornadas, não por um
    render da casca. É a mesma cobertura de antes desta task, não uma regressão dela.
  - O croqui vetorial foi reproduzido a partir do artefato aprovado (é a única fonte do
    desenho). Não é código copiado do mock — o markup, as classes e as cores são novos e a
    cor vive na folha —, mas a GEOMETRIA é a mesma, deliberadamente, porque é ela que o
    gate visual aprovou.

Human decisions required: none

Notas de execução: branch `feat/f-007-porta-de-entrada`, sem commit (COMMIT: forbidden no
contrato). Executor: Claude Code / implementador-opus, conforme `assignments.md`.
Arquivos tocados: exatamente os três do escopo — `apps/web/src/App.tsx`,
`apps/web/src/styles.css`, `apps/web/src/App.test.tsx`.
```
