package planner

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

// Helper function to create a test task file
func createTestTask(t *testing.T, taskID, title string, dependencies []string) string {
	taskDir := filepath.Join("tasks", taskID)
	err := os.MkdirAll(taskDir, 0755)
	if err != nil {
		t.Fatalf("failed to create task directory: %v", err)
	}

	contractPath := filepath.Join(taskDir, "contract.md")
	content := fmt.Sprintf(`---
id: %s
title: "%s"
description: "Test task for %s"
role: builder
requires:
  - implementation
dependencies: %v
---

# Test Task

This is a test task.
`, taskID, title, taskID, formatDependencies(dependencies))

	err = os.WriteFile(contractPath, []byte(content), 0644)
	if err != nil {
		t.Fatalf("failed to write task contract: %v", err)
	}

	return contractPath
}

// Helper to format dependencies list for YAML
func formatDependencies(deps []string) string {
	if len(deps) == 0 {
		return "[]"
	}
	result := "["
	for i, dep := range deps {
		if i > 0 {
			result += ", "
		}
		result += fmt.Sprintf("\"%s\"", dep)
	}
	result += "]"
	return result
}

// Clean up test tasks
func cleanupTestTasks(t *testing.T, taskIDs ...string) {
	for _, id := range taskIDs {
		taskDir := filepath.Join("tasks", id)
		os.RemoveAll(taskDir)
	}
}

// Test LoadTask with valid file
func TestLoadTask_Valid(t *testing.T) {
	defer cleanupTestTasks(t, "TEST-001")
	createTestTask(t, "TEST-001", "Valid Task", []string{})

	task, err := LoadTask("TEST-001")
	if err != nil {
		t.Fatalf("LoadTask failed: %v", err)
	}

	if task.ID != "TEST-001" {
		t.Errorf("Expected ID TEST-001, got %s", task.ID)
	}

	if task.Title != "Valid Task" {
		t.Errorf("Expected title 'Valid Task', got %s", task.Title)
	}

	if task.Role != "builder" {
		t.Errorf("Expected role 'builder', got %s", task.Role)
	}
}

// Test LoadTask with missing file
func TestLoadTask_MissingFile(t *testing.T) {
	_, err := LoadTask("NONEXISTENT-TASK")
	if err == nil {
		t.Errorf("Expected error for missing task file")
	}
}

// Test LoadTask with malformed YAML
func TestLoadTask_MalformedYAML(t *testing.T) {
	defer cleanupTestTasks(t, "TEST-BAD-YAML")

	taskDir := filepath.Join("tasks", "TEST-BAD-YAML")
	os.MkdirAll(taskDir, 0755)

	contractPath := filepath.Join(taskDir, "contract.md")
	content := `---
id: TEST-BAD-YAML
title: Bad YAML
role: [invalid yaml structure::
---
Content`

	os.WriteFile(contractPath, []byte(content), 0644)

	_, err := LoadTask("TEST-BAD-YAML")
	if err == nil {
		t.Errorf("Expected error for malformed YAML")
	}
}

// Test BuildDAG with single task (no dependencies)
func TestBuildDAG_SingleTask(t *testing.T) {
	defer cleanupTestTasks(t, "TEST-SINGLE")
	createTestTask(t, "TEST-SINGLE", "Single Task", []string{})

	task, err := LoadTask("TEST-SINGLE")
	if err != nil {
		t.Fatalf("LoadTask failed: %v", err)
	}

	dag, err := BuildDAG(task)
	if err != nil {
		t.Fatalf("BuildDAG failed: %v", err)
	}

	if len(dag.Nodes) != 1 {
		t.Errorf("Expected 1 node in DAG, got %d", len(dag.Nodes))
	}

	if len(dag.Root) != 1 {
		t.Errorf("Expected 1 root node, got %d", len(dag.Root))
	}

	if dag.Root[0].Task.ID != "TEST-SINGLE" {
		t.Errorf("Expected root task TEST-SINGLE, got %s", dag.Root[0].Task.ID)
	}
}

// Test BuildDAG with linear chain (A -> B -> C)
func TestBuildDAG_LinearChain(t *testing.T) {
	defer cleanupTestTasks(t, "TEST-C", "TEST-B", "TEST-A")
	createTestTask(t, "TEST-C", "Task C", []string{})
	createTestTask(t, "TEST-B", "Task B", []string{"TEST-C"})
	createTestTask(t, "TEST-A", "Task A", []string{"TEST-B"})

	task, err := LoadTask("TEST-A")
	if err != nil {
		t.Fatalf("LoadTask failed: %v", err)
	}

	dag, err := BuildDAG(task)
	if err != nil {
		t.Fatalf("BuildDAG failed: %v", err)
	}

	if len(dag.Nodes) != 3 {
		t.Errorf("Expected 3 nodes in DAG, got %d", len(dag.Nodes))
	}

	// Check that TEST-C is a root (no dependencies)
	cNode := dag.Nodes["TEST-C"]
	if cNode == nil {
		t.Errorf("Node TEST-C not found in DAG")
	} else if len(cNode.Dependencies) != 0 {
		t.Errorf("Expected TEST-C to have 0 dependencies, got %d", len(cNode.Dependencies))
	}
}

