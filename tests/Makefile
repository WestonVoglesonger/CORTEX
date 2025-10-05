# Makefile for CORTEX C tests

CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11 -I../include
LDFLAGS = -pthread -lm

# Source files
REPLAYER_SRC = ../src/replayer/replayer.c
SCHEDULER_SRC = ../src/scheduler/scheduler.c

# Test binaries
TEST_REPLAYER = test_replayer
TEST_SCHEDULER = test_scheduler

.PHONY: all clean test test-replayer test-scheduler

all: $(TEST_REPLAYER) $(TEST_SCHEDULER)

$(TEST_REPLAYER): test_replayer.c $(REPLAYER_SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

$(TEST_SCHEDULER): test_scheduler.c $(SCHEDULER_SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

test: test-replayer test-scheduler

test-replayer: $(TEST_REPLAYER)
	@echo "Running replayer tests..."
	@./$(TEST_REPLAYER)

test-scheduler: $(TEST_SCHEDULER)
	@echo "Running scheduler tests..."
	@./$(TEST_SCHEDULER)

clean:
	rm -f $(TEST_REPLAYER) $(TEST_SCHEDULER)
	rm -f /tmp/cortex_test_*.dat

help:
	@echo "Available targets:"
	@echo "  all           - Build all tests (default)"
	@echo "  test          - Run all tests"
	@echo "  test-replayer - Run replayer tests only"
	@echo "  clean         - Remove test binaries and temp files"
	@echo "  help          - Show this help message"
