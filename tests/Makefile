# Makefile for CORTEX C tests

CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11 -I../include
LDFLAGS = -lpthread -lm

# Source files
REPLAYER_SRC = ../src/replayer/replayer.c
SCHEDULER_SRC = ../src/scheduler/scheduler.c
TELEMETRY_SRC = ../src/harness/telemetry/telemetry.c
UTIL_SRC = ../src/harness/util/util.c
LOADER_SRC = ../src/harness/loader/loader.c

# Test binaries
TEST_REPLAYER = test_replayer
TEST_SCHEDULER = test_scheduler
TEST_KERNEL_REGISTRY = test_kernel_registry
TEST_KERNEL_ACCURACY = test_kernel_accuracy
TEST_CLOCK_RESOLUTION = test_clock_resolution

.PHONY: all clean test test-replayer test-scheduler test-kernel-registry test-kernel-accuracy test-clock-resolution

all: $(TEST_REPLAYER) $(TEST_SCHEDULER) $(TEST_KERNEL_REGISTRY) $(TEST_KERNEL_ACCURACY) $(TEST_CLOCK_RESOLUTION)

$(TEST_REPLAYER): test_replayer.c $(REPLAYER_SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

$(TEST_SCHEDULER): test_scheduler.c $(SCHEDULER_SRC) $(TELEMETRY_SRC) $(UTIL_SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

$(TEST_KERNEL_REGISTRY): test_kernel_registry.c
	$(CC) $(CFLAGS) -o $@ $^

$(TEST_KERNEL_ACCURACY): test_kernel_accuracy.c $(LOADER_SRC)
	$(CC) $(CFLAGS) -I../src -I../src/scheduler -I../src/replayer -I../src/harness/telemetry -I../src/harness/config -I../src/harness/util -o $@ $^ $(LDFLAGS) -ldl -lm

$(TEST_CLOCK_RESOLUTION): test_clock_resolution.c
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

test: test-replayer test-scheduler test-kernel-registry

test-clock-resolution: $(TEST_CLOCK_RESOLUTION)
	@echo "Running clock resolution tests..."
	@./$(TEST_CLOCK_RESOLUTION)

test-replayer: $(TEST_REPLAYER)
	@echo "Running replayer tests..."
	@./$(TEST_REPLAYER)

test-scheduler: $(TEST_SCHEDULER)
	@echo "Running scheduler tests..."
	@./$(TEST_SCHEDULER)

test-kernel-registry: $(TEST_KERNEL_REGISTRY)
	@echo "Running kernel registry tests..."
	@cd .. && ./tests/$(TEST_KERNEL_REGISTRY)

test-kernel-accuracy: $(TEST_KERNEL_ACCURACY)
	@echo "Running kernel accuracy tests..."
	@./$(TEST_KERNEL_ACCURACY) --kernel notch_iir --windows 5 --verbose

clean:
	rm -f $(TEST_REPLAYER) $(TEST_SCHEDULER) $(TEST_KERNEL_REGISTRY) $(TEST_KERNEL_ACCURACY) $(TEST_CLOCK_RESOLUTION)
	rm -f /tmp/cortex_test_*.dat /tmp/test_output.bin /tmp/test_input_*

help:
	@echo "Available targets:"
	@echo "  all                - Build all tests (default)"
	@echo "  test               - Run all tests"
	@echo "  test-replayer      - Run replayer tests only"
	@echo "  test-scheduler     - Run scheduler tests only"
	@echo "  test-kernel-registry - Run kernel registry tests only"
	@echo "  test-kernel-accuracy - Run kernel accuracy tests only"
	@echo "  test-clock-resolution - Run clock resolution and timing accuracy tests"
	@echo "  clean              - Remove test binaries and temp files"
	@echo "  help               - Show this help message"
