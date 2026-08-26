package gate

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/biahflow/engineering-os/biah/pkg/adapter"
	"github.com/biahflow/engineering-os/biah/pkg/planner"
)

// TestPromptReadyToRunApproved tests the READY_TO_RUN gate with approval
func TestPromptReadyToRunApproved(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	stdin := bytes.NewBufferString("y\n")
	stdout := &bytes.Buffer{}

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, stdin, stdout)

	task := &planner.Task{
		ID:          "HC-001",
		Title:       "User Authentication",
		Description: "Implement user authentication",
	}

	workers := []string{"claude", "codex", "copilot"}
	ctx := context.Background()

	approved, decision, err := gate.PromptReadyToRun(ctx, task, workers)

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !approved {
		t.Error("expected approval, but got rejection")
	}

	if decision == nil {
		t.Fatal("expected decision, but got nil")
	}

	if decision.TaskID != "HC-001" {
		t.Errorf("expected TaskID 'HC-001', got '%s'", decision.TaskID)
	}

	if decision.GateName != ReadyToRunGate {
		t.Errorf("expected GateName '%s', got '%s'", ReadyToRunGate, decision.GateName)
	}

	if !decision.Decision {
		t.Error("expected Decision to be true, got false")
	}

	// Verify decision was logged
	log, err := gate.loadDecisionLog()
	if err != nil {
		t.Fatalf("failed to load decision log: %v", err)
	}

	if len(log.Decisions) != 1 {
		t.Errorf("expected 1 decision logged, got %d", len(log.Decisions))
	}
}

// TestPromptReadyToRunRejected tests the READY_TO_RUN gate with rejection
func TestPromptReadyToRunRejected(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	stdin := bytes.NewBufferString("n\n")
	stdout := &bytes.Buffer{}

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, stdin, stdout)

	task := &planner.Task{
		ID:          "HC-002",
		Title:       "API Implementation",
		Description: "Implement REST API",
	}

	workers := []string{"codex"}
	ctx := context.Background()

	approved, decision, err := gate.PromptReadyToRun(ctx, task, workers)

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if approved {
		t.Error("expected rejection, but got approval")
	}

	if decision == nil {
		t.Fatal("expected decision, but got nil")
	}

	if decision.Decision {
		t.Error("expected Decision to be false, got true")
	}
}

// TestPromptReadyToReviewApproved tests the READY_TO_REVIEW gate with approval
func TestPromptReadyToReviewApproved(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	stdin := bytes.NewBufferString("yes\n")
	stdout := &bytes.Buffer{}

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, stdin, stdout)

	task := &planner.Task{
		ID:    "HC-003",
		Title: "Database Schema",
	}

	results := map[string]*adapter.BuildReport{
		"claude": {
			Status:         "BUILD_COMPLETE",
			FilesChanged:   []string{"schema.sql", "migrations.sql"},
			Assumptions:    []string{"Using PostgreSQL"},
			RemainingRisks: []string{"Performance impact on large tables"},
		},
		"codex": {
			Status:         "BUILD_COMPLETE",
			FilesChanged:   []string{"models.go"},
			Assumptions:    []string{"ORM selected"},
			RemainingRisks: []string{},
		},
	}

	ctx := context.Background()

	approved, decision, err := gate.PromptReadyToReview(ctx, task, results)

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !approved {
		t.Error("expected approval, but got rejection")
	}

	if decision == nil {
		t.Fatal("expected decision, but got nil")
	}

	if decision.GateName != ReadyToReviewGate {
		t.Errorf("expected GateName '%s', got '%s'", ReadyToReviewGate, decision.GateName)
	}

	if !decision.Decision {
		t.Error("expected Decision to be true, got false")
	}
}

// TestPromptReadyToReviewRejected tests the READY_TO_REVIEW gate with rejection
func TestPromptReadyToReviewRejected(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	stdin := bytes.NewBufferString("no\n")
	stdout := &bytes.Buffer{}

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, stdin, stdout)

	task := &planner.Task{
		ID:    "HC-004",
		Title: "Testing Framework",
	}

	results := map[string]*adapter.BuildReport{
		"claude": {
			Status:         "BUILD_BLOCKED",
			FilesChanged:   []string{},
			RemainingRisks: []string{"critical: test coverage below threshold"},
		},
	}

	ctx := context.Background()

	approved, decision, err := gate.PromptReadyToReview(ctx, task, results)

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if approved {
		t.Error("expected rejection, but got approval")
	}

	if decision.Decision {
		t.Error("expected Decision to be false, got true")
	}
}

