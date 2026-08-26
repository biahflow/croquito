# Review Feedback and Automatic Repair

## Purpose

Define what an EngineeringOS-compatible harness must do when the independent Reviewer does not return `REVIEW_PASS`.

Reviewer findings are engineering feedback. They are not, by themselves, a Human Gate.

The default lifecycle is:

```text
Builder
  ↓
local/browser validation
  ↓
Reviewer
  ├─ REVIEW_PASS → publish/continue
  ├─ REVIEW_FINDINGS → classify → Builder repair ↺
  └─ REVIEW_EVIDENCE_INCOMPLETE → produce/recover evidence ↺
```

A human is required only when the finding cannot be resolved safely inside the accepted Task Contract, an approval boundary is reached, or the bounded repair loop is exhausted.

## Review states are not stop states

The following Reviewer results do not automatically stop execution:

```text
REVIEW_FINDINGS
REVIEW_EVIDENCE_INCOMPLETE
```

The harness MUST inspect the reported findings and classify whether they can be repaired within the current contract.

`REVIEW_PASS` means the reviewed revision is eligible to continue to Git publication / remote CI as applicable. It is not human approval.

## Finding classification

Before changing code or evidence, classify the Reviewer result into one of:

```text
REVIEW_REPAIR_TASK_SCOPE
REVIEW_REPAIR_EVIDENCE_ONLY
REVIEW_REPAIR_PREEXISTING
REVIEW_REPAIR_SCOPE_AMBIGUOUS
REVIEW_REPAIR_HUMAN_DECISION
```

### REVIEW_REPAIR_TASK_SCOPE

The finding is directly covered by the accepted Task Contract and can be fixed without introducing a new product, design, architecture, security, data or scope decision.

Examples:

- an acceptance criterion was not fully implemented;
- an approved design token/state was omitted;
- required tests are missing;
- browser evidence reveals a defect in the implemented surface;
- implementation does not match an already approved Design Approval Package.

Action: automatically return to the Builder.

### REVIEW_REPAIR_EVIDENCE_ONLY

The implementation may be acceptable but required evidence is missing or stale and can be produced deterministically without changing approved behavior.

Examples:

- required screenshots were not captured;
- a rendered state was not exercised;
- a validation result/report was not persisted;
- evidence does not identify the exact revision.

Action: produce/recover the missing evidence, create a new Review Evidence Package, and start a new Reviewer round.

Do not invoke an LLM merely to serialize evidence that already exists in structured form.

### REVIEW_REPAIR_PREEXISTING

The Reviewer surfaced a change/failure that predates the current task or belongs to unrelated user work.

Action:

- establish baseline/provenance;
- do not claim ownership;
- do not silently fix unrelated work;
- exclude/separate it from the task when safe;
- if it cannot be safely separated, classify the condition as scope ambiguous or blocked.

### REVIEW_REPAIR_SCOPE_AMBIGUOUS

It is unclear whether the requested repair belongs to the accepted Task Contract, or the repair would materially broaden scope.

Action: stop with `HUMAN_ATTENTION_REQUIRED` and state the exact ambiguity.

### REVIEW_REPAIR_HUMAN_DECISION

The Reviewer finding requires a decision that EngineeringOS reserves for a human.

Examples:

- new Design Approval beyond the approved revision;
- new product behavior or UX decision;
- architecture/security/data tradeoff not already authorized;
- waiver of a required guardrail;
- acceptance of a known blocking risk.

Action: stop at the applicable Human Gate.

## Automatic repair loop

For `REVIEW_REPAIR_TASK_SCOPE`:

```text
REVIEW_FINDINGS
  ↓
classify finding
  ↓
Builder repairs within Task Contract
  ↓
affected local/browser validation
  ↓
new BUILD REPORT
  ↓
new immutable Review Evidence Package
  ↓
new Reviewer round
  ↺
```

For `REVIEW_REPAIR_EVIDENCE_ONLY`:

```text
REVIEW_EVIDENCE_INCOMPLETE
  ↓
produce/recover required evidence
  ↓
new evidence revision
  ↓
new Reviewer round
  ↺
```

A materially changed implementation or evidence package MUST start a new Reviewer round. Never rewrite the previous Reviewer conclusion in place.

## Bounded iterations

Automatic review repair MUST be bounded.

Default:

```text
max_review_feedback_iterations = 3
```

Projects may override the value explicitly.

`feedback_iterations` counts Builder/Reviewer repair rounds caused by Reviewer findings/evidence deficiencies. It is separate from `ci_repair_iterations`, which is defined by `ci-feedback-and-repair.md`.

If the limit is exhausted and the Reviewer still cannot return `REVIEW_PASS`:

```text
REVIEW_REPAIR_BLOCKED
HUMAN_ATTENTION_REQUIRED
```

The harness must publish/report the unresolved findings and iteration history without weakening the acceptance criteria.

## Publication boundary

By default, unresolved blocking Reviewer findings prevent normal task publication as human-ready work.

```text
REVIEW_FINDINGS / REVIEW_EVIDENCE_INCOMPLETE
  → repair loop

REVIEW_PASS
  → commit/push/PR when other preconditions are satisfied
```

A project may permit publishing a draft PR earlier for collaboration, but it MUST NOT represent that revision as `READY_FOR_HUMAN_REVIEW` while blocking Reviewer findings or evidence deficiencies remain.

## Relationship to remote CI

Review repair and CI repair are distinct loops:

```text
IMPLEMENTATION LOOP
Builder ↔ Reviewer

then

INTEGRATION LOOP
PR ↔ required remote CI
```

If CI repair changes code, the repaired revision re-enters the Reviewer according to `ci-feedback-and-repair.md` before final readiness.

## Human attention conditions

Stop for a human only when one or more apply:

- a required explicit Human Gate is reached;
- scope is ambiguous or would need expansion;
- a new product/design/architecture/security/data decision is required;
- required capability/evidence cannot be produced;
- preexisting unrelated work cannot be separated safely;
- the configured review feedback iteration limit is exhausted;
- continuing automatically would violate another EngineeringOS guardrail.

Do not stop merely because a Reviewer found an in-scope defect.

## Evidence

Track at least:

```text
feedback_iterations
review_round
review_result
finding classification
repair revision/commit when applicable
validation rerun
remaining findings
human attention reason when blocked
```

## FinOps

Finding classification may require reasoning when scope is genuinely ambiguous.

Deterministic evidence capture, test execution, browser screenshots, status updates and iteration counting MUST NOT invoke an LLM merely for convenience.

`feedback_iterations` is a useful quality/rework metric and SHOULD remain separate from `ci_repair_iterations`.