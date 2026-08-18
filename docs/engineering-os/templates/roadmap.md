# Roadmap

Governed by `workflows/feature.md` (see "Roadmap and status"). This index is a discovery view,
not the source of truth for a feature's lifecycle status once a Feature Contract exists.

For an entry with a `Feature Contract` link, that `feature.md` is the canonical record of the
feature's lifecycle status — this row must stay a synchronized view of it, not an independent
claim. For an entry with no `Feature Contract` yet, this row is itself the canonical record of
its pre-specification status.

Use only the lifecycle states defined in `workflows/feature.md`: `BACKLOG`, `READY_FOR_SPEC`,
`SPEC_IN_PROGRESS`, `READY_FOR_PLANNING`, `PLANNING`, `READY_FOR_BUILD`, `IN_PROGRESS`,
`READY_FOR_REVIEW`, `READY_FOR_HUMAN_REVIEW`, `DONE`, `BLOCKED`, `CANCELLED`. Do not invent a new
state here.

| ID | Item | Priority | Status | Feature Contract | Source |
| --- | --- | --- | --- | --- | --- |
| {{F-001}} | {{short item name}} | {{project-defined priority}} | {{lifecycle state}} | {{link to feature.md, or "—" when none yet}} | {{where this item came from — request, incident, decision}} |

Keep each row brief: a stable ID, priority, current lifecycle status, and a link to the Feature
Contract when one exists. Do not duplicate the full technical specification here — that belongs
in `feature.md`.
