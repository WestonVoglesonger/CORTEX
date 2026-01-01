/*
 * native adapter - Phase 1 minimal adapter
 *
 * Runs kernels on local host (native architecture), communicating via stdin/stdout.
 * Implements handshake and window processing for loopback testing.
 *
 * Protocol:
 *   1. Send HELLO (advertise noop kernel)
 *   2. Receive CONFIG (kernel selection)
 *   3. Send ACK (ready)
 *   4. Loop: Receive WINDOW → Process → Send RESULT
 */

#define _POSIX_C_SOURCE 200809L

#include "cortex_transport.h"
#include "cortex_adapter_transport.h"
#include "cortex_protocol.h"
#include "cortex_adapter_helpers.h"

#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>

/* Kernel plugin API (from cortex_plugin.h) */
typedef struct cortex_plugin_config {
    uint32_t abi_version;
    uint32_t struct_size;
    uint32_t sample_rate_hz;
    uint32_t window_length_samples;
    uint32_t hop_samples;
    uint32_t channels;
    uint32_t dtype;
    uint8_t  allow_in_place;
    uint8_t  reserved0[3];
    const void *kernel_params;
    uint32_t   kernel_params_size;
    const void *calibration_state;
    uint32_t calibration_state_size;
} cortex_plugin_config_t;

typedef struct {
    void *handle;
    uint32_t output_window_length_samples;
    uint32_t output_channels;
    uint32_t capabilities;
} cortex_init_result_t;

typedef cortex_init_result_t (*cortex_init_fn)(const cortex_plugin_config_t *config);
typedef void (*cortex_process_fn)(void *handle, const void *input, void *output);
typedef void (*cortex_teardown_fn)(void *handle);

/* Calibrate function type (for v3 detection only, not stored) */
typedef void* (*cortex_calibrate_fn)(const cortex_plugin_config_t *, const void *, uint32_t);

/* Loaded kernel state */
typedef struct {
    void *dl_handle;             /* dlopen handle */
    cortex_init_fn init;
    cortex_process_fn process;
    cortex_teardown_fn teardown;
    void *kernel_handle;         /* Kernel instance from init() */
    uint32_t output_window_length_samples;  /* Actual output shape */
    uint32_t output_channels;
} kernel_plugin_t;

/* Generate random boot ID */
static uint32_t generate_boot_id(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec ^ ts.tv_nsec);
}

