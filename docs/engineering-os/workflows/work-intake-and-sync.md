# Work Intake and Cross-System Synchronization

## Purpose

Define the operating contract between business delivery, engineering execution, client acceptance, and roadmap state without duplicating the same state across multiple tools.

> Pulse chooses and prioritizes business work. GitHub Issues specify engineering work. EngineeringOS executes engineering work. One captures client acceptance. The roadmap explains macro direction.

EngineeringOS remains vendor-neutral at the harness layer, but the Biahflow reference implementation uses Pulse + GitHub + One directly.

## Systems of record

| Concern | Source of truth | Responsibility |
| --- | --- | --- |
| CRM, customer, opportunity, business priority | Pulse | Business/operational state |
| Non-technical operational work | Pulse | Business execution |
| Executable engineering task | GitHub Issue | Technical Task Contract consumed by the harness |
| Engineering board/queue | GitHub Issues / Projects | Engineering work state |
| Code, PR, CI, review evidence | GitHub | Engineering state and evidence |
| Engineering rules and role contracts | EngineeringOS | How work is planned, built, reviewed, and approved |
| Strategic sequence and milestone state | `roadmap.md` in the product repository | Macro direction |
| Client acceptance | One | Client-facing review and acceptance evidence |

ClickUp, Make, or similar external tools are optional adapters only. They are not dependencies of the Biahflow core workflow.

## Work hierarchy

```text
Pulse / Implementation Plan / roadmap.md
        ↓
GitHub Issue
        ↓
Planner
        ↓
Execution Plan
        ↓
Builder
        ↓
Deterministic validation
        ↓
Reviewer
        ↓
Harness commit + push + open PR
        ↓
PR CI + evidence publication
        ↓
READY_FOR_HUMAN_REVIEW
        ↓
Human Gate
        ↓
Human Merge
        ↓
Ready for Acceptance
        ↓
One / Client Review
        ↓
Accepted
        ↓
Done
```

For `INTERFACE_CHANGE`, insert the required Design Approval Gate before planning and the browser/runtime validation required by `browser-runtime-validation.md` after implementation.

## Harness source of work

The GitHub Issue is the primary executable work contract for a Builder.

The harness MUST NOT scan Pulse, GitHub Projects, or the roadmap looking for the next task to implement. Work selection is an operational responsibility outside the Builder.

A GitHub Issue intended for EngineeringOS execution SHOULD contain:

- objective;
- context necessary for the task;
- acceptance criteria;
- scope;
- out of scope;
- affected components when known;
- dependencies;
- applicable ADR/NFR/FDD references;
- validation requirements, including browser validation class when applicable;
- milestone/workstream reference;
- Pulse/project reference when useful for audit/correlation.

References SHOULD be explicit so agents retrieve only the context required for the current role.

## Pulse to GitHub

When business planning determines that an item requires engineering, the Pulse backend MAY provision a GitHub Issue through the GitHub API.

Before creation, the integration SHOULD validate the minimum Task Contract:

- title;
- objective;
- acceptance criteria;
- repository;
- relevant references;
- workstream/milestone.

Pulse SHOULD persist the GitHub repository, issue number, URL, and correlation identifiers. Provisioning an Issue does not necessarily mean execution started.

No LLM is required for this transformation when the source fields are structured.

## GitHub execution ledger

GitHub is the engineering work ledger, not merely the place where a task originates.

When write access is available, execution state and evidence SHOULD be discoverable from the originating Issue and/or PR. The harness SHOULD publish deterministic lifecycle checkpoints and canonical evidence according to `git-publishing-and-human-merge.md` rather than leaving the only record in a local terminal transcript.

Publishing comments, commit metadata, PR links, validation summaries, and status transitions is deterministic work. Do not invoke another model merely to re-summarize reports that already exist.

## GitHub to Pulse

The Pulse backend consumes GitHub webhooks directly. Webhook handlers MUST be idempotent and retry-safe.

Recommended semantic projection into Pulse:

| GitHub event | Business-facing meaning |
| --- | --- |
| Issue created | Engineering work provisioned |
| Harness/Builder starts | Engineering in progress |
| PR opened | Internal/human review artifact available |
| Required CI/review fails | Remain in internal review; expose link/evidence |
| PR ready for human review | Awaiting Human Gate |
| PR merged by human | Ready for acceptance |
| Client accepts in One | Accepted |
| Operational close | Done |

