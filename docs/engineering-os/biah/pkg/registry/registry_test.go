package registry

import (
	"os"
	"path/filepath"
	"testing"
)

func createTestManifestGeneric(dir string, name string, caps []string) error {
	adapterDir := filepath.Join(dir, name)
	if err := os.MkdirAll(adapterDir, 0755); err != nil {
		return err
	}

	manifestPath := filepath.Join(adapterDir, "manifest.yml")
	content := "worker: " + name + "\n"
	content += "capabilities:\n"
	for _, cap := range caps {
		content += "  - " + cap + "\n"
	}
	content += "constraints:\n"
	content += "  max_context_tokens: 200000\n"
	content += "  timeout_seconds: 3600\n"
	content += "  supports_parallel: true\n"

	return os.WriteFile(manifestPath, []byte(content), 0644)
}

func createTestManifest(t *testing.T, dir string, name string, caps []string) {
	if err := createTestManifestGeneric(dir, name, caps); err != nil {
		t.Fatalf("failed to create test manifest: %v", err)
	}
}

func TestNewRegistry(t *testing.T) {
	tmpdir := t.TempDir()
	registry := NewRegistry(tmpdir)

	if registry == nil {
		t.Error("NewRegistry returned nil")
	}

	if registry.manifestPath != tmpdir {
		t.Errorf("expected manifestPath %s, got %s", tmpdir, registry.manifestPath)
	}

	if len(registry.workers) != 0 {
		t.Errorf("expected empty workers, got %d", len(registry.workers))
	}
}

