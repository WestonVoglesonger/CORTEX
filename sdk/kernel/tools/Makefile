CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../include

# Platform-specific linker flags
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    # macOS: dlopen is in libSystem, no -ldl needed
    LDFLAGS = -L../lib -lcortex -lpthread -lm
else
    # Linux: requires explicit -ldl for dlopen/dlsym
    LDFLAGS = -L../lib -lcortex -ldl -lpthread -lm
endif

all: cortex_calibrate cortex_validate

cortex_calibrate: calibrate.c ../lib/libcortex.a
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)

cortex_validate: validate.c ../lib/libcortex.a
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)

clean:
	rm -f cortex_calibrate cortex_validate

.PHONY: all clean
