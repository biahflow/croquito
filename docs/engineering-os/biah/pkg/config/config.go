package config

// Config holds Biah configuration
type Config struct {
	BasePath         string
	EOS_ROOT         string
	DefaultBranch    string
	ExecutionTimeout int
	Workers          map[string]WorkerConfig
}

// WorkerConfig holds per-worker configuration
type WorkerConfig struct {
	Enabled bool
	CLIPath string
	Timeout int
}

// DefaultConfig returns the default configuration
func DefaultConfig() *Config {
	return &Config{
		BasePath:         ".",
		EOS_ROOT:         ".", // Will be replaced with actual path
		DefaultBranch:    "main",
		ExecutionTimeout: 3600,
		Workers: map[string]WorkerConfig{
			"claude": {
				Enabled: true,
				CLIPath: "claude",
				Timeout: 3600,
			},
			"codex": {
				Enabled: true,
				CLIPath: "codex",
				Timeout: 3600,
			},
			"copilot": {
				Enabled: true,
				CLIPath: "copilot",
				Timeout: 3600,
			},
		},
	}
}
