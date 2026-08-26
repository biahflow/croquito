# Engineering OS: Multi-Vendor Multi-Agent Execution Layer

## Repository Purpose

Engineering OS is a **vendor-neutral orchestration framework** for AI-assisted software delivery. It is **not** a tool for choosing between Claude Code, Codex, or Copilot.

Instead, it defines:

- **Global governance** — Engineering standards, approval boundaries, and agent contracts
- **Portable task contracts** — Tasks that execute identically regardless of which AI worker handles them
- **Routing and execution** — Rules for distributing work across Claude, Codex, Copilot, or future vendors
- **Evidence and gates** — Structured validation and human-approval requirements

This repository contains documentation, contracts, bootstrap adapters, and execution workflows. The actual orchestration happens via **Biah CLI** (currently in planning; this repo is the foundation).

## Architecture: The Biah Model

The goal is **vendor-neutral multi-agent execution**:

```
               YOU
                │
                ▼
      ┌─────────────────────┐
      │   BIAH CLI          │  ← Single entry point (orchestrator)
      │  (Engineering OS)   │
      └─────────┬───────────┘
                │
         Planner / Router
                │
      ┌─────────┼──────────┐
      ▼         ▼          ▼
    CLAUDE    CODEX     COPILOT     ← Workers (parallel, isolated worktrees)
      │         │          │
      └─────────┼──────────┘
                ▼
            REVIEW
                │
                ▼
           HUMAN GATE
```

**Key principle:** You never start Claude Code, Codex Desktop, or Copilot CLI directly. You use **Biah**, which routes work to the appropriate worker based on task requirements, not your preference.

### Directory Structure and Purpose

| Directory | Purpose |
|-----------|---------|
| `core/` | Global engineering principles, guardrails, and the definition of done that all work must satisfy |
| `agents/` | Role contracts for Planner, Builder, and Reviewer agents—defines capabilities, responsibilities, and required report formats |
| `adapters/` | CLI bridges for each vendor (Claude, Codex, Copilot)—enable Biah to invoke each vendor's CLI programmatically |
| `workflows/` | Vendor-neutral lifecycle conventions for work intake, execution, and delivery |
| `templates/` | Reusable starting points for canonical work artifacts (design approvals, evidence packages) |
| `scripts/` | Operator utilities, including `install-adapters.sh` (currently for bootstrapping harnesses; will evolve for Biah) |

## Key Concepts and Conventions

### 1. Adapters Are Worker Bridges, Not Harness Choices

The `adapters/` directory contains CLI bridges for each vendor:

- `adapters/claude/` — Invokes Claude CLI programmatically
- `adapters/codex/` — Invokes Codex CLI programmatically  
- `adapters/copilot/` — Invokes Copilot CLI programmatically

**Do NOT confuse adapters with harness selection.** They are not options for you to choose. They are how Biah reaches each worker.

Future adapters (Gemini CLI, Qwen, OpenCode, etc.) will follow the same pattern—without changing Engineering OS.

### 2. Capability-Based Routing (Not Vendor Preference)

Biah routes tasks based on **required capabilities**, not hardcoded preferences:

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
      - code_review

  copilot:
    capabilities:
      - implementation
      - github_native
      - repository_operations
```

A task declares what it needs:

```yaml
task:
  id: HC-006-backend
  requires:
    - implementation
    - testing
