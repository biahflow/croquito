package worktree

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
)

// Manager handles git worktree lifecycle
type Manager struct {
	repoRoot string
	mu       sync.Mutex
	active   map[string]string // taskID -> worktree path
}

// NewManager creates a new worktree manager
func NewManager(repoRoot string) *Manager {
	return &Manager{
		repoRoot: repoRoot,
		active:   make(map[string]string),
	}
}

// Create creates an isolated git worktree for a task
func (m *Manager) Create(ctx context.Context, taskID string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Check if worktree already exists for this task
	if _, exists := m.active[taskID]; exists {
		return "", fmt.Errorf("worktree already exists for task: %s", taskID)
	}

	// Generate worktree path
	worktreePath := filepath.Join("/tmp", fmt.Sprintf("biah-wt-%s", taskID))

	// Verify repo root exists
	if _, err := os.Stat(m.repoRoot); os.IsNotExist(err) {
		return "", fmt.Errorf("repository root does not exist: %s", m.repoRoot)
	}

	// Create a unique branch for this worktree
	branchName := fmt.Sprintf("worktree-%s", taskID)

	// Create the worktree using git worktree add with a detached HEAD or new branch
	createCmd := exec.CommandContext(ctx, "git", "-C", m.repoRoot, "worktree", "add", "-b", branchName, worktreePath)
	if output, err := createCmd.CombinedOutput(); err != nil {
		return "", fmt.Errorf("failed to create worktree: %w (output: %s)", err, string(output))
	}

	// Track the worktree
	m.active[taskID] = worktreePath

	return worktreePath, nil
}

// Cleanup removes a git worktree
func (m *Manager) Cleanup(ctx context.Context, taskID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	worktreePath, exists := m.active[taskID]
	if !exists {
		return fmt.Errorf("worktree not found for task: %s", taskID)
	}

	// Remove the worktree using git worktree remove
	removeCmd := exec.CommandContext(ctx, "git", "-C", m.repoRoot, "worktree", "remove", worktreePath, "--force")
	if output, err := removeCmd.CombinedOutput(); err != nil {
		return fmt.Errorf("failed to remove worktree: %w (output: %s)", err, string(output))
	}

	// Untrack the worktree
	delete(m.active, taskID)

	return nil
}

// GetPath returns the worktree path for a given task
func (m *Manager) GetPath(taskID string) string {
	m.mu.Lock()
	defer m.mu.Unlock()

	return m.active[taskID]
}

// IsActive checks if a worktree exists for the given task
func (m *Manager) IsActive(taskID string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()

	_, exists := m.active[taskID]
	return exists
}
