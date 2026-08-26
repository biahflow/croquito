package executor

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/biahflow/engineering-os/biah/pkg/adapter"
	"github.com/biahflow/engineering-os/biah/pkg/planner"
	"github.com/biahflow/engineering-os/biah/pkg/router"
)

// TaskStatus represents the status of a task
type TaskStatus string

const (
	TaskStatusPending   TaskStatus = "PENDING"
	TaskStatusRunning   TaskStatus = "RUNNING"
	TaskStatusSuccess   TaskStatus = "SUCCESS"
	TaskStatusFailure   TaskStatus = "FAILURE"
	TaskStatusBlocked   TaskStatus = "BLOCKED"
	TaskStatusTimeout   TaskStatus = "TIMEOUT"
	TaskStatusCancelled TaskStatus = "CANCELLED"
)

// TaskResult holds the result of a single task execution
type TaskResult struct {
	TaskID      string
	Status      TaskStatus
	WorkerName  string
	BuildReport *adapter.BuildReport
	Error       string
	DurationMs  int64
	StartTime   time.Time
	EndTime     time.Time
}

// ExecutionResult holds the results of executing all tasks in a DAG
type ExecutionResult struct {
	Status          string
	TotalTasks      int
	SuccessfulTasks int
	FailedTasks     int
	BlockedTasks    int
	TaskResults     map[string]*TaskResult
	ExecutionTimeMs int64
	FailureReasons  []string
}

// WorktreeManagerInterface defines the interface for worktree management
type WorktreeManagerInterface interface {
	Create(ctx context.Context, taskID string) (string, error)
	Cleanup(ctx context.Context, taskID string) error
	GetPath(taskID string) string
	IsActive(taskID string) bool
}

// AdapterRegistryInterface defines the interface for adapter registry
type AdapterRegistryInterface interface {
	Get(name string) (adapter.Adapter, error)
}

// Executor runs tasks in parallel respecting DAG dependencies
type Executor struct {
	dag         *planner.DAG
	assignments map[string]*router.Assignment
	adapterReg  AdapterRegistryInterface
	worktreeMgr WorktreeManagerInterface

	mu             sync.Mutex
	taskStatus     map[string]TaskStatus
	taskResults    map[string]*TaskResult
	failureReasons []string
	failedTasks    map[string]bool
}

// NewExecutor creates a new executor
func NewExecutor(
	dag *planner.DAG,
	assignments map[string]*router.Assignment,
	adapterReg AdapterRegistryInterface,
	worktreeMgr WorktreeManagerInterface,
) *Executor {
	return &Executor{
		dag:         dag,
		assignments: assignments,
		adapterReg:  adapterReg,
		worktreeMgr: worktreeMgr,
		taskStatus:  make(map[string]TaskStatus),
		taskResults: make(map[string]*TaskResult),
		failedTasks: make(map[string]bool),
	}
}

// Execute runs all tasks in the DAG respecting dependencies
func (e *Executor) Execute(ctx context.Context) (*ExecutionResult, error) {
	startTime := time.Now()
	fmt.Println("Executing tasks...")

	// Initialize task status for all tasks
	for taskID := range e.dag.Nodes {
		e.taskStatus[taskID] = TaskStatusPending
	}

	// Topologically sort the DAG
	sorted, err := e.topologicalSort()
	if err != nil {
		return nil, err
	}

	// Track which tasks have been started
	started := make(map[string]bool)
	var wg sync.WaitGroup

	// Create a done channel to track completion
	doneChan := make(chan string, len(e.dag.Nodes))

	// Execute tasks in waves, respecting dependencies
	for i := 0; i < len(sorted); {
		// Find all tasks that can be executed now (no pending dependencies)
		readyTasks := e.findReadyTasks(sorted, started)

		if len(readyTasks) == 0 {
			// No more tasks can be executed, but we may have pending tasks
			// This shouldn't happen if the DAG is valid
			break
		}

		// Start all ready tasks in parallel
		for _, taskID := range readyTasks {
			wg.Add(1)
			go func(tid string) {
				defer wg.Done()
				e.executeTask(ctx, tid, doneChan)
			}(taskID)
			started[taskID] = true
			e.setTaskStatus(taskID, TaskStatusRunning)
		}

		// Wait for at least one task to complete
		select {
		case <-ctx.Done():
			// Context cancelled, cleanup all active worktrees
			e.cleanupAll(ctx)
			return nil, ctx.Err()
		case <-doneChan:
			// Task completed, continue to next iteration
		}

		// Count started tasks to advance through the sorted list
		count := 0
		for _, taskID := range sorted[:i+len(readyTasks)] {
			if started[taskID] {
				count++
			}
		}
		i = count
	}

	// Wait for all goroutines to complete
	wg.Wait()

	// Close the done channel
	close(doneChan)

	// Mark tasks with failed dependencies as BLOCKED if they were never started
	for taskID := range e.dag.Nodes {
		if !started[taskID] {
			// Task was never started, check if any dependency failed
			dagNode := e.dag.Nodes[taskID]
			hasFailed := false
			for _, depNode := range dagNode.Dependencies {
				if e.isTaskFailed(depNode.Task.ID) {
					hasFailed = true
					break
				}
			}
			if hasFailed {
				taskResult := &TaskResult{
					TaskID:    taskID,
					Status:    TaskStatusBlocked,
					StartTime: time.Now(),
					EndTime:   time.Now(),
				}
				e.mu.Lock()
				e.taskResults[taskID] = taskResult
				e.taskStatus[taskID] = TaskStatusBlocked
				e.mu.Unlock()
			}
		}
	}

	// Cleanup all worktrees
	e.cleanupAll(ctx)

	// Build execution result
	endTime := time.Now()
	result := e.buildExecutionResult(endTime.Sub(startTime))

	return result, nil
}

