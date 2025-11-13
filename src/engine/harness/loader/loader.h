/* Plugin loader utilities (dlopen/dlsym wrappers) */

#ifndef CORTEX_HARNESS_LOADER_H
#define CORTEX_HARNESS_LOADER_H

#include <stddef.h>
#include <stdint.h>

#include "../scheduler/scheduler.h"

typedef struct cortex_loaded_plugin {
    void *so_handle;
    cortex_scheduler_plugin_api_t api;
} cortex_loaded_plugin_t;

/* Build a platform-specific plugin path from spec_uri (e.g., "primitives/kernels/v1/car@f32" → "primitives/kernels/v1/car@f32/libcar.dylib"). */
int cortex_plugin_build_path(const char *spec_uri, char *out_path, size_t out_sz);

/* Load a plugin shared library into memory and resolve the required symbols. */
int cortex_plugin_load(const char *path, cortex_loaded_plugin_t *out);

/* Unload a plugin library. */
void cortex_plugin_unload(cortex_loaded_plugin_t *p);

#endif /* CORTEX_HARNESS_LOADER_H */




