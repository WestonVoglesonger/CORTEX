#include "cortex_loader.h"

#include <stdio.h>
#include <string.h>
#include <dlfcn.h>

static int validate_plugin_name(const char *name) {
    if (!name) return -1;
    /* Reject names containing path traversal sequences */
    if (strstr(name, "..") != NULL) return -1;
    if (strchr(name, '/') != NULL) return -1;
    if (strchr(name, '\\') != NULL) return -1;
    if (strchr(name, ':') != NULL) return -1;  /* Windows drive letters */
    return 0;
}

static void sanitize_name(const char *in, char *out, size_t out_sz) {
    if (!in || !out || out_sz == 0) return;
    /* Copy while stripping any quote characters anywhere in the string. */
    size_t j = 0;
    for (size_t i = 0; in[i] != '\0' && j + 1 < out_sz; i++) {
        if (in[i] == '"' || in[i] == '\'') continue;
        out[j++] = in[i];
    }
    out[j] = '\0';
}

int cortex_plugin_build_path(const char *spec_uri, char *out_path, size_t out_sz) {
    if (!spec_uri || !out_path || out_sz == 0) return -1;

    /* spec_uri is either:
     *   New layout: "primitives/kernels/v1/car/f32" (dtype subdirectory)
     *   Legacy:     "primitives/kernels/v1/car@f32" (flat directory)
     *
     * Extract kernel name: for new layout, it's the parent directory name.
     * For legacy, it's the last component before '@'.
     * The library lives in the spec_uri directory itself. */
    char clean[256];
    sanitize_name(spec_uri, clean, sizeof(clean));

    /* Find the last path component */
    const char *last_slash = strrchr(spec_uri, '/');
    const char *last_component = last_slash ? last_slash + 1 : spec_uri;

    char kernel_name[64];

    if (strchr(last_component, '@')) {
        /* Legacy format: "car@f32" — extract name before '@' */
        size_t i = 0;
        while (last_component[i] != '\0' && last_component[i] != '@' && i < sizeof(kernel_name)-1) {
            kernel_name[i] = last_component[i];
            i++;
        }
        kernel_name[i] = '\0';
    } else {
        /* New format: last component is dtype (e.g., "f32"), kernel name is parent */
        /* Find second-to-last slash */
        char uri_copy[256];
        strncpy(uri_copy, spec_uri, sizeof(uri_copy) - 1);
        uri_copy[sizeof(uri_copy) - 1] = '\0';

        /* Trim trailing slash if present */
        size_t len = strlen(uri_copy);
        if (len > 0 && uri_copy[len - 1] == '/') uri_copy[--len] = '\0';

        /* Remove last component (dtype) */
        char *slash = strrchr(uri_copy, '/');
        if (slash) {
            *slash = '\0';
            /* Now find the kernel name (last component of remaining path) */
            char *name_start = strrchr(uri_copy, '/');
            name_start = name_start ? name_start + 1 : uri_copy;
            strncpy(kernel_name, name_start, sizeof(kernel_name) - 1);
            kernel_name[sizeof(kernel_name) - 1] = '\0';
        } else {
            /* Fallback: use the dtype component as name (shouldn't happen) */
            strncpy(kernel_name, last_component, sizeof(kernel_name) - 1);
            kernel_name[sizeof(kernel_name) - 1] = '\0';
        }
    }

    /* Validate kernel name for security (prevent path traversal) */
    if (validate_plugin_name(kernel_name) < 0) {
        return -1;
    }

    /* Build full path: {spec_uri}/lib{name}.{ext} */
#ifdef __APPLE__
    snprintf(out_path, out_sz, "%s/lib%s.dylib", spec_uri, kernel_name);
#else
    snprintf(out_path, out_sz, "%s/lib%s.so", spec_uri, kernel_name);
#endif

    return 0;
}

int cortex_plugin_load(const char *path, cortex_loaded_plugin_t *out) {
    if (!path || !out) return -1;
    memset(out, 0, sizeof(*out));
    void *handle = dlopen(path, RTLD_LAZY);
    if (!handle) {
        fprintf(stderr, "[loader] dlopen failed: %s\n", dlerror());
        return -1;
    }

    /* Load required v2/v3 functions */
    dlerror();  /* Clear any previous error */
    out->api.init = dlsym(handle, "cortex_init");
    out->api.process = dlsym(handle, "cortex_process");
    out->api.teardown = dlsym(handle, "cortex_teardown");
    const char *err = dlerror();
    if (err || !out->api.init || !out->api.process || !out->api.teardown) {
        fprintf(stderr, "[loader] dlsym failed for required symbols: %s\n",
                err ? err : "missing cortex_init/process/teardown");
        dlclose(handle);
        return -1;
    }

    /* Attempt to load optional v3 calibration function */
    dlerror();  /* Clear any previous error */
    out->api.calibrate = dlsym(handle, "cortex_calibrate");
    err = dlerror();
    if (err || !out->api.calibrate) {
        /* Not an error - kernel is v2 compatible (no calibration support) */
        out->api.calibrate = NULL;
        out->api.capabilities = 0;
        fprintf(stderr, "[loader] Plugin is ABI v2 compatible (no calibration support)\n");
    } else {
        /* v3 trainable kernel detected */
        fprintf(stderr, "[loader] Plugin is ABI v3 trainable (calibration supported)\n");
        /* Capabilities will be set after cortex_init() returns */
    }

    out->so_handle = handle;
    return 0;
}

void cortex_plugin_unload(cortex_loaded_plugin_t *p) {
    if (!p) return;
    if (p->so_handle) dlclose(p->so_handle);
    memset(p, 0, sizeof(*p));
}


