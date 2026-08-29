# F-007 — Porta de entrada: tela de login com marca

## Status

`DONE`

> **Aceite humano em 2026-08-28**, sobre o pacote de revisão em [evidence.md](evidence.md).
> Dívida declarada, não exercida: deploy da imagem nova do Keycloak em homologação; texto
> final (copy) da tela segue em aberto.
>
> Selecionada, planejada e executada por decisões humanas de 2026-08-18. As seis tasks do
> [plano](plan.md) estão integradas e revisadas, a validação integrada está verde — inclusive
> o smoke headless atravessando o login real com `?job` preservado — e o pacote de revisão
> está em [evidence.md](evidence.md). O que falta é a decisão humana final: merge, que também
> exerce o gate de deploy da imagem nova do Keycloak pela esteira.
>
> Decisões humanas de 2026-08-18 que moldam o escopo: a raiz do host passa a levar a uma porta
> de entrada própria (`/login`); a marca acompanha a jornada **inteira**, inclusive a página do
> Keycloak; a tela funciona em celular e em desktop; e **o visual foi aprovado** na revisão 2 do
> mock, que já reserva o espaço do login com Google. O texto continua em aberto.

## Priority

`HIGH` — definida por ato humano em 2026-08-18. Esta feature não é portão de nada: ao
contrário de F-006, nada depende dela para funcionar. O que ela move é a primeira impressão
do produto com o profissional que homologa, e é esse argumento de produto — não um de
engenharia — que sustenta a prioridade.

## Problem

O produto não tem porta de entrada. Quem digita `croquito-hml.biahflow.ai` cai na casca da
tela de revisão, vazia, e precisa achar sozinho um botão de segunda ordem para entrar.

A causa não está no React, está antes dele. `deploy/nginx.conf` declara
`location = / { return 302 /revisao/; }` com o comentário "Raiz do host é atalho para a sessão
de cena, não uma terceira tela" — a borda decide, hoje, que o produto **não tem** tela de
entrada. O React apenas cumpre a decisão: sem sessão, `App.tsx` renderiza `telaAnonima`, um
`<section className="context-bar">` com um eyebrow e um `<h1>`, e nada mais, dentro da casca
completa — topbar escura, marca, pílula de versão de schema. O ato mais importante daquela
tela, entrar, é um `button button-quiet` na topbar, espremido entre a pílula de schema e a
borda direita. É o menor peso visual da página.

Três consequências, todas mensuráveis hoje:

- **A jornada perde a marca no meio do caminho.** `loginTheme` é `null` nos dois realms
  (`keycloak/croquito-realm.json` e `keycloak/croquito-hml-realm.json`), então entre a tela do
  Croquito e a volta ao Croquito o profissional atravessa a página padrão do Keycloak. O smoke
  registra isso sem querer: `e2e/smoke-headless.mjs` espera por
  `#kc-form-login, input[name='username']` sob o comentário "os campos têm os nomes padrão do
  tema".
- **O produto não abre em celular.** `apps/web/src/styles.css` declara
  `body { min-width: 1180px }`. A regra é defensável para uma prancha de revisão com viewport,
  camadas e painel de decisão; ela não é defensável para a porta de entrada, que é justamente
  a tela que se abre no celular para conferir se o ambiente está no ar.
- **O estado sem sessão não é um lugar, é uma ausência.** `telaAnonima` não diz o que o
  produto é, não diz de quem é o acesso, não distingue "você não entrou" de "o ambiente está
  quebrado" — e o aviso de OIDC não configurado aparece como um `<p>` solto acima dela.

O redirect de autenticação, esse, **já está correto e não é o problema**: `signIn()` manda a
query canônica da jornada no `state`, e `readSession()` consome o código de uso único e
devolve a rota à URL. Esta feature não reescreve esse mecanismo; ela lhe dá uma fachada e o
protege de uma regressão nova.

## Desired Outcome

O endereço do produto abre uma porta com a cara do Croquito, no celular ou no desktop. O
"Entrar" leva a uma página do Keycloak que continua parecendo o Croquito. E a volta cai
exatamente na jornada que a pessoa pediu — inclusive quando ela chegou por um link
`?job=<uuid>` que alguém mandou.

## Scope

