# Design Approval

## Purpose and authority

This workflow defines when work that produces a human-perceivable surface requires an approved
visual artifact before it may be planned, and what that artifact must contain. It is
vendor-neutral and project-neutral.

It does **not** define a design system, a visual language, a tool, or a file format. Those are
project property and are owned by the Project Context. This workflow defines a gate and an
evidence requirement, nothing more.

## The problem this solves

Written acceptance criteria under-specify visual work. Two competent implementations of the same
criteria can look nothing alike, and only one of them is acceptable to the person who asked. A
Feature Contract can be complete, internally consistent, correctly scoped — and still describe a
screen the human would reject on sight.

Build effort on a user-visible surface is cheap to discard only before it exists. After it
exists, discarding it costs the implementation, the tests written against it, the evidence
produced for it, and the review that passed it. This gate moves the disagreement to the point
where changing your mind is cheap.

It is not a design process. It is a mechanism for making rejection cheap.

## Classification

Whoever writes the Feature Contract declares one classification:

```text
INTERFACE_CHANGE      creates or materially alters a human-perceivable surface
COPY_CHANGE           alters wording only, with no structural or visual change
NO_INTERFACE_CHANGE   no perceivable difference to any human surface
```

`INTERFACE_CHANGE` covers more than screens: layouts, navigation, emails, generated documents
and exports, printed output, and command-line output where presentation is the deliverable. It
covers error, empty, loading, and unauthorized states — those are surfaces a human perceives,
and they are the ones most often discovered late.

Classifying an `INTERFACE_CHANGE` as anything else is an evidence defect, not a judgment call.

## Position in the lifecycle

```text
FEATURE SPECIFICATION
        ↓
DESIGN APPROVAL          (required when INTERFACE_CHANGE)
        ↓
READY_FOR_PLANNING
```

The gate sits **before planning**, not before building. A plan that decomposes an unapproved
surface produces tasks that must be re-cut when the design changes, and a Planner asked to
decompose an undecided surface will either invent the design or stall. Both are failures the
gate prevents.

A feature may be split so that non-interface work proceeds while the gate is open. Splitting is
a decision, and it must be recorded as one — not performed silently by starting the "obvious"
part.

## The Design Approval Package

Create the package from [the global template](../templates/design-approval.md). The package is
one artifact plus its record. It must contain:

1. **A self-contained rendering.** It must open without the project's build, toolchain, or
   network. Whoever approves must not have to run anything.
2. **Fixed evidence of what was rendered.** Images or an equivalent frozen capture, alongside
   the source. A rendering depends on fonts, browser, and platform; the frozen capture is what
   the approval actually refers to.
3. **The states, not only the success path.** At minimum the states the feature declares:
   empty, error, unauthorized, loading, and any state the surface can reach.
4. **Provenance of every visual value.** Each color, type choice, spacing rule, and asset must
   cite where it came from in the project's design system, or be marked explicitly as new and
   therefore as part of what is being approved.
5. **An explicit boundary between delivered and reserved.** What this feature builds, versus
   what is drawn to hold space for future work. Reserved elements must be visually distinguished
   and must state the condition under which they become real.
6. **A statement of what approval does not cover.** Approval is scoped; anything outside the
   scope stays an open decision and must be named.

## Approval is scoped, dated, and revisioned

An approval record states **what** was approved, **which revision**, and **when**. Visual
approval is not copy approval; copy approval is not visual approval. Approval of revision N is
not approval of revision N+1: a materially changed package is a new revision and needs its own
approval, in the same way that a materially updated Review Evidence Package begins a new review
round.

## Evidence requirement

The approved package is versioned alongside the Feature Contract and is reachable from the
execution environment of any agent that will build the surface, per the Execution artifacts
requirement in `core/definition-of-done.md`.

A Feature Contract that claims design approval without a reachable artifact is an incomplete
handoff. A description of an approved design never substitutes for the approved design — the
same rule that forbids a summary from replacing source evidence.

## Agent authority

```text
PRODUCE_DESIGN_ARTIFACT    allowed
REVISE_DESIGN_ARTIFACT     allowed
RECORD_APPROVAL            allowed, transcribing an explicit human decision
APPROVE_DESIGN             forbidden
```

No agent approves a design, including a design it did not produce. An agent that produced a
package must state which parts are its proposal rather than the project's established language,
so the human knows what is actually being decided.

## Project responsibility

The project owns its design system and declares in the Project Context where it lives. The
package cites it; this workflow does not define it.

Absence of a documented design system does not exempt a project from this gate. It makes the
gate more necessary, because every visual value in the package is then a new decision. A project
in that position should expect its first approved package to establish language that later
packages cite — and should extract that language into a document rather than leave it in the
artifact.

## Anti-patterns

- **Approving a description instead of an artifact.** "A clean login screen with the logo" is
  not an approved design; it is the ambiguity that caused the rework.
- **A mock that is also the implementation.** The package is evidence, not source. Code copied
  out of a mock arrives without tests, accessibility, or state handling, and carries the mock's
  shortcuts into the product.
- **Approval without revision identity.** An approval that does not name what it approved cannot
  be checked later and will be re-litigated.
- **Building the surface while the gate is open**, on the assumption that approval is a
  formality.
- **Treating copy as approved because the visual was.** Wording is the part humans change most
  and the part agents most often invent.
- **Letting the package drift from the design system it cited.** When they diverge, the design
  system wins and the package is stale.

## Conceptual check

- Is the classification declared, and is it the honest one?
- Can the approver open the artifact without running anything?
- Are the failure and empty states in the package, or only the happy path?
- Does every visual value cite the design system, or is it marked as new?
- Does the approval record say what was approved, which revision, and when?
- Is the artifact reachable by the agent that will build it?
- Is anything being built right now that this approval could invalidate?
