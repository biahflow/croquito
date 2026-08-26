package planner

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// Task represents a single unit of work
type Task struct {
	ID           string   `yaml:"id"`
	Title        string   `yaml:"title"`
	Description  string   `yaml:"description"`
	Role         string   `yaml:"role"` // builder, reviewer, etc.
	Requires     []string `yaml:"requires"`
	Dependencies []string `yaml:"dependencies"`
	CreatedAt    time.Time
}

// DAGNode represents a task in the directed acyclic graph
type DAGNode struct {
	Task         *Task
	Dependencies []*DAGNode
	DependedBy   []*DAGNode
}

// DAG represents the task dependency graph
type DAG struct {
	Nodes map[string]*DAGNode
	Root  []*DAGNode // Tasks with no dependencies
}

// LoadTask loads a task contract from file
func LoadTask(taskID string) (*Task, error) {
	// Get current working directory
	cwd, err := os.Getwd()
	if err != nil {
		cwd = "."
	}

	// Try multiple possible locations for the tasks directory
	possiblePaths := []string{
		filepath.Join("tasks", taskID, "contract.md"),
		filepath.Join("..", "tasks", taskID, "contract.md"),
		filepath.Join("..", "..", "tasks", taskID, "contract.md"),
		filepath.Join(cwd, "tasks", taskID, "contract.md"),
		filepath.Join(cwd, "..", "tasks", taskID, "contract.md"),
	}

	var content []byte
	var usedPath string

	for _, path := range possiblePaths {
		data, err := os.ReadFile(path)
		if err == nil {
			content = data
			usedPath = path
			break
		}
	}

	if content == nil {
		return nil, fmt.Errorf("failed to read task contract for %s in any of the searched paths", taskID)
	}

	// Parse YAML frontmatter
	contentStr := string(content)
	if !strings.HasPrefix(contentStr, "---") {
		return nil, fmt.Errorf("task contract %s missing YAML frontmatter", usedPath)
	}

	// Find the end of frontmatter
	parts := strings.Split(contentStr, "---")
	if len(parts) < 3 {
		return nil, fmt.Errorf("task contract %s has invalid YAML frontmatter", usedPath)
	}

	yamlContent := parts[1]

	// Parse YAML with both "id" and "task_id" support
	rawData := make(map[string]interface{})
	err = yaml.Unmarshal([]byte(yamlContent), rawData)
	if err != nil {
		return nil, fmt.Errorf("failed to parse YAML in %s: %w", usedPath, err)
	}

	// Build Task struct, handling both id and task_id
	task := &Task{
		CreatedAt: time.Now(),
	}

	// Extract ID (prefer task_id, fall back to id, then use taskID parameter)
	if v, ok := rawData["task_id"].(string); ok && v != "" {
		task.ID = v
	} else if v, ok := rawData["id"].(string); ok && v != "" {
		task.ID = v
	} else {
		task.ID = taskID
	}

	// Extract Title
	if v, ok := rawData["title"].(string); ok {
		task.Title = v
	}

	// Extract Description
	if v, ok := rawData["description"].(string); ok {
		task.Description = v
	}

	// Extract Role
	if v, ok := rawData["role"].(string); ok {
		task.Role = v
	}

	// Extract Requires
	if v, ok := rawData["requires"].([]interface{}); ok {
		for _, item := range v {
			if s, ok := item.(string); ok {
				task.Requires = append(task.Requires, s)
			}
		}
	}

	// Extract Dependencies
	if v, ok := rawData["dependencies"].([]interface{}); ok {
		for _, item := range v {
			if s, ok := item.(string); ok {
				task.Dependencies = append(task.Dependencies, s)
			}
		}
	}

	// Validate required fields
	if task.Title == "" {
		return nil, fmt.Errorf("task contract %s missing title field", usedPath)
	}

	return task, nil
}

// BuildDAG constructs a directed acyclic graph from a root task
func BuildDAG(rootTask *Task) (*DAG, error) {
	nodes := make(map[string]*DAGNode)
	visited := make(map[string]bool)
	var circularDepErr error

	dag := &DAG{
		Nodes: nodes,
		Root:  []*DAGNode{},
	}

	// Recursively load dependencies
	_, err := buildDAGRecursive(rootTask, nodes, visited, &circularDepErr)
	if err != nil {
		return nil, err
	}

	if circularDepErr != nil {
		return nil, circularDepErr
	}

	// Identify actual root nodes (tasks with no dependencies)
	for _, node := range nodes {
		if len(node.Dependencies) == 0 {
			dag.Root = append(dag.Root, node)
		}
	}

	return dag, nil
}