- **Borda (`deploy/nginx.conf`)**: `/` deixa de redirecionar para `/revisao/` e passa a
  redirecionar para `/login`; location nova servindo `/revisao/index.html` em `/login`, com as
  mesmas políticas de cache e `X-Content-Type-Options` das demais.
- **`apps/web`**: a tela de login como estado próprio da SPA em `/login` — marca, proposta do
  produto em uma linha, um CTA de entrar com peso de CTA, e um estado de erro legível para
  ambiente sem OIDC ou fora do ar. Responsiva de 360px a desktop, como exceção declarada ao
  `min-width` global, que continua valendo para as jornadas.
- **Espaço reservado para o login federado**: o card nasce com o divisor e a posição do botão
  "Entrar com Google", que a [F-008](../F-008-ciclo-de-vida-de-conta/feature.md) liga. O botão
  é **renderizado apenas quando existe identity provider configurado** — porta que não abre não
  entra no ar. Reservar agora evita redesenhar uma tela já aprovada.
- **Regra de rebote**: `/revisao/` sem sessão leva a `/login` preservando a query; `/login`
  com sessão leva a `/revisao/`. Com a exceção explícita do retorno do OIDC, abaixo.
- **Tema `croquito` do Keycloak**, com `loginTheme` apontado para ele nos dois realms. O tema
  cobre `login.ftl` **e as páginas que a F-008 vai habilitar** — `login-reset-password`,
  `login-update-password`, `login-verify-email` e `login-page-expired` — mais os templates de
  e-mail. Vestir só o `login.ftl` faria a F-008 entrar e derrubar a pessoa numa página crua do
  Keycloak no meio do fluxo, que é exatamente o problema que esta feature existe para resolver.
- **[ADR-0032](../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md)**, redigido e **aceito
  por ato humano** em 2026-08-18: registra o endereço de entrada, o contrato do estado sem
  sessão e o acoplamento do tema à versão do Keycloak.
- **Rede de regressão**: `apps/web/src/App.test.tsx` e `e2e/smoke-headless.mjs` atualizados
  para o desenho novo, mais um teste automatizado do caso do retorno do OIDC.
- **Reconciliação documental**: `docs/operations/HML.md` e o comentário de cabeçalho de
  `deploy/nginx.conf`, que hoje descreve o mapa de rotas antigo.

## Out of Scope

- **Convite, recuperação de senha, verificação de e-mail e login com Google.** Passaram a ser
  trabalho declarado na [F-008](../F-008-ciclo-de-vida-de-conta/feature.md), que depende de
  infraestrutura de e-mail inexistente hoje. Esta feature entrega a fachada e o tema; a F-008
  liga as capacidades por trás delas.
- **Autocadastro aberto.** Decisão humana de 2026-08-18, alinhada ao
  [ADR-0011](../../adr/0011-oidc-portable-identity.md): conta nasce por convite.
- **Campos de usuário e senha dentro do Croquito.** `directAccessGrantsEnabled` é `false` nos
  dois realms, e o ADR-0011 põe a identidade no OIDC. Trazer credencial para dentro da SPA é
  decisão de segurança própria, não efeito colateral de uma tela bonita.
- **Tornar o app inteiro responsivo.** `min-width: 1180px` continua valendo para as duas
  jornadas. A exceção é a porta de entrada e é declarada como exceção.
- **Página pública de marketing.** `/login` é porta de acesso, não landing de produto.
- **Mudança nos `redirectUris` dos realms.** Ver a primeira Constraint: se esta feature
  precisar mexer neles, o desenho escorregou.
- **A homologação real da orçamentista** e os atos de produção abertos em
  [F-003](../F-003-medicao-v1-migration/feature.md) e
  [F-004](../F-004-migrations-runner/feature.md).

## Acceptance Criteria

1. `GET /` na borda responde `302` para `/login`, e `GET /login` serve o `index.html` da SPA
   com os assets resolvendo sob `/revisao/assets/`.
2. Sem sessão, `/login` mostra a tela de entrada. Em viewport de 390px e de 1440px não há
   barra de rolagem horizontal e o CTA é alcançável sem rolagem.
3. Com sessão válida, `/login` não mostra a porta: redireciona para `/revisao/`.
4. Sem sessão e sem parâmetros de retorno do OIDC, `/revisao/` leva a `/login` preservando a
   query original.
