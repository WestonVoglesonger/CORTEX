CC = gcc
CFLAGS = -Wall -Wextra -g -O2 -std=c11 -I../include -I../scheduler -I../replayer -Iapp -Iconfig -Iloader -I../telemetry -Iutil -Ireport

# Platform-specific linker flags
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    # macOS: dlopen is in libSystem, no -ldl needed
    LDFLAGS = -lpthread -lm
else
    # Linux: requires explicit -ldl for dlopen/dlsym
    LDFLAGS = -ldl -lpthread -lm
endif

APP_SOURCES = app/main.c
CFG_SOURCES = config/config.c
LOD_SOURCES = loader/loader.c
TEL_SOURCES = ../telemetry/telemetry.c
UTL_SOURCES = util/util.c util/signal_handler.c
RPT_SOURCES = report/report.c

SOURCES = $(APP_SOURCES) $(CFG_SOURCES) $(LOD_SOURCES) $(TEL_SOURCES) $(UTL_SOURCES) $(RPT_SOURCES)
OBJECTS = $(SOURCES:.c=.o)

all: cortex

cortex: $(OBJECTS) ../scheduler/scheduler.o ../replayer/replayer.o
	$(CC) $(OBJECTS) ../scheduler/scheduler.o ../replayer/replayer.o -o cortex $(LDFLAGS)

clean:
	rm -f $(OBJECTS) cortex

.PHONY: all clean




