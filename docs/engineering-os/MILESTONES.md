# Engineering OS Milestones

The Engineering OS is built in phases. Each milestone adds a layer of capability without weakening prior layers.

## M1: Global Governance Foundation ✓

**Goal:** Establish vendor-neutral global context that all harnesses consume identically.

**Includes:**
- `core/principles/` — Architecture principles, engineering standards
- `core/guardrails/` — Production, database, infrastructure, git constraints
- `core/definition-of-done.md` — Global acceptance criteria
- `agents/` — Planner, Builder, Reviewer contracts
- `workflows/feature.md` and `workflows/execution.md` — Portable task and execution model
- `adapters/` — Bootstrap documents for Claude Code and Codex (initially)
- `templates/` — Canonical work artifact templates

**Explicitly Out of Scope:** Orchestration, model routing, worktrees, parallel agents, observability, FinOps.

**Constraint:** Adapters bootstrap harnesses but do not select or route work. Humans choose which harness to use.

## M2-M6: Foundation Hardening (Future)

**Anticipated capabilities:**
- Pinned mirrors in consumer projects (distribution)
- Multi-vendor adapter coverage (Copilot, Gemini, Qwen, etc.)
- Extended agent capabilities (specialist agents)
- Task complexity and dependency patterns
- Evidence collection and audit trails
- Integration patterns with external systems

*Note: M2-M6 are currently planned but not yet detailed. They will be added as Engineering OS matures in use.*

## M7: Biah CLI + Vendor-Neutral Multi-Agent Execution ← Next Priority

**Goal:** Single orchestrator that routes work across Claude, Codex, Copilot, and future vendors without vendor lock-in.

**Includes:**

### Biah as Unified Orchestrator
```
biah task HC-006        # Accept a task
biah plan HC-006        # See execution plan
biah run HC-006         # Execute with router
biah review HC-006      # Collect evidence
biah status             # Monitor execution
```

### Capability-Based Routing (Not Vendor Preference)
```yaml
workers:
  claude:
    capabilities:
      - architecture_reasoning
      - large_context
      - refactoring
  
  codex:
    capabilities:
      - implementation
      - debugging
      - testing
  
  copilot:
    capabilities:
      - implementation
      - github_native
```

Task declares requirements:
```yaml
requires:
  - implementation
  - testing
```

Router automatically matches. Tomorrow, replace Codex with Gemini Code without changing the task.

### Parallel Worktree Execution
- Each task gets isolated worktree
- Dependencies declared upfront (DAG)
- Truly parallel execution for independent tasks
- Each worker produces fixed-format BUILD REPORT
- Evidence collected and unified for review

### Multi-Vendor Adapter Layer
- `adapters/claude/` → invokes Claude CLI programmatically
- `adapters/codex/` → invokes Codex CLI programmatically
- `adapters/copilot/` → invokes Copilot CLI programmatically
- Future: `adapters/gemini/`, `adapters/qwen/`, etc.

Each adapter is a thin bridge—not the source of rules.

### Human Gates Across All Workers
- HUMAN_GATE before execution (review plan)
- HUMAN_GATE after execution (review evidence)
- No harness can bypass gates
- Gates are identical across all workers

### Structured Evidence and Quality Gates
- All workers produce `BUILD REPORT` (fixed format)
- Unified evidence package from all workers
- Quality gates (lint, type-check, tests) run before approval
- Verification of harness parity (evidence should be comparable)

### M7 Execution Flow

