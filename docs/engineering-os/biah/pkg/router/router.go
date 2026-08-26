package router

import (
	"fmt"
	"sort"

	"github.com/biahflow/engineering-os/biah/pkg/adapter"
	"github.com/biahflow/engineering-os/biah/pkg/planner"
)

// WorkerMatch represents a matched worker with capability score
type WorkerMatch struct {
	Worker       adapter.Adapter
	Score        int // Percentage 0-100
	CapsMatched  int // Number of matched capabilities
	CapsRequired int // Number of required capabilities
	Ranking      int // Position in sorted results (1-based)
}

// Registry is the interface for accessing workers
type Registry interface {
	Get(name string) (adapter.Adapter, error)
	// ListAll returns all available adapters
	ListAll() []adapter.Adapter
}

// Router matches tasks to workers by capability
type Router struct {
	registry Registry
}

// NewRouter creates a new router with a given registry
func NewRouter(registry Registry) *Router {
	return &Router{
		registry: registry,
	}
}

// Route assigns a task to ranked workers based on capability matching
func (r *Router) Route(task *planner.Task) ([]WorkerMatch, error) {
	// Handle nil registry
	if r.registry == nil {
		return nil, fmt.Errorf("router has no registry")
	}

	// Handle nil task
	if task == nil {
		return nil, fmt.Errorf("task is nil")
	}

	// Handle empty requirements - return all workers with score 100
	if len(task.Requires) == 0 {
		workers := r.registry.ListAll()
		matches := make([]WorkerMatch, len(workers))
		for i, w := range workers {
			matches[i] = WorkerMatch{
				Worker:       w,
				Score:        100,
				CapsMatched:  0,
				CapsRequired: 0,
				Ranking:      i + 1,
			}
		}
		return matches, nil
	}

	// Get all workers and score them
	workers := r.registry.ListAll()
	matches := make([]WorkerMatch, 0, len(workers))

	for _, worker := range workers {
		match := r.scoreWorker(worker, task.Requires)
		if match != nil {
			matches = append(matches, *match)
		}
	}

	// If no workers match all requirements, return error
	if len(matches) == 0 {
		return nil, fmt.Errorf("no workers match required capabilities: %v", task.Requires)
	}

	// Sort matches by score descending (higher score first)
	sort.Slice(matches, func(i, j int) bool {
		if matches[i].Score != matches[j].Score {
			return matches[i].Score > matches[j].Score
		}
		// Tiebreaker: maintain stable order by worker name
		return matches[i].Worker.Name() < matches[j].Worker.Name()
	})

	// Assign rankings
	for i := range matches {
		matches[i].Ranking = i + 1
	}

	return matches, nil
}

// scoreWorker calculates the match score for a worker against required capabilities
func (r *Router) scoreWorker(worker adapter.Adapter, required []string) *WorkerMatch {
	if worker == nil || len(required) == 0 {
		return nil
	}

	workerCaps := worker.Capabilities()
	if len(workerCaps) == 0 {
		return nil
	}

	// Build a map for fast lookup
	capMap := make(map[string]bool)
	for _, cap := range workerCaps {
		capMap[cap] = true
	}

	// Count matched capabilities
	matched := 0
	for _, req := range required {
		if capMap[req] {
			matched++
		}
	}

	// If no capabilities match, don't include this worker
	if matched == 0 {
		return nil
	}

	// Calculate score as percentage: (matched / required) * 100, rounded
	score := (matched * 100) / len(required)

	return &WorkerMatch{
		Worker:       worker,
		Score:        score,
		CapsMatched:  matched,
		CapsRequired: len(required),
		Ranking:      0, // Will be set after sorting
	}
}

// Assignment maps a task to a worker (legacy support)
type Assignment struct {
	TaskID string
	Worker string
	Score  float64 // Match score (0-1)
}

// AssignTask finds the best worker for a task (legacy support)
func (r *Router) AssignTask(task *planner.Task) *Assignment {
	matches, err := r.Route(task)
	if err != nil {
		return &Assignment{
			TaskID: task.ID,
			Worker: "unknown",
			Score:  0.0,
		}
	}

	if len(matches) == 0 {
		return &Assignment{
			TaskID: task.ID,
			Worker: "unknown",
			Score:  0.0,
		}
	}

	// Return the best match
	best := matches[0]
	return &Assignment{
		TaskID: task.ID,
		Worker: best.Worker.Name(),
		Score:  float64(best.Score) / 100.0,
	}
}

// AssignTasks assigns all tasks in a DAG (legacy support)
func (r *Router) AssignTasks(dag *planner.DAG) map[string]*Assignment {
	assignments := make(map[string]*Assignment)

	for id, node := range dag.Nodes {
		assignment := r.AssignTask(node.Task)
		assignments[id] = assignment
	}

	return assignments
}

// PrintAssignments prints the routing plan (legacy support)
func PrintAssignments(assignments map[string]*Assignment) {
	fmt.Println("\nRouting by capability:")
	for _, a := range assignments {
		fmt.Printf("  %s → %s (score: %.2f)\n", a.TaskID, a.Worker, a.Score)
	}
}
