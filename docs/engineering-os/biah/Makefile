.PHONY: build run test clean help

BINARY_NAME=biah
MAIN_PATH=cmd/biah/main.go

# Build the biah binary
build:
	@echo "Building $(BINARY_NAME)..."
	@go build -o bin/$(BINARY_NAME) $(MAIN_PATH)
	@echo "✓ Built: bin/$(BINARY_NAME)"

# Run biah (requires arguments)
run: build
	@./bin/$(BINARY_NAME)

# Run specific command
task:
	@./bin/$(BINARY_NAME) task HC-006

plan:
	@./bin/$(BINARY_NAME) plan HC-006

status:
	@./bin/$(BINARY_NAME) status

# Run tests
test:
	@echo "Running tests..."
	@go test ./...

# Code coverage
coverage:
	@go test -v -coverprofile=coverage.out ./...
	@go tool cover -html=coverage.out -o coverage.html
	@echo "✓ Coverage: coverage.html"

# Lint
lint:
	@golangci-lint run ./...

# Format
fmt:
	@go fmt ./...

# Tidy dependencies
tidy:
	@go mod tidy

# Clean build artifacts
clean:
	@rm -rf bin/ coverage.*
	@echo "✓ Cleaned"

# Help
help:
	@echo "Biah CLI - Vendor-Neutral Multi-Agent Orchestrator"
	@echo ""
	@echo "Usage:"
	@echo "  make build       - Build biah binary"
	@echo "  make run         - Run biah (shows help)"
	@echo "  make task        - Run: biah task HC-006 (example)"
	@echo "  make plan        - Run: biah plan HC-006 (example)"
	@echo "  make status      - Run: biah status (example)"
	@echo "  make test        - Run tests"
	@echo "  make coverage    - Generate coverage report"
	@echo "  make lint        - Run linter"
	@echo "  make fmt         - Format code"
	@echo "  make tidy        - Tidy dependencies"
	@echo "  make clean       - Remove build artifacts"
	@echo "  make help        - Show this help"
