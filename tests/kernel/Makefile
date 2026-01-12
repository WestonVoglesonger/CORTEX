CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11 -DBUILD_STANDALONE
INCLUDES = -I../../sdk/kernel/include -I../fixtures/common

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LDFLAGS = -lm
else
    LDFLAGS = -ldl -lm
endif

UNIT_TESTS := $(patsubst unit/%.c,build/%,$(wildcard unit/test_*.c))
EXAMPLE_TESTS := $(patsubst examples/%.c,build/%,$(wildcard examples/*.c))
ALL_TESTS := $(UNIT_TESTS) $(EXAMPLE_TESTS)

STATE_IO_SRC = ../../sdk/kernel/lib/state_io/state_io.c

.PHONY: all tests clean

all: build $(ALL_TESTS)

build:
	mkdir -p build

tests: $(ALL_TESTS)
	@echo "========================================="
	@echo "Running Kernel SDK Tests"
	@echo "========================================="
	@for test in $(ALL_TESTS); do \
		echo "Running $$test..."; \
		./$$test || exit 1; \
	done
	@echo "Kernel SDK tests: PASS"

build/test_state_io: unit/test_state_io.c $(STATE_IO_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

build/hello_kernel: examples/hello_kernel.c
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

clean:
	rm -rf build/
