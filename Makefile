# Top-level Makefile for CORTEX benchmarking pipeline
# Orchestrates building SDK, harness, plugins, and tests

.PHONY: all sdk harness plugins adapters tests clean help

# Default target: build everything
all: sdk harness plugins adapters tests

# Build SDK (kernel library and tools)
sdk:
	@echo "Building CORTEX SDK..."
	$(MAKE) -C sdk

# Build the harness
harness: sdk
	@echo "Building harness..."
	$(MAKE) -C src/engine/harness

# Build plugins (kernels from registry) - depends on SDK
plugins: sdk
	@echo "Building kernel plugins from registry..."
	@for version_dir in primitives/kernels/v*/; do \
		if [ -d "$$version_dir" ]; then \
			for dir in $$version_dir*@*/; do \
				if [ -f "$$dir/Makefile" ]; then \
					echo "  Building $$(basename $$(dirname $$dir))/$$(basename $$dir)..."; \
					$(MAKE) -C "$$dir"; \
				fi \
			done \
		fi \
	done

# Build adapters - depends on SDK
adapters: sdk
	@echo "Building device adapters..."
	@for version_dir in primitives/adapters/v*/; do \
		if [ -d "$$version_dir" ]; then \
			for dir in $$version_dir*/; do \
				if [ -f "$$dir/Makefile" ] && [ "$$(basename $$dir)" != "README.md" ]; then \
					echo "  Building $$(basename $$(dirname $$dir))/$$(basename $$dir)..."; \
					$(MAKE) -C "$$dir"; \
				fi \
			done \
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
	$(MAKE) -C sdk clean
	$(MAKE) -C src/engine/harness clean
	@for version_dir in primitives/kernels/v*/; do \
		if [ -d "$$version_dir" ]; then \
			for dir in $$version_dir*@*/; do \
				if [ -f "$$dir/Makefile" ]; then \
					$(MAKE) -C "$$dir" clean || true; \
				fi \
			done \
		fi \
	done
	@for version_dir in primitives/adapters/v*/; do \
		if [ -d "$$version_dir" ]; then \
			for dir in $$version_dir*/; do \
				if [ -f "$$dir/Makefile" ]; then \
					$(MAKE) -C "$$dir" clean || true; \
				fi \
			done \
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
	@echo "  all      - Build SDK, harness, plugins, adapters, and run tests (default)"
	@echo "  sdk      - Build CORTEX SDK (kernel lib + tools)"
	@echo "  harness  - Build the benchmarking harness"
	@echo "  plugins  - Build all kernel plugins"
	@echo "  adapters - Build all device adapters"
	@echo "  tests    - Build and run unit tests"
	@echo "  clean    - Clean all build artifacts"
	@echo "  dev      - Full clean + rebuild cycle"
	@echo "  help     - Show this help message"
	@echo ""
	@echo "Examples:"
	@echo "  make              # Build everything"
	@echo "  make sdk          # Build only SDK"
	@echo "  make harness      # Build only harness"
	@echo "  make plugins      # Build only plugins"
	@echo "  make adapters     # Build only adapters"
	@echo "  make clean all    # Clean and rebuild"
