/*
 * CORTEX Instruction Counter — Hardware PMU wrapper
 *
 * Provides exact retired instruction counts by wrapping a function call
 * with hardware performance counter enable/disable.
 *
 * Platform support:
 *   Linux (x86_64, ARM64): perf_event_open(PERF_COUNT_HW_INSTRUCTIONS)
 *   macOS Apple Silicon:   kpc_get_thread_counters() (private kperf framework)
 *
 * Usage:
 *   cortex_inscount_init();
 *   cortex_inscount_start();
 *   // ... call function under test ...
 *   uint64_t count = cortex_inscount_stop();
 *   cortex_inscount_teardown();
 */

#ifndef CORTEX_INSCOUNT_H
#define CORTEX_INSCOUNT_H

#include <stdint.h>

/* Multi-counter PMU result (SE-5 Phase 4) */
typedef struct cortex_pmu_counters {
    uint64_t instruction_count;
    uint64_t cycle_count;
    uint64_t backend_stall_cycles;   /* 0 if unavailable */
    uint8_t  has_cycles;
    uint8_t  has_backend_stall;
} cortex_pmu_counters_t;

/* Initialize the instruction counter subsystem. Returns 0 on success, -1 on failure. */
int cortex_inscount_init(void);

/* Reset and enable the instruction counter. */
void cortex_inscount_start(void);

/* Disable all counters and return multi-counter result. */
cortex_pmu_counters_t cortex_inscount_stop_all(void);

/* Disable the counter and return the instruction count since start (backward compat). */
uint64_t cortex_inscount_stop(void);

/* Release resources. */
void cortex_inscount_teardown(void);

/* Check if hardware instruction counting is available on this platform. */
int cortex_inscount_available(void);

/* Query single-core max CPU frequency in Hz. Returns 0 if unknown. */
uint64_t cortex_inscount_cpu_freq_hz(void);

#endif /* CORTEX_INSCOUNT_H */
