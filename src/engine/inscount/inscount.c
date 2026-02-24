/*
 * CORTEX Instruction Counter — Hardware PMU wrapper
 *
 * Platform-specific implementations:
 *   Linux (x86_64, ARM64): perf_event_open(PERF_COUNT_HW_INSTRUCTIONS)
 *   macOS Apple Silicon:   kpc_get_thread_counters() (private kperf framework)
 *   Other:                 Stubs returning -1 (unavailable)
 */

/* Feature test macro: expose pid_t, syscall() etc. under -std=c11 on Linux */
#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif

#include "inscount.h"

#include <stdio.h>
#include <string.h>

/* ================================================================
 * Linux: perf_event_open
 * ================================================================ */
#if defined(__linux__)

#include <unistd.h>
#include <sched.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>

static int fd_instructions = -1;
static int fd_cycles = -1;
static int fd_backend_stall = -1;
static int pinned_cpu = -1;  /* CPU we pinned to for PMU (used for freq query) */

static long perf_event_open(struct perf_event_attr *hw_event, pid_t pid,
                            int cpu, int group_fd, unsigned long flags)
{
    return syscall(__NR_perf_event_open, hw_event, pid, cpu, group_fd, flags);
}

/* On big.LITTLE ARM (e.g. Apple Silicon under Asahi Linux), efficiency cores
 * may not support PERF_TYPE_HARDWARE counters. Probe each CPU and pin to
 * the first one where perf_event_open + a test read returns non-zero. */
static int pin_to_pmu_capable_core(void)
{
    int ncpus = (int)sysconf(_SC_NPROCESSORS_ONLN);
    if (ncpus <= 0) ncpus = 8;

    for (int cpu = ncpus - 1; cpu >= 0; cpu--) {  /* P-cores typically last */
        cpu_set_t mask;
        CPU_ZERO(&mask);
        CPU_SET(cpu, &mask);
        if (sched_setaffinity(0, sizeof(mask), &mask) != 0)
            continue;

        struct perf_event_attr pe;
        memset(&pe, 0, sizeof(pe));
        pe.type           = PERF_TYPE_HARDWARE;
        pe.size           = sizeof(pe);
        pe.config         = PERF_COUNT_HW_INSTRUCTIONS;
        pe.disabled       = 1;
        pe.exclude_kernel = 1;
        pe.exclude_hv     = 1;

        int fd = (int)perf_event_open(&pe, 0, -1, -1, 0);
        if (fd < 0) continue;

        ioctl(fd, PERF_EVENT_IOC_RESET, 0);
        ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);
        /* Burn a few instructions */
        volatile int dummy = 0;
        for (int i = 0; i < 1000; i++) dummy += i;
        ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);

        uint64_t count = 0;
        read(fd, &count, sizeof(count));
        close(fd);

        if (count > 0) {
            (void)dummy;
            return cpu;
        }
    }
    return -1;  /* no capable core found */
}

int cortex_inscount_init(void)
{
    struct perf_event_attr pe;

    /* On ARM big.LITTLE, pin to a PMU-capable core */
#if defined(__aarch64__)
    pinned_cpu = pin_to_pmu_capable_core();
    if (pinned_cpu >= 0) {
        fprintf(stderr, "inscount: pinned to cpu%d for PMU\n", pinned_cpu);
    }
#endif

    /* Instructions (group leader) */
    memset(&pe, 0, sizeof(pe));
    pe.type           = PERF_TYPE_HARDWARE;
    pe.size           = sizeof(pe);
    pe.config         = PERF_COUNT_HW_INSTRUCTIONS;
    pe.disabled       = 1;
    pe.exclude_kernel = 1;
    pe.exclude_hv     = 1;

    fd_instructions = (int)perf_event_open(&pe, 0, -1, -1, 0);
    if (fd_instructions < 0) {
        perror("perf_event_open(instructions)");
        return -1;
    }

    /* CPU cycles (group member) */
    memset(&pe, 0, sizeof(pe));
    pe.type           = PERF_TYPE_HARDWARE;
    pe.size           = sizeof(pe);
    pe.config         = PERF_COUNT_HW_CPU_CYCLES;
    pe.disabled       = 1;
    pe.exclude_kernel = 1;
    pe.exclude_hv     = 1;

    fd_cycles = (int)perf_event_open(&pe, 0, -1, fd_instructions, 0);
    if (fd_cycles < 0) {
        /* Non-fatal: cycles unavailable */
        fd_cycles = -1;
    }

    /* Backend stall cycles (non-fatal) */
    memset(&pe, 0, sizeof(pe));
    pe.type           = PERF_TYPE_HARDWARE;
    pe.size           = sizeof(pe);
    pe.config         = PERF_COUNT_HW_STALLED_CYCLES_BACKEND;
    pe.disabled       = 1;
    pe.exclude_kernel = 1;
    pe.exclude_hv     = 1;

    fd_backend_stall = (int)perf_event_open(&pe, 0, -1, fd_instructions, 0);
    if (fd_backend_stall < 0) {
        /* Non-fatal: backend stall unavailable */
        fd_backend_stall = -1;
    }

    return 0;
}

