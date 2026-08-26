package adapter

import (
	"context"
	"fmt"
)

// BuildReport represents the fixed-format output from a worker
type BuildReport struct {
	Status               string   `json:"status"` // BUILD_COMPLETE, BUILD_BLOCKED, etc.
	FilesChanged         []string `json:"files_changed"`
	ValidationExecuted   []string `json:"validation_executed"`
	ValidationSkipped    []string `json:"validation_skipped"`
	Assumptions          []string `json:"assumptions"`
	RemainingRisks       []string `json:"remaining_risks"`
	HumanDecisionsNeeded []string `json:"human_decisions_required"`
	WorkerName           string   `json:"worker_name"`
	TaskID               string   `json:"task_id"`
	RawOutput            string   `json:"raw_output"`
}

// WorktreeContext holds the execution context for a task
type WorktreeContext struct {
	TaskID       string
	WorktreePath string
	EnvVars      map[string]string
	Timeout      int // seconds
}

// Adapter is the interface all workers must implement
type Adapter interface {
	Name() string
	Capabilities() []string
	Invoke(ctx *WorktreeContext) (*BuildReport, error)
	InvokeWithContext(ctx context.Context, taskID string, worktreePath string) (*BuildReport, error)
}

// ClaudeAdapter is the stub adapter for Claude
type ClaudeAdapter struct{}

func (a *ClaudeAdapter) Name() string {
	return "claude"
}

func (a *ClaudeAdapter) Capabilities() []string {
	return []string{
		"architecture_reasoning",
		"large_context",
		"refactoring",
	}
}

func (a *ClaudeAdapter) Invoke(ctx *WorktreeContext) (*BuildReport, error) {
	fmt.Printf("Claude adapter invoking task %s (stub)\n", ctx.TaskID)
	return &BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
	}, nil
}

func (a *ClaudeAdapter) InvokeWithContext(ctx context.Context, taskID string, worktreePath string) (*BuildReport, error) {
	fmt.Printf("Claude adapter invoking task %s (stub with context)\n", taskID)
	return &BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "claude",
		TaskID:               taskID,
	}, nil
}

// CodexAdapter is the stub adapter for Codex
type CodexAdapter struct{}

func (a *CodexAdapter) Name() string {
	return "codex"
}

func (a *CodexAdapter) Capabilities() []string {
	return []string{
		"implementation",
		"debugging",
		"testing",
		"code_review",
	}
}

func (a *CodexAdapter) Invoke(ctx *WorktreeContext) (*BuildReport, error) {
	fmt.Printf("Codex adapter invoking task %s (stub)\n", ctx.TaskID)
	return &BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
	}, nil
}

func (a *CodexAdapter) InvokeWithContext(ctx context.Context, taskID string, worktreePath string) (*BuildReport, error) {
	fmt.Printf("Codex adapter invoking task %s (stub with context)\n", taskID)
	return &BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "codex",
		TaskID:               taskID,
	}, nil
}

// CopilotAdapter is the stub adapter for Copilot
type CopilotAdapter struct{}

func (a *CopilotAdapter) Name() string {
	return "copilot"
}

func (a *CopilotAdapter) Capabilities() []string {
	return []string{
		"implementation",
		"github_native",
		"repository_operations",
	}
}

func (a *CopilotAdapter) Invoke(ctx *WorktreeContext) (*BuildReport, error) {
	fmt.Printf("Copilot adapter invoking task %s (stub)\n", ctx.TaskID)
	return &BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
	}, nil
}

func (a *CopilotAdapter) InvokeWithContext(ctx context.Context, taskID string, worktreePath string) (*BuildReport, error) {
	fmt.Printf("Copilot adapter invoking task %s (stub with context)\n", taskID)
	return &BuildReport{
		Status:               "BUILD_COMPLETE",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "copilot",
		TaskID:               taskID,
	}, nil
}

// AdapterRegistry holds all available adapters
type AdapterRegistry struct {
	adapters map[string]Adapter
}

// NewRegistry creates a new adapter registry
func NewRegistry() *AdapterRegistry {
	return &AdapterRegistry{
		adapters: map[string]Adapter{
			"claude":  &ClaudeAdapter{},
			"codex":   &CodexAdapter{},
			"copilot": &CopilotAdapter{},
		},
	}
}

// Get retrieves an adapter by name
func (r *AdapterRegistry) Get(name string) (Adapter, error) {
	adapter, ok := r.adapters[name]
	if !ok {
		return nil, fmt.Errorf("unknown adapter: %s", name)
	}
	return adapter, nil
}
