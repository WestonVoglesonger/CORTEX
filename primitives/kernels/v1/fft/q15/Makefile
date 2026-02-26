# Makefile for fft@q15 kernel plugin
# CRITICAL: -DFIXED_POINT=16 must apply to BOTH fft.c and kiss_fft.c.
# Mismatch = silent ABI breakage (kiss_fft_cpx layout differs).

CC = cc
CFLAGS = -Wall -Wextra -O2 -g -fPIC -DFIXED_POINT=16 -I../../../../../sdk/kernel/include -Idependencies

# Detect OS for shared library extension and flags
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
	LIB_EXT = dylib
	SOFLAGS = -dynamiclib -undefined dynamic_lookup
	LDFLAGS = -L../../../../../sdk/kernel/lib -lcortex -lm
else
	LIB_EXT = so
	SOFLAGS = -shared
	LDFLAGS = -L../../../../../sdk/kernel/lib -lcortex -lm
endif

TARGET = libfft.$(LIB_EXT)
SRCS = fft.c dependencies/kiss_fft.c
OBJS = $(SRCS:.c=.o)

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(SOFLAGS) $(OBJS) $(LDFLAGS) -o $@

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)