// TestDecisionLogging tests that decisions are properly logged to persistent storage
func TestDecisionLogging(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, nil, nil)

	decision1 := &GateDecision{
		GateName:   ReadyToRunGate,
		TaskID:     "HC-005",
		ApprovedBy: "user@example.com",
		Timestamp:  time.Now(),
		Decision:   true,
		Comments:   "Looks good",
	}

	decision2 := &GateDecision{
		GateName:   ReadyToReviewGate,
		TaskID:     "HC-005",
		ApprovedBy: "user@example.com",
		Timestamp:  time.Now(),
		Decision:   true,
		Comments:   "Approved for merge",
	}

	if err := gate.logDecision(decision1); err != nil {
		t.Fatalf("failed to log decision 1: %v", err)
	}

	if err := gate.logDecision(decision2); err != nil {
		t.Fatalf("failed to log decision 2: %v", err)
	}

	// Verify file exists and contains both decisions
	data, err := os.ReadFile(decisionPath)
	if err != nil {
		t.Fatalf("failed to read decision file: %v", err)
	}

	var log DecisionLog
	if err := json.Unmarshal(data, &log); err != nil {
		t.Fatalf("failed to unmarshal decision log: %v", err)
	}

	if len(log.Decisions) != 2 {
		t.Errorf("expected 2 decisions logged, got %d", len(log.Decisions))
	}

	// Verify permission bits are restrictive (0600)
	fileInfo, err := os.Stat(decisionPath)
	if err != nil {
		t.Fatalf("failed to stat decision file: %v", err)
	}

	perms := fileInfo.Mode().Perm()
	expectedPerms := os.FileMode(0600)
	if perms != expectedPerms {
		t.Errorf("expected file permissions 0600, got %o", perms)
	}
}

// TestGetDecisionHistory tests retrieving decision history for a task
func TestGetDecisionHistory(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, nil, nil)

	// Log decisions for different tasks
	decisions := []GateDecision{
		{
			GateName:   ReadyToRunGate,
			TaskID:     "HC-006",
			ApprovedBy: "alice@example.com",
			Timestamp:  time.Now(),
			Decision:   true,
		},
		{
			GateName:   ReadyToReviewGate,
			TaskID:     "HC-006",
			ApprovedBy: "alice@example.com",
			Timestamp:  time.Now().Add(time.Hour),
			Decision:   true,
		},
		{
			GateName:   ReadyToRunGate,
			TaskID:     "HC-007",
			ApprovedBy: "bob@example.com",
			Timestamp:  time.Now(),
			Decision:   false,
		},
	}

	for _, decision := range decisions {
		if err := gate.logDecision(&decision); err != nil {
			t.Fatalf("failed to log decision: %v", err)
		}
	}

	// Get history for HC-006
	history, err := gate.GetDecisionHistory("HC-006")
	if err != nil {
		t.Fatalf("failed to get decision history: %v", err)
	}

	if len(history) != 2 {
		t.Errorf("expected 2 decisions for HC-006, got %d", len(history))
	}

	for _, d := range history {
		if d.TaskID != "HC-006" {
			t.Errorf("expected TaskID 'HC-006', got '%s'", d.TaskID)
		}
	}

	// Verify correct gates for HC-006
	if history[0].GateName != ReadyToRunGate {
		t.Errorf("expected first gate to be %s, got %s", ReadyToRunGate, history[0].GateName)
	}
	if history[1].GateName != ReadyToReviewGate {
		t.Errorf("expected second gate to be %s, got %s", ReadyToReviewGate, history[1].GateName)
	}

	// Get history for HC-007
	history, err = gate.GetDecisionHistory("HC-007")
	if err != nil {
		t.Fatalf("failed to get decision history: %v", err)
	}

	if len(history) != 1 {
		t.Errorf("expected 1 decision for HC-007, got %d", len(history))
	}

	// Verify HC-007 is rejected
	if history[0].Decision {
		t.Error("expected HC-007 decision to be rejected (false), but got approved (true)")
	}
}