Pulse SHOULD store only the engineering state necessary for business visibility and orchestration. Detailed technical evidence remains in GitHub.

## Git publishing authority

After the applicable Builder and Reviewer requirements are satisfied, the authorized harness MAY:

- create focused commit(s);
- push its task branch;
- open/update the pull request;
- publish execution and review evidence.

The harness MUST NOT merge, enable auto-merge, bypass branch protection, or approve on behalf of a human.

```text
OPEN PR
  = machine-prepared review artifact

MERGE
  = explicit Human Gate
```

The full authority and failure contract is defined by `git-publishing-and-human-merge.md`.

## Merge is not Done

A merged PR proves engineering integration completed. It does not prove business/client acceptance.

```text
PR merged
    ≠
Done
```

The preferred semantic event is:

```text
engineering.ready_for_acceptance
```

Client acceptance is a separate transition and separate evidence.

## One acceptance loop

One is the client-facing projection and acceptance surface.

When engineering becomes ready for acceptance:

```text
Human merges GitHub PR
  ↓
Pulse receives webhook
  ↓
Pulse records Ready for Acceptance
  ↓
One receives/refreshes client projection
  ↓
Client reviews and accepts
  ↓
client.accepted
  ↓
Pulse closes business state
  ↓
GitHub Issue may move to Done/Closed by deterministic integration
```

The authoritative business acceptance evidence MUST be durable outside transient observability tooling.

## Where technical detail lives

Pulse and One SHOULD NOT mirror every CI check, review thread, or code detail.

Detailed evidence remains in GitHub:

- test results;
- lint/type checks;
- browser/runtime evidence when applicable;
- security checks;
- review threads;
- code diff;
- PR approval evidence.

Pulse and One link or project the business-relevant result instead of copying technical detail.

## Roadmap discipline

The roadmap is strategic state, not an execution queue.

Do not update the roadmap on every Issue or PR. A roadmap item SHOULD change when a Feature, Workstream, or Milestone changes macro state.

A roadmap update SHOULD normally arrive through a reviewed documentation PR instead of an integration writing directly to `main`.

## `roadmap.md` and `status.md`

Projects SHOULD avoid maintaining two documents containing the same operational state.

Preferred model:

- `roadmap.md` contains `Now`, `Next`, `Later`, milestone/workstream state, and strategic context;
- Pulse contains business/operational state;
- GitHub contains detailed engineering state;
- One contains client-facing review/acceptance state.

A separate `status.md` SHOULD NOT exist unless it contains materially different information with a clear owner and consumer.

Machine-generated status views SHOULD derive from authoritative systems rather than becoming duplicate prose.

## Deterministic automation rule

Do not spend model tokens on deterministic transitions.

Use ordinary application/harness code for:

- GitHub API calls;
- webhook handling;
- status mapping;
- Issue creation from structured fields;
- commit/push/PR publication after engineering decisions are complete;
- comments and links;
- validation/evidence serialization;
- notifications;
- metadata propagation;
- roadmap checkbox/state synchronization after an explicit macro-state decision.

Use an LLM only where reasoning materially contributes, for example planning, implementation, review, architecture analysis, risk analysis, and ambiguous discovery.

## Correlation

Cross-system automation SHOULD preserve stable identifiers when available:

- pulse_project_id;
- pulse_work_item_id;
- github_repository;
- github_issue_number;
- github_pr_number;
- one_delivery_id;
- workstream_id;
- correlation_id.

## Failure behavior

Integration MUST be retry-safe and SHOULD be idempotent.

At minimum:

- do not create a second GitHub Issue when a work item already stores one;
- do not create duplicate PRs for the same task/branch;
- deduplicate webhook deliveries using provider delivery IDs/event IDs;
- do not regress business state because an older webhook arrives late;
- do not mark `DONE` from a GitHub merge event;
- surface failed synchronization/publication for human repair;
- keep authoritative state in the owning system.

## Human gate

Automation may synchronize state, publish commits/PRs, and publish evidence, but it MUST NOT weaken human approval gates defined by EngineeringOS or project-level policy.

For the default GitHub lifecycle, **merge is human-only**.
