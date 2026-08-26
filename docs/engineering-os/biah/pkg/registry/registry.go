package registry

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"

	"gopkg.in/yaml.v3"
)

// Constraints defines resource constraints for a worker
type Constraints struct {
	MaxContextTokens int  `yaml:"max_context_tokens"`
	TimeoutSeconds   int  `yaml:"timeout_seconds"`
	SupportsParallel bool `yaml:"supports_parallel"`
}

// Worker represents a worker capability profile from a manifest
type Worker struct {
	Name         string      `yaml:"worker"`
	Capabilities []string    `yaml:"capabilities"`
	Constraints  Constraints `yaml:"constraints"`
}

// Registry manages worker manifests and provides capability matching
type Registry struct {
	manifestPath string
	workers      []Worker
	mu           sync.RWMutex
}

// NewRegistry creates a new registry with the given manifest directory path
func NewRegistry(manifestPath string) *Registry {
	return &Registry{
		manifestPath: manifestPath,
		workers:      []Worker{},
	}
}

// LoadManifests loads all YAML manifest files from the adapters directory
func (r *Registry) LoadManifests() error {
	r.mu.Lock()
	defer r.mu.Unlock()

	// Check if path exists
	if _, err := os.Stat(r.manifestPath); err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("manifest path does not exist: %s", r.manifestPath)
		}
		return fmt.Errorf("error accessing manifest path: %w", err)
	}

	// Read all files in the directory
	entries, err := os.ReadDir(r.manifestPath)
	if err != nil {
		return fmt.Errorf("error reading manifest directory: %w", err)
	}

	workers := []Worker{}

	// Process each directory (each adapter)
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		manifestPath := filepath.Join(r.manifestPath, entry.Name(), "manifest.yml")

		// Check if manifest file exists
		if _, err := os.Stat(manifestPath); os.IsNotExist(err) {
			continue
		}

		// Read and parse the manifest
		data, err := os.ReadFile(manifestPath)
		if err != nil {
			return fmt.Errorf("error reading manifest %s: %w", manifestPath, err)
		}

		var worker Worker
		if err := yaml.Unmarshal(data, &worker); err != nil {
			return fmt.Errorf("error parsing manifest %s: %w", manifestPath, err)
		}

		// Validate the manifest
		if err := validateWorker(&worker); err != nil {
			return fmt.Errorf("validation failed for manifest %s: %w", manifestPath, err)
		}

		workers = append(workers, worker)
	}

	r.workers = workers
	return nil
}

// GetWorkersByCapability returns all workers that have ALL of the required capabilities
func (r *Registry) GetWorkersByCapability(required []string) []Worker {
	r.mu.RLock()
	defer r.mu.RUnlock()

	if len(required) == 0 {
		return r.workers
	}

	// Create a set of required capabilities for faster lookup
	requiredSet := make(map[string]bool)
	for _, cap := range required {
		requiredSet[cap] = true
	}

	var matching []Worker

	for _, worker := range r.workers {
		workerCapSet := make(map[string]bool)
		for _, cap := range worker.Capabilities {
			workerCapSet[cap] = true
		}

		// Check if worker has all required capabilities
		hasAll := true
		for _, req := range required {
			if !workerCapSet[req] {
				hasAll = false
				break
			}
		}

		if hasAll {
			matching = append(matching, worker)
		}
	}

	return matching
}

// GetAllWorkers returns all loaded workers
func (r *Registry) GetAllWorkers() []Worker {
	r.mu.RLock()
	defer r.mu.RUnlock()

	// Return a copy to prevent external modification
	workers := make([]Worker, len(r.workers))
	copy(workers, r.workers)
	return workers
}

// GetWorkerByName returns a specific worker by name
func (r *Registry) GetWorkerByName(name string) *Worker {
	r.mu.RLock()
	defer r.mu.RUnlock()

	for i := range r.workers {
		if r.workers[i].Name == name {
			return &r.workers[i]
		}
	}
	return nil
}

// ValidateManifest validates a single worker manifest structure
func (r *Registry) ValidateManifest(worker *Worker) error {
	return validateWorker(worker)
}

// validateWorker is the internal validation function
func validateWorker(worker *Worker) error {
	if worker.Name == "" {
		return fmt.Errorf("worker name is required")
	}

	if len(worker.Capabilities) == 0 {
		return fmt.Errorf("worker %s must have at least one capability", worker.Name)
	}

	// Check for duplicate capabilities
	seen := make(map[string]bool)
	for _, cap := range worker.Capabilities {
		if cap == "" {
			return fmt.Errorf("worker %s has empty capability", worker.Name)
		}
		if seen[cap] {
			return fmt.Errorf("worker %s has duplicate capability: %s", worker.Name, cap)
		}
		seen[cap] = true
	}

	return nil
}

// CheckCircularDependencies detects circular dependency patterns in workers
// Note: This is a placeholder for future dependency tracking
func (r *Registry) CheckCircularDependencies() error {
	r.mu.RLock()
	defer r.mu.RUnlock()

	// Current implementation: no dependencies tracked yet
	return nil
}

// GetCapabilityStats returns statistics about available capabilities
func (r *Registry) GetCapabilityStats() map[string]int {
	r.mu.RLock()
	defer r.mu.RUnlock()

	stats := make(map[string]int)
	for _, worker := range r.workers {
		for _, cap := range worker.Capabilities {
			stats[cap]++
		}
	}

	return stats
}

// ListCapabilities returns a sorted list of all available capabilities
func (r *Registry) ListCapabilities() []string {
	stats := r.GetCapabilityStats()
	capabilities := make([]string, 0, len(stats))
	for cap := range stats {
		capabilities = append(capabilities, cap)
	}
	sort.Strings(capabilities)
	return capabilities
}
