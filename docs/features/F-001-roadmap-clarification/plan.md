# FEATURE EXECUTION PLAN — F-001

feature_id: F-001  
goal: Clarify the canonical roadmap through a frozen bullet-level, evidence-backed
classification and reconcile AWS, GCP, and local environments without inferring remote
state.  
assumptions: The approved Feature Contract is authoritative; `docs/product/ROADMAP.md`
remains canonical; `docs/STATUS.md` remains derived.  
risks: A documented deployment path may be mistaken for a live environment; baseline
worktree changes may be confused with F-001; a classification may exceed its evidence.

## Tasks

### F001-T01

- role: builder
- goal: Establish the execution baseline and persist the approved F-001 contract and plan.
- scope: Before editing, run `git status --short --branch` and record the baseline in the
  Builder Report. Then create `feature.md` and `plan.md` in this directory.
- out_of_scope: Task Contracts, `evidence.md`, code, infrastructure, ADRs, Git mutation
  beyond approved feature files, and remote state.
- expected_areas: `docs/features/F-001-roadmap-clarification/`
- acceptance_criteria: The baseline identifies all preexisting worktree changes before
  F-001; `feature.md` preserves the approved contract and records `IN_PROGRESS`; this
  `plan.md` exists only after human plan approval; neither Task Contracts nor
  `evidence.md` exists.
- depends_on: []
- validation: Confirm both artifacts resolve from the repository; defer `make check` to
  F001-T03.
- required_capabilities: READ, WRITE, VALIDATE
- risk: The approved contract or plan could be altered beyond the allowed lifecycle
  transition.
- relative_effort: S

### F001-T02

- role: builder
- goal: Add the frozen roadmap inventory and environment reconciliation to the canonical
  roadmap.
- scope: Modify only `docs/product/ROADMAP.md`; add the F-001 discovery entry with stable
  ID, HIGH priority, `IN_PROGRESS` lifecycle, and `feature.md` reference; classify only
  the frozen inventory below.
- out_of_scope: Classifying the new F-001 entry, altering `STATUS.md`, code, Terraform,
  deploy workflow, ADRs, infrastructure, remote-state checks, or unsupported
  classifications.
- expected_areas: `docs/product/ROADMAP.md`
- acceptance_criteria: The table has exactly one row for each frozen inventory item, with
  item, classification, evidence, and observation; insufficient evidence is `UNKNOWN`;
  observations distinguish versioned configuration, documentary assertion, and unverified
  remote state.
- depends_on: [F001-T01]
- validation: Compare table keys with the frozen inventory; verify relative links; defer
  `make check` to F001-T03.
- required_capabilities: READ, WRITE, VALIDATE
- risk: The canonical roadmap may present configured GCP deployment as verified current
  operation.
- relative_effort: M

### F001-T03

- role: builder
- goal: Validate the integrated documentation change and report unresolved evidence gaps.
- scope: Run `make check`; correct only documentation defects introduced by F001-T01 or
  F001-T02.
- out_of_scope: Reclassification without evidence, Task Contracts, `evidence.md`,
  unrelated tests/evals, code, infrastructure, ADRs, Git operations, and remote checks.
- expected_areas: F-001 feature artifacts and `docs/product/ROADMAP.md`
- acceptance_criteria: `make check` passes; feature and plan links resolve; the inventory
  contains no F-001 row; any preexisting failure is distinguished from a failure
  introduced by F-001.
- depends_on: [F001-T02]
- validation: `make check`
- required_capabilities: READ, WRITE, VALIDATE
- risk: A preexisting documentation failure could be misattributed to F-001.
- relative_effort: XS

### F001-T04 (round R1)

- role: builder
- goal: Correct the frozen inventory and the canonical roadmap after review round R0, and
  persist the feature evidence package.
- scope: Reproduce the 34 frozen bullets verbatim, including every qualifier and the exact
  section title; define the classification vocabulary in the roadmap; split the environment
  reconciliation into versioned configuration, documentary assertion, and verified remote
  state; create `evidence.md`. Only `docs/product/ROADMAP.md`, `feature.md`, `plan.md`, and
  the new `evidence.md` may change.
- out_of_scope: Reclassifying any item by agent preference, editing `docs/STATUS.md`, ADRs,
  code, infrastructure, workflows, remote-state verification, and creating a commit.