// executeTask executes a single task
func (e *Executor) executeTask(ctx context.Context, taskID string, doneChan chan<- string) {
	defer func() { doneChan <- taskID }()

	taskResult := &TaskResult{
		TaskID:    taskID,
		Status:    TaskStatusRunning,
		StartTime: time.Now(),
	}
	defer func() {
		taskResult.EndTime = time.Now()
		taskResult.DurationMs = taskResult.EndTime.Sub(taskResult.StartTime).Milliseconds()
		e.mu.Lock()
		e.taskResults[taskID] = taskResult
		e.mu.Unlock()
	}()

	// Check if context was cancelled
	select {
	case <-ctx.Done():
		taskResult.Status = TaskStatusCancelled
		taskResult.Error = "execution cancelled"
		e.setTaskStatus(taskID, TaskStatusCancelled)
		return
	default:
	}

	// Check if any dependency failed
	dagNode := e.dag.Nodes[taskID]
	for _, depNode := range dagNode.Dependencies {
		if e.isTaskFailed(depNode.Task.ID) {
			taskResult.Status = TaskStatusBlocked
			taskResult.Error = "dependency failed"
			e.setTaskStatus(taskID, TaskStatusBlocked)
			return
		}
	}

	// Get assignment
	assignment := e.assignments[taskID]
	if assignment == nil || assignment.Worker == "" || assignment.Worker == "unknown" {
		taskResult.Status = TaskStatusFailure
		taskResult.Error = "no worker assigned"
		e.setTaskStatus(taskID, TaskStatusFailure)
		e.addFailureReason(fmt.Sprintf("Task %s: no worker assigned", taskID))
		e.failedTasks[taskID] = true
		return
	}

	// Get adapter
	adp, err := e.adapterReg.Get(assignment.Worker)
	if err != nil {
		taskResult.Status = TaskStatusFailure
		taskResult.Error = fmt.Sprintf("failed to get adapter: %v", err)
		e.setTaskStatus(taskID, TaskStatusFailure)
		e.addFailureReason(fmt.Sprintf("Task %s: %v", taskID, err))
		e.failedTasks[taskID] = true
		return
	}

	taskResult.WorkerName = adp.Name()
	fmt.Printf("Executing task: %s (worker: %s)\n", taskID, adp.Name())

	// Create worktree
	wtPath, err := e.worktreeMgr.Create(ctx, taskID)
	if err != nil {
		taskResult.Status = TaskStatusFailure
		taskResult.Error = fmt.Sprintf("failed to create worktree: %v", err)
		e.setTaskStatus(taskID, TaskStatusFailure)
		e.addFailureReason(fmt.Sprintf("Task %s: failed to create worktree: %v", taskID, err))
		e.failedTasks[taskID] = true
		return
	}

	// Invoke adapter with context
	report, err := adp.InvokeWithContext(ctx, taskID, wtPath)
	if err != nil {
		taskResult.Status = TaskStatusFailure
		taskResult.Error = fmt.Sprintf("adapter invocation failed: %v", err)
		e.setTaskStatus(taskID, TaskStatusFailure)
		e.addFailureReason(fmt.Sprintf("Task %s: adapter invocation failed: %v", taskID, err))
		e.failedTasks[taskID] = true
		return
	}

	// Check the report status
	taskResult.BuildReport = report
	if report.Status == "BUILD_COMPLETE" || report.Status == "SUCCESS" {
		taskResult.Status = TaskStatusSuccess
		e.setTaskStatus(taskID, TaskStatusSuccess)
	} else if report.Status == "BUILD_BLOCKED" {
		taskResult.Status = TaskStatusBlocked
		e.setTaskStatus(taskID, TaskStatusBlocked)
	} else {
		taskResult.Status = TaskStatusFailure
		e.setTaskStatus(taskID, TaskStatusFailure)
		e.addFailureReason(fmt.Sprintf("Task %s: build failed with status %s", taskID, report.Status))
		e.failedTasks[taskID] = true
	}
}

