package evidence

import (
	"fmt"
	"strings"
	"time"

	"github.com/biahflow/engineering-os/biah/pkg/adapter"
	"github.com/biahflow/engineering-os/biah/pkg/executor"
	"github.com/google/uuid"
)

// ParityValidation holds the results of harness parity checks
type ParityValidation struct {
	Valid       bool
	Differences []string
	Warnings    []string
}

// EvidencePackage holds all aggregated worker evidence
type EvidencePackage struct {
	TaskID                   string
	ExecutionID              string // UUID for this run
	CreatedAt                time.Time
	TotalDuration            int64 // milliseconds
	WorkerReports            map[string]*adapter.BuildReport
	HarnessParity            ParityValidation
	DetailedParityValidation *DetailedParityValidation // Enhanced parity with scoring
	OverallStatus            string                    // SUCCESS, PARTIAL, FAILURE
	FilesChanged             int
	ValidationsPassed        int
	RisksIdentified          []string
	Assumptions              []string
}

// Aggregate combines all BUILD REPORTs from executor results into an EvidencePackage
func Aggregate(results *executor.ExecutionResult) (*EvidencePackage, error) {
	if results == nil {
		return nil, fmt.Errorf("execution results cannot be nil")
	}

	pkg := &EvidencePackage{
		ExecutionID:   uuid.New().String(),
		CreatedAt:     time.Now(),
		TotalDuration: results.ExecutionTimeMs,
		WorkerReports: make(map[string]*adapter.BuildReport),
		OverallStatus: results.Status,
	}

	// Aggregate reports from all task results
	filesChangedSet := make(map[string]bool)
	riskSet := make(map[string]bool)
	assumptionSet := make(map[string]bool)

	for taskID, taskResult := range results.TaskResults {
		if taskResult.BuildReport != nil {
			workerName := taskResult.WorkerName
			if workerName == "" {
				workerName = fmt.Sprintf("unknown_%d", len(pkg.WorkerReports))
			}

			// Store the report keyed by worker name
			pkg.WorkerReports[workerName] = taskResult.BuildReport

			// Aggregate files changed
			for _, file := range taskResult.BuildReport.FilesChanged {
				filesChangedSet[file] = true
			}

			// Aggregate risks
			for _, risk := range taskResult.BuildReport.RemainingRisks {
				riskSet[risk] = true
			}

			// Aggregate assumptions
			for _, assumption := range taskResult.BuildReport.Assumptions {
				assumptionSet[assumption] = true
			}

			// Count validations passed
			pkg.ValidationsPassed += len(taskResult.BuildReport.ValidationExecuted)
		}

		// Set TaskID from first task found
		if pkg.TaskID == "" && taskID != "" {
			pkg.TaskID = taskID
		}
	}

	// Convert sets to slices
	pkg.FilesChanged = len(filesChangedSet)
	for risk := range riskSet {
		pkg.RisksIdentified = append(pkg.RisksIdentified, risk)
	}
	for assumption := range assumptionSet {
		pkg.Assumptions = append(pkg.Assumptions, assumption)
	}

	// Validate harness parity
	pkg.HarnessParity = validateParity(pkg)
	pkg.DetailedParityValidation = validateParityEnhanced(pkg)

	return pkg, nil
}

// ValidateParity checks that all workers produced comparable evidence
// Returns a list of any validation issues
func ValidateParity(pkg *EvidencePackage) ([]string, error) {
	if pkg == nil {
		return nil, fmt.Errorf("evidence package cannot be nil")
	}

	var issues []string

	if !pkg.HarnessParity.Valid {
		issues = append(issues, pkg.HarnessParity.Differences...)
	}
	issues = append(issues, pkg.HarnessParity.Warnings...)

	return issues, nil
}

