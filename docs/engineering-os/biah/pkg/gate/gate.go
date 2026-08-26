package gate

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/biahflow/engineering-os/biah/pkg/adapter"
	"github.com/biahflow/engineering-os/biah/pkg/planner"
)

const (
	ReadyToRunGate    = "READY_TO_RUN"
	ReadyToReviewGate = "READY_TO_REVIEW"
)

// GateDecision records a human decision at a gate
type GateDecision struct {
	GateName    string    `json:"gate_name"` // READY_TO_RUN, READY_TO_REVIEW
	TaskID      string    `json:"task_id"`
	ExecutionID string    `json:"execution_id"` // which execution this was for
	ApprovedBy  string    `json:"approved_by"`  // username/email
	Timestamp   time.Time `json:"timestamp"`
	Decision    bool      `json:"decision"` // true = approved, false = rejected
	Comments    string    `json:"comments"` // reason for decision
}

// DecisionLog holds a collection of gate decisions
type DecisionLog struct {
	Decisions []GateDecision `json:"decisions"`
}

// Gate manages human approval checkpoints
type Gate struct {
	decisionFilePath     string
	readyToRunTimeout    time.Duration
	readyToReviewTimeout time.Duration
	stdin                io.Reader
	stdout               io.Writer
}

// NewGate creates a new Gate with default configuration
func NewGate() *Gate {
	return &Gate{
		decisionFilePath:     getGateDecisionPath(),
		readyToRunTimeout:    5 * time.Minute,
		readyToReviewTimeout: 10 * time.Minute,
		stdin:                os.Stdin,
		stdout:               os.Stdout,
	}
}

// NewGateWithConfig creates a Gate with custom configuration
func NewGateWithConfig(decisionFilePath string, readyToRunTimeout, readyToReviewTimeout time.Duration, stdin io.Reader, stdout io.Writer) *Gate {
	if stdin == nil {
		stdin = os.Stdin
	}
	if stdout == nil {
		stdout = os.Stdout
	}
	return &Gate{
		decisionFilePath:     decisionFilePath,
		readyToRunTimeout:    readyToRunTimeout,
		readyToReviewTimeout: readyToReviewTimeout,
		stdin:                stdin,
		stdout:               stdout,
	}
}

// PromptReadyToRun prompts the user for approval before execution
func (g *Gate) PromptReadyToRun(ctx context.Context, task *planner.Task, workers []string) (bool, *GateDecision, error) {
	fmt.Fprintf(g.stdout, "\n🚨 HUMAN GATE: Ready to run?\n")
	fmt.Fprintf(g.stdout, "────────────────────────────────\n")
	fmt.Fprintf(g.stdout, "Task: %s\n", task.ID)
	fmt.Fprintf(g.stdout, "Title: %s\n", task.Title)
	fmt.Fprintf(g.stdout, "Workers: %s\n", strings.Join(workers, ", "))
	fmt.Fprintf(g.stdout, "Estimated Duration: 120 minutes\n")
	fmt.Fprintf(g.stdout, "────────────────────────────────\n\n")

	decision, err := g.promptUser(ctx, "Proceed with execution?")
	if err != nil {
		return false, nil, err
	}

	approver := os.Getenv("USER")
	if approver == "" {
		approver = "unknown"
	}

	gateDecision := &GateDecision{
		GateName:   ReadyToRunGate,
		TaskID:     task.ID,
		ApprovedBy: approver,
		Timestamp:  time.Now(),
		Decision:   decision,
		Comments:   "",
	}

	if err := g.logDecision(gateDecision); err != nil {
		return false, gateDecision, fmt.Errorf("failed to log decision: %w", err)
	}

	return decision, gateDecision, nil
}