```
$ biah task HC-006

Planning...
✓ Context loaded (PRD, FDD, ADRs, repo state)
✓ Architecture constraints loaded
✓ Task contract validated

Building DAG:
HC-006-A  schema       (depends: none)
HC-006-B  backend      (depends: HC-006-A)
HC-006-C  frontend     (depends: HC-006-B)
HC-006-D  review       (depends: HC-006-B, HC-006-C)

Routing by capability:
HC-006-A  schema       → codex (implementation)
HC-006-B  backend      → codex (implementation, testing)
HC-006-C  frontend     → copilot (implementation, github_native)
HC-006-D  review       → claude (architecture_reasoning)

Create worktrees? [y/n]
y

[✓] PLAN
[✓] WORKTREE
[✓] SCHEMA     codex
[●] BACKEND    codex
[  ] FRONTEND  copilot
[  ] REVIEW    claude
[  ] QUALITY
[  ] HUMAN_GATE

← monitoring parallel execution →

[✓] BACKEND    codex    (5m 23s, 4 files changed)
[●] FRONTEND   copilot  (building...)
[  ] REVIEW    claude   (waiting for dependencies)

← frontend completes →

[✓] FRONTEND   copilot  (3m 12s, 8 files changed)
[●] REVIEW     claude   (building...)

← review completes →

[✓] REVIEW     claude   (2m 55s, architecture approved)
[●] QUALITY    (running lint, type-check, tests)

← quality gates pass →

[✓] QUALITY

=== EVIDENCE PACKAGE ===

HC-006-A BUILD REPORT (schema)
  Status: BUILD_COMPLETE
  Files: migrations/001_create_schema.sql
  Validation executed: none
  Validation skipped: none
  Assumptions: PostgreSQL 14+
  Risks: none
  Decisions: none

HC-006-B BUILD REPORT (backend)
  Status: BUILD_COMPLETE
  Files: src/models/user.ts, src/services/auth.ts, tests/auth.test.ts
  Validation executed: unit tests (4/4 passed), linting (0 issues)
  Validation skipped: none
  Assumptions: NestJS 9+
  Risks: none
  Decisions: none

HC-006-C BUILD REPORT (frontend)
  Status: BUILD_COMPLETE
  Files: app/dashboard/page.tsx, app/components/AuthWidget.tsx
  Validation executed: type-check (0 errors), linting (0 issues)
  Validation skipped: none
  Assumptions: Next.js 13+, React 18+
  Risks: none
  Decisions: none

HC-006-D BUILD REPORT (review)
  Status: BUILD_COMPLETE
  Files changed: none
  Validation executed: architecture review, parity validation
  Validation skipped: none
  Assumptions: Design matches approved ADR-005
  Risks: none
  Decisions: none

=== HUMAN GATE ===

Ready to merge?
- All workers produced evidence ✓
- Harness parity validated ✓
- Quality gates passed ✓
- Architecture constraints respected ✓
- No approval gates remain ✓

[y/n] y

✓ Evidence package filed
✓ Ready for merge
```

## Advantages of M7

### 1. No Vendor Lock-In
- Claude, Codex, Copilot, or future vendors—Biah treats them as workers
- A capability-matched worker from a new vendor replaces its predecessor
- No rewrite of contracts, workflows, or core rules needed

### 2. True Multi-Vendor Parallelism
- Independent tasks run on different vendors simultaneously
- Dependencies are declared upfront (no surprises)
- Each worker produces comparable evidence

### 3. Harness Parity
- Same Core rules govern all workers
- Same BUILD REPORT format from every vendor
- Reviewer validates that evidence is equivalent
- "Which vendor did this?" becomes an implementation detail

### 4. Future-Proof
- New vendors: add adapter + register capabilities
- New capabilities: register, add to worker registry
- New requirements: add to Core (affects all workers equally)

### 5. Product Identity
- "I use Biah" instead of "I use Claude Code" or "I use Codex"
- Biah becomes the OS; workers are interchangeable compute
- Single entry point, familiar CLI, consistent experience

## Roadmap to M7

### Phase 1: Plan and Validate (Current)
- [ ] Document M7 architecture in workflows/
- [ ] Update adapters/README.md with M7 context
- [ ] Clarify `.github/copilot-instructions.md` as M7-aware

### Phase 2: Prototype Biah (Minimal)
- [ ] Biah CLI skeleton (entry point + help)
- [ ] Task loading and contract validation
- [ ] Planner invocation and DAG construction
- [ ] Router (capability matching)

### Phase 3: Worker Adapters
- [ ] Claude adapter (programmatic invocation)
- [ ] Codex adapter (programmatic invocation)
- [ ] Copilot adapter (programmatic invocation)
- [ ] Worktree creation and isolation

### Phase 4: Execution and Evidence
- [ ] Execute tasks in parallel with dependency ordering
- [ ] Collect BUILD REPORTs from all workers
- [ ] Evidence package creation
- [ ] Human gate workflow

### Phase 5: Observability (Nice-to-Have)
- [ ] Biah Portal (task status, worker performance, costs)
- [ ] Real-time execution monitoring
- [ ] Historical analytics

## How M7 Changes Current Usage

### Before (M1 — Today)
```
You pick: Claude Code
    ↓
You use Claude's agents
    ↓
You get Claude-based results
```

### After (M7 — Future)
```
You pick: Biah
    ↓
Biah picks workers based on task requirements
    ↓
You get optimal results + freedom to swap vendors
```

## Keeping M1-M6 Stable

M7 is an orchestration layer **on top of** M1-M6, not a rewrite. The Core, contracts, and workflows from M1 remain unchanged and binding.

In fact, M7 **depends on** M1-M6:
- M7 reads `.github/copilot-instructions.md` and project contracts (M1)
- M7 invokes Planner, Builder, Reviewer per their contracts (M1)
- M7 enforces Definition of Done and human gates (M1)
- M7 validates harness parity per `workflows/execution.md` (M1)

M7 adds the orchestration layer that M1 explicitly excluded. Both are needed for the full vision.
