/*
 * Clock Resolution and Timing Accuracy Test
 * 
 * Measures and validates the timing precision of CLOCK_MONOTONIC
 * used for latency measurements in CORTEX benchmarks.
 * 
 * This test:
 * 1. Queries the system's clock resolution using clock_getres()
 * 2. Measures minimum observable time difference
 * 3. Tests timing overhead of clock_gettime() calls
 * 4. Validates that reported latencies are within resolution bounds
 */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>
#include <string.h>
#include <limits.h>
#include <math.h>

#ifdef __APPLE__
#include <mach/mach_time.h>
#endif

#define NSEC_PER_SEC 1000000000ULL
#define TEST_ITERATIONS 10000

/* Query clock resolution using POSIX clock_getres() */
static void test_clock_resolution(void) {
    struct timespec res;
    int ret = clock_getres(CLOCK_MONOTONIC, &res);
    
    if (ret != 0) {
        printf("ERROR: clock_getres() failed\n");
        return;
    }
    
    uint64_t res_ns = (uint64_t)res.tv_sec * NSEC_PER_SEC + (uint64_t)res.tv_nsec;
    
    printf("\n=== Clock Resolution Test ===\n");
    printf("clock_getres(CLOCK_MONOTONIC) = %llu.%09llu seconds\n", 
           (unsigned long long)res.tv_sec, (unsigned long long)res.tv_nsec);
    printf("Resolution: %llu nanoseconds\n", (unsigned long long)res_ns);
    
    if (res_ns <= 1000) {
        printf("✓ Resolution is ≤ 1µs (excellent for microsecond measurements)\n");
    } else if (res_ns <= 1000000) {
        printf("⚠ Resolution is ≤ 1ms (acceptable but coarse for µs measurements)\n");
    } else {
        printf("✗ Resolution > 1ms (too coarse for accurate microsecond measurements)\n");
    }
}

/* Measure minimum observable time difference */
static void test_minimum_time_difference(void) {
    printf("\n=== Minimum Time Difference Test ===\n");
    printf("Measuring minimum observable time difference over %d iterations...\n", TEST_ITERATIONS);
    
    uint64_t min_diff = UINT64_MAX;
    uint64_t max_diff = 0;
    uint64_t sum_diff = 0;
    uint64_t zero_count = 0;
    
    struct timespec start, end;
    
    for (int i = 0; i < TEST_ITERATIONS; i++) {
        clock_gettime(CLOCK_MONOTONIC, &start);
        clock_gettime(CLOCK_MONOTONIC, &end);
        
        uint64_t start_ns = (uint64_t)start.tv_sec * NSEC_PER_SEC + (uint64_t)start.tv_nsec;
        uint64_t end_ns = (uint64_t)end.tv_sec * NSEC_PER_SEC + (uint64_t)end.tv_nsec;
        
        uint64_t diff = end_ns - start_ns;
        
        if (diff == 0) {
            zero_count++;
        } else {
            if (diff < min_diff) min_diff = diff;
            if (diff > max_diff) max_diff = diff;
            sum_diff += diff;
        }
    }
    
    uint64_t avg_diff = (TEST_ITERATIONS - zero_count > 0) ? 
                        sum_diff / (TEST_ITERATIONS - zero_count) : 0;
    
    printf("Minimum time difference: %llu ns\n", (unsigned long long)min_diff);
    printf("Maximum time difference: %llu ns\n", (unsigned long long)max_diff);
    printf("Average time difference: %llu ns\n", (unsigned long long)avg_diff);
    printf("Zero-difference calls: %llu / %d (%.2f%%)\n",
           (unsigned long long)zero_count, TEST_ITERATIONS,
           100.0 * zero_count / TEST_ITERATIONS);
    
    if (min_diff > 0 && min_diff < 1000) {
        printf("✓ Can reliably measure differences down to ~%llu ns\n", (unsigned long long)min_diff);
    } else if (min_diff == 0) {
        printf("⚠ Many zero-difference calls - clock resolution may be limited\n");
    } else {
        printf("✗ Minimum difference is %llu ns (coarse for microsecond measurements)\n", 
               (unsigned long long)min_diff);
    }
}

/* Measure timing overhead of clock_gettime() */
static void test_timing_overhead(void) {
    printf("\n=== Timing Overhead Test ===\n");
    printf("Measuring clock_gettime() call overhead (%d iterations)...\n", TEST_ITERATIONS);
    
    struct timespec start, mid, end;
    uint64_t sum_overhead = 0;
    
    for (int i = 0; i < TEST_ITERATIONS; i++) {
        clock_gettime(CLOCK_MONOTONIC, &start);
        clock_gettime(CLOCK_MONOTONIC, &mid);
        clock_gettime(CLOCK_MONOTONIC, &end);
        
        uint64_t start_ns = (uint64_t)start.tv_sec * NSEC_PER_SEC + (uint64_t)start.tv_nsec;
        uint64_t mid_ns = (uint64_t)mid.tv_sec * NSEC_PER_SEC + (uint64_t)mid.tv_nsec;
        uint64_t end_ns = (uint64_t)end.tv_sec * NSEC_PER_SEC + (uint64_t)end.tv_nsec;
        
        uint64_t overhead = (end_ns - mid_ns) + (mid_ns - start_ns);
        sum_overhead += overhead;
    }
    
    uint64_t avg_overhead = sum_overhead / (2 * TEST_ITERATIONS);
    
    printf("Average clock_gettime() overhead: %llu ns\n", (unsigned long long)avg_overhead);
    
    if (avg_overhead < 100) {
        printf("✓ Overhead < 100ns (excellent, negligible for µs measurements)\n");
    } else if (avg_overhead < 1000) {
        printf("⚠ Overhead < 1µs (acceptable, but adds ~%.1f%% to 6µs measurements)\n",
               100.0 * avg_overhead / 6000.0);
    } else {
        printf("✗ Overhead ≥ 1µs (significant for microsecond measurements)\n");
    }
}

