# Device communication layer Makefile

CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11
INCLUDES = -I../../../../sdk/adapter/include

SRCS = device_comm.c
OBJS = $(SRCS:.c=.o)

all: $(OBJS)

%.o: %.c
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

clean:
	rm -f $(OBJS)

.PHONY: all clean