void cortex_inscount_start(void)
{
    if (fd_instructions >= 0) {
        ioctl(fd_instructions, PERF_EVENT_IOC_RESET, 0);
        ioctl(fd_instructions, PERF_EVENT_IOC_ENABLE, 0);
    }
    if (fd_cycles >= 0) {
        ioctl(fd_cycles, PERF_EVENT_IOC_RESET, 0);
        ioctl(fd_cycles, PERF_EVENT_IOC_ENABLE, 0);
    }
    if (fd_backend_stall >= 0) {
        ioctl(fd_backend_stall, PERF_EVENT_IOC_RESET, 0);
        ioctl(fd_backend_stall, PERF_EVENT_IOC_ENABLE, 0);
    }
}

cortex_pmu_counters_t cortex_inscount_stop_all(void)
{
    cortex_pmu_counters_t result;
    memset(&result, 0, sizeof(result));

    if (fd_instructions >= 0) {
        ioctl(fd_instructions, PERF_EVENT_IOC_DISABLE, 0);
        uint64_t count = 0;
        if (read(fd_instructions, &count, sizeof(count)) == sizeof(count))
            result.instruction_count = count;
    }
    if (fd_cycles >= 0) {
        ioctl(fd_cycles, PERF_EVENT_IOC_DISABLE, 0);
        uint64_t count = 0;
        if (read(fd_cycles, &count, sizeof(count)) == sizeof(count)) {
            result.cycle_count = count;
            result.has_cycles = 1;
        }
    }
    if (fd_backend_stall >= 0) {
        ioctl(fd_backend_stall, PERF_EVENT_IOC_DISABLE, 0);
        uint64_t count = 0;
        if (read(fd_backend_stall, &count, sizeof(count)) == sizeof(count)) {
            result.backend_stall_cycles = count;
            result.has_backend_stall = 1;
        }
    }
    return result;
}

uint64_t cortex_inscount_stop(void)
{
    cortex_pmu_counters_t all = cortex_inscount_stop_all();
    return all.instruction_count;
}

