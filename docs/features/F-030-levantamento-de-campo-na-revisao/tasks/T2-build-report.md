# T2 — BUILD REPORT

Relatório do Builder para o [Task Contract T2](T2-foto-avulsa-e-leitura.md) da
[F-030](../feature.md). Executado diretamente na `main`, sem push e sem chamada paga.

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - services/api/src/croquito_api/database.py
  - services/api/src/croquito_api/migrations/versions/0017_field_evidence.py
    Confirmação humana polimórfica para fotos de survey ou avulsas, sem FK que limite a
    origem; o estado da análise continua numa cabeça única por alvo e tarefa.
  - services/api/src/croquito_api/main.py
    Presign URL-free na idempotência, confirmação por leitura/digest, pedido explícito de
    leitura, confirmação/correção append-only e composição no painel.
  - services/api/src/croquito_api/pubsub_queue.py
    Envelope `analyze_field_evidence` idêntico nos transportes Pub/Sub e SQS.
  - services/worker/src/croquito_worker/survey_photo_analysis.py
    Ids determinísticos nas leituras e artefato job-scoped sem medida/geometria.
  - services/worker/src/croquito_worker/local_queue.py
    Handler idempotente, passe offline sempre e gates de entitlement + autorização antes
    do mesmo `PromptTask.FIELD_PHOTO_READING` já contratado.
  - tests/api/test_field_evidence.py
  - tests/api/test_pubsub_queue.py
  - tests/worker/test_field_evidence_analysis.py
  - tests/worker/test_survey_photo_analysis.py
    Cobertura determinística de MIME/digest, custo zero no upload, explicit request,
    deduplicação, gates, lineage e correção append-only.
  - docs/architecture/API_CONTRACT.md
  - tests/api/openapi.snapshot.json
    Contrato e snapshot das quatro operações novas.

Validation executed:
  - pytest tests/api/test_field_evidence.py
           tests/worker/test_field_evidence_analysis.py
           tests/worker/test_survey_photo_analysis.py ................. exit 0 (34 passed)
  - make check ........................................................ exit 0
    Ruff/formatação (626 arquivos), mypy strict (253 fontes), docs, schemas/contratos,
    builds web/field e Terraform fmt.
  - make test .......................................................... PENDING_FINAL_GATE

Validation skipped:
  - Nenhuma rodada real de provider: explicitamente proibida nesta task.

Unavailable capabilities: none

Assumptions:
  - A confirmação humana normaliza o valor final para milímetros no corpo; o texto lido
    permanece ao lado para auditoria e pode ser corrigido pelo profissional.
  - Replays da solicitação podem republicar a mensagem enquanto a cabeça está QUEUED;
    o worker deduplica por estado antes de tocar o provider.

Remaining risks:
  - Classificação visual usa a mesma tabela de estado, mas contrato e handler pertencem à T6.

Human decisions required: none
```
