# F-032 — Execution Plan (fatia de sincronização ampliada)

Terceiro plano da feature, autorizado pelo usuário em 2026-08-21 (sessão de
planejamento com decisões registradas no [feature.md](feature.md)): transporte real
(`/v1/surveys` + mídia por presign + conflito, prancha 6), login OIDC, export do
pacote para o motor, e o escopo reaberto — voz (áudio offline + transcrição no sync),
IA/CV sobre fotos (propostas CV, leitura por provider, qualidade no aparelho) e iOS
na matriz do piloto.

Decisão de arquitetura desta fatia (fecha a incógnita do Feature Contract): o pacote
é um contrato **novo**, `SurveyPacket`, Pydantic em
`packages/core/src/croquito_core/field.py`, gerado pelo pipeline `make contracts` —
cumprindo a mitigação do ADR-0043 ("contrato gerado pelo pipeline `make contracts`
na fatia de sincronização"). Backend por extensão da `croquito_api` (ADR-0043 D4):
nenhum serviço novo, mídia por presign, processamento assíncrono na fila existente.

```text
FEATURE EXECUTION PLAN

feature_id: F-032
goal: Ligar o app de campo ao backend: outbox sincronizado por operações idempotentes
  contra /v1/surveys, mídia (foto e áudio) por presign com digest, conflito
  campo×escritório com decisão explícita (prancha 6b), login OIDC com tolerância a
  expiração offline (6c), export do levantamento como observações no pipeline, e as
  frentes de IA: transcrição de áudio, propostas CV e leitura por provider sobre
  fotos, e checagem de qualidade de foto no aparelho.
assumptions: baseline verde na branch f-032-app-levantamento-campo (registrada em
  evidence-sync.md antes de T7); a 0007 da F-029 existe só como trabalho não
  commitado na main — a migração desta fatia nasce como próxima da branch (0007 sobre
  0006) e a relinearização com a F-029 é etapa explícita de integração
  (PLAN_DEVIATION prevista, como na rodada F-025); DAP rev.1 cobre a prancha 6
  (sync/conflito/login) mas NÃO cobre voz, aviso de qualidade nem estado de
  transcrição — essas superfícies aguardam DAP rev.2; providers reais permanecem
  desligados por padrão e nenhum teste faz chamada paga.
risks: main.py é um arquivo de ~8800 linhas vivo em outras frentes — tarefas de API
  sequenciadas, nunca em paralelo entre si; T11/T13/T14 tocam o dispatch do worker
  (local_queue.py) — sequenciadas por PARALLELISM_RISK declarado; codec de áudio
  divergente Android×iOS (webm/opus × mp4/aac) tratado no contrato (mime real
  registrado) e no worker (aceita ambos); fornecedor de speech-to-text é gate humano
  aberto — T13 só inicia depois dele.

tasks:
  - id: T7
    role: builder
    goal: Contrato SurveyPacket (croquito_core/field.py + make contracts) e módulo
      único de mapeamento domínio↔contrato em apps/field
      (tasks/T7-contrato-survey-packet.md)
    scope: packages/core/src/croquito_core/field.py (novo), schema_export (registro
      do modelo novo), packages/contracts/** (gerados), apps/field/src/sync/contract.ts
      (novo, mapeamento), testes correspondentes
    out_of_scope: rotas, transporte, UI, worker, migração
    acceptance_criteria: ver Task Contract T7
    depends_on: []
    validation: make contracts; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis; COMMIT forbidden
    risk: contrato divergir do domínio do app (mm inteiros, âncoras por sha256)
    relative_effort: M
  - id: T8
    role: builder
    goal: Tabelas + migração aditiva + rotas /v1/surveys (operations em lote
      idempotente, GET estado, media/presign, media/confirm, complete, conflito
      SURVEY_CONFLICT) exigindo field_technician
      (tasks/T8-backend-v1-surveys.md)
    scope: services/api/src/croquito_api/{main.py,database.py}, migração nova,
      pubsub_queue.py (enqueue novos), tests/api/**, snapshot OpenAPI
    out_of_scope: worker/handlers, apps/field, providers
    acceptance_criteria: ver Task Contract T8
    depends_on: [T7]
    validation: uv run pytest tests/api; make openapi-snapshot; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis; COMMIT forbidden
    risk: quebrar rotas existentes de main.py; migração fora do padrão expand/contract
    relative_effort: L
  - id: T9
    role: builder
    goal: SyncEngine no app (lotes em ordem seq, backoff, ack, mídia por categoria com
      progresso, painel prancha 6a/6b real, transação Dexie saveSurvey+appendOperation)
    scope: apps/field/src/sync/** (novo), src/outbox/** (integração), src/storage/**
      (transação), src/ui/** (painel), AGENTS.md do field (autorização de rede em sync/)
    out_of_scope: login (T10), voz (T12), backend
    acceptance_criteria: contrato derivado ao iniciar a onda
    depends_on: [T7, T8]
    validation: npm run field:test; npm run field:check; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis; COMMIT forbidden
    risk: apagar/regravar dado local antes do ack; violar 6a (mídia antes de metadados)
    relative_effort: L
  - id: T10
    role: builder
    goal: Login OIDC no app (papel field_technician, padrão apps/web/src/auth.ts,
      tolerância a expiração offline — coleta continua, reautenticação só ao enviar, 6c)
    scope: apps/field/src/auth/** (novo), src/ui/** (integração mínima), env do app
    out_of_scope: realm Keycloak (ato humano), SyncEngine
    acceptance_criteria: contrato derivado ao iniciar a onda
    depends_on: [T7]
    validation: npm run field:test; npm run field:check; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis; COMMIT forbidden
    risk: bloquear coleta offline por token expirado (violaria 6c)
    relative_effort: M
  - id: T11
    role: builder
    goal: Handler survey-export no worker — SurveyPacket consolidado vira observações
      (approximate/unresolved com Provenance, mm→m em Decimal), sujeito aos portões
      do scene graph; nada vira exact
    scope: services/worker/src/croquito_worker/{local_queue.py (dispatch),
      survey_export.py (novo)}, tests/worker/**
    out_of_scope: transcrição, CV, API
    acceptance_criteria: contrato derivado ao iniciar a onda
    depends_on: [T8]
    validation: uv run pytest tests/worker; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis; COMMIT forbidden
    risk: criar geometria exata a partir do levantamento; contornar export_errors()
    relative_effort: L
  - id: T12
    role: builder
    goal: Voz no app — gravação MediaRecorder offline, codecs Android/iOS, âncora como
      ObservationNote com local_media_ref de áudio, sync como mídia
    scope: apps/field/src/voice/** (novo), src/domain/types.ts (nota com áudio),
      src/photos|storage (mídia de áudio), src/ui/** (superfície da DAP rev.2)
    out_of_scope: transcrição (worker), providers
    acceptance_criteria: contrato derivado ao iniciar a onda
    depends_on: [T7, T9]
    validation: npm run field:test; npm run field:check; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis; COMMIT forbidden
    risk: iniciar sem DAP rev.2 aprovada (gate humano); codec incompatível no iOS
    relative_effort: M
  - id: T13
    role: builder
    goal: Transcrição no worker (command survey-transcribe) — provider de
      speech-to-text atrás de entitlement/budget/lineage; texto vira rascunho ligado
      à nota de áudio, nunca auto-confirmado
    scope: services/worker/src/croquito_worker/{providers.py (adapter novo),
      local_queue.py (dispatch), survey_transcribe.py (novo)}, tests/worker/**,
      docs/ai/MODEL_ROUTING.md, docs/security/AI_VENDOR_RISK.md
    out_of_scope: UI, export, CV
    acceptance_criteria: contrato derivado ao iniciar a onda
    depends_on: [T8, T12]
    validation: uv run pytest tests/worker; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis; COMMIT forbidden
    risk: iniciar sem o gate humano do fornecedor; teste que chama serviço pago
    relative_effort: M
  - id: T14
    role: builder
    goal: IA/CV pós-sync sobre fotos (command survey-photo-analysis) — caminho CV
      offline gera candidatos unresolved/export=false; leitura por provider de visão
      existente extrai texto/medidas visíveis como leituras a revisar, com lineage
    scope: services/worker/src/croquito_worker/{survey_photo_analysis.py (novo),
      local_queue.py (dispatch), providers.py (reuso)}, tests/worker/**
    out_of_scope: UI, treinamento de modelo, F-030 (fotos na revisão do escritório)
    acceptance_criteria: contrato derivado ao iniciar a onda
    depends_on: [T8, T11]
    validation: uv run pytest tests/worker; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis; COMMIT forbidden
    risk: candidato virar geometria sem revisão; chamada paga sem entitlement
    relative_effort: L
  - id: T15
    role: builder
    goal: Checagem de qualidade de foto no aparelho (photos/quality.ts — nitidez por
      variância de Laplaciano, exposição por histograma; aviso não bloqueante)
    scope: apps/field/src/photos/quality.ts (novo) + testes, src/ui/** (aviso da DAP rev.2)
    out_of_scope: providers, rede, desfoque/edição de foto
    acceptance_criteria: contrato derivado ao iniciar a onda
    depends_on: [T7]
    validation: npm run field:test; npm run field:check; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis; COMMIT forbidden
    risk: iniciar a parte de UI sem DAP rev.2; falso positivo bloquear o técnico
    relative_effort: S
  - id: T16
    role: builder
    goal: e2e in-process com fakes — coleta offline → sync (ops+fotos+áudio) →
      conflito resolvido → complete → worker (export+transcrição fake+CV) →
      observações nos portões; evidence-sync.md consolidado
    scope: tests/e2e/**, tests/fakes.py (extensões), docs/features/F-032-.../evidence-sync.md
    out_of_scope: chamadas pagas reais, aparelho real
    acceptance_criteria: contrato derivado ao iniciar a onda
    depends_on: [T9, T10, T11, T12, T13, T14, T15]
    validation: uv run pytest tests/e2e; make check; make test
    required_capabilities: READ repo; WRITE escopo acima; VALIDATE perfis; COMMIT forbidden
    risk: e2e que passa sem exercer o portão de export
    relative_effort: M

parallel_groups: [T8, T10] após T7 (áreas disjuntas: services/api × apps/field);
  [T9, T11] após T8 (apps/field × worker); [T12, T15] quando DAP rev.2 aprovada;
  worker sempre sequencial entre si (T11 → T13/T14) por toque comum em local_queue.py
critical_path: T7 → T8 → T9 → T12 → T13 → T16 (contrato → rotas → transporte → voz →
  transcrição → e2e; T8 e T9 são os maiores esforços do caminho)
integration_strategy: ondas na mesma branch f-032-app-levantamento-campo — onda 1 = T7;
  onda 2 = T8+T10; onda 3 = T9+T11; onda 4 = T12+T15 (pós DAP rev.2) e T13+T14
  (T13 pós gate do fornecedor); onda 5 = T16. Revisão linha a linha e commit pelo
  modelo principal ao fim de cada tarefa; portões completos por onda; relinearização
  da migração com a 0007 da F-029 registrada como PLAN_DEVIATION na integração com a
  main.
human_gates: DAP rev.2 (voz, aviso de qualidade, estado de transcrição) antes de
  T12/T15; papel field_technician + path do app no realm Keycloak (teste real);
  fornecedor de speech-to-text (envio de áudio de cliente a serviço externo) antes de
  T13; chamadas pagas em massa por rodada; decisão de merge/push da branch
  (inalterada, segue segurada).
planning_findings: ARCHITECTURE_DECISION_REQUIRED não — ADR-0043 cobre a fatia
  (D2/D3/D4); a decisão do formato do pacote (SurveyPacket novo) está registrada
  neste plano e no Feature Contract; DESIGN_APPROVAL_REQUIRED registrado para as
  superfícies de voz/qualidade/transcrição (DAP rev.2); PARALLELISM_RISK registrado
  para main.py (tarefas de API nunca em paralelo entre si) e local_queue.py
  (worker sequencial); vínculo survey↔project/job no export é decisão do spec de T11
  com escalada ao usuário se virar decisão de arquitetura.
```

## Validação do plano

`PLAN_VALID` — 2026-08-21. IDs únicos (T7–T16, sequência da feature), dependências
existentes, DAG acíclico (T7 → {T8,T10,T15} → {T9,T11} → {T12} → {T13,T14} → T16),
critérios e validação com comandos reais do projeto, escopo bounded em arquivos,
paralelismo sem sobreposição de arquivos (grupos declarados; worker e main.py
explicitamente sequenciais), critical path com rationale de esforço, gates humanos
nomeados; nenhum requisito dos itens 7–10 do Feature Contract sem dono.

## PLAN_DEVIATION

(nenhum até o momento; a relinearização da migração 0007×F-029 será registrada aqui
quando a integração com a main acontecer)
