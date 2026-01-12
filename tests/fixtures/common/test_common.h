/*
 * CORTEX Test Common - Shared Test Utilities
 *
 * Provides:
 * - Enhanced assertion macros with better error messages
 * - Floating point comparisons
 * - Array comparisons
 * - Test timing utilities
 * - Mock object creation helpers
 */

/* Define feature test macros BEFORE any includes */
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L  /* For clock_gettime, CLOCK_MONOTONIC, usleep */
#endif

#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE          /* For M_PI and other BSD/SVID features (Linux) */
#endif

#ifndef TEST_COMMON_H
#define TEST_COMMON_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <stdint.h>

/* Define M_PI if not already defined (macOS compatibility) */
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ========================================================================
 * Basic Assertions
 * ======================================================================== */

#define ASSERT(cond, msg) do { \
    if (!(cond)) { \
        fprintf(stderr, "\n[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
        fprintf(stderr, "  Condition: %s\n", #cond); \
        return -1; \
    } \
} while (0)

#define ASSERT_EQ(a, b, msg) do { \
    if ((a) != (b)) { \
        fprintf(stderr, "\n[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
        fprintf(stderr, "  Expected: %ld\n", (long)(b)); \
        fprintf(stderr, "  Got:      %ld\n", (long)(a)); \
        return -1; \
    } \
} while (0)

#define ASSERT_NEQ(a, b, msg) do { \
    if ((a) == (b)) { \
        fprintf(stderr, "\n[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
        fprintf(stderr, "  Should not equal: %ld\n", (long)(b)); \
        return -1; \
    } \
} while (0)

#define ASSERT_NULL(ptr, msg) do { \
    if ((ptr) != NULL) { \
        fprintf(stderr, "\n[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
        fprintf(stderr, "  Expected NULL, got: %p\n", (void*)(ptr)); \
        return -1; \
    } \
} while (0)

#define ASSERT_NOT_NULL(ptr, msg) do { \
    if ((ptr) == NULL) { \
        fprintf(stderr, "\n[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
        fprintf(stderr, "  Expected non-NULL pointer\n"); \
        return -1; \
    } \
} while (0)

#define ASSERT_STR_EQ(a, b, msg) do { \
    if (strcmp((a), (b)) != 0) { \
        fprintf(stderr, "\n[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
        fprintf(stderr, "  Expected: \"%s\"\n", (b)); \
        fprintf(stderr, "  Got:      \"%s\"\n", (a)); \
        return -1; \
    } \
} while (0)

/* ========================================================================
 * Floating Point Assertions
 * ======================================================================== */

#define ASSERT_FLOAT_EQ(a, b, tol, msg) do { \
    float _a = (a); \
    float _b = (b); \
    float _diff = fabsf(_a - _b); \
    if (_diff > (tol)) { \
        fprintf(stderr, "\n[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
        fprintf(stderr, "  Expected: %.6f\n", _b); \
        fprintf(stderr, "  Got:      %.6f\n", _a); \
        fprintf(stderr, "  Diff:     %.6e (tolerance: %.6e)\n", _diff, (float)(tol)); \
        return -1; \
    } \
} while (0)

#define ASSERT_DOUBLE_EQ(a, b, tol, msg) do { \
    double _a = (a); \
    double _b = (b); \
    double _diff = fabs(_a - _b); \
    if (_diff > (tol)) { \
        fprintf(stderr, "\n[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
        fprintf(stderr, "  Expected: %.12f\n", _b); \
        fprintf(stderr, "  Got:      %.12f\n", _a); \
        fprintf(stderr, "  Diff:     %.6e (tolerance: %.6e)\n", _diff, (tol)); \
        return -1; \
    } \
} while (0)

/* ========================================================================
 * Array Assertions
 * ======================================================================== */

#define ASSERT_ARRAY_EQ(a, b, n, msg) do { \
    for (size_t _i = 0; _i < (n); _i++) { \
        if ((a)[_i] != (b)[_i]) { \
            fprintf(stderr, "\n[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
            fprintf(stderr, "  Arrays differ at index %zu\n", _i); \
            fprintf(stderr, "  Expected: %ld\n", (long)(b)[_i]); \
            fprintf(stderr, "  Got:      %ld\n", (long)(a)[_i]); \
            return -1; \
        } \
    } \
} while (0)

#define ASSERT_FLOAT_ARRAY_EQ(a, b, n, tol, msg) do { \
    for (size_t _i = 0; _i < (n); _i++) { \
        float _diff = fabsf((a)[_i] - (b)[_i]); \
        if (_diff > (tol)) { \
            fprintf(stderr, "\n[FAIL] %s:%d: %s\n", __FILE__, __LINE__, msg); \
            fprintf(stderr, "  Arrays differ at index %zu\n", _i); \
            fprintf(stderr, "  Expected: %.6f\n", (b)[_i]); \
            fprintf(stderr, "  Got:      %.6f\n", (a)[_i]); \
            fprintf(stderr, "  Diff:     %.6e (tolerance: %.6e)\n", _diff, (float)(tol)); \
            return -1; \
        } \
    } \
} while (0)

