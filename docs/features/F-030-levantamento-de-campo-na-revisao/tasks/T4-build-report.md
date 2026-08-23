# T4 — BUILD REPORT

Relatório do Builder para o [Task Contract T4](T4-testemunhas-no-servidor.md) da
[F-030](../feature.md). Executado diretamente na `main`, sem push.

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - services/api/src/croquito_api/main.py
    Contratos, resolução server-side das duas fontes, diferença neutra, associação/
    retração versionada e exposição no ReviewResponse.
  - services/worker/src/croquito_worker/review_store.py
  - services/worker/src/croquito_worker/review_refresh.py
  - services/worker/src/croquito_worker/local_queue.py
    Todos os writers de revisão carregam testemunhas e observações verbatim; um ato
    posterior nunca apaga contexto de campo por usar default.
  - tests/api/test_review_field_witnesses.py
    Múltiplas fontes, draft recusado, número do cliente proibido, replay, retração e
    invariância de cena/blockers/pacote.
  - docs/architecture/API_CONTRACT.md
  - tests/api/openapi.snapshot.json
    Contrato e snapshot da rota e do campo de resposta.

Validation executed:
  - pytest tests/api/test_review_field_witnesses.py
           tests/worker/test_review_refresh.py
           tests/worker/test_local_queue.py ........................... exit 0 (40 passed)
  - make check ........................................................ exit 0
    Ruff/formatação (628 arquivos), mypy strict (254 fontes), docs, contratos,
    builds web/field e Terraform fmt.
  - make test .......................................................... PENDING_FINAL_GATE

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - `value_si` da leitura em metros é convertido para milímetros; leitura originalmente
    em milímetros permanece no mesmo valor, preservando Decimal exato.
  - A lista da cabeça contém testemunhas ativas. A retraída permanece recuperável na
    revisão-pai imutável, sem estado duplicado no item corrente.

Remaining risks:
  - Nenhuma tolerância foi criada. Classificar a diferença exige calibração futura e está
    explicitamente fora desta task.

Human decisions required: none
```
