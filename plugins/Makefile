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

# Placeholder Makefile (no plugins to build while specs are being written)

all:
	@echo "No plugins to build. Specs in progress."

clean:
	@true

.PHONY: all clean




