# Infrastructure Guardrails

Infrastructure is declared as code. Every cloud, PaaS, DNS, and SaaS resource that a Terraform provider can manage is provisioned and changed through versioned Terraform or OpenTofu configuration, reviewed like application code.

Agents must never:

- create, modify, or delete infrastructure through a provider console, web dashboard, or imperative CLI such as `aws`, `gcloud`, or `az`;
- introduce a different provisioning tool, including Pulumi, CDK, CloudFormation, or provider-native templates, without explicit human approval recorded in an ADR;
- run `apply` against a production or shared environment autonomously, or apply a plan that a human has not reviewed;
- keep infrastructure state in local files, or in a backend without remote storage, locking, and versioning;
- commit credentials, tokens, or other secrets to configuration or variable files, or expose state, plan output, or logs that contain them.

Agents must:

- present the `plan` output, including every destroy and replace, and wait for human approval before any `apply`;
- keep configuration, variables, and module versions pinned and versioned in the repository;
- treat state as sensitive data: encrypted at rest, access restricted, never committed;
- reconcile drift and import any resource that was created outside the configuration back into it.

A manual change is admissible only to bootstrap the state backend itself or to mitigate an active incident, and only with explicit human approval at the time. The resource must be imported into the configuration, and drift reduced to zero, before the task is considered complete.
