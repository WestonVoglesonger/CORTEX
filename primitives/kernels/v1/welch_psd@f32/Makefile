CC = cc

# For standalone builds, set include paths if not already set by top-level Makefile
CORTEX_PRIMITIVE_INCLUDES ?= -I.. -I../../../../primitives/adapters/v1

CFLAGS = -Wall -Wextra -O2 -g -fPIC $(CORTEX_PRIMITIVE_INCLUDES) -I../../../../src/engine/params -Idependencies
PARAMS_LIB = ../../../../src/engine/params/libcortex_params.a
KERNEL_ABI_OBJ = ../cortex_plugin_abi.o
LDFLAGS = -lm

# Detect OS for shared library extension and flags
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
	LIB_EXT = dylib
	SOFLAGS = -dynamiclib -undefined dynamic_lookup
else
	LIB_EXT = so
	SOFLAGS = -shared
endif

TARGET = libwelch_psd.$(LIB_EXT)
SRCS = welch_psd.c dependencies/kiss_fft.c
OBJS = $(SRCS:.c=.o)

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJS) $(PARAMS_LIB) $(KERNEL_ABI_OBJ)
	$(CC) $(SOFLAGS) $(OBJS) $(KERNEL_ABI_OBJ) $(PARAMS_LIB) $(LDFLAGS) -o $@

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# Build PARAMS_LIB if it doesn't exist (for standalone builds)
$(PARAMS_LIB):
	$(MAKE) -C ../../../../src/engine/params

# Build KERNEL_ABI_OBJ if it doesn't exist (for standalone builds)
$(KERNEL_ABI_OBJ):
	$(MAKE) -C ../../../../ primitives/kernels/v1/cortex_plugin_abi.o

clean:
	rm -f $(OBJS) $(TARGET)
