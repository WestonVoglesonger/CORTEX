CC = gcc
CFLAGS = -Wall -Wextra -g -O0 -std=c11
INCLUDES = -I../../src/engine/scheduler \
           -I../../src/engine/replayer \
           -I../../src/engine/telemetry \
           -I../../src/engine/harness/util \
           -I../../src/engine/harness/config \
           -I../../src/engine/harness/device \
           -I../../sdk/kernel/include \
           -I../../sdk/adapter/include \
           -I../fixtures/common

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LDFLAGS = -L../../sdk/kernel/lib -lcortex -lpthread -lm
else
    LDFLAGS = -L../../sdk/kernel/lib -lcortex -ldl -lpthread -lm
endif

UNIT_TESTS := $(patsubst unit/%.c,%,$(wildcard unit/test_*.c))
INTEGRATION_TESTS := $(patsubst integration/%.c,%,$(wildcard integration/test_*.c))
ALL_TESTS := $(UNIT_TESTS) $(INTEGRATION_TESTS)

REPLAYER_SRC = ../../src/engine/replayer/replayer.c
SCHEDULER_SRC = ../../src/engine/scheduler/scheduler.c
TELEMETRY_SRC = ../../src/engine/telemetry/telemetry.c
UTIL_SRC = ../../src/engine/harness/util/util.c
SIGNAL_HANDLER_SRC = ../../src/engine/harness/util/signal_handler.c
CONFIG_SRC = ../../src/engine/harness/config/config.c
DEVICE_COMM_SRC = ../../src/engine/harness/device/device_comm.c
PROTOCOL_SRC = ../../sdk/adapter/lib/protocol/protocol.c ../../sdk/adapter/lib/protocol/crc32.c
TRANSPORT_SRC = ../../sdk/adapter/lib/transport/local/mock.c \
                ../../sdk/adapter/lib/transport/serial/uart_posix.c \
                ../../sdk/adapter/lib/transport/network/tcp_common.c \
                ../../sdk/adapter/lib/transport/network/tcp_client.c \
                ../../sdk/adapter/lib/transport/network/tcp_server.c
ADAPTER_HELPERS_SRC = ../../sdk/adapter/lib/adapter_helpers/transport_helpers.c \
                      ../../sdk/adapter/lib/adapter_helpers/protocol_helpers.c \
                      ../../sdk/adapter/lib/adapter_helpers/system_info.c

.PHONY: all tests clean

all: $(ALL_TESTS)

tests: $(ALL_TESTS)
	@echo "========================================="
	@echo "Running Engine Tests"
	@echo "========================================="
	@for test in $(ALL_TESTS); do \
		if [ "$$test" = "test_scheduler" ]; then \
			echo "SKIP: $$test (needs device_comm rewrite)"; \
		elif [ "$$test" = "test_kernel_registry" ]; then \
			echo "Running $$test..."; \
			( cd ../.. && ./tests/engine/$$test ) || exit 1; \
		else \
			echo "Running $$test..."; \
			./$$test || exit 1; \
		fi; \
	done
	@echo "Engine tests: PASS"

test_replayer: unit/test_replayer.c $(REPLAYER_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_scheduler: unit/test_scheduler.c $(SCHEDULER_SRC) $(TELEMETRY_SRC) $(UTIL_SRC) $(DEVICE_COMM_SRC) $(PROTOCOL_SRC) $(TRANSPORT_SRC) $(ADAPTER_HELPERS_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_telemetry: unit/test_telemetry.c $(TELEMETRY_SRC) $(UTIL_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_signal_handler: unit/test_signal_handler.c $(SIGNAL_HANDLER_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_clock_resolution: unit/test_clock_resolution.c
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_kernel_registry: unit/test_kernel_registry.c
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

test_config_overrides: integration/test_config_overrides.c $(CONFIG_SRC) $(UTIL_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^ $(LDFLAGS)

clean:
	rm -f $(ALL_TESTS)
