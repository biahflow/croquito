# Feature Lifecycle and Work Intake

## Purpose and authority

This workflow defines how planned work is discovered, specified, planned, executed, evidenced, and concluded. It is vendor-neutral and project-neutral. It defines conventions, not automation, a scheduler, or an executable state machine.

```text
ROADMAP
   ↓
FEATURE SELECTION
   ↓
FEATURE SPECIFICATION
   ↓
DESIGN APPROVAL          (when INTERFACE_CHANGE)
   ↓
READY_FOR_PLANNING
   ↓
PLANNER
   ↓
PLAN VALIDATION
   ↓
READY_FOR_BUILD
   ↓
TASK EXECUTION
   ↓
INTEGRATION
   ↓
VALIDATION
   ↓
REVIEW
   ↓
READY_FOR_HUMAN_REVIEW
   ↓
HUMAN DECISION
   ↓
DONE
```

`BLOCKED` and `CANCELLED` may apply when appropriate. Design approval is defined in [`design-approval.md`](design-approval.md); it applies only to work classified `INTERFACE_CHANGE`, and it precedes planning rather than building, because a plan that decomposes an unapproved surface produces tasks that must be re-cut when the design changes.

```text
ROADMAP ITEM
      ↓
FEATURE CONTRACT
      ↓
EXECUTION PLAN
      ↓
TASK CONTRACTS
      ↓
EXECUTION
      ↓
VALIDATION / REVIEW EVIDENCE
      ↓
HUMAN GATE
      ↓
DONE
```

Each artifact has one responsibility:

- **Roadmap item:** what the product or project intends to build.
- **Feature Contract:** what a feature must deliver correctly.
- **Design Approval Package:** what an `INTERFACE_CHANGE` surface must look like, approved by a human before planning.
- **Execution Plan:** how the feature is decomposed and executed.
- **Task Contract:** the bounded scope assigned to an executor.
- **Evidence:** proof of implementation, validation, integration, and review.

Do not use an artifact to silently replace another artifact's responsibility.

## Roadmap and status

`ROADMAP.md` is the default canonical index for planned work and work discovery, created from [the global template](../templates/roadmap.md). A project may document an equivalent location in its Project Context. A roadmap entry is intentionally brief: it identifies a stable feature ID, priority, lifecycle status, and Feature Contract when one exists. It does not contain the full technical specification.

For a feature that has a `feature.md`, that contract is the canonical detailed record of its lifecycle status. The corresponding roadmap entry is a synchronized discovery view and must not independently contradict it. For an item that has no Feature Contract yet, its roadmap entry is the canonical record of its pre-specification status.

`STATUS.md`, when present, is a `DERIVED_STATUS_VIEW`: a snapshot, dashboard, or summary derived from canonical roadmap, feature, plan, task, and evidence artifacts. It must never be maintained as an independent decision about whether work is in progress or done.

## Default project layout

The recommended default is:

```text
repo/
├── ROADMAP.md
└── docs/
    └── features/
        └── F-023-customer-onboarding/
            ├── feature.md
            ├── plan.md
            └── evidence.md
```

Task Contracts may live under `docs/features/<feature-id>/tasks/` when that improves clarity. Projects may use an equivalent documented layout; they must not create a second incompatible lifecycle or destructively reorganize existing documentation merely to match this default.

Feature IDs must be unique, stable, legible, and used consistently by related artifacts. `F-001` is a recommended format, not a required numbering system.

## Lifecycle

| State | Meaning and expected eligibility |
| --- | --- |
| `BACKLOG` | Planned work not executable. |
| `READY_FOR_SPEC` | Awaiting a Feature Contract. |
| `SPEC_IN_PROGRESS` | Feature Contract is being prepared. |
| `READY_FOR_PLANNING` | Feature Contract is sufficient for the Planner. |
| `PLANNING` | Planner is producing or revising the Execution Plan. |
| `READY_FOR_BUILD` | Plan is valid and any applicable planning gate is satisfied. |
| `IN_PROGRESS` | At least one authorized task is executing. |
| `READY_FOR_REVIEW` | Implementation is integrated and awaiting review. |
| `READY_FOR_HUMAN_REVIEW` | Required checks and review are complete; a human decision remains. |
| `DONE` | Applicable completion criteria and human gate are satisfied. |
| `BLOCKED` | A dependency or decision prevents progress. |
| `CANCELLED` | Work will not continue. |