/* Get timestamp in nanoseconds (CLOCK_MONOTONIC) */
static uint64_t get_timestamp_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/* Load kernel plugin via dlopen */
static int load_kernel_plugin(
    const char *plugin_name,
    uint32_t sample_rate_hz,
    uint32_t window_samples,
    uint32_t hop_samples,
    uint32_t channels,
    const char *plugin_params,
    const void *calib_state,
    size_t calib_state_size,
    kernel_plugin_t *out_plugin
)
{
    /* plugin_name is now spec_uri: "primitives/kernels/v1/noop@f32" */
    /* Extract kernel@dtype from path (last component after final slash) */
    const char *last_slash = strrchr(plugin_name, '/');
    const char *kernel_at_dtype = last_slash ? (last_slash + 1) : plugin_name;

    /* Extract base kernel name (before '@') */
    char lib_name[64];
    const char *at_sign = strchr(kernel_at_dtype, '@');
    if (at_sign) {
        size_t base_len = (size_t)(at_sign - kernel_at_dtype);
        if (base_len >= sizeof(lib_name)) {
            fprintf(stderr, "Kernel name too long: %s\n", kernel_at_dtype);
            return -1;
        }
        memcpy(lib_name, kernel_at_dtype, base_len);
        lib_name[base_len] = '\0';
    } else {
        snprintf(lib_name, sizeof(lib_name), "%s", kernel_at_dtype);
    }

    /* Construct library path using spec_uri */
    char lib_path[512];
#ifdef __APPLE__
    snprintf(lib_path, sizeof(lib_path),
             "%s/lib%s.dylib", plugin_name, lib_name);
#else
    snprintf(lib_path, sizeof(lib_path),
             "%s/lib%s.so", plugin_name, lib_name);
#endif

    /* Convert to absolute path (adapter working directory = harness working directory) */
    char abs_lib_path[1024];
    if (lib_path[0] != '/') {
        char cwd[512];
        if (getcwd(cwd, sizeof(cwd)) == NULL) {
            fprintf(stderr, "getcwd failed\n");
            return -1;
        }
        snprintf(abs_lib_path, sizeof(abs_lib_path), "%s/%s", cwd, lib_path);
    } else {
        snprintf(abs_lib_path, sizeof(abs_lib_path), "%s", lib_path);
    }

    /* Load library */
    void *dl = dlopen(abs_lib_path, RTLD_NOW | RTLD_LOCAL);
    if (!dl) {
        fprintf(stderr, "dlopen failed: %s\n", dlerror());
        fprintf(stderr, "  Tried: %s\n", abs_lib_path);
        return -1;
    }

    /* Load symbols */
    cortex_init_fn init_fn = (cortex_init_fn)dlsym(dl, "cortex_init");
    cortex_process_fn process_fn = (cortex_process_fn)dlsym(dl, "cortex_process");
    cortex_teardown_fn teardown_fn = (cortex_teardown_fn)dlsym(dl, "cortex_teardown");
    cortex_calibrate_fn calibrate_fn = (cortex_calibrate_fn)dlsym(dl, "cortex_calibrate");

    if (!init_fn || !process_fn || !teardown_fn) {
        fprintf(stderr, "Failed to load kernel symbols: %s\n", dlerror());
        dlclose(dl);
        return -1;
    }

    /* Detect kernel ABI version */
    uint32_t kernel_abi_version = (calibrate_fn != NULL) ? 3 : 2;

    /* Initialize kernel */
    cortex_plugin_config_t config = {
        .abi_version = kernel_abi_version,
        .struct_size = sizeof(cortex_plugin_config_t),
        .sample_rate_hz = sample_rate_hz,
        .window_length_samples = window_samples,
        .hop_samples = hop_samples,
        .channels = channels,
        .dtype = 1,  /* CORTEX_DTYPE_FLOAT32 */
        .allow_in_place = 0,
        .kernel_params = plugin_params,
        .kernel_params_size = (uint32_t)strlen(plugin_params),
        .calibration_state = calib_state,
        .calibration_state_size = (uint32_t)calib_state_size
    };

    cortex_init_result_t result = init_fn(&config);
    if (!result.handle) {
        fprintf(stderr, "[ERROR] Kernel init failed (returned NULL handle)\n");
        dlclose(dl);
        return -1;
    }

    void *kernel_handle = result.handle;

    /* Populate output */
    out_plugin->dl_handle = dl;
    out_plugin->init = init_fn;
    out_plugin->process = process_fn;
    out_plugin->teardown = teardown_fn;
    out_plugin->kernel_handle = kernel_handle;
    out_plugin->output_window_length_samples = result.output_window_length_samples;
    out_plugin->output_channels = result.output_channels;

    return 0;
}

/* Unload kernel plugin */
static void unload_kernel_plugin(kernel_plugin_t *plugin)
{
    if (!plugin) return;

    if (plugin->teardown && plugin->kernel_handle) {
        plugin->teardown(plugin->kernel_handle);
    }

    if (plugin->dl_handle) {
        dlclose(plugin->dl_handle);
    }

    memset(plugin, 0, sizeof(*plugin));
}

