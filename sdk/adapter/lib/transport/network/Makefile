CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../../../include

# Network transport sources
SOURCES = tcp_client.c
OBJECTS = $(SOURCES:.c=.o)

all: $(OBJECTS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS)

.PHONY: all clean
