# Task Execution and Harness Parity

## Purpose and authority

This workflow defines what makes an authorized Task Contract executable by any harness, how a harness is assigned to a task, and how writable execution is isolated.

It is vendor-neutral: Claude Code, Codex, and other harnesses consume the same rules and approval boundaries.

```text
TASK CONTRACT
  → HARNESS ASSIGNMENT
  → PARALLELISM ASSESSMENT
  → TASK WORKTREE
  → EXECUTION
  → BUILD REPORT
```

The Planner does not select a vendor/model. Harness assignment remains an orchestration or human responsibility unless a later approved routing contract says otherwise.

Writable execution follows [`worktree-execution.md`](worktree-execution.md). Reviewer feedback/repair follows [`review-feedback-and-repair.md`](review-feedback-and-repair.md). Git publication and the final human merge boundary follow [`git-publishing-and-human-merge.md`](git-publishing-and-human-merge.md).

## Why parity matters

A harness is an execution environment, not a source of rules. The same Task Contract picked up by a different harness must be governed by the same Core, produce the same evidence, and stop at the same gates.

Two common failures break parity:

- **Divergent bootstrap.** The adapters reach different documents, so one executor holds a guardrail the other does not.
- **Context outside the contract.** A task is executable only because of something said in a conversation or established in an earlier session that the other harness or Reviewer cannot access.

## Portability requirements

A Task Contract is portable when all of the following hold:

1. **Self-contained.** Goal, scope, out of scope, acceptance criteria, dependencies, required capabilities, validation classification, and sources to read are in the contract.
2. **Commands are real and named.** Validation profiles carry the project's actual commands.
3. **Baseline is declared.** The executor knows which failures already exist.
4. **Scope is bounded.** Adjacent work that must not be touched is explicit.
5. **Gates are named.** Required Design Approval, browser/runtime validation, Git publication, and Human Merge gates are declared when applicable.
6. **Report format is fixed.** The complete `BUILD REPORT` from the Builder contract is required.
7. **Capabilities are verifiable.** Pre-flight checks can be performed from the contract and project context.
8. **Execution ownership is attributable.** The task branch/worktree and active Builder ownership are unambiguous for writable execution.

A contract that fails these requirements is `TASK_CONTRACT_NOT_PORTABLE`. Record what is missing; do not repair it only inside private execution context.

## Harness assignment

Assignment is recorded independently from the frozen execution plan:

```text
HARNESS ASSIGNMENT

task_id: <value>
harness: <value>
assigned_by: <human-or-authorized-router>
rationale: <value>
```

Rules:

- one task has one active writable executor at a time;
- assignment does not change scope;
- a harness may not use capabilities the contract/project did not grant;
- reassignment after execution begins preserves prior evidence and is recorded when it changes planned execution.

## Writable execution isolation

A task with `WRITE` capability SHOULD execute in a dedicated branch and dedicated worktree according to [`worktree-execution.md`](worktree-execution.md).

Default invariant:

```text
one task
  → one branch
  → one writable worktree
  → one active Builder
```

The primary checkout SHOULD remain clean and primarily track/synchronize `main` rather than serve as the writable implementation environment for multiple tasks.

## Concurrent execution

Two tasks may execute concurrently only after their relationship has been classified:

```text
SAFE_TO_PARALLELIZE
PARALLELISM_RISK
DEPENDENCY_BLOCKED
```

`SAFE_TO_PARALLELIZE` permits execution in separate worktrees.

`PARALLELISM_RISK` requires explicit resolution before concurrent writable execution.

`DEPENDENCY_BLOCKED` means one task must wait for another task, artifact, migration, Design Approval, or architectural decision.

Worktree isolation prevents Git-state collisions; it does not prove architectural independence.

Each parallel task keeps a distinct Builder Report and Review Evidence Package. Do not merge multiple task reports into a summary that loses attribution.

## Interface changes

For `INTERFACE_CHANGE`, writable implementation must not begin before the required Design Approval Package receives explicit human approval.

A worktree may be created earlier for preparation, but its existence is not authorization to build the surface.

