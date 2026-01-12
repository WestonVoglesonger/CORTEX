# CORTEX Testing System - Auto-Discovery Makefile
#
# Directory Structure:
#   c/unit/core/      - Core engine tests (scheduler, telemetry, replayer)
#   c/unit/protocol/  - Protocol and transport tests
#   c/integration/    - Integration tests (adapter, end-to-end)
#   c/mock_adapter/   - Controllable test adapter
#   c/common/         - Shared test utilities (test_common.h)

CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11
INCLUDES = -I../sdk/kernel/include -I../sdk/adapter/include -I../src/engine/scheduler -I../src/engine/replayer -I../src/engine/harness/device -I../src/engine/harness/util -I../src/engine/harness/config -I../src/engine/telemetry -Ic/common

# Platform-specific linker flags
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LDFLAGS = -L../sdk/kernel/lib -lcortex -lpthread -lm
else
    LDFLAGS = -L../sdk/kernel/lib -lcortex -ldl -lpthread -lm
endif

# ========================================================================
# Source Files
# ========================================================================

# Engine source files
REPLAYER_SRC = ../src/engine/replayer/replayer.c
SCHEDULER_SRC = ../src/engine/scheduler/scheduler.c
TELEMETRY_SRC = ../src/engine/telemetry/telemetry.c
UTIL_SRC = ../src/engine/harness/util/util.c
SIGNAL_HANDLER_SRC = ../src/engine/harness/util/signal_handler.c
DEVICE_COMM_SRC = ../src/engine/harness/device/device_comm.c
CONFIG_SRC = ../src/engine/harness/config/config.c

# Adapter SDK source files
PROTOCOL_SRC = ../sdk/adapter/lib/protocol/protocol.c \
               ../sdk/adapter/lib/protocol/crc32.c
TRANSPORT_SRC = ../sdk/adapter/lib/transport/local/mock.c \
                ../sdk/adapter/lib/transport/serial/uart_posix.c \
                ../sdk/adapter/lib/transport/network/tcp_common.c \
                ../sdk/adapter/lib/transport/network/tcp_client.c \
                ../sdk/adapter/lib/transport/network/tcp_server.c
ADAPTER_HELPERS_SRC = ../sdk/adapter/lib/adapter_helpers/transport_helpers.c \
                      ../sdk/adapter/lib/adapter_helpers/protocol_helpers.c \
                      ../sdk/adapter/lib/adapter_helpers/system_info.c

# ========================================================================
# Test Discovery
# ========================================================================

# Auto-discover test files in each directory
CORE_TESTS_SRC := $(wildcard c/unit/core/test_*.c)
PROTOCOL_TESTS_SRC := $(wildcard c/unit/protocol/test_*.c)
INTEGRATION_TESTS_SRC := $(wildcard c/integration/test_*.c)

# Generate binary names (strip .c extension and directory prefix)
CORE_TESTS := $(patsubst c/unit/core/%.c,%,$(CORE_TESTS_SRC))
PROTOCOL_TESTS := $(patsubst c/unit/protocol/%.c,%,$(PROTOCOL_TESTS_SRC))
INTEGRATION_TESTS := $(patsubst c/integration/%.c,%,$(INTEGRATION_TESTS_SRC))

# All test binaries
ALL_TESTS := $(CORE_TESTS) $(PROTOCOL_TESTS) $(INTEGRATION_TESTS)

# ========================================================================
# Build Rules
# ========================================================================

.PHONY: all tests clean help mock-adapter
.PHONY: test-core test-protocol test-integration
.PHONY: $(patsubst %,run-%,$(ALL_TESTS))

# Default: build all tests and mock adapter
all: $(ALL_TESTS) mock-adapter

# Run all tests
tests: test-core test-protocol test-integration

# ========================================================================
# Core Unit Tests
# ========================================================================

