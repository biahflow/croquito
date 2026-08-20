# F-021 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-021
goal: leitura que o pipeline reconhece como recado (kind="note" do provider ou
      padrão h= no texto) chega à decisão com "Anotação da folha" pré-selecionada
      e frase explicando por quê, sem remover o portão humano
assumptions:
  - ReviewPacket NÃO entra no manifesto de contratos gerados (verificado:
    contracts.manifest.json só lista SceneRevision e valuation; a serialização é o
    Pydantic da rota GET /v1/jobs/{id}/review) — sem make contracts
  - tipos do web em apps/web/src/api.ts são escritos à mão; ReviewReading.kind é
    string solta, campo novo opcional não quebra nada
  - leitura kind="note" sem normalized_value é descartada HOJE como
    READING_{n}_INCOMPLETE antes de chegar ao kind (provider_review.py:562) — a
    mudança só alcança note completo (valor + target_hint)
risks:
  - colisão de vocabulário: apps/web/src/capture.ts já tem kind:"note" (conceito do
    traçado); o campo novo chama annotation_suggested justamente para não colidir
  - CroquiApp.tsx é arquivo grande vivo COM mudanças não commitadas na árvore
    (conserto da etapa 2 desta sessão) — preservar, nunca reverter
  - efeito de pré-preenchimento do chat (declarado depois do reset de leitura de
    propósito) tem precedência documentada; a sugestão não pode vencê-lo

tasks:
  - id: T1
    role: builder
    goal: worker deixa de descartar note completo; campo annotation_suggested no
          DimensionReading; nota de segurança própria para note sem valor
    scope: services/worker/src/croquito_worker/review.py,
           services/worker/src/croquito_worker/provider_review.py,
           tests/worker/test_providers.py, docs/ai/PROMPT_CONTRACTS.md
    out_of_scope: transcription.py (caminho paralelo permanece como está),
                  count/unknown (continuam descartados), web, prompts
    expected_areas: services/worker, tests, docs/ai
    acceptance_criteria: ver tasks/T1-worker-note.md
    depends_on: []
    validation: make check + make test
    required_capabilities: READ, WRITE, VALIDATE
    risk: laço de leituras de provider_review.py é lógica de domínio sensível
    relative_effort: S
  - id: T2
    role: builder
    goal: decisão nasce com ANNOTATION_OPTION pré-selecionada quando
          annotation_suggested=true (sinal do modelo) ou padrão h= (client-side),
          com frase visível e precedências respeitadas
    scope: apps/web/src/api.ts, apps/web/src/labels.ts, apps/web/src/CroquiApp.tsx,
           apps/web/src/labels.test.ts, docs/architecture/API_CONTRACT.md
    out_of_scope: etapa de traçado, capture.ts, chat.ts, backend
    expected_areas: apps/web, docs/architecture
    acceptance_criteria: ver tasks/T2-web-sugestao.md
    depends_on: []
    validation: make check + npm --workspace @croquito/web run test
    required_capabilities: READ, WRITE, VALIDATE
    risk: arquivo grande vivo com mudanças não commitadas; precedência de efeitos
    relative_effort: M

parallel_groups: [[T1, T2]]
critical_path: T2 (integração no arquivo vivo é o maior esforço; T1 é fechado com
               oráculo de teste claro)
integration_strategy: T1 e T2 não compartilham arquivo nenhum; o contrato entre
                      eles é o campo annotation_suggested (nome e semântica fixados
                      NESTE plano, não negociados entre tasks). Integração final é
                      make check + make test na árvore com os dois diffs.
human_gates: aprovação deste plano antes do build (concedida em 2026-08-20, na
             sessão da seleção); nenhum gate de produção
planning_findings: nenhum ARCHITECTURE_DECISION_REQUIRED; PARALLELISM_RISK ausente
                   (conjuntos de arquivos disjuntos)
```