- expected_areas: `docs/product/ROADMAP.md`, `docs/features/F-001-roadmap-clarification/`
- acceptance_criteria: The 34 keys are verbatim and appear exactly once; the classification
  distribution is unchanged from R0; the vocabulary is defined and checked against all 34
  rows without altering any classification; the reconciliation states the three axes for
  AWS, GCP, and local; `evidence.md` preserves `BASELINE → CHANGE → FINAL`, the R0 review,
  and the human authorization that expanded scope.
- depends_on: [F001-T03]
- validation: `make check`; automated comparison of the 34 bullets against
  `git show HEAD:docs/product/ROADMAP.md`.
- required_capabilities: READ, WRITE, VALIDATE
- risk: A verbatim correction could be used to silently reclassify an item.
- relative_effort: M

## Frozen inventory

Os 34 bullets abaixo são reproduzidos **verbatim** de
`git show HEAD:docs/product/ROADMAP.md` (commit `a92fda7`), cada um precedido do título
exato da seção em que vive. Quebras de linha do original foram colapsadas em espaço e
links relativos foram reancorados ao diretório deste arquivo; nenhuma outra alteração de
texto foi feita. A rodada R0 truncou qualificadores de vários bullets — a correção e seu
efeito nas classificações estão registrados em [evidence.md](evidence.md).

