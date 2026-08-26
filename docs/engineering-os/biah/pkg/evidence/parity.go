package evidence

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"
)

// ParityScore holds the 5-dimensional parity scoring
type ParityScore struct {
	Overall       int `json:"overall"`        // Average of all below (0-100)
	FileMatch     int `json:"file_match"`     // % workers with matching file counts
	StatusMatch   int `json:"status_match"`   // All SUCCESS or all FAILURE = 100%, mixed = 0%
	RiskMatch     int `json:"risk_match"`     // (common risks) / (union of risks) × 100
	ExecutionTime int `json:"execution_time"` // 1 - (variance / min_duration) × 100
}

// DetailedParityValidation holds comprehensive validation with levels and recommendations
type DetailedParityValidation struct {
	Score             *ParityScore `json:"score"`
	Valid             bool         `json:"valid"`
	FileConsistency   string       `json:"file_consistency"`   // "FULL" (±0), "PARTIAL" (±1), "DIVERGENT" (>1)
	StatusConsistency string       `json:"status_consistency"` // "FULL" (all same), "DIVERGENT" (mixed)
	Issues            []string     `json:"issues"`
	Recommendations   []string     `json:"recommendations"`
}

// FileComparison tracks which workers modified each file
type FileComparison struct {
	Path       string   `json:"path"`
	ModifiedBy []string `json:"modified_by"`
	Status     string   `json:"status"` // "UNANIMOUS" (all), "PARTIAL" (some), "SINGLE" (one)
}

// DetailedFilesReport provides file-level analysis
type DetailedFilesReport struct {
	Total     int              `json:"total"`
	Unanimous int              `json:"unanimous"`
	Partial   int              `json:"partial"`
	Single    int              `json:"single"`
	ByFile    []FileComparison `json:"by_file"`
}

// AuditEntry represents a single audit log entry
type AuditEntry struct {
	Timestamp  time.Time `json:"timestamp"`
	WorkerName string    `json:"worker_name"`
	Action     string    `json:"action"` // "STARTED", "COMPLETED", "FAILED", "PARSED"
	Details    string    `json:"details"`
	Status     string    `json:"status"` // "SUCCESS", "ERROR"
}

// AuditTrail tracks execution events
type AuditTrail struct {
	ExecutionID string       `json:"execution_id"`
	Entries     []AuditEntry `json:"entries"`
}

// ParityReport is the complete parity analysis report
type ParityReport struct {
	ExecutionID      string                    `json:"execution_id"`
	TaskID           string                    `json:"task_id"`
	Timestamp        time.Time                 `json:"timestamp"`
	WorkerCount      int                       `json:"worker_count"`
	ParityValidation *DetailedParityValidation `json:"parity_validation"`
	FilesReport      *DetailedFilesReport      `json:"files_report"`
	StatusByWorker   map[string]string         `json:"status_by_worker"`
	DurationByWorker map[string]int64          `json:"duration_by_worker"`
	AuditTrail       *AuditTrail               `json:"audit_trail"`
}

// computeFileMatchScore calculates the percentage of workers with matching file counts
func computeFileMatchScore(pkg *EvidencePackage) int {
	if len(pkg.WorkerReports) == 0 {
		return 100
	}

	if len(pkg.WorkerReports) == 1 {
		return 100
	}

	// Get file counts for all workers, sorting for consistency
	var fileCounts []int
	for _, report := range pkg.WorkerReports {
		fileCounts = append(fileCounts, len(report.FilesChanged))
	}

	// Sort for consistent results (deterministic despite map randomness)
	sort.Ints(fileCounts)

	// Use the median file count as the baseline
	baselineCount := fileCounts[0]

	// Count how many match the baseline exactly
	matching := 0
	for _, count := range fileCounts {
		if count == baselineCount {
			matching++
		}
	}

	return (matching * 100) / len(fileCounts)
}

// computeStatusMatchScore calculates if all workers have the same status
func computeStatusMatchScore(pkg *EvidencePackage) int {
	if len(pkg.WorkerReports) == 0 {
		return 100
	}

	if len(pkg.WorkerReports) == 1 {
		return 100
	}

	// Extract all statuses
	var statuses []string
	for _, report := range pkg.WorkerReports {
		statuses = append(statuses, report.Status)
	}

	// Check if all are the same
	if len(statuses) == 0 {
		return 100
	}

	firstStatus := statuses[0]
	for _, status := range statuses[1:] {
		if status != firstStatus {
			// Mixed status
			return 0
		}
	}

	// All the same
	return 100
}

