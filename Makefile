# Top-level Makefile for CORTEX benchmarking pipeline
# Orchestrates building harness, plugins, and tests

.PHONY: all params harness plugins tests clean help

# Primitive include paths - exported for sub-makes
export CORTEX_PRIMITIVE_INCLUDES = -I$(PWD)/primitives/kernels/v1 -I$(PWD)/primitives/adapters/v1

# Kernel ABI object (compiled once, linked into all kernels)
KERNEL_ABI_OBJ = primitives/kernels/v1/cortex_plugin_abi.o

# Adapter ABI object (compiled once, linked into all adapters)
ADAPTER_ABI_OBJ = primitives/adapters/v1/cortex_adapter_abi.o

# Default target: build everything
all: params harness plugins tests

# Build parameter accessor library
params:
	@echo "Building parameter accessor library..."
	$(MAKE) -C src/engine/params

# Build the harness
harness:
	@echo "Building harness..."
	$(MAKE) -C src/engine/harness

# Build kernel ABI object (compiled once, linked by all kernels)
$(KERNEL_ABI_OBJ): primitives/kernels/v1/cortex_plugin_abi.c primitives/kernels/v1/cortex_plugin.h
	@echo "Building kernel ABI object..."
	$(CC) -c -fPIC $(CORTEX_PRIMITIVE_INCLUDES) -o $@ $<

# Build adapter ABI object (compiled once, linked by all adapters)
$(ADAPTER_ABI_OBJ): primitives/adapters/v1/cortex_adapter_abi.c primitives/adapters/v1/cortex_adapter.h
	@echo "Building adapter ABI object..."
	$(CC) -c -fPIC $(CORTEX_PRIMITIVE_INCLUDES) -o $@ $<

# Build plugins (kernels from registry) - depends on params and ABI object
plugins: params $(KERNEL_ABI_OBJ)
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

# Build and run tests
tests:
	@echo "Building and running tests..."
	$(MAKE) -C tests
	$(MAKE) -C tests test

# Clean everything
clean:
	@echo "Cleaning all build artifacts..."
	$(MAKE) -C src/engine/harness clean
	$(MAKE) -C src/engine/params clean
	@for version_dir in primitives/kernels/v*/; do \
		if [ -d "$$version_dir" ]; then \
			for dir in $$version_dir*@*/; do \
				if [ -f "$$dir/Makefile" ]; then \
					$(MAKE) -C "$$dir" clean || true; \
				fi \
			done \
		fi \
	done
	$(MAKE) -C tests clean
	@rm -f $(KERNEL_ABI_OBJ)
	@rm -f $(ADAPTER_ABI_OBJ)

# Development workflow
dev: clean all
	@echo "Full development build complete!"

# Show help
help:
	@echo "CORTEX Build System"
	@echo ""
	@echo "Available targets:"
	@echo "  all      - Build params, harness, plugins, and run tests (default)"
	@echo "  params   - Build parameter accessor library"
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
