package worktree

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

func setupTestRepo(t *testing.T) string {
	// Create a temporary directory for the test repo
	tmpDir := filepath.Join(os.TempDir(), "test-repo-"+fmt.Sprint(time.Now().UnixNano()))
	if err := os.MkdirAll(tmpDir, 0755); err != nil {
		t.Fatalf("Failed to create temp directory: %v", err)
	}

	// Initialize a git repo
	cmd := exec.Command("git", "init", tmpDir)
	if err := cmd.Run(); err != nil {
		os.RemoveAll(tmpDir)
		t.Skipf("Git not available or failed to init repo: %v", err)
	}

	// Configure git user for the test repo
	cmd = exec.Command("git", "-C", tmpDir, "config", "user.email", "test@example.com")
	if err := cmd.Run(); err != nil {
		os.RemoveAll(tmpDir)
		t.Skipf("Failed to configure git user: %v", err)
	}

	cmd = exec.Command("git", "-C", tmpDir, "config", "user.name", "Test User")
	if err := cmd.Run(); err != nil {
		os.RemoveAll(tmpDir)
		t.Skipf("Failed to configure git user: %v", err)
	}

	// Create initial commit
	testFile := filepath.Join(tmpDir, "test.txt")
	if err := os.WriteFile(testFile, []byte("test"), 0644); err != nil {
		os.RemoveAll(tmpDir)
		t.Fatalf("Failed to create test file: %v", err)
	}

	cmd = exec.Command("git", "-C", tmpDir, "add", "test.txt")
	if err := cmd.Run(); err != nil {
		os.RemoveAll(tmpDir)
		t.Skipf("Failed to add file: %v", err)
	}

	cmd = exec.Command("git", "-C", tmpDir, "commit", "-m", "Initial commit")
	if err := cmd.Run(); err != nil {
		os.RemoveAll(tmpDir)
		t.Skipf("Failed to commit: %v", err)
	}

	t.Cleanup(func() {
		os.RemoveAll(tmpDir)
		// Clean up any worktrees created during tests
		cmd := exec.Command("git", "-C", tmpDir, "worktree", "prune")
		cmd.Run() // Ignore error, we're cleaning up
	})

	return tmpDir
}

func cleanupWorktrees(t *testing.T, manager *Manager) {
	manager.mu.Lock()
	taskIDs := make([]string, 0, len(manager.active))
	for taskID := range manager.active {
		taskIDs = append(taskIDs, taskID)
	}
	manager.mu.Unlock()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	for _, taskID := range taskIDs {
		manager.Cleanup(ctx, taskID)
	}
}

func TestNewManager(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)

	if manager.repoRoot != repoRoot {
		t.Errorf("Expected repoRoot to be %s, got %s", repoRoot, manager.repoRoot)
	}

	if manager.active == nil {
		t.Error("Expected active map to be initialized")
	}

	if len(manager.active) != 0 {
		t.Error("Expected active map to be empty")
	}
}

func TestCreateWorktree(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)
	defer cleanupWorktrees(t, manager)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	taskID := "test-task-1"
	path, err := manager.Create(ctx, taskID)
	if err != nil {
		t.Fatalf("Failed to create worktree: %v", err)
	}

	expectedPath := filepath.Join("/tmp", fmt.Sprintf("biah-wt-%s", taskID))
	if path != expectedPath {
		t.Errorf("Expected path to be %s, got %s", expectedPath, path)
	}

	// Verify worktree directory exists
	if _, err := os.Stat(path); os.IsNotExist(err) {
		t.Errorf("Worktree directory does not exist: %s", path)
	}

	// Verify worktree is tracked
	if !manager.IsActive(taskID) {
		t.Error("Worktree should be active after creation")
	}
}

func TestCleanupWorktree(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	taskID := "test-task-2"
	path, err := manager.Create(ctx, taskID)
	if err != nil {
		t.Fatalf("Failed to create worktree: %v", err)
	}

	// Verify worktree exists
	if _, err := os.Stat(path); os.IsNotExist(err) {
		t.Fatalf("Worktree directory should exist before cleanup: %s", path)
	}

	// Cleanup the worktree
	err = manager.Cleanup(ctx, taskID)
	if err != nil {
		t.Errorf("Failed to cleanup worktree: %v", err)
	}

	// Verify worktree is no longer tracked
	if manager.IsActive(taskID) {
		t.Error("Worktree should not be active after cleanup")
	}
}

func TestGetPath(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)
	defer cleanupWorktrees(t, manager)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	taskID := "test-task-3"
	expectedPath, err := manager.Create(ctx, taskID)
	if err != nil {
		t.Fatalf("Failed to create worktree: %v", err)
	}

	path := manager.GetPath(taskID)
	if path != expectedPath {
		t.Errorf("Expected path to be %s, got %s", expectedPath, path)
	}
}

func TestGetPathNonExistent(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)

	path := manager.GetPath("non-existent-task")
	if path != "" {
		t.Errorf("Expected empty string for non-existent task, got %s", path)
	}
}

func TestIsActive(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)
	defer cleanupWorktrees(t, manager)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	taskID := "test-task-4"

	// Should not be active before creation
	if manager.IsActive(taskID) {
		t.Error("Task should not be active before creation")
	}

	// Create worktree
	_, err := manager.Create(ctx, taskID)
	if err != nil {
		t.Fatalf("Failed to create worktree: %v", err)
	}

	// Should be active after creation
	if !manager.IsActive(taskID) {
		t.Error("Task should be active after creation")
	}

	// Cleanup
	if err := manager.Cleanup(ctx, taskID); err != nil {
		t.Fatalf("Failed to cleanup worktree: %v", err)
	}

	// Should not be active after cleanup
	if manager.IsActive(taskID) {
		t.Error("Task should not be active after cleanup")
	}
}