5. **`/revisao/?code=…&state=…` nunca rebate.** A sessão fecha, a URL é limpa e a jornada
   abre. Coberto por teste automatizado que falharia com a regra de rebote ingênua.
6. Um link `/revisao/?job=<uuid>` aberto sem sessão termina, depois do login, naquele job. É
   o alvo declarado de `e2e/smoke-headless.mjs`, que continua verde sem afrouxar seletor nem
   asserção.
7. A página de login do Keycloak serve o tema `croquito` — logo e paleta da folha da marca — e
   o formulário continua sendo encontrado pelo smoke.
8. **Nenhuma página do tema cai no padrão do Keycloak.** Cada template listado no escopo é
   aberto e conferido visualmente, inclusive os que só a F-008 vai alcançar em produção.
9. **Sem identity provider configurado no realm, o botão "Entrar com Google" não é
   renderizado** — nem desabilitado, nem oculto por CSS. Verificado com o realm atual.
10. `make check` e `make test` verdes. Nenhum teste removido ou relaxado para passar; o teste
    de `App.test.tsx` que hoje afirma `"Acesse uma revisão autenticada"` é **substituído** pela
    asserção equivalente do desenho novo, não apagado.

## Constraints

- **O `redirect_uri` continua sendo `origin + BASE_URL`, isto é, `/revisao/`.** `/login` é
  onde a pessoa clica, não para onde o Keycloak devolve. Por isso o realm de homologação, que
  autoriza apenas `/revisao/*` e `/medicao/*`, não precisa mudar. Se em algum momento
  `/login` aparecer em `redirectUris`, é sinal de que o desenho saiu do trilho.
- **Same-origin é requisito da borda**, não estética: o cabeçalho de `deploy/nginx.conf`
  registra que cookie de sessão, `redirect_uri` e `Authorization` vivem sob um endereço só. A
  tela nova não introduz origem nem build adicional.
- **Um build só.** `vite.config.ts` fixa `base: "/revisao/"` fora de desenvolvimento; servir a
  mesma SPA em `/login` depende de os assets serem absolutos. Nenhum segundo build, nenhum
  segundo `index.html`.
- **A marca vem dos tokens de `:root` em `apps/web/src/styles.css`**, e as regras escritas na
  própria folha valem aqui: `--accent` só em preenchimento com `--accent-ink` por cima; texto
  ou traço fino em verde sobre claro usa `--accent-text`.
- **O tema do Keycloak é imagem.** `keycloak/Dockerfile` é build em duas fases com
  `start --optimized`; mexer no tema exige reconstruir a imagem e redeployar o serviço. Não
  há caminho de configuração em runtime.
- **Nenhum segredo no tema.** Vale a mesma política do Dockerfile: camada de imagem é legível
  para quem puxa a imagem.
- Sem `Location` absoluto na borda: `absolute_redirect off` está declarado porque o Cloud Run
  entrega em HTTP na 8080, e o redirect novo herda a mesma armadilha.

## Dependencies

- [F-006](../F-006-hml-conserto/feature.md): sem homologação no ar, os critérios 1 a 8 só são
  verificáveis contra o stack local.
- [F-008](../F-008-ciclo-de-vida-de-conta/feature.md) **depende desta**, e não o contrário: ela
  liga capacidades sobre o tema e o card que esta entrega. Esta feature não espera aquela.
- [ADR-0011](../../adr/0011-oidc-portable-identity.md) — identidade portável em OIDC.
- [ADR-0024](../../adr/0024-rebranding-to-croquito.md) — a marca que o tema precisa vestir.
- [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md) — a borda que ganha rota nova.
- [ADR-0028](../../adr/0028-medicao-na-api-v1-autenticada.md), D9 — uma sessão OIDC, um build,
  um deploy. É a decisão que obriga `/login` a ser estado da mesma SPA.
- [ADR-0032](../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md) — `Accepted` por ato
  humano em 2026-08-18; é a decisão que esta feature implementa.

## Unknowns

Todos resolvidos na rodada de planejamento de 2026-08-18 — nenhum por suposição:

- ~~Como `/login` se representa em `route.ts`~~ — **delimitado no
  [Task Contract da T2](tasks/T2-estado-login-e-rebote.md)**: camada acima da jornada
  (preferida, preserva o contrato do módulo) ou terceiro `kind`; a escolha fica registrada
  no código e no BUILD REPORT.
