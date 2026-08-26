# Engineering OS

Engineering OS is a vendor-neutral source of truth for AI-assisted software delivery. It defines global engineering standards, approval boundaries, and agent contracts independently of any AI harness.

## v0.1 goal

Establish shared global context that both Claude Code and Codex can consume:

```text
Core → harness bootstrap → project instructions → task
```

Claude Code and Codex are harnesses/adapters. They consume this repository; they do not define its global rules. Both must reach the same Core and produce the same evidence for the same Task Contract; [`workflows/execution.md`](workflows/execution.md) defines that parity, and [`scripts/install-adapters.sh`](scripts/install-adapters.sh) installs the bootstraps that make the global context reachable from outside this checkout.

## Versioning and consumption

Consumer projects vendor this repository as a complete pinned mirror and name the version
they copied. [`VERSIONING.md`](VERSIONING.md) defines the SemVer policy for a rules layer —
what makes a change `MAJOR`, how a release is cut, and how a consumer advances its pin.

## Structure

| Area | Purpose |
| --- | --- |
| `core/` | Global engineering principles, guardrails, definition of done, and AI FinOps/context policy. |
| `agents/` | Role contracts for the Planner, Builder, and Reviewer. |
| `adapters/` | Minimal bootstrap documents for each harness. |
| `workflows/` | Vendor-neutral lifecycle conventions for work intake, execution, worktree isolation, review feedback/repair, validation, CI feedback/repair, Git publishing, release and delivery. |
| `templates/` | Small, reusable starting points for canonical work artifacts. |
| `scripts/` | Operator utilities, including adapter installation. |

## Operating model

Rules are resolved from the most general to the most specific:

```text
Core → Project instructions → Task
```

Project-level instructions may add constraints. They cannot weaken human approval gates or global guardrails in `core/`.

For cross-system delivery, [`workflows/work-intake-and-sync.md`](workflows/work-intake-and-sync.md) defines the responsibility split between Pulse, GitHub, EngineeringOS, One, and the project roadmap.

For model cost and context discipline, [`core/ai-finops-and-context.md`](core/ai-finops-and-context.md) defines minimum sufficient context, role-specific context budgets, and the rule that deterministic automation must not spend model tokens.

For user-visible changes, [`workflows/design-approval.md`](workflows/design-approval.md) defines the pre-build design gate and [`workflows/browser-runtime-validation.md`](workflows/browser-runtime-validation.md) defines post-build rendered/runtime evidence.

For writable task isolation and safe parallel execution, [`workflows/worktree-execution.md`](workflows/worktree-execution.md) defines the one-task/one-branch/one-worktree model, parallelism classification, synchronization, and cleanup.

For independent review feedback, [`workflows/review-feedback-and-repair.md`](workflows/review-feedback-and-repair.md) defines the bounded automatic Builder ↔ Reviewer repair loop and the conditions that truly require a human.

For remote verification, [`workflows/ci-feedback-and-repair.md`](workflows/ci-feedback-and-repair.md) defines CI states, bounded automatic repair, failure classification, and the rule that required remote CI must be green before human-review readiness.

For Git authority, [`workflows/git-publishing-and-human-merge.md`](workflows/git-publishing-and-human-merge.md) defines commit/push/PR authority while keeping merge as an explicit Human Gate.

For trunk-based release, [`workflows/trunk-based-delivery.md`](workflows/trunk-based-delivery.md) defines the generic `main → HML → immutable release promotion → PROD` model.

## Default review boundary

```text
Task Contract
  ↓
Planner
  ↓
Parallelism assessment
  ↓
Dedicated task worktree
  ↓
Builder + local/browser validation
  ↓
Reviewer
  ├─ findings/evidence gap → bounded automatic repair ↺
  └─ REVIEW_PASS
  ↓
Harness commits + pushes + opens PR
  ↓
Remote CI
  ├─ in-scope failure → bounded automatic repair ↺
  └─ CI_GREEN
  ↓
READY_FOR_HUMAN_REVIEW
  ↓
Human validates PR
  ↓
Human merges
  ↓
Local main sync + safe worktree cleanup
```

`REVIEW_FINDINGS` is not automatically a Human Gate.

`PR_OPEN` is not the same as `READY_FOR_HUMAN_REVIEW`.

A merged PR is engineering integration evidence. It is not automatically business/client acceptance or operational `DONE`.

## Scope boundaries

The original M1 bootstrap intentionally excluded orchestration, model routing, worktrees, parallel agents, and other advanced execution capabilities. Those capabilities are introduced only through explicit reviewed contracts and must not weaken human gates or vendor-neutral principles.
