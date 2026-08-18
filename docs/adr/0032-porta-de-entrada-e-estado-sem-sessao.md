# ADR-0032: Porta de entrada própria e contrato do estado sem sessão

Status: Accepted
Data: 2026-08-18  
Responsável: Engineering / Product

## Contexto

O produto não tem endereço de entrada. A decisão está na borda, antes de qualquer código de
aplicação: `deploy/nginx.conf` declara `location = / { return 302 /revisao/; }`, sob o
comentário "Raiz do host é atalho para a sessão de cena, não uma terceira tela". Quem digita
`croquito-hml.biahflow.ai` chega, portanto, na jornada de revisão — e, sem sessão, no que
`apps/web/src/App.tsx` chama de `telaAnonima`: um `<section className="context-bar">` com um
eyebrow e um `<h1>`, renderizado dentro da casca completa do app (topbar escura, marca, pílula
de versão de schema). O ato de entrar é um `button button-quiet` na topbar, entre a pílula de
schema e a borda direita — o menor peso visual da página.

Três propriedades do estado atual condicionam qualquer solução:

- **O `redirect_uri` é fixo na base da SPA.** `apps/web/src/auth.ts` monta
  `redirect_uri: ${window.location.origin}${basePath}`, com `basePath = import.meta.env.BASE_URL`,
  que `vite.config.ts` fixa em `/revisao/` fora de desenvolvimento. O realm de homologação
  autoriza exatamente `https://croquito-hml.biahflow.ai/revisao/*` e `/medicao/*`. Qualquer
  endereço que pretenda receber o retorno do Keycloak precisa entrar nessa lista.
- **A jornada perde a marca no meio do caminho.** `loginTheme` é `null` em
  `keycloak/croquito-realm.json` e em `keycloak/croquito-hml-realm.json`. Entre a tela do
  Croquito e a volta ao Croquito, o profissional atravessa a página padrão do Keycloak.
- **O produto declara-se desktop-only.** `apps/web/src/styles.css` fixa
  `body { min-width: 1180px }`. A regra é defensável para uma prancha com viewport, camadas e
  painel de decisão; não é defensável para a tela que se abre no celular só para conferir se o
  ambiente está no ar.

Há ainda uma armadilha específica. O retorno do OIDC chega em `/revisao/?code=…&state=…` num
momento em que **ainda não existe sessão em memória**: `readSession()` só a estabelece depois de
`signinRedirectCallback()`. Qualquer regra do tipo "sem sessão, vá para a porta de entrada"
aplicada ingenuamente intercepta esse retorno e cria um loop de login fechado — que tranca todos
para fora, inclusive quem consertaria.

Por fim, o [ADR-0028](0028-medicao-na-api-v1-autenticada.md), D9, já decidiu que as jornadas
vivem num build só, servido em subrota da mesma origem; e o cabeçalho de `deploy/nginx.conf`
registra que same-origin não é estética, é o que faz cookie de sessão, `redirect_uri` e
`Authorization` viverem sob um endereço só.

## Decisão

**D1. A raiz do host leva à porta de entrada.** `GET /` responde `302` para `/login`, e não mais
para `/revisao/`.

**D2. `/login` é servido pelo mesmo build da SPA.** A borda serve `/revisao/index.html` no
caminho `/login`; os assets continuam resolvendo sob `/revisao/assets/`. Não há segundo build,
segundo `index.html` nem segunda origem.

**D3. `/login` é o único lugar onde o produto se apresenta sem sessão.** Nenhuma peça da casca
das jornadas — topbar, pílula de schema, alternância de jornada — é renderizada antes de haver
sessão.

**D4. `/revisao/` sem sessão redireciona para `/login`, preservando a query original — exceto
quando a URL carrega `code` e `state`.** O retorno do OIDC é sempre processado no lugar onde
chega. Esta exceção é parte da decisão, não detalhe de implementação: sem ela o produto fica
inacessível.

**D5. O `redirect_uri` permanece `origin + BASE_URL`, isto é, `/revisao/`.** `/login` é onde se
clica, não para onde o Keycloak devolve; ele **não** é `redirect_uri` e **não** entra nos
`redirectUris` de nenhum realm. Aparecer ali é o sinal de que o desenho escorregou.

**D6. A porta de entrada é responsiva; as jornadas não.** `/login` funciona de 360px a desktop,
como exceção declarada. `min-width: 1180px` continua valendo para revisão e medição.

**D7. O tema `croquito` é o `loginTheme` dos dois realms e veste todos os templates de login e
de e-mail que os realms possam habilitar** — não apenas `login.ftl`. Vestir só a página de
entrada faria a primeira capacidade nova de identidade derrubar o profissional numa página crua
do Keycloak no meio do fluxo.

**D8. O tema é artefato de imagem.** `keycloak/Dockerfile` é build em duas fases com
`start --optimized`; alterar o tema exige reconstruir a imagem e redeployar o serviço. Não existe
caminho de configuração em runtime, e a compatibilidade do tema é acoplada à versão fixada do
Keycloak.

## Alternativas

**Manter o estado sem sessão dentro de `/revisao/`, apenas redesenhado.** É o menor esforço e não
toca borda nem rota. Rejeitada porque não resolve a causa: a raiz do host continuaria entregando a
casca de uma jornada a quem ainda não entrou, e "porta" e "sala" continuariam sendo o mesmo
endereço — sem endereço próprio para divulgar, marcar como favorito ou mandar para alguém.

