/*
 * CORTEX Instruction Counter — Hardware PMU wrapper
 *
 * Platform-specific implementations:
 *   Linux (x86_64, ARM64): perf_event_open(PERF_COUNT_HW_INSTRUCTIONS)
 *   macOS Apple Silicon:   kpc_get_thread_counters() (private kperf framework)
 *   Other:                 Stubs returning -1 (unavailable)
 */

#include "inscount.h"

#include <stdio.h>
#include <string.h>

/* ================================================================
 * Linux: perf_event_open
 * ================================================================ */
#if defined(__linux__)

#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>

static int pmu_fd = -1;

static long perf_event_open(struct perf_event_attr *hw_event, pid_t pid,
                            int cpu, int group_fd, unsigned long flags)
{
    return syscall(__NR_perf_event_open, hw_event, pid, cpu, group_fd, flags);
}

int cortex_inscount_init(void)
{
    struct perf_event_attr pe;
    memset(&pe, 0, sizeof(pe));
    pe.type           = PERF_TYPE_HARDWARE;
    pe.size           = sizeof(pe);
    pe.config         = PERF_COUNT_HW_INSTRUCTIONS;
    pe.disabled       = 1;
    pe.exclude_kernel = 1;
    pe.exclude_hv     = 1;

    pmu_fd = (int)perf_event_open(&pe, 0, -1, -1, 0);
    if (pmu_fd < 0) {
        perror("perf_event_open");
        return -1;
    }
    return 0;
}

void cortex_inscount_start(void)
{
    if (pmu_fd < 0) return;
    ioctl(pmu_fd, PERF_EVENT_IOC_RESET, 0);
    ioctl(pmu_fd, PERF_EVENT_IOC_ENABLE, 0);
}

uint64_t cortex_inscount_stop(void)
{
    if (pmu_fd < 0) return 0;
    ioctl(pmu_fd, PERF_EVENT_IOC_DISABLE, 0);

    uint64_t count = 0;
    if (read(pmu_fd, &count, sizeof(count)) != sizeof(count)) {
        return 0;
    }
    return count;
}

void cortex_inscount_teardown(void)
{
    if (pmu_fd >= 0) {
        close(pmu_fd);
        pmu_fd = -1;
    }
}

int cortex_inscount_available(void)
{
    if (cortex_inscount_init() == 0) {
        cortex_inscount_teardown();
        return 1;
    }
    return 0;
}

uint64_t cortex_inscount_cpu_freq_hz(void)
{
    /* Linux: read max freq from sysfs (returns kHz) */
    FILE *f = fopen("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", "r");
    if (f) {
        uint64_t khz = 0;
        if (fscanf(f, "%llu", (unsigned long long *)&khz) == 1) {
            fclose(f);
            return khz * 1000;  /* kHz -> Hz */
        }
        fclose(f);
    }
    return 0;
}

/* ================================================================
 * macOS Apple Silicon: kpc (private kperf framework)
 * ================================================================ */
#elif defined(__APPLE__) && defined(__aarch64__)

#include <dlfcn.h>
#include <sys/sysctl.h>

/* KPC constants (from private headers) */
#define KPC_CLASS_FIXED          (0)
#define KPC_CLASS_CONFIGURABLE   (1)
#define KPC_CLASS_FIXED_MASK     (1u << KPC_CLASS_FIXED)

/* Maximum counters we'll read */
#define KPC_MAX_COUNTERS 32

/* Function pointer types for kpc API */
typedef int (*kpc_force_all_ctrs_set_fn)(int);
typedef int (*kpc_set_counting_fn)(uint32_t);
typedef int (*kpc_set_thread_counting_fn)(uint32_t);
typedef int (*kpc_get_thread_counters_fn)(int, unsigned int, uint64_t *);
typedef uint32_t (*kpc_get_counter_count_fn)(uint32_t);

static kpc_force_all_ctrs_set_fn    kpc_force_all_ctrs_set_p;
static kpc_set_counting_fn          kpc_set_counting_p;
static kpc_set_thread_counting_fn   kpc_set_thread_counting_p;
static kpc_get_thread_counters_fn   kpc_get_thread_counters_p;
static kpc_get_counter_count_fn     kpc_get_counter_count_p;

static void *kperf_handle;
static uint64_t baseline[KPC_MAX_COUNTERS];
static uint32_t counter_count;
/* Fixed counter index 0 = retired instructions on Apple Silicon */
static const int INSN_COUNTER_IDX = 0;