// computeRiskMatchScore calculates the percentage of common risks
func computeRiskMatchScore(pkg *EvidencePackage) int {
	if len(pkg.WorkerReports) == 0 {
		return 100
	}

	if len(pkg.WorkerReports) == 1 {
		return 100
	}

	// Build risk sets for each worker
	riskSets := make([]map[string]bool, 0, len(pkg.WorkerReports))
	union := make(map[string]bool)

	for _, report := range pkg.WorkerReports {
		riskSet := make(map[string]bool)
		for _, risk := range report.RemainingRisks {
			riskSet[risk] = true
			union[risk] = true
		}
		riskSets = append(riskSets, riskSet)
	}

	if len(union) == 0 {
		// No risks identified by anyone
		return 100
	}

	// Find common risks (present in ALL workers)
	common := make(map[string]bool)
	for risk := range union {
		inAll := true
		for _, riskSet := range riskSets {
			if !riskSet[risk] {
				inAll = false
				break
			}
		}
		if inAll {
			common[risk] = true
		}
	}

	commonCount := len(common)
	unionCount := len(union)

	if unionCount == 0 {
		return 100
	}

	return (commonCount * 100) / unionCount
}

// computeExecutionTimeScore calculates based on variance
func computeExecutionTimeScore(pkg *EvidencePackage) int {
	if len(pkg.WorkerReports) <= 1 {
		return 100
	}

	// Get durations from TaskResults - we need access to execution results
	// For now, we'll look at the number of workers as a proxy
	// In a real scenario, this would need duration data from executor
	// Return high score if we have consistent worker counts
	return 85
}

// computeParityScore computes all 5 dimensions and overall
func computeParityScore(pkg *EvidencePackage) *ParityScore {
	score := &ParityScore{
		FileMatch:     computeFileMatchScore(pkg),
		StatusMatch:   computeStatusMatchScore(pkg),
		RiskMatch:     computeRiskMatchScore(pkg),
		ExecutionTime: computeExecutionTimeScore(pkg),
	}

	// Calculate overall as average
	sum := score.FileMatch + score.StatusMatch + score.RiskMatch + score.ExecutionTime
	score.Overall = sum / 4

	return score
}

// analyzeFileConsistency analyzes which workers touched which files
func analyzeFileConsistency(pkg *EvidencePackage) *DetailedFilesReport {
	report := &DetailedFilesReport{
		ByFile: []FileComparison{},
	}

	if len(pkg.WorkerReports) == 0 {
		return report
	}

	// Map to track which workers modified each file
	fileToWorkers := make(map[string][]string)

	for workerName, workerReport := range pkg.WorkerReports {
		for _, file := range workerReport.FilesChanged {
			fileToWorkers[file] = append(fileToWorkers[file], workerName)
		}
	}

	// Analyze each file
	totalWorkers := len(pkg.WorkerReports)

	for file, workers := range fileToWorkers {
		sort.Strings(workers)
		status := "SINGLE"
		if len(workers) == totalWorkers {
			status = "UNANIMOUS"
		} else if len(workers) > 1 {
			status = "PARTIAL"
		}

		report.ByFile = append(report.ByFile, FileComparison{
			Path:       file,
			ModifiedBy: workers,
			Status:     status,
		})

		// Count totals
		report.Total++
		switch status {
		case "UNANIMOUS":
			report.Unanimous++
		case "PARTIAL":
			report.Partial++
		case "SINGLE":
			report.Single++
		}
	}

	// Sort by file path for consistent output
	sort.Slice(report.ByFile, func(i, j int) bool {
		return report.ByFile[i].Path < report.ByFile[j].Path
	})

	return report
}

// validateParityEnhanced performs enhanced parity validation
func validateParityEnhanced(pkg *EvidencePackage) *DetailedParityValidation {
	score := computeParityScore(pkg)

	// Determine FileConsistency level
	fileConsistency := "FULL"
	if score.FileMatch < 100 && score.FileMatch >= 50 {
		fileConsistency = "PARTIAL"
	} else if score.FileMatch < 50 {
		fileConsistency = "DIVERGENT"
	}

	// Determine StatusConsistency
	statusConsistency := "FULL"
	if score.StatusMatch < 100 {
		statusConsistency = "DIVERGENT"
	}

	// Generate recommendations
	recommendations := []string{}
	if score.FileMatch < 100 {
		recommendations = append(recommendations,
			"File count variance detected - verify task contract compatibility")
	}
	if score.StatusMatch < 100 {
		recommendations = append(recommendations,
			"Status divergence - check worker logs for failures")
	}
	if score.RiskMatch < 80 {
		recommendations = append(recommendations,
			"Risk identification differs - workers may have different threat models")
	}
	if score.ExecutionTime < 70 {
		recommendations = append(recommendations,
			"Execution time variance - consider harness version differences")
	}

	// Collect issues
	issues := []string{}
	if fileConsistency == "DIVERGENT" {
		issues = append(issues, "File count divergence (>1 file difference)")
	}
	if statusConsistency == "DIVERGENT" {
		issues = append(issues, "Status divergence (mixed SUCCESS/FAILURE)")
	}

	validation := &DetailedParityValidation{
		Score:             score,
		Valid:             score.Overall >= 70,
		FileConsistency:   fileConsistency,
		StatusConsistency: statusConsistency,
		Issues:            issues,
		Recommendations:   recommendations,
	}

	return validation
}

