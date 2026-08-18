# <FEATURE-ID> — Evidence

The review handoff. It consolidates references; it does not replace the source artifacts
it points to. A summary here is never more authoritative than the evidence it summarizes.

Every reference must be accessible to the Reviewer, unambiguous, stable for the review
round, and independent of private context from an earlier session.

## Round

```text
round: <value>
reviewed_commit_or_state: <value>
authorization: <the human decision that authorized this round, with its date>
```

If the package is materially updated after `REVIEW_EVIDENCE_INCOMPLETE`, start a new
round. Do not revise a previous result in place.

## 1. Contract and plan

References to the Feature Contract, the Execution Plan, and each Task Contract.

## 2. BASELINE

The state before the change, and every known preexisting failure. A preexisting failure
recorded here is not attributable to this work; one that is not recorded here will be.

## 3. CHANGE

What was done, per task. For each task, the complete `BUILD REPORT` or an accessible,
unambiguous reference to it. Preserve task attribution; do not merge reports into a
summary that loses authorship.

## 4. Validation

Profiles executed and their results, per task and for the integrated state. Profiles
skipped, with the reason.

## 5. Integration

Integration evidence and integrated validation, when integration occurred.

## 6. FINAL

The state after the change: files changed, diff or commits, and the working tree.

## 7. Review

Reviewer result for each round: `REVIEW_PASS`, `REVIEW_FINDINGS`, or
`REVIEW_EVIDENCE_INCOMPLETE`, with each finding, its severity, and its outcome.

## 8. Deviations, risks, and pending human decisions

Plan deviations, remaining risks, and the decisions that require human authority. A
review result is not human approval; list what is still owed.
