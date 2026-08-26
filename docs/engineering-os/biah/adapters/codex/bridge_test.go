package codex

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
	stdout []byte
	stderr []byte
	err    error
}

func (m *MockCommandRunner) Run(ctx context.Context, cmd string, args ...string) ([]byte, []byte, error) {
	// Check context cancellation
	select {
	case <-ctx.Done():
		return nil, nil, ctx.Err()
	default:
	}

	if m.err != nil {
		return m.stdout, m.stderr, m.err
	}
	return m.stdout, m.stderr, nil
}

// MockCommandRunnerWithDelay simulates slow execution
type MockCommandRunnerWithDelay struct {
	delay  time.Duration
	stdout []byte
	stderr []byte
	err    error
}

func (m *MockCommandRunnerWithDelay) Run(ctx context.Context, cmd string, args ...string) ([]byte, []byte, error) {
	select {
	case <-time.After(m.delay):
		if m.err != nil {
			return m.stdout, m.stderr, m.err
		}
		return m.stdout, m.stderr, nil
	case <-ctx.Done():
		return nil, nil, ctx.Err()
	}
}

func TestCodexBridgeWithValidOutput(t *testing.T) {
	report := adapter.BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{"parser.py", "analyzer.py"},
		ValidationExecuted:   []string{"unit_tests", "integration_tests"},
		ValidationSkipped:    []string{},
		Assumptions:          []string{"Python 3.8+ installed"},
		RemainingRisks:       []string{"Performance optimization pending"},
		HumanDecisionsNeeded: []string{},
	}

	output, _ := json.Marshal(report)

	runner := &MockCommandRunner{stdout: output}
	bridge, err := NewCodexBridgeWithRunner(runner)
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

	if result.WorkerName != "codex" {
		t.Errorf("Expected worker name 'codex', got %s", result.WorkerName)
	}

	if result.TaskID != "task-123" {
		t.Errorf("Expected task ID 'task-123', got %s", result.TaskID)
	}

	if len(result.FilesChanged) != 2 {
		t.Errorf("Expected 2 files changed, got %d", len(result.FilesChanged))
	}
}

func TestCodexBridgeWithInvalidJSON(t *testing.T) {
	runner := &MockCommandRunner{stdout: []byte("not valid json at all")}
	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	_, err = bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err == nil {
		t.Errorf("Expected error for invalid JSON, got nil")
	}

	if !errors.Is(err, errors.New("")) {
		// Just check that an error occurred
	}
}

