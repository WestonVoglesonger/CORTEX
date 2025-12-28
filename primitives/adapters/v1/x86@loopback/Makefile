# x86@loopback adapter Makefile

CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11
INCLUDES = -I../../../../sdk/adapter/include
LDFLAGS = -L../../../../sdk/adapter/lib/transport -L../../../../sdk/adapter/lib/protocol
LIBS = -ldl -lpthread

TARGET = cortex_adapter_x86_loopback

SRCS = adapter.c
OBJS = $(SRCS:.c=.o)

# Protocol and transport object files (not yet built as libraries)
PROTOCOL_OBJS = ../../../../sdk/adapter/lib/protocol/protocol.o \
                ../../../../sdk/adapter/lib/protocol/crc32.o
TRANSPORT_OBJS = ../../../../sdk/adapter/lib/transport/mock.o

all: $(TARGET)

$(TARGET): $(OBJS) $(PROTOCOL_OBJS) $(TRANSPORT_OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(PROTOCOL_OBJS) $(TRANSPORT_OBJS) $(LIBS)

%.o: %.c
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# Ensure protocol and transport objects are built
$(PROTOCOL_OBJS):
	$(MAKE) -C ../../../../sdk/adapter/lib/protocol

$(TRANSPORT_OBJS):
	$(MAKE) -C ../../../../sdk/adapter/lib/transport

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