// topologicalSort performs a topological sort of the DAG
func (e *Executor) topologicalSort() ([]string, error) {
	var result []string
	visited := make(map[string]bool)
	visiting := make(map[string]bool)

	for taskID := range e.dag.Nodes {
		if !visited[taskID] {
			err := e.topologicalSortDFS(taskID, visited, visiting, &result)
			if err != nil {
				return nil, err
			}
		}
	}

	return result, nil
}

// topologicalSortDFS performs DFS for topological sort
func (e *Executor) topologicalSortDFS(taskID string, visited, visiting map[string]bool, result *[]string) error {
	if visited[taskID] {
		return nil
	}

	if visiting[taskID] {
		return fmt.Errorf("circular dependency detected involving task %s", taskID)
	}

	visiting[taskID] = true

	dagNode := e.dag.Nodes[taskID]
	for _, depNode := range dagNode.Dependencies {
		err := e.topologicalSortDFS(depNode.Task.ID, visited, visiting, result)
		if err != nil {
			return err
		}
	}

	visiting[taskID] = false
	visited[taskID] = true
	*result = append(*result, taskID)

	return nil
}

// findReadyTasks finds all tasks that have no pending dependencies
func (e *Executor) findReadyTasks(sorted []string, started map[string]bool) []string {
	var ready []string

	for _, taskID := range sorted {
		if started[taskID] {
			continue // Already started
		}

		// Check if all dependencies are complete and successful
		dagNode := e.dag.Nodes[taskID]
		allDepsComplete := true
		anyDepFailed := false

		for _, depNode := range dagNode.Dependencies {
			depID := depNode.Task.ID
			if !started[depID] {
				allDepsComplete = false
				break
			}

			status := e.getTaskStatus(depID)
			if status == TaskStatusFailure {
				anyDepFailed = true
				break
			}
			// Dependencies must be complete (SUCCESS), not just running
			if status != TaskStatusSuccess {
				allDepsComplete = false
				break
			}
		}

		if allDepsComplete && !anyDepFailed {
			ready = append(ready, taskID)
		}
	}

	return ready
}

// Helper functions for thread-safe status management

func (e *Executor) setTaskStatus(taskID string, status TaskStatus) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.taskStatus[taskID] = status
}

func (e *Executor) getTaskStatus(taskID string) TaskStatus {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.taskStatus[taskID]
}

func (e *Executor) isTaskFailed(taskID string) bool {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.failedTasks[taskID]
}

func (e *Executor) addFailureReason(reason string) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.failureReasons = append(e.failureReasons, reason)
}

// cleanupAll cleans up all active worktrees
func (e *Executor) cleanupAll(ctx context.Context) {
	for taskID := range e.dag.Nodes {
		// Ignore errors during cleanup
		_ = e.worktreeMgr.Cleanup(ctx, taskID)
	}
}

// buildExecutionResult constructs the final execution result
func (e *Executor) buildExecutionResult(duration time.Duration) *ExecutionResult {
	e.mu.Lock()
	defer e.mu.Unlock()

	result := &ExecutionResult{
		TotalTasks:      len(e.dag.Nodes),
		TaskResults:     e.taskResults,
		ExecutionTimeMs: duration.Milliseconds(),
		FailureReasons:  e.failureReasons,
	}

	// Count task statuses
	for _, taskResult := range e.taskResults {
		switch taskResult.Status {
		case TaskStatusSuccess:
			result.SuccessfulTasks++
		case TaskStatusFailure:
			result.FailedTasks++
		case TaskStatusBlocked:
			result.BlockedTasks++
		}
	}

	// Determine overall status
	if result.FailedTasks > 0 || result.BlockedTasks > 0 {
		if result.SuccessfulTasks > 0 {
			result.Status = "PARTIAL"
		} else {
			result.Status = "FAILURE"
		}
	} else if result.SuccessfulTasks == result.TotalTasks {
		result.Status = "SUCCESS"
	} else {
		result.Status = "INCOMPLETE"
	}

	return result
}

// Results returns the execution results (legacy support)
func (e *Executor) Results() map[string]*adapter.BuildReport {
	e.mu.Lock()
	defer e.mu.Unlock()

	results := make(map[string]*adapter.BuildReport)
	for taskID, taskResult := range e.taskResults {
		if taskResult.BuildReport != nil {
			results[taskID] = taskResult.BuildReport
		}
	}
	return results
}
