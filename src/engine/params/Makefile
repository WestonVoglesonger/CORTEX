# Makefile for CORTEX parameter accessor library

CC = cc
CFLAGS = -Wall -Wextra -O2 -g -fPIC -std=c11
AR = ar

# Library name
LIB = libcortex_params.a

# Source files
SRCS = accessor.c
OBJS = $(SRCS:.c=.o)

all: $(LIB)

$(LIB): $(OBJS)
	$(AR) rcs $@ $^

%.o: %.c accessor.h
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJS) $(LIB)

.PHONY: all clean
