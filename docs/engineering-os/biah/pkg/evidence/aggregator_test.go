package evidence

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/biahflow/engineering-os/biah/pkg/adapter"
	"github.com/biahflow/engineering-os/biah/pkg/executor"
)

// Helper function to create a test BuildReport
func createTestReport(workerName string, status string, filesCount int, assumptions int, risks int) *adapter.BuildReport {
	var files []string
	for i := 0; i < filesCount; i++ {
		files = append(files, "file"+string(rune('A'+i)))
	}

	var assumptionsList []string
	for i := 0; i < assumptions; i++ {
		assumptionsList = append(assumptionsList, "assumption "+string(rune('1'+i)))
	}

	var risksList []string
	for i := 0; i < risks; i++ {
		risksList = append(risksList, "risk "+string(rune('1'+i)))
	}

	return &adapter.BuildReport{
		Status:               status,
		FilesChanged:         files,
		ValidationExecuted:   []string{"validation1", "validation2"},
		ValidationSkipped:    []string{},
		Assumptions:          assumptionsList,
		RemainingRisks:       risksList,
		HumanDecisionsNeeded: []string{},
		WorkerName:           workerName,
		TaskID:               "task-001",
		RawOutput:            "Raw output from " + workerName,
	}
}

// Helper function to create a test ExecutionResult
func createTestExecutionResult(workerReports map[string]*adapter.BuildReport, status string) *executor.ExecutionResult {
	taskResults := make(map[string]*executor.TaskResult)
	successCount := 0
	failureCount := 0

	i := 0
	for workerName, report := range workerReports {
		taskID := "task-" + string(rune('0'+i))
		taskResults[taskID] = &executor.TaskResult{
			TaskID:      taskID,
			Status:      executor.TaskStatusSuccess,
			WorkerName:  workerName,
			BuildReport: report,
			Error:       "",
			DurationMs:  1000,
			StartTime:   time.Now().Add(-2 * time.Second),
			EndTime:     time.Now(),
		}
		successCount++
		i++
	}

	return &executor.ExecutionResult{
		Status:          status,
		TotalTasks:      len(workerReports),
		SuccessfulTasks: successCount,
		FailedTasks:     failureCount,
		BlockedTasks:    0,
		TaskResults:     taskResults,
		ExecutionTimeMs: 3000,
		FailureReasons:  []string{},
	}
}

func TestAggregateNilInput(t *testing.T) {
	pkg, err := Aggregate(nil)
	if err == nil {
		t.Errorf("Expected error for nil input, got nil")
	}
	if pkg != nil {
		t.Errorf("Expected nil package for nil input")
	}
}

func TestAggregateSingleWorker(t *testing.T) {
	report := createTestReport("claude", "SUCCESS", 3, 2, 1)
	workerReports := map[string]*adapter.BuildReport{
		"claude": report,
	}
	result := createTestExecutionResult(workerReports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if pkg == nil {
		t.Fatalf("Expected non-nil package")
	}

	if len(pkg.WorkerReports) != 1 {
		t.Errorf("Expected 1 worker report, got %d", len(pkg.WorkerReports))
	}

	if pkg.FilesChanged != 3 {
		t.Errorf("Expected 3 files changed, got %d", pkg.FilesChanged)
	}

	if len(pkg.Assumptions) != 2 {
		t.Errorf("Expected 2 assumptions, got %d", len(pkg.Assumptions))
	}

	if len(pkg.RisksIdentified) != 1 {
		t.Errorf("Expected 1 risk identified, got %d", len(pkg.RisksIdentified))
	}

	if pkg.OverallStatus != "SUCCESS" {
		t.Errorf("Expected SUCCESS status, got %s", pkg.OverallStatus)
	}
}

func TestAggregateMultipleWorkers(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude":  createTestReport("claude", "SUCCESS", 5, 3, 2),
		"codex":   createTestReport("codex", "SUCCESS", 5, 3, 2),
		"copilot": createTestReport("copilot", "SUCCESS", 5, 3, 2),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if len(pkg.WorkerReports) != 3 {
		t.Errorf("Expected 3 worker reports, got %d", len(pkg.WorkerReports))
	}

	if pkg.FilesChanged != 5 {
		t.Errorf("Expected 5 unique files, got %d", pkg.FilesChanged)
	}

	if !pkg.HarnessParity.Valid {
		t.Errorf("Expected valid parity for identical reports")
	}

	if pkg.HarnessParity.Valid && len(pkg.HarnessParity.Differences) > 0 {
		t.Errorf("Expected no differences for identical reports, got %v", pkg.HarnessParity.Differences)
	}
}

func TestParityValidationFileCountMismatch(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 3, 2, 1), // File count differs by 2
	}
	result := createTestExecutionResult(reports, "PARTIAL")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if pkg.HarnessParity.Valid {
		t.Errorf("Expected invalid parity for file count mismatch")
	}

	if len(pkg.HarnessParity.Differences) == 0 {
		t.Errorf("Expected differences to be recorded for file count mismatch")
	}

	found := false
	for _, diff := range pkg.HarnessParity.Differences {
		if strings.Contains(diff, "File count mismatch") {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("Expected file count mismatch difference to be recorded")
	}
}