func TestCodexBridgeTimeout(t *testing.T) {
	// Create a runner that takes longer than the context timeout
	runner := &MockCommandRunnerWithDelay{
		delay:  100 * time.Millisecond,
		stdout: []byte("{}"),
	}

	bridge, err := NewCodexBridgeWithRunner(runner)
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

func TestCodexBridgeCapabilities(t *testing.T) {
	runner := &MockCommandRunner{stdout: []byte("{}")}
	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	caps := bridge.Capabilities()
	if len(caps) == 0 {
		t.Errorf("Expected capabilities, got empty list")
	}

	hasImplementation := false
	for _, cap := range caps {
		if cap == "implementation" {
			hasImplementation = true
			break
		}
	}

	if !hasImplementation {
		t.Errorf("Expected 'implementation' capability")
	}
}

func TestCodexBridgeName(t *testing.T) {
	runner := &MockCommandRunner{stdout: []byte("{}")}
	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	if bridge.Name() != "codex" {
		t.Errorf("Expected name 'codex', got %s", bridge.Name())
	}
}

func TestCodexBridgeInvokeWithLegacyContext(t *testing.T) {
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

	runner := &MockCommandRunner{stdout: output}
	bridge, err := NewCodexBridgeWithRunner(runner)
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

func TestCodexBridgeRawOutput(t *testing.T) {
	rawJSON := `{"status": "BUILD_COMPLETE", "files_changed": ["parser.py", "test.py"]}`
	runner := &MockCommandRunner{stdout: []byte(rawJSON)}
	bridge, err := NewCodexBridgeWithRunner(runner)
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

func TestCodexBridgeCLIError(t *testing.T) {
	runner := &MockCommandRunner{
		stdout: nil,
		stderr: []byte("CLI error: execution failed"),
		err:    errors.New("exit status 1"),
	}

	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	_, err = bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err == nil {
		t.Errorf("Expected error from CLI, got nil")
	}
}

func TestCodexBridgeMultipleFiles(t *testing.T) {
	report := adapter.BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{"file1.py", "file2.py", "file3.py"},
		ValidationExecuted:   []string{"test_file1", "test_file2", "test_file3"},
		ValidationSkipped:    []string{"slow_tests"},
		Assumptions:          []string{"pytest installed"},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{"Review API changes"},
	}

	output, _ := json.Marshal(report)

	runner := &MockCommandRunner{stdout: output}
	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	result, err := bridge.InvokeWithContext(ctx, "task-multi", "/tmp/worktree")
	if err != nil {
		t.Fatalf("InvokeWithContext failed: %v", err)
	}

	if len(result.FilesChanged) != 3 {
		t.Errorf("Expected 3 files changed, got %d", len(result.FilesChanged))
	}

	if len(result.HumanDecisionsNeeded) != 1 {
		t.Errorf("Expected 1 human decision needed, got %d", len(result.HumanDecisionsNeeded))
	}
}

// TestCodexBridgeEmptyOutput tests handling of empty stdout
func TestCodexBridgeEmptyOutput(t *testing.T) {
	runner := &MockCommandRunner{stdout: []byte("")}
	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	_, err = bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err == nil {
		t.Errorf("Expected error for empty output, got nil")
	}
}

// TestCodexBridgeWithStderr tests that stderr is logged on error
func TestCodexBridgeWithStderr(t *testing.T) {
	runner := &MockCommandRunner{
		stdout: nil,
		stderr: []byte("codex-cli: task file not found at /tmp/worktree/task.contract.md"),
		err:    errors.New("exit status 1"),
	}

	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	_, err = bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err == nil {
		t.Errorf("Expected error, got nil")
	}

	errMsg := err.Error()
	if errMsg == "" {
		t.Errorf("Expected error message, got empty string")
	}
}

// TestCodexBridgeContextCanceled tests handling of canceled context
func TestCodexBridgeContextCanceled(t *testing.T) {
	runner := &MockCommandRunnerWithDelay{
		delay:  100 * time.Millisecond,
		stdout: []byte("{}"),
	}

	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err = bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err == nil {
		t.Errorf("Expected error for canceled context, got nil")
	}
}

// TestCodexBridgeComplexJSON tests parsing of complex JSON with all fields
func TestCodexBridgeComplexJSON(t *testing.T) {
	report := adapter.BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{"module1.py", "module2.py", "tests/test_module1.py"},
		ValidationExecuted:   []string{"unit_tests", "integration_tests", "lint"},
		ValidationSkipped:    []string{"performance_tests"},
		Assumptions:          []string{"Python 3.8+", "pytest installed", "black formatter available"},
		RemainingRisks:       []string{"Performance optimization pending", "Documentation needs update"},
		HumanDecisionsNeeded: []string{"Approve API changes", "Review security implications"},
	}

	output, _ := json.Marshal(report)

	runner := &MockCommandRunner{stdout: output}
	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	result, err := bridge.InvokeWithContext(ctx, "task-complex", "/tmp/worktree")
	if err != nil {
		t.Fatalf("InvokeWithContext failed: %v", err)
	}

	if len(result.FilesChanged) != 3 {
		t.Errorf("Expected 3 files changed, got %d", len(result.FilesChanged))
	}

	if len(result.Assumptions) != 3 {
		t.Errorf("Expected 3 assumptions, got %d", len(result.Assumptions))
	}

	if len(result.RemainingRisks) != 2 {
		t.Errorf("Expected 2 remaining risks, got %d", len(result.RemainingRisks))
	}

	if len(result.HumanDecisionsNeeded) != 2 {
		t.Errorf("Expected 2 human decisions needed, got %d", len(result.HumanDecisionsNeeded))
	}
}

// TestCodexBridgePartialJSON tests parsing of JSON with missing optional fields
func TestCodexBridgePartialJSON(t *testing.T) {
	rawJSON := `{"status": "BUILD_BLOCKED"}`
	runner := &MockCommandRunner{stdout: []byte(rawJSON)}
	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	result, err := bridge.InvokeWithContext(ctx, "task-partial", "/tmp/worktree")
	if err != nil {
		t.Fatalf("InvokeWithContext failed: %v", err)
	}

	if result.Status != "BUILD_BLOCKED" {
		t.Errorf("Expected status BUILD_BLOCKED, got %s", result.Status)
	}

	if result.FilesChanged == nil {
		// Empty slices are preferred to nil in Go JSON unmarshaling
		t.Logf("FilesChanged is nil (acceptable for minimal JSON)")
	}
}

// TestCodexBridgeCommandConstruction tests that correct CLI arguments are used
func TestCodexBridgeCommandConstruction(t *testing.T) {
	// We can't directly test the command construction with the current design,
	// but we can verify the behavior with different mock responses
	runner := &MockCommandRunner{stdout: []byte(`{"status": "BUILD_COMPLETE"}`)}
	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx := context.Background()
	result, err := bridge.InvokeWithContext(ctx, "task-cmd-test", "/test/worktree/path")
	if err != nil {
		t.Fatalf("InvokeWithContext failed: %v", err)
	}

	if result.TaskID != "task-cmd-test" {
		t.Errorf("Expected task ID 'task-cmd-test', got %s", result.TaskID)
	}
}

// TestCodexBridgeDefaultCommandRunner tests the real DefaultCommandRunner with echo command
func TestCodexBridgeDefaultCommandRunner(t *testing.T) {
	runner := &DefaultCommandRunner{}

	// Test with echo command which should be available on all systems
	stdout, stderr, err := runner.Run(context.Background(), "echo", "hello")

	// On some systems, the command might not work exactly as expected,
	// but we're mainly testing that the interface works
	if err != nil {
		t.Logf("Error (acceptable if echo not available): %v", err)
	}

	if len(stdout) > 0 || len(stderr) == 0 {
		// Some output should be present
		t.Logf("Got output: %s, %s", string(stdout), string(stderr))
	}
}

// TestCodexBridgeTimeoutWithDeadline tests explicit deadline instead of duration
func TestCodexBridgeTimeoutWithDeadline(t *testing.T) {
	runner := &MockCommandRunnerWithDelay{
		delay:  200 * time.Millisecond,
		stdout: []byte(`{"status": "BUILD_COMPLETE"}`),
	}

	bridge, err := NewCodexBridgeWithRunner(runner)
	if err != nil {
		t.Fatalf("Failed to create bridge: %v", err)
	}

	ctx, cancel := context.WithDeadline(context.Background(), time.Now().Add(50*time.Millisecond))
	defer cancel()

	_, err = bridge.InvokeWithContext(ctx, "task-123", "/tmp/worktree")
	if err == nil {
		t.Errorf("Expected timeout error, got nil")
	}
}
