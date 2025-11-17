#ifndef CORTEX_HARNESS_UTIL_H
#define CORTEX_HARNESS_UTIL_H

#include <stddef.h>
#include <stdint.h>

uint64_t cortex_now_ns(void);  /* CLOCK_MONOTONIC in ns */
void cortex_generate_run_id(char out[32]);
int cortex_create_directories(const char *path);  /* Create parent directories for file */

/**
 * Check if multiplying two size_t values would overflow.
 *
 * Uses compiler builtins when available (GCC 5.1+, Clang 3.4+) for optimal
 * performance (single instruction). Falls back to portable division check
 * on other compilers.
 *
 * This function is used by the harness to validate buffer size calculations
 * before allocation. Prevents heap corruption from integer overflow.
 *
 * @param a First operand
 * @param b Second operand
 * @param result Pointer to store result if no overflow
 * @return 0 if multiplication is safe (result stored in *result)
 *         1 if multiplication would overflow
 *
 * Example:
 *   size_t window_samples;
 *   if (cortex_mul_size_overflow(config->window_length, config->channels, &window_samples)) {
 *       errno = EOVERFLOW;
 *       return NULL;  // overflow detected
 *   }
 *   buffer = malloc(window_samples * sizeof(float));  // safe
 */
static inline int cortex_mul_size_overflow(size_t a, size_t b, size_t *result) {
    /* Use compiler builtins when available for optimal performance.
     * Must carefully guard __has_builtin to avoid breaking GCC preprocessor. */
#if defined(__GNUC__) && !defined(__clang__)
    /* GCC 5.1+ has __builtin_mul_overflow */
    #if __GNUC__ > 5 || (__GNUC__ == 5 && __GNUC_MINOR__ >= 1)
        return __builtin_mul_overflow(a, b, result);
    #else
        /* Older GCC: use portable fallback */
        if (a > 0 && b > 0 && a > SIZE_MAX / b) {
            return 1;  /* overflow would occur */
        }
        *result = a * b;
        return 0;  /* safe */
    #endif
#elif defined(__clang__)
    /* Clang: check if builtin is available using __has_builtin */
    #if defined(__has_builtin)
        #if __has_builtin(__builtin_mul_overflow)
            return __builtin_mul_overflow(a, b, result);
        #else
            /* Clang without builtin: use portable fallback */
            if (a > 0 && b > 0 && a > SIZE_MAX / b) {
                return 1;
            }
            *result = a * b;
            return 0;
        #endif
    #else
        /* Old Clang without __has_builtin: assume builtin exists (Clang 3.4+) */
        return __builtin_mul_overflow(a, b, result);
    #endif
#else
    /* Other compilers (MSVC, etc.): portable fallback */
    if (a > 0 && b > 0 && a > SIZE_MAX / b) {
        return 1;  /* overflow would occur */
    }
    *result = a * b;
    return 0;  /* safe */
#endif
}

#endif /* CORTEX_HARNESS_UTIL_H */