// Test BuildDAG with diamond pattern (A -> B,C; B -> D; C -> D)
func TestBuildDAG_DiamondPattern(t *testing.T) {
	defer cleanupTestTasks(t, "TEST-D-BASE", "TEST-D-LEFT", "TEST-D-RIGHT", "TEST-D-TOP")
	createTestTask(t, "TEST-D-BASE", "Base", []string{})
	createTestTask(t, "TEST-D-LEFT", "Left", []string{"TEST-D-BASE"})
	createTestTask(t, "TEST-D-RIGHT", "Right", []string{"TEST-D-BASE"})
	createTestTask(t, "TEST-D-TOP", "Top", []string{"TEST-D-LEFT", "TEST-D-RIGHT"})

	task, err := LoadTask("TEST-D-TOP")
	if err != nil {
		t.Fatalf("LoadTask failed: %v", err)
	}

	dag, err := BuildDAG(task)
	if err != nil {
		t.Fatalf("BuildDAG failed: %v", err)
	}

	if len(dag.Nodes) != 4 {
		t.Errorf("Expected 4 nodes in DAG, got %d", len(dag.Nodes))
	}

	// Check that BASE is root
	baseNode := dag.Nodes["TEST-D-BASE"]
	if len(baseNode.Dependencies) != 0 {
		t.Errorf("Expected TEST-D-BASE to have 0 dependencies")
	}
}

// Test BuildDAG with circular dependency
func TestBuildDAG_CircularDependency(t *testing.T) {
	defer cleanupTestTasks(t, "TEST-CIRC-A", "TEST-CIRC-B", "TEST-CIRC-C")

	// Create tasks without running the circular dependency check first
	taskDir1 := filepath.Join("tasks", "TEST-CIRC-A")
	os.MkdirAll(taskDir1, 0755)
	os.WriteFile(filepath.Join(taskDir1, "contract.md"), []byte(`---
id: TEST-CIRC-A
title: Task A
role: builder
dependencies: ["TEST-CIRC-B"]
---
Content`), 0644)

	taskDir2 := filepath.Join("tasks", "TEST-CIRC-B")
	os.MkdirAll(taskDir2, 0755)
	os.WriteFile(filepath.Join(taskDir2, "contract.md"), []byte(`---
id: TEST-CIRC-B
title: Task B
role: builder
dependencies: ["TEST-CIRC-A"]
---
Content`), 0644)

	task, err := LoadTask("TEST-CIRC-A")
	if err != nil {
		t.Fatalf("LoadTask failed: %v", err)
	}

	_, err = BuildDAG(task)
	if err == nil {
		t.Errorf("Expected error for circular dependency")
	}
}

// Test ValidateDAG with valid DAG
func TestValidateDAG_Valid(t *testing.T) {
	defer cleanupTestTasks(t, "TEST-V-A", "TEST-V-B")
	createTestTask(t, "TEST-V-B", "Task B", []string{})
	createTestTask(t, "TEST-V-A", "Task A", []string{"TEST-V-B"})

	task, _ := LoadTask("TEST-V-A")
	dag, _ := BuildDAG(task)

	err := ValidateDAG(dag)
	if err != nil {
		t.Errorf("ValidateDAG should pass for valid DAG: %v", err)
	}
}

// Test ValidateDAG with no root nodes
func TestValidateDAG_NoRoots(t *testing.T) {
	dag := &DAG{
		Nodes: make(map[string]*DAGNode),
		Root:  []*DAGNode{},
	}

	err := ValidateDAG(dag)
	if err == nil {
		t.Errorf("Expected error for DAG with no root nodes")
	}
}

// Test TopologicalSort with single task
func TestTopologicalSort_SingleTask(t *testing.T) {
	defer cleanupTestTasks(t, "TEST-TOPO-1")
	createTestTask(t, "TEST-TOPO-1", "Single", []string{})

	task, _ := LoadTask("TEST-TOPO-1")
	dag, _ := BuildDAG(task)

	sorted, err := TopologicalSort(dag)
	if err != nil {
		t.Fatalf("TopologicalSort failed: %v", err)
	}

	if len(sorted) != 1 {
		t.Errorf("Expected 1 task, got %d", len(sorted))
	}

	if sorted[0].ID != "TEST-TOPO-1" {
		t.Errorf("Expected TEST-TOPO-1, got %s", sorted[0].ID)
	}
}

