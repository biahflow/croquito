# Git Publishing and Human Merge Gate

## Purpose

Define the default Git authority of an EngineeringOS-compatible harness after implementation and review.

```text
Task Contract
  ↓
Planner
  ↓
Builder + local validation
  ↓
Reviewer
  ↓
commit + push + PR
  ↓
remote CI
  ↓
repair loop when required
  ↓
CI_GREEN
  ↓
READY_FOR_HUMAN_REVIEW
  ↓
Human reviews and merges
```

Remote CI and automatic repair follow `ci-feedback-and-repair.md`.

## Default harness authority

When a Task Contract is authorized and repository access permits it, the harness MAY:

- use the dedicated task branch/worktree;
- create focused commits in accepted scope;
- push the task branch;
- open/update the pull request;
- observe required remote CI;
- inspect failed jobs and relevant logs;
- repair failures classified as task-scope failures within the bounded loop in `ci-feedback-and-repair.md`;
- publish execution, review and CI evidence to the Issue/PR.

These actions prepare work for human review; they do not approve it.

## Human-only authority

The harness MUST NOT merge a pull request, enable auto-merge, approve its own work on behalf of a human, bypass required protections, or mark acceptance-required work `Done` merely because a PR merged.

```text
PR_OPEN
  = published review artifact; CI may still be pending

READY_FOR_HUMAN_REVIEW
  = required local evidence complete + required remote CI green

MERGE
  = explicit human decision
```

## Preconditions for opening a PR

Before initial publication, the harness MUST have:

- a valid Task Contract;
- approved planning/design gates when required;
- a complete Builder Report;
- applicable local validation;
- a Reviewer result that permits publication for remote verification;
- required browser/runtime evidence when applicable at this stage;
- a focused diff within accepted scope.

Opening the PR does not establish final readiness.

## Preconditions for `READY_FOR_HUMAN_REVIEW`

The harness MUST NOT publish `READY_FOR_HUMAN_REVIEW` until:

- local validation is complete for the final published revision;
- Review Evidence is complete;
- the current Reviewer result permits human handoff;
- required browser/runtime evidence is complete;
- every required remote CI check for the current revision is green;
- no blocking finding remains;
- the PR is accessible to the human reviewer.

When required CI is pending or failing, use the states defined in `ci-feedback-and-repair.md` instead.

## Engineering ledger

GitHub is the engineering work ledger. Relevant state SHOULD be published deterministically rather than remaining only in a local harness transcript.

Useful checkpoints:

```text
execution.started
build.completed
review.completed
pr.opened
ci.pending
ci.failed / ci.repair_in_progress
ci.green
ready_for_human_review
```

A final human-review publication SHOULD include or reference the final commit, local validation, browser evidence when applicable, required CI result, `ci_repair_iterations`, Reviewer result, PR URL, risks and the pending Human Merge Gate.

Do not invoke another model merely to rewrite evidence that already exists in structured form.

## Pull request expectations

The PR SHOULD link the originating Issue, summarize scope, expose validation and CI evidence, identify remaining rollout steps and remain open for human inspection.

Use a non-closing Issue reference when merge is not equivalent to final operational/client acceptance.

## Failure behavior

Publishing and CI observation MUST be safe to retry. Do not create duplicate PRs or noisy duplicate status comments. A required CI failure enters `ci-feedback-and-repair.md`; it does not become `READY_FOR_HUMAN_REVIEW`.

## FinOps

Commit/push/PR operations, CI status polling, job/log retrieval and evidence serialization are deterministic operations. Model reasoning should be used only when diagnosis or repair actually requires engineering reasoning.