func TestParityValidationStatusMismatch(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "FAILURE", 5, 2, 1), // Status differs
	}
	result := createTestExecutionResult(reports, "FAILURE")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if pkg.HarnessParity.Valid {
		t.Errorf("Expected invalid parity for status mismatch")
	}

	found := false
	for _, diff := range pkg.HarnessParity.Differences {
		if strings.Contains(diff, "Status mismatch") {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("Expected status mismatch difference to be recorded")
	}
}

func TestParityValidationAssumptionWarning(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 5, 5, 1), // Assumption count differs by 3
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if len(pkg.HarnessParity.Warnings) == 0 {
		t.Errorf("Expected warnings for large assumption count difference")
	}

	found := false
	for _, warning := range pkg.HarnessParity.Warnings {
		if strings.Contains(warning, "Assumption count") {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("Expected assumption count warning to be recorded")
	}
}

func TestParityValidationFileCountTolerance(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 6, 2, 1), // File count differs by 1 (acceptable)
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if !pkg.HarnessParity.Valid {
		t.Errorf("Expected valid parity for file count difference within tolerance")
	}

	if len(pkg.HarnessParity.Differences) > 0 {
		t.Errorf("Expected no differences for file count within tolerance, got %v", pkg.HarnessParity.Differences)
	}
}

func TestValidateParityNilInput(t *testing.T) {
	issues, err := ValidateParity(nil)
	if err == nil {
		t.Errorf("Expected error for nil input")
	}
	if issues != nil {
		t.Errorf("Expected nil issues for nil input")
	}
}

func TestValidateParityWithIssues(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "FAILURE", 3, 2, 1),
	}
	result := createTestExecutionResult(reports, "FAILURE")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	issues, err := ValidateParity(pkg)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if len(issues) == 0 {
		t.Errorf("Expected issues to be reported for parity violations")
	}
}

func TestValidateParityNoIssues(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	issues, err := ValidateParity(pkg)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if len(issues) > 0 {
		t.Errorf("Expected no issues for identical reports, got %v", issues)
	}
}

func TestSummarySuccess(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 3, 2),
		"codex":  createTestReport("codex", "SUCCESS", 5, 3, 2),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	summary := pkg.Summary()

	// Check for expected content
	if !strings.Contains(summary, "✅") {
		t.Errorf("Expected success emoji in summary")
	}

	if !strings.Contains(summary, "SUCCESS") {
		t.Errorf("Expected SUCCESS status in summary")
	}

	if !strings.Contains(summary, "Files Changed: 5") {
		t.Errorf("Expected files changed count in summary")
	}

	if !strings.Contains(summary, "Parity: Valid") {
		t.Errorf("Expected parity status in summary")
	}

	if !strings.Contains(summary, "Assumptions:") {
		t.Errorf("Expected assumptions count in summary")
	}

	if !strings.Contains(summary, "Risks:") {
		t.Errorf("Expected risks count in summary")
	}
}

