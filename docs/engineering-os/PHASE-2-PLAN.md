# Phase 2: Router + Adapter Implementation

## Phase 2.1: Worker Registry (Capability Loader)

**Todo ID:** m7-worker-registry
**Depends on:** m7-cli-skeleton, m7-planner-integration
**Owner:** m7-adapter-registry (background agent)

### Task

Implement `pkg/registry/registry.go` to:

1. Load capability manifests from `biah/adapters/*/manifest.yml`
2. Parse worker name, capabilities, constraints (timeout, tokens, parallelism)
3. Expose `GetWorkersByCapability(required []string) []Worker`
4. Support hot-reload (watch manifest files)
5. Validate manifest schema on load

### Acceptance Criteria

- [ ] LoadManifests() loads all YAML files in adapters/ directory
- [ ] ParseManifest() extracts: name, capabilities, constraints
- [ ] GetWorkersByCapability() returns workers matching ALL required capabilities
- [ ] ValidateManifest() checks for required fields
- [ ] Unit tests (70%+ coverage)
- [ ] No circular dependencies between packages

### Example

```go
registry := NewRegistry("biah/adapters")
registry.LoadManifests()

// Get workers that can handle [implementation, testing]
workers := registry.GetWorkersByCapability([]string{"implementation", "testing"})
// Returns: [Claude (impl+testing), Codex (impl+testing)]
// Not: [Copilot (testing only)]
```

---

## Phase 2.2: Router (Capability Matching)

**Todo ID:** m7-router-impl
**Depends on:** m7-worker-registry
**Owner:** m7-router-impl (background agent)

### Task

Implement `pkg/router/router.go` to:

1. Read task requires[] fields (from Planner)
2. Query Worker Registry for matching workers
3. Implement scoring algorithm (capability match strength, resource constraints)
4. Return ranked list of workers
5. Handle edge cases: no match found, single worker required, parallel execution

### Acceptance Criteria

- [ ] Route() returns ranked list of workers matching task requirements
- [ ] Scoring: 100 points if all caps match, 0 if any missing
- [ ] Constraint checking: timeout, token budget, parallelism
- [ ] Error handling: task with no matching workers → error
- [ ] Unit tests (70%+ coverage)
- [ ] Deterministic output (same input → same ranking)

### Example

```go
router := NewRouter(registry)

task := &Task{
  ID: "HC-006",
  Requires: []string{"implementation", "testing", "database_migration"},
}

workers := router.Route(task)
// Returns: [Codex (3/3), Claude (3/3), Copilot (1/3)]
// Sorted by match score descending
```

---

## Phase 2.3: Adapter CLI Bridges

**Todo ID:** m7-adapter-bridges
**Depends on:** m7-worker-registry
**Owner:** m7-adapter-bridges (background agent)

### Task

Implement actual CLI bridges for each worker:

1. `adapters/claude/bridge.go` → `claude-cli` invocation
2. `adapters/codex/bridge.go` → `codex-cli` invocation  
3. `adapters/copilot/bridge.go` → `copilot-cli` invocation

Each bridge must:
- Check if CLI is available (fallback handling)
- Invoke with task contract as input
- Capture stdout → BUILD_REPORT JSON
- Parse BUILD_REPORT (Status, FilesChanged, Validation, Risks, Decisions)
- Return typed BuildReport struct

### Acceptance Criteria

- [ ] Each bridge implements Adapter interface
- [ ] Invokes actual CLI (with availability check)
- [ ] Parses BUILD_REPORT from stdout
- [ ] Handles CLI unavailable → error or fallback
- [ ] Unit tests (mocked CLI invocation)
- [ ] Integration stubs for E2E testing

### Example

```go
adapter := claude.NewBridge()
report, err := adapter.Execute(context.Background(), task, worktree)
// Invokes: claude-cli run task=HC-006 worktree=/tmp/wt-HC-006
// Returns: BuildReport{Status: "SUCCESS", FilesChanged: 3, ...}
```

---

## Phase 2 Success Criteria

✅ All three components integrate:
- Planner outputs task with requires[] 
- Router queries Registry for matching workers
- Executor invokes selected worker via Bridge
- BUILD_REPORT returned for evidence aggregation

✅ Tests pass for all three components

✅ Example end-to-end: `biah run HC-006` prints routing decision + selected worker

---

## Timeline

- **Phase 2.1 (Registry):** 45 min (manifest loading, validation, tests)
- **Phase 2.2 (Router):** 45 min (matching algorithm, scoring, tests)
- **Phase 2.3 (Bridges):** 60 min (3 CLI wrappers, error handling, mocking)

**Total Phase 2:** ~2.5 hours → Ready for Phase 3 (Worktree + Executor)
