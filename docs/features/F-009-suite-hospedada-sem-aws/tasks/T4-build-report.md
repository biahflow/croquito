# T4 — BUILD REPORT

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  docs/adr/0035-suite-hospedada-openai-anthropic-direto.md (novo)
    - ADR registrando a suite hospedada sem AWS: contexto (AWS nunca rodou no ambiente
      GCP publicado; OCR do Textract era código morto; OCR_EVIDENCE_MISSING documentado
      nunca implementado), decisão (D1-D6: três braços openai/anthropic/ocr, Anthropic
      primário/OpenAI reserva com notas PROVIDER_FALLBACK_*, corroboração de OCR por
      leitura, rótulos honestos, 401/403 REFUSED não-retryável, teto/allowlist/kill
      switch), alternativas (Vertex AI, Document AI como escalada, manter Bedrock),
      consequências (revisita parcial do ADR-0002, custo de reentrega 5x, retenção 7
      dias), pendências (incluindo F-010) e riscos remanescentes herdados dos build
      reports T1/T3/T5. Status Proposed — aceitação é ato humano.
  docs/adr/README.md
    - Linha nova do índice para o ADR-0035 (Proposed), exigida pelo processo de ADR e
      pelo portão de paridade índice×arquivo do check_docs.
  docs/ai/MODEL_ROUTING.md
    - "Rotas padrão" reescrita: suite hospedada com Anthropic primário/OpenAI
      reserva/OCR Cloud Vision, sem Bedrock/Textract; seções novas "Fallback e
      comparação dupla" e "Caminho de comparação: eval por linha de comando"
      (build_extraction_arm, independente da suite hospedada, ainda fala Bedrock só
      para eval); "Estado de implementação local" e "Falhas" reescritas com a
      semântica real (PROVIDER_FALLBACK_*, READING_n_OCR_CONFIRMED/_EVIDENCE_MISSING,
      OCR_UNAVAILABLE, BUDGET_EXCEEDED nunca aciona fallback); pendência das linhas
      ~29-35 fechada (providers_json agora inclui anthropic, e o motivo de ocr ficar
      fora está registrado).
  docs/operations/HML.md
    - Seção nova "Providers de IA": tabela de envs/segredos do deploy do worker,
      runbook de ativação em 8 passos na ordem do contrato (secrets do GitHub em
      biahflow/infra -> PR/plan/apply pela esteira -> Keycloak -> entitlement (curl
      pronto) -> digest na allowlist -> merge=deploy -> re-upload -> rollback pela
      flag), com o estado real dos PRs de infra (#14 mesclado com apply que falhou em
      403 no Vision; #15 concede a permissão que falta, aguardando merge) e aviso de
      custo (teto por invocação x reentrega, pior caso 5x).
  docs/product/ROADMAP.md
    - Linha F-009 corrigida para apontar à suite hospedada real (antes apontava para
      "Jornada guiada da revisão", um item DIFERENTE que colidia no mesmo ID — ver
      "Desvios conscientes"); linha nova F-010 (revisão assistida em lote, aprovada
      2026-08-19); "Jornada guiada da revisão" renumerada de F-009 para F-011;
      parágrafos correspondentes reescritos/adicionados; data de revisão atualizada.
  docs/features/F-009-suite-hospedada-sem-aws/feature.md
    - Status de READY_FOR_BUILD para READY_FOR_REVIEW (T1/T2/T3/T5 BUILD_COMPLETE,
      T4 fecha a documentação); bloco novo no callout listando o que resta (ato
      humano: ADR, infra, segredos, entitlement, allowlist, merge/deploy).
  docs/STATUS.md
    - Cabeçalho "Última revisão" ganha a menção a F-009/ADR-0035; parágrafo novo
      antes de "Condição para avançar ao processamento real" registrando o
      diagnóstico, a suite nova e o que resta (mesmo conteúdo factual do ADR/roadmap,
      na convenção narrativa deste arquivo — mesmo padrão usado para F-006/F-007/F-008).

Validation executed:
  BASELINE: make check verde herdado de T1+T2+T3+T5 (confirmado nos build reports
    dessas tasks; branch estava com working tree limpo ao iniciar esta task).
  FINAL:
    uv run python scripts/check_docs.py
      -> "Documentação válida: 186 arquivos Markdown, paridade de lifecycle
         verificada." (checa TODO link relativo, paridade ADR índice x arquivo, e
         paridade ROADMAP x feature.md/Status)
    make check -> exit 0
      ruff check . -> All checks passed!
      ruff format --check . -> 350 files already formatted
      mypy --strict (packages/core, packages/valuation, services/api,
        services/worker, tests) -> Success: no issues found in 187 source files
      scripts/check_docs.py -> verde (acima)
      schema_export --check-dir packages/contracts -> sem drift
      contracts:check -> sem drift
      web:check (tsc -b && vite build) -> build limpo
      infra-check (terraform fmt -check -recursive infra) -> sem diff
  Nenhum arquivo fora de docs/ foi tocado (git status --porcelain confirma: só
    docs/STATUS.md, docs/adr/README.md, docs/ai/MODEL_ROUTING.md,
    docs/features/F-009-suite-hospedada-sem-aws/feature.md, docs/operations/HML.md,
    docs/product/ROADMAP.md modificados, e docs/adr/0035-*.md novo).

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - O estado real da F-009 ao fim desta task é READY_FOR_REVIEW (T1/T2/T3/T5
    BUILD_COMPLETE, T4 fechando a documentação; a revisão linha a linha do modelo
    principal ainda não ocorreu). O contrato deixou a decisão explícita a critério do
    executor ("conforme o estado real na sua execução"); READY_FOR_REVIEW é o estado
    do vocabulário de lifecycle que corresponde a "implementação integrada aguardando
    review" na tabela da Engineering OS.
  - F-010 "revisão assistida em lote" entra no ROADMAP como BACKLOG/READY_FOR_SPEC —
    usei READY_FOR_SPEC (aprovada por ato humano, mas ainda sem Feature Contract),
    espelhando o padrão já usado para "Jornada guiada da revisão" antes desta
    revisão.
  - Os fatos sobre os PRs #14/#15 de biahflow/infra vieram da instrução de lançamento
    (usuário já os havia verificado); confirmei via `gh pr view` antes de escrever
    (título, corpo e estado de cada PR) em vez de transcrever às cegas — ambos batem
    com o que a instrução descreveu.
  - Não toquei docs/architecture/API_CONTRACT.md, docs/adr/0002-*.md, nem
    docs/architecture/AWS_DEPLOYMENT.md: nenhum deles está listado no escopo do
    contrato, e nenhum contém afirmação que a suite hospedada nova contradiga (o
    ADR-0002 continua descrevendo o desenho de PRODUÇÃO em AWS, que esta entrega não
    altera — só a suite HOSPEDADA deixa de depender de AWS, e o ADR-0035 registra
    essa distinção explicitamente).

