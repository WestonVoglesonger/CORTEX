#define _POSIX_C_SOURCE 200809L

#include "util.h"

#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libgen.h>
#include <sys/stat.h>
#include <unistd.h>
#include <errno.h>

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

int cortex_create_directories(const char *path) {
    if (!path) return -1;

    /* Make a copy since dirname may modify the string */
    char *path_copy = strdup(path);
    if (!path_copy) return -1;

    /* Get directory part */
    char *dir = dirname(path_copy);

    /* Create directory recursively */
    char *slash = dir;
    while ((slash = strchr(slash + 1, '/'))) {
        *slash = '\0';
        if (mkdir(dir, 0755) == -1 && errno != EEXIST) {
            free(path_copy);
            return -1;
        }
        *slash = '/';
    }

    /* Create the final directory */
    if (mkdir(dir, 0755) == -1 && errno != EEXIST) {
        free(path_copy);
        return -1;
    }

    free(path_copy);
    return 0;
}