1. Agora — MVP privado / Golden dataset e eval harness.
2. Agora — MVP privado / Upload, processamento, revisão e DXF.
3. Agora — MVP privado / Guaxindiba, Toca e Raul Campelo.
4. Agora — MVP privado / Dois provedores, Textract e scene graph.
5. Agora — MVP privado / AWS gerenciada, retenção e observabilidade.
6. Próximo — generalização controlada / Ampliar regressão com documentos autorizados.
7. Próximo — generalização controlada / Biblioteca versionada de símbolos e blocos.
8. Próximo — generalização controlada / Melhor associação automática entre cotas e segmentos.
9. Próximo — generalização controlada / Curvas e polígonos com constraints adicionais.
10. Próximo — generalização controlada / Projetos persistentes com política contratual de retenção.
11. Próximo — generalização controlada / Métricas de qualidade por categoria de croqui.
12. Agora — medição de obra (contexto valuation, v1 em marcos) / **Obra licitada (medição)**: o contrato manda. O preço SCO é composto (mão de obra e insumos dentro do código de serviço). A relação entre elemento da prancha e código de serviço é N:N ([ADR-0053](../../adr/0053-cardinalidade-n-n-elemento-servico.md), aceito em 2026-08-25): um mesmo elemento pode disparar vários códigos e um mesmo código recebe parcelas de vários elementos, cada par com sua parcela de quantidade — não é escolher execução em vez de mero fornecimento, é um **pacote de serviços**, que a UI deve tornar visível. No arquivo real da Toca, `17.23` = `PJ14100500(/)` ("Tela… **Fornecimento** e colocação") e `17.25` = `PJ14150203(A)` ("**Alambrado**… estrutura tubular") entram **os dois** sobre a mesma área de 783,86 m², ligados por `=F686`, somando 62% do orçamento. Item que não está na lista SCO/contrato **não pode** vir de outra tabela: o caminho é **aditivo de contrato** (RE-RA) solicitando a inclusão — o sistema deve detectar esses itens e produzir o **dossiê do aditivo** (item, quantitativo, justificativa), nunca precificar por fora. Criação/gestão de RE-RA segue no item abaixo.
13. Agora — medição de obra (contexto valuation, v1 em marcos) / **Pré-licitação (orçamento-base)**: aí sim vale a cadeia **SCO → EMOP → composição manual**. Importador da tabela EMOP como segundo catálogo com proveniência (`PriceCatalogEntry.origin` vira dado; catálogo digital oficial é **pago** via GRE, em .DBF, com sincronização mensal possível por rotina — nova versão com data-base própria, nunca troca silenciosa de preço), e composição com coeficientes declarados (item → várias linhas: horas, insumos). É o coração do "gerador de orçamento" da fase 1 da visão de produto.
14. Agora — medição de obra (contexto valuation, v1 em marcos) / **M6 — UI web de homologação da medição** (priorizado pelo usuário em 2026-08-13): revisão do takeoff, shortlist com descrição completa do catálogo, confirmação de código e boletim — o ato humano da orçamentista numa tela, não no CLI. Destrava a homologação da cadeia existente; a rodada real da Toca está estacionada no elo da confirmação até este marco.
15. Agora — medição de obra (contexto valuation, v1 em marcos) / **M7 — matcher híbrido de código SCO** (priorizado pelo usuário em 2026-08-13, durante a homologação: "não posso correr o risco de o código ter no SCO e não fazer o match"): léxico com radical conservador + sinônimos de domínio como dado, retrieval semântico por embeddings do catálogo (dado público SCO; índice local por digest) com fusão de ranking, e a garantia virando gate de eval — golden set com `recall@20 = 100%`. Candidatos sempre com origem e score declarados; confirmar segue ato humano; sem chave/teto, o léxico permanece como fallback funcional declarado.
16. Agora — medição de obra (contexto valuation, v1 em marcos) / **M8 — fronteira licitada × pré-licitação** (entregue em código em 2026-08-17, [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md)): dossiê do aditivo como artefato de fechamento da rodada licitada (VAL-08); `PriceOrigin` + importador EMOP offline (.DBF com layout como dado; o arquivo real depende da assinatura GRE) + guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN`; composição manual compilada a catálogo e orçamento-base (`build-estimate`) com cascata declarada e proveniência por linha (VAL-09). A UI do orçamento-base e o `.xlsx` no modelo da prefeitura ficam para marco futuro, quando houver exemplar real como template.
17. Próximo — medição além do v1 / Modo teto / orçamento invertido ("escopo dentro de R$ X" da relação de demanda); porta: `EstimateTarget` reservado no glossário do contexto.
18. Próximo — medição além do v1 / Composição própria como caminho de escrita para item sem preço de referência; porta: `PriceCatalogEntry.origin`.
19. Próximo — medição além do v1 / Quantitativo automático derivado do scene graph aprovado; porta: `TakeoffItem.source` discriminado + `QuantitySource` lendo o `quantitativos.csv` do export DXF. Depende de identidade estruturada de elemento nas entidades (hoje rótulo é texto livre).
20. Próximo — medição além do v1 / Criação e gestão de re-ratificações (RE-RA); no v1 elas são apenas lidas para o cálculo de saldo.
21. Próximo — medição além do v1 / Reajuste de preços entre medições (data-base móvel).
22. Próximo — medição além do v1 / UI web de revisão da medição (v1 é CLI-first, como o resto do produto).
23. Próximo — medição além do v1 / Múltiplas pranchas por praça na extração de legenda.
24. Próximo — medição além do v1 / Cascata configurável de fontes de preço além do SCO (SINAPI, SICRO, tabelas estaduais), cada fonte com importador próprio — tabela de preços é dado, não código.
25. Depois — produto comercial ampliado / DWG após decisão de licenciamento.
26. Depois — produto comercial ampliado / Comparação de versões V1/V2.
27. Depois — produto comercial ampliado / Templates de layers por cliente.
28. Depois — produto comercial ampliado / Multi-page alignment com referências explícitas.
29. Depois — produto comercial ampliado / Integrações CAD e gestão de projetos.
30. Depois — produto comercial ampliado / Modelos especializados somente após dataset licenciado e evals robustas.
31. Não planejado sem nova decisão / Promessa de conversão universal sem revisão.
32. Não planejado sem nova decisão / Inferência automática de dimensões inexistentes.
33. Não planejado sem nova decisão / Substituição de responsabilidade técnica do engenheiro.
34. Não planejado sem nova decisão / BIM/IFC ou modelagem 3D.

critical_path: F001-T01 (S) → F001-T02 (M) → F001-T03 (XS) → F001-T04 (M, round R1).  
integration_strategy: The outputs are `feature.md`, `plan.md`, `evidence.md`, and the
canonical roadmap update. No Task Contracts are created. `evidence.md` was out of scope in
R0 and entered scope in R1 by explicit human authorization.  
human_gates: Plan approval transitions F-001 to `READY_FOR_BUILD`; starting F001-T01
transitions it to `IN_PROGRESS`. Human approval remains required for the resulting
inventory and environment reconciliation; no remote verification, deployment, or ADR
decision is authorized. On 2026-08-17 the human authorized correction round R1 over four
files, explicitly expanding scope to include `evidence.md`, declared the R0 execution
evidence unrecoverable, and prohibited a commit. F-001 remains `IN_PROGRESS`.  
planning_findings: Repository evidence distinguishes AWS production target, GCP HML
configuration/documentation, and the local environment; it does not independently verify
current remote service state. R0 showed that truncating a bullet changes the scope being
classified: the frozen inventory is only sound when reproduced verbatim.
