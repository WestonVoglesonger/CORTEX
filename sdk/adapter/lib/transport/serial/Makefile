CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../../../include

# Serial transport sources
SOURCES = uart_posix.c
OBJECTS = $(SOURCES:.c=.o)

all: $(OBJECTS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS)

.PHONY: all clean
