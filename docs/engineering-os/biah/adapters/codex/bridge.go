package codex

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/biahflow/engineering-os/biah/pkg/adapter"
)

// CommandRunner is an interface for running CLI commands
type CommandRunner interface {
	Run(ctx context.Context, cmd string, args ...string) ([]byte, []byte, error)
}

// DefaultCommandRunner implements CommandRunner using os/exec
type DefaultCommandRunner struct{}

func (d *DefaultCommandRunner) Run(ctx context.Context, cmd string, args ...string) ([]byte, []byte, error) {
	command := exec.CommandContext(ctx, cmd, args...)
	var stdout, stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr

	err := command.Run()
	return stdout.Bytes(), stderr.Bytes(), err
}

// CodexBridge is the real CLI implementation for Codex
type CodexBridge struct {
	cliPath string
	runner  CommandRunner
}

// NewCodexBridge creates a new Codex bridge, detecting CLI availability
func NewCodexBridge() (*CodexBridge, error) {
	cliPath, err := findCLI("codex-cli")
	if err != nil {
		return nil, fmt.Errorf("codex-cli not found, install with: pip install codex-cli")
	}

	return &CodexBridge{
		cliPath: cliPath,
		runner:  &DefaultCommandRunner{},
	}, nil
}

// NewCodexBridgeWithRunner creates a new Codex bridge with a custom command runner
// Used for testing - bypasses CLI lookup since runner is mocked
func NewCodexBridgeWithRunner(runner CommandRunner) (*CodexBridge, error) {
	return &CodexBridge{
		cliPath: "codex-cli",
		runner:  runner,
	}, nil
}

// findCLI searches for a CLI executable in PATH
func findCLI(name string) (string, error) {
	path, err := exec.LookPath(name)
	if err != nil {
		return "", err
	}
	return path, nil
}

// Name returns the adapter name
func (cb *CodexBridge) Name() string {
	return "codex"
}

// Capabilities returns the capabilities of Codex
func (cb *CodexBridge) Capabilities() []string {
	return []string{
		"implementation",
		"debugging",
		"testing",
		"code_review",
	}
}

// Invoke is the legacy method for compatibility
func (cb *CodexBridge) Invoke(ctx *adapter.WorktreeContext) (*adapter.BuildReport, error) {
	timeout := time.Duration(ctx.Timeout) * time.Second
	bkgCtx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	return cb.InvokeWithContext(bkgCtx, ctx.TaskID, ctx.WorktreePath)
}

// InvokeWithContext invokes the Codex CLI with proper timeout handling
func (cb *CodexBridge) InvokeWithContext(ctx context.Context, taskID string, worktreePath string) (*adapter.BuildReport, error) {
	taskFile := filepath.Join(worktreePath, "task.contract.md")

	// Invoke CLI with proper arguments
	args := []string{
		"execute",
		"--task=" + taskID,
		"--task-file=" + taskFile,
		"--output-dir=" + worktreePath,
	}

	stdout, stderr, err := cb.runner.Run(ctx, cb.cliPath, args...)

	// Handle context deadline exceeded
	if ctx.Err() == context.DeadlineExceeded {
		return nil, fmt.Errorf("codex-cli timeout: operation exceeded context deadline")
	}

	// Handle command execution errors
	if err != nil {
		// Check if it's a "command not found" error
		if ctx.Err() == context.Canceled {
			return nil, fmt.Errorf("codex-cli execution canceled")
		}

		// Capture stderr for better error messaging
		stderrStr := string(stderr)
		if stderrStr != "" {
			log.Printf("codex-cli stderr: %s", stderrStr)
		}

		return nil, fmt.Errorf("failed to invoke codex-cli: %w (stderr: %s)", err, stderrStr)
	}

	// Parse JSON output from stdout
	var report adapter.BuildReport
	if len(stdout) == 0 {
		return nil, fmt.Errorf("codex-cli produced no output")
	}

	if err := json.Unmarshal(stdout, &report); err != nil {
		log.Printf("Failed to parse JSON from codex-cli: %v", err)
		log.Printf("Raw output was: %s", string(stdout))
		return nil, fmt.Errorf("failed to parse codex-cli output: %w", err)
	}

	report.WorkerName = "codex"
	report.TaskID = taskID
	report.RawOutput = string(stdout)

	return &report, nil
}
