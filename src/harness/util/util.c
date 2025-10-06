#include "util.h"

#include <time.h>
#include <stdio.h>

#define NSEC_PER_SEC 1000000000ULL

uint64_t cortex_now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * NSEC_PER_SEC + (uint64_t)ts.tv_nsec;
}

void cortex_generate_run_id(char out[32]) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    snprintf(out, 32, "%u%03u", (unsigned)ts.tv_sec, (unsigned)(ts.tv_nsec/1000000));
}




