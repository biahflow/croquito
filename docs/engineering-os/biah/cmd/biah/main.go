package main

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/biahflow/engineering-os/biah/pkg/cli"
	"github.com/biahflow/engineering-os/biah/pkg/registry"
)

func main() {
	// Initialize the worker registry
	adaptorsPath := filepath.Join(filepath.Dir(os.Args[0]), "..", "adapters")
	if _, err := os.Stat(adaptorsPath); os.IsNotExist(err) {
		// Try relative path from current working directory
		adaptorsPath = "biah/adapters"
	}

	reg := registry.NewRegistry(adaptorsPath)
	if err := reg.LoadManifests(); err != nil {
		// Log warning but don't fail - registry is optional for some operations
		fmt.Fprintf(os.Stderr, "Warning: Failed to load worker manifests: %v\n", err)
	} else {
		workers := reg.GetAllWorkers()
		if len(workers) > 0 {
			fmt.Fprintf(os.Stderr, "Loaded %d worker adapters\n", len(workers))
		}
	}

	cmd := cli.NewRootCommand()
	if err := cmd.Execute(); err != nil {
		os.Exit(1)
	}
}
