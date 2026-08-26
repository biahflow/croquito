package claude

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
	output, err := command.CombinedOutput()
	return output, err
}

// ClaudeBridge is the real CLI implementation for Claude
type ClaudeBridge struct {
	cliPath string
	runner  CommandRunner
}

// NewClaudeBridge creates a new Claude bridge, detecting CLI availability
func NewClaudeBridge() (*ClaudeBridge, error) {
	cliPath, err := findCLI("claude-cli")
	if err != nil {
		return nil, fmt.Errorf("claude-cli not found, install with: brew install claude-cli")
	}

	return &ClaudeBridge{
		cliPath: cliPath,
		runner:  &DefaultCommandRunner{},
	}, nil
}

// NewClaudeBridgeWithRunner creates a new Claude bridge with a custom command runner
// Used for testing - bypasses CLI lookup since runner is mocked
func NewClaudeBridgeWithRunner(runner CommandRunner) (*ClaudeBridge, error) {
	return &ClaudeBridge{
		cliPath: "claude-cli",
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
func (cb *ClaudeBridge) Name() string {
	return "claude"
}

// Capabilities returns the capabilities of Claude
func (cb *ClaudeBridge) Capabilities() []string {
	return []string{
		"architecture_reasoning",
		"large_context",
		"refactoring",
	}
}

// Invoke is the legacy method for compatibility
func (cb *ClaudeBridge) Invoke(ctx *adapter.WorktreeContext) (*adapter.BuildReport, error) {
	timeout := time.Duration(ctx.Timeout) * time.Second
	bkgCtx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	return cb.InvokeWithContext(bkgCtx, ctx.TaskID, ctx.WorktreePath)
}

// InvokeWithContext invokes the Claude CLI with proper timeout handling
func (cb *ClaudeBridge) InvokeWithContext(ctx context.Context, taskID string, worktreePath string) (*adapter.BuildReport, error) {
	taskFile := filepath.Join(worktreePath, "task.contract.md")

	// Construct command: claude-cli execute --task=<TASK_ID> --task-file=<PATH> --output-dir=<WORKTREE> --output=json
	output, err := cb.runner.Run(ctx, cb.cliPath, "execute",
		"--task="+taskID,
		"--task-file="+taskFile,
		"--output-dir="+worktreePath,
		"--output=json")

	if err != nil {
		// Context deadline exceeded - timeout
		if ctx.Err() == context.DeadlineExceeded {
			return nil, fmt.Errorf("claude-cli timeout: operation exceeded context deadline")
		}
		// Other errors from CLI execution
		return nil, fmt.Errorf("failed to invoke claude-cli: %w", err)
	}

	// Parse JSON output
	var report adapter.BuildReport
	if err := json.Unmarshal(output, &report); err != nil {
		// Log parsing error but continue with empty report
		return nil, fmt.Errorf("failed to parse claude-cli output: %w", err)
	}

	report.WorkerName = "claude"
	report.TaskID = taskID
	report.RawOutput = string(output)

	return &report, nil
}
