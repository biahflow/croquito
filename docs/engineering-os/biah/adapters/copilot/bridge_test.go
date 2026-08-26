package copilot

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/biahflow/engineering-os/biah/pkg/adapter"
)

// MockCommandRunner implements CommandRunner for testing
type MockCommandRunner struct {
	output []byte
	err    error
}

func (m *MockCommandRunner) Run(ctx context.Context, cmd string, args ...string) ([]byte, error) {
	// Check context cancellation
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}

	if m.err != nil {
		return nil, m.err
	}
	return m.output, nil
}

// MockCommandRunnerWithDelay simulates slow execution
type MockCommandRunnerWithDelay struct {
	delay  time.Duration
	output []byte
	err    error
}

func (m *MockCommandRunnerWithDelay) Run(ctx context.Context, cmd string, args ...string) ([]byte, error) {
	select {
	case <-time.After(m.delay):
		if m.err != nil {
			return nil, m.err
		}
		return m.output, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

func TestCopilotBridgeWithValidOutput(t *testing.T) {
	report := adapter.BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{"main.ts", "app.tsx"},
		ValidationExecuted:   []string{"eslint", "type_check"},
		ValidationSkipped:    []string{},
		Assumptions:          []string{"TypeScript 4.9+ installed"},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
	}

	output, _ := json.Marshal(report)

	runner := &MockCommandRunner{output: output}
	bridge, err := NewCopilotBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	result, err := bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err != nil {
		t.Fatalf("InvokeWithContext failed: %v", err)
	}

	if result.Status != "BUILD_COMPLETE" {
		t.Errorf("Expected status BUILD_COMPLETE, got %s", result.Status)
	}

	if result.WorkerName != "copilot" {
		t.Errorf("Expected worker name 'copilot', got %s", result.WorkerName)
	}

	if result.TaskID != "task-123" {
		t.Errorf("Expected task ID 'task-123', got %s", result.TaskID)
	}

	if len(result.FilesChanged) != 2 {
		t.Errorf("Expected 2 files changed, got %d", len(result.FilesChanged))
	}
}

func TestCopilotBridgeWithInvalidJSON(t *testing.T) {
	runner := &MockCommandRunner{output: []byte("malformed json]")}
	bridge, err := NewCopilotBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	_, err = bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err == nil {
		t.Errorf("Expected error for invalid JSON, got nil")
	}
}

func TestCopilotBridgeTimeout(t *testing.T) {
	// Create a runner that takes longer than the context timeout
	runner := &MockCommandRunnerWithDelay{
		delay:  100 * time.Millisecond,
		output: []byte("{}"),
	}

	bridge, err := NewCopilotBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Millisecond)
	defer cancel()

	_, err = bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err == nil {
		t.Errorf("Expected timeout error, got nil")
	}
}

func TestCopilotBridgeCapabilities(t *testing.T) {
	runner := &MockCommandRunner{output: []byte("{}")}
	bridge, err := NewCopilotBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	caps := bridge.Capabilities()
	if len(caps) == 0 {
		t.Errorf("Expected capabilities, got empty list")
	}

	hasGitHub := false
	for _, cap := range caps {
		if cap == "github_native" {
			hasGitHub = true
			break
		}
	}

	if !hasGitHub {
		t.Errorf("Expected 'github_native' capability")
	}
}

func TestCopilotBridgeName(t *testing.T) {
	runner := &MockCommandRunner{output: []byte("{}")}
	bridge, err := NewCopilotBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	if bridge.Name() != "copilot" {
		t.Errorf("Expected name 'copilot', got %s", bridge.Name())
	}
}

func TestCopilotBridgeInvokeWithLegacyContext(t *testing.T) {
	report := adapter.BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
	}

	output, _ := json.Marshal(report)

	runner := &MockCommandRunner{output: output}
	bridge, err := NewCopilotBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	wtCtx := &adapter.WorktreeContext{
		TaskID:       "task-456",
		WorktreePath: "/tmp/worktree",
		EnvVars:      make(map[string]string),
		Timeout:      30,
	}

	_, err = bridge.Invoke(wtCtx)
	if err != nil {
		t.Logf("Invoke returned error (expected if task file missing): %v", err)
	}
}

func TestCopilotBridgeRawOutput(t *testing.T) {
	rawJSON := `{"status": "BUILD_COMPLETE", "files_changed": ["main.ts"]}`
	runner := &MockCommandRunner{output: []byte(rawJSON)}
	bridge, err := NewCopilotBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	result, err := bridge.InvokeWithContext(ctx, "task-789", "/tmp/worktree")
	if err != nil {
		t.Fatalf("InvokeWithContext failed: %v", err)
	}

	if result.RawOutput != rawJSON {
		t.Errorf("Expected RawOutput to match input, got %s", result.RawOutput)
	}
}

func TestCopilotBridgeCLIError(t *testing.T) {
	runner := &MockCommandRunner{
		output: nil,
		err:    errors.New("CLI error: GitHub API rate limit exceeded"),
	}

	bridge, err := NewCopilotBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	_, err = bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err == nil {
		t.Errorf("Expected error from CLI, got nil")
	}
}

func TestCopilotBridgeRepositoryOperations(t *testing.T) {
	report := adapter.BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{"src/component.tsx", "tests/component.test.tsx", ".github/workflows/ci.yml"},
		ValidationExecuted:   []string{"github_actions", "github_api"},
		ValidationSkipped:    []string{},
		Assumptions:          []string{"GitHub token available", "Push access to repo"},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
	}

	output, _ := json.Marshal(report)

	runner := &MockCommandRunner{output: output}
	bridge, err := NewCopilotBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	result, err := bridge.InvokeWithContext(ctx, "task-repo", "/tmp/worktree")
	if err != nil {
		t.Fatalf("InvokeWithContext failed: %v", err)
	}

	if len(result.FilesChanged) != 3 {
		t.Errorf("Expected 3 files changed, got %d", len(result.FilesChanged))
	}

	// Check for workflow file
	hasWorkflow := false
	for _, file := range result.FilesChanged {
		if file == ".github/workflows/ci.yml" {
			hasWorkflow = true
			break
		}
	}

	if !hasWorkflow {
		t.Errorf("Expected workflow file in changes")
	}
}

func TestCopilotBridgeContextCancellation(t *testing.T) {
	runner := &MockCommandRunnerWithDelay{
		delay:  50 * time.Millisecond,
		output: []byte("{}"),
	}

	bridge, err := NewCopilotBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(5 * time.Millisecond)
		cancel()
	}()

	_, err = bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err == nil {
		t.Errorf("Expected error on context cancellation, got nil")
	}
}
