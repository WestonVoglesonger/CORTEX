# Makefile for CORTEX C tests

CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11 -I../sdk/kernel/include

# Platform-specific linker flags
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LDFLAGS = -L../sdk/kernel/lib -lcortex -lpthread -lm
else
    LDFLAGS = -L../sdk/kernel/lib -lcortex -ldl -lpthread -lm
endif

# Source files
REPLAYER_SRC = ../src/engine/replayer/replayer.c
SCHEDULER_SRC = ../src/engine/scheduler/scheduler.c
TELEMETRY_SRC = ../src/engine/telemetry/telemetry.c
UTIL_SRC = ../src/engine/harness/util/util.c
SIGNAL_HANDLER_SRC = ../src/engine/harness/util/signal_handler.c

# Test binaries
TEST_REPLAYER = test_replayer
TEST_SCHEDULER = test_scheduler
TEST_TELEMETRY = test_telemetry
TEST_KERNEL_REGISTRY = test_kernel_registry
TEST_CLOCK_RESOLUTION = test_clock_resolution
TEST_SIGNAL_HANDLER = test_signal_handler
TEST_PARAM_ACCESSOR = test_param_accessor

.PHONY: all clean test test-replayer test-scheduler test-telemetry test-kernel-registry test-clock-resolution test-signal-handler test-param-accessor

all: $(TEST_REPLAYER) $(TEST_SCHEDULER) $(TEST_TELEMETRY) $(TEST_KERNEL_REGISTRY) $(TEST_CLOCK_RESOLUTION) $(TEST_SIGNAL_HANDLER) $(TEST_PARAM_ACCESSOR)

$(TEST_REPLAYER): test_replayer.c $(REPLAYER_SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

$(TEST_SCHEDULER): test_scheduler.c $(SCHEDULER_SRC) $(TELEMETRY_SRC) $(UTIL_SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

$(TEST_TELEMETRY): test_telemetry.c $(TELEMETRY_SRC) $(UTIL_SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

$(TEST_KERNEL_REGISTRY): test_kernel_registry.c
	$(CC) $(CFLAGS) -o $@ $^

$(TEST_CLOCK_RESOLUTION): test_clock_resolution.c
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

$(TEST_SIGNAL_HANDLER): test_signal_handler.c $(SIGNAL_HANDLER_SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

$(TEST_PARAM_ACCESSOR): test_param_accessor.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

test: test-replayer test-scheduler test-telemetry test-kernel-registry test-signal-handler test-param-accessor

test-clock-resolution: $(TEST_CLOCK_RESOLUTION)
	@echo "Running clock resolution tests..."
	@./$(TEST_CLOCK_RESOLUTION)

test-replayer: $(TEST_REPLAYER)
	@echo "Running replayer tests..."
	@./$(TEST_REPLAYER)

test-scheduler: $(TEST_SCHEDULER)
	@echo "Running scheduler tests..."
	@./$(TEST_SCHEDULER)

test-telemetry: $(TEST_TELEMETRY)
	@echo "Running telemetry tests..."
	@./$(TEST_TELEMETRY)

test-kernel-registry: $(TEST_KERNEL_REGISTRY)
	@echo "Running kernel registry tests..."
	@cd .. && ./tests/$(TEST_KERNEL_REGISTRY)

test-signal-handler: $(TEST_SIGNAL_HANDLER)
	@echo "Running signal handler tests..."
	@./$(TEST_SIGNAL_HANDLER)

test-param-accessor: $(TEST_PARAM_ACCESSOR)
	@echo "Running parameter accessor tests..."
	@./$(TEST_PARAM_ACCESSOR)

clean:
	rm -f $(TEST_REPLAYER) $(TEST_SCHEDULER) $(TEST_TELEMETRY) $(TEST_KERNEL_REGISTRY) $(TEST_CLOCK_RESOLUTION) $(TEST_SIGNAL_HANDLER) $(TEST_PARAM_ACCESSOR)
	rm -f /tmp/cortex_test_*.dat /tmp/test_output.bin /tmp/test_input_* /tmp/cortex_test_telemetry.*

help:
	@echo "Available targets:"
	@echo "  all                  - Build all tests (default)"
	@echo "  test                 - Run all tests"
	@echo "  test-replayer        - Run replayer tests only"
	@echo "  test-scheduler       - Run scheduler tests only"
	@echo "  test-telemetry       - Run telemetry tests only"
	@echo "  test-kernel-registry - Run kernel registry tests only"
	@echo "  test-clock-resolution - Run clock resolution and timing accuracy tests"
	@echo "  test-signal-handler  - Run signal handler tests only"
	@echo "  test-param-accessor  - Run parameter accessor tests only"
	@echo "  clean                - Remove test binaries and temp files"
	@echo "  help                 - Show this help message"