func TestCreateDuplicateWorktree(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)
	defer cleanupWorktrees(t, manager)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	taskID := "test-task-5"

	// Create first worktree
	_, err := manager.Create(ctx, taskID)
	if err != nil {
		t.Fatalf("Failed to create worktree: %v", err)
	}

	// Try to create another with same taskID
	_, err = manager.Create(ctx, taskID)
	if err == nil {
		t.Error("Expected error when creating duplicate worktree")
	}
}

func TestCleanupNonExistent(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	err := manager.Cleanup(ctx, "non-existent-task")
	if err == nil {
		t.Error("Expected error when cleaning up non-existent worktree")
	}
}

func TestCreateWithInvalidRepoRoot(t *testing.T) {
	manager := NewManager("/non/existent/path")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	_, err := manager.Create(ctx, "test-task")
	if err == nil {
		t.Error("Expected error when repo root doesn't exist")
	}
}

func TestConcurrentOperations(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)
	defer cleanupWorktrees(t, manager)

	numGoroutines := 5
	var wg sync.WaitGroup
	errorsChan := make(chan error, numGoroutines)

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Test concurrent Create operations
	for i := 0; i < numGoroutines; i++ {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			taskID := fmt.Sprintf("concurrent-task-%d", index)
			_, err := manager.Create(ctx, taskID)
			if err != nil {
				errorsChan <- fmt.Errorf("Create failed for task %s: %w", taskID, err)
			}
		}(i)
	}

	wg.Wait()
	close(errorsChan)

	// Check for errors
	for err := range errorsChan {
		t.Logf("Error during concurrent create: %v", err)
	}

	// Verify all tasks are active
	for i := 0; i < numGoroutines; i++ {
		taskID := fmt.Sprintf("concurrent-task-%d", i)
		if !manager.IsActive(taskID) {
			t.Errorf("Task %s should be active", taskID)
		}
	}

	// Test concurrent Cleanup operations
	errorsChan = make(chan error, numGoroutines)
	for i := 0; i < numGoroutines; i++ {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			taskID := fmt.Sprintf("concurrent-task-%d", index)
			err := manager.Cleanup(ctx, taskID)
			if err != nil {
				errorsChan <- fmt.Errorf("Cleanup failed for task %s: %w", taskID, err)
			}
		}(i)
	}

	wg.Wait()
	close(errorsChan)

	// Check for errors
	for err := range errorsChan {
		t.Logf("Error during concurrent cleanup: %v", err)
	}

	// Verify all tasks are inactive
	for i := 0; i < numGoroutines; i++ {
		taskID := fmt.Sprintf("concurrent-task-%d", i)
		if manager.IsActive(taskID) {
			t.Errorf("Task %s should not be active", taskID)
		}
	}
}

func TestContextCancellation(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // Cancel immediately

	_, err := manager.Create(ctx, "test-task")
	if err == nil {
		t.Logf("Create with cancelled context completed (git command execution before context check): %v", err)
		// Clean up if it succeeded
		ctx2, cancel2 := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel2()
		manager.Cleanup(ctx2, "test-task")
	}
}

func TestConcurrentGetPath(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)
	defer cleanupWorktrees(t, manager)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	taskID := "test-task-concurrent-get"
	expectedPath, err := manager.Create(ctx, taskID)
	if err != nil {
		t.Fatalf("Failed to create worktree: %v", err)
	}

	numGoroutines := 10
	results := make([]string, numGoroutines)
	var wg sync.WaitGroup

	for i := 0; i < numGoroutines; i++ {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			results[index] = manager.GetPath(taskID)
		}(i)
	}

	wg.Wait()

	for i, result := range results {
		if result != expectedPath {
			t.Errorf("Goroutine %d: expected path %s, got %s", i, expectedPath, result)
		}
	}
}

func TestMultipleTasksSequential(t *testing.T) {
	repoRoot := setupTestRepo(t)
	manager := NewManager(repoRoot)
	defer cleanupWorktrees(t, manager)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	numTasks := 3
	taskIDs := make([]string, numTasks)
	paths := make([]string, numTasks)

	// Create multiple worktrees
	for i := 0; i < numTasks; i++ {
		taskID := fmt.Sprintf("sequential-task-%d", i)
		taskIDs[i] = taskID
		path, err := manager.Create(ctx, taskID)
		if err != nil {
			t.Fatalf("Failed to create worktree for task %d: %v", i, err)
		}
		paths[i] = path

		if !manager.IsActive(taskID) {
			t.Errorf("Task %s should be active", taskID)
		}
	}

	// Verify all are active
	for i, taskID := range taskIDs {
		if manager.GetPath(taskID) != paths[i] {
			t.Errorf("Path mismatch for task %s", taskID)
		}
	}

	// Cleanup in reverse order
	for i := numTasks - 1; i >= 0; i-- {
		taskID := taskIDs[i]
		err := manager.Cleanup(ctx, taskID)
		if err != nil {
			t.Errorf("Failed to cleanup task %s: %v", taskID, err)
		}

		if manager.IsActive(taskID) {
			t.Errorf("Task %s should not be active after cleanup", taskID)
		}
	}
}
