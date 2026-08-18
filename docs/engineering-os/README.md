# Engineering OS

Engineering OS is a vendor-neutral source of truth for AI-assisted software delivery. It defines global engineering standards, approval boundaries, and agent contracts independently of any AI harness.

## v0.1 goal

Establish shared global context that both Claude Code and Codex can consume:

```text
Core → harness bootstrap → project instructions → task
```

Claude Code and Codex are harnesses/adapters. They consume this repository; they do not define its global rules. Both must reach the same Core and produce the same evidence for the same Task Contract; [`workflows/execution.md`](workflows/execution.md) defines that parity, and [`scripts/install-adapters.sh`](scripts/install-adapters.sh) installs the bootstraps that make the global context reachable from outside this checkout.

## Structure

| Area | Purpose |
| --- | --- |
| `core/` | Global engineering principles, guardrails, and definition of done. |
| `agents/` | Role contracts for the Planner, Builder, and Reviewer. |
| `adapters/` | Minimal bootstrap documents for each harness. |
| `workflows/` | Vendor-neutral lifecycle conventions for work intake, execution, and delivery. |
| `templates/` | Small, reusable starting points for canonical work artifacts. |
| `scripts/` | Operator utilities, including adapter installation. |

## Operating model

Rules are resolved from the most general to the most specific:

```text
Core → Project instructions → Task
```

Project-level instructions may add constraints. They cannot weaken the human approval gates or global guardrails in `core/`.

## Scope boundaries

Milestone 1 intentionally excludes orchestration, model routing, LiteLLM, observability, Grafana, FinOps, worktrees, parallel agents, scheduled tasks, and external knowledge-base integrations. Those capabilities are considered only after this global context has been reviewed in use.