Remaining risks:
  - ADR-0035 nasce Proposed; até aceitação humana, a decisão registrada não é
    vinculante — comportamento normal do processo, não risco desta entrega.
  - O runbook de HML.md descreve o passo 2 (PR/apply em biahflow/infra) com o estado
    de 2026-08-19; se o merge do PR #15 e o re-apply acontecerem antes de alguém ler
    este runbook, a seção "Estado real em 2026-08-19" ficará desatualizada até
    próxima revisão — é prosa datada por desenho (mesmo padrão de "Estado verificado"
    em HML.md), não lacuna estrutural.
  - Notei que docs/STATUS.md já registra uma divergência PREEXISTENTE não
    relacionada a esta task: a seção sobre F-007 (linha ~936-938) ainda diz
    `READY_FOR_PLANNING`, mas o ROADMAP.md e o feature.md de F-007 já mostram
    `READY_FOR_HUMAN_REVIEW` (PRs #13-#18 da F-007 já mesclados). Não corrigi —
    está fora do escopo desta task (F-007, não F-009) e corrigi-la seria consertar
    área alheia sem instrução. Registrado como oportunidade não implementada abaixo.

Human decisions required:
  - Aceitar ou rejeitar o ADR-0035 (Proposed).
  - Mergear biahflow/infra#15 e re-rodar o apply do stack hml_croquito que falhou em
    403 (passo 2 do runbook).
  - Os demais atos humanos do runbook de HML.md (secrets, entitlement, digest,
    merge/deploy, re-upload) — nenhum executado por este builder, por contrato.
```

## Desvios conscientes do contrato

1. **Colisão de ID no ROADMAP.md: F-009 já existia apontando para um item DIFERENTE
   ("Jornada guiada da revisão").** O contrato pede para atualizar "a entrada F-009"
   assumindo implicitamente que ela já descrevia a suite hospedada. Ao ler
   `docs/product/ROADMAP.md` linha 31 antes de editar, a linha `F-009` da tabela
   "Trabalho de engenharia em andamento" apontava para "Jornada guiada da revisão (a
   definir em contrato)" — uma feature de UX inteiramente diferente, nascida também
   em 2026-08-19 mas sem Feature Contract, sem diretório em `docs/features/` e sem
   nenhuma relação com providers/AWS. `docs/features/F-009-suite-hospedada-sem-aws/`
   já existe, commitado nesta branch desde `394ca06` (contrato+plano+tasks), com T1,
   T2, T3, T5 implementadas sob esse ID. Resolvi a colisão renumerando o item SEM
   Feature Contract (jornada guiada) para F-011, deixando F-009 apontar para a suite
   hospedada (o que já tinha trabalho publicado sob esse número) e abrindo F-010 para
   "revisão assistida em lote", exatamente como o contrato pedia. `scripts/
   check_docs.py` não capturava essa colisão antes da correção porque o portão de
   paridade só valida linha↔arquivo quando a célula "Contrato" tem link — a linha
   antiga não tinha (estado `READY_FOR_SPEC`, pré-especificação), então o `check_docs`
   ficava verde apontando para o item errado. Documentei a renumeração no próprio
   texto do ROADMAP (parágrafo de F-011) para quem procurar o "F-009" antigo entender
   o que aconteceu. Nenhum diretório `docs/features/F-011-*` foi criado (a feature
   segue sem Feature Contract, como estava).
2. **`docs/STATUS.md` recebeu mais texto do que uma frase de cabeçalho.** O contrato
   diz "atualizar se o marco mudou (leia o arquivo e decida; se não mudar, diga por
   quê)". Decidi que o "marco" numerado (quarto marco local) não muda, mas segui o
   precedente que o próprio arquivo já estabelece para F-006/F-007/F-008 (cada uma
   ganhou um parágrafo narrativo quando abriu ou fechou) e escrevi um parágrafo
   equivalente para F-009, para manter a vista derivada consistente com o padrão do
   documento — não deixei a atualização só no cabeçalho.
3. **ADR-0035 recebeu itens de "Riscos e mitigação" herdados dos build reports T1/T3/
   T5** (granularidade de OCR por parágrafo, erro embutido do Cloud Vision sempre
   UNAVAILABLE, TF_VAR vazio se o GH secret existir mas estiver sem valor, o 403 do
   apply). O contrato não pede explicitamente uma tabela de riscos, mas o formato do
   ADR_TEMPLATE.md (seguido pelos ADRs vizinhos, 0025/0031/0032) inclui essa seção, e
   omitir riscos já conhecidos e documentados pelos builders anteriores teria sido
   perder informação que o próprio contrato manda eu ler ("leia os build reports
   T1/T2/T3 ... antes de escrever").

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- `docs/STATUS.md` linha ~936-938 (seção de F-007) ainda declara `READY_FOR_PLANNING`
  enquanto o ROADMAP e o feature.md de F-007 já mostram `READY_FOR_HUMAN_REVIEW`
  (commits de PRs #13-#18 já mesclados na branch). Divergência preexistente, não
  causada por esta task e fora do escopo de F-009; não corrigida.
- `docs/architecture/AWS_DEPLOYMENT.md` e `docs/architecture/API_CONTRACT.md` não
  foram tocados. Nenhum dos dois contradiz a suite hospedada nova (o primeiro
  descreve o desenho de PRODUÇÃO em AWS, nunca aplicado; o segundo já documenta o
  endpoint de entitlement sem citar providers específicos), mas ambos poderiam ganhar
  uma nota cruzando para o ADR-0035 se uma revisão futura achar necessário.
- `croquito-demo extraction-eval` mantém o default `bedrock:...` do eixo de
  comparação — registrado como pendência no ADR-0035 e no MODEL_ROUTING.md, não
  corrigido (é mudança de código, fora do escopo desta task de documentação).
- Não criei `docs/features/F-010-revisao-assistida-em-lote/` nem
  `docs/features/F-011-jornada-guiada-da-revisao/`: o contrato pede apenas a entrada
  no ROADMAP ("aprovada por ato humano de 2026-08-19... especificação futura"); criar
  o diretório da feature é trabalho de especificação, não desta task de documentação.
