# Project Adoption and Migration

## Purpose and authority

Global standards define the target operating model. Existing repositories are migrated explicitly, never implicitly.

```text
GLOBAL STANDARD → defines target
LEGACY PROJECT → must be inspected
MIGRATION PLAN → must be approved
ONLY THEN → project changes
```

This workflow defines a vendor-neutral, project-neutral adoption process. It does not authorize automatic migration, an executable state machine, an adoption agent, or changes to any repository merely because it differs from the current standard.

```text
DISCOVER
   ↓
CLASSIFY
   ↓
GAP ANALYSIS
   ↓
MIGRATION PLAN
   ↓
HUMAN APPROVAL
   ↓
MIGRATE
   ↓
VALIDATE
   ↓
ENGINEERING_OS_COMPLIANT
```

## Adoption states

| State | Meaning |
| --- | --- |
| `LEGACY` | The repository has not yet been validated against the adopted Engineering OS standard. |
| `ADOPTION_IN_PROGRESS` | An adoption assessment or, after approval, a migration is under way. |
| `ENGINEERING_OS_COMPLIANT` | The repository has been validated against its currently adopted Engineering OS standard. |
| `ADOPTION_BLOCKED` | A human decision, source-of-truth conflict, or other material conflict prevents progress. |

`ENGINEERING_OS_COMPLIANT` does not mean zero technical debt, warnings, bugs, or architectural imperfections. It means the project has sufficient operating structure and contracts for predictable Engineering OS use: global and project context are known, work intake and sources of truth are unambiguous, validation commands and human gates are known, and adapters do not contradict the Core.

`READY_FOR_HUMAN_APPROVAL` is an adoption checkpoint, not a separate adoption state. Discovery, classification, reporting, and migration planning may occur read-only during adoption, but they never authorize project changes.

## Discover

Discovery is preferably read-only and proportionate. Start with repository-root files, relevant Git metadata, documentation, manifests, configuration, and known directories. Expand only when evidence requires it; do not indiscriminately read large or irrelevant files.

Inspect, when present:

- repository structure, Git status, and relevant history;
- README, agent adapters, project instructions, and documentation;
- roadmap, status, TODO, planning, backlog, feature, requirements, and decision artifacts;
- architecture documents, ADRs, PRD, RF/NFR, and historical notes;
- test, build, package-manager, CI/CD, infrastructure, and validation configuration.

Search semantic variants such as `roadmap.md`, `docs/roadmap.md`, `planning.md`, `backlog.md`, `tasks.md`, `features.md`, `status.md`, `TODO.md`, and `TODOs.md`. A filename is not a classification; inspect its content and observed use first.

## Classify and identify authority

Classify artifacts by their observed responsibility:

```text
PRODUCT_ROADMAP
FEATURE_SPECIFICATION
TASK_BACKLOG
PROJECT_STATUS
PROJECT_CONTEXT
ARCHITECTURE
ARCHITECTURE_DECISION
REQUIREMENTS
VALIDATION_CONFIG
CI_CD
TECHNICAL_DEBT
HISTORICAL_NOTE
UNKNOWN
```

An artifact may be `MIXED_RESPONSIBILITIES`. Record its sections and their conceptual destinations; do not split, move, rename, or rewrite it during discovery.

Determine the real current source for backlog, feature definition, project state, architectural decisions, and validation commands. Do not assume that an artifact named `ROADMAP.md` is authoritative.

When sources disagree, record `SOURCE_OF_TRUTH_CONFLICT` rather than silently selecting one:

```text
artifact_a: <value>
artifact_b: <value>
conflicting_information: <value>
impact: <value>
human_decision_required: <value>
```

The conflict may block migration of the affected information. Discovery represents the observed state, not the desired state.

Unknown-origin or unclear-intent files are `PREEXISTING_USER_ARTIFACT`. They must not be deleted, overwritten, moved, added to Git, ignored, stashed, or renamed automatically.

## Gap analysis and Adoption Report

Before any project modification, create an `ENGINEERING OS ADOPTION REPORT` using [the global template](../templates/project-adoption-report.md). Evaluate at least:

```text
Global Context
Project Context
Agent Adapters
Canonical Roadmap
Feature Lifecycle
Feature Specifications
Planner Compatibility
Validation Profiles
Architecture Documentation
ADRs / Decisions
Definition of Done compatibility
Human Gates
Git hygiene
Source-of-truth consistency
```

Use only `PASS`, `PARTIAL`, `FAIL`, `NOT_APPLICABLE`, or `UNKNOWN`. Do not create an artificial compliance score.

Each finding must contain:

```text
id: <value>
category: <value>
severity: BLOCKER | HIGH | MEDIUM | LOW | INFO
current_state: <value>
target_state: <value>
evidence: <value>
impact: <value>
recommended_direction: <value>
human_decision_required: <value>
```

Severity communicates material risk; it must not dramatize cosmetic differences.

## Migration plan and approval

Produce a `PROJECT ADOPTION PLAN` from the report before changing the project:

```text
PROJECT ADOPTION PLAN

repository: <value>
current_state: <value>
target_state: <value>

steps:
  - id: M01
    action: KEEP | CREATE | MOVE | RENAME | MERGE | SPLIT | REFERENCE | DEPRECATE | DELETE_CANDIDATE | HUMAN_DECISION
    source: <value>
    destination: <value>
    reason: <value>
    risk: <value>
    human_gate: <value>
    validation: <value>

dependencies: <value>
expected_result: <value>
```

Plans must be incremental: each small, auditable migration step has its own validation. `DELETE_CANDIDATE` is never deletion authority. Preserve repository history and provenance where practical when moving documentation.

The required handoff is:

```text
DISCOVER → REPORT → MIGRATION PLAN → READY_FOR_HUMAN_APPROVAL
```

In an Adoption Report, `READY_FOR_MIGRATION` means the report and plan are ready to be submitted for human approval; it is not authorization to modify the repository.

Only explicit human approval authorizes project changes. It does not authorize an agent to expand an approved migration plan.

## Migration rules

Apply only the approved plan. Do not silently broaden scope. Record any new condition as:

```text
MIGRATION_DEVIATION

planned: <value>
actual: <value>
reason: <value>
impact: <value>
human_decision_required: <value>
```

Prefer focused, semantically distinct commits when a migration is authorized. Do not create a single opaque rewrite when independent steps can be reviewed separately.

For work-intake artifacts, follow [the Feature Lifecycle and Work Intake workflow](feature.md): identify the true backlog source first; preserve IDs, priorities, historical context, dependencies, status, and references; then propose any consolidation. Do not transform technical tasks into product features automatically.

`STATUS.md` may become a `DERIVED_STATUS_VIEW` only after its canonical responsibilities and historical information have been preserved elsewhere. Existing Project Context, architecture, commands, and adapters should be referenced or adapted before new copies are created. Validation profiles must be recorded as `KNOWN`, `UNKNOWN`, or `NOT_APPLICABLE`; never invent commands.

## Validate and classify compliance

After migration, repeat the adoption analysis and compare `BEFORE → AFTER`. When applicable, verify that Global Context and Project Context are visible, the roadmap and Feature Contracts are discoverable, validation commands are available, and human gates are visible.

A project can be `ENGINEERING_OS_COMPLIANT` only when all of the following hold:

1. Global Context is operational.
2. Project Context is identified.
3. Adapters do not contradict the Core.
4. The canonical source of planned work is clear.
5. `ROADMAP.md` or a documented equivalent is defined.
6. The feature lifecycle is comprehensible.
7. Executable features have sufficient Feature Contracts.
8. The Planner can find its inputs.
9. Applicable validation profiles are known.
10. Human gates are preserved.
11. No critical source-of-truth conflict remains.
12. Unknown user artifacts were preserved.

Old backlog items may remain `BACKLOG` or `READY_FOR_SPEC`; compliance does not require retroactively completing every Feature Contract.

An explicit Project Context exception, such as a documented alternative roadmap location, may be compliant. Semantic consistency matters more than cosmetic filesystem uniformity. If a future Engineering OS change is incompatible with an adopted standard, perform a new compliance check; this workflow defines no versioning engine.

## Distribution and pinning

Adoption is not complete while the global layer is reachable only from the operator's
machine. A compliant project makes the layer reachable from its own checkout — the
recommended mechanism is the complete pinned mirror described in
[`adapters/README.md`](../adapters/README.md): full copy, provenance record naming the
source commit, deliberate reviewed resynchronization. References from project documents to
global rules should point at the mirror, so the project's own documentation gates validate
them; a textual mention of a global document that no link can reach is dead text, not a
reference.

## Global and project responsibilities

Global Engineering OS defines adoption process, target semantics, compliance criteria, migration safety, and human gates. The project supplies its actual files, architecture, commands, roadmap, history, and documented exceptions. Do not move project-specific knowledge into the Global layer.

## Anti-patterns

- **Automatic Rewrite:** reorganizing a repository merely because it differs from the standard.
- **Blind Rename:** renaming a roadmap artifact without checking semantics or references.
- **Destructive Cleanup:** deleting old TODO, status, or documentation because it appears redundant.
- **Invented Specification:** adding acceptance criteria that are not evidenced.
- **Dual Source of Truth:** introducing a new canonical roadmap while another remains active.
- **Cosmetic Compliance:** renaming directories without improving operational clarity.
- **Agent-Owned Product Priority:** allowing an agent to choose which legacy feature comes first.

## Conceptual check

For a hypothetical repository containing `README.md`, `STATUS.md`, `TODO.md`, `docs/roadmap.md`, and `docs/architecture.md`, where status mixes progress and backlog, TODO mixes bugs and debt, and the roadmap is partly stale, the correct initial result is:

```text
LEGACY → DISCOVER → CLASSIFY → SOURCE_OF_TRUTH_CONFLICT
→ ADOPTION REPORT → MIGRATION PLAN → READY_FOR_HUMAN_APPROVAL
```

No project file changes occur during that sequence.