/* Validate latency measurement accuracy */
static void test_latency_measurement_simulation(void) {
    printf("\n=== Simulated Latency Measurement Test ===\n");
    printf("Simulating latency measurement pattern (like scheduler.c)...\n");
    
    /* Simulate measuring a 6µs operation (typical notch_iir latency) */
    uint64_t target_latency_ns = 6000;  // 6 microseconds
    uint64_t sum_measured = 0;
    uint64_t min_measured = UINT64_MAX;
    uint64_t max_measured = 0;
    
    for (int i = 0; i < TEST_ITERATIONS; i++) {
        struct timespec start_ts, end_ts;
        
        clock_gettime(CLOCK_MONOTONIC, &start_ts);
        
        /* Simulate kernel work - busy wait for ~6µs */
        #ifdef __x86_64__
        uint32_t start_low, start_high;
        __asm__ __volatile__("rdtsc" : "=a" (start_low), "=d" (start_high));
        uint64_t start_cycle = ((uint64_t)start_high << 32) | start_low;
        #else
        volatile uint64_t dummy = 0;
        #endif
        
        while (1) {
            #ifdef __x86_64__
            uint32_t end_low, end_high;
            __asm__ __volatile__("rdtsc" : "=a" (end_low), "=d" (end_high));
            uint64_t end_cycle = ((uint64_t)end_high << 32) | end_low;
            if ((end_cycle - start_cycle) > 10000) break;  // Rough calibration for ~6µs
            #else
            dummy++;
            if (dummy > 5000) break;  // Rough calibration
            #endif
        }
        
        clock_gettime(CLOCK_MONOTONIC, &end_ts);
        
        /* Calculate latency like scheduler.c does */
        uint64_t latency_ns = (uint64_t)((end_ts.tv_sec - start_ts.tv_sec) * NSEC_PER_SEC) +
                             (uint64_t)(end_ts.tv_nsec - start_ts.tv_nsec);
        
        if (latency_ns < min_measured) min_measured = latency_ns;
        if (latency_ns > max_measured) max_measured = latency_ns;
        sum_measured += latency_ns;
    }
    
    uint64_t avg_measured = sum_measured / TEST_ITERATIONS;
    double error = fabs((double)avg_measured - (double)target_latency_ns) / (double)target_latency_ns * 100.0;
    
    printf("Target latency: %llu ns (6.0 µs)\n", (unsigned long long)target_latency_ns);
    printf("Average measured: %llu ns (%.2f µs)\n", 
           (unsigned long long)avg_measured, avg_measured / 1000.0);
    printf("Min measured: %llu ns\n", (unsigned long long)min_measured);
    printf("Max measured: %llu ns\n", (unsigned long long)max_measured);
    printf("Measurement error: %.2f%%\n", error);
    
    if (error < 10.0) {
        printf("✓ Measurement accuracy within 10%% (acceptable)\n");
    } else {
        printf("⚠ Measurement error > 10%%, consider calibration\n");
    }
}

/* Platform-specific timing information */
static void show_platform_info(void) {
    printf("\n=== Platform Information ===\n");
    
#ifdef __APPLE__
    mach_timebase_info_data_t timebase;
    kern_return_t ret = mach_timebase_info(&timebase);
    
    if (ret == KERN_SUCCESS) {
        printf("macOS mach_timebase_info:\n");
        printf("  Numerator: %u\n", timebase.numer);
        printf("  Denominator: %u\n", timebase.denom);
        printf("  Effective resolution: %.2f ns\n", 
               (double)timebase.numer / (double)timebase.denom);
    }
    printf("Note: macOS CLOCK_MONOTONIC is mapped to mach_absolute_time()\n");
#endif

#ifdef __linux__
    printf("Linux kernel version info:\n");
    FILE *f = fopen("/proc/version", "r");
    if (f) {
        char buf[256];
        if (fgets(buf, sizeof(buf), f)) {
            printf("  %s", buf);
        }
        fclose(f);
    }
    printf("Note: Linux CLOCK_MONOTONIC uses high-resolution timers (hrtimers)\n");
#endif
}

int main(void) {
    printf("CORTEX Clock Resolution and Timing Accuracy Test\n");
    printf("=================================================\n");
    
    show_platform_info();
    test_clock_resolution();
    test_minimum_time_difference();
    test_timing_overhead();
    test_latency_measurement_simulation();
    
    printf("\n=== Summary ===\n");
    printf("This test validates that CLOCK_MONOTONIC provides sufficient\n");
    printf("resolution and accuracy for microsecond-scale latency measurements\n");
    printf("as used in CORTEX benchmarking reports.\n");
    printf("\nKey takeaways:\n");
    printf("1. Clock resolution should be ≤ 1µs for accurate µs measurements\n");
    printf("2. Timing overhead should be < 10%% of measured latencies\n");
    printf("3. Measurement errors > 10%% suggest system limitations\n");
    
    return 0;
}