/* ========================================================================
 * Test Organization
 * ======================================================================== */

#define TEST_START(name) \
    fprintf(stderr, "[TEST] %s ... ", name); \
    fflush(stderr)

#define TEST_PASS() do { \
    fprintf(stderr, "PASS\n"); \
    return 0; \
} while (0)

#define TEST_SKIP(reason) do { \
    fprintf(stderr, "SKIP (%s)\n", reason); \
    return 0; \
} while (0)

/* ========================================================================
 * Timing Utilities
 * ======================================================================== */

static inline uint64_t test_get_timestamp_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

#define TEST_TIME_START() uint64_t _test_start_ns = test_get_timestamp_ns()

#define TEST_TIME_END_MS(msg) do { \
    uint64_t _elapsed_ns = test_get_timestamp_ns() - _test_start_ns; \
    double _elapsed_ms = _elapsed_ns / 1000000.0; \
    fprintf(stderr, "  [TIME] %s: %.3f ms\n", msg, _elapsed_ms); \
} while (0)

/* ========================================================================
 * Memory Leak Detection Helpers
 * ======================================================================== */

static inline void* test_malloc_tracked(size_t size, const char *location)
{
    void *ptr = malloc(size);
    if (!ptr) {
        fprintf(stderr, "[ALLOC FAIL] %s: malloc(%zu) failed\n", location, size);
    }
    return ptr;
}

#define STRINGIFY(x) #x
#define TOSTRING(x) STRINGIFY(x)
#define TEST_MALLOC(size) test_malloc_tracked(size, __FILE__ ":" TOSTRING(__LINE__))

#define TEST_FREE(ptr) do { \
    if (ptr) { \
        free(ptr); \
        ptr = NULL; \
    } \
} while (0)

/* ========================================================================
 * Mock Data Generation
 * ======================================================================== */

static inline void test_generate_sine_wave(float *buffer, size_t samples,
                                           float frequency, float sample_rate)
{
    for (size_t i = 0; i < samples; i++) {
        float t = (float)i / sample_rate;
        buffer[i] = sinf(2.0f * M_PI * frequency * t);
    }
}

static inline void test_fill_constant(float *buffer, size_t samples, float value)
{
    for (size_t i = 0; i < samples; i++) {
        buffer[i] = value;
    }
}

static inline void test_fill_sequence(float *buffer, size_t samples)
{
    for (size_t i = 0; i < samples; i++) {
        buffer[i] = (float)i;
    }
}

/* ========================================================================
 * String Utilities
 * ======================================================================== */

static inline char* test_strdup(const char *s)
{
    if (!s) return NULL;
    size_t len = strlen(s);
    char *copy = (char*)malloc(len + 1);
    if (copy) {
        memcpy(copy, s, len + 1);
    }
    return copy;
}

#endif /* TEST_COMMON_H */
