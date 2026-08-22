# F-037 — Plano de execução

feature_id: F-037
goal: a orçamentista escolhe a tabela de preços de uma lista publicada pela plataforma, em
vez de obter e subir um arquivo JSON — mantendo o upload como caminho declarado para tabela
própria, e sem afrouxar nenhuma guarda de isolamento.

assumptions:
- **A migração é a `0014`.** A última na main é `0013_review_interaction_ms.py`. Se outra
  branch entrar antes, é rebase de integração; o encadeamento relativo entre as tasks é que
  precisa sobreviver.
- **O acervo nasce só com SCO.** O `catalog.json` do SCO-Rio 07/2026 já está importado
  localmente (`output/sco-rio-2026-07/catalogo-D/` e `catalogo-O/`, 4.865 entradas cada).
  SINAPI e SICRO dependem de download manual — apurado em 2026-08-22 que a Caixa responde
  `429` a automação e o DNIT monta a listagem por JavaScript. **Isso não bloqueia nenhuma
  task**: o acervo funciona com uma tabela, e as duas variantes do SCO já dão duas opções
  reais na lista.
- Recusa é `403`/`409`/`422` com código estável em `application/problem+json`, como o resto
  da API.
- A jornada do acervo é do orçamento (`/v1/estimate-rounds` já cai no prefixo `orcamento` de
  `JOURNEY_ROUTE_PREFIXES`); a administração é `/v1/platform`, que é `JOURNEYLESS`.

risks:
- **Primeira tabela sem `tenant_id` do projeto.** Verificado: as 26 tabelas de
  `database.py` têm `tenant_id`, duas até na chave primária. Mitigação: a condição que
  sustenta a ausência está no ADR-0047 decisão 1 e vira **teste** na T1, não comentário.
- **Três guardas de prefixo dependem de comparação de string** — `signed_artifact_url`
  (`valuation_rounds.py:601`), `_preview_urls` (`main.py:2873`) e `_export_response`
  (`main.py:2887`). Mitigação: o objeto do acervo fica fora de `tenants/` e **nenhuma rota
  o assina**; a T1 cobre a recusa com teste, e recusar é o comportamento correto.
- `main.py` tem 10.686 linhas e `OrcamentoApp.tsx` 2.842. Mitigação: T1 e T2 entram por
  seams que já existem (`_install_catalog`, `ensure_source_installable`,
  `round_state_payload`), e a tela é conferida contra as capturas aprovadas renderizando com
  a folha real — foi assim que a F-034 achou três divergências que o recorte de CSS escondia.
- **Contrato de rota existente muda**: `POST .../catalogs` passa a aceitar duas formas de
  entrada. Mitigação: `upload_id` continua funcionando idêntico; a forma nova é alternativa,
  não substituição, e o snapshot de OpenAPI torna a mudança visível.

## O que o levantamento decidiu, e economizou

**O acervo não importa formato bruto.** A rota de instalação aceita só `application/json`
(`_install_catalog`, `main.py:2576-2625`), e os importadores de `.xlsx`/`.dbf` rodam apenas
no CLI local — nunca em request path da API ou do worker. O ADR-0047 decisão 9 fixou que
isso **não muda**: o operador importa pelo CLI que já existe e publica o `catalog.json`. Isso
tira do escopo um leitor de formato binário sobre arquivo externo dentro do servidor, que
seria superfície de ataque nova sem valor de produto correspondente.

**O produto já compartilha catálogo entre tenants.** `CatalogCache`
(`valuation_rounds.py:623`) decodifica por digest e é explicitamente cross-tenant: "duas
rodadas com o mesmo catálogo compartilham a mesma decodificação de propósito, porque o
conteúdo é idêntico byte a byte". O acervo torna isso persistente; não inventa o conceito.

**Publicar não tem tenant alvo, e a auditoria não aceita tenant nulo** (`_record_audit`,
`main.py:2010`). Decisão 11 do ADR-0047: grava o tenant **do operador**, que é o fato
verdadeiro, com o identificador do catálogo nos detalhes.

