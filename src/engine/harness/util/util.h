#ifndef CORTEX_HARNESS_UTIL_H
#define CORTEX_HARNESS_UTIL_H

#include <stdint.h>

uint64_t cortex_now_ns(void);  /* CLOCK_MONOTONIC in ns */
void cortex_generate_run_id(char out[32]);
int cortex_create_directories(const char *path);  /* Create parent directories for file */

#endif /* CORTEX_HARNESS_UTIL_H */




