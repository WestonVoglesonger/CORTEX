/* Plugin loader utilities (dlopen/dlsym wrappers) */

#ifndef CORTEX_HARNESS_LOADER_H
#define CORTEX_HARNESS_LOADER_H

#include <stddef.h>
#include <stdint.h>
#include "cortex_plugin.h"

/*
 * Plugin API structure
 * Contains function pointers loaded from shared library via dlsym.
 *
 * ABI v3 extension: calibrate function pointer is optional (NULL for v2 kernels).
 * Loader detects calibration support via dlsym("cortex_calibrate").
 */
typedef struct cortex_plugin_api {
    cortex_init_result_t (*init)(const cortex_plugin_config_t *config);
    void (*process)(void *handle, const void *input, void *output);
    void (*teardown)(void *handle);
    cortex_calibration_result_t (*calibrate)(const cortex_plugin_config_t *config,
                                             const void *calibration_data,
                                             uint32_t num_windows);  /* ABI v3+, NULL if not supported */
    uint32_t capabilities;  /* Capability flags from cortex_init_result_t (v3+), 0 for v2 kernels */
} cortex_plugin_api_t;

typedef struct cortex_loaded_plugin {
    void *so_handle;
    cortex_plugin_api_t api;
} cortex_loaded_plugin_t;

/* Build a platform-specific plugin path from spec_uri (e.g., "primitives/kernels/v1/car@f32" → "primitives/kernels/v1/car@f32/libcar.dylib"). */
int cortex_plugin_build_path(const char *spec_uri, char *out_path, size_t out_sz);

/* Load a plugin shared library into memory and resolve the required symbols. */
int cortex_plugin_load(const char *path, cortex_loaded_plugin_t *out);

/* Unload a plugin library. */
void cortex_plugin_unload(cortex_loaded_plugin_t *p);

#endif /* CORTEX_HARNESS_LOADER_H */




