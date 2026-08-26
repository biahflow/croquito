# Documentation Drift and Tracked Follow-up

## Purpose

Prevent documentation, naming, indexes, generated knowledge artifacts, and other canonical project context from becoming stale findings that exist only in a chat, Builder report, Reviewer comment, or PR note.

EngineeringOS treats discovered drift as work that must be either repaired safely or tracked explicitly.

## Core invariant

```text
DISCOVERED_DRIFT
  ↓
classify
  ├─ TASK_SCOPE / REQUIRED_FOR_CORRECTNESS
  │     → repair in current task when safe
  ├─ PREEXISTING_SEPARABLE
  │     → create/link dedicated GitHub Issue
  └─ SCOPE_AMBIGUOUS / DECISION_REQUIRED
        → HUMAN_ATTENTION_REQUIRED
```

A prose-only recommendation such as "this deserves a follow-up issue" is not sufficient closure.

## What counts as documentation drift

Examples include:

- ADR/FDD/RFC indexes that omit canonical files;
- roadmap or PRD terminology that no longer matches the current product/system identity;
- current-state docs that contradict accepted ADRs or executable configuration;
- stale links or source-of-truth references;
- generated documentation/knowledge artifacts that no longer match their canonical inputs;
- renamed products/components that remain presented as the current name in canonical docs;
- README/project-context instructions that point harnesses to obsolete paths or workflows.

Historical references are not drift merely because they use an old name. They become drift when the document presents historical terminology as the current state or leaves the distinction ambiguous.

## Classification

### `DOCUMENTATION_DRIFT_TASK_SCOPE`

The drift is introduced by, directly caused by, or required to make the current Task Contract correct and complete.

Repair it in the current task when the change is deterministic, safe, and does not expand product/architecture scope.

### `DOCUMENTATION_DRIFT_PREEXISTING`

The drift predates the task and is separable from the current Task Contract.

Do not silently fold it into unrelated implementation. Before the current task can be reported complete, the harness MUST create or link a dedicated GitHub Issue containing:

- the stale source/location;
- expected current source of truth;
- bounded maintenance scope;
- acceptance criteria;
- provenance showing the finding is pre-existing when material;
- relationship/dependency to the discovering task when relevant.

The current task may continue when the drift does not invalidate its correctness, review evidence, or acceptance criteria.

### `DOCUMENTATION_DRIFT_SCOPE_AMBIGUOUS`

It is unclear whether correcting the documentation changes product meaning, architecture, contract scope, or an accepted decision.

Stop at `HUMAN_ATTENTION_REQUIRED`. Do not rewrite canonical meaning based only on inference.

## Completion rule

A task that discovers material drift MUST NOT finish with an untracked statement such as:

```text
"Fica para depois"
"Vale abrir uma Issue"
"Não é desta entrega"
```

unless that finding is accompanied by one of:

```text
FIXED_IN_CURRENT_TASK
TRACKED_FOLLOW_UP_ISSUE: <url-or-id>
HUMAN_ATTENTION_REQUIRED: <reason>
```

For separable pre-existing drift, the minimum accepted state is `TRACKED_FOLLOW_UP_ISSUE`.

## Reviewer responsibility

Reviewer MUST check whether material documentation/context drift reported by Builder has a disposition.

If a material finding has no repair, linked Issue, or justified human decision state, Reviewer returns:

```text
REVIEW_EVIDENCE_INCOMPLETE
reason: UNTRACKED_DOCUMENTATION_DRIFT
```

This is ordinarily evidence/follow-up repair: the harness creates or links the Issue and resubmits the evidence package. It is not automatically a Human Gate.

## Generated artifacts and indexes

When a repository commits deterministic derived artifacts or indexes, the applicable maintenance task must regenerate them using the repository's canonical command rather than hand-editing generated output when such a command exists.

Index completeness checks should be deterministic whenever practical. LLMs MUST NOT be used merely to enumerate filenames, compare IDs, detect missing index entries, or regenerate deterministic artifacts.

## Naming changes

When a product/system is renamed, the Task Contract or a dedicated migration task SHOULD inventory canonical current-state sources such as:

```text
README / project context
PRD / roadmap
ADR/FDD indexes
shell/product copy
runbooks
API or deployment naming when materially applicable
```

Do not blindly replace historical records. Preserve history and clarify current naming.

## Evidence

Builder/Reviewer evidence SHOULD record:

- finding classification;
- source file/location;
- whether it was task-scope or pre-existing;
- repair commit when fixed;
- linked follow-up Issue when separated;
- validation used to prove consistency.

## FinOps

File enumeration, ID sequence checks, link validation, grep/search, generated-index comparison, and repository metadata checks are deterministic operations and MUST NOT invoke an LLM merely for convenience.