// Test TopologicalSort with linear chain
func TestTopologicalSort_LinearChain(t *testing.T) {
	defer cleanupTestTasks(t, "TEST-TOPO-C", "TEST-TOPO-B", "TEST-TOPO-A")
	createTestTask(t, "TEST-TOPO-C", "C", []string{})
	createTestTask(t, "TEST-TOPO-B", "B", []string{"TEST-TOPO-C"})
	createTestTask(t, "TEST-TOPO-A", "A", []string{"TEST-TOPO-B"})

	task, _ := LoadTask("TEST-TOPO-A")
	dag, _ := BuildDAG(task)

	sorted, err := TopologicalSort(dag)
	if err != nil {
		t.Fatalf("TopologicalSort failed: %v", err)
	}

	if len(sorted) != 3 {
		t.Errorf("Expected 3 tasks, got %d", len(sorted))
	}

	// Verify order: C must come before B, B must come before A
	indexMap := make(map[string]int)
	for i, task := range sorted {
		indexMap[task.ID] = i
	}

	if indexMap["TEST-TOPO-C"] >= indexMap["TEST-TOPO-B"] {
		t.Errorf("TEST-TOPO-C should come before TEST-TOPO-B")
	}

	if indexMap["TEST-TOPO-B"] >= indexMap["TEST-TOPO-A"] {
		t.Errorf("TEST-TOPO-B should come before TEST-TOPO-A")
	}
}

// Test TopologicalSort with diamond pattern
func TestTopologicalSort_DiamondPattern(t *testing.T) {
	defer cleanupTestTasks(t, "TEST-TOPO-D-BASE", "TEST-TOPO-D-LEFT", "TEST-TOPO-D-RIGHT", "TEST-TOPO-D-TOP")
	createTestTask(t, "TEST-TOPO-D-BASE", "Base", []string{})
	createTestTask(t, "TEST-TOPO-D-LEFT", "Left", []string{"TEST-TOPO-D-BASE"})
	createTestTask(t, "TEST-TOPO-D-RIGHT", "Right", []string{"TEST-TOPO-D-BASE"})
	createTestTask(t, "TEST-TOPO-D-TOP", "Top", []string{"TEST-TOPO-D-LEFT", "TEST-TOPO-D-RIGHT"})

	task, _ := LoadTask("TEST-TOPO-D-TOP")
	dag, _ := BuildDAG(task)

	sorted, err := TopologicalSort(dag)
	if err != nil {
		t.Fatalf("TopologicalSort failed: %v", err)
	}

	if len(sorted) != 4 {
		t.Errorf("Expected 4 tasks, got %d", len(sorted))
	}

	// Verify constraints
	indexMap := make(map[string]int)
	for i, task := range sorted {
		indexMap[task.ID] = i
	}

	if indexMap["TEST-TOPO-D-BASE"] >= indexMap["TEST-TOPO-D-LEFT"] {
		t.Errorf("Base should come before Left")
	}

	if indexMap["TEST-TOPO-D-BASE"] >= indexMap["TEST-TOPO-D-RIGHT"] {
		t.Errorf("Base should come before Right")
	}

	if indexMap["TEST-TOPO-D-LEFT"] >= indexMap["TEST-TOPO-D-TOP"] {
		t.Errorf("Left should come before Top")
	}

	if indexMap["TEST-TOPO-D-RIGHT"] >= indexMap["TEST-TOPO-D-TOP"] {
		t.Errorf("Right should come before Top")
	}
}

// Test with real HC-006 task
func TestRealTask_HC006(t *testing.T) {
	// Load the real HC-006 task
	task, err := LoadTask("HC-006")
	if err != nil {
		t.Skipf("HC-006 task not found (may be running from different directory): %v", err)
	}

	if task.ID != "HC-006" {
		t.Errorf("Expected ID HC-006, got %s", task.ID)
	}

	if task.Title == "" {
		t.Errorf("HC-006 should have a title")
	}

	// Build DAG
	dag, err := BuildDAG(task)
	if err != nil {
		t.Fatalf("BuildDAG failed: %v", err)
	}

	// Validate DAG
	err = ValidateDAG(dag)
	if err != nil {
		t.Fatalf("ValidateDAG failed: %v", err)
	}

	// Sort topologically
	sorted, err := TopologicalSort(dag)
	if err != nil {
		t.Fatalf("TopologicalSort failed: %v", err)
	}

	if len(sorted) == 0 {
		t.Errorf("TopologicalSort should return at least 1 task")
	}

	t.Logf("HC-006 loaded successfully. Dependencies: %v", task.Dependencies)
}
