# Browser and Runtime Validation Evidence

## Purpose

Define when an EngineeringOS task must validate behavior in a real rendered/browser/runtime surface, instead of relying only on static analysis, unit tests, component tests, or API tests.

This policy complements `workflows/design-approval.md`:

- **Design Approval** proves that an intended human-perceivable surface was approved before planning/building.
- **Browser/Runtime Validation** proves that the implemented surface actually renders and behaves as required after building.

Neither substitutes for the other.

## Classification

Every executable Task Contract MUST declare one browser-validation classification:

```text
BROWSER_REQUIRED
BROWSER_CONDITIONAL
BROWSER_NOT_REQUIRED
```

If the Task Contract omits the classification, the Planner MUST infer it from the rules below and record the result in the Execution Plan. If the change is user-visible and the classification remains ambiguous, return `TASK_CONTRACT_NOT_PORTABLE` or request clarification instead of silently skipping browser evidence.

## BROWSER_REQUIRED

Browser/runtime validation is REQUIRED when the change:

- creates or materially changes a human-perceivable web surface;
- changes layout, navigation, visual hierarchy, color, typography, spacing, responsive behavior, interaction, focus, loading, empty, error, unauthorized, or disabled states;
- introduces or changes a design-system token/component in a way visible in rendered UI;
- changes frontend behavior whose acceptance criteria depend on real browser execution;
- fixes a browser-specific or integration-visible defect;
- changes client-side routing, authentication/session behavior, accessibility behavior, or browser storage when those semantics are part of acceptance;
- is explicitly classified `INTERFACE_CHANGE` and the implementation reaches a browser-rendered surface.

Required evidence SHOULD include, as applicable:

- browser/tool and environment used;
- route or scenario exercised;
- viewport(s) when layout/responsiveness matters;
- states exercised;
- automated browser result (for example Playwright) and/or direct browser evidence;
- fixed screenshot(s) or equivalent rendered evidence when visual acceptance matters;
- any deviations from the approved Design Approval Package.

A passing unit/component test suite does not satisfy `BROWSER_REQUIRED` by itself.

## BROWSER_CONDITIONAL

Browser/runtime validation is CONDITIONAL when the code change is not itself frontend work but can alter a user-visible projection or runtime behavior.

Examples:

- backend/configuration change that causes a new flag/status to appear automatically in an existing UI;
- API contract change consumed by an existing frontend;
- permissions or feature-flag change whose visible result depends on runtime configuration;
- integration change that may affect an already-rendered status surface.

For `BROWSER_CONDITIONAL`, the Planner MUST state the condition that makes browser validation necessary.

If that condition is satisfied by the implementation or acceptance criteria, browser evidence becomes REQUIRED. Otherwise the Builder MAY skip it, but MUST record why the condition did not apply.

## BROWSER_NOT_REQUIRED

Browser/runtime validation is NOT REQUIRED for changes whose acceptance can be fully established without a rendered human surface, for example:

- isolated backend/domain logic;
- infrastructure/IaC with no browser-facing acceptance criterion;
- deterministic integration adapters;
- internal refactors with no observable surface change;
- documentation-only changes;
- pure data migrations validated by project-approved migration checks.

This classification does not waive other required validation.

## Evidence rules

A Builder Report MUST distinguish:

```text
browser_validation: executed | skipped_not_required | skipped_condition_not_met | blocked
classification: BROWSER_REQUIRED | BROWSER_CONDITIONAL | BROWSER_NOT_REQUIRED
```

When executed, record enough evidence for a Reviewer to reproduce or inspect the result.

When `BROWSER_REQUIRED` is blocked by an unavailable capability/environment, the task cannot claim complete validation. Record the blocker; do not silently downgrade the requirement.

## Reviewer rule

If `BROWSER_REQUIRED` applies and browser/runtime evidence is absent, the Reviewer MUST return:

```text
REVIEW_EVIDENCE_INCOMPLETE
```

with an `EVIDENCE_FINDING` identifying the missing browser evidence.

If `BROWSER_CONDITIONAL` was skipped, the Reviewer verifies the Builder's stated condition and rationale. If the condition actually applied, the evidence is incomplete.

## FinOps rule

Browser validation does not require an LLM merely to drive deterministic checks.

Prefer ordinary browser automation/test tooling for repeatable validation. Use model reasoning only where interpretation is materially needed.

Do not generate redundant screenshots or rerun broad browser suites when a bounded scenario proves the acceptance criteria. Evidence should be sufficient, not maximal.

## Relationship to Design Approval

For an `INTERFACE_CHANGE`:

```text
Approved Design Artifact
        ↓
Planning / Build
        ↓
Rendered Browser Validation
        ↓
Reviewer
        ↓
Human Gate
```

The Reviewer compares implementation evidence against the approved revision when one is required. Browser evidence proves implementation fidelity; it does not authorize a new visual decision that was never approved.
