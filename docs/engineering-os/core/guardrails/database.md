# Database Guardrails

Agents must never:

- modify a migration that has already been applied outside the local development environment;
- apply a destructive migration, including dropping tables or removing columns, without explicit human approval;
- disable constraints or isolation controls to make tests pass;
- introduce a database technology without an ADR.

Agents must:

- use forward-only migrations and describe rollback or recovery considerations;
- preserve tenant isolation and data integrity;
- assess indexes and query cost for new access patterns;
- use representative, non-production data for development and tests.
