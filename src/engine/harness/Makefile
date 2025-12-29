CC = gcc
CFLAGS = -Wall -Wextra -g -O2 -std=c11 -I../../../sdk/kernel/include -I../../../sdk/adapter/include -I../scheduler -I../replayer -Iapp -Iconfig -I../telemetry -Iutil -Ireport -Idevice

# Platform-specific linker flags
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    # macOS: dlopen is in libSystem, no -ldl needed
    LDFLAGS = -L../../../sdk/kernel/lib -lcortex -lpthread -lm
else
    # Linux: requires explicit -ldl for dlopen/dlsym
    LDFLAGS = -L../../../sdk/kernel/lib -lcortex -ldl -lpthread -lm
endif

APP_SOURCES = app/main.c
CFG_SOURCES = config/config.c
TEL_SOURCES = ../telemetry/telemetry.c
UTL_SOURCES = util/util.c util/signal_handler.c
RPT_SOURCES = report/report.c
DEV_SOURCES = device/device_comm.c

SOURCES = $(APP_SOURCES) $(CFG_SOURCES) $(TEL_SOURCES) $(UTL_SOURCES) $(RPT_SOURCES) $(DEV_SOURCES)
OBJECTS = $(SOURCES:.c=.o)

# Adapter SDK libraries (protocol, transport, etc.)
ADAPTER_LIBS = ../../../sdk/adapter/lib/protocol/protocol.o \
               ../../../sdk/adapter/lib/protocol/crc32.o \
               ../../../sdk/adapter/lib/transport/local/mock.o

all: cortex

cortex: $(OBJECTS) ../scheduler/scheduler.o ../replayer/replayer.o $(ADAPTER_LIBS)
	$(CC) $(OBJECTS) ../scheduler/scheduler.o ../replayer/replayer.o $(ADAPTER_LIBS) -o cortex $(LDFLAGS)

clean:
	rm -f $(OBJECTS) cortex

.PHONY: all clean




