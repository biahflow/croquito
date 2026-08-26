# M7 Phase 5 - Real CLI Integration (Worker Harness Bridge)

**Status:** In Progress  
**Started:** 2026-08-23 19:24 UTC-3  
**Target Completion:** 2026-08-23 22:00 UTC-3 (parallel execution)

---

## Architecture

```
┌─────────────────────────────────────┐
│ Real CLI Integration Layer          │
├─────────────────────────────────────┤
│  Adapter Bridge (Real CLIs)         │
│  ├─ Claude Bridge (WS1)             │
│  │  └─ claude-cli execute           │
│  ├─ Codex Bridge (WS2)              │
│  │  └─ codex-cli execute            │
│  └─ Copilot Bridge (WS3)            │
│     └─ copilot-cli execute          │
├─────────────────────────────────────┤
│ Output Parsing                      │
│  ├─ BUILD REPORT JSON parsing       │
│  ├─ File capture                    │
│  └─ Execution time tracking         │
├─────────────────────────────────────┤
│ Evidence Aggregation (WS4)          │
│  ├─ Multi-worker collection         │
│  ├─ Parity scoring (0-100%)         │
│  ├─ File-level comparison           │
│  └─ Audit trail logging             │
├─────────────────────────────────────┤
│ E2E Integration Testing (WS5)       │
│  ├─ Real CLI execution              │
│  ├─ Evidence validation             │
│  └─ Gate approval workflow          │
└─────────────────────────────────────┘
```

---

## Workstreams (Parallel)

### ✅ WS1: Real Claude CLI Bridge
**Owner:** m7-phase5-claude  
**Status:** RUNNING  
**Scope:**
- Replace mock Execute() with real claude-cli invocation
- Parse BUILD REPORT JSON
- Handle timeouts/errors
- Add unit tests (70%+ coverage)

**Files:**
- `biah/adapters/claude/bridge.go` (modify)
- `biah/adapters/claude/bridge_test.go` (add/enhance)

---

### ✅ WS2: Real Codex CLI Bridge
**Owner:** m7-phase5-codex  
**Status:** RUNNING  
**Scope:**
- Replace mock Execute() with real codex-cli invocation
- Parse BUILD REPORT JSON
- Handle timeouts/errors
- Add unit tests (70%+ coverage)

**Files:**
- `biah/adapters/codex/bridge.go` (modify)
- `biah/adapters/codex/bridge_test.go` (add/enhance)

---

### ✅ WS3: Real Copilot CLI Bridge
**Owner:** m7-phase5-copilot  
**Status:** RUNNING  
**Scope:**
- Replace mock Execute() with real copilot-cli invocation
- Parse BUILD REPORT JSON
- Handle timeouts/errors
- Add unit tests (70%+ coverage)

**Files:**
- `biah/adapters/copilot/bridge.go` (modify)
- `biah/adapters/copilot/bridge_test.go` (add/enhance)

---

### ⏳ WS4: Enhanced Evidence Aggregation & Parity
**Owner:** m7-phase5-evidence  
**Status:** WAITING (for WS1+WS2+WS3)  
**Scope:**
- ParityScore (0-100%): file match, status match, risk match, execution time
- DetailedParityValidation: FULL/PARTIAL/DIVERGENT levels
- File-level comparison: UNANIMOUS/PARTIAL/SINGLE tracking
- Audit trail: persistent logging to jsonl
- ParityReport generation

**Files:**
- `biah/pkg/evidence/aggregator.go` (enhance)
- `biah/pkg/evidence/aggregator_test.go` (add tests)
- `biah/pkg/evidence/parity.go` (new - scoring logic)

**Tests:**
- TestParityScoreFull/Partial/Divergent
- TestFileConsistencyAnalysis
- TestAuditTrailLogging
- TestParityReportGeneration
- TestRecommendationLogic

---

### ⏳ WS5: E2E Integration Testing
**Owner:** m7-phase5-e2e  
**Status:** WAITING (for WS4)  
**Scope:**
- Create test harness task (HC-006-like)
- Execute across all 3 workers in parallel
- Aggregate outputs with real data
- Validate parity
- Test gates interactively
- Stress test worktrees

**Files:**
- `biah/cmd/e2e-integration-test/main.go` (new)
- `biah/cmd/e2e-demo/main.go` (extend)

**Tests:**
- TestE2EFullWorkflow
- TestE2EParallelExecution
- TestE2EWorktreeIsolation
- TestE2EApprovalGates
- TestE2EReportGeneration

---

## Timeline

