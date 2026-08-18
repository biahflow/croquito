# Global Definition of Done

A task is complete only when the applicable requirements below are satisfied:

- implementation matches the accepted task specification;
- project architecture and applicable ADRs are respected;
- for work classified `INTERFACE_CHANGE`, an approved Design Approval Package exists, is referenced by the Feature Contract, and matches the revision that was built;
- relevant tests pass, including regression coverage when practical;
- linting, type checks, build, and security checks pass where configured;
- no secrets, credentials, or unrelated changes are introduced;
- documentation and operational notes are updated when the behavior or contract changed;
- the git diff is focused and reviewable;
- required human approval gates remain unbypassed.

## Validation baseline and final state

Validation evidence must distinguish the state before the change from the state after it:

```text
BASELINE → CHANGE → FINAL
```

- Record applicable preexisting failures as baseline evidence; do not attribute them to the current change without evidence.
- A failure introduced by the task prevents completion.
- Do not silently fix a preexisting failure outside the accepted scope. Expanding scope to fix it requires an explicit decision.

## Validation profiles

Projects should expose applicable validation profiles for their changes, such as `unit`, `integration`, `e2e`, `lint`, `typecheck`, `build`, and `security`. The Project Context owns the real commands and the task selects the applicable profiles; this Core does not prescribe tools or commands.

## Execution artifacts

Every artifact needed to execute or review a task, including its contract and acceptance criteria, must be accessible from the execution environment of the relevant agent. The project or workflow chooses the location; this Core does not prescribe a directory structure.

## Pre-flight capability check

Before a Builder modifies code, the workflow must establish that the required execution artifacts are accessible and that the Builder can read the needed scope, edit the accepted scope, and execute the validation profiles selected by the Project Context or Task Contract. Creating a commit is workflow-dependent.

If a required validation cannot be executed, deterministic validation evidence is incomplete and the task cannot be declared complete. This Core defines the requirement only; projects and tasks define the applicable commands.

## Final task report

The final task report must include:

1. files changed;
2. checks run and their result;
3. assumptions made;
4. remaining risks or follow-up work;
5. any approval still required.

For Builder work, the required `BUILD REPORT` in `agents/builder.md` is the canonical structured form of this report and `PRIMARY_EXECUTION_EVIDENCE` for that task. A Review Evidence Package may summarize execution, but it must preserve every applicable complete Builder Report or an accessible, unambiguous reference to it. A summary never replaces source evidence.