// TestTimeoutHandling tests that the gate times out correctly
func TestTimeoutHandling(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	// Create a pipe that never receives input
	reader, _ := io.Pipe()
	stdout := &bytes.Buffer{}

	gate := NewGateWithConfig(decisionPath, 100*time.Millisecond, 10*time.Second, reader, stdout)

	task := &planner.Task{
		ID:    "HC-008",
		Title: "Timeout Test",
	}

	workers := []string{"claude"}
	ctx := context.Background()

	start := time.Now()
	approved, _, err := gate.PromptReadyToRun(ctx, task, workers)
	elapsed := time.Since(start)

	if err == nil || !strings.Contains(err.Error(), "timeout") {
		t.Errorf("expected timeout error, got: %v", err)
	}

	if approved {
		t.Error("expected rejection on timeout, got approval")
	}

	// Verify timeout actually waited
	if elapsed < 100*time.Millisecond {
		t.Errorf("timeout was too short: %v", elapsed)
	}
}

// TestContextCancelledHandling tests that the gate respects context cancellation
func TestContextCancelledHandling(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	stdin := &bytes.Buffer{}
	stdout := &bytes.Buffer{}

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, stdin, stdout)

	task := &planner.Task{
		ID:    "HC-009",
		Title: "Context Cancel Test",
	}

	workers := []string{"claude"}
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // Cancel immediately

	approved, _, err := gate.PromptReadyToRun(ctx, task, workers)

	if err == nil || !strings.Contains(err.Error(), "cancelled") {
		t.Errorf("expected context cancelled error, got: %v", err)
	}

	if approved {
		t.Error("expected rejection on context cancellation")
	}
}

// TestEmptyDecisionHistory tests getting history for a task with no decisions
func TestEmptyDecisionHistory(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, nil, nil)

	history, err := gate.GetDecisionHistory("HC-999")
	if err != nil {
		t.Fatalf("failed to get decision history: %v", err)
	}

	if len(history) != 0 {
		t.Errorf("expected empty history for HC-999, got %d decisions", len(history))
	}
}

// TestMultipleTasks tests handling multiple tasks with different workers
func TestMultipleTasks(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")
	stdout := &bytes.Buffer{}

	tasks := []struct {
		ID      string
		Title   string
		Workers []string
	}{
		{"HC-010", "Auth System", []string{"claude", "codex"}},
		{"HC-011", "API Gateway", []string{"codex", "copilot"}},
		{"HC-012", "Database", []string{"claude"}},
	}

	ctx := context.Background()

	for _, tc := range tasks {
		// Create a fresh stdin for each task
		stdin := bytes.NewBufferString("y\n")
		gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, stdin, stdout)

		task := &planner.Task{
			ID:    tc.ID,
			Title: tc.Title,
		}

		approved, decision, err := gate.PromptReadyToRun(ctx, task, tc.Workers)

		if err != nil {
			t.Fatalf("task %s: unexpected error: %v", tc.ID, err)
		}

		if !approved {
			t.Errorf("task %s: expected approval", tc.ID)
		}

		if decision.TaskID != tc.ID {
			t.Errorf("task %s: expected TaskID '%s', got '%s'", tc.ID, tc.ID, decision.TaskID)
		}
	}

	// Verify all decisions are logged
	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, nil, stdout)

	for _, tc := range tasks {
		history, err := gate.GetDecisionHistory(tc.ID)
		if err != nil {
			t.Fatalf("failed to get decision history for %s: %v", tc.ID, err)
		}

		if len(history) != 1 {
			t.Errorf("expected 1 decision for %s, got %d", tc.ID, len(history))
		}
	}
}

