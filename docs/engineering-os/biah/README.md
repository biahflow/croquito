# Biah CLI - Vendor-Neutral Multi-Agent Orchestrator (M7)

Biah is the orchestration layer for Engineering OS. It routes work across Claude, Codex, Copilot, and future vendors based on task requirements, not vendor preference.

## Status

**Phase 1: CLI Skeleton + Planner Integration** (In Progress)

- [x] Project structure initialized
- [x] Go module setup
- [x] CLI framework (Cobra)
- [x] Commands stubbed (task, plan, run, review, status, evidence)
- [ ] Planner integration (load tasks, build DAG)
- [ ] Router implementation (capability matching)
- [ ] Adapter bridges (invoke CLI for real)
- [ ] Integration testing

## Quick Start

### Build

```bash
cd biah/
make build
```

### Run

```bash
# Show help
./bin/biah

# Try example commands
make task      # biah task HC-006
make plan      # biah plan HC-006
make status    # biah status
```

## Architecture

### Packages

- **pkg/cli** — CLI commands (task, plan, run, review, status)
- **pkg/planner** — Task loading, DAG construction
- **pkg/router** — Capability-based worker matching
- **pkg/adapter** — Worker interfaces and implementations
- **pkg/worktree** — Git worktree lifecycle
- **pkg/executor** — Parallel task execution
- **pkg/evidence** — BUILD REPORT aggregation
- **pkg/gate** — Human approval gates
- **pkg/config** — Configuration management

### Worker Adapters

Each worker has:
- `adapters/{vendor}/manifest.yml` — Capabilities and constraints
- `adapters/{vendor}/bridge.sh` — CLI invocation script (not yet implemented)

**Available Workers:**
- Claude (architecture reasoning, large context, refactoring)
- Codex (implementation, debugging, testing, code review)
- Copilot (implementation, GitHub native, repository operations)

## Key Concepts

### Task Contracts

Tasks are defined in YAML with metadata:

```yaml
task_id: HC-006
role: builder
requires:
  - implementation
  - testing
dependencies:
  - HC-005
```

### DAG (Directed Acyclic Graph)

Biah builds a DAG of tasks with dependencies:

```
HC-006-A (schema)        ← no dependencies
  ↓
HC-006-B (backend)       ← depends on A
  ↓
HC-006-C (frontend)      ← depends on B
HC-006-D (review)        ← depends on B, C
```

### Capability-Based Routing

Router matches tasks to workers by capabilities:

```yaml
Task HC-006-B requires: [implementation, testing]
  ↓
Check registry:
  - Claude: [architecture_reasoning, large_context] ✗
  - Codex: [implementation, debugging, testing] ✓
  - Copilot: [implementation, github_native] ✓
  ↓
Best match: Codex (score: 1.0)
```

### Parallel Execution

Tasks run in parallel when dependencies allow. Biah:
1. Topological sorts the DAG
2. Groups tasks by depth (can run in parallel)
3. Executes each group concurrently
4. Waits for dependencies before next group

### Evidence Collection

Each worker produces a BUILD REPORT in fixed format:

```json
{
  "status": "BUILD_COMPLETE",
  "files_changed": ["src/auth.ts"],
  "validation_executed": ["unit_tests", "lint"],
  "validation_skipped": [],
  "assumptions": ["Node 18+"],
  "remaining_risks": [],
  "human_decisions_required": []
}
```

Biah aggregates all BUILD REPORTs and validates harness parity.

### Human Gates

Two approval checkpoints:

1. **READY_TO_RUN** — Before execution
   - Plan validated
   - Context loaded
   - Worktrees ready
   - User approves? [y/n]

2. **READY_TO_REVIEW** — After execution
   - All workers completed
   - Evidence collected
   - Parity check passed
   - Quality gates passed
   - User approves merge? [y/n]

## Workflow Example

```bash
# 1. Accept a task
$ biah task HC-006
Loading task: HC-006
✓ Task loaded
✓ Contract validated
Next: biah plan HC-006

# 2. See the execution plan
$ biah plan HC-006
Planning: HC-006

DAG:
  HC-006-A  schema       (depends: none)
  HC-006-B  backend      (depends: HC-006-A)
  HC-006-C  frontend     (depends: HC-006-B)
  HC-006-D  review       (depends: HC-006-B, HC-006-C)

Routing by capability:
  HC-006-A  schema       → codex
  HC-006-B  backend      → codex
  HC-006-C  frontend     → copilot
  HC-006-D  review       → claude

# 3. Execute (with approval)
$ biah run HC-006
🚨 HUMAN GATE: Ready to run?
Proceed with execution? [y/n]: y

Executing tasks...
✓ Schema task (codex) completed
✓ Backend task (codex) completed
✓ Frontend task (copilot) completed
✓ Review task (claude) completed

# 4. Review evidence (with approval)
$ biah review HC-006
Evidence Package:
  [✓] HC-006-A BUILD_COMPLETE (schema)
  [✓] HC-006-B BUILD_COMPLETE (backend)
  [✓] HC-006-C BUILD_COMPLETE (frontend)
  [✓] HC-006-D BUILD_COMPLETE (review)

Parity check: ✓
Quality gates: ✓

🚨 HUMAN GATE: Ready to merge?
Approve and merge? [y/n]: y
✓ Ready for merge
```

## Development

### Add a new package

1. Create `pkg/{name}/` directory
2. Define interfaces in `{name}.go`
3. Implement in package
4. Add unit tests in `{name}_test.go`

### Add a new worker

1. Create `adapters/{vendor}/manifest.yml`
2. Create `pkg/adapter/{vendor}.go`
3. Implement `Adapter` interface
4. Register in `AdapterRegistry`

### Test

```bash
make test        # Run all tests
make coverage    # Generate coverage report
```

### Lint and Format

```bash
make lint        # Run golangci-lint
make fmt         # Format code
make tidy        # Tidy dependencies
```

## Next Steps

**Phase 1 (Weeks 1-2):**
- [ ] Implement task loading from YAML
- [ ] Implement full DAG construction
- [ ] Implement Planner invocation
- [ ] Integration test: load real task, show plan

**Phase 2 (Weeks 2-3):**
- [ ] Implement Router capability matching
- [ ] Load adapter manifests (YAML)
- [ ] Test: router assigns tasks correctly

**Phase 3 (Week 3):**
- [ ] Implement Worktree Manager
- [ ] Implement parallel Executor
- [ ] Test: run sample task with worktree isolation

**Phase 4 (Week 4):**
- [ ] Implement BUILD REPORT parser
- [ ] Implement evidence aggregator
- [ ] Implement human gate prompts
- [ ] Test: collected evidence matches worker output

**Phase 5 (Week 5):**
- [ ] Implement real CLI bridges (claude, codex, copilot)
- [ ] End-to-end integration testing
- [ ] Performance optimization
- [ ] Documentation and examples

## Documentation

- [`MILESTONES.md`](../MILESTONES.md) — Full M7 roadmap
- [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) — Engineering OS M7 context
- [`adapters/README.md`](../adapters/README.md) — Adapter model explanation

## License

Same as Engineering OS (See parent repository)
