CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11
INCLUDES = -I../../sdk/adapter/include \
           -I../../sdk/kernel/include \
           -I../../src/engine/harness/device \
           -I../fixtures/common

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LDFLAGS = -lpthread -lm
else
    LDFLAGS = -ldl -lpthread -lm
endif

UNIT_TESTS := $(patsubst unit/%.c,build/%,$(wildcard unit/test_*.c))
INTEGRATION_TESTS := $(patsubst integration/%.c,build/%,$(wildcard integration/test_*.c))
ALL_TESTS := $(UNIT_TESTS) $(INTEGRATION_TESTS)

PROTOCOL_SRC = ../../sdk/adapter/lib/protocol/protocol.c ../../sdk/adapter/lib/protocol/crc32.c
TRANSPORT_SRC = ../../sdk/adapter/lib/transport/local/mock.c \
                ../../sdk/adapter/lib/transport/serial/uart_posix.c \
                ../../sdk/adapter/lib/transport/network/tcp_common.c \
                ../../sdk/adapter/lib/transport/network/tcp_client.c \
                ../../sdk/adapter/lib/transport/network/tcp_server.c
ADAPTER_HELPERS_SRC = ../../sdk/adapter/lib/adapter_helpers/transport_helpers.c \
                      ../../sdk/adapter/lib/adapter_helpers/protocol_helpers.c \
                      ../../sdk/adapter/lib/adapter_helpers/system_info.c
DEVICE_COMM_SRC = ../../src/engine/harness/device/device_comm.c

.PHONY: all tests clean

all: build $(ALL_TESTS)

build:
	mkdir -p build

tests: $(ALL_TESTS)
	@echo "========================================="
	@echo "Running Adapter Tests"
	@echo "========================================="
	@for test in $(ALL_TESTS); do \
		case "$$test" in \
			build/test_adapter_*|build/test_socketpair_*) \
				echo "SKIP: $$test (requires native adapter binary)";; \
			*) \
				echo "Running $$test..."; \
				./$$test || exit 1;; \
		esac; \
	done
	@echo "Adapter tests: PASS"

build/test_protocol: unit/test_protocol.c $(PROTOCOL_SRC) ../../sdk/adapter/lib/transport/local/mock.c
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

build/test_protocol_loopback: unit/test_protocol_loopback.c $(PROTOCOL_SRC) $(TRANSPORT_SRC) $(ADAPTER_HELPERS_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

build/test_adapter_smoke: integration/test_adapter_smoke.c $(DEVICE_COMM_SRC) $(PROTOCOL_SRC) $(TRANSPORT_SRC) $(ADAPTER_HELPERS_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

build/test_adapter_all_kernels: integration/test_adapter_all_kernels.c $(DEVICE_COMM_SRC) $(PROTOCOL_SRC) $(TRANSPORT_SRC) $(ADAPTER_HELPERS_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

build/test_socketpair_hello: integration/test_socketpair_hello.c $(PROTOCOL_SRC) $(TRANSPORT_SRC) $(ADAPTER_HELPERS_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

clean:
	rm -rf build/