tasks:
  - id: T1
    role: builder
    goal: o acervo existe, é administrado por platform_operator e é imutável por digest
    scope: migração 0014 (tabela `reference_catalogs`, sem `tenant_id`), modelo SQLAlchemy,
      chave de objeto sob prefixo próprio fora de `tenants/`, rotas `/v1/platform/`
      (publicar, listar, retirar de circulação), auditoria pelo tenant do operador,
      snapshot de OpenAPI, testes de API — inclusive o teste da guarda de prefixo e o de
      republicação do mesmo conteúdo.
    out_of_scope: qualquer arquivo de `apps/web`; a rota de escolha e a instalação a partir
      do acervo (é a T2); importar `.xlsx`/`.dbf` no servidor.
    depends_on: []
    validation: make check, make test
    relative_effort: L
  - id: T2
    role: builder
    goal: instalar na cascata a partir do acervo, com a procedência registrada
    scope: rota de listagem do que está disponível para a rodada (filtrada pelo regime),
      `POST .../catalogs` aceitando referência do acervo como alternativa a `upload_id`,
      procedência na `CascadeEntry` e no estado da rodada, snapshot de OpenAPI, testes.
    out_of_scope: qualquer arquivo de `apps/web`; mudar as regras existentes da cascata
      (origem duplicada, regime, trava por decisão de código) — elas valem iguais.
    depends_on: [T1]
    validation: make check, make test
    relative_effort: M
  - id: T3
    role: builder
    goal: administrar o acervo na jornada de Plataforma, conforme a revisão aprovada
    scope: `apps/web/src/plataforma/` — aba nova, lista com fora de circulação, publicação,
      recusa de republicar, rótulos e testes.
    out_of_scope: qualquer arquivo de `services/`; a tela do orçamento (é a T4).
    depends_on: [T1]
    validation: npm --workspace @croquito/web run test, npm run web:check
    relative_effort: M
  - id: T4
    role: builder
    goal: a escolha da tabela na cascata do orçamento, conforme a revisão aprovada
    scope: `apps/web/src/orcamento/` — a lista como caminho principal, o upload como
      alternativa nomeada, a procedência na cascata, o acervo vazio, o filtro sob regime,
      rótulos e testes.
    out_of_scope: qualquer arquivo de `services/`; a tela de plataforma (é a T3); o bloco
      **reservado** do mock (atualização automática).
    depends_on: [T2]
    validation: npm --workspace @croquito/web run test, npm run web:check
    relative_effort: M
  - id: T5
    role: builder
    goal: e2e da cadeia publicando no acervo e montando orçamento a partir dele
    scope: `tests/e2e/` — publicar como operador, escolher como orçamentista, montar o
      orçamento e conferir que a proveniência por linha é a mesma do caminho de upload.
    out_of_scope: qualquer arquivo de produção; qualquer arquivo de `apps/web`.
    depends_on: [T2]
    validation: uv run pytest tests/e2e/, make test
    relative_effort: S

  - id: T6
    role: builder
    goal: presign próprio da plataforma, para publicar não depender da jornada do croqui
    scope: rota de presign sob `/v1/platform` no molde de `presign_upload`, com papel de
      plataforma e tipo fixo; API Contract; snapshot de OpenAPI; testes — inclusive o que
      publica com o croqui `disabled`.
    out_of_scope: `journeys.py` inteiro; `POST /v1/uploads/presign`; qualquer arquivo de
      `apps/web`.
    depends_on: [T1]
    validation: make check, make test
    relative_effort: S

## PLAN_DEVIATION — T6 acrescentada em 2026-08-22

Registrada conforme o contrato do Planner: **mudança em trabalho planejado depois de o plano
ser congelado**.

- **Task**: T6, nova.
- **Estado planejado**: cinco tasks; publicar no acervo usaria `POST /v1/uploads/presign`,
  como o Task Contract da T1 instruiu.
- **Estado real**: a revisão da T1 apurou que `/v1/uploads` cai no prefixo `croqui` de
  `JOURNEY_ROUTE_PREFIXES` e que o portão da F-034 é dependência do router — logo, um
  ambiente com o croqui desligado deixa o acervo sem como ser alimentado. O croqui é
  justamente o módulo que a F-034 nasceu para poder desligar.
- **Impacto**: uma task nova de esforço `S`, dependente só da T1; não altera o caminho
  crítico (T1 → T2 → T4). A T3 passa a chamar a rota nova em vez do presign genérico.
- **Resolução**: decisão humana de 2026-08-22 — presign próprio sob `/v1/platform`. A
  alternativa de classificar `/v1/uploads` como sem jornada foi **recusada**: resolveria
  isto enfraquecendo a F-034.

parallel_groups:
- [T3, T4, T5] — T3 depende só de T1; T4 e T5 dependem de T2. Não compartilham arquivo:
  T3 é `apps/web/src/plataforma/`, T4 é `apps/web/src/orcamento/`, T5 é `tests/e2e/`.
- T6 depende só de T1, mas toca `main.py` — **não** roda junto com T2, que também o toca.
critical_path: T1 → T2 → T4. É o caminho que leva ao valor da feature (a orçamentista
  escolhendo), e T1 é a task de maior esforço porque carrega a tabela nova, a migração e a
  decisão de isolamento.
integration_strategy: commits separados por task, com revisão linha a linha entre eles.
  Nenhuma task encerra com portão vermelho. T1 e T2 tocam `main.py`; rodam em sequência, não
  em paralelo, para não disputar o mesmo arquivo.
human_gates: nenhum aberto. ADR-0047 `Accepted` e Design Approval Package revisão 1 aprovado,
  ambos por ato humano em 2026-08-22. Seguem **fora** desta aprovação, por declaração
  explícita do registro: a copy final, os nomes de rota e os códigos de erro. Publicar os
  arquivos reais em homologação é ato do operador, pós-deploy.
planning_findings:
- **A listagem do acervo cabe melhor sob a rodada do que global.** A rodada conhece o regime
  e pode filtrar; uma rota global obrigaria a tela a reimplementar a regra do regime, que é
  exatamente o que a F-033 evitou ao publicar `allowed_cascade_origins` do servidor. Fica
  como decisão da T2, registrada aqui como recomendação forte.
- **A questão aberta 2 do pacote de design** — o que fazer quando houver muitas data-bases da
  mesma tabela — **não** é resolvida por nenhuma task. Com uma ou duas por origem a lista
  simples serve. É a primeira coisa a revisitar quando o acervo crescer.