func TestSummaryFailure(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "FAILURE", 3, 2, 1),
	}
	result := createTestExecutionResult(reports, "FAILURE")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	summary := pkg.Summary()

	if !strings.Contains(summary, "❌") {
		t.Errorf("Expected failure emoji in summary")
	}

	if !strings.Contains(summary, "FAILURE") {
		t.Errorf("Expected FAILURE status in summary")
	}

	if !strings.Contains(summary, "Parity:") {
		t.Errorf("Expected parity section in summary")
	}

	if !strings.Contains(summary, "Issues Detected") {
		t.Errorf("Expected issues detected in parity section")
	}
}

func TestSummaryPartial(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "PARTIAL")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	summary := pkg.Summary()

	if !strings.Contains(summary, "⚠️") {
		t.Errorf("Expected warning emoji in summary for PARTIAL status")
	}

	if !strings.Contains(summary, "PARTIAL") {
		t.Errorf("Expected PARTIAL status in summary")
	}
}

func TestSummaryContainsWorkerNames(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	summary := pkg.Summary()

	if !strings.Contains(summary, "Claude") && !strings.Contains(summary, "claude") {
		t.Errorf("Expected Claude in worker list")
	}

	if !strings.Contains(summary, "Codex") && !strings.Contains(summary, "codex") {
		t.Errorf("Expected Codex in worker list")
	}
}

func TestAggregateWithNoReports(t *testing.T) {
	result := &executor.ExecutionResult{
		Status:          "SUCCESS",
		TotalTasks:      0,
		SuccessfulTasks: 0,
		FailedTasks:     0,
		BlockedTasks:    0,
		TaskResults:     make(map[string]*executor.TaskResult),
		ExecutionTimeMs: 0,
		FailureReasons:  []string{},
	}

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if len(pkg.WorkerReports) != 0 {
		t.Errorf("Expected no worker reports for empty results")
	}

	if pkg.FilesChanged != 0 {
		t.Errorf("Expected 0 files changed")
	}
}

func TestAggregateValidationCount(t *testing.T) {
	report1 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{"file1", "file2"},
		ValidationExecuted:   []string{"val1", "val2"},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "claude",
		TaskID:               "task-001",
	}

	report2 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{"file1", "file2"},
		ValidationExecuted:   []string{"val1", "val2", "val3"},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "codex",
		TaskID:               "task-001",
	}

	reports := map[string]*adapter.BuildReport{
		"claude": report1,
		"codex":  report2,
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	// Should count all validations: 2 + 3 = 5
	if pkg.ValidationsPassed != 5 {
		t.Errorf("Expected 5 validations passed, got %d", pkg.ValidationsPassed)
	}
}

func TestParityEmptyWorkerReports(t *testing.T) {
	pkg := &EvidencePackage{
		TaskID:        "task-001",
		ExecutionID:   "exec-001",
		CreatedAt:     time.Now(),
		TotalDuration: 1000,
		WorkerReports: make(map[string]*adapter.BuildReport),
	}

	parity := validateParity(pkg)
	if !parity.Valid {
		t.Errorf("Expected valid parity for empty worker reports")
	}
}

func TestParitySingleWorker(t *testing.T) {
	pkg := &EvidencePackage{
		TaskID:        "task-001",
		ExecutionID:   "exec-001",
		CreatedAt:     time.Now(),
		TotalDuration: 1000,
		WorkerReports: map[string]*adapter.BuildReport{
			"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		},
	}

	parity := validateParity(pkg)
	if !parity.Valid {
		t.Errorf("Expected valid parity for single worker")
	}

	if len(parity.Differences) > 0 {
		t.Errorf("Expected no differences for single worker")
	}
}

func TestAggregateDeduplicatesFiles(t *testing.T) {
	report1 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{"fileA", "fileB", "fileC"},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "claude",
		TaskID:               "task-001",
	}

	report2 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{"fileB", "fileC", "fileD"},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "codex",
		TaskID:               "task-001",
	}

	reports := map[string]*adapter.BuildReport{
		"claude": report1,
		"codex":  report2,
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	// Should have fileA, fileB, fileC, fileD = 4 unique files
	if pkg.FilesChanged != 4 {
		t.Errorf("Expected 4 unique files, got %d", pkg.FilesChanged)
	}
}

