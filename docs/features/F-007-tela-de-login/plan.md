# F-007 — Execution Plan

Produzido pelo Planner a partir do [Feature Contract](feature.md) aceito e do
[ADR-0032](../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md) (`Accepted`), no formato
exigido pelo [contrato de Planner](../../engineering-os/agents/planner.md). Harness e modelo
ficam fora do plano por regra do contrato; a atribuição é registrada à parte, em
`assignments.md`, após decisão humana.

```text
FEATURE EXECUTION PLAN

feature_id: F-007
goal: o endereço do produto abre uma porta com a cara do Croquito (celular e desktop); o
  "Entrar" atravessa um Keycloak com o tema croquito; a volta cai na jornada pedida,
  inclusive por link ?job=<uuid>; o retorno do OIDC nunca rebate (sem loop de login).
assumptions:
  - ADR-0032 D1–D8 fixa o desenho; nenhuma task decide arquitetura nova.
  - O mock revisão 2 (visual aprovado) é a referência da tela; o texto é gate humano à parte.
  - /medicao/ sem sessão está coberto por estrutura: a borda já redireciona /medicao/ para
    /revisao/?rodada=, que cai na regra de rebote de T2 preservando a query — não há decisão
    nova a tomar.
  - O ambiente local (make dev-services + make dev) verifica os critérios 1–8; a homologação
    verifica pós-deploy (F-006 DONE, ambiente no ar).
risks:
  - Loop de login (risco nº 1 do contrato): mitigado por T2 carregar o critério 5 como teste
    automatizado obrigatório, e pela revisão linha a linha do diff de T2.
  - Links ?job= já entregues: o smoke headless (T5) não pode ser afrouxado; critério 6.
  - Tema acoplado à versão do Keycloak: T4 verifica o formato na versão fixada (26.2), nunca
    infere de versão anterior; conferência visual template a template é critério 8.
  - T2 e T3 editam os mesmos arquivos (App.tsx, styles.css): PARALLELISM_RISK registrado;
    execução sequencial obrigatória.

tasks:
  - id: T1
    role: builder
    goal: a raiz da borda leva a /login e /login serve a SPA, com o cabeçalho do nginx
      descrevendo o mapa novo.
    scope: deploy/nginx.conf (troca do 302 da raiz, linhas 64–67; location nova `= /login`
      servindo /revisao/index.html com no-store e X-Content-Type-Options como as demais;
      cabeçalho de rotas, linhas 1–29, reconciliado).
    out_of_scope: qualquer mudança em /api/, /auth/, /medicao/, cache de assets; docs fora do
      próprio nginx.conf (HML.md é T6); nenhuma mudança de app.
    expected_areas: deploy/nginx.conf
    acceptance_criteria: critério 1 do contrato — GET / responde 302 /login (relativo, por
      causa do absolute_redirect off); GET /login serve o index.html da SPA com assets sob
      /revisao/assets/; verificado com curl contra o stack local (make dev-services + docker
      compose do deploy); make check verde.
    depends_on: []
    validation: make check; subida do nginx local e curl -i em /, /login, /revisao/,
      /medicao/ comparando com o mapa do cabeçalho.
    required_capabilities: READ repo; WRITE deploy/nginx.conf; VALIDATE make check + stack
      local; COMMIT forbidden.
    risk: baixo — config declarativa com oráculo direto; a armadilha conhecida é Location
      absoluto (proibido pelo absolute_redirect off, já declarado).
    relative_effort: S

  - id: T2
    role: builder
    goal: /login existe como estado da SPA e a regra de rebote de D3/D4 funciona sem
      interceptar o retorno do OIDC.
    scope: apps/web/src/route.ts (representar o estado de path /login acima da camada de
      jornada — as opções admissíveis ficam delimitadas no Task Contract; a decisão fica
      registrada no próprio código/testes); apps/web/src/App.tsx (ordem do efeito de sessão;
      sem sessão em /revisao/ → /login preservando a query, exceto com code+state na URL; com
      sessão em /login → /revisao/; telaAnonima deixa de ser o estado sem sessão);
      apps/web/src/App.test.tsx (asserção antiga substituída, teste novo do critério 5 que
      falharia com a regra ingênua, testes de rebote nos dois sentidos).
    out_of_scope: apps/web/src/auth.ts (o mecanismo de state/redirect_uri está correto e não
      é tocado — mudar redirectUris de realm é sinal de desenho errado, D5); o visual da tela
      (T3); styles.css.
    expected_areas: apps/web/src/route.ts, apps/web/src/App.tsx, apps/web/src/App.test.tsx
    acceptance_criteria: critérios 3, 4 e 5 do contrato, cada um com teste automatizado; o
      teste "Acesse uma revisão autenticada" substituído (não apagado) conforme critério 10;
      make check e make test verdes.
    depends_on: []
    validation: make check; make test; npm --workspace @croquito/web run test.
    required_capabilities: READ repo; WRITE os três arquivos do escopo; VALIDATE make
      check/test; COMMIT forbidden.
    risk: o mais alto da feature — o loop de login mora aqui; exige revisão linha a linha.
    relative_effort: M

  - id: T3
    role: builder
    goal: a tela de login do mock aprovado (revisão 2) vira o estado sem sessão real,
      responsiva de 360px a desktop, sem nenhuma peça da casca antes da sessão (D3).
    scope: apps/web/src/App.tsx (render do estado /login no lugar do telaAnonima; casca —
      topbar, pílula de schema, alternância — só com sessão); apps/web/src/styles.css
      (classes novas .login-*, exceção declarada de responsividade ao min-width global,
      tokens SÓ da tabela do Design System — valor novo do mock aprovado é citado como
      aprovado na revisão 2); botão "Entrar com Google" renderizado apenas quando existir
      identity provider no realm (critério 9 — com o realm atual, não renderiza).
    out_of_scope: lógica de rota/rebote (T2, já entregue quando T3 começa); copy fora do
      conjunto aprovado pelo gate humano de texto; qualquer mudança nas jornadas.
    expected_areas: apps/web/src/App.tsx, apps/web/src/styles.css, apps/web/src/App.test.tsx
    acceptance_criteria: critérios 2 e 9 do contrato; fidelidade ao mock (composição,
      hierarquia, peso do CTA) conferida contra os PNGs aprovados; make check e make test
      verdes.
    depends_on: [T2]
    validation: make check; make test; conferência visual contra
      mock/01-login-desktop.png e mock/02-login-celular.png em 390px e 1440px.
    required_capabilities: READ repo (incl. mock e DESIGN_SYSTEM.md); WRITE os arquivos do
      escopo; VALIDATE make check/test + dev server; COMMIT forbidden.
    risk: médio — nuance de design system (regras de --accent/--accent-text) e a exceção de
      responsividade que precisa continuar declarada.
    relative_effort: M

  - id: T4
    role: builder
    goal: o tema croquito veste o Keycloak — login e as páginas que a F-008 vai alcançar,
      mais os e-mails — e os dois realms apontam para ele.
    scope: keycloak/ (diretório de tema novo; formato VERIFICADO na versão fixada 26.2, sem
      inferir de versões anteriores — é o primeiro passo da task); keycloak/Dockerfile (COPY
      do tema na fase correta, verificada); keycloak/croquito-realm.json e
      keycloak/croquito-hml-realm.json (loginTheme: "croquito"); docker-compose.local.yml se
      necessário para testar o tema localmente (montagem de volume, sem trocar a imagem);
      templates: login.ftl, login-reset-password, login-update-password, login-verify-email,
      login-page-expired e os templates de e-mail.
    out_of_scope: qualquer capacidade de conta (F-008); segredos no tema (política do
      Dockerfile: camada de imagem é pública para quem puxa); mudanças de realm além do
      loginTheme; deploy (gate humano).
    expected_areas: keycloak/
    acceptance_criteria: critérios 7 e 8 do contrato — a página de login serve o tema com
      logo e paleta da marca E o formulário continua encontrado pelo seletor do smoke
      (#kc-form-login, input[name='username']); cada template do escopo aberto e conferido
      visualmente no Keycloak local, com captura de tela arquivada como evidência; make
      check verde.
    depends_on: []
    validation: make check; Keycloak local (make dev-services) servindo o tema; capturas de
      cada template como evidência.
    required_capabilities: READ repo; WRITE keycloak/ e docker-compose.local.yml; VALIDATE
      stack local + build da imagem; COMMIT forbidden.
    risk: alto em manutenção (tema acoplado à versão), médio em execução; o unknown do
      formato 26.2 é resolvido dentro da task por verificação, não por suposição.
    relative_effort: L

  - id: T5
    role: builder
    goal: a rede de regressão atravessa o desenho novo sem afrouxar nada — smoke de borda e
      e2e headless.
    scope: scripts/smoke_hml.py (verificações novas: GET / responde 302 para /login; GET
      /login serve a SPA); apps/web/e2e/smoke-headless.mjs (fluxo novo: raiz → tela de login
      → CTA → formulário do Keycloak com o MESMO seletor de hoje → volta com ?job
      preservado — critério 6 intacto, nenhum seletor ou asserção afrouxado).
    out_of_scope: qualquer mudança de app, borda ou tema para "fazer o teste passar" — se o
      teste não passa, a task para e reporta; os quatro checks existentes do smoke_hml.py
      não são enfraquecidos.
    expected_areas: scripts/smoke_hml.py, apps/web/e2e/smoke-headless.mjs
    acceptance_criteria: critério 6 do contrato (o e2e parte de ?job e termina no job, verde
      sem relaxamento); os checks novos de / e /login passam contra o stack local; make
      check e make test verdes.
    depends_on: [T1, T2, T3, T4]
    validation: make check; make test; CROQUITO_ALLOW_TEST_TOKENS=true make smoke-local;
      execução do smoke-headless contra o stack local.
    required_capabilities: READ repo; WRITE os dois arquivos do escopo; VALIDATE stack local
      completo; COMMIT forbidden.
    risk: médio — é a única rede que atravessa o redirect real; o anti-padrão nomeado é
      afrouxar para caber no desenho.
    relative_effort: S

  - id: T6
    role: builder
    goal: a documentação operacional descreve o mapa novo.
    scope: docs/operations/HML.md (mapa de rotas com /login; fumaça manual ganha o check da
      raiz); varredura de menções ao mapa antigo ("/ redireciona para /revisao/") em docs/.
    out_of_scope: STATUS.md/ROADMAP.md (transições de estado são do workflow, não desta
      task); qualquer arquivo de app ou borda.
    expected_areas: docs/operations/HML.md
    acceptance_criteria: HML.md descreve o mapa novo e a fumaça manual inclui a raiz;
      make check verde (check_docs pega link quebrado).
    depends_on: [T1]
    validation: make check.
    required_capabilities: READ docs; WRITE docs/operations/HML.md; VALIDATE make check;
      COMMIT forbidden.
    risk: baixo.
    relative_effort: XS

parallel_groups:
  - [T1, T2, T4]   # arquivos disjuntos: borda, SPA-lógica, tema
  - [T3]           # depois de T2 (mesmos arquivos de T2/T3: sequencial por PARALLELISM_RISK)
  - [T5, T6]       # T5 depois de T1–T4; T6 depois de T1; entre si, arquivos disjuntos
critical_path: T2 → T3 → T5 — a lógica de sessão (M) precede a tela (M), que precede a rede
  de regressão (S); T4 (L) corre em paralelo e só converge em T5.
integration_strategy: uma branch de feature; cada task entra como commit(s) próprios com seu
  BUILD REPORT preservado em evidence.md; integração final valida make check + make test +
  smoke-local antes de READY_FOR_REVIEW; deploy de homologação (imagem nova do Keycloak) só
  após merge, pelo pipeline existente, e é gate humano.
human_gates:
  - Aprovação do texto da tela ANTES de T3 executar (gate do contrato; o visual já foi
    aprovado na revisão 2).
  - Decisão sobre a pílula de ambiente (só homologação ou também produção) antes de T3.
  - Autorização para a execução começar (gate do contrato).
  - Deploy da imagem nova do Keycloak em homologação (pós-merge, gate do contrato).
planning_findings:
  - PARALLELISM_RISK: T2 e T3 editam App.tsx/App.test.tsx (e T3 styles.css); sequencial.
  - O unknown "/medicao/ sem sessão" resolve por estrutura (borda já redireciona para
    /revisao/?rodada=, que cai no rebote de T2 preservando a query); nenhuma decisão nova.
  - O unknown "representação de /login em route.ts" fica delimitado no Task Contract de T2
    (decisão de implementação dentro do desenho do ADR-0032, não decisão arquitetural nova).
  - O unknown "formato do tema no Keycloak 26.2" é resolvido por verificação dentro de T4.
  - Nenhum ARCHITECTURE_DECISION_REQUIRED: o ADR-0032 (Accepted) cobre o desenho inteiro.
  - DESIGN_APPROVAL: pacote aprovado (mock revisão 2) cobre o visual; o TEXTO segue gate
    humano aberto e está nomeado acima — nenhuma task inventa copy.
```

## Validação do plano

`PLAN_VALID` — verificado contra o checklist do contrato de Planner em 2026-08-18: IDs
únicos; toda dependência nomeia task existente; grafo acíclico (T3←T2; T5←T1,T2,T3,T4;
T6←T1); cada task tem critérios verificáveis, validação com comandos reais do projeto,
capacidades e risco; nenhum requisito do contrato ficou sem dono (critérios 1→T1, 2→T3,
3–5→T2, 6→T5, 7–8→T4, 9→T3, 10→T2/T3/T5); paralelismo declarado não compartilha arquivo;
caminho crítico justificado por esforço relativo e dependência.

## Desvios do plano

Nenhum registrado. Após o congelamento, mudanças entram aqui como `PLAN_DEVIATION`.
