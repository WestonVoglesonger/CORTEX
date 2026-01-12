# Mock Adapter Makefile
# Builds controllable adapter for testing scheduler, device_comm, error handling

CC = gcc
CFLAGS = -Wall -Wextra -O0 -g -std=c11
INCLUDES = -I../../../sdk/adapter/include -I../../../sdk/kernel/include
LDFLAGS = -L../../../sdk/adapter/lib/transport -L../../../sdk/adapter/lib/protocol
LIBS = -lpthread -lm

TARGET = mock_adapter

SRCS = mock_adapter.c
OBJS = $(SRCS:.c=.o)

# SDK object files
PROTOCOL_OBJS = ../../../sdk/adapter/lib/protocol/protocol.o \
                ../../../sdk/adapter/lib/protocol/crc32.o
TRANSPORT_OBJS = ../../../sdk/adapter/lib/transport/local/mock.o \
                 ../../../sdk/adapter/lib/transport/network/tcp_server.o \
                 ../../../sdk/adapter/lib/transport/network/tcp_common.o \
                 ../../../sdk/adapter/lib/transport/serial/uart_posix.o
ADAPTER_HELPERS_OBJS = ../../../sdk/adapter/lib/adapter_helpers/protocol_helpers.o \
                       ../../../sdk/adapter/lib/adapter_helpers/system_info.o \
                       ../../../sdk/adapter/lib/adapter_helpers/transport_helpers.o

all: $(TARGET)

$(TARGET): $(OBJS) build-sdk-deps
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(PROTOCOL_OBJS) $(TRANSPORT_OBJS) $(ADAPTER_HELPERS_OBJS) $(LIBS)

%.o: %.c
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# Ensure SDK objects are built (always run make in SDK directories)
.PHONY: build-sdk-deps
build-sdk-deps:
	$(MAKE) -C ../../../sdk/adapter/lib/protocol
	$(MAKE) -C ../../../sdk/adapter/lib/transport
	$(MAKE) -C ../../../sdk/adapter/lib/adapter_helpers

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
