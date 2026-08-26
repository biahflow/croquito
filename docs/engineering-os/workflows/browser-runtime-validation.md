# Browser and Runtime Validation

## Purpose

Define when rendered/browser evidence is required after implementation. This complements `design-approval.md`: Design Approval decides what may be built before planning; browser/runtime validation proves what was actually built after implementation.

## Classification

Every Task Contract MUST declare one validation class when user-visible behavior may be affected:

```text
BROWSER_REQUIRED
BROWSER_CONDITIONAL
BROWSER_NOT_REQUIRED
```

### BROWSER_REQUIRED

Use when the task creates or materially changes a human-perceivable browser surface, including layout, navigation, visual identity, design-system primitives, form behavior, loading/error/empty/unauthorized states, responsive behavior, or browser-visible accessibility behavior.

Required evidence SHOULD include:

- the real application rendered in a browser or equivalent production-like runtime;
- the routes/states exercised;
- frozen evidence such as screenshots when practical;
- functional interaction evidence for changed behavior;
- accessibility checks when applicable;
- viewport/responsive coverage when acceptance criteria depend on it.

For `INTERFACE_CHANGE`, `BROWSER_REQUIRED` is the default unless the Task Contract documents a concrete reason the browser is not the relevant runtime.

### BROWSER_CONDITIONAL

Use when a backend/configuration change may project into an existing UI but the UI is not itself being changed.

Browser validation becomes required when an acceptance criterion depends on the rendered projection. If it does not, the Builder may report browser validation as not executed with a reason and the Reviewer evaluates whether that leaves evidence incomplete.

### BROWSER_NOT_REQUIRED

Use for changes whose acceptance criteria are completely satisfied by non-browser evidence, such as isolated backend services, libraries, migrations, deterministic integrations, or documentation-only changes with no rendered-product requirement.

## Task Contract requirement

The Task Contract SHOULD state the selected class and concrete validation requirements. The harness MUST NOT invent browser work merely because browser tooling is available.

Example:

```text
Validation class: BROWSER_REQUIRED
Required evidence:
- render /settings and /dashboard
- verify light/dark tokens and semantic states
- capture desktop and mobile screenshots
- verify keyboard focus for changed controls
```

## Builder behavior

When `BROWSER_REQUIRED`, the Builder MUST execute browser/runtime validation before declaring `BUILD_COMPLETE`. If required browser execution is unavailable, the Builder reports the limitation and the task remains validation-incomplete; it must not be presented as fully ready for review.

When `BROWSER_CONDITIONAL`, the Builder records whether browser validation was executed and why.

When `BROWSER_NOT_REQUIRED`, the Builder does not spend time or model context on browser validation unless new evidence changes the classification.

## Reviewer behavior

The Reviewer MUST return `REVIEW_EVIDENCE_INCOMPLETE` when:

- browser/runtime evidence is required by the Task Contract and absent;
- an `INTERFACE_CHANGE` was built without required rendered evidence;
- screenshots or claims refer to a different revision than the code under review;
- the evidence omits a user-visible state required by acceptance criteria.

The Reviewer MUST NOT substitute its own visual preference for an approved Design Approval Package.

## FinOps rule

Browser automation is deterministic validation. It SHOULD use ordinary browser/E2E tooling and MUST NOT invoke an LLM merely to click, capture screenshots, compare deterministic states, or serialize results.

Use model reasoning only when interpretation is materially required.
