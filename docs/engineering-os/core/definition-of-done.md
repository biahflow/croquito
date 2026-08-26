# Global Definition of Done

A task is complete only when the applicable requirements below are satisfied:

- implementation matches the accepted task specification;
- project architecture and applicable ADRs are respected;
- for work classified `INTERFACE_CHANGE`, an approved Design Approval Package exists, is referenced by the Feature Contract, and matches the revision that was built;
- browser/runtime validation satisfies `workflows/browser-runtime-validation.md` for the declared validation class;
- relevant local tests pass, including regression coverage when practical;
- local linting, type checks, build, and security checks pass where configured;
- required remote CI for the published revision is green before `READY_FOR_HUMAN_REVIEW`;
- CI failures follow the bounded classification/repair workflow in `workflows/ci-feedback-and-repair.md`;
- no secrets, credentials, or unrelated changes are introduced;
- documentation and operational notes are updated when behavior or contract changed;
- the git diff is focused and reviewable;
- required human approval gates remain unbypassed.

## Validation baseline and final state

Validation evidence must distinguish:

```text
BASELINE → LOCAL CHANGE → PUBLISHED REVISION → REMOTE CI → FINAL
```

- Record applicable preexisting failures as baseline evidence.
- A failure introduced by the task prevents completion.
- Do not silently fix a preexisting failure outside accepted scope.
- Local success does not replace remote CI when CI is required.
- Remote CI success does not replace local validation.

## Validation profiles

Projects should expose applicable validation profiles such as `unit`, `integration`, `e2e`, `browser`, `lint`, `typecheck`, `build`, `security`, and required remote CI checks. The Project Context owns actual commands/check names.

For user-visible behavior, the Task Contract should declare `BROWSER_REQUIRED`, `BROWSER_CONDITIONAL`, or `BROWSER_NOT_REQUIRED` according to `workflows/browser-runtime-validation.md`.

## Execution artifacts

Every artifact needed to execute or review a task, including its contract and acceptance criteria, must be accessible from the relevant execution environment.

## Pre-flight capability check

Before a Builder modifies code, establish that required artifacts are accessible and the Builder can read/write accepted scope and run required local validation.

Creating commits, pushing the task branch, opening/updating the PR, observing CI and publishing evidence are allowed by default when authorized and supported, subject to `workflows/git-publishing-and-human-merge.md` and `workflows/ci-feedback-and-repair.md`.

If required validation cannot run, evidence is incomplete and the task cannot be declared complete.

## Human merge boundary

```text
Builder + local validation
  ↓
Reviewer
  ↓
commit + push + PR
  ↓
required remote CI
  ↓
CI_GREEN
  ↓
READY_FOR_HUMAN_REVIEW
  ↓
HUMAN MERGE GATE
```

The harness MUST NOT merge or enable auto-merge. Merge remains an explicit human decision.

A merge does not automatically imply business/client acceptance or operational `DONE` when a later acceptance stage exists.

## Final task report

The final task report must include:

1. files changed;
2. local checks run and results;
3. browser/runtime validation status/evidence when applicable;
4. remote CI state and final green check/run reference when required;
5. `ci_repair_iterations` and repair history when non-zero;
6. assumptions made;
7. remaining risks/follow-up work;
8. commit SHA and PR URL when publishing is available;
9. any approval still required.

The Builder Report remains primary execution evidence for Builder work. Review summaries must preserve source evidence rather than replace it.

When GitHub write access is available, execution/review/CI state and final `READY_FOR_HUMAN_REVIEW` evidence should be discoverable from the originating Issue and/or PR rather than existing only in a local harness transcript.
