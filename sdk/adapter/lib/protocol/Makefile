CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../../include -I.

# Protocol implementation sources
SOURCES = protocol.c crc32.c
OBJECTS = $(SOURCES:.c=.o)

all: $(OBJECTS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS)

.PHONY: all clean