void cortex_inscount_teardown(void)
{
    if (fd_instructions >= 0) { close(fd_instructions); fd_instructions = -1; }
    if (fd_cycles >= 0) { close(fd_cycles); fd_cycles = -1; }
    if (fd_backend_stall >= 0) { close(fd_backend_stall); fd_backend_stall = -1; }
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
    /* Linux: read max freq from sysfs (returns kHz).
     * Use pinned CPU if available (on big.LITTLE, cpu0 may be an E-core
     * with a much lower max freq than the P-core we're actually running on). */
    int cpu = (pinned_cpu >= 0) ? pinned_cpu : 0;
    char path[128];
    snprintf(path, sizeof(path),
             "/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq", cpu);
    FILE *f = fopen(path, "r");
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
#define KPC_CLASS_CONFIGURABLE_MASK (1u << KPC_CLASS_CONFIGURABLE)

/* MAP_STALL_DISPATCH: dispatch back-pressure stall cycles on Apple Silicon.
 * Unofficial Firestorm PMU event from dougallj's reverse-engineered event list.
 * Raw PMESR event code 0x70; CFGWORD_EL0A64EN selects userspace-only counting.
 * Event code may change across chip generations — verified on M1. */
#define MAP_STALL_DISPATCH_EVENT   0x70
#define CFGWORD_EL0A64EN_MASK      0x20000
#define MAP_STALL_DISPATCH_CONFIG  (MAP_STALL_DISPATCH_EVENT | CFGWORD_EL0A64EN_MASK)

/* Maximum counters we'll read (M1: 2 fixed + 8 configurable = 10) */
#define KPC_MAX_COUNTERS 32

/* Function pointer types for kpc API */
typedef int (*kpc_force_all_ctrs_set_fn)(int);
typedef int (*kpc_set_counting_fn)(uint32_t);
typedef int (*kpc_set_thread_counting_fn)(uint32_t);
typedef int (*kpc_get_thread_counters_fn)(int, unsigned int, uint64_t *);
typedef uint32_t (*kpc_get_counter_count_fn)(uint32_t);
typedef int (*kpc_set_config_fn)(uint32_t, uint64_t *);
typedef uint32_t (*kpc_get_config_count_fn)(uint32_t);

static kpc_force_all_ctrs_set_fn    kpc_force_all_ctrs_set_p;
static kpc_set_counting_fn          kpc_set_counting_p;
static kpc_set_thread_counting_fn   kpc_set_thread_counting_p;
static kpc_get_thread_counters_fn   kpc_get_thread_counters_p;
static kpc_get_counter_count_fn     kpc_get_counter_count_p;
static kpc_set_config_fn            kpc_set_config_p;
static kpc_get_config_count_fn      kpc_get_config_count_p;

static void *kperf_handle;
static uint64_t baseline[KPC_MAX_COUNTERS];
static uint32_t counter_count;
static uint32_t fixed_count;        /* Number of fixed counters (offset for configurable) */
static int has_configurable;        /* Whether MAP_STALL_DISPATCH is configured */
/* Apple Silicon kpc fixed counter mapping (verified via kpc_probe):
 *   index 0 = CPU cycles
 *   index 1 = retired instructions
 * Note: counter[1]/iter matches exact instruction count from disassembly. */
static const int CYCLE_COUNTER_IDX = 0;
static const int INSN_COUNTER_IDX = 1;

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
    kpc_set_config_p          = (kpc_set_config_fn)dlsym(kperf_handle, "kpc_set_config");
    kpc_get_config_count_p    = (kpc_get_config_count_fn)dlsym(kperf_handle, "kpc_get_config_count");

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

    /* Try to configure MAP_STALL_DISPATCH on first programmable counter (PMC2).
     * Non-fatal: if configurable counters are unavailable, we still have
     * fixed counters for cycles and instructions. */
    fixed_count = counter_count;
    has_configurable = 0;

    if (kpc_set_config_p && kpc_get_config_count_p) {
        uint32_t cfg_count = kpc_get_config_count_p(KPC_CLASS_CONFIGURABLE_MASK);
        if (cfg_count > 0 && cfg_count <= KPC_MAX_COUNTERS) {
            uint64_t config[KPC_MAX_COUNTERS] = {0};
            config[0] = MAP_STALL_DISPATCH_CONFIG;  /* PMC2 = MAP_STALL_DISPATCH */

            if (kpc_set_config_p(KPC_CLASS_CONFIGURABLE_MASK, config) == 0) {
                uint32_t combined = KPC_CLASS_FIXED_MASK | KPC_CLASS_CONFIGURABLE_MASK;
                if (kpc_set_counting_p(combined) == 0 &&
                    kpc_set_thread_counting_p(combined) == 0) {
                    counter_count = kpc_get_counter_count_p(combined);
                    if (counter_count > fixed_count && counter_count <= KPC_MAX_COUNTERS) {
                        has_configurable = 1;
                        fprintf(stderr, "inscount: MAP_STALL_DISPATCH configured on PMC2 "
                                "(counter index %u)\n", fixed_count);
                    }
                }
            }
        }
    }

    if (!has_configurable) {
        fprintf(stderr, "inscount: configurable counters unavailable, "
                "backend_stall disabled\n");
    }

    return 0;
}

void cortex_inscount_start(void)
{
    if (!kperf_handle) return;
    memset(baseline, 0, sizeof(baseline));
    kpc_get_thread_counters_p(0, counter_count, baseline);
}

cortex_pmu_counters_t cortex_inscount_stop_all(void)
{
    cortex_pmu_counters_t result;
    memset(&result, 0, sizeof(result));

    if (!kperf_handle) return result;

    uint64_t current[KPC_MAX_COUNTERS];
    memset(current, 0, sizeof(current));
    kpc_get_thread_counters_p(0, counter_count, current);

    result.instruction_count = current[INSN_COUNTER_IDX] - baseline[INSN_COUNTER_IDX];

    if (counter_count > (uint32_t)CYCLE_COUNTER_IDX) {
        result.cycle_count = current[CYCLE_COUNTER_IDX] - baseline[CYCLE_COUNTER_IDX];
        result.has_cycles = 1;
    }

    /* Backend stall from configurable counter (MAP_STALL_DISPATCH on PMC2) */
    if (has_configurable && counter_count > fixed_count) {
        result.backend_stall_cycles = current[fixed_count] - baseline[fixed_count];
        result.has_backend_stall = 1;
    }

    return result;
}

uint64_t cortex_inscount_stop(void)
{
    cortex_pmu_counters_t all = cortex_inscount_stop_all();
    return all.instruction_count;
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
cortex_pmu_counters_t cortex_inscount_stop_all(void) {
    cortex_pmu_counters_t r;
    memset(&r, 0, sizeof(r));
    return r;
}
uint64_t cortex_inscount_stop(void)     { return 0; }
void cortex_inscount_teardown(void)     { }
int cortex_inscount_available(void)     { return 0; }
uint64_t cortex_inscount_cpu_freq_hz(void) { return 0; }

#endif
