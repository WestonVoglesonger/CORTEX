CC = cc
CFLAGS = -Wall -Wextra -O2 -g -fPIC -I../include
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SOFLAG = -dynamiclib
    LIBEXT = .dylib
else
    SOFLAG = -shared
    LIBEXT = .so
endif

# Automatic plugin detection and building
PLUGIN_NAMES = $(basename $(wildcard *.c))
PLUGIN_LIBS = $(addprefix lib, $(addsuffix $(LIBEXT), $(PLUGIN_NAMES)))
PLUGIN_OBJS = $(PLUGIN_NAMES:=.o)

all: $(PLUGIN_LIBS)

# Pattern rule for building plugin libraries
lib%$(LIBEXT): %.o
	$(CC) $(SOFLAG) -o $@ $^

# Pattern rule for compiling plugin objects
%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -f $(PLUGIN_OBJS) $(PLUGIN_LIBS)

.PHONY: all clean




