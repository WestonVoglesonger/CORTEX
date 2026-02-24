/*
 * CORTEX OS Noise Measurement — tracefs osnoise wrapper
 *
 * Provides per-window OS noise measurement on Linux via the osnoise tracer.
 * Stubs return -1/0 on unsupported platforms (macOS, etc.).
 *
 * Usage:
 *   cortex_osnoise_init();
 *   cortex_osnoise_reset();      // before window
 *   // ... execute window ...
 *   uint64_t ns = cortex_osnoise_read_ns();  // after window
 *   cortex_osnoise_teardown();
 */

#ifndef CORTEX_OSNOISE_H
#define CORTEX_OSNOISE_H

#include <stdint.h>

/* Initialize osnoise tracer. Returns 0 if available, -1 otherwise. */
int cortex_osnoise_init(void);

/* Reset accumulator before window dispatch. */
void cortex_osnoise_reset(void);

/* Read accumulated noise in nanoseconds since last reset. */
uint64_t cortex_osnoise_read_ns(void);

/* Release resources. */
void cortex_osnoise_teardown(void);

/* Check if osnoise tracer is available on this platform. */
int cortex_osnoise_available(void);

#endif /* CORTEX_OSNOISE_H */