| Phase | Start | Duration | Status |
|-------|-------|----------|--------|
| Launch WS1+WS2+WS3 | 19:25 | 5 min | ✅ DONE |
| WS1+WS2+WS3 Execution | 19:30 | 2-3 hrs | ⏳ RUNNING |
| WS4 Execution | 21:30 | 1-2 hrs | ⏳ WAITING |
| WS5 Execution | 22:30 | 1-2 hrs | ⏳ WAITING |
| Final Validation | 23:00 | 30 min | ⏳ WAITING |
| **Total** | 19:25 | 4-5 hrs | ⏳ IN PROGRESS |

---

## Success Criteria

| Item | Target | Status |
|------|--------|--------|
| Unit tests pass | 100% | ⏳ |
| Code coverage | 85%+ | ⏳ |
| Race conditions | 0 | ⏳ |
| E2E workflow | Operational | ⏳ |
| Real CLI integration | Working | ⏳ |
| Parity validation | Scoring + detailed | ⏳ |
| Audit trail | Persistent jsonl | ⏳ |
| Documentation | Complete | ⏳ |

---

## Implementation Notes

### CLI Invocation Pattern
```bash
# Each adapter will execute:
<worker>-cli execute \
  --task=HC-006-A \
  --task-file=/path/to/task.yaml \
  --output-dir=/tmp/biah-wt-<ID>

# Expected stdout:
{
  "status": "SUCCESS",
  "filesChanged": ["src/foo.go", "test/bar_test.go"],
  "startTime": "2026-08-23T19:30:00Z",
  "endTime": "2026-08-23T19:35:00Z",
  "errors": [],
  "notes": ["Implemented feature X"]
}
```

### Parity Scoring Examples

**Example 1: Perfect Match**
```
Worker A: 5 files, SUCCESS, 2 risks, 3 min
Worker B: 5 files, SUCCESS, 2 risks, 3.1 min
Worker C: 5 files, SUCCESS, 2 risks, 2.95 min

Parity Score: 98%
- FileMatch: 100% (all have 5)
- StatusMatch: 100% (all SUCCESS)
- RiskMatch: 100% (same 2 risks)
- ExecutionTime: 98% (variation <5%)
```

**Example 2: Partial Match**
```
Worker A: 5 files, SUCCESS, 2 risks, 3 min
Worker B: 6 files, SUCCESS, 2 risks, 3.2 min
Worker C: 5 files, SUCCESS, 3 risks, 2.95 min

Parity Score: 77%
- FileMatch: 67% (2/3 match)
- StatusMatch: 100% (all SUCCESS)
- RiskMatch: 67% (2/3 common)
- ExecutionTime: 98%
```

**Example 3: Divergent**
```
Worker A: 5 files, SUCCESS, 2 risks, 3 min
Worker B: 8 files, FAILURE, 5 risks, 10 min
Worker C: 3 files, SUCCESS, 1 risk, 2 min

Parity Score: 25%
- FileMatch: 0% (all differ)
- StatusMatch: 0% (mixed SUCCESS/FAILURE)
- RiskMatch: 20% (little overlap)
- ExecutionTime: 20% (high variance)

Recommendations:
- Check Worker B logs for failure cause
- Validate task contract compatibility
- Consider harness version differences
```

---

## Integration Checkpoints

### After WS1+WS2+WS3
- [ ] All 3 adapters use real CLIs
- [ ] No mock data in Execute()
- [ ] BUILD REPORT JSON parsing verified
- [ ] Timeout/error handling working
- [ ] 70%+ coverage on each adapter

### After WS4
- [ ] ParityScore computed correctly
- [ ] DetailedParityValidation in place
- [ ] File-level comparison working
- [ ] Audit trail persistent (jsonl)
- [ ] ParityReport JSON valid
- [ ] 75%+ coverage on new code

### After WS5
- [ ] E2E test harness functional
- [ ] All 3 workers execute in parallel
- [ ] Evidence aggregation with real data
- [ ] Parity validation showing accurate scores
- [ ] Gates work with real data
- [ ] Full workflow reproducible

---

## Known Issues & Mitigations

| Issue | Mitigation |
|-------|-----------|
| CLIs not installed | Graceful fallback with error message |
| Slow CLI execution | 10-minute timeout per task |
| JSON parse errors | Continue with empty report + log |
| File conflicts | Worktree isolation (per-task) |
| Concurrent gate prompts | Synchronized approval via mutex |

---

## Deliverables (Phase 5 Complete)

- ✅ 3 real CLI adapter bridges (claude/codex/copilot)
- ✅ Enhanced evidence aggregation with parity scoring
- ✅ Audit trail logging (persistent jsonl)
- ✅ E2E integration test harness
- ✅ 200+ new tests (total 367+)
- ✅ 85%+ code coverage
- ✅ Production-ready binary
- ✅ Complete documentation

---

**Phase 5 In Progress → Awaiting WS1+WS2+WS3 Completion**

Created: 2026-08-23 19:25 UTC-3  
By: Copilot CLI (M7 Phase 5 Coordinator)
