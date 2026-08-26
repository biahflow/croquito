package copilot

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/biahflow/engineering-os/biah/pkg/adapter"
)

// CommandRunner is an interface for running CLI commands
type CommandRunner interface {
	Run(ctx context.Context, cmd string, args ...string) ([]byte, error)
}

// DefaultCommandRunner implements CommandRunner using os/exec
type DefaultCommandRunner struct{}

func (d *DefaultCommandRunner) Run(ctx context.Context, cmd string, args ...string) ([]byte, error) {
	command := exec.CommandContext(ctx, cmd, args...)
	return command.Output()
}

// CopilotBridge is the real CLI implementation for Copilot
type CopilotBridge struct {
	cliPath string
	runner  CommandRunner
}

// NewCopilotBridge creates a new Copilot bridge, detecting CLI availability
func NewCopilotBridge() (*CopilotBridge, error) {
	cliPath, err := findCLI("copilot-cli")
	if err != nil {
		return nil, fmt.Errorf("copilot-cli not found, install with: npm install -g copilot-cli")
	}

	return &CopilotBridge{
		cliPath: cliPath,
		runner:  &DefaultCommandRunner{},
	}, nil
}

// NewCopilotBridgeWithRunner creates a new Copilot bridge with a custom command runner
// Used for testing - bypasses CLI lookup since runner is mocked
func NewCopilotBridgeWithRunner(runner CommandRunner) (*CopilotBridge, error) {
	return &CopilotBridge{
		cliPath: "copilot-cli",
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
func (cb *CopilotBridge) Name() string {
	return "copilot"
}

// Capabilities returns the capabilities of Copilot
func (cb *CopilotBridge) Capabilities() []string {
	return []string{
		"implementation",
		"github_native",
		"repository_operations",
	}
}

// Invoke is the legacy method for compatibility
func (cb *CopilotBridge) Invoke(ctx *adapter.WorktreeContext) (*adapter.BuildReport, error) {
	timeout := time.Duration(ctx.Timeout) * time.Second
	bkgCtx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	return cb.InvokeWithContext(bkgCtx, ctx.TaskID, ctx.WorktreePath)
}

// InvokeWithContext invokes the Copilot CLI with proper timeout handling
func (cb *CopilotBridge) InvokeWithContext(ctx context.Context, taskID string, worktreePath string) (*adapter.BuildReport, error) {
	taskFile := filepath.Join(worktreePath, "task.contract.md")

	// Invoke CLI - the CLI will handle missing files
	output, err := cb.runner.Run(ctx, cb.cliPath, "execute", "--task-file", taskFile, "--output", "json")
	if err != nil {
		// Context deadline exceeded - timeout
		if ctx.Err() == context.DeadlineExceeded {
			return nil, fmt.Errorf("copilot-cli timeout: operation exceeded context deadline")
		}
		return nil, fmt.Errorf("failed to invoke copilot-cli: %w", err)
	}

	// Parse JSON output
	var report adapter.BuildReport
	if err := json.Unmarshal(output, &report); err != nil {
		return nil, fmt.Errorf("failed to parse copilot-cli output: %w", err)
	}

	report.WorkerName = "copilot"
	report.TaskID = taskID
	report.RawOutput = string(output)

	return &report, nil
}
