# AI FinOps and Minimum Sufficient Context

## Purpose

Model tokens are an engineering resource and cost center. EngineeringOS treats context selection, model usage, and repeated document reads as FinOps concerns rather than incidental prompt design.

> Context is a cost center. Retrieve only what the current role needs.

> Never spend tokens where deterministic code is sufficient.

## Principle: minimum sufficient context

Every agent or harness role SHOULD receive the smallest context set that allows it to perform safely and satisfy its contract.

More context is not automatically better. Redundant context can increase token cost, latency, distraction, conflicting interpretation, repeated reads and stale-context risk.

The goal is minimum sufficient context, not minimum context at any cost.

## Role-specific context budgets

### Planner

Typical context:

- GitHub Issue / Task Contract;
- relevant roadmap or implementation-plan slice;
- applicable ADRs/NFRs/FDDs;
- relevant architecture boundaries;
- repository/project instructions.

Avoid unrelated milestones/history/all-ADR reads by default.

### Builder

Typical context:

- approved Execution Plan;
- Issue / acceptance criteria;
- explicitly relevant ADRs/NFRs;
- affected code/tests;
- project/harness instructions.

During CI repair, add only the failed workflow/job/step evidence and bounded relevant log section needed to diagnose the in-scope defect. Do not resend the entire prior project context or full CI log by default.

### Reviewer

Prioritize:

- Issue and acceptance criteria;
- exact diff/revision;
- local validation and required CI evidence;
- applicable ADRs/NFRs;
- approved plan/design evidence when useful.

A Reviewer should not need full project history for a bounded change.

## Explicit references over discovery

Task Contracts SHOULD explicitly reference the documents that constrain work. Broad discovery remains available for ambiguity but MUST NOT be the default.

## Document duplication is token waste

Projects SHOULD avoid multiple files repeating the same state.

Preferred pattern:

```text
roadmap.md → macro direction
Pulse      → business/operational state
GitHub     → engineering state/evidence
One        → client-facing acceptance
```

Machine summaries should derive from authoritative systems rather than becoming a second source of truth.

## Deterministic work must not invoke an LLM

Examples that SHOULD remain deterministic:

- structured Pulse item → GitHub Issue;
- GitHub API/webhook operations;
- link/identifier/status mapping;
- notifications;
- validation of required fields;
- Git branch/worktree creation and cleanup;
- commit/push/PR publication;
- CI polling/status checks;
- listing failed workflow jobs/steps;
- retrieving CI logs;
- extracting bounded error context by deterministic rules;
- retrying an eligible CI job;
- publishing structured evidence.

Reasoning workloads MAY invoke models for planning, coding, review, architecture tradeoffs, ambiguous classification and diagnosis/repair of in-scope CI defects.

## CI repair context discipline

`workflows/ci-feedback-and-repair.md` defines the remote CI loop.

Before model diagnosis, deterministic tooling SHOULD preserve provenance and reduce CI evidence to the minimum useful set:

```text
workflow/run
job
step
status/exit result
relevant error block
file/line when available
link to full logs
```

Do not send multi-thousand-line logs when a bounded failure block is sufficient.

## AI cost and quality telemetry

Where usage is exposed, EngineeringOS-compatible implementations SHOULD track enough metadata to answer:

- token/cost per run;
- token/cost per role;
- cost per GitHub Issue / Task Contract;
- cost per model/provider;
- cost per Feature/Milestone;
- `feedback_iterations`;
- `ci_repair_iterations`;
- first-pass CI success rate;
- time from PR open to `CI_GREEN`;
- model/provider versus CI rework rate.

`feedback_iterations` and `ci_repair_iterations` are distinct. A model may pass local review but still create remote CI rework; that difference is valuable quality evidence.

## Cost is not the only optimization target

A cheaper run that creates rework or weak evidence is not optimized.

AI FinOps balances cost, quality, latency, reliability, safety and human review burden.

The target is cost per accepted unit of engineering value.

A useful operational measure is:

```text
AI Cost / Accepted Engineering Value
```

## Caching and reuse

Stable derived context may be reused when correctness permits, such as approved Execution Plans, file summaries tied to commit SHA, architecture boundaries tied to document revision, and deterministic metadata.

Caching MUST NOT hide changes to acceptance criteria, ADRs/NFRs or code revisions.

## Observability

AI FinOps metrics SHOULD be observable without requiring an LLM to summarize them. Dashboards and deterministic reports are preferred for recurring cost/quality views.
