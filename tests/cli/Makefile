# CLI Pillar Tests - Python unit and integration tests
#
# These tests require the cortex package to be installed:
#   pip install -e .

.PHONY: all tests clean help
.PHONY: test-unit test-integration

# Python tests don't have a build step
all:
	@echo "CLI tests are Python - no build step required"
	@echo "Run 'make tests' to execute tests"

# Run all CLI tests (unit + integration)
tests: test-unit test-integration

# Run unit tests only
test-unit:
	@echo "========================================="
	@echo "Running CLI Unit Tests"
	@echo "========================================="
	@cd ../.. && python -m pytest tests/cli/unit -v

# Run integration tests only
test-integration:
	@echo "========================================="
	@echo "Running CLI Integration Tests"
	@echo "========================================="
	@cd ../.. && python -m pytest tests/cli/integration -v

# No build artifacts to clean for Python tests
clean:
	@echo "Cleaning Python cache files..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "CLI tests cleaned!"

help:
	@echo "CLI Pillar Tests (Python)"
	@echo ""
	@echo "Prerequisites:"
	@echo "  pip install -e .    # Install cortex package in development mode"
	@echo ""
	@echo "Test Targets:"
	@echo "  tests               # Run all CLI tests (unit + integration)"
	@echo "  test-unit           # Run unit tests only"
	@echo "  test-integration    # Run integration tests only"
	@echo ""
	@echo "Utilities:"
	@echo "  clean               # Remove Python cache files"
	@echo "  help                # Show this message"