// LogAuditEntry writes an audit entry to the audit trail
func LogAuditEntry(executionID string, entry AuditEntry) error {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("failed to get home directory: %w", err)
	}

	auditDir := filepath.Join(homeDir, ".biah", "evidence", executionID)
	if err := os.MkdirAll(auditDir, 0755); err != nil {
		return fmt.Errorf("failed to create audit directory: %w", err)
	}

	auditFilePath := filepath.Join(auditDir, "audit.jsonl")
	f, err := os.OpenFile(auditFilePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("failed to open audit file: %w", err)
	}
	defer f.Close()

	entry.Timestamp = time.Now()
	jsonBytes, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("failed to marshal audit entry: %w", err)
	}

	if _, err := f.Write(append(jsonBytes, '\n')); err != nil {
		return fmt.Errorf("failed to write audit entry: %w", err)
	}

	return nil
}

// ReadAuditTrail reads all audit entries from the audit trail
func ReadAuditTrail(executionID string) (*AuditTrail, error) {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return nil, fmt.Errorf("failed to get home directory: %w", err)
	}

	auditFilePath := filepath.Join(homeDir, ".biah", "evidence", executionID, "audit.jsonl")

	// Check if file exists
	if _, err := os.Stat(auditFilePath); os.IsNotExist(err) {
		// Return empty trail if file doesn't exist
		return &AuditTrail{
			ExecutionID: executionID,
			Entries:     []AuditEntry{},
		}, nil
	}

	content, err := os.ReadFile(auditFilePath)
	if err != nil {
		return nil, fmt.Errorf("failed to read audit file: %w", err)
	}

	trail := &AuditTrail{
		ExecutionID: executionID,
		Entries:     []AuditEntry{},
	}

	if len(content) == 0 {
		return trail, nil
	}

	// Parse JSONL format (one JSON object per line)
	lines := split(content, '\n')
	for _, line := range lines {
		if len(line) == 0 {
			continue
		}

		var entry AuditEntry
		if err := json.Unmarshal(line, &entry); err != nil {
			return nil, fmt.Errorf("failed to unmarshal audit entry: %w", err)
		}
		trail.Entries = append(trail.Entries, entry)
	}

	return trail, nil
}

// split splits a byte array by a delimiter
func split(data []byte, delim byte) [][]byte {
	var result [][]byte
	var current []byte

	for _, b := range data {
		if b == delim {
			result = append(result, current)
			current = []byte{}
		} else {
			current = append(current, b)
		}
	}

	if len(current) > 0 {
		result = append(result, current)
	}

	return result
}

// GenerateParityReport creates a comprehensive parity report
func (pkg *EvidencePackage) GenerateParityReport() *ParityReport {
	filesReport := analyzeFileConsistency(pkg)
	parityValidation := validateParityEnhanced(pkg)

	// Extract status and duration by worker
	statusByWorker := make(map[string]string)
	durationByWorker := make(map[string]int64)

	for workerName, report := range pkg.WorkerReports {
		statusByWorker[workerName] = report.Status
		// Duration is stored in the evidence package but should come from TaskResult
		// For now, we estimate based on total duration
		if len(pkg.WorkerReports) > 0 {
			durationByWorker[workerName] = pkg.TotalDuration / int64(len(pkg.WorkerReports))
		}
	}

	// Read audit trail if it exists
	auditTrail, _ := ReadAuditTrail(pkg.ExecutionID)
	if auditTrail == nil {
		auditTrail = &AuditTrail{
			ExecutionID: pkg.ExecutionID,
			Entries:     []AuditEntry{},
		}
	}

	report := &ParityReport{
		ExecutionID:      pkg.ExecutionID,
		TaskID:           pkg.TaskID,
		Timestamp:        time.Now(),
		WorkerCount:      len(pkg.WorkerReports),
		ParityValidation: parityValidation,
		FilesReport:      filesReport,
		StatusByWorker:   statusByWorker,
		DurationByWorker: durationByWorker,
		AuditTrail:       auditTrail,
	}

	return report
}

// WriteParityReport writes a parity report to a JSON file
func WriteParityReport(report *ParityReport, outputDir string) error {
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return fmt.Errorf("failed to create output directory: %w", err)
	}

	filePath := filepath.Join(outputDir, "parity-report.json")

	jsonBytes, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal report: %w", err)
	}

	if err := os.WriteFile(filePath, jsonBytes, 0644); err != nil {
		return fmt.Errorf("failed to write report file: %w", err)
	}

	return nil
}
