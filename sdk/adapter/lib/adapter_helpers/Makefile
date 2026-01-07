CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../../include

# Adapter SDK helpers
SOURCES = protocol_helpers.c transport_helpers.c system_info.c
OBJECTS = $(SOURCES:.c=.o)

all: $(OBJECTS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS)

.PHONY: all clean