The normal direction is `BACKLOG → READY_FOR_SPEC → SPEC_IN_PROGRESS → READY_FOR_PLANNING → PLANNING → READY_FOR_BUILD → IN_PROGRESS → READY_FOR_REVIEW → READY_FOR_HUMAN_REVIEW → DONE`. `BLOCKED` and `CANCELLED` may be entered when justified and returned from only through an explicit decision. This is a semantic lifecycle, not automatic enforcement.

No executor may mark a feature `DONE` merely because one task is complete. `DONE` requires the applicable Definition of Done, retained evidence, and the human gate required by the work.

## Work intake and eligibility

For discovery, an agent must:

```text
READ ROADMAP → IDENTIFY ELIGIBLE ITEMS → REPORT → HUMAN SELECTS → SPEC / PLAN → EXECUTE
```

An agent may inspect the roadmap, identify eligible or blocked items, and report inconsistencies. Without authorization, it may not select product priority, choose which feature to implement, move an item from `BACKLOG` to `IN_PROGRESS`, or begin implementation.

Eligibility is conceptual:

- `BACKLOG` is not executable.
- `READY_FOR_SPEC` needs a Feature Contract.
- `READY_FOR_PLANNING` permits planning only when the Feature Contract is sufficient.
- `READY_FOR_BUILD` requires a valid Execution Plan and any applicable human planning gate.
- `IN_PROGRESS` requires at least one authorized task.
- `READY_FOR_REVIEW` requires completed implementation and a review handoff.
- `READY_FOR_HUMAN_REVIEW` requires applicable validation and review evidence.
- `DONE` requires the applicable human decision.

## Specification, planning, tasks, and evidence

Create a Feature Contract from [the global template](../templates/feature.md). It states **what** must be delivered; it does not contain task decomposition, harness or model selection, or worktree details.

`plan.md` is produced by the Planner from `feature.md` and states **how** the accepted feature will be executed, using [the global template](../templates/plan.md). The Planner's authority and required plan format remain exclusively in [the Planner contract](../agents/planner.md); this workflow does not duplicate them.

Task Contracts are derived from the valid Execution Plan, using [the global template](../templates/task.md). Builders must not spontaneously create their own tasks. Each Task Contract references its Feature ID, Task ID, parent plan, scope, out of scope, acceptance criteria, dependencies, validation requirements, and required capabilities. [The execution workflow](execution.md) defines when such a contract is portable between harnesses and how an executor is assigned to it.

`evidence.md` consolidates baseline, Builder reports, validation results, commits, integration evidence, Reviewer results, plan deviations, remaining risks, and outstanding human decisions, using [the global template](../templates/evidence.md). It is the review handoff, not a substitute for the source artifacts. A future workflow may generate it; this workflow does not automate it.

## Roles and gates

The Planner creates and validates the Execution Plan, the Builder executes one authorized Task Contract with deterministic evidence, and the Reviewer evaluates the evidence read-only. Their detailed authorities are defined in the respective agent contracts.

Neither a Planner, Builder, nor Reviewer grants human approval. Global guardrails remain in force throughout the lifecycle. Production changes, destructive migrations or data changes, security exceptions, and consequential architectural changes require explicit human approval.

## Global and project responsibilities

Global Engineering OS defines the names, lifecycle, hierarchy, template, authority boundaries, and expected agent behavior. Project Context defines the actual roadmap, priorities, feature data, stack, validation commands, architecture, and any documented equivalent artifact locations.

A project may adapt the default structure but must explain a materially different convention. It must not silently weaken global approval gates or invent an incompatible lifecycle.

## Existing repositories

Existing projects may already use `roadmap.md`, `ROADMAP.md`, `docs/roadmap.md`, `status.md`, or `TODO.md`. Onboarding must inspect which artifact is currently authoritative, propose a controlled migration, preserve history, and never delete or rewrite existing planning content automatically.

## Anti-patterns

- “Read all markdown files, see what is missing, and implement it”: it couples discovery, prioritization, planning, and implementation.
- Treating `ROADMAP.md` and `STATUS.md` as independent sources of lifecycle truth.
- A Feature Contract without verifiable acceptance criteria.
- A Builder deciding or broadening its own task scope.
- A Planner changing feature requirements.
- Marking a feature `DONE` without applicable evidence and human gate.
- Recording a technical task directly as a product feature when it belongs under a parent feature.

## Conceptual check

A hypothetical `F-101` can move from `READY_FOR_SPEC`, through a Feature Contract and valid plan with task contracts, to `IN_PROGRESS`, then `READY_FOR_HUMAN_REVIEW`, and only to `DONE` after the applicable human decision. This example establishes no real Engineering OS feature.
