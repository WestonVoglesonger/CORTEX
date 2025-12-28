CC = gcc
CFLAGS = -Wall -Wextra -g -O2 -std=c11 -I../../../sdk/kernel/include -I../scheduler -I../replayer -Iapp -Iconfig -I../telemetry -Iutil -Ireport

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

SOURCES = $(APP_SOURCES) $(CFG_SOURCES) $(TEL_SOURCES) $(UTL_SOURCES) $(RPT_SOURCES)
OBJECTS = $(SOURCES:.c=.o)

all: cortex

cortex: $(OBJECTS) ../scheduler/scheduler.o ../replayer/replayer.o
	$(CC) $(OBJECTS) ../scheduler/scheduler.o ../replayer/replayer.o -o cortex $(LDFLAGS)

clean:
	rm -f $(OBJECTS) cortex

.PHONY: all clean




