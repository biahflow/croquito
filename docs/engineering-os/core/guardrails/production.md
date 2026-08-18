# Production Guardrails

Production changes require explicit human approval.

Agents must never autonomously:

- deploy or roll back production;
- modify production secrets or access credentials;
- apply destructive infrastructure changes;
- alter IAM privileges or authentication controls;
- disable monitoring, alerts, backups, or security protections.

Agents may prepare a reviewed plan, deployment artifact, validation checklist, and rollback plan for a human operator.
