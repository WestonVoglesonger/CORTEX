/*
 * CORTEX Kernel Parameter Accessor API
 *
 * Provides a generic, type-safe interface for kernels to extract runtime
 * parameters from simple key-value format strings passed by the harness.
 *
 * Design principles:
 *  - Zero coupling: accessor library knows nothing about specific kernels
 *  - Type safety: typed functions with compile-time checking
 *  - Default values: kernels always get valid values (fallback on missing)
 *  - Error tolerance: graceful handling of malformed input
 *  - No heap allocation in accessor functions (stack only)
 *  - No external dependencies (pure C11 + standard library)
 *
 * Input format (from YAML params):
 *   "key1: value1\nkey2: value2\n"
 *   or
 *   "key1=value1,key2=value2"
 *
 * Usage example (in kernel cortex_init):
 *   const char *params_str = (const char*)config->kernel_params;
 *   double f0_hz = cortex_param_float(params_str, "f0_hz", 60.0);
 *   int order = cortex_param_int(params_str, "order", 129);
 *   const char *window = cortex_param_string(params_str, "window", "hamming");
 */

#ifndef CORTEX_PARAMS_ACCESSOR_H
#define CORTEX_PARAMS_ACCESSOR_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stddef.h>

/*
 * Get floating-point parameter from params string.
 * Returns default_value if key not found or value not parseable as double.
 *
 * Thread-safe: does not modify input string.
 * No heap allocation: uses stack only.
 */
double cortex_param_float(const char *params,
                          const char *key,
                          double default_value);

/*
 * Get integer parameter from params string.
 * Returns default_value if key not found or value not parseable as int64.
 *
 * Thread-safe: does not modify input string.
 * No heap allocation: uses stack only.
 */
int64_t cortex_param_int(const char *params,
                         const char *key,
                         int64_t default_value);

/*
 * Get string parameter from params string.
 * Copies value to user-provided buffer (up to buf_size bytes).
 * Returns pointer to buffer on success, default_value on failure.
 *
 * Thread-safe: does not modify input string.
 * No heap allocation: user provides buffer.
 *
 * Example:
 *   char window[32];
 *   cortex_param_string(params, "window", window, sizeof(window), "hamming");
 */
const char* cortex_param_string(const char *params,
                                const char *key,
                                char *buf,
                                size_t buf_size,
                                const char *default_value);

/*
 * Get boolean parameter (true/false, yes/no, 1/0).
 * Returns default_value if key not found or value not parseable as bool.
 *
 * Thread-safe: does not modify input string.
 * No heap allocation: uses stack only.
 */
int cortex_param_bool(const char *params,
                      const char *key,
                      int default_value);

#ifdef __cplusplus
}
#endif

#endif /* CORTEX_PARAMS_ACCESSOR_H */
