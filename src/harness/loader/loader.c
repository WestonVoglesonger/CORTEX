#include "loader.h"

#include <stdio.h>
#include <string.h>
#include <dlfcn.h>

#include "../scheduler/scheduler.h"

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
    
    /* spec_uri is like "kernels/v1/car@f32" - build path to libcar.dylib in that directory */
    char clean[256];
    sanitize_name(spec_uri, clean, sizeof(clean));
    
    /* Extract kernel name from spec_uri (e.g., "car" from "kernels/v1/car@f32") */
    const char *name_start = strrchr(spec_uri, '/');
    if (!name_start) name_start = spec_uri;
    else name_start++; /* Skip the '/' */
    
    /* Trim @f32 or @dtype suffix to get just the kernel name */
    char kernel_name[64];
    size_t i = 0;
    while (name_start[i] != '\0' && name_start[i] != '@' && i < sizeof(kernel_name)-1) {
        kernel_name[i] = name_start[i];
        i++;
    }
    kernel_name[i] = '\0';
    
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
        fprintf(stderr, "dlopen failed: %s\n", dlerror());
        return -1;
    }
    dlerror();
    out->api.init = dlsym(handle, "cortex_init");
    out->api.process = dlsym(handle, "cortex_process");
    out->api.teardown = dlsym(handle, "cortex_teardown");
    const char *err = dlerror();
    if (err || !out->api.init || !out->api.process || !out->api.teardown) {
        fprintf(stderr, "dlsym failed: %s\n", err ? err : "missing required symbols");
        dlclose(handle);
        return -1;
    }
    out->so_handle = handle;
    return 0;
}

void cortex_plugin_unload(cortex_loaded_plugin_t *p) {
    if (!p) return;
    if (p->so_handle) dlclose(p->so_handle);
    memset(p, 0, sizeof(*p));
}


