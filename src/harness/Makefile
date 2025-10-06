CC = gcc
CFLAGS = -Wall -Wextra -g -O2 -std=c11 -I../../include -I../scheduler -I../replayer -Iapp -Iconfig -Iloader -Itelemetry -Iutil
LDFLAGS = -ldl -lpthread -lm

APP_SOURCES = app/main.c
CFG_SOURCES = config/config.c
LOD_SOURCES = loader/loader.c
TEL_SOURCES = telemetry/telemetry.c
UTL_SOURCES = util/util.c

SOURCES = $(APP_SOURCES) $(CFG_SOURCES) $(LOD_SOURCES) $(TEL_SOURCES) $(UTL_SOURCES)
OBJECTS = $(SOURCES:.c=.o)

all: cortex

cortex: $(OBJECTS) ../scheduler/scheduler.o ../replayer/replayer.o
	$(CC) $(OBJECTS) ../scheduler/scheduler.o ../replayer/replayer.o -o cortex $(LDFLAGS)

clean:
	rm -f $(OBJECTS) cortex

.PHONY: all clean




