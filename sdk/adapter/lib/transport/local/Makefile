CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../../../include

# Local transport sources
SOURCES = mock.c shm.c
OBJECTS = $(SOURCES:.c=.o)

all: $(OBJECTS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS)

.PHONY: all clean
