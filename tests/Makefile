# CORTEX Testing System - 4-Pillar Architecture
#
# Directory Structure (aligned with CORTEX architecture):
#   engine/     - Engine pillar (scheduler, telemetry, replayer, harness)
#   adapter/    - Adapter SDK pillar (protocol, transport, device communication)
#   kernel/     - Kernel SDK pillar (plugin interface examples)
#   cli/        - CLI pillar (Python orchestration and commands)
#   fixtures/   - Shared test utilities and mock implementations
#
# Each pillar has its own Makefile with auto-discovery and build/ subdirectory.

.PHONY: all tests clean help
.PHONY: test-engine test-adapter test-kernel test-cli

# Build all C test binaries
all:
	@echo "Building all test binaries..."
	@$(MAKE) -C engine all
	@$(MAKE) -C adapter all
	@$(MAKE) -C kernel all
	@echo "All test binaries built successfully!"

# Run all test suites
tests: test-engine test-adapter test-kernel test-cli

# Run Engine pillar tests
test-engine:
	@$(MAKE) -C engine tests

# Run Adapter SDK pillar tests
test-adapter:
	@$(MAKE) -C adapter tests

# Run Kernel SDK pillar tests
test-kernel:
	@$(MAKE) -C kernel tests

# Run CLI pillar tests (Python)
test-cli:
	@echo "========================================="
	@echo "Running CLI Tests"
	@echo "========================================="
	@echo "Running Python unit tests..."
	@cd .. && python -m pytest tests/unit -v
	@echo "Running Python integration tests..."
	@cd .. && python -m pytest tests/integration -v
	@echo "CLI tests: PASS"

# Clean all build artifacts
clean:
	@$(MAKE) -C engine clean
	@$(MAKE) -C adapter clean
	@$(MAKE) -C kernel clean
	@echo "All build artifacts cleaned!"

# Show help
help:
	@echo "CORTEX Testing System - 4-Pillar Architecture"
	@echo ""
	@echo "Build Targets:"
	@echo "  all            - Build all C test binaries (engine, adapter, kernel)"
	@echo ""
	@echo "Test Suites:"
	@echo "  tests          - Run all test suites (engine, adapter, kernel, CLI)"
	@echo "  test-engine    - Run Engine pillar tests (scheduler, telemetry, etc.)"
	@echo "  test-adapter   - Run Adapter SDK pillar tests (protocol, transport)"
	@echo "  test-kernel    - Run Kernel SDK pillar tests (plugin examples)"
	@echo "  test-cli       - Run CLI pillar tests (Python unit/integration)"
	@echo ""
	@echo "Utilities:"
	@echo "  clean          - Remove all build artifacts"
	@echo "  help           - Show this message"
	@echo ""
	@echo "Directory Structure:"
	@echo "  engine/        - Engine pillar C tests"
	@echo "  adapter/       - Adapter SDK C tests"
	@echo "  kernel/        - Kernel SDK C examples"
	@echo "  cli/           - CLI Python tests"
	@echo "  fixtures/      - Shared test utilities"