test_replayer: c/unit/core/test_replayer.c $(REPLAYER_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_scheduler: c/unit/core/test_scheduler.c $(SCHEDULER_SRC) $(TELEMETRY_SRC) $(UTIL_SRC) $(DEVICE_COMM_SRC) $(PROTOCOL_SRC) $(TRANSPORT_SRC) $(ADAPTER_HELPERS_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_telemetry: c/unit/core/test_telemetry.c $(TELEMETRY_SRC) $(UTIL_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_kernel_registry: c/unit/core/test_kernel_registry.c
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_clock_resolution: c/unit/core/test_clock_resolution.c
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_signal_handler: c/unit/core/test_signal_handler.c $(SIGNAL_HANDLER_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_param_accessor: c/unit/core/test_param_accessor.c
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

# ========================================================================
# Protocol Unit Tests
# ========================================================================

test_protocol: c/unit/protocol/test_protocol.c $(PROTOCOL_SRC) ../sdk/adapter/lib/transport/local/mock.c
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lpthread

test_protocol_loopback: c/unit/protocol/test_protocol_loopback.c $(PROTOCOL_SRC) $(TRANSPORT_SRC) $(ADAPTER_HELPERS_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lpthread

# ========================================================================
# Integration Tests
# ========================================================================

test_adapter_smoke: c/integration/test_adapter_smoke.c $(DEVICE_COMM_SRC) $(PROTOCOL_SRC) $(TRANSPORT_SRC) $(ADAPTER_HELPERS_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lpthread

test_adapter_all_kernels: c/integration/test_adapter_all_kernels.c $(DEVICE_COMM_SRC) $(PROTOCOL_SRC) $(TRANSPORT_SRC) $(ADAPTER_HELPERS_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lpthread

test_socketpair_hello: c/integration/test_socketpair_hello.c $(PROTOCOL_SRC) $(TRANSPORT_SRC) $(ADAPTER_HELPERS_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ -lpthread

test_config_overrides: c/integration/test_config_overrides.c $(CONFIG_SRC) $(UTIL_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

# ========================================================================
# Mock Adapter
# ========================================================================

mock-adapter:
	@echo "Building mock adapter..."
	@$(MAKE) -C c/mock_adapter

# ========================================================================
# Test Runners
# ========================================================================

test-core: $(CORE_TESTS)
	@echo "========================================="
	@echo "Running Core Unit Tests"
	@echo "========================================="
	@for test in $(CORE_TESTS); do \
		if [ "$$test" = "test_scheduler" ]; then \
			echo "SKIP: $$test (needs device_comm rewrite)"; \
		elif [ "$$test" = "test_kernel_registry" ]; then \
			echo "Running $$test..."; \
			( cd .. && ./tests/$$test ) || exit 1; \
		else \
			echo "Running $$test..."; \
			./$$test || exit 1; \
		fi; \
	done
	@echo "Core tests: PASS"

test-protocol: $(PROTOCOL_TESTS)
	@echo "========================================="
	@echo "Running Protocol Unit Tests"
	@echo "========================================="
	@for test in $(PROTOCOL_TESTS); do \
		echo "Running $$test..."; \
		./$$test || exit 1; \
	done
	@echo "Protocol tests: PASS"

test-integration: $(INTEGRATION_TESTS)
	@echo "========================================="
	@echo "Running Integration Tests"
	@echo "========================================="
	@for test in $(INTEGRATION_TESTS); do \
		echo "Running $$test..."; \
		( cd .. && ./tests/$$test ) || exit 1; \
	done
	@echo "Integration tests: PASS"

# Individual test runners (run-test_name)
$(patsubst %,run-%,$(CORE_TESTS)): run-%: %
	@echo "Running $<..."
	@./$<

$(patsubst %,run-%,$(PROTOCOL_TESTS)): run-%: %
	@echo "Running $<..."
	@./$<

$(patsubst %,run-%,$(INTEGRATION_TESTS)): run-%: %
	@echo "Running $<..."
	@cd .. && ./tests/$<

# ========================================================================
# Utilities
# ========================================================================

clean:
	rm -f $(ALL_TESTS)
	rm -f /tmp/cortex_test_*.dat /tmp/test_output.bin /tmp/test_input_* /tmp/cortex_test_telemetry.*
	$(MAKE) -C c/mock_adapter clean

help:
	@echo "CORTEX Testing System"
	@echo ""
	@echo "Build Targets:"
	@echo "  all                - Build all tests and mock adapter"
	@echo "  mock-adapter       - Build controllable test adapter"
	@echo ""
	@echo "Test Suites:"
	@echo "  tests              - Run all test suites"
	@echo "  test-core          - Run core unit tests (scheduler, telemetry, replayer)"
	@echo "  test-protocol      - Run protocol unit tests"
	@echo "  test-integration   - Run integration tests"
	@echo ""
	@echo "Individual Tests:"
	@for test in $(CORE_TESTS); do \
		echo "  run-$$test"; \
	done
	@for test in $(PROTOCOL_TESTS); do \
		echo "  run-$$test"; \
	done
	@for test in $(INTEGRATION_TESTS); do \
		echo "  run-$$test"; \
	done
	@echo ""
	@echo "Utilities:"
	@echo "  clean              - Remove test binaries and temp files"
	@echo "  help               - Show this message"
	@echo ""
	@echo "Directory Structure:"
	@echo "  c/unit/core/       - $(words $(CORE_TESTS)) tests"
	@echo "  c/unit/protocol/   - $(words $(PROTOCOL_TESTS)) tests"
	@echo "  c/integration/     - $(words $(INTEGRATION_TESTS)) tests"