/* Main adapter loop */
int main(int argc, char **argv)
{
    uint32_t boot_id = generate_boot_id();
    uint32_t session_id = 0;
    uint32_t sequence = 0;

    /* Parse transport config from argv[1] (defaults to "local://") */
    const char *config_uri = (argc > 1) ? argv[1] : "local://";

    /* Create transport from URI configuration */
    cortex_transport_t *tp = cortex_adapter_transport_create(config_uri);
    if (!tp) {
        fprintf(stderr, "Failed to create transport from URI: %s\n", config_uri);
        return 1;
    }

    /* 1. Send HELLO */
    if (cortex_adapter_send_hello(tp, boot_id, "x86@loopback", "noop@f32", 1024, 64) < 0) {
        fprintf(stderr, "Failed to send HELLO\n");
        cortex_transport_destroy(tp);
        return 1;
    }

    /* 2. Receive CONFIG */
    uint32_t sample_rate_hz, window_samples, hop_samples, channels;
    char plugin_name[64], plugin_params[256];
    void *calibration_state = NULL;
    uint32_t calibration_state_size = 0;

    if (cortex_adapter_recv_config(tp, &session_id, &sample_rate_hz, &window_samples,
                                    &hop_samples, &channels, plugin_name, plugin_params,
                                    &calibration_state, &calibration_state_size) < 0) {
        fprintf(stderr, "Failed to receive CONFIG\n");
        cortex_transport_destroy(tp);
        return 1;
    }

    /* 3. Load kernel plugin */
    kernel_plugin_t kernel_plugin = {0};
    if (load_kernel_plugin(plugin_name, sample_rate_hz, window_samples, hop_samples,
                           channels, plugin_params, calibration_state, calibration_state_size, &kernel_plugin) < 0) {
        fprintf(stderr, "Failed to load kernel: %s\n", plugin_name);
        free(calibration_state);  /* Free calibration state on error */
        cortex_transport_destroy(tp);
        return 1;
    }

    /* 4. Send ACK (kernel ready, with output dimensions) */
    /* Send actual output dimensions from kernel init result */
    if (cortex_adapter_send_ack_with_dims(tp,
                                         kernel_plugin.output_window_length_samples,
                                         kernel_plugin.output_channels) < 0) {
        fprintf(stderr, "Failed to send ACK\n");
        free(calibration_state);
        unload_kernel_plugin(&kernel_plugin);
        cortex_transport_destroy(tp);
        return 1;
    }

    /* 4. Window loop */
    float *window_buf = (float *)malloc(window_samples * channels * sizeof(float));

    /* Allocate output buffer based on kernel's actual output shape */
    size_t output_samples = kernel_plugin.output_window_length_samples * kernel_plugin.output_channels;
    float *output_buf = (float *)malloc(output_samples * sizeof(float));


    if (!window_buf || !output_buf) {
        fprintf(stderr, "Failed to allocate window buffers\n");
        free(window_buf);
        free(output_buf);
        free(calibration_state);
        unload_kernel_plugin(&kernel_plugin);
        cortex_transport_destroy(tp);
        return 1;
    }

    while (1) {
        /* Receive chunked WINDOW */
        uint32_t received_window_samples = 0;
        uint32_t received_channels = 0;

        int ret = cortex_protocol_recv_window_chunked(
            tp,
            sequence,
            window_buf,
            window_samples * channels * sizeof(float),
            &received_window_samples,
            &received_channels,
            CORTEX_WINDOW_TIMEOUT_MS
        );

        if (ret < 0) {
            /* Timeout or error - exit gracefully */
            break;
        }

        /* Set tin AFTER reassembly complete */
        uint64_t tin = get_timestamp_ns();

        /* Process window with loaded kernel */
        uint64_t tstart = get_timestamp_ns();
        kernel_plugin.process(kernel_plugin.kernel_handle, window_buf, output_buf);
        uint64_t tend = get_timestamp_ns();

        /* Send RESULT with actual output shape */
        uint64_t tfirst_tx = get_timestamp_ns();
        ret = cortex_adapter_send_result(
            tp,
            session_id,
            sequence,
            tin,
            tstart,
            tend,
            tfirst_tx,
            tfirst_tx,  /* tlast_tx = tfirst_tx for now (approximate) */
            output_buf,
            kernel_plugin.output_window_length_samples,
            kernel_plugin.output_channels
        );
        uint64_t tlast_tx = get_timestamp_ns();

        (void)tlast_tx;  /* TODO: Update cortex_adapter_send_result to capture actual tlast_tx */

        if (ret < 0) {
            fprintf(stderr, "Failed to send RESULT\n");
            break;
        }

        sequence++;
    }

    free(window_buf);
    free(output_buf);
    free(calibration_state);  /* Free calibration state if it was allocated */
    unload_kernel_plugin(&kernel_plugin);
    cortex_transport_destroy(tp);

    return 0;
}
