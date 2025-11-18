CC = gcc
CFLAGS = -Wall -Wextra -O3 -fPIC -shared -I../../../../src/engine/include -Idependencies
LDFLAGS = 

# Detect OS for shared library extension
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
	LIB_EXT = dylib
else
	LIB_EXT = so
endif

TARGET = libwelch_psd.$(LIB_EXT)
SRCS = welch_psd.c dependencies/kiss_fft.c
OBJS = $(SRCS:.c=.o)

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)