func TestAggregateDeduplicatesRisksAndAssumptions(t *testing.T) {
	report1 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{"assume1", "assume2"},
		RemainingRisks:       []string{"risk1", "risk2"},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "claude",
		TaskID:               "task-001",
	}

	report2 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{"assume2", "assume3"},
		RemainingRisks:       []string{"risk2", "risk3"},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "codex",
		TaskID:               "task-001",
	}

	reports := map[string]*adapter.BuildReport{
		"claude": report1,
		"codex":  report2,
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	// Should deduplicate: 3 unique assumptions, 3 unique risks
	if len(pkg.Assumptions) != 3 {
		t.Errorf("Expected 3 unique assumptions, got %d", len(pkg.Assumptions))
	}

	if len(pkg.RisksIdentified) != 3 {
		t.Errorf("Expected 3 unique risks, got %d", len(pkg.RisksIdentified))
	}
}

func TestSummaryContainsDuration(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")
	result.ExecutionTimeMs = 5432

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	summary := pkg.Summary()

	if !strings.Contains(summary, "5432ms") {
		t.Errorf("Expected duration in summary")
	}
}

func TestSummaryContainsTaskID(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	summary := pkg.Summary()

	if !strings.Contains(summary, "task-") {
		t.Errorf("Expected task ID in summary")
	}
}

// ============ Enhanced Parity Scoring Tests ============

