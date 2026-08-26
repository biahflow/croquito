package main

import (
	"fmt"
	"github.com/biahflow/engineering-os/biah/pkg/adapter"
	"github.com/biahflow/engineering-os/biah/pkg/evidence"
	"strings"
)

func main() {
	reports := map[string]*adapter.BuildReport{
		"claude": &adapter.BuildReport{},
		"codex": &adapter.BuildReport{},
	}
	
	pkg := &evidence.EvidencePackage{
		TaskID: "test",
		WorkerReports: reports,
		OverallStatus: "SUCCESS",
	}
	
	summary := pkg.Summary()
	fmt.Println("=== Summary ===")
	fmt.Println(summary)
	fmt.Println("\n=== Checking ===")
	fmt.Println("Contains 'Claude':", strings.Contains(summary, "Claude"))
	fmt.Println("Contains 'claude':", strings.Contains(summary, "claude"))
	fmt.Println("Contains 'Codex':", strings.Contains(summary, "Codex"))
	fmt.Println("Contains 'codex':", strings.Contains(summary, "codex"))
}
