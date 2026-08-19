# F-007 — Evidence

Status: `READY_FOR_HUMAN_REVIEW`
Responsável: Engineering
Última revisão: 2026-08-18

Pacote de revisão no formato da camada pinada
([template](../../engineering-os/templates/evidence.md)): consolida referências; **não
substitui** as fontes. Cada `BUILD REPORT` é evidência primária da sua task e está
preservado com autoria em `tasks/T<N>-build-report.md`.

## Contrato, plano e execução

| Artefato | Onde |
|---|---|
| Feature Contract | [feature.md](feature.md) — 10 critérios de aceite |
| Execution Plan (congelado, `PLAN_VALID`) | [plan.md](plan.md) — 6 tasks, 2 `PLAN_DEVIATION` registrados |
| Task Contracts | [tasks/](tasks/) — um por task, template global |
| Atribuições de harness/modelo | [assignments.md](assignments.md) — decisões humanas de 2026-08-18 |
| Baseline | `main` em `522aa4b` (pós-PR #12): `make check` e `make test` verdes |

## Execução por task — um relatório por executor, autoria preservada

| Task | Executor (harness/modelo) | Status do BUILD REPORT | Commit | Revisão linha a linha |
|---|---|---|---|---|
| T1 borda | Codex / gpt-5.6-luna | `BUILD_COMPLETE` — [relatório](tasks/T1-build-report.md) | `5c3ca82` | limpa; Location relativo e regressões re-verificados pelo revisor com build real |
| T2 rebote | Claude Code / implementador-opus | `BUILD_COMPLETE` — [relatório](tasks/T2-build-report.md) | `e06342c` | limpa; prova de mutação do critério 5 no relatório |
| T3 tela | Claude Code / implementador-opus | `BUILD_COMPLETE` — [relatório](tasks/T3-build-report.md) | `45f29db` | limpa; 3 arbitragens declaradas e endossadas |
| T4 tema | Claude Code / implementador-opus | `BUILD_COMPLETE` — [relatório](tasks/T4-build-report.md) | `2c8a3aa` (merge de worktree) | limpa; desvio do `emailTheme` endossado (exigido pelo D7) |
| T5 smoke | Codex / gpt-5.6-sol | `BUILDER_VALIDATION_BLOCKED` — [relatório](tasks/T5-build-report.md), íntegro e imutável | `15493ff` | limpa; e2e ficou MAIS estrito; validação de stack pelo operador (abaixo) |
| T6 docs | Codex / gpt-5.6-luna | `BUILD_COMPLETE` — [relatório](tasks/T6-build-report.md) | `2d8a66d` | limpa; varredura sem sobras |

## Validação integrada (operador, 2026-08-18)

Executada na branch integrada após as seis tasks, com o postgres do croquito em porta
alternativa (15432) para não tocar container de outro projeto (`PLAN_DEVIATION` 2):

- `make check` — verde ponta a ponta (ruff, mypy strict, check_docs com paridade de
  lifecycle, drift de contratos, build web, terraform fmt).
- `make test` — verde: 1438 pytest (10 skipped) + 529 vitest.
- `scripts/smoke_local.py` — verde 2× (tenant-smoke e tenant-local), cadeia completa até o
  ZIP auditado; job semeado para o e2e.
- **Smoke headless — verde de ponta a ponta**: tela de login nova → Keycloak com o tema
  `croquito` → sessão estabelecida → `?job` preservado através do redirect OIDC → jornada
  da revisão renderizada. Nenhum seletor ou asserção afrouxado; a âncora do clique ficou
  mais estrita (`main.login`, `exact: true`).
- Borda (revisão da T1): imagem `docker/web.Dockerfile` construída e verificada por curl —
  `/` → `302` com `Location: /login` **relativo**; `/login` → 200 com `no-store`,
  `nosniff` e assets sob `/revisao/assets/`; `/medicao/` → `302 /revisao/?rodada=`
  (regressão intacta).
- Evidência visual do tema: 12 capturas em [tasks/evidencia-tema/](tasks/evidencia-tema/),
  incluindo as páginas que só a F-008 alcança e três e-mails renderizados de envio real a
  sink SMTP.
- Os dois checks novos de `scripts/smoke_hml.py` (`/` e `/login`) serão exercitados contra
  a homologação real pela esteira, no primeiro deploy pós-merge.

## Cobertura dos critérios de aceite

1 ✅ (T1 + curl da revisão) · 2 ✅ (T3, medições DOM em 360/390/1440) · 3–5 ✅ (T2, testes
com prova de mutação) · 6 ✅ (T5 + headless verde com `?job`) · 7 ✅ (T4, tema servido e
seletor intacto) · 8 ✅ (T4, 12 capturas, nenhuma página no padrão) · 9 ✅ (T3, ausência de
DOM testada) · 10 ✅ (portões integrados verdes; asserção antiga substituída, nada
removido).

## Desvios do plano

Dois, registrados em [plan.md](plan.md#desvios-do-plano): o conserto de baseline do realm
local (perfil dos usuários de fixture — defeito pré-existente que travava qualquer branch
em `VERIFY_PROFILE`) e a autoria dividida da evidência da T5.

## Riscos remanescentes e decisões humanas em aberto

- **Páginas do Keycloak em inglês** (T4): `internationalizationEnabled` é falso nos realms
  e o tema não traz `messages/` — ligar i18n é campo de realm e traduzir é copy com gate.
  O mock aprovado está em português; decidir se entra como task própria ou na F-008.
- **`sessionNotice` dinâmico** (T3): a mensagem de erro de sessão inclui texto do
  oidc-client-ts, fora do conjunto de copy aprovado — pré-existente, declarado.
- **Cold start do Keycloak** (contrato): `min_instance_count` continua decisão de custo
  consciente da F-006; a porta nova o torna mais visível.
- **Deploy**: o merge dispara a esteira, que constrói e publica a imagem nova do Keycloak
  (com tema) e a borda nova — é o gate humano "deploy da imagem" exercido pelo merge; a
  fumaça da esteira valida as seis rotas em seguida.

## Revisão humana — rodada 1 (2026-08-18, sobre a tela em homologação)

Três achados do responsável, todos resolvidos na branch `fix/f-007-revisao-humana`:

1. **Copy incompleta**: a tela mostrava só o conjunto enxuto aprovado no planejamento; o
   responsável aprovou a copy inteira do mock (revisão 2 do texto, registrada no
   [mock/README.md](mock/README.md)) — eyebrow, título, subtítulo, garantia de senha,
   rodapé de convite e apoio da promessa entraram palavra por palavra.
2. **Keycloak em pt-BR**: decisão humana fechando o risco aberto da T4 —
   `internationalizationEnabled` + `defaultLocale: pt-BR` nos dois realms, com o locale
   embutido da versão (nenhuma tradução custom, nenhum template tocado). Validado no
   Keycloak local com tema: "Entrar na sua conta", campos e botão em português.
3. **Composição do painel escuro**: wordmark pequeno e croqui perdido em viewport largo. A
   causa-mecanismo: o `align-items: stretch` padrão esticava o `img` do wordmark (o desenho
   recentrava dentro do viewBox) e o `footer` global impunha `space-between`. Correção:
   coluna interna com largura máxima, ancoragem `flex-start`, wordmark em `clamp()` maior
   (decisão do responsável) com compensação óptica da margem interna do lettering, e
   subtítulo/rodapé do mock que faltavam. Validação no Chrome em seis larguras (390, 768,
   1024, 1440, 1920, 2560): zero overflow horizontal e composição coesa em todas.

Portões re-rodados após a rodada: `make check` e 529 testes web verdes (asserções novas
cobrindo a copy da revisão 2).

## Revisão humana — rodada 2 (2026-08-19, incidente e decisões)

1. **Incidente: loop de login silencioso — reproduzido, causado e consertado.** O relato
   ("já loguei no Keycloak mas me redireciona para o login de novo") foi reproduzido com
   navegador contra a homologação: retorno com `code`+`state` que falham na troca
   terminava em `/login` **sem aviso**. Causa: `readSession()` engolia a falha do callback
   e o `finally` limpava a URL — comportamento benigno antes da F-007, transformado em
   loop pelo rebote (a exceção de D4 nunca via o `code`, já removido; com SSO ativo, cada
   "Entrar" voltava com código novo que falhava igual). Conserto em `auth.ts`: a falha só
   continua silenciosa quando existe sessão armazenada para amortecê-la (o caso original
   de código gasto em reload); sem sessão viva, ela sobe e vira aviso visível na porta.
   Rede de regressão nova: `apps/web/e2e/callback-failure.mjs` (`smoke:callback`),
   verde contra o conserto. O acesso do responsável funcionou em tentativa limpa
   ("Sessão: daniel" registrada em captura).
2. **Marca pequena na topbar da jornada**: mesma correção óptica da porta aplicada ao
   `.brand-logo` (34px com compensação do lettering).
3. **Botão do Google**: decisão humana — **espera a F-008 completa**; o critério 9
   permanece como aprovado (botão morto não entra no ar).
4. **Jornada guiada (próxima tarefa só habilita quando a atual é cumprida)**: pedido de
   produto registrado como **F-009** no roadmap (`READY_FOR_SPEC`, prioridade a definir);
   é `INTERFACE_CHANGE` e seguirá o gate de Design Approval antes do planejamento. O
   portão de paridade aprendeu que item pré-contrato vive sem link de feature.md (2 testes
   novos).
5. **Pílula de ambiente removida** (decisão humana de 2026-08-19): sem pílula em
   ambiente nenhum — a URL diferencia; mecanismo de hostname, CSS e teste do mecanismo
   removidos; registro da divergência aprovada no mock/README.md.
6. **Realm de HML — recriação autorizada**: decisão humana de 2026-08-19 autoriza o
   caminho destrutivo do runbook (apagar o realm e deixar o import recriá-lo com tema e
   pt-BR); só o usuário do responsável existia e será recriado por ele — com e-mail e
   nome preenchidos, pela lição do VERIFY_PROFILE. Execução pelos comandos no terminal
   do responsável (o classificador do harness barrou a via automática, corretamente).
7. **Ato de console pendente (HML)** — substituído pelo item 6: o diagnóstico confirmou o tema antigo e inglês
   ainda ativos no realm de homologação — o `IGNORE_EXISTING` do import não aplica
   `loginTheme`/`emailTheme`/i18n a realm existente; os passos de console estão com o
   responsável (runbook HML_KEYCLOAK, "Mudança no realm depois que ele já existe").

## Revisão humana — rodada 3 (2026-08-19, segundo incidente: 401 pós-login)

Relato: usuário recriado loga no Keycloak, volta a `/revisao/` e não entra. Investigação
por logs dos três serviços, com reprodução local instrumentada:

- **Causa raiz**: o usuário recriado ficou **sem o atributo `tenant_id`** — token válido,
  troca de código 200, e `GET /v1/projects → 401` em toda tentativa (o cenário literal do
  ADR-0033). Nenhum código estava errado NESTE ponto; o dado do realm estava.
- **Três defeitos reais expostos e consertados no mesmo PR**:
  1. `identity_from_claims` agora distingue **`TOKEN_WITHOUT_TENANT`** de `INVALID_TOKEN`
     (código estável novo no API Contract; 6 testes em `tests/core/test_oidc.py`), e o
     web mostra explicação clara em vez de código cru — **e não tenta renovar**, porque
     token novo não conserta conta sem organização (2 testes em `api.test.ts`).
  2. A renovação silenciosa era **quebrada por construção**: sem `silent_redirect_uri`, o
     iframe carregava a SPA inteira, que processava o código da renovação como login.
     Agora existe entry próprio do mesmo build (`silent-renew.html`, ADR-0028 D9
     preservado; coberto pelos `redirectUris` existentes — nenhum realm muda).
  3. O double-mount do React em dev gastava o código de uso único duas vezes ("Code not
     valid" como aviso falso): a troca virou promise única compartilhada no módulo.
- **Achados de ambiente**, corrigidos/registrados: `VITE_OIDC_AUTHORITY` do `.env.local`
  da raiz apontava porta velha (8081→8083, arquivo local do operador); e o PR #16 estava
  **aberto**, não mergeado (nenhum defeito de esteira — a lista de runs não mente).
- **A rede que faltava, agora na esteira**: passo **"Fumaça autenticada"** no
  `deploy-hml.yml` — navegador real atravessa raiz → porta (copy) → Keycloak (tema,
  pt-BR, sem seletor) → credenciais do usuário de fumaça (`smoke.hml`, tenant isolado,
  criado por `scripts/create_hml_smoke_user.sh`) → `Sessão:` → **`GET /v1/projects`
  200** → URL estável (loop reprova). É exatamente o teste que teria pego este incidente
  e o anterior antes de qualquer humano. Localmente, `npm run smoke:auth` roda o mesmo
  fluxo contra o stack local (validado verde nesta rodada, junto do headless com `?job`
  e do `smoke:callback`).
- **Adiado com registro**: o espelho local completo da borda (nginx local com upstreams
  parametrizados) — o proxy usa VIP privado do Google com SNI por serviço, e
  parametrizá-lo com fidelidade merece PR revisado próprio, não um anexo de incidente. O
  pulo do nginx permanece coberto pelos curls da T1 e pela fumaça de seis rotas da
  esteira.

## Revisão humana — rodada 4 (2026-08-19, a Fumaça Autenticada morde no primeiro dia)

O passo novo da esteira reprovou o primeiro deploy que atravessou: login fecha, sessão
abre, e `GET /v1/projects → 401 INVALID_TOKEN` (não `TOKEN_WITHOUT_TENANT` — o usuário de
fumaça estava perfeito, provado por decodificação dos claims: issuer público, `aud` com
`croquito-web`, tenant e papel presentes).

- **Causa raiz, provada por reprodução da validação fora da API**: o domínio público passa
  pelo **Cloudflare**, e a proteção de bot devolve **403 ao `Python-urllib`** — o
  User-Agent do PyJWT. A API não conseguia BAIXAR o JWKS pela borda pública; sem chaves,
  todo token é `INVALID_TOKEN`. Defeito de arquitetura latente: validação de token dando a
  volta pela borda pública.
- **Conserto em duas camadas**: `CROQUITO_OIDC_JWKS_URL` — a busca das chaves vai pela URL
  direta do serviço no Cloud Run, fora do Cloudflare (o `iss` validado continua sendo o
  público); e User-Agent próprio (`croquito-oidc/1.0`) no cliente JWKS. `oidc.py` ganhou o
  parâmetro (cacheado por par issuer×URL, com teste), a API o encadeia por config, e o
  deploy o define. O Cloudflare na frente do domínio agora está documentado no HML.md —
  não estava em lugar nenhum.
- Nota de método: foi a fumaça autenticada que pegou — exatamente como desenhada. Sem ela,
  o próximo humano a logar herdaria o mistério.

## Resultado da revisão

Seis diffs revisados linha a linha pelo modelo principal contra contrato, ADR-0032 e
Design System; verificação independente dos oráculos críticos (mutação do critério 5,
curl da borda, headless integrado). Nenhum `CODE_FINDING` aberto; pacote de evidência
completo. `REVIEW_PASS` — que, como sempre, **não é aprovação humana**: a decisão final é
do gate `READY_FOR_HUMAN_REVIEW`.