func TestParityScoreFull(t *testing.T) {
	// Create 3 workers with identical results
	reports := map[string]*adapter.BuildReport{
		"claude":  createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":   createTestReport("codex", "SUCCESS", 5, 2, 1),
		"copilot": createTestReport("copilot", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	score := pkg.GetParityScore()
	if score == nil {
		t.Fatalf("Expected non-nil score")
	}

	if score.FileMatch != 100 {
		t.Errorf("Expected FileMatch 100, got %d", score.FileMatch)
	}

	if score.StatusMatch != 100 {
		t.Errorf("Expected StatusMatch 100, got %d", score.StatusMatch)
	}

	if score.Overall < 80 {
		t.Errorf("Expected Overall >= 80, got %d", score.Overall)
	}
}

func TestParityScorePartial(t *testing.T) {
	// Create 3 workers with minor differences (1 file difference, same status)
	reports := map[string]*adapter.BuildReport{
		"claude":  createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":   createTestReport("codex", "SUCCESS", 6, 2, 1),
		"copilot": createTestReport("copilot", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	score := pkg.GetParityScore()
	if score == nil {
		t.Fatalf("Expected non-nil score")
	}

	// FileMatch should be 66% (2 out of 3 match)
	if score.FileMatch < 50 || score.FileMatch > 100 {
		t.Errorf("Expected FileMatch between 50-100, got %d", score.FileMatch)
	}

	if score.StatusMatch != 100 {
		t.Errorf("Expected StatusMatch 100, got %d", score.StatusMatch)
	}

	if score.Overall < 60 {
		t.Errorf("Expected Overall >= 60, got %d", score.Overall)
	}
}

func TestParityScoreDivergent(t *testing.T) {
	// Create 3 workers with major differences (mixed status, different file counts)
	reports := map[string]*adapter.BuildReport{
		"claude":  createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":   createTestReport("codex", "FAILURE", 3, 2, 1),
		"copilot": createTestReport("copilot", "SUCCESS", 7, 2, 1),
	}
	result := createTestExecutionResult(reports, "FAILURE")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	score := pkg.GetParityScore()
	if score == nil {
		t.Fatalf("Expected non-nil score")
	}

	if score.StatusMatch != 0 {
		t.Errorf("Expected StatusMatch 0 for divergent status, got %d", score.StatusMatch)
	}

	if score.Overall >= 70 {
		t.Errorf("Expected Overall < 70 for divergent results, got %d", score.Overall)
	}
}

func TestDetailedParityValidationFull(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	validation := pkg.DetailedParityValidation
	if validation == nil {
		t.Fatalf("Expected non-nil validation")
	}

	if !validation.Valid {
		t.Errorf("Expected Valid=true for identical reports")
	}

	if validation.FileConsistency != "FULL" {
		t.Errorf("Expected FileConsistency=FULL, got %s", validation.FileConsistency)
	}

	if validation.StatusConsistency != "FULL" {
		t.Errorf("Expected StatusConsistency=FULL, got %s", validation.StatusConsistency)
	}

	if len(validation.Recommendations) > 0 {
		t.Errorf("Expected no recommendations for full parity, got %v", validation.Recommendations)
	}
}

func TestDetailedParityValidationPartial(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 6, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	validation := pkg.DetailedParityValidation
	if validation == nil {
		t.Fatalf("Expected non-nil validation")
	}

	if validation.FileConsistency != "PARTIAL" {
		t.Errorf("Expected FileConsistency=PARTIAL, got %s", validation.FileConsistency)
	}

	// Should have recommendations for file count variance
	hasFileRec := false
	for _, rec := range validation.Recommendations {
		if strings.Contains(rec, "File count") {
			hasFileRec = true
			break
		}
	}
	if !hasFileRec {
		t.Errorf("Expected file count recommendation")
	}
}

func TestDetailedParityValidationDivergent(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "FAILURE", 3, 2, 1),
	}
	result := createTestExecutionResult(reports, "FAILURE")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	validation := pkg.DetailedParityValidation
	if validation == nil {
		t.Fatalf("Expected non-nil validation")
	}

	if validation.StatusConsistency != "DIVERGENT" {
		t.Errorf("Expected StatusConsistency=DIVERGENT, got %s", validation.StatusConsistency)
	}

	if validation.Valid {
		t.Errorf("Expected Valid=false for divergent status")
	}

	// Should have status divergence in issues
	hasStatusIssue := false
	for _, issue := range validation.Issues {
		if strings.Contains(issue, "Status") {
			hasStatusIssue = true
			break
		}
	}
	if !hasStatusIssue {
		t.Errorf("Expected status divergence issue")
	}
}

func TestFileConsistencyUnanimous(t *testing.T) {
	// All workers touch the same files
	report1 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{"fileA", "fileB", "fileC"},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "claude",
		TaskID:               "task-001",
	}

	report2 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{"fileA", "fileB", "fileC"},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "codex",
		TaskID:               "task-001",
	}

	reports := map[string]*adapter.BuildReport{
		"claude": report1,
		"codex":  report2,
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	filesReport := pkg.GetFilesReport()
	if filesReport == nil {
		t.Fatalf("Expected non-nil files report")
	}

	if filesReport.Unanimous != 3 {
		t.Errorf("Expected 3 unanimous files, got %d", filesReport.Unanimous)
	}

	if filesReport.Partial != 0 {
		t.Errorf("Expected 0 partial files, got %d", filesReport.Partial)
	}

	if filesReport.Single != 0 {
		t.Errorf("Expected 0 single files, got %d", filesReport.Single)
	}

	for _, fc := range filesReport.ByFile {
		if fc.Status != "UNANIMOUS" {
			t.Errorf("Expected UNANIMOUS status for all files, got %s for %s", fc.Status, fc.Path)
		}
	}
}

func TestFileConsistencyPartial(t *testing.T) {
	// Some workers touch different files
	report1 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{"fileA", "fileB", "fileC"},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "claude",
		TaskID:               "task-001",
	}

	report2 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{"fileB", "fileC", "fileD"},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "codex",
		TaskID:               "task-001",
	}

	reports := map[string]*adapter.BuildReport{
		"claude": report1,
		"codex":  report2,
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	filesReport := pkg.GetFilesReport()
	if filesReport == nil {
		t.Fatalf("Expected non-nil files report")
	}

	// fileA: 1 worker (SINGLE)
	// fileB: 2 workers (UNANIMOUS/PARTIAL depending on total)
	// fileC: 2 workers
	// fileD: 1 worker (SINGLE)

	if filesReport.Single < 2 {
		t.Errorf("Expected at least 2 single files, got %d", filesReport.Single)
	}

	if filesReport.Total != 4 {
		t.Errorf("Expected 4 total files, got %d", filesReport.Total)
	}
}

