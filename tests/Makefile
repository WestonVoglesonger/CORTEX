# Makefile for CORTEX C tests

CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11 -I../include
LDFLAGS = -pthread -lm

# Source files
REPLAYER_SRC = ../src/replayer/replayer.c
SCHEDULER_SRC = ../src/scheduler/scheduler.c
TELEMETRY_SRC = ../src/harness/telemetry/telemetry.c
UTIL_SRC = ../src/harness/util/util.c

# Test binaries
TEST_REPLAYER = test_replayer
TEST_SCHEDULER = test_scheduler
TEST_KERNEL_REGISTRY = test_kernel_registry

.PHONY: all clean test test-replayer test-scheduler test-kernel-registry

all: $(TEST_REPLAYER) $(TEST_SCHEDULER) $(TEST_KERNEL_REGISTRY)

$(TEST_REPLAYER): test_replayer.c $(REPLAYER_SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

$(TEST_SCHEDULER): test_scheduler.c $(SCHEDULER_SRC) $(TELEMETRY_SRC) $(UTIL_SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

$(TEST_KERNEL_REGISTRY): test_kernel_registry.c
	$(CC) $(CFLAGS) -o $@ $^

test: test-replayer test-scheduler test-kernel-registry

test-replayer: $(TEST_REPLAYER)
	@echo "Running replayer tests..."
	@./$(TEST_REPLAYER)

test-scheduler: $(TEST_SCHEDULER)
	@echo "Running scheduler tests..."
	@./$(TEST_SCHEDULER)

test-kernel-registry: $(TEST_KERNEL_REGISTRY)
	@echo "Running kernel registry tests..."
	@cd .. && ./tests/$(TEST_KERNEL_REGISTRY)

clean:
	rm -f $(TEST_REPLAYER) $(TEST_SCHEDULER) $(TEST_KERNEL_REGISTRY)
	rm -f /tmp/cortex_test_*.dat

help:
	@echo "Available targets:"
	@echo "  all                - Build all tests (default)"
	@echo "  test               - Run all tests"
	@echo "  test-replayer      - Run replayer tests only"
	@echo "  test-scheduler     - Run scheduler tests only"
	@echo "  test-kernel-registry - Run kernel registry tests only"
	@echo "  clean              - Remove test binaries and temp files"
	@echo "  help               - Show this help message"
