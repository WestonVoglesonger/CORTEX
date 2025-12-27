# Makefile for building CAR kernel plugin
# Platform-specific shared library build

CC = cc

# For standalone builds, set include paths if not already set by top-level Makefile
CORTEX_PRIMITIVE_INCLUDES ?= -I.. -I../../../../primitives/adapters/v1

CFLAGS = -Wall -Wextra -O2 -g -fPIC $(CORTEX_PRIMITIVE_INCLUDES) -I../../../../src/engine/params
PARAMS_LIB = ../../../../src/engine/params/libcortex_params.a
KERNEL_ABI_OBJ = ../cortex_plugin_abi.o

# Detect platform and set extension/flag
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SOFLAG = -dynamiclib
    LIBEXT = .dylib
else
    SOFLAG = -shared
    LIBEXT = .so
endif

# Kernel name from directory (e.g., "car" from "car@f32/")
KERNEL_NAME = $(shell basename $(CURDIR) | sed 's/@.*//')
PLUGIN_SRC = $(KERNEL_NAME).c
PLUGIN_OBJ = $(KERNEL_NAME).o
PLUGIN_LIB = lib$(KERNEL_NAME)$(LIBEXT)

all: $(PLUGIN_LIB)

$(PLUGIN_OBJ): $(PLUGIN_SRC)
	$(CC) $(CFLAGS) -c -o $@ $<

# Build PARAMS_LIB if it doesn't exist (for standalone builds)
$(PARAMS_LIB):
	$(MAKE) -C ../../../../src/engine/params

# Build KERNEL_ABI_OBJ if it doesn't exist (for standalone builds)
$(KERNEL_ABI_OBJ):
	$(MAKE) -C ../../../../ primitives/kernels/v1/cortex_plugin_abi.o

$(PLUGIN_LIB): $(PLUGIN_OBJ) $(PARAMS_LIB) $(KERNEL_ABI_OBJ)
	$(CC) $(SOFLAG) -o $@ $(PLUGIN_OBJ) $(KERNEL_ABI_OBJ) $(PARAMS_LIB)

clean:
	rm -f $(PLUGIN_OBJ) $(PLUGIN_LIB)

.PHONY: all clean

