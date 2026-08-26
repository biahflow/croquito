package cli

import (
	"fmt"

	"github.com/spf13/cobra"
)

// NewRootCommand creates the root biah command
func NewRootCommand() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "biah",
		Short: "Biah: Vendor-Neutral Multi-Agent Orchestrator",
		Long: `Biah is the orchestration layer for Engineering OS.

It routes work across Claude, Codex, Copilot, and future vendors based on
task requirements, not vendor preference. Use biah to:

  - Plan work (identify dependencies, build DAG)
  - Route tasks to best-fit workers (capability matching)
  - Execute in parallel with isolated worktrees
  - Collect and validate evidence
  - Enforce human approval gates

Examples:
  biah task HC-006                 # Accept and validate a task
  biah plan HC-006                 # See execution plan (DAG + routing)
  biah run HC-006                  # Execute the plan
  biah review HC-006               # Review evidence and approve
  biah status                      # Show all tasks and status
`,
		Version: "0.0.1-alpha",
	}

	cmd.AddCommand(
		NewTaskCommand(),
		NewPlanCommand(),
		NewRunCommand(),
		NewReviewCommand(),
		NewStatusCommand(),
		NewEvidenceCommand(),
	)

	return cmd
}

// NewTaskCommand loads and validates a task contract
func NewTaskCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "task <task-id>",
		Short: "Load and validate a task contract",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			taskID := args[0]
			fmt.Printf("Loading task: %s\n", taskID)
			fmt.Println("✓ Task loaded (stub)")
			fmt.Println("✓ Contract validated (stub)")
			fmt.Println("\nNext: biah plan " + taskID)
			return nil
		},
	}
}

// NewPlanCommand shows the execution plan (DAG + routing)
func NewPlanCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "plan <task-id>",
		Short: "Show execution plan (DAG + routing)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			taskID := args[0]
			fmt.Printf("Planning: %s\n\n", taskID)
			fmt.Println("DAG:")
			fmt.Println("  HC-006-A  schema       (depends: none)")
			fmt.Println("  HC-006-B  backend      (depends: HC-006-A)")
			fmt.Println("  HC-006-C  frontend     (depends: HC-006-B)")
			fmt.Println("  HC-006-D  review       (depends: HC-006-B, HC-006-C)")
			fmt.Println("\nRouting by capability:")
			fmt.Println("  HC-006-A  schema       → codex (implementation)")
			fmt.Println("  HC-006-B  backend      → codex (implementation, testing)")
			fmt.Println("  HC-006-C  frontend     → copilot (implementation, github_native)")
			fmt.Println("  HC-006-D  review       → claude (architecture_reasoning)")
			fmt.Println("\nNext: biah run " + taskID)
			return nil
		},
	}
}

// NewRunCommand executes the task plan
func NewRunCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "run <task-id>",
		Short: "Execute the task plan",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			taskID := args[0]
			fmt.Printf("Executing: %s\n", taskID)
			fmt.Println("✓ Context loaded")
			fmt.Println("✓ Worktrees created")
			fmt.Println("✓ Schema task (codex) completed")
			fmt.Println("✓ Backend task (codex) completed")
			fmt.Println("✓ Frontend task (copilot) completed")
			fmt.Println("✓ Review task (claude) completed")
			fmt.Println("\nNext: biah review " + taskID)
			return nil
		},
	}
}

// NewReviewCommand reviews evidence and requests approval
func NewReviewCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "review <task-id>",
		Short: "Review evidence and request approval",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			taskID := args[0]
			fmt.Printf("Reviewing: %s\n\n", taskID)
			fmt.Println("Evidence Package:")
			fmt.Println("  [✓] HC-006-A BUILD_COMPLETE (schema)")
			fmt.Println("  [✓] HC-006-B BUILD_COMPLETE (backend)")
			fmt.Println("  [✓] HC-006-C BUILD_COMPLETE (frontend)")
			fmt.Println("  [✓] HC-006-D BUILD_COMPLETE (review)")
			fmt.Println("\nParity check: ✓ (all evidence aligned)")
			fmt.Println("Quality gates: ✓ (tests, lint, type-check passed)")
			fmt.Println("\n⚠️  Ready to merge? [y/n] (stub - not asking for real input yet)")
			return nil
		},
	}
}

// NewStatusCommand shows all tasks and their status
func NewStatusCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "status",
		Short: "Show all tasks and status",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Println("Biah Status")
			fmt.Println("-----------")
			fmt.Println("  HC-006  [✓] PLAN          Execution plan ready")
			fmt.Println("  HC-007  [●] IN_PROGRESS   Running backend task")
			fmt.Println("  HC-008  [ ] PENDING       Waiting for HC-007")
			fmt.Println("\nNext: biah review <task-id> or biah run <task-id>")
			return nil
		},
	}
}

// NewEvidenceCommand shows complete evidence package
func NewEvidenceCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "evidence <task-id>",
		Short: "Show complete evidence package",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			taskID := args[0]
			fmt.Printf("Evidence: %s\n\n", taskID)
			fmt.Println("BUILD REPORTS:")
			fmt.Println("  HC-006-A: ../evidence/HC-006-A.json")
			fmt.Println("  HC-006-B: ../evidence/HC-006-B.json")
			fmt.Println("  HC-006-C: ../evidence/HC-006-C.json")
			fmt.Println("  HC-006-D: ../evidence/HC-006-D.json")
			fmt.Println("\nAggregated: ../evidence/HC-006-evidence.json")
			return nil
		},
	}
}
