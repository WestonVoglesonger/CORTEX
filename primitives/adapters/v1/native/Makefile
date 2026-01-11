# native adapter Makefile

CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11
INCLUDES = -I../../../../sdk/adapter/include -I../../../../sdk/kernel/include
LDFLAGS = -L../../../../sdk/adapter/lib/transport -L../../../../sdk/adapter/lib/protocol
LIBS = -ldl -lpthread

TARGET = cortex_adapter_native

SRCS = adapter.c
OBJS = $(SRCS:.c=.o)

# SDK object files (not yet built as libraries)
PROTOCOL_OBJS = ../../../../sdk/adapter/lib/protocol/protocol.o \
                ../../../../sdk/adapter/lib/protocol/crc32.o
TRANSPORT_OBJS = ../../../../sdk/adapter/lib/transport/local/mock.o \
                 ../../../../sdk/adapter/lib/transport/serial/uart_posix.o \
                 ../../../../sdk/adapter/lib/transport/network/tcp_common.o \
                 ../../../../sdk/adapter/lib/transport/network/tcp_client.o \
                 ../../../../sdk/adapter/lib/transport/network/tcp_server.o
ADAPTER_HELPERS_OBJS = ../../../../sdk/adapter/lib/adapter_helpers/protocol_helpers.o \
                       ../../../../sdk/adapter/lib/adapter_helpers/transport_helpers.o \
                       ../../../../sdk/adapter/lib/adapter_helpers/system_info.o

all: $(TARGET)

$(TARGET): $(OBJS) $(PROTOCOL_OBJS) $(TRANSPORT_OBJS) $(ADAPTER_HELPERS_OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(PROTOCOL_OBJS) $(TRANSPORT_OBJS) $(ADAPTER_HELPERS_OBJS) $(LIBS)

%.o: %.c
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# Ensure SDK objects are built
$(PROTOCOL_OBJS):
	$(MAKE) -C ../../../../sdk/adapter/lib/protocol

$(TRANSPORT_OBJS):
	$(MAKE) -C ../../../../sdk/adapter/lib/transport

$(ADAPTER_HELPERS_OBJS):
	$(MAKE) -C ../../../../sdk/adapter/lib/adapter_helpers

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