func TestAuditTrailLogging(t *testing.T) {
	// Create a temporary execution ID for this test
	execID := "test-audit-" + fmt.Sprintf("%d", time.Now().UnixNano())

	entry := AuditEntry{
		WorkerName: "claude",
		Action:     "STARTED",
		Details:    "Starting task execution",
		Status:     "SUCCESS",
	}

	err := LogAuditEntry(execID, entry)
	if err != nil {
		t.Fatalf("Failed to log audit entry: %v", err)
	}

	// Read back
	trail, err := ReadAuditTrail(execID)
	if err != nil {
		t.Fatalf("Failed to read audit trail: %v", err)
	}

	if len(trail.Entries) == 0 {
		t.Errorf("Expected at least 1 audit entry")
	}

	if trail.Entries[0].WorkerName != "claude" {
		t.Errorf("Expected worker name 'claude', got %s", trail.Entries[0].WorkerName)
	}

	if trail.Entries[0].Action != "STARTED" {
		t.Errorf("Expected action 'STARTED', got %s", trail.Entries[0].Action)
	}

	// Clean up
	homeDir, _ := os.UserHomeDir()
	os.RemoveAll(filepath.Join(homeDir, ".biah", "evidence", execID))
}

func TestAuditTrailPersistence(t *testing.T) {
	// Create a temporary execution ID for this test
	execID := "test-audit-persist-" + fmt.Sprintf("%d", time.Now().UnixNano())

	// Log multiple entries
	for i := 0; i < 3; i++ {
		entry := AuditEntry{
			WorkerName: "worker" + string(rune('a'+i)),
			Action:     "COMPLETED",
			Details:    "Task " + string(rune('0'+i)) + " completed",
			Status:     "SUCCESS",
		}
		if err := LogAuditEntry(execID, entry); err != nil {
			t.Fatalf("Failed to log audit entry: %v", err)
		}
	}

	// Read all entries
	trail, err := ReadAuditTrail(execID)
	if err != nil {
		t.Fatalf("Failed to read audit trail: %v", err)
	}

	if len(trail.Entries) != 3 {
		t.Errorf("Expected 3 audit entries, got %d", len(trail.Entries))
	}

	// Verify order
	for i := 0; i < 3 && i < len(trail.Entries); i++ {
		expected := "worker" + string(rune('a'+i))
		if trail.Entries[i].WorkerName != expected {
			t.Errorf("Entry %d: expected worker name %s, got %s", i, expected, trail.Entries[i].WorkerName)
		}
	}

	// Clean up
	homeDir, _ := os.UserHomeDir()
	os.RemoveAll(filepath.Join(homeDir, ".biah", "evidence", execID))
}

func TestParityReportGeneration(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	report := pkg.GenerateParityReport()
	if report == nil {
		t.Fatalf("Expected non-nil parity report")
	}

	if report.ExecutionID != pkg.ExecutionID {
		t.Errorf("Expected ExecutionID %s, got %s", pkg.ExecutionID, report.ExecutionID)
	}

	if report.TaskID != pkg.TaskID {
		t.Errorf("Expected TaskID %s, got %s", pkg.TaskID, report.TaskID)
	}

	if report.WorkerCount != 2 {
		t.Errorf("Expected WorkerCount 2, got %d", report.WorkerCount)
	}

	if report.ParityValidation == nil {
		t.Errorf("Expected non-nil ParityValidation")
	}

	if report.FilesReport == nil {
		t.Errorf("Expected non-nil FilesReport")
	}

	if len(report.StatusByWorker) != 2 {
		t.Errorf("Expected 2 status entries, got %d", len(report.StatusByWorker))
	}
}

