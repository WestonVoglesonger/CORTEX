# Makefile for building no-op kernel plugin
# Platform-specific shared library build

CC = cc
CFLAGS = -Wall -Wextra -O2 -g -fPIC -I../../../../sdk/kernel/include

# Detect platform and set extension/flag
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SOFLAG = -dynamiclib
    LIBEXT = .dylib
    LDFLAGS = -L../../../../sdk/kernel/lib -lcortex
else
    SOFLAG = -shared
    LIBEXT = .so
    LDFLAGS = -L../../../../sdk/kernel/lib -lcortex
endif

# Kernel name from directory (e.g., "noop" from "noop@f32/")
KERNEL_NAME = $(shell basename $(CURDIR) | sed 's/@.*//')
PLUGIN_SRC = $(KERNEL_NAME).c
PLUGIN_OBJ = $(KERNEL_NAME).o
PLUGIN_LIB = lib$(KERNEL_NAME)$(LIBEXT)

all: $(PLUGIN_LIB)

$(PLUGIN_OBJ): $(PLUGIN_SRC)
	$(CC) $(CFLAGS) -c -o $@ $<

$(PLUGIN_LIB): $(PLUGIN_OBJ)
	$(CC) $(SOFLAG) -o $@ $(PLUGIN_OBJ) $(LDFLAGS)

clean:
	rm -f $(PLUGIN_OBJ) $(PLUGIN_LIB)

.PHONY: all clean
