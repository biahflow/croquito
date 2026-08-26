package router

import (
	"context"
	"testing"

	"github.com/biahflow/engineering-os/biah/pkg/adapter"
	"github.com/biahflow/engineering-os/biah/pkg/planner"
)

// MockAdapter is a test adapter
type MockAdapter struct {
	name         string
	capabilities []string
}

func (m *MockAdapter) Name() string {
	return m.name
}

func (m *MockAdapter) Capabilities() []string {
	return m.capabilities
}

func (m *MockAdapter) Invoke(ctx *adapter.WorktreeContext) (*adapter.BuildReport, error) {
	return nil, nil
}

func (m *MockAdapter) InvokeWithContext(ctx context.Context, taskID string, worktreePath string) (*adapter.BuildReport, error) {
	return nil, nil
}

// MockRegistry is a test registry
type MockRegistry struct {
	adapters map[string]adapter.Adapter
	order    []string // To maintain deterministic iteration order
}

func NewMockRegistry() *MockRegistry {
	return &MockRegistry{
		adapters: make(map[string]adapter.Adapter),
		order:    []string{},
	}
}

func (mr *MockRegistry) Add(name string, caps []string) {
	mr.adapters[name] = &MockAdapter{
		name:         name,
		capabilities: caps,
	}
	mr.order = append(mr.order, name)
}

func (mr *MockRegistry) Get(name string) (adapter.Adapter, error) {
	a, ok := mr.adapters[name]
	if !ok {
		return nil, nil
	}
	return a, nil
}

func (mr *MockRegistry) ListAll() []adapter.Adapter {
	result := make([]adapter.Adapter, 0, len(mr.order))
	for _, name := range mr.order {
		result = append(result, mr.adapters[name])
	}
	return result
}

