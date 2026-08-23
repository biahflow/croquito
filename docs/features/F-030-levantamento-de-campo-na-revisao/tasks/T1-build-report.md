# T1 — BUILD REPORT

Relatório do Builder para o [Task Contract T1](T1-vinculo-e-evidencia.md) da
[F-030](../feature.md). Executado diretamente na `main`, com publicação adiada até o gate
consolidado da feature.

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - services/api/src/croquito_api/database.py
    Vínculo muitos-para-muitos, foto avulsa, estado comum de análises, confirmações
    humanas append-only e campos versionados da revisão.
  - services/api/src/croquito_api/migrations/versions/0017_field_evidence.py
    Migration aditiva e forward-only, com defaults de servidor para deploy rolante.
  - services/api/src/croquito_api/main.py
    Listagem paginada dos levantamentos concluídos, vínculo/desvínculo idempotentes e
    leitura unificada da evidência com URL temporária criada apenas na resposta.
  - tests/api/test_field_evidence.py
    Cobertura de tenant, papel, concorrência, idempotência, âncoras, medidas e saneamento.
  - tests/api/test_migrations.py
    Relação explícita das tabelas criadas depois da baseline.
  - tests/api/openapi.snapshot.json
    Snapshot regenerado para a superfície pública da task.
  - docs/architecture/API_CONTRACT.md
    Contrato das quatro operações públicas da task.

Validation executed:
  - ruff check (arquivos da task) .......................... exit 0
  - pytest tests/api/test_field_evidence.py ................ exit 0 (5 passed)
  - pytest tests/api/test_migrations.py .................... exit 0 (1 passed, 10 skipped;
    casos PostgreSQL entram no gate posterior com banco efêmero)
  - make check ............................................. exit 0
    Ruff e formatação (625 arquivos); mypy strict (252 fontes); docs (395 Markdown);
    schemas/contratos; builds web (78 módulos) e field (86 módulos); Terraform fmt.
  - make test .............................................. exit 0
    Pytest: 2383 passed, 13 skipped; web: 43 arquivos/1075 testes; field:
    24 arquivos/261 testes.

Validation skipped: nenhum gate da task; PostgreSQL será executado no gate consolidado.

Unavailable capabilities: none

Assumptions:
  - JobRecord.version é o contador otimista único da coleção de evidências de campo. O
    contador já existia e não tinha outro writer no produto.
  - O estado de análise usa uma tabela polimórfica controlada por origin/evidence_id para
    atender igualmente fotos do survey e fotos avulsas, sem duas fontes de verdade.

Remaining risks:
  - Os handlers que transitam os estados de análise pertencem às tasks T2 e T6.

Human decisions required: none
```