// TestGateDecisionStructure tests the GateDecision struct fields
func TestGateDecisionStructure(t *testing.T) {
	decision := &GateDecision{
		GateName:    ReadyToRunGate,
		TaskID:      "HC-013",
		ExecutionID: "exec-001",
		ApprovedBy:  "user@example.com",
		Timestamp:   time.Now(),
		Decision:    true,
		Comments:    "Test comment",
	}

	if decision.GateName != ReadyToRunGate {
		t.Errorf("expected GateName %s, got %s", ReadyToRunGate, decision.GateName)
	}

	if decision.TaskID != "HC-013" {
		t.Errorf("expected TaskID HC-013, got %s", decision.TaskID)
	}

	if decision.ExecutionID != "exec-001" {
		t.Errorf("expected ExecutionID exec-001, got %s", decision.ExecutionID)
	}

	if decision.ApprovedBy != "user@example.com" {
		t.Errorf("expected ApprovedBy user@example.com, got %s", decision.ApprovedBy)
	}

	if !decision.Decision {
		t.Error("expected Decision to be true")
	}

	if decision.Comments != "Test comment" {
		t.Errorf("expected Comments 'Test comment', got '%s'", decision.Comments)
	}
}

// TestLoadNonexistentDecisionLog tests loading decision log when file doesn't exist
func TestLoadNonexistentDecisionLog(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "nonexistent.json")

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, nil, nil)

	log, err := gate.loadDecisionLog()
	if err != nil {
		t.Fatalf("expected no error for nonexistent log, got: %v", err)
	}

	if log == nil {
		t.Fatal("expected empty log, got nil")
	}

	if len(log.Decisions) != 0 {
		t.Errorf("expected empty decisions list, got %d", len(log.Decisions))
	}
}

// TestNewGateDefaults tests that NewGate creates a gate with defaults
func TestNewGateDefaults(t *testing.T) {
	gate := NewGate()

	if gate.decisionFilePath == "" {
		t.Error("expected decisionFilePath to be set")
	}

	if gate.readyToRunTimeout == 0 {
		t.Error("expected readyToRunTimeout to be set")
	}

	if gate.readyToReviewTimeout == 0 {
		t.Error("expected readyToReviewTimeout to be set")
	}

	if gate.readyToRunTimeout != 5*time.Minute {
		t.Errorf("expected readyToRunTimeout 5m, got %v", gate.readyToRunTimeout)
	}

	if gate.readyToReviewTimeout != 10*time.Minute {
		t.Errorf("expected readyToReviewTimeout 10m, got %v", gate.readyToReviewTimeout)
	}
}

// TestDisplayOutput tests that proper output is displayed to stdout
func TestDisplayOutput(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	stdin := bytes.NewBufferString("y\n")
	stdout := &bytes.Buffer{}

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, stdin, stdout)

	task := &planner.Task{
		ID:    "HC-014",
		Title: "Output Test",
	}

	workers := []string{"claude", "codex"}
	ctx := context.Background()

	gate.PromptReadyToRun(ctx, task, workers)

	output := stdout.String()

	if !strings.Contains(output, "HUMAN GATE") {
		t.Error("expected 'HUMAN GATE' in output")
	}

	if !strings.Contains(output, "HC-014") {
		t.Error("expected task ID in output")
	}

	if !strings.Contains(output, "claude") {
		t.Error("expected worker name in output")
	}
}

// TestReviewDisplayOutput tests that proper output is displayed for review gate
func TestReviewDisplayOutput(t *testing.T) {
	tmpFile := t.TempDir()
	decisionPath := filepath.Join(tmpFile, "decisions.json")

	stdin := bytes.NewBufferString("y\n")
	stdout := &bytes.Buffer{}

	gate := NewGateWithConfig(decisionPath, 5*time.Second, 10*time.Second, stdin, stdout)

	task := &planner.Task{
		ID:    "HC-015",
		Title: "Review Display Test",
	}

	results := map[string]*adapter.BuildReport{
		"claude": {
			Status:         "BUILD_COMPLETE",
			FilesChanged:   []string{"file1.go", "file2.go"},
			Assumptions:    []string{"Assumption 1"},
			RemainingRisks: []string{"Risk 1"},
		},
	}

	ctx := context.Background()

	gate.PromptReadyToReview(ctx, task, results)

	output := stdout.String()

	if !strings.Contains(output, "review") {
		t.Error("expected 'review' in output")
	}

	if !strings.Contains(output, "HC-015") {
		t.Error("expected task ID in output")
	}

	if !strings.Contains(output, "Results Summary") {
		t.Error("expected results summary in output")
	}

	if !strings.Contains(output, "claude") {
		t.Error("expected worker name in output")
	}

	if !strings.Contains(output, "BUILD_COMPLETE") {
		t.Error("expected build status in output")
	}
}
