CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11 -DBUILD_STANDALONE
INCLUDES = -I../../sdk/kernel/include

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LDFLAGS = -lm
else
    LDFLAGS = -ldl -lm
endif

EXAMPLE_TESTS := $(patsubst examples/%.c,build/%,$(wildcard examples/*.c))
ALL_TESTS := $(EXAMPLE_TESTS)

.PHONY: all tests clean

all: build $(ALL_TESTS)

build:
	mkdir -p build

tests: $(ALL_TESTS)
	@echo "========================================="
	@echo "Running Kernel SDK Examples"
	@echo "========================================="
	@for test in $(ALL_TESTS); do \
		echo "Running $$test..."; \
		./$$test || exit 1; \
	done
	@echo "Kernel SDK examples: PASS"

build/hello_kernel: examples/hello_kernel.c
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

clean:
	rm -rf build/
