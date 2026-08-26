# Adapters (M1: Bootstrap Phase)

An adapter is a bootstrap: the smallest document that points one harness at this repository. It carries no rules of its own, and it cannot grant a harness authority the Core denies.

**Current Status (M1 — Bootstrap):** Adapters are installed individually by operators. Each harness is bootstrapped separately. You choose which harness to use.

**Future Status (M7 — Orchestration):** Adapters become CLI bridges that Biah invokes programmatically. You use Biah; Biah selects workers by capability.

## Current Adapters (M1)

| Harness | Adapter | Installed at | Purpose |
| --- | --- | --- | --- |
| Claude Code | `claude/CLAUDE.md` | `${CLAUDE_CONFIG_DIR:-~/.claude}/engineering-os.md` | Bootstrap Claude Code with global Core references |
| Codex | `codex/AGENTS.md` | `${CODEX_HOME:-~/.codex}/AGENTS.md` | Bootstrap Codex with global Core references |

### Installation

The Claude adapter is installed beside the global instruction file rather than replacing it:
- `CLAUDE.md` at that path is the operator's own document
- It imports the adapter with `@${CLAUDE_CONFIG_DIR:-~/.claude}/engineering-os.md`
- Personal preferences and Engineering OS bootstrap stay in separate files
- Reinstalling never overwrites the operator's own instructions

Codex has no equivalent import convention, so its adapter becomes the global file directly.

## Why adapters are rendered, not copied

Both harnesses read their global instruction file from a fixed path outside this
repository. A relative reference resolved from that path does not reach this repository,
so every reference to the source of truth must be absolute. Hardcoding one operator's
absolute path in a versioned file makes the repository non-portable.

The adapters therefore carry the `{{EOS_ROOT}}` placeholder, and
[`../scripts/install-adapters.sh`](../scripts/install-adapters.sh) resolves it to this
checkout's absolute path at install time:

```bash
scripts/install-adapters.sh --dry-run   # inspect
scripts/install-adapters.sh             # install
```

The substitution is literal: a checkout path containing `&`, `#`, or a backslash is
inserted unchanged. An existing file at a destination is backed up, never discarded — that
path may hold the operator's own global instructions — and a destination that is a symlink is
refused rather than written through, because writing through the link would modify whatever
manages it while the backup landed somewhere else. Both adapters are rendered and validated
before either is written, so a failure does not leave the two harnesses under different
Cores.

## Resolution order

```text
Global adapter → Core → project instructions → task
```

Both adapters must reach the same Core documents and the same agent contracts. An
asymmetry between them is a defect: it means the same task carries different rules
depending on which harness picked it up. [`../workflows/execution.md`](../workflows/execution.md)
defines what the two harnesses must share for a Task Contract to be portable between them.

## Consumer projects: the pinned mirror

Adapters solve reachability for exactly one machine: the operator's. CI, a new
collaborator, and an agent running in the cloud never see the rendered bootstrap, so for
them the global layer does not exist — which violates the execution-artifact requirement in
[`../core/definition-of-done.md`](../core/definition-of-done.md).

A consumer repository closes that gap by vendoring a **complete pinned mirror** of this
repository inside its own tree:

- the mirror is a full copy, so internal links between global documents keep resolving;
- a provenance record names the source commit, the source tree state, and the sync date —
  while no new sync lands, that commit **is** the global layer for that repository;
- resynchronizing is a deliberate act performed against a clean source tree, and the
  resulting diff is reviewed like any other change — never an automatic job;
- the mirror is excluded from the project's local formatting (fidelity to the source wins)
  but included in its link validation.

When the operator's live checkout has moved past a project's pin, the two are in visible,
dated drift: for work inside that project, **the pin is authoritative**, including for an
executor whose personal bootstrap points at the live checkout. Advancing the pin is a
reviewed change in the consumer repository, not a side effect of editing this one.

## Installing is not verifying

A rendered file at the right path is not evidence that a harness loaded it. Confirm in
each harness that the Core is present before treating global context as operational.

## Adapters in M7: From Bootstrap to Worker Bridge

**Current (M1):** Adapters bootstrap harnesses. You choose which one to use.

**Future (M7):** Adapters become programmatic worker bridges. Biah invokes them, not vice versa.

### M7 Adapter Model

In M7, each adapter becomes a thin CLI bridge:

```
Biah (Orchestrator)
    │
    ├─→ adapters/claude/  → invoke claude CLI with task
    ├─→ adapters/codex/   → invoke codex CLI with task
    └─→ adapters/copilot/ → invoke copilot CLI with task
```

Each adapter:
- Receives a task contract from Biah
- Invokes the vendor's CLI in an isolated worktree
- Collects and returns the BUILD REPORT
- Does not modify task requirements or worker selection

### Capability Registration (M7)

Each adapter declares what the worker can do:

```yaml
# adapters/claude/manifest.yml
worker: claude
capabilities:
  - architecture_reasoning
  - large_context
  - refactoring
```

Biah reads this registry when routing tasks. If a task requires `architecture_reasoning`, Biah sends it to Claude—not because you asked for Claude, but because the task requirements match Claude's capabilities.

### Example M7 Flow

```
Task HC-006-backend requires: [implementation, testing]

Biah checks registry:
  claude: [architecture_reasoning, large_context, refactoring]
  codex: [implementation, debugging, testing, code_review]  ← matches!
  copilot: [implementation, github_native, repository_operations]

Biah invokes: adapters/codex/bridge.sh HC-006-backend
  → worker: codex
  → worktree: /tmp/worktree-HC-006-backend
  → BUILD REPORT: ✓ implementation complete

Biah waits for dependencies, then:
Biah invokes: adapters/claude/bridge.sh HC-006-review
  → worker: claude
  → worktree: /tmp/worktree-HC-006-review
  → BUILD REPORT: ✓ architecture review complete

All BUILD REPORTs collected → HUMAN_GATE
```

### Adding New Vendors (M7+)

To add Gemini Code as a worker:

1. Create `adapters/gemini/`
2. Write `bridge.sh` to invoke Gemini CLI
3. Write `manifest.yml` with Gemini's capabilities
4. Register in Biah's worker registry

Done. No changes to Core, contracts, or workflows. Existing tasks route to Gemini automatically when its capabilities match.

### Backward Compatibility

M1 adapters (bootstrap documents) continue to work. Teams that prefer to pick their own harness can still run:

```bash
scripts/install-adapters.sh
```

and bootstrap Claude Code or Codex individually. The adapters are designed to serve both purposes:
- **M1 use:** As bootstrap documents for human harness selection
- **M7 use:** As worker bridges invoked by Biah orchestrator

## See Also

- [`MILESTONES.md`](../MILESTONES.md) — Full roadmap from M1 through M7
- [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) — M7-aware instructions for Engineering OS