// validateParity performs internal parity validation
func validateParity(pkg *EvidencePackage) ParityValidation {
	parity := ParityValidation{
		Valid:       true,
		Differences: []string{},
		Warnings:    []string{},
	}

	if len(pkg.WorkerReports) == 0 {
		return parity
	}

	if len(pkg.WorkerReports) == 1 {
		// Only one worker, no parity check needed
		return parity
	}

	// Extract all reports
	var reports []*adapter.BuildReport
	var workerNames []string
	for name, report := range pkg.WorkerReports {
		reports = append(reports, report)
		workerNames = append(workerNames, name)
	}

	if len(reports) == 0 {
		return parity
	}

	firstReport := reports[0]

	// Check file count consistency (±1 tolerance acceptable)
	fileCountFirst := len(firstReport.FilesChanged)
	for i, report := range reports[1:] {
		fileCount := len(report.FilesChanged)
		if diff := abs(fileCount - fileCountFirst); diff > 1 {
			parity.Valid = false
			parity.Differences = append(parity.Differences,
				fmt.Sprintf("File count mismatch: %s reports %d files, %s reports %d files",
					workerNames[0], fileCountFirst, workerNames[i+1], fileCount))
		}
	}

	// Check status consistency
	firstStatus := firstReport.Status
	for i, report := range reports[1:] {
		if report.Status != firstStatus {
			parity.Valid = false
			parity.Differences = append(parity.Differences,
				fmt.Sprintf("Status mismatch: %s reports %q, %s reports %q",
					workerNames[0], firstStatus, workerNames[i+1], report.Status))
		}
	}

	// Check for assumption differences (warnings only)
	firstAssumptions := len(firstReport.Assumptions)
	for i, report := range reports[1:] {
		assumptionCount := len(report.Assumptions)
		if diff := abs(assumptionCount - firstAssumptions); diff > 2 {
			parity.Warnings = append(parity.Warnings,
				fmt.Sprintf("Assumption count differs: %s has %d, %s has %d",
					workerNames[0], firstAssumptions, workerNames[i+1], assumptionCount))
		}
	}

	return parity
}

// GetParityScore returns the parity score from enhanced validation
func (pkg *EvidencePackage) GetParityScore() *ParityScore {
	if pkg.DetailedParityValidation == nil || pkg.DetailedParityValidation.Score == nil {
		return &ParityScore{Overall: 0}
	}
	return pkg.DetailedParityValidation.Score
}

// GetFilesReport returns the detailed files analysis
func (pkg *EvidencePackage) GetFilesReport() *DetailedFilesReport {
	if pkg.DetailedParityValidation == nil {
		return &DetailedFilesReport{}
	}
	return analyzeFileConsistency(pkg)
}

// Summary returns a human-readable summary of the evidence package
func (pkg *EvidencePackage) Summary() string {
	var sb strings.Builder

	// Overall status indicator
	statusEmoji := "❓"
	switch pkg.OverallStatus {
	case "SUCCESS":
		statusEmoji = "✅"
	case "FAILURE":
		statusEmoji = "❌"
	case "PARTIAL":
		statusEmoji = "⚠️"
	}

	sb.WriteString(fmt.Sprintf("%s Evidence Package: %s\n", statusEmoji, pkg.TaskID))

	// Workers
	var workerList []string
	for name := range pkg.WorkerReports {
		workerList = append(workerList, toTitleCase(name))
	}
	sb.WriteString(fmt.Sprintf("Workers: %s\n", strings.Join(workerList, ", ")))

	// Overall status
	sb.WriteString(fmt.Sprintf("Status: %s\n", pkg.OverallStatus))

	// Files changed
	sb.WriteString(fmt.Sprintf("Files Changed: %d\n", pkg.FilesChanged))

	// Parity status
	if pkg.HarnessParity.Valid {
		sb.WriteString("Parity: Valid\n")
	} else {
		sb.WriteString("Parity: ⚠️ Issues Detected\n")
		for _, diff := range pkg.HarnessParity.Differences {
			sb.WriteString(fmt.Sprintf("  - %s\n", diff))
		}
	}

	// Warnings
	for _, warning := range pkg.HarnessParity.Warnings {
		sb.WriteString(fmt.Sprintf("  ⚠️ %s\n", warning))
	}

	// Validations passed
	sb.WriteString(fmt.Sprintf("Validations Passed: %d\n", pkg.ValidationsPassed))

	// Assumptions count
	sb.WriteString(fmt.Sprintf("Assumptions: %d total\n", len(pkg.Assumptions)))

	// Risks
	sb.WriteString(fmt.Sprintf("Risks: %d identified\n", len(pkg.RisksIdentified)))

	// Duration
	sb.WriteString(fmt.Sprintf("Duration: %dms\n", pkg.TotalDuration))

	return sb.String()
}

// Helper function
func abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}

// toTitleCase converts a string to proper title case (e.g., "claude" -> "Claude")
func toTitleCase(s string) string {
	if len(s) == 0 {
		return s
	}
	return strings.ToUpper(s[:1]) + strings.ToLower(s[1:])
}
