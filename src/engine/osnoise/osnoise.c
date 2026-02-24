/*
 * CORTEX OS Noise Measurement — tracefs osnoise wrapper
 *
 * Linux: reads osnoise per-cpu stats from tracefs.
 * macOS/other: stubs returning -1/0.
 */

#include "osnoise.h"

#include <stdio.h>
#include <string.h>

/* ================================================================
 * Linux: tracefs osnoise tracer
 * ================================================================ */
#if defined(__linux__)

#include <stdlib.h>
#include <unistd.h>
#include <dirent.h>

static const char *TRACEFS_ROOT = "/sys/kernel/tracing";
static const char *TRACEFS_ROOT_ALT = "/sys/kernel/debug/tracing";
static const char *tracefs_path = NULL;
static int osnoise_enabled = 0;
static uint64_t baseline_noise_ns = 0;

/* Read total noise from per_cpu stats.
 * File: <tracefs>/osnoise/per_cpu/cpu<N>/noise
 * We sum across all CPUs for simplicity. */
static uint64_t read_total_noise_ns(void)
{
    char path[256];
    uint64_t total = 0;
    DIR *cpudir;

    snprintf(path, sizeof(path), "%s/osnoise/per_cpu", tracefs_path);
    cpudir = opendir(path);
    if (!cpudir) return 0;

    struct dirent *entry;
    while ((entry = readdir(cpudir)) != NULL) {
        if (strncmp(entry->d_name, "cpu", 3) != 0)
            continue;

        char noise_path[512];
        snprintf(noise_path, sizeof(noise_path), "%s/%s/noise",
                 path, entry->d_name);

        FILE *f = fopen(noise_path, "r");
        if (f) {
            uint64_t val = 0;
            if (fscanf(f, "%llu", (unsigned long long *)&val) == 1) {
                total += val;
            }
            fclose(f);
        }
    }
    closedir(cpudir);
    return total;
}

/* Write a string to a tracefs file. */
static int write_tracefs(const char *relpath, const char *value)
{
    char path[256];
    snprintf(path, sizeof(path), "%s/%s", tracefs_path, relpath);
    FILE *f = fopen(path, "w");
    if (!f) return -1;
    fprintf(f, "%s", value);
    fclose(f);
    return 0;
}

int cortex_osnoise_init(void)
{
    /* Find tracefs mount */
    char check[256];

    snprintf(check, sizeof(check), "%s/osnoise", TRACEFS_ROOT);
    if (access(check, F_OK) == 0) {
        tracefs_path = TRACEFS_ROOT;
    } else {
        snprintf(check, sizeof(check), "%s/osnoise", TRACEFS_ROOT_ALT);
        if (access(check, F_OK) == 0) {
            tracefs_path = TRACEFS_ROOT_ALT;
        } else {
            return -1;
        }
    }

    /* Enable osnoise tracer */
    if (write_tracefs("current_tracer", "osnoise") != 0) {
        tracefs_path = NULL;
        return -1;
    }

    osnoise_enabled = 1;
    baseline_noise_ns = 0;
    return 0;
}

void cortex_osnoise_reset(void)
{
    if (!osnoise_enabled) return;
    baseline_noise_ns = read_total_noise_ns();
}

uint64_t cortex_osnoise_read_ns(void)
{
    if (!osnoise_enabled) return 0;
    uint64_t current = read_total_noise_ns();
    return (current >= baseline_noise_ns) ? (current - baseline_noise_ns) : 0;
}

void cortex_osnoise_teardown(void)
{
    if (osnoise_enabled && tracefs_path) {
        write_tracefs("current_tracer", "nop");
    }
    osnoise_enabled = 0;
    tracefs_path = NULL;
}

int cortex_osnoise_available(void)
{
    if (cortex_osnoise_init() == 0) {
        cortex_osnoise_teardown();
        return 1;
    }
    return 0;
}

/* ================================================================
 * Unsupported platform: stubs
 * ================================================================ */
#else

int cortex_osnoise_init(void)          { return -1; }
void cortex_osnoise_reset(void)        { }
uint64_t cortex_osnoise_read_ns(void)  { return 0; }
void cortex_osnoise_teardown(void)     { }
int cortex_osnoise_available(void)     { return 0; }

#endif
