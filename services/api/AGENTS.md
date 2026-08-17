# Instruções para agentes — API

Estas regras estendem o [AGENTS.md](../../AGENTS.md). Leia
[Domain Model](../../docs/architecture/DOMAIN_MODEL.md),
[API Contract](../../docs/architecture/API_CONTRACT.md) e
[Threat Model](../../docs/security/THREAT_MODEL.md).

## Boundary

A API autentica, autoriza, valida comandos e coordena lifecycle. Não renderiza PDF,
chama modelos nem gera DXF no request path.

## Regras

- FastAPI/Pydantic nos boundaries; domínio sem dependência de HTTP.
- Toda query tenant-scoped deriva tenant do JWT, nunca do body.
- Mutação externa aceita idempotency key.
- Revisions usam optimistic concurrency e operations allowlist.
- Upload/download somente por URLs assinadas após ownership check.
- Erros usam codes estáveis e `application/problem+json`.
- Não retornar provider raw responses.
- StartExecution persiste intent/IDs antes de responder.
- Não manter transação de banco durante chamada AWS externa longa.
- Migrations são revisões Alembic em `src/croquito_api/migrations/versions/`, aplicadas por
  `croquito_api.bootstrap` ([ADR-0029](../../docs/adr/0029-runner-de-migrations-revisadas.md)).
  São forward-only: `downgrade` não existe em ambiente hospedado.
- Mudou modelo em `database.py`? Gere a revisão (`make db-revision MESSAGE=...`) e revise o
  arquivo gerado. O CI compara migrations com `Base.metadata` e reprova divergência.
- Migrations seguem expand/contract quando houver rolling deploy; remover coluna é trabalho
  posterior ao que parou de usá-la e exige aprovação humana explícita.
- `Database.create_schema()` só cria schema do zero (teste e banco novo); não use para
  evoluir banco existente.

## Testes mínimos

- Cross-tenant/IDOR negativos.
- JWT inválido/expirado.
- Idempotência e revision conflict.
- Job state transitions.
- Presign ownership/expiry.
- Delete/retry behavior.
- OpenAPI compatibility.

