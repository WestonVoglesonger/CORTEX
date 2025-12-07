CC = cc
CFLAGS = -Wall -Wextra -O2 -g -fPIC -I../../../../src/engine/include -I../../../../src/engine/params -Idependencies
PARAMS_LIB = ../../../../src/engine/params/libcortex_params.a
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

$(TARGET): $(OBJS) $(PARAMS_LIB)
	$(CC) $(SOFLAGS) $(OBJS) $(PARAMS_LIB) $(LDFLAGS) -o $@

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# Build params library if it doesn't exist
$(PARAMS_LIB):
	$(MAKE) -C ../../../../src/engine/params

clean:
	rm -f $(OBJS) $(TARGET)