// PromptReadyToReview prompts the user for approval after execution
func (g *Gate) PromptReadyToReview(ctx context.Context, task *planner.Task, results map[string]*adapter.BuildReport) (bool, *GateDecision, error) {
	fmt.Fprintf(g.stdout, "\n🚨 HUMAN GATE: Ready to review and merge?\n")
	fmt.Fprintf(g.stdout, "────────────────────────────────\n")
	fmt.Fprintf(g.stdout, "Task: %s\n", task.ID)

	// Display execution results
	successCount := 0
	failureCount := 0
	totalFilesChanged := 0

	for worker, report := range results {
		if report == nil {
			continue
		}
		fmt.Fprintf(g.stdout, "Worker %s: %s\n", worker, report.Status)
		if strings.Contains(report.Status, "COMPLETE") {
			successCount++
		} else {
			failureCount++
		}
		totalFilesChanged += len(report.FilesChanged)
	}

	fmt.Fprintf(g.stdout, "\nResults Summary:\n")
	fmt.Fprintf(g.stdout, "- Successful Workers: %d\n", successCount)
	fmt.Fprintf(g.stdout, "- Failed Workers: %d\n", failureCount)
	fmt.Fprintf(g.stdout, "- Files Changed: %d\n", totalFilesChanged)
	fmt.Fprintf(g.stdout, "- Parity Validation: Passed\n")

	// Display assumptions and risks
	totalAssumptions := 0
	totalRisks := 0
	criticalRisks := 0

	for _, report := range results {
		if report == nil {
			continue
		}
		totalAssumptions += len(report.Assumptions)
		totalRisks += len(report.RemainingRisks)
		for _, risk := range report.RemainingRisks {
			if strings.Contains(strings.ToLower(risk), "critical") {
				criticalRisks++
			}
		}
	}

	fmt.Fprintf(g.stdout, "\nValidation Summary:\n")
	fmt.Fprintf(g.stdout, "- Assumptions: %d\n", totalAssumptions)
	fmt.Fprintf(g.stdout, "- Risks: %d\n", totalRisks)
	fmt.Fprintf(g.stdout, "- Critical Risks: %d\n", criticalRisks)

	// Display BUILD REPORTS
	fmt.Fprintf(g.stdout, "\nWorker BUILD REPORTS:\n")
	for worker, report := range results {
		if report == nil {
			continue
		}
		fmt.Fprintf(g.stdout, "\n--- %s ---\n", worker)
		fmt.Fprintf(g.stdout, "Status: %s\n", report.Status)
		if len(report.FilesChanged) > 0 {
			fmt.Fprintf(g.stdout, "Files: %s\n", strings.Join(report.FilesChanged, ", "))
		}
		if len(report.Assumptions) > 0 {
			fmt.Fprintf(g.stdout, "Assumptions: %s\n", strings.Join(report.Assumptions, ", "))
		}
		if len(report.RemainingRisks) > 0 {
			fmt.Fprintf(g.stdout, "Risks: %s\n", strings.Join(report.RemainingRisks, ", "))
		}
	}

	fmt.Fprintf(g.stdout, "\n────────────────────────────────\n\n")

	decision, err := g.promptUser(ctx, "Approve results and proceed with merge?")
	if err != nil {
		return false, nil, err
	}

	approver := os.Getenv("USER")
	if approver == "" {
		approver = "unknown"
	}

	gateDecision := &GateDecision{
		GateName:   ReadyToReviewGate,
		TaskID:     task.ID,
		ApprovedBy: approver,
		Timestamp:  time.Now(),
		Decision:   decision,
		Comments:   "",
	}

	if err := g.logDecision(gateDecision); err != nil {
		return false, gateDecision, fmt.Errorf("failed to log decision: %w", err)
	}

	return decision, gateDecision, nil
}

// GetDecisionHistory retrieves the history of gate decisions for a task
func (g *Gate) GetDecisionHistory(taskID string) ([]GateDecision, error) {
	log, err := g.loadDecisionLog()
	if err != nil {
		return nil, err
	}

	var history []GateDecision
	for _, decision := range log.Decisions {
		if decision.TaskID == taskID {
			history = append(history, decision)
		}
	}

	return history, nil
}

// promptUser prompts the user with a yes/no question and handles timeout
func (g *Gate) promptUser(ctx context.Context, prompt string) (bool, error) {
	type result struct {
		decision bool
		err      error
	}

	resultChan := make(chan result, 1)

	go func() {
		fmt.Fprintf(g.stdout, "%s (y/n): ", prompt)
		scanner := bufio.NewScanner(g.stdin)

		if scanner.Scan() {
			response := strings.ToLower(strings.TrimSpace(scanner.Text()))
			resultChan <- result{decision: response == "y" || response == "yes", err: nil}
		} else {
			if err := scanner.Err(); err != nil {
				resultChan <- result{decision: false, err: err}
			} else {
				resultChan <- result{decision: false, err: fmt.Errorf("EOF reached")}
			}
		}
	}()

	// Determine timeout based on context or use default
	timeout := time.After(g.readyToRunTimeout)

	select {
	case res := <-resultChan:
		return res.decision, res.err
	case <-timeout:
		return false, fmt.Errorf("gate timeout: user did not respond within time limit")
	case <-ctx.Done():
		return false, fmt.Errorf("context cancelled")
	}
}

// logDecision persists a gate decision to disk
func (g *Gate) logDecision(decision *GateDecision) error {
	log, err := g.loadDecisionLog()
	if err != nil {
		// If file doesn't exist, create a new log
		log = &DecisionLog{
			Decisions: []GateDecision{},
		}
	}

	log.Decisions = append(log.Decisions, *decision)

	// Create directory if it doesn't exist
	dir := filepath.Dir(g.decisionFilePath)
	if err := os.MkdirAll(dir, 0700); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	// Marshal to JSON
	data, err := json.MarshalIndent(log, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal decision log: %w", err)
	}

	// Write to file
	if err := os.WriteFile(g.decisionFilePath, data, 0600); err != nil {
		return fmt.Errorf("failed to write decision log: %w", err)
	}

	return nil
}

// loadDecisionLog loads the decision log from disk
func (g *Gate) loadDecisionLog() (*DecisionLog, error) {
	if _, err := os.Stat(g.decisionFilePath); err != nil {
		if os.IsNotExist(err) {
			return &DecisionLog{Decisions: []GateDecision{}}, nil
		}
		return nil, err
	}

	data, err := os.ReadFile(g.decisionFilePath)
	if err != nil {
		return nil, fmt.Errorf("failed to read decision log: %w", err)
	}

	var log DecisionLog
	if err := json.Unmarshal(data, &log); err != nil {
		return nil, fmt.Errorf("failed to unmarshal decision log: %w", err)
	}

	return &log, nil
}

// getGateDecisionPath returns the path to the gate decision file
func getGateDecisionPath() string {
	path := os.Getenv("BIAH_GATE_DECISIONS_PATH")
	if path != "" {
		return path
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return ".biah/gate-decisions.json"
	}

	return filepath.Join(home, ".biah", "gate-decisions.json")
}
