# Makefile for building CSP kernel plugin (ABI v3 trainable)
# Platform-specific shared library build

CC = cc
CFLAGS = -Wall -Wextra -O2 -g -fPIC -I../../../../sdk/kernel/include

# Detect platform and set extension/flag
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SOFLAG = -dynamiclib
    LIBEXT = .dylib
    LDFLAGS = -L../../../../sdk/kernel/lib -lcortex -lm
else
    SOFLAG = -shared
    LIBEXT = .so
    LDFLAGS = -L../../../../sdk/kernel/lib -lcortex -lm
endif

# Kernel name from directory (e.g., "ica" from "ica@f32/")
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
