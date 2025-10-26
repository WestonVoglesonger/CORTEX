# Top-level Makefile for CORTEX benchmarking pipeline
# Orchestrates building harness, plugins, and tests

.PHONY: all harness plugins tests clean help

# Default target: build everything
all: harness plugins tests

# Build the harness
harness:
	@echo "Building harness..."
	$(MAKE) -C src/harness

# Build plugins (kernels from registry)
plugins:
	@echo "Building kernel plugins from registry..."
	@for dir in kernels/v1/*@*/; do \
		if [ -f "$$dir/Makefile" ]; then \
			echo "  Building $$(basename $$dir)..."; \
			$(MAKE) -C "$$dir" || true; \
		fi \
	done

# Build and run tests
tests:
	@echo "Building and running tests..."
	$(MAKE) -C tests
	$(MAKE) -C tests test

# Clean everything
clean:
	@echo "Cleaning all build artifacts..."
	$(MAKE) -C src/harness clean
	@for dir in kernels/v1/*@*/; do \
		if [ -f "$$dir/Makefile" ]; then \
			$(MAKE) -C "$$dir" clean || true; \
		fi \
	done
	$(MAKE) -C tests clean

# Development workflow
dev: clean all
	@echo "Full development build complete!"

# Show help
help:
	@echo "CORTEX Build System"
	@echo ""
	@echo "Available targets:"
	@echo "  all      - Build harness, plugins, and run tests (default)"
	@echo "  harness  - Build the benchmarking harness"
	@echo "  plugins  - Build all plugins"
	@echo "  tests    - Build and run unit tests"
	@echo "  clean    - Clean all build artifacts"
	@echo "  dev      - Full clean + rebuild cycle"
	@echo "  help     - Show this help message"
	@echo ""
	@echo "Examples:"
	@echo "  make              # Build everything"
	@echo "  make harness      # Build only harness"
	@echo "  make plugins      # Build only plugins"
	@echo "  make clean all    # Clean and rebuild"
