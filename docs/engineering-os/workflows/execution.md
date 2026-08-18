# Task Execution and Harness Parity

## Purpose and authority

This workflow defines what makes an authorized Task Contract executable by any harness,
and how a harness is assigned to a task. It is vendor-neutral: it names Claude Code and
Codex only as examples of harnesses, and it grants neither of them authority the Core
denies.

It defines conventions, not orchestration. Scheduling, routing, parallel agents, and
worktrees remain outside this milestone.

```text
TASK CONTRACT → HARNESS ASSIGNMENT → EXECUTION → BUILD REPORT
```

The Planner does not assign a harness; [its contract](../agents/planner.md) places harness
and model selection outside the plan. Assignment is a separate, human-owned act performed
on a task that is already `READY_FOR_BUILD`.

## Why parity matters

A harness is an execution environment, not a source of rules. The same Task Contract
picked up by a different harness must be governed by the same Core, produce the same
evidence, and stop at the same gates. When it does not, the harness has become a hidden
source of truth, and the difference between two executions stops being explainable.

Two failures make that happen:

- **Divergent bootstrap.** The adapters reach different documents, so one executor holds a
  guardrail the other does not. This is a defect in
  [the adapters](../adapters/README.md), not a property of the harness.
- **Context that lives outside the contract.** A task is executable only because of
  something the assigning human said in a conversation, or something an earlier session
  established. The other harness cannot see it, and neither can a Reviewer.

## Portability requirements

A Task Contract is portable when all of the following hold. Each is checkable before
assignment.

1. **Self-contained.** Goal, scope, out of scope, acceptance criteria, dependencies,
   required capabilities, and the sources to read are all in the contract. No requirement
   arrives by conversation.
2. **Commands are real and named.** Validation profiles carry the project's actual
   commands, from the Project Context. A profile without a command is not a profile.
3. **Baseline is declared.** The executor knows which failures already exist, so a
   preexisting failure is not attributed to the change and a new one is not absorbed into
   the noise.
4. **Scope is bounded in files, not intentions.** "Do not touch adjacent problem X" is
   stated, because an executor that notices X will otherwise fix it.
5. **Gates are named in place.** Approval gates the task will reach are written into the
   contract, not left to the executor to recognize.
6. **Report format is fixed.** The contract requires the complete `BUILD REPORT` from
   [the Builder contract](../agents/builder.md). Identical structure from every harness is
   what makes two executions comparable.
7. **Capabilities are verifiable.** The pre-flight capability check in
   [the Definition of Done](../core/definition-of-done.md) can be performed from the
   contract alone.

A contract that fails any of these is `TASK_CONTRACT_NOT_PORTABLE`. Record the missing
element and return it; do not repair it inside the executing session, where the repair
becomes invisible context.

## Harness assignment

Assignment is recorded outside the plan, so that reassigning a task does not edit frozen
planning:

```text
HARNESS ASSIGNMENT

task_id: <value>
harness: <value>
assigned_by: <human>
rationale: <value>
```

Rules:

- A human assigns; no agent selects its own harness or reassigns another agent's task.
- One task has one executor at a time. Two harnesses on one task produce two claims of
  authorship over one scope.
- Assignment does not change scope. A harness with a capability the contract did not grant
  still may not use it.
- Reassignment after execution began is a `PLAN_DEVIATION` when it changes planned work,
  and it does not discard the first executor's report.

## Concurrent execution

Two tasks may execute concurrently only when the plan placed them in the same
parallel group and neither carries an unresolved `PARALLELISM_RISK`. Each executor
reports independently.

Do not merge concurrent reports into one summary. The Review Evidence Package requires a
distinct report per task, with attribution preserved; a merged report loses exactly the
information a Reviewer needs to tell two executions apart.

## Evidence parity

Regardless of harness:

- every task ends with a complete `BUILD REPORT`;
- validation actually executed is distinguished from validation skipped;
- the harness is recorded alongside the report, as execution context — never as a reason a
  requirement did not apply;
- a missing or incomplete report is `BUILDER_CONTRACT_INCOMPLETE`, and correct code does
  not make it complete.

If two harnesses executing comparable tasks produce materially different evidence for the
same requirement, that is a finding about the contracts or the adapters. Record it; do not
resolve it by preferring the harness whose output reads better.

## Anti-patterns

- **Harness as rule set:** letting a harness's defaults decide what a task may change.
- **Verbal task:** an executable task that exists only in a conversation.
- **Invented command:** filling a validation profile with a plausible command.
- **Silent reassignment:** moving a task between harnesses without recording it.
- **Merged evidence:** one report covering several tasks or executors.
- **Capability drift:** using a capability the harness happens to have but the contract
  did not grant.
