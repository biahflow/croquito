# T4 — Build Report

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - docs/features/F-012-operacao-saas-autorizacao-ia/feature.md
      motivo: Status IN_PROGRESS -> READY_FOR_REVIEW (T1-T3 completas, T4 fechando a
      implementação); é o estado real ao fim desta task, e precisa andar em par com a
      linha do ROADMAP (exigido por validate_roadmap_feature_parity em check_docs.py).
  - docs/product/ROADMAP.md
      motivo: linha F-012 IN_PROGRESS -> READY_FOR_REVIEW (par com feature.md); cinco
      linhas novas na tabela "Trabalho de engenharia em andamento" para F-013..F-017
      (inventário SaaS aberto pelo Out of Scope da F-012, formato "A DEFINIR /
      READY_FOR_SPEC" igual ao já usado por F-010/F-011); parágrafo narrativo da F-012
      (decisão, ADR-0036, as quatro tasks e o que resta) e parágrafo do inventário
      F-013..F-017 com uma linha cada e a data de nascimento (2026-08-19), inseridos após
      o parágrafo de F-011 e antes de "## Agora — MVP privado"; nota na "Última revisão"
      do cabeçalho.
  - docs/STATUS.md
      motivo: parágrafo da F-012 no estilo dos existentes (decisão, ADR-0036, o que as
      quatro tasks entregaram, o que resta, inventário F-013..F-017), inserido depois do
      parágrafo da F-009 e antes de "## Condição para avançar ao processamento real"; nota
      curta de atualização no próprio parágrafo da F-009, porque ele lista a allowlist por
      digest como pendência que a F-012 fechou (evitar leitura desatualizada sem reescrever
      o parágrafo histórico); "Última revisão" do cabeçalho ganhou a menção à F-012.
  - docs/operations/HML.md (seção "Providers de IA")
      motivo: tabela de envs perdeu a linha de `CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS`
      (variável que o worker hospedado não lê mais); "Status real" ganhou frase apontando
      o ADR-0036 sem reescrever a descrição do ADR-0035; runbook de ativação reescrito —
      os passos de infra (secrets do GitHub, PR/apply em `biahflow/infra`) viram um bloco
      histórico único ("concluída em 2026-08-19, não se repete por tenant nem por
      documento") em vez de passo numerado do fluxo de ativação por tenant; "ativar a
      autorização contratual do tenant" por curl virou "ativar pela jornada Plataforma"
      (`?plataforma=`, papel `platform_operator`, sem curl nem token do DevTools); o passo
      de digest da allowlist foi removido inteiro (não existe mais); o passo de
      merge=deploy por documento saiu, porque nenhuma ativação por tenant exige mais
      commit; "subir o PDF pela SPA depois da ativação" e o rollback pela flag
      permaneceram; aviso de custo permaneceu, com a frase final trocada de "o teto e a
      allowlist" para "sem allowlist por documento, o teto e o kill switch são a única
      segunda camada"; referência cruzada ao "passo 2" (que não existe mais como número)
      corrigida para apontar o bloco de infra; "Última revisão" do cabeçalho atualizada.
  - docs/product/FDD.md (seção "1. Autenticação e projetos")
      motivo: mudança de comportamento (Disciplina de mudança do AGENTS.md raiz) — a
      frase "administrada por um operador da plataforma fora da tela de revisão" descrevia
      o ritual manual anterior (curl); passou a descrever a jornada "Plataforma" real,
      dentro do produto, visível só ao papel `platform_operator`; "Última revisão" do
      cabeçalho atualizada.
  - docs/adr/0035-suite-hospedada-openai-anthropic-direto.md
      motivo: nota curta pedida pelo spec — o D6 (allowlist por digest) recebeu uma nota
      apontando o ADR-0036 sem reescrever a decisão original; a pendência registrada
      "rota de plataforma dedicada para administrar a allowlist" ganhou uma linha
      marcando-a resolvida por ADR-0036 (a allowlist foi removida, não administrada por
      rota nova). O ADR-0035 não foi reaberto nem teve Status/Decisão/Consequências
      reescritos.
  - apps/web/AGENTS.md
      motivo: pendência de escopo que a T3 registrou explicitamente ("apps/web/AGENTS.md
      não tem seção da jornada de plataforma... documentação é a T4"). Decisão registrada
      abaixo em "Desvios conscientes": tratada como dentro do escopo desta task porque a
      Disciplina de mudança do AGENTS.md raiz manda atualizar FDD em mudança de
      comportamento, e este arquivo é onde as regras de produto de cada jornada
      (croqui/medição) já vivem — deixar a jornada nova sem a seção equivalente
      contradiria o padrão do próprio arquivo. Mudanças: leitura obrigatória ganhou
      referência ao ADR-0036 e à seção do FDD; "Boundary" passou de duas para três
      jornadas, com uma frase sobre o que a jornada de plataforma não faz; nova seção
      "Regras da jornada de plataforma (`src/plataforma/`)" espelhando o formato da seção
      de medição (precedência de rota, botão condicional ao papel, `GET /v1/me` uma vez
      por sessão e fail-closed, montagem por rota não por papel, `Idempotency-Key` sem
      bloqueio client-side de `agreement_reference`, duplicação deliberada de
      `formatarInstante`, ausência de folha própria); "Conclusão" ganhou o mesmo padrão de
      instrução que a seção de medição já tem (mudança de comportamento -> FDD; mudança de
      contrato -> rotas `/v1/me`/`/v1/platform/*` primeiro, depois aqui).

Validation executed:
  - make check -> verde (ruff check, ruff format --check, mypy strict em 187 arquivos,
    check_docs.py: "Documentação válida: 197 arquivos Markdown, paridade de lifecycle
    verificada", schema_export --check-dir, contracts:check, web:check — tsc -b + vite
    build —, infra-check: terraform fmt -check)
  - grep manual em docs/operations/HML.md por "AI_EXTRACTION_ALLOWED_DIGESTS|allowlist" ->
    as únicas ocorrências restantes descrevem a remoção (cabeçalho, "Status real", início
    do runbook, aviso de custo); nenhuma é passo vivo de ativação (critério de aceite 2)
  - leitura da tabela "Trabalho de engenharia em andamento" do ROADMAP.md após a edição:
    F-012 READY_FOR_REVIEW e F-013..F-017 A DEFINIR/READY_FOR_SPEC presentes, cada um com
    uma linha (critério de aceite 3); datas de nascimento (2026-08-19) registradas no
    parágrafo narrativo logo abaixo da tabela
  - git status --short -> só os sete arquivos Markdown listados acima; nenhum código
    tocado

Validation skipped: none (a task não exige make test; a Validation do contrato lista só
  "full: make check")

Unavailable capabilities: none

Assumptions:
  - "Disciplina de mudança" do AGENTS.md raiz ("mudança de comportamento: atualize FDD e
    critérios de aceite") foi lida como cobrindo tanto a seção 1 do FDD (autorização de IA
    passou a ser administrada pela jornada, não por curl) quanto a seção de regras de
    `apps/web/AGENTS.md`, que documenta o comportamento de produto de cada jornada web —
    tratado como escopo desta task por já estar registrado como pendência explícita da T3,
    e não como "aproveitar para melhorar" área vizinha.
  - O parágrafo da F-009 em STATUS.md, que lista a allowlist por digest entre o que
    "resta" da F-009, não foi reescrito por ser registro histórico de um marco fechado;
    recebeu só uma nota curta de atualização apontando o parágrafo novo da F-012, na
    mesma lógica que o próprio ADR-0036 usa para o ADR-0035 (nota, não reescrita).
  - RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md **não foi tocado**: a allowlist que ele cita
    (`CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS`, `extract-legend-real`) é do caminho
    offline de `extraction_eval.py`, explicitamente preservado pelo ADR-0036 — o
    ADR-0036 cita esse runbook como "atualizado pela T4" ao lado de HML.md no bloco de
    riscos, mas o texto do próprio runbook mostra que o uso ali é o caminho que continua
    vivo (operador que roda o comando de medição autoriza o próprio documento); mudar
    esse texto estaria fora do que o spec de T4 pediu (HML.md, ROADMAP.md, STATUS.md,
    feature.md, FDD, MODEL_ROUTING/ADR-0035) e descreveria incorretamente um mecanismo
    que segue correto. Registrado aqui como leitura consciente do ADR-0036, não como
    lacuna.
  - docs/ai/MODEL_ROUTING.md não menciona a allowlist (`grep` vazio) — nenhuma edição
    necessária ali, conforme o próprio spec pedia para conferir antes de mexer.
  - docs/architecture/API_CONTRACT.md não foi tocado: já reflete `GET /v1/me` e os dois
    GETs de plataforma (entregue pela T2); não cita allowlist por digest; nada no spec de
    T4 pedia mudança lá além do que a T2 já fez.

Remaining risks: nenhum identificado dentro do escopo desta task (documentação). O ADR-0036
  segue `Proposed` — aceite é ato humano, já registrado como Human Gate na feature e não
  antecipado por esta task.

Human decisions required: aceite do ADR-0036 (Proposed -> Accepted/Rejected); merge da
  feature F-012 (= deploy), ambos já declarados como Human Gates da feature e do plano.
```

## Desvios conscientes do spec

1. **`apps/web/AGENTS.md` foi editado, mas não estava na lista `Scope` literal da task
   (que cita `HML.md`, `ROADMAP.md`, `STATUS.md`, `feature.md`, `FDD.md` e a checagem em
   `MODEL_ROUTING.md`/ADR-0035).** O próprio spec pedia para verificar e decidir: "inclua-a
   no seu escopo de docs se a Disciplina de mudança do AGENTS.md mandar documentar jornada
   nova". A Disciplina de mudança do AGENTS.md raiz diz "mudança de comportamento: atualize
   FDD e critérios de aceite" — não cita `apps/web/AGENTS.md` por nome — mas o próprio
   `apps/web/AGENTS.md` já é o lugar onde as regras de produto de cada jornada web vivem
   (seção "Regras da jornada de medição") e a T3 registrou expressamente a lacuna como
   pendência desta task. Decisão: tratar como dentro do escopo, por ser o padrão já
   estabelecido pelo próprio arquivo e por já estar nomeado como pendência da T3, não uma
   extensão de escopo por iniciativa própria.
2. Nenhum outro desvio. Runbook, ROADMAP e STATUS seguem o formato e a distribuição de
   arquivo pedidos pelo spec; `RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md` foi deliberadamente
   deixado intocado pelo motivo documentado em "Assumptions".

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- `docs/architecture/API_CONTRACT.md` não ganhou seção própria de "jornada de plataforma"
  na documentação de produto — só a seção técnica de rotas que a T2 já escreveu. Não fazia
  parte do spec desta task.
- Nenhuma folha de estilo própria para a jornada de plataforma (`apps/web/AGENTS.md` só
  registra que ela reaproveita classes existentes) — já declarado como decisão pendente de
  produto no BUILD REPORT da T3, fora do escopo de documentação desta task.
- `docs/ai/MODEL_ROUTING.md` não foi editado porque não menciona a allowlist — conferido
  por `grep`, conforme o spec pedia.