**Fazer de `/login` um `redirect_uri` próprio.** Daria simetria aparente ao fluxo. Rejeitada por
ampliar superfície sem ganho: exigiria acrescentar o path aos `redirectUris` dos dois realms e ao
roteamento, e o retorno já tem destino natural, que é a jornada. Menos endereços autorizados a
receber código de autorização é melhor postura, não pior.

**Um segundo build, ou uma página estática separada, para o login.** Permitiria uma porta leve,
sem carregar o bundle das jornadas. Rejeitada por contrariar o ADR-0028, D9 — uma sessão, um
build, um deploy — e por duplicar os tokens da marca em dois lugares, que é como identidade
diverge.

**Rebater `/revisao/` → `/login` no nginx.** Seria decidido antes do primeiro paint. Rejeitada
porque a borda não enxerga a sessão: ela vive em `sessionStorage`, no navegador. O nginx
redirecionaria também quem tem sessão válida, e a exceção do retorno do OIDC teria de ser
expressa em regex de query string — frágil exatamente no caminho que não pode falhar.

**Trazer usuário e senha para dentro do Croquito**, com Direct Access Grants. Rejeitada:
`directAccessGrantsEnabled` é `false` nos dois realms e o
[ADR-0011](0011-oidc-portable-identity.md) põe a identidade no OIDC. Credencial digitada na SPA
transforma o app em superfície de coleta de senha e amarra o produto ao provedor atual.

**Não customizar o tema do Keycloak**, aceitando a página padrão. Rejeitada porque o único ponto
do fluxo em que a pessoa digita uma credencial seria o único sem marca — o pior lugar possível
para uma descontinuidade visual, do ponto de vista de confiança e de phishing.

## Consequências

### Positivas

- O produto passa a ter um endereço divulgável, e a primeira tela responde "o que é isto e de
  quem é o acesso" antes de pedir qualquer coisa.
- A jornada de autenticação fica contínua: Croquito → Keycloak com marca → Croquito.
- O estado sem sessão vira um lugar com contrato, capaz de distinguir "você não entrou" de "o
  ambiente está fora do ar" — distinção que hoje não existe e que custou quatro dias silenciosos
  na [F-006](../features/F-006-hml-conserto/feature.md).
- A porta abre no celular sem prometer que o app inteiro abre.
- Nenhum realm muda: D5 mantém a superfície de `redirectUris` como está.

### Negativas

- Um salto a mais entre a raiz e a jornada para quem já tem sessão — mitigado por `/login`
  redirecionar para `/revisao/` quando há sessão, mas o salto existe.
- O tema passa a ser um artefato mantido: seis templates e os e-mails, acoplados à versão do
  Keycloak, que quebram em upgrade de major exatamente na tela que todo mundo vê.
- Rota por caminho é conceito novo para `apps/web/src/route.ts`, cujo módulo declara hoje que a
  rota deriva só da query e que "parâmetro desconhecido não é jornada".
- Uma exceção de responsividade convive com uma regra global de `min-width` — divergência que
  precisa continuar declarada para não virar inconsistência acidental.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| A regra de D4 intercepta o retorno do OIDC e fecha um loop de login, trancando todos para fora | Teste automatizado que exerce `/revisao/?code=…&state=…` e falha com a regra ingênua; é critério de aceite da F-007, não nota de rodapé |
| Links `?job=<uuid>` já entregues param de funcionar por causa do salto novo | O smoke headless parte justamente de um link `?job` e atravessa o redirect real; ele não pode ser afrouxado para caber no desenho novo |
| O tema quebra em upgrade do Keycloak, na única tela que todo mundo vê | Tema versionado junto da imagem, com a versão do Keycloak fixada no `Dockerfile`; upgrade passa a exigir conferência visual das páginas do tema |
| Cold start do Keycloak faz a porta bonita demorar dezenas de segundos | A [F-006](../features/F-006-hml-conserto/feature.md) registra `min_instance_count` como decisão de custo consciente; a porta não muda esse trade-off, mas o torna mais visível |
| `/login` servido com assets de `/revisao/` quebra se o `base` do Vite mudar | O acoplamento fica declarado em D2 e no comentário da location; mudar `base` passa a ser mudança de rota, não de build |

## Rastreabilidade

- Requirements: NFR-SEC-001 (autenticação por convite e isolamento por tenant — esta decisão não
  a altera, apenas dá lugar ao ato de entrar); NFR-SEC-005 (nenhum token em log, inclusive na
  location nova da borda).
- Decisões preservadas: [ADR-0011](0011-oidc-portable-identity.md) (identidade OIDC portável),
  [ADR-0024](0024-rebranding-to-croquito.md) (marca que o tema veste),
  [ADR-0025](0025-homologacao-em-gcp-cloud-run.md) (borda que ganha a rota),
  [ADR-0028](0028-medicao-na-api-v1-autenticada.md) (uma sessão, um build, um deploy).
- Especificação e execução na feature
  [F-007](../features/F-007-tela-de-login/feature.md). As capacidades de ciclo de conta que
  usarão o tema estão em [F-008](../features/F-008-ciclo-de-vida-de-conta/feature.md) e no
  [ADR-0033](0033-conta-por-convite-e-login-federado.md). A entrada na
  [matriz de rastreabilidade](../engineering/TRACEABILITY.md) é criada junto da implementação,
  quando existir verificação a citar.
- Supersedes: none
- Superseded by: none
