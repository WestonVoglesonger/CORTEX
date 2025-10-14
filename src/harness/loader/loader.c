#include "loader.h"

#include <stdio.h>
#include <string.h>
#include <dlfcn.h>

#include "../scheduler/scheduler.h"

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

int cortex_plugin_build_path(const char *name, char *out_path, size_t out_sz) {
    if (!name || !out_path || out_sz == 0) return -1;
    char clean[128];
    sanitize_name(name, clean, sizeof(clean));
    
    /* Platform-specific extension: .dylib on macOS, .so on Linux */
#ifdef __APPLE__
    snprintf(out_path, out_sz, "plugins/lib%s.dylib", clean);
#else
    snprintf(out_path, out_sz, "plugins/lib%s.so", clean);
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
    out->api.get_info = dlsym(handle, "cortex_get_info");
    out->api.init = dlsym(handle, "cortex_init");
    out->api.process = dlsym(handle, "cortex_process");
    out->api.teardown = dlsym(handle, "cortex_teardown");
    const char *err = dlerror();
    if (err) {
        fprintf(stderr, "dlsym failed: %s\n", err);
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


