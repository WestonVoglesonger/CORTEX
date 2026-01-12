# CLI Pillar Tests - Python unit and integration tests
#
# These tests require the cortex package to be installed:
#   pip install -e .

.PHONY: all tests clean help check-env
.PHONY: test-unit test-integration

# Python tests don't have a build step
all:
	@echo "CLI tests are Python - no build step required"
	@echo "Run 'make tests' to execute tests"

# Validate Python environment before running tests
check-env:
	@echo "Validating Python environment..."
	@python -c "import cortex" 2>/dev/null || \
		(echo "" && \
		 echo "❌ ERROR: cortex package not installed" && \
		 echo "" && \
		 echo "Required setup (from CORTEX root):" && \
		 echo "  pip install -e ." && \
		 echo "" && \
		 echo "This installs the cortex package in development mode," && \
		 echo "allowing tests to import from src/cortex/." && \
		 echo "" && exit 1)
	@echo "✓ cortex package found"

# Run all CLI tests (unit + integration)
tests: check-env test-unit test-integration

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
	@echo "  tests               # Run all CLI tests (validates environment first)"
	@echo "  test-unit           # Run unit tests only"
	@echo "  test-integration    # Run integration tests only"
	@echo "  check-env           # Validate Python environment (auto-run before tests)"
	@echo ""
	@echo "Utilities:"
	@echo "  clean               # Remove Python cache files"
	@echo "  help                # Show this message"