- ~~Onde mora o rebote de `/revisao/` sem sessão~~ — **no React, depois de `readSession()`**
  (a borda não enxerga sessão; o ADR-0032 rejeitou o rebote no nginx). O primeiro paint é
  estado neutro mínimo em T2; T3 o veste.
- ~~Formato do tema no Keycloak 26.2~~ — **resolvido por verificação dentro da T4** (passo 1
  do contrato), nunca por inferência.
- ~~O texto da tela~~ — **aprovado por ato humano em 2026-08-18**; conjunto fixado no
  [Task Contract da T3](tasks/T3-tela-de-login.md).
- ~~A pílula de ambiente~~ — **só em homologação** (2026-08-18); **substituída em
  2026-08-19**: sem pílula em ambiente nenhum — a URL diferencia o ambiente.
- ~~`/medicao/` sem sessão~~ — **resolvido por estrutura**: a borda já redireciona
  `/medicao/` para `/revisao/?rodada=`, que cai na regra de rebote preservando a query;
  nenhum comportamento novo.

## Risks

- **Loop de login.** É o modo de falha mais provável e o mais caro: uma regra de rebote que
  não excepcione o retorno do OIDC manda `/revisao/?code=…` de volta para `/login` antes de a
  sessão fechar, e ninguém entra mais. Fecha todo mundo do lado de fora, inclusive quem
  poderia consertar. É por isso que virou o critério 5 e não uma nota.
- **Links `?job=` já entregues.** O comentário de `route.ts` registra que preservar esses
  links foi decisão explícita; uma porta nova no caminho é exatamente o tipo de mudança que os
  quebra em silêncio.
- **Tema acoplado à versão.** Tema customizado de Keycloak quebra em upgrade de major, e a
  quebra aparece na tela de login — a única tela que todo mundo vê. O risco cresce com o
  escopo: são agora seis templates mais os e-mails, não um.
- **Cold start.** A F-006 registra que o Keycloak esteve com `min_instance_count = 0` no
  ambiente. Uma porta bonita que leva dezenas de segundos para responder é pior do que a tela
  feia de hoje, porque promete mais.
- **O smoke é a única rede que atravessa o redirect real.** Se ele for afrouxado para caber no
  desenho novo, a feature entrega a tela e perde a garantia.

## Human Gates

- ~~Aceitação do ADR-0032~~ — **aceito por ato humano em 2026-08-18**.
- ~~Aprovação do visual da tela~~ — **aprovado em 2026-08-18**, sobre a revisão 2 do
  [mock](mock/README.md), versionado junto deste contrato.
- ~~Aprovação do **texto** da tela~~ — **aprovado em 2026-08-18**; o conjunto está no
  [Task Contract da T3](tasks/T3-tela-de-login.md) e no [mock](mock/README.md).
- ~~Definição da prioridade de F-007 no roadmap~~ — **definida `HIGH` em 2026-08-18**.
- ~~Autorização para a execução começar~~ — **autorizada por ato humano em 2026-08-18**,
  com o plano congelado e os contratos derivados.
- Deploy da imagem nova do Keycloak em homologação.

## References

- [Mock aprovado](mock/README.md) — o artefato do gate visual, com HTML e imagens
- [ROADMAP](../../product/ROADMAP.md)
- [F-006](../F-006-hml-conserto/feature.md),
  [F-008](../F-008-ciclo-de-vida-de-conta/feature.md)
- [ADR-0032](../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md) — a decisão desta feature
- [ADR-0011](../../adr/0011-oidc-portable-identity.md),
  [ADR-0024](../../adr/0024-rebranding-to-croquito.md),
  [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md),
  [ADR-0028](../../adr/0028-medicao-na-api-v1-autenticada.md)
- [HML](../../operations/HML.md), [HML_KEYCLOAK](../../operations/HML_KEYCLOAK.md)
- Fontes lidas para este contrato: `deploy/nginx.conf`, `apps/web/vite.config.ts`,
  `apps/web/src/App.tsx`, `apps/web/src/auth.ts`, `apps/web/src/route.ts`,
  `apps/web/src/styles.css`, `apps/web/src/App.test.tsx`, `apps/web/e2e/smoke-headless.mjs`,
  `keycloak/Dockerfile`, `keycloak/croquito-realm.json`, `keycloak/croquito-hml-realm.json`.
