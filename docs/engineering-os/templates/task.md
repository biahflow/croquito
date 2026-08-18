# <TASK-ID> — <Task Name>

A Task Contract is the unit handed to an executor. It is derived from a valid Execution
Plan; a Builder never creates its own task.

It must be self-contained. Assume the executor has the Core, this contract, and the
repository — and nothing else. No memory of an earlier session, no context from the
conversation that produced the plan, no access to the person who wrote it.

## Identity

```text
feature_id: <value>
task_id: <value>
parent_plan: <path to the plan this task was derived from>
depends_on: <task IDs from the parent plan, or none>
```

## Goal

One outcome, stated so that its completion is checkable by someone who did not plan it.

## Scope

The files, modules, or contracts this task may change.

## Out of Scope

What this task must not touch, including adjacent problems the executor will notice and
must leave alone. Name them; an unnamed exclusion gets absorbed.

## Acceptance Criteria

Verifiable criteria. Each one states how it is checked, not only what should be true.

Every criterion must be executable literally as written: run each command a criterion names
before publishing the contract. A criterion that cannot pass as written — a command that
does not show what the criterion expects, a check the granted capabilities forbid — is
returned as `TASK_CONTRACT_NOT_PORTABLE` by a correct executor, at the cost of a full
contract round trip.

## Validation

The validation profiles this task must run, with the project's real commands, and the
baseline expected before the change.

```text
baseline: <command(s) and the known preexisting result>
required: <profile: command>
```

Do not invent a command. A required check that cannot run does not become optional: report
`BUILDER_VALIDATION_BLOCKED`, list the check under `Validation skipped` with the reason it
could not run, and name `VALIDATE` in `Unavailable capabilities`, as
[the Builder contract](../agents/builder.md) requires.

## Required Capabilities

```text
READ:     <scope that must be readable>
WRITE:    <scope that must be writable>
VALIDATE: <profiles that must be executable>
COMMIT:   allowed | forbidden
```

## Context to Read First

The specific canonical sources for this task — not the whole documentation set.

## Known Risks

What is likely to go wrong in this scope, and what a wrong turn would look like.

## Human Gates

Decisions inside or adjacent to this scope that the executor must stop at rather than
resolve. State the gate even when the executor is expected to reach it.

## Reporting

End with the complete `BUILD REPORT` required by
[the Builder contract](../agents/builder.md). Every field present; `none` where empty.