```

Biah matches. Tomorrow, a new worker with better `implementation` capability replaces Codex automatically.

### 3. Rule Resolution Hierarchy

Rules cascade from most general to most specific:

```
Global Core → Project Instructions → Task Contract
```

Each layer may add constraints but cannot weaken guardrails from higher levels.

The Core rules (in `core/`) are **binding on all workers**. An adapter to a new vendor must still respect them.

### 4. Task Portability and Harness Parity

A task is portable between workers only when:

- **Self-contained:** Goal, scope, acceptance criteria, dependencies, and sources to read are all in the task contract
- **Commands are real:** Validation profiles use actual project commands, not invented ones
- **Baseline is declared:** The executor knows which failures already exist
- **Scope is bounded in files:** Boundaries are explicit; "avoid fixing problem X" is stated, not assumed
- **Gates are named:** Approval gates and required human decisions are in the contract
- **Report format is fixed:** Builder tasks require the complete `BUILD REPORT` structure defined in `agents/builder.md`

If any of these are missing, the task is `TASK_CONTRACT_NOT_PORTABLE` and Biah will not dispatch it.

### 5. Agent Roles and Contracts

Three agent roles define execution in any worker:

- **Planner** (`agents/planner.md`): Breaks work into tasks, identifies dependencies, creates portable task contracts. Does not select workers (Biah's router does).
- **Builder** (`agents/builder.md`): Implements one bounded task in an isolated worktree, establishes validation baselines, runs applicable profiles, and produces a complete `BUILD REPORT` with fixed format. The report is identical regardless of which worker executes it.
- **Reviewer** (`agents/reviewer.md`): Evaluates evidence from all Builders, verifies acceptance criteria, validates that all workers respected the Core, and determines if approval gates are satisfied.

### 6. Execution Model: Parallel Worktrees

When Biah executes:

```
biah task HC-006
```

It:

1. Loads context (PRD, FDD, ADRs, task contract, repo state)
2. Invokes Planner → produces DAG with dependencies
3. Invokes Router → matches tasks to workers by capability
4. Creates isolated worktrees for each parallel task
5. Invokes each worker's CLI adapter in its worktree
6. Collects BUILD REPORTS from all workers
7. Invokes Reviewer against all evidence
8. Stops at HUMAN_GATE if required
9. Produces final evidence package

Each worker:
- Operates in its own worktree
- Cannot see other workers' work
- Produces a `BUILD REPORT` (fixed format)
- Stops at approval gates

Workers can run **truly in parallel** because dependencies are declared and validated upfront.

### 7. Definition of Done

Every task is complete only when all of these are satisfied (see `core/definition-of-done.md` for details):

- Implementation matches the accepted task specification
- Project architecture and ADRs are respected
- For `INTERFACE_CHANGE` work, an approved Design Approval Package exists and is referenced
- Relevant tests pass (including regression coverage when practical)
- Linting, type checks, build, and security checks pass (where configured)
- No secrets, credentials, or unrelated changes are introduced
- Documentation and operational notes are updated when behavior changed
- The git diff is focused and reviewable
- Required human approval gates remain unbypassed

This is identical for all workers. Validation evidence must not differ because a different vendor executed the task.

### 8. Validation Evidence and Baseline

When executing a task:

```
BASELINE (before) → CHANGE → FINAL (after)
```

- Record preexisting failures as baseline evidence; do not attribute them to your change without evidence
- A failure introduced by the task prevents task completion
- Do not silently fix unrelated preexisting failures; expanding scope requires explicit human approval

This baseline discipline ensures **harness parity**—two workers producing comparable evidence for the same task.

### 9. Architecture Principles

The Core defines these key principles (see `core/principles/architecture.md`):

- **Boundaries are contracts:** Make module ownership, public interfaces, and failure modes explicit
- **Prefer existing patterns:** Use established structure, dependency direction, error handling, logging, and testing conventions in the project before introducing new patterns
- **Design for change, not speculation:** Use simple, observable designs that satisfy current requirements—do not add hypothetical abstractions
- **Protect data boundaries:** Preserve authorization, tenant isolation, input validation, and data integrity at every boundary
- **Document consequential decisions:** Create an ADR when a choice has durable impact on architecture, operations, security, or cost

These principles apply **across all workers**. Codex should not introduce a pattern that Claude would reject.

## Installation and Usage

### Today: Bootstrap for Claude, Codex, or Copilot

Currently, adapters bootstrap individual harnesses with Core references:

```bash
scripts/install-adapters.sh
```

This renders adapter documents with absolute paths to Engineering OS and installs them at each harness's global instruction path.

### Tomorrow: Biah CLI (The Unified Orchestrator)

The roadmap includes **Biah CLI** — the single entry point:

```bash
biah task HC-006
biah plan HC-006
biah run HC-006
biah status
biah review HC-006
biah evidence HC-006
```

Internally, Biah:
1. Loads the Core and project instructions
2. Invokes Planner to create a task DAG
3. Invokes Router to match tasks to workers by capability
4. Creates worktrees and invokes each adapter
5. Collects and validates evidence
6. Stops at human gates

For now, this exists as a **concept and directory structure**. The actual CLI orchestrator will be implemented as **M7 — Vendor-Neutral Multi-Agent Execution Layer** in a separate module.

## Workflows and Reading Order

### When Biah Assigns You Work

If you receive a task, you are acting in a specific role:

**Planner role:** Read `agents/planner.md` and relevant Core documents. Your output is a portable task contract with declared dependencies.

**Builder role:** Read `agents/builder.md` and the task contract. You will execute in an isolated worktree. Your output is a complete `BUILD REPORT` in the fixed format.

**Reviewer role:** Read `agents/reviewer.md` and collect all evidence (plans, BUILD REPORTs, validation results). Your responsibility is confirming harness parity—evidence should be identical across workers.

### When You Are Reading This Repository

1. Start with `README.md` for the overall vision
2. Read the applicable Core documents for your area:
   - Architecting? Read `core/principles/architecture.md`
   - Deploying? Read `core/guardrails/production.md`
   - Planning a feature? Read `workflows/feature.md`
3. Read the agent contract for your role
4. Read `workflows/execution.md` to understand harness parity and portability
5. Check `adapters/README.md` to understand how adapters work

### Document Links and Repository References

- All links are relative to the repository root
- In adapter documents, `{{EOS_ROOT}}` is replaced at install time with the absolute path
- The Core is the single source of truth—adapters import from it, not vice versa

### Adding Project-Level Constraints

Create `.github/copilot-instructions.md` in your **project repository** (not this one). It may add constraints to Engineering OS but cannot weaken Core guardrails or human approval gates.

## Validation and Quality Gates

This is a documentation and governance repository, not a traditional code project. Validation depends on the area being modified:

**Documentation and contracts:** Verify that:
- Links are correct and resolve to the intended document
- Formatting is consistent and readable
- Concepts are clearly explained
- Examples in workflows are realistic

**Adapters:** Verify that:
- `scripts/install-adapters.sh` renders them without errors
- References to Core documents are correct
- The adapter would guide a harness to the correct rules

**Guardrails documents:** Verify that:
- New guardrails do not contradict existing Core principles
- Approval gates and constraints are clearly stated
- Examples are concrete and testable

**Scripts:** Test locally before committing:
```bash
scripts/install-adapters.sh --dry-run
```

## Design Philosophy

### Vendor Independence

Every design decision in Engineering OS is motivated by a single question: **"Would this work identically with Claude, Codex, Copilot, Gemini, or any future vendor?"**

If the answer is no, it belongs in an adapter, not in Core.

Examples:

- ✅ **Core:** "Builders must produce a BUILD REPORT in fixed format"
- ❌ **Not Core:** "Configure Claude with n_completions=X"

- ✅ **Adapter:** How to invoke the Claude CLI with Engineering OS flags
- ❌ **Not Adapter:** Claude-specific prompting tricks

### No Vendor Lock-In

Adapters are small, disposable bridges. If a new worker becomes strategically important, you:

1. Write a new adapter (500–1000 lines)
2. Register its capabilities in `workers` registry
3. Biah automatically includes it in routing

You do **not** rewrite Core, workflows, or contracts.

### Human-Centered Approval Gates

Every workflow has **HUMAN_GATE** checkpoints. Agents (all workers, including future ones) must stop and report evidence before proceeding. No harness can skip this.

## Milestones and Roadmap

### Current State (M1–M6 complete)

- Core principles, guardrails, definition of done ✓
- Agent contracts (Planner, Builder, Reviewer) ✓
- Workflow conventions (feature, execution) ✓
- Bootstrap adapters for Claude, Codex ✓
- Task portability and harness parity model ✓

### Next: M7 — Biah CLI + Multi-Agent Execution

Implement the Biah orchestrator with:

- **Biah CLI:** Single entry point (`biah task HC-006`, `biah review`, etc.)
- **Adapter layer:** Programmatic invocation of Claude, Codex, Copilot CLIs
- **Router:** Capability-based task assignment (not vendor preference)
- **Worktree management:** Isolated, parallel execution per task
- **Evidence collection:** Unified BUILD REPORTs from all workers
- **Human gates:** Structured approval workflow before and after execution

The goal is to make this line of code possible:

```bash
$ biah task HC-006
Planning HC-006...
✓ Context loaded
✓ Architecture constraints loaded
✓ Task contract validated

Execution plan:
HC-006-A  backend       → codex
HC-006-B  frontend      → copilot
HC-006-C  review        → claude

Run? [y/n]
```

Then, behind the scenes, parallel worktrees execute with each worker, and you review the unified result.
