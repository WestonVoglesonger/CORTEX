CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../include

SOURCES = loader/loader.c state_io/state_io.c params/accessor.c
OBJECTS = $(SOURCES:.c=.o)

all: libcortex.a

libcortex.a: $(OBJECTS)
	ar rcs $@ $^

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS) libcortex.a

.PHONY: all clean