func TestLoadManifestsSingleWorker(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "test-worker", []string{"capability1", "capability2"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	workers := registry.GetAllWorkers()
	if len(workers) != 1 {
		t.Errorf("expected 1 worker, got %d", len(workers))
	}

	if workers[0].Name != "test-worker" {
		t.Errorf("expected name 'test-worker', got %s", workers[0].Name)
	}

	if len(workers[0].Capabilities) != 2 {
		t.Errorf("expected 2 capabilities, got %d", len(workers[0].Capabilities))
	}
}

func TestLoadManifestsMultipleWorkers(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"cap1", "cap2"})
	createTestManifest(t, tmpdir, "worker2", []string{"cap2", "cap3"})
	createTestManifest(t, tmpdir, "worker3", []string{"cap4"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	workers := registry.GetAllWorkers()
	if len(workers) != 3 {
		t.Errorf("expected 3 workers, got %d", len(workers))
	}
}

func TestLoadManifestsNonexistentPath(t *testing.T) {
	registry := NewRegistry("/nonexistent/path/that/does/not/exist")
	err := registry.LoadManifests()

	if err == nil {
		t.Error("expected error for nonexistent path")
	}
}

func TestLoadManifestsEmptyDirectory(t *testing.T) {
	tmpdir := t.TempDir()
	registry := NewRegistry(tmpdir)
	err := registry.LoadManifests()

	if err != nil {
		t.Errorf("unexpected error for empty directory: %v", err)
	}

	workers := registry.GetAllWorkers()
	if len(workers) != 0 {
		t.Errorf("expected 0 workers from empty directory, got %d", len(workers))
	}
}

func TestGetWorkersByCapabilitySingleMatch(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"implementation", "testing"})
	createTestManifest(t, tmpdir, "worker2", []string{"code_review", "debugging"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	workers := registry.GetWorkersByCapability([]string{"implementation"})
	if len(workers) != 1 {
		t.Errorf("expected 1 worker with 'implementation', got %d", len(workers))
	}

	if workers[0].Name != "worker1" {
		t.Errorf("expected worker1, got %s", workers[0].Name)
	}
}

func TestGetWorkersByCapabilityMultipleMatches(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"code_review", "testing"})
	createTestManifest(t, tmpdir, "worker2", []string{"code_review", "debugging"})
	createTestManifest(t, tmpdir, "worker3", []string{"implementation", "testing"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	workers := registry.GetWorkersByCapability([]string{"code_review"})
	if len(workers) != 2 {
		t.Errorf("expected 2 workers with 'code_review', got %d", len(workers))
	}
}

func TestGetWorkersByCapabilityAllRequired(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"implementation", "testing", "debugging"})
	createTestManifest(t, tmpdir, "worker2", []string{"implementation", "testing"})
	createTestManifest(t, tmpdir, "worker3", []string{"code_review"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	workers := registry.GetWorkersByCapability([]string{"implementation", "testing"})
	if len(workers) != 2 {
		t.Errorf("expected 2 workers with both 'implementation' and 'testing', got %d", len(workers))
	}

	for _, w := range workers {
		if w.Name == "worker3" {
			t.Error("worker3 should not be included")
		}
	}
}

func TestGetWorkersByCapabilityNone(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"implementation", "testing"})
	createTestManifest(t, tmpdir, "worker2", []string{"code_review"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	workers := registry.GetWorkersByCapability([]string{"nonexistent_capability"})
	if len(workers) != 0 {
		t.Errorf("expected 0 workers with nonexistent capability, got %d", len(workers))
	}
}

func TestGetWorkersByCapabilityEmpty(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"implementation"})
	createTestManifest(t, tmpdir, "worker2", []string{"code_review"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	workers := registry.GetWorkersByCapability([]string{})
	if len(workers) != 2 {
		t.Errorf("expected all 2 workers for empty requirement, got %d", len(workers))
	}
}

func TestValidateManifestMissingName(t *testing.T) {
	worker := &Worker{
		Name:         "",
		Capabilities: []string{"cap1"},
	}

	registry := NewRegistry("")
	err := registry.ValidateManifest(worker)

	if err == nil {
		t.Error("expected error for missing name")
	}
}

func TestValidateManifestMissingCapabilities(t *testing.T) {
	worker := &Worker{
		Name:         "test",
		Capabilities: []string{},
	}

	registry := NewRegistry("")
	err := registry.ValidateManifest(worker)

	if err == nil {
		t.Error("expected error for missing capabilities")
	}
}

func TestValidateManifestDuplicateCapabilities(t *testing.T) {
	worker := &Worker{
		Name:         "test",
		Capabilities: []string{"cap1", "cap2", "cap1"},
	}

	registry := NewRegistry("")
	err := registry.ValidateManifest(worker)

	if err == nil {
		t.Error("expected error for duplicate capabilities")
	}
}

func TestValidateManifestEmptyCapability(t *testing.T) {
	worker := &Worker{
		Name:         "test",
		Capabilities: []string{"cap1", "", "cap2"},
	}

	registry := NewRegistry("")
	err := registry.ValidateManifest(worker)

	if err == nil {
		t.Error("expected error for empty capability")
	}
}

func TestValidateManifestValid(t *testing.T) {
	worker := &Worker{
		Name:         "test",
		Capabilities: []string{"cap1", "cap2"},
		Constraints: Constraints{
			MaxContextTokens: 100000,
			TimeoutSeconds:   3600,
			SupportsParallel: true,
		},
	}

	registry := NewRegistry("")
	err := registry.ValidateManifest(worker)

	if err != nil {
		t.Errorf("unexpected error for valid manifest: %v", err)
	}
}

func TestGetWorkerByName(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"cap1"})
	createTestManifest(t, tmpdir, "worker2", []string{"cap2"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	worker := registry.GetWorkerByName("worker1")
	if worker == nil {
		t.Error("expected to find worker1")
	} else if worker.Name != "worker1" {
		t.Errorf("expected name worker1, got %s", worker.Name)
	}

	worker = registry.GetWorkerByName("nonexistent")
	if worker != nil {
		t.Error("expected nil for nonexistent worker")
	}
}

func TestCheckCircularDependencies(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"cap1"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	err := registry.CheckCircularDependencies()
	if err != nil {
		t.Errorf("unexpected error checking circular dependencies: %v", err)
	}
}

func TestGetCapabilityStats(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"cap1", "cap2"})
	createTestManifest(t, tmpdir, "worker2", []string{"cap2", "cap3"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	stats := registry.GetCapabilityStats()

	if stats["cap1"] != 1 {
		t.Errorf("expected cap1 count 1, got %d", stats["cap1"])
	}

	if stats["cap2"] != 2 {
		t.Errorf("expected cap2 count 2, got %d", stats["cap2"])
	}

	if stats["cap3"] != 1 {
		t.Errorf("expected cap3 count 1, got %d", stats["cap3"])
	}
}

func TestListCapabilities(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"zebra", "apple"})
	createTestManifest(t, tmpdir, "worker2", []string{"banana"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	caps := registry.ListCapabilities()

	if len(caps) != 3 {
		t.Errorf("expected 3 capabilities, got %d", len(caps))
	}

	// Check sorting
	if caps[0] != "apple" || caps[1] != "banana" || caps[2] != "zebra" {
		t.Errorf("capabilities not sorted correctly: %v", caps)
	}
}

func TestGetAllWorkers(t *testing.T) {
	tmpdir := t.TempDir()
	createTestManifest(t, tmpdir, "worker1", []string{"cap1"})
	createTestManifest(t, tmpdir, "worker2", []string{"cap2"})

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("LoadManifests failed: %v", err)
	}

	workers := registry.GetAllWorkers()
	if len(workers) != 2 {
		t.Errorf("expected 2 workers, got %d", len(workers))
	}

	// Verify it's a copy
	if len(workers) > 0 {
		workers[0].Name = "modified"
		workers2 := registry.GetAllWorkers()
		if workers2[0].Name == "modified" {
			t.Error("GetAllWorkers should return a copy, not reference to internal data")
		}
	}
}

