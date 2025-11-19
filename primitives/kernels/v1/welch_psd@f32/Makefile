CC = cc
CFLAGS = -Wall -Wextra -O2 -g -fPIC -I../../../../src/engine/include -Idependencies
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

$(TARGET): $(OBJS)
	$(CC) $(SOFLAGS) $(OBJS) $(LDFLAGS) -o $@

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)
