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

## Resultado da revisão

Seis diffs revisados linha a linha pelo modelo principal contra contrato, ADR-0032 e
Design System; verificação independente dos oráculos críticos (mutação do critério 5,
curl da borda, headless integrado). Nenhum `CODE_FINDING` aberto; pacote de evidência
completo. `REVIEW_PASS` — que, como sempre, **não é aprovação humana**: a decisão final é
do gate `READY_FOR_HUMAN_REVIEW`.