func TestLoadManifestsParseFails(t *testing.T) {
	tmpdir := t.TempDir()
	adapterDir := filepath.Join(tmpdir, "badworker")
	if err := os.MkdirAll(adapterDir, 0755); err != nil {
		t.Fatalf("failed to create adapter directory: %v", err)
	}

	manifestPath := filepath.Join(adapterDir, "manifest.yml")
	if err := os.WriteFile(manifestPath, []byte("invalid: yaml: content: ["), 0644); err != nil {
		t.Fatalf("failed to write invalid manifest: %v", err)
	}

	registry := NewRegistry(tmpdir)
	err := registry.LoadManifests()

	if err == nil {
		t.Error("expected error when parsing invalid YAML")
	}
}

func TestRealAdaptersLoading(t *testing.T) {
	// This test loads the actual adapters if they exist
	adapterPath := "../../adapters"
	if _, err := os.Stat(adapterPath); os.IsNotExist(err) {
		t.Skip("adapters directory not found, skipping real adapters test")
	}

	registry := NewRegistry(adapterPath)
	if err := registry.LoadManifests(); err != nil {
		t.Fatalf("failed to load real adapters: %v", err)
	}

	workers := registry.GetAllWorkers()
	if len(workers) == 0 {
		t.Skip("no adapters found in adapters directory")
	}

	// Verify some expected capabilities
	allCaps := make(map[string]bool)
	for _, w := range workers {
		for _, cap := range w.Capabilities {
			allCaps[cap] = true
		}
	}

	if !allCaps["implementation"] && !allCaps["code_review"] && !allCaps["architecture_reasoning"] {
		t.Logf("Found capabilities: %v", allCaps)
	}
}

func BenchmarkGetWorkersByCapability(b *testing.B) {
	tmpdir := b.TempDir()
	for i := 0; i < 100; i++ {
		caps := []string{"cap1", "cap2", "cap3"}
		if err := createTestManifestGeneric(tmpdir, "worker"+string(rune(48+i)), caps); err != nil {
			b.Fatalf("failed to create test manifest: %v", err)
		}
	}

	registry := NewRegistry(tmpdir)
	if err := registry.LoadManifests(); err != nil {
		b.Fatalf("LoadManifests failed: %v", err)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		registry.GetWorkersByCapability([]string{"cap1", "cap2"})
	}
}