After implementation, browser/runtime validation follows [`browser-runtime-validation.md`](browser-runtime-validation.md).

## Automatic implementation feedback loop

Independent review is part of execution, not a human approval boundary.

```text
Builder
  ↓
local/browser validation
  ↓
Reviewer
  ├─ REVIEW_PASS → continue
  ├─ REVIEW_FINDINGS → classify → Builder repair ↺
  └─ REVIEW_EVIDENCE_INCOMPLETE → recover evidence → Reviewer ↺
```

`REVIEW_FINDINGS` and `REVIEW_EVIDENCE_INCOMPLETE` MUST NOT automatically stop the harness for a human.

The harness follows [`review-feedback-and-repair.md`](review-feedback-and-repair.md): in-scope defects and evidence deficiencies are repaired automatically within a bounded loop. A human is called only for a genuine approval/scope/decision boundary, unavailable required capability/evidence, unsafe preexisting-work conflict, or exhausted feedback iterations.

Default review feedback budget:

```text
max_review_feedback_iterations = 3
```

`feedback_iterations` is separate from `ci_repair_iterations`.

## Publishing and merge boundary

When validation and review permit publication, the harness may create focused commits, push the task branch, open/update the PR, and publish evidence as defined in [`git-publishing-and-human-merge.md`](git-publishing-and-human-merge.md).

The normal integration path is:

```text
Task worktree
  ↓
Builder + deterministic validation
  ↓
Reviewer repair loop until REVIEW_PASS
  ↓
commit + push
  ↓
Pull Request
  ↓
required remote CI + bounded CI repair loop
  ↓
CI_GREEN
  ↓
READY_FOR_HUMAN_REVIEW
  ↓
HUMAN MERGE
```

The harness MUST NOT merge the task branch into local `main` as a substitute for the PR gate.

## Post-merge cleanup

After a human merges the PR, synchronize the primary local `main`, then remove the merged task worktree/branch only when cleanup is safe.

The detailed cleanup contract and safety checks are in [`worktree-execution.md`](worktree-execution.md).

## Evidence parity

Regardless of harness:

- every Builder round ends with a complete `BUILD REPORT`;
- every materially changed review revision receives a new Reviewer round;
- validation executed is distinguished from validation skipped;
- browser/runtime evidence is present when required;
- `feedback_iterations` and `ci_repair_iterations` are attributable and distinct;
- branch/worktree ownership and final commit/PR references are attributable when writable execution occurred;
- the harness is recorded as execution context, never as a reason a requirement did not apply;
- a missing or incomplete report remains `BUILDER_CONTRACT_INCOMPLETE` even when code appears correct.

If comparable harness executions produce materially different evidence for the same requirement, record a contract/adapter finding rather than preferring the nicer-looking output.

## Anti-patterns

- **Harness as rule set:** letting harness defaults decide policy.
- **Verbal task:** requirements exist only in conversation.
- **Invented command:** validation uses a plausible but unverified command.
- **Shared writable checkout:** parallel Builders mutate the same worktree/index.
- **Worktree equals safe parallelism:** assuming filesystem isolation proves dependency independence.
- **Reviewer as human gate:** stopping for a person on an in-scope defect the Builder can repair automatically.
- **Silent reassignment:** executor changes without evidence.
- **Local-main integration:** task branch is merged locally to bypass the PR/Human Gate.
- **Unsafe cleanup:** deleting a worktree/branch with uncommitted work or an unmerged task.
- **Merged evidence:** one report hides distinct task/executor provenance.
- **Capability drift:** using a capability simply because the harness exposes it.

## Evolution to automatic worker routing

Future orchestration may automatically select workers from declared capabilities. That changes assignment mechanics, not the execution contract.

A future router must still preserve:

- Task Contract portability;
- parallelism/dependency classification;
- one writable ownership per task;
- dedicated branch/worktree isolation;
- Builder/Reviewer evidence parity;
- automatic bounded Reviewer repair;
- browser/runtime evidence when required;
- harness-prepared PR;
- human-only merge authority.

Adding or replacing a worker must not require changing Core engineering policy.