int cortex_inscount_init(void)
{
    /* Try framework path first (macOS 13+), then legacy path */
    kperf_handle = dlopen("/System/Library/PrivateFrameworks/kperf.framework/kperf", RTLD_LAZY);
    if (!kperf_handle) {
        kperf_handle = dlopen("/usr/lib/libkperf.dylib", RTLD_LAZY);
    }
    if (!kperf_handle) {
        fprintf(stderr, "inscount: cannot load kperf: %s\n", dlerror());
        return -1;
    }

    kpc_force_all_ctrs_set_p  = (kpc_force_all_ctrs_set_fn)dlsym(kperf_handle, "kpc_force_all_ctrs_set");
    kpc_set_counting_p        = (kpc_set_counting_fn)dlsym(kperf_handle, "kpc_set_counting");
    kpc_set_thread_counting_p = (kpc_set_thread_counting_fn)dlsym(kperf_handle, "kpc_set_thread_counting");
    kpc_get_thread_counters_p = (kpc_get_thread_counters_fn)dlsym(kperf_handle, "kpc_get_thread_counters");
    kpc_get_counter_count_p   = (kpc_get_counter_count_fn)dlsym(kperf_handle, "kpc_get_counter_count");

    if (!kpc_force_all_ctrs_set_p || !kpc_set_counting_p ||
        !kpc_set_thread_counting_p || !kpc_get_thread_counters_p ||
        !kpc_get_counter_count_p) {
        fprintf(stderr, "inscount: failed to resolve kpc symbols\n");
        dlclose(kperf_handle);
        kperf_handle = NULL;
        return -1;
    }

    if (kpc_force_all_ctrs_set_p(1) != 0) {
        fprintf(stderr, "inscount: kpc_force_all_ctrs_set failed (requires sudo or entitlement)\n");
        dlclose(kperf_handle);
        kperf_handle = NULL;
        return -1;
    }

    if (kpc_set_counting_p(KPC_CLASS_FIXED_MASK) != 0) {
        fprintf(stderr, "inscount: kpc_set_counting failed\n");
        dlclose(kperf_handle);
        kperf_handle = NULL;
        return -1;
    }

    if (kpc_set_thread_counting_p(KPC_CLASS_FIXED_MASK) != 0) {
        fprintf(stderr, "inscount: kpc_set_thread_counting failed\n");
        dlclose(kperf_handle);
        kperf_handle = NULL;
        return -1;
    }

    counter_count = kpc_get_counter_count_p(KPC_CLASS_FIXED_MASK);
    if (counter_count == 0 || counter_count > KPC_MAX_COUNTERS) {
        fprintf(stderr, "inscount: unexpected counter count: %u\n", counter_count);
        dlclose(kperf_handle);
        kperf_handle = NULL;
        return -1;
    }

    return 0;
}

void cortex_inscount_start(void)
{
    if (!kperf_handle) return;
    memset(baseline, 0, sizeof(baseline));
    kpc_get_thread_counters_p(0, counter_count, baseline);
}

uint64_t cortex_inscount_stop(void)
{
    if (!kperf_handle) return 0;

    uint64_t current[KPC_MAX_COUNTERS];
    memset(current, 0, sizeof(current));
    kpc_get_thread_counters_p(0, counter_count, current);

    return current[INSN_COUNTER_IDX] - baseline[INSN_COUNTER_IDX];
}

void cortex_inscount_teardown(void)
{
    if (kperf_handle) {
        dlclose(kperf_handle);
        kperf_handle = NULL;
    }
}

int cortex_inscount_available(void)
{
    if (cortex_inscount_init() == 0) {
        cortex_inscount_teardown();
        return 1;
    }
    return 0;
}

uint64_t cortex_inscount_cpu_freq_hz(void)
{
    /* Try hw.cpufrequency_max first (Intel Macs) */
    uint64_t freq = 0;
    size_t size = sizeof(freq);
    if (sysctlbyname("hw.cpufrequency_max", &freq, &size, NULL, 0) == 0 && freq > 0) {
        return freq;
    }

    /* Apple Silicon: hw.cpufrequency_max doesn't exist.
     * Look up max P-core frequency from chip name. */
    char brand[128] = {0};
    size = sizeof(brand);
    if (sysctlbyname("machdep.cpu.brand_string", brand, &size, NULL, 0) != 0) {
        return 0;
    }

    /* Known Apple Silicon max P-core frequencies (Hz).
     * Source: Eclectic Light Company (powermetrics measurements).
     * Match longest prefix first to distinguish e.g. "M4 Pro" from "M4". */
    static const struct { const char *name; uint64_t freq_hz; } chips[] = {
        {"Apple M4 Max",   4512000000ULL},
        {"Apple M4 Pro",   4512000000ULL},
        {"Apple M4",       4512000000ULL},
        {"Apple M3 Ultra", 4056000000ULL},
        {"Apple M3 Max",   4056000000ULL},
        {"Apple M3 Pro",   4056000000ULL},
        {"Apple M3",       4056000000ULL},
        {"Apple M2 Ultra", 3696000000ULL},
        {"Apple M2 Max",   3696000000ULL},
        {"Apple M2 Pro",   3696000000ULL},
        {"Apple M2",       3696000000ULL},
        {"Apple M1 Ultra", 3228000000ULL},
        {"Apple M1 Max",   3228000000ULL},
        {"Apple M1 Pro",   3228000000ULL},
        {"Apple M1",       3228000000ULL},
    };
    for (size_t i = 0; i < sizeof(chips) / sizeof(chips[0]); i++) {
        if (strncmp(brand, chips[i].name, strlen(chips[i].name)) == 0) {
            return chips[i].freq_hz;
        }
    }

    return 0;
}

/* ================================================================
 * Unsupported platform: stubs
 * ================================================================ */
#else

int cortex_inscount_init(void)          { return -1; }
void cortex_inscount_start(void)        { }
uint64_t cortex_inscount_stop(void)     { return 0; }
void cortex_inscount_teardown(void)     { }
int cortex_inscount_available(void)     { return 0; }
uint64_t cortex_inscount_cpu_freq_hz(void) { return 0; }

#endif