// Test single capability match
func TestRouteSingleCapabilityMatch(t *testing.T) {
	registry := NewMockRegistry()
	registry.Add("worker1", []string{"implementation"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "task1",
		Requires: []string{"implementation"},
	}

	matches, err := router.Route(task)

	if err != nil {
		t.Fatalf("Route returned error: %v", err)
	}

	if len(matches) != 1 {
		t.Fatalf("Expected 1 match, got %d", len(matches))
	}

	if matches[0].Score != 100 {
		t.Errorf("Expected score 100, got %d", matches[0].Score)
	}

	if matches[0].CapsMatched != 1 {
		t.Errorf("Expected 1 cap matched, got %d", matches[0].CapsMatched)
	}

	if matches[0].CapsRequired != 1 {
		t.Errorf("Expected 1 cap required, got %d", matches[0].CapsRequired)
	}

	if matches[0].Ranking != 1 {
		t.Errorf("Expected ranking 1, got %d", matches[0].Ranking)
	}
}

// Test multiple capability match (3 required, worker has 3)
func TestRouteMultipleCapabilityMatch(t *testing.T) {
	registry := NewMockRegistry()
	registry.Add("codex", []string{"implementation", "testing", "database_migration"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "HC-006",
		Requires: []string{"implementation", "testing", "database_migration"},
	}

	matches, err := router.Route(task)

	if err != nil {
		t.Fatalf("Route returned error: %v", err)
	}

	if len(matches) != 1 {
		t.Fatalf("Expected 1 match, got %d", len(matches))
	}

	match := matches[0]
	if match.Score != 100 {
		t.Errorf("Expected score 100, got %d", match.Score)
	}

	if match.CapsMatched != 3 {
		t.Errorf("Expected 3 caps matched, got %d", match.CapsMatched)
	}

	if match.CapsRequired != 3 {
		t.Errorf("Expected 3 caps required, got %d", match.CapsRequired)
	}
}

// Test partial match (worker has 2/3, should be lower ranked)
func TestRoutePartialMatch(t *testing.T) {
	registry := NewMockRegistry()
	registry.Add("claude", []string{"architecture_reasoning", "large_context", "code_review", "implementation", "testing"})
	registry.Add("codex", []string{"implementation", "debugging", "testing", "database_migration"})
	registry.Add("copilot", []string{"testing", "code_review"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "HC-006",
		Requires: []string{"implementation", "testing", "database_migration"},
	}

	matches, err := router.Route(task)

	if err != nil {
		t.Fatalf("Route returned error: %v", err)
	}

	if len(matches) != 3 {
		t.Fatalf("Expected 3 matches, got %d", len(matches))
	}

	// Codex should be first (3/3 = 100%)
	if matches[0].Worker.Name() != "codex" || matches[0].Score != 100 {
		t.Errorf("Expected codex with score 100 first, got %s with score %d", matches[0].Worker.Name(), matches[0].Score)
	}

	// Claude should be second (2/3 = 66%)
	if matches[1].Worker.Name() != "claude" || matches[1].Score != 66 {
		t.Errorf("Expected claude with score 66 second, got %s with score %d", matches[1].Worker.Name(), matches[1].Score)
	}

	// Copilot should be third (1/3 = 33%)
	if matches[2].Worker.Name() != "copilot" || matches[2].Score != 33 {
		t.Errorf("Expected copilot with score 33 third, got %s with score %d", matches[2].Worker.Name(), matches[2].Score)
	}

	// Verify rankings
	for i, match := range matches {
		if match.Ranking != i+1 {
			t.Errorf("Expected ranking %d, got %d", i+1, match.Ranking)
		}
	}
}

// Test no match (no worker has any of the required caps → error)
func TestRouteNoMatch(t *testing.T) {
	registry := NewMockRegistry()
	registry.Add("claude", []string{"architecture_reasoning", "large_context"})
	registry.Add("codex", []string{"debugging", "refactoring"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "task1",
		Requires: []string{"implementation", "testing", "database_migration"},
	}

	matches, err := router.Route(task)

	if err == nil {
		t.Fatalf("Expected error for no match, got nil")
	}

	if matches != nil {
		t.Errorf("Expected nil matches on error, got %v", matches)
	}
}

// Test empty requirements (should return all workers, score 100)
func TestRouteEmptyRequirements(t *testing.T) {
	registry := NewMockRegistry()
	registry.Add("claude", []string{"architecture_reasoning"})
	registry.Add("codex", []string{"implementation"})
	registry.Add("copilot", []string{"testing"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "task1",
		Requires: []string{},
	}

	matches, err := router.Route(task)

	if err != nil {
		t.Fatalf("Route returned error: %v", err)
	}

	if len(matches) != 3 {
		t.Fatalf("Expected 3 matches for empty requirements, got %d", len(matches))
	}

	// All should have score 100
	for i, match := range matches {
		if match.Score != 100 {
			t.Errorf("Match %d: Expected score 100 for empty requirements, got %d", i, match.Score)
		}
		if match.CapsMatched != 0 {
			t.Errorf("Match %d: Expected 0 caps matched for empty requirements, got %d", i, match.CapsMatched)
		}
		if match.CapsRequired != 0 {
			t.Errorf("Match %d: Expected 0 caps required for empty requirements, got %d", i, match.CapsRequired)
		}
	}
}

// Test deterministic output (same input → same output)
func TestRouteDeterministic(t *testing.T) {
	// Create registry with consistent order
	newRegistry := func() *MockRegistry {
		registry := NewMockRegistry()
		registry.Add("alice", []string{"implementation", "testing"})
		registry.Add("bob", []string{"testing", "debugging"})
		registry.Add("charlie", []string{"implementation", "testing", "database_migration"})
		return registry
	}

	router1 := NewRouter(newRegistry())
	router2 := NewRouter(newRegistry())

	task := &planner.Task{
		ID:       "task1",
		Requires: []string{"implementation", "testing", "database_migration"},
	}

	matches1, err1 := router1.Route(task)
	matches2, err2 := router2.Route(task)

	if err1 != nil || err2 != nil {
		t.Fatalf("Route returned errors: %v, %v", err1, err2)
	}

	if len(matches1) != len(matches2) {
		t.Fatalf("Expected same number of matches, got %d vs %d", len(matches1), len(matches2))
	}

	// Compare results
	for i := range matches1 {
		m1 := matches1[i]
		m2 := matches2[i]

		if m1.Worker.Name() != m2.Worker.Name() {
			t.Errorf("Match %d: Worker names differ: %s vs %s", i, m1.Worker.Name(), m2.Worker.Name())
		}

		if m1.Score != m2.Score {
			t.Errorf("Match %d: Scores differ: %d vs %d", i, m1.Score, m2.Score)
		}

		if m1.CapsMatched != m2.CapsMatched {
			t.Errorf("Match %d: CapsMatched differ: %d vs %d", i, m1.CapsMatched, m2.CapsMatched)
		}

		if m1.Ranking != m2.Ranking {
			t.Errorf("Match %d: Rankings differ: %d vs %d", i, m1.Ranking, m2.Ranking)
		}
	}
}

// Test nil registry
func TestRouteNilRegistry(t *testing.T) {
	router := NewRouter(nil)
	task := &planner.Task{
		ID:       "task1",
		Requires: []string{"implementation"},
	}

	matches, err := router.Route(task)

	if err == nil {
		t.Fatalf("Expected error for nil registry, got nil")
	}

	if matches != nil {
		t.Errorf("Expected nil matches on error, got %v", matches)
	}
}

// Test nil task
func TestRouteNilTask(t *testing.T) {
	registry := NewMockRegistry()
	registry.Add("worker1", []string{"implementation"})

	router := NewRouter(registry)

	matches, err := router.Route(nil)

	if err == nil {
		t.Fatalf("Expected error for nil task, got nil")
	}

	if matches != nil {
		t.Errorf("Expected nil matches on error, got %v", matches)
	}
}

// Test score calculation accuracy
func TestRouteScoreCalculation(t *testing.T) {
	registry := NewMockRegistry()
	// Worker has 1/3 capabilities
	registry.Add("partial1", []string{"implementation"})
	// Worker has 2/3 capabilities
	registry.Add("partial2", []string{"implementation", "testing"})
	// Worker has 3/3 capabilities
	registry.Add("full", []string{"implementation", "testing", "database_migration"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "task1",
		Requires: []string{"implementation", "testing", "database_migration"},
	}

	matches, err := router.Route(task)

	if err != nil {
		t.Fatalf("Route returned error: %v", err)
	}

	testCases := []struct {
		expectedWorker string
		expectedScore  int
		expectedRank   int
	}{
		{"full", 100, 1},
		{"partial2", 66, 2},
		{"partial1", 33, 3},
	}

	for i, tc := range testCases {
		if matches[i].Worker.Name() != tc.expectedWorker {
			t.Errorf("Position %d: Expected worker %s, got %s", i, tc.expectedWorker, matches[i].Worker.Name())
		}

		if matches[i].Score != tc.expectedScore {
			t.Errorf("Position %d: Expected score %d, got %d", i, tc.expectedScore, matches[i].Score)
		}

		if matches[i].Ranking != tc.expectedRank {
			t.Errorf("Position %d: Expected ranking %d, got %d", i, tc.expectedRank, matches[i].Ranking)
		}
	}
}

// Test ranking field is correctly assigned
func TestWorkerMatchRanking(t *testing.T) {
	registry := NewMockRegistry()
	registry.Add("w1", []string{"a", "b", "c"})
	registry.Add("w2", []string{"a", "b"})
	registry.Add("w3", []string{"a"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "task1",
		Requires: []string{"a", "b", "c"},
	}

	matches, _ := router.Route(task)

	for i, match := range matches {
		if match.Ranking != i+1 {
			t.Errorf("Expected ranking %d at position %d, got %d", i+1, i, match.Ranking)
		}
	}
}

// Test CapsMatched and CapsRequired fields
func TestCapabilityMatching(t *testing.T) {
	registry := NewMockRegistry()
	registry.Add("worker1", []string{"a", "b", "c", "d", "e"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "task1",
		Requires: []string{"a", "b", "c"},
	}

	matches, _ := router.Route(task)

	match := matches[0]
	if match.CapsMatched != 3 {
		t.Errorf("Expected CapsMatched 3, got %d", match.CapsMatched)
	}

	if match.CapsRequired != 3 {
		t.Errorf("Expected CapsRequired 3, got %d", match.CapsRequired)
	}

	// Verify the score is correct
	expectedScore := (match.CapsMatched * 100) / match.CapsRequired
	if match.Score != expectedScore {
		t.Errorf("Score mismatch: expected %d, got %d", expectedScore, match.Score)
	}
}

// Test tiebreaker (same score, different workers)
func TestTiebreakerByWorkerName(t *testing.T) {
	registry := NewMockRegistry()
	// Both have same score
	registry.Add("zebra", []string{"implementation"})
	registry.Add("alpha", []string{"implementation"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "task1",
		Requires: []string{"implementation"},
	}

	matches, _ := router.Route(task)

	// Both should have score 100, but alpha should come first (alphabetical tiebreaker)
	if matches[0].Worker.Name() != "alpha" {
		t.Errorf("Expected 'alpha' first in tiebreaker, got %s", matches[0].Worker.Name())
	}

	if matches[1].Worker.Name() != "zebra" {
		t.Errorf("Expected 'zebra' second in tiebreaker, got %s", matches[1].Worker.Name())
	}
}

// Test case sensitivity in capability matching
func TestCapabilityMatchingCaseSensitive(t *testing.T) {
	registry := NewMockRegistry()
	registry.Add("worker1", []string{"Implementation", "Testing"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "task1",
		Requires: []string{"implementation", "testing"},
	}

	matches, err := router.Route(task)

	// Should not match because case is different
	if err == nil {
		t.Fatalf("Expected error for case-sensitive mismatch, got nil")
	}

	if matches != nil {
		t.Errorf("Expected nil matches, got %v", matches)
	}
}

// Test with many workers
func TestManyWorkers(t *testing.T) {
	registry := NewMockRegistry()
	for i := 0; i < 10; i++ {
		name := string(rune('a' + i))
		// Give each worker different number of matching capabilities
		var caps []string
		for j := 0; j <= i; j++ {
			caps = append(caps, string(rune('x'+j)))
		}
		registry.Add(name, caps)
	}

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "task1",
		Requires: []string{"x", "y", "z"},
	}

	matches, err := router.Route(task)

	if err != nil {
		t.Fatalf("Route returned error: %v", err)
	}

	if len(matches) != 10 {
		t.Fatalf("Expected 10 matches, got %d", len(matches))
	}

	// Verify sorting order (descending by score)
	for i := 0; i < len(matches)-1; i++ {
		if matches[i].Score < matches[i+1].Score {
			t.Errorf("Matches not sorted correctly: position %d has score %d, position %d has score %d",
				i, matches[i].Score, i+1, matches[i+1].Score)
		}
	}

	// Verify rankings are sequential
	for i, match := range matches {
		if match.Ranking != i+1 {
			t.Errorf("Expected ranking %d at position %d, got %d", i+1, i, match.Ranking)
		}
	}
}

// Benchmark Route with typical scenario
func BenchmarkRoute(b *testing.B) {
	registry := NewMockRegistry()
	registry.Add("claude", []string{"architecture_reasoning", "large_context", "code_review", "implementation", "testing"})
	registry.Add("codex", []string{"implementation", "debugging", "testing", "database_migration"})
	registry.Add("copilot", []string{"testing", "code_review", "github_native"})

	router := NewRouter(registry)
	task := &planner.Task{
		ID:       "HC-006",
		Requires: []string{"implementation", "testing", "database_migration"},
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		router.Route(task)
	}
}
