# Design Approval Package — {{feature-id}} {{surface name}}

Classification: INTERFACE_CHANGE  
Revision: {{n}}  
Status: {{Draft | Awaiting approval | Approved | Superseded by revision n+1}}  
Date: {{yyyy-mm-dd}}  
Produced by: {{agent or person}}

> Governed by `workflows/design-approval.md`. This artifact is evidence for a human gate. It is
> not implementation and must not be copied into application code.

## Approval record

| Field | Value |
| --- | --- |
| What was approved | {{visual / copy / both / nothing yet}} |
| Approved by | {{person}} |
| Date | {{yyyy-mm-dd}} |
| Revision approved | {{n}} |
| Explicitly **not** approved | {{list — anything left open stays a decision}} |

Approval of this revision is not approval of a later one. A materially changed package is a new
revision and needs its own record.

## Artifact

| File | What it is |
| --- | --- |
| {{artifact}} | Self-contained rendering. Opens without the project build, toolchain, or network. |
| {{capture}} | Frozen capture of what was rendered. This is what the approval refers to. |

## Surfaces and states included

List every state in the package, and every state deliberately left out with its reason. A state
that is neither included nor excluded is an omission.

| Surface | State | In package |
| --- | --- | --- |
| {{surface}} | success | {{yes/no}} |
| {{surface}} | empty | {{yes/no}} |
| {{surface}} | error / service unavailable | {{yes/no}} |
| {{surface}} | unauthorized | {{yes/no}} |
| {{surface}} | loading | {{yes/no}} |

## Provenance of visual values

Every color, type choice, spacing rule, and asset either cites the project's design system or is
declared new — and a new value is part of what is being approved.

| Value | Source | New? |
| --- | --- | --- |
| {{token or asset}} | {{design system location}} | {{no / yes — being decided here}} |

Design system referenced: {{location declared in the Project Context}}, read on {{date}}.
If this package and that source diverge, the source wins and this package is stale.

## Delivered vs reserved

| Element | This feature | Reserved for | Becomes real when |
| --- | --- | --- | --- |
| {{element}} | delivers | — | — |
| {{element}} | draws space only | {{feature id}} | {{explicit condition}} |

Reserved elements must be visually distinguished in the artifact. State how a reserved element
behaves before it is real — hidden, absent, or inert — because shipping an inert control is a
defect, not a placeholder.

## Decisions this package carries

Design choices being decided by approving this artifact, each with its reason. These are the
substance of the gate; without them the approver is judging taste rather than deciding.

- {{decision and why}}

## Open questions

Everything the package does **not** settle. Anything left here remains an open decision after
approval and must not be resolved by an agent during implementation.

- {{question}}

## Notes for the implementer

- What in this artifact is intentional and must be preserved.
- What is illustrative — sample data, placeholder names, example content — and must not be
  treated as specification.
- Constraints the artifact cannot show: accessibility, focus order, keyboard behavior,
  internationalization, motion.