func buildDAGRecursive(task *Task, nodes map[string]*DAGNode, visited map[string]bool, circularErr *error) (*DAGNode, error) {
	// Handle nil task
	if task == nil {
		return nil, fmt.Errorf("cannot build DAG from nil task")
	}

	// Mark as visiting (detect cycles) - check BEFORE nodes map
	if visited[task.ID] {
		*circularErr = fmt.Errorf("circular dependency detected: task %s", task.ID)
		return nil, *circularErr
	}

	// Check if already fully processed
	if node, exists := nodes[task.ID]; exists {
		return node, nil
	}

	visited[task.ID] = true

	// Create node for this task
	node := &DAGNode{
		Task:         task,
		Dependencies: []*DAGNode{},
		DependedBy:   []*DAGNode{},
	}
	nodes[task.ID] = node

	// Load and process dependencies
	for _, depID := range task.Dependencies {
		depTask, err := LoadTask(depID)
		if err != nil {
			return nil, fmt.Errorf("failed to load dependency %s for task %s: %w", depID, task.ID, err)
		}

		depNode, err := buildDAGRecursive(depTask, nodes, visited, circularErr)
		if err != nil {
			return nil, err
		}

		if *circularErr != nil {
			return nil, *circularErr
		}

		// Link dependency
		node.Dependencies = append(node.Dependencies, depNode)
		depNode.DependedBy = append(depNode.DependedBy, node)
	}

	// Unmark as visiting
	visited[task.ID] = false

	return node, nil
}

// ValidateDAG checks for cycles, orphans, and other issues
func ValidateDAG(dag *DAG) error {
	if len(dag.Root) == 0 {
		return fmt.Errorf("DAG has no root nodes")
	}

	reachable := make(map[string]bool)

	// Check reachability from all root nodes
	for _, root := range dag.Root {
		markReachable(root, reachable)
	}

	// Check for unreachable nodes (orphans)
	for nodeID := range dag.Nodes {
		if !reachable[nodeID] {
			return fmt.Errorf("unreachable/orphan node: %s", nodeID)
		}
	}

	// Check for cycles using DFS
	for _, root := range dag.Root {
		visited := make(map[string]bool)
		recStack := make(map[string]bool)
		if hasCycle(root, visited, recStack) {
			return fmt.Errorf("circular dependency detected in DAG")
		}
	}

	return nil
}

func markReachable(node *DAGNode, reachable map[string]bool) {
	if reachable[node.Task.ID] {
		return
	}
	reachable[node.Task.ID] = true

	for _, dep := range node.DependedBy {
		markReachable(dep, reachable)
	}
}

func hasCycle(node *DAGNode, visited map[string]bool, recStack map[string]bool) bool {
	visited[node.Task.ID] = true
	recStack[node.Task.ID] = true

	for _, dep := range node.Dependencies {
		if !visited[dep.Task.ID] {
			if hasCycle(dep, visited, recStack) {
				return true
			}
		} else if recStack[dep.Task.ID] {
			return true
		}
	}

	recStack[node.Task.ID] = false
	return false
}

// TopologicalSort returns tasks in execution order using Kahn's algorithm
func TopologicalSort(dag *DAG) ([]*Task, error) {
	// Calculate in-degree for each node
	inDegree := make(map[string]int)
	for nodeID, node := range dag.Nodes {
		inDegree[nodeID] = len(node.Dependencies)
	}

	// Find all nodes with no dependencies
	queue := []*DAGNode{}
	for _, node := range dag.Nodes {
		if inDegree[node.Task.ID] == 0 {
			queue = append(queue, node)
		}
	}

	result := []*Task{}
	processed := make(map[string]bool)

	for len(queue) > 0 {
		// Dequeue
		current := queue[0]
		queue = queue[1:]

		result = append(result, current.Task)
		processed[current.Task.ID] = true

		// Process nodes that depend on current
		for _, dependent := range current.DependedBy {
			inDegree[dependent.Task.ID]--
			if inDegree[dependent.Task.ID] == 0 {
				queue = append(queue, dependent)
			}
		}
	}

	// Check if all nodes were processed (detect cycles)
	if len(result) != len(dag.Nodes) {
		return nil, fmt.Errorf("topological sort failed: circular dependencies detected")
	}

	return result, nil
}

// PrintDAG prints the DAG in human-readable format
func PrintDAG(dag *DAG) {
	fmt.Println("DAG (Directed Acyclic Graph):")
	for _, root := range dag.Root {
		printNodeTree(root, "  ")
	}
}

func printNodeTree(node *DAGNode, indent string) {
	fmt.Printf("%s├─ %s: %s\n", indent, node.Task.ID, node.Task.Title)
	for _, dep := range node.DependedBy {
		printNodeTree(dep, indent+"  ")
	}
}