func TestParityReportJSON(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	report := pkg.GenerateParityReport()

	// Create a temporary directory for output
	tmpDir := t.TempDir()

	err = WriteParityReport(report, tmpDir)
	if err != nil {
		t.Fatalf("Failed to write parity report: %v", err)
	}

	// Read back and verify
	jsonFile := filepath.Join(tmpDir, "parity-report.json")
	content, err := os.ReadFile(jsonFile)
	if err != nil {
		t.Fatalf("Failed to read parity report file: %v", err)
	}

	var readReport ParityReport
	err = json.Unmarshal(content, &readReport)
	if err != nil {
		t.Fatalf("Failed to unmarshal parity report: %v", err)
	}

	if readReport.ExecutionID != report.ExecutionID {
		t.Errorf("Expected ExecutionID %s, got %s", report.ExecutionID, readReport.ExecutionID)
	}

	if readReport.WorkerCount != report.WorkerCount {
		t.Errorf("Expected WorkerCount %d, got %d", report.WorkerCount, readReport.WorkerCount)
	}
}

func TestGetParityScore(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	score := pkg.GetParityScore()
	if score == nil {
		t.Fatalf("Expected non-nil score")
	}

	if score.Overall == 0 {
		t.Errorf("Expected non-zero overall score for identical reports")
	}

	if score.Overall > 100 {
		t.Errorf("Expected score <= 100, got %d", score.Overall)
	}
}

func TestRiskMatchScore(t *testing.T) {
	// Workers identify common risks
	report1 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{"risk1", "risk2", "risk3"},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "claude",
		TaskID:               "task-001",
	}

	report2 := &adapter.BuildReport{
		Status:               "SUCCESS",
		FilesChanged:         []string{},
		ValidationExecuted:   []string{},
		ValidationSkipped:    []string{},
		Assumptions:          []string{},
		RemainingRisks:       []string{"risk1", "risk2", "risk4"},
		HumanDecisionsNeeded: []string{},
		WorkerName:           "codex",
		TaskID:               "task-001",
	}

	reports := map[string]*adapter.BuildReport{
		"claude": report1,
		"codex":  report2,
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	score := pkg.GetParityScore()
	if score == nil {
		t.Fatalf("Expected non-nil score")
	}

	// Common risks: risk1, risk2 (2 out of 4 total)
	// Expected RiskMatch: (2/4) * 100 = 50%
	if score.RiskMatch < 40 || score.RiskMatch > 60 {
		t.Errorf("Expected RiskMatch around 50 percent, got %d", score.RiskMatch)
	}
}

func TestComputeStatusMatchAllSuccess(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude":  createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":   createTestReport("codex", "SUCCESS", 5, 2, 1),
		"copilot": createTestReport("copilot", "SUCCESS", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "SUCCESS")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	score := pkg.GetParityScore()
	if score == nil {
		t.Fatalf("Expected non-nil score")
	}

	if score.StatusMatch != 100 {
		t.Errorf("Expected StatusMatch 100 for all SUCCESS, got %d", score.StatusMatch)
	}
}

func TestComputeStatusMatchAllFailure(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "FAILURE", 5, 2, 1),
		"codex":  createTestReport("codex", "FAILURE", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "FAILURE")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	score := pkg.GetParityScore()
	if score == nil {
		t.Fatalf("Expected non-nil score")
	}

	if score.StatusMatch != 100 {
		t.Errorf("Expected StatusMatch 100 for all FAILURE, got %d", score.StatusMatch)
	}
}

func TestComputeStatusMatchMixed(t *testing.T) {
	reports := map[string]*adapter.BuildReport{
		"claude": createTestReport("claude", "SUCCESS", 5, 2, 1),
		"codex":  createTestReport("codex", "FAILURE", 5, 2, 1),
	}
	result := createTestExecutionResult(reports, "FAILURE")

	pkg, err := Aggregate(result)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	score := pkg.GetParityScore()
	if score == nil {
		t.Fatalf("Expected non-nil score")
	}

	if score.StatusMatch != 0 {
		t.Errorf("Expected StatusMatch 0 for mixed status, got %d", score.StatusMatch)
	}
}
