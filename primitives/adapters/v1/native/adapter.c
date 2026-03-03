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
#include "cortex_wire.h"
#include "inscount.h"
#include "osnoise.h"

#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <signal.h>
#include <errno.h>
#include <stdbool.h>

/* Global shutdown flag for signal handling */
static volatile sig_atomic_t g_shutdown = 0;

/* Signal handler for graceful shutdown */
static void signal_handler(int sig)
{
    if (sig == SIGINT || sig == SIGTERM) {
        g_shutdown = 1;
    }
}

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
    size_t elem_size;            /* Element size in bytes (detected from dtype) */
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

/* Sample current CPU frequency in MHz.
 * On Linux: reads sysfs. On macOS/other: returns 0. */
static uint32_t sample_cpu_freq_mhz(void)
{
#ifdef __linux__
    FILE *f = fopen("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "r");
    if (f) {
        unsigned long freq_khz = 0;
        if (fscanf(f, "%lu", &freq_khz) == 1) {
            fclose(f);
            return (uint32_t)(freq_khz / 1000);
        }
        fclose(f);
    }
#endif
    return 0;
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
    /* plugin_name is spec_uri: "primitives/kernels/v1/noop/f32" (new) or "noop@f32" (legacy) */
    /* Extract kernel name: for new layout it's the parent of the last component */
    char lib_name[64];
    {
        /* Make a mutable copy */
        char uri_copy[256];
        strncpy(uri_copy, plugin_name, sizeof(uri_copy) - 1);
        uri_copy[sizeof(uri_copy) - 1] = '\0';

        /* Trim trailing slash */
        size_t len = strlen(uri_copy);
        if (len > 0 && uri_copy[len - 1] == '/') uri_copy[--len] = '\0';

        const char *last_slash = strrchr(uri_copy, '/');
        const char *last_component = last_slash ? last_slash + 1 : uri_copy;

        if (strchr(last_component, '@')) {
            /* Legacy: "noop@f32" → extract "noop" */
            const char *at_sign = strchr(last_component, '@');
            size_t base_len = (size_t)(at_sign - last_component);
            if (base_len >= sizeof(lib_name)) {
                fprintf(stderr, "Kernel name too long: %s\n", last_component);
                return -1;
            }
            memcpy(lib_name, last_component, base_len);
            lib_name[base_len] = '\0';
        } else {
            /* New layout: last component is dtype, parent is kernel name */
            if (last_slash) {
                *((char *)last_slash) = '\0'; /* Won't work on const, use copy */
            }
            /* Re-parse from the copy */
            char *second_slash = strrchr(uri_copy, '/');
            const char *name_start = second_slash ? second_slash + 1 : uri_copy;
            snprintf(lib_name, sizeof(lib_name), "%s", name_start);
        }
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
    /* Detect dtype from path: new layout has "/q15/" or "/q7/", legacy has "@q15" or "@q7" */
    uint32_t dtype = 1;  /* CORTEX_DTYPE_FLOAT32 default */
    if (strstr(plugin_name, "/q15") || strstr(plugin_name, "@q15")) {
        dtype = 2;  /* CORTEX_DTYPE_Q15 */
    } else if (strstr(plugin_name, "/q7") || strstr(plugin_name, "@q7")) {
        dtype = 4;  /* CORTEX_DTYPE_Q7 */
    }

    cortex_plugin_config_t config = {
        .abi_version = kernel_abi_version,
        .struct_size = sizeof(cortex_plugin_config_t),
        .sample_rate_hz = sample_rate_hz,
        .window_length_samples = window_samples,
        .hop_samples = hop_samples,
        .channels = channels,
        .dtype = dtype,
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

    /* Derive element size from detected dtype */
    size_t detected_elem_size = sizeof(float);
    if (dtype == 2) detected_elem_size = sizeof(int16_t);
    else if (dtype == 4) detected_elem_size = sizeof(int8_t);

    /* Populate output */
    out_plugin->dl_handle = dl;
    out_plugin->init = init_fn;
    out_plugin->process = process_fn;
    out_plugin->teardown = teardown_fn;
    out_plugin->kernel_handle = kernel_handle;
    out_plugin->output_window_length_samples = result.output_window_length_samples;
    out_plugin->output_channels = result.output_channels;
    out_plugin->elem_size = detected_elem_size;

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

/**
 * Run a single session: handshake + window loop + cleanup
 * Returns: 0 on normal close, -1 on error
 */
static int run_session(cortex_transport_t *tp, uint32_t boot_id)
{
    int rc = -1;
    uint32_t session_id = 0;
    uint32_t sequence = 0;
    void *calibration_state = NULL;
    float *window_buf = NULL;
    float *output_buf = NULL;
    kernel_plugin_t kernel_plugin = {0};
    int pmu_initialized = 0;
    int osnoise_initialized = 0;
    size_t elem_size = sizeof(float);  /* Updated from kernel_plugin.elem_size after load */

    /* 1. Send HELLO */
    if (cortex_adapter_send_hello(tp, boot_id, "native", "noop@f32", 1024, 64) < 0) {
        fprintf(stderr, "Failed to send HELLO\n");
        goto cleanup;
    }

    /* 2. Receive CONFIG */
    uint32_t sample_rate_hz, window_samples, hop_samples, channels;
    char plugin_name[256], plugin_params[256];
    uint32_t calibration_state_size = 0;

    if (cortex_adapter_recv_config(tp, &session_id, &sample_rate_hz, &window_samples,
                                    &hop_samples, &channels, plugin_name, plugin_params,
                                    &calibration_state, &calibration_state_size) < 0) {
        fprintf(stderr, "Failed to receive CONFIG\n");
        goto cleanup;
    }

    /* 3. Load kernel plugin */
    if (load_kernel_plugin(plugin_name, sample_rate_hz, window_samples, hop_samples,
                           channels, plugin_params, calibration_state, calibration_state_size, &kernel_plugin) < 0) {
        fprintf(stderr, "Failed to load kernel: %s\n", plugin_name);

        /* Send ERROR frame to harness */
        char error_msg[256];
        snprintf(error_msg, sizeof(error_msg), "Failed to load kernel plugin: %s", plugin_name);
        cortex_adapter_send_error(tp, CORTEX_ERROR_KERNEL_INIT_FAILED, error_msg);

        goto cleanup;
    }

    /* 4. Send ACK (kernel ready, with output dimensions) */
    /* Send actual output dimensions from kernel init result */
    if (cortex_adapter_send_ack_with_dims(tp,
                                         kernel_plugin.output_window_length_samples,
                                         kernel_plugin.output_channels) < 0) {
        fprintf(stderr, "Failed to send ACK\n");
        goto cleanup;
    }

    /* 5. Initialize PMU counters (per-thread, measured around kernel process()) */
    pmu_initialized = (cortex_inscount_init() == 0) ? 1 : 0;

    /* Initialize osnoise tracer (for device-side OS noise measurement) */
    osnoise_initialized = (cortex_osnoise_init() == 0) ? 1 : 0;

    /* 6. Allocate window buffers (dtype-aware sizing from kernel load).
     * Use calloc for overflow-safe allocation (calloc checks size_t overflow). */
    elem_size = kernel_plugin.elem_size;
    window_buf = (float *)calloc(window_samples * channels, elem_size);

    /* Allocate output buffer based on kernel's actual output shape */
    size_t output_samples = kernel_plugin.output_window_length_samples * kernel_plugin.output_channels;
    output_buf = (float *)calloc(output_samples, elem_size);

    if (!window_buf || !output_buf) {
        fprintf(stderr, "Failed to allocate window buffers\n");

        /* Send ERROR frame to harness */
        char error_msg[256];
        size_t window_buf_size = window_samples * channels * elem_size;
        snprintf(error_msg, sizeof(error_msg),
                 "Failed to allocate window buffers (window: %zu bytes, output: %zu bytes)",
                 window_buf_size, output_samples * elem_size);
        cortex_adapter_send_error(tp, CORTEX_ERROR_KERNEL_INIT_FAILED, error_msg);

        goto cleanup;
    }

    /* 6. Window processing loop */
    while (1) {
        /* Check for shutdown signal (Ctrl+C, SIGTERM) */
        if (g_shutdown) {
            fprintf(stderr, "[adapter] Shutdown requested, stopping gracefully\n");
            cortex_adapter_send_error(tp, CORTEX_ERROR_SHUTDOWN,
                                      "Adapter shutting down (signal received)");
            rc = 0;  /* Clean exit, not an error */
            goto cleanup;
        }

        /* Receive chunked WINDOW */
        int ret = cortex_protocol_recv_window_chunked(
            tp,
            sequence,
            window_buf,
            window_samples * channels * elem_size,
            CORTEX_WINDOW_TIMEOUT_MS
        );

        if (ret < 0) {
            /* Timeout or error - exit gracefully */
            break;
        }

        /* Set tin AFTER reassembly complete */
        uint64_t tin = get_timestamp_ns();

        /* Sample device-side platform state before kernel execution */
        uint32_t cpu_freq_mhz = sample_cpu_freq_mhz();
        if (osnoise_initialized) cortex_osnoise_reset();

        /* PMU inside timestamp reads — matches tstart/tend window exactly.
         * Previous ordering had inscount_start() before tstart and
         * inscount_stop_all() after tend, inflating cycle counts by the
         * cost of two clock_gettime calls + kpc read.  For fast kernels
         * (< 50 µs) this made effective_freq exceed physical CPU max. */
        cortex_pmu_counters_t pmu = {0};

        uint64_t tstart = get_timestamp_ns();
        if (pmu_initialized) cortex_inscount_start();
        kernel_plugin.process(kernel_plugin.kernel_handle, window_buf, output_buf);
        if (pmu_initialized) pmu = cortex_inscount_stop_all();
        uint64_t tend = get_timestamp_ns();

        /* Read device-side OS noise after kernel execution */
        uint64_t osnoise_ns = osnoise_initialized ? cortex_osnoise_read_ns() : 0;

        /* Send RESULT with actual output shape + PMU counters + platform state */
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
            kernel_plugin.output_channels,
            pmu.cycle_count,
            pmu.instruction_count,
            pmu.backend_stall_cycles,
            cpu_freq_mhz,
            osnoise_ns,
            elem_size
        );
        uint64_t tlast_tx = get_timestamp_ns();

        (void)tlast_tx;  /* TODO: Update cortex_adapter_send_result to capture actual tlast_tx */

        if (ret < 0) {
            fprintf(stderr, "Failed to send RESULT\n");
            break;
        }

        sequence++;
    }

    /* Normal completion */
    rc = 0;

cleanup:
    /* Cleanup - always executed regardless of error path */
    if (osnoise_initialized) {
        cortex_osnoise_teardown();
    }
    if (pmu_initialized) {
        cortex_inscount_teardown();
    }
    free(window_buf);
    free(output_buf);
    free(calibration_state);
    if (kernel_plugin.dl_handle) {
        unload_kernel_plugin(&kernel_plugin);
    }

    return rc;
}

/* Main adapter loop */
int main(int argc, char **argv)
{
    uint32_t boot_id = generate_boot_id();

    /* Install signal handlers for graceful shutdown */
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    signal(SIGPIPE, SIG_IGN);  /* Don't crash on broken pipe */

    /* Parse transport config from argv[1] (defaults to "local://") */
    const char *config_uri = (argc > 1) ? argv[1] : "local://";

    /* Validate URI length to prevent malformed input from crashing */
    if (config_uri && strlen(config_uri) > 512) {
        fprintf(stderr, "Transport URI too long (max 512 chars): %zu\n", strlen(config_uri));
        return 1;
    }

    /* Parse URI to detect transport mode */
    cortex_uri_t uri;
    if (cortex_parse_adapter_uri(config_uri, &uri) != 0) {
        fprintf(stderr, "Invalid URI: %s\n", config_uri);
        return 1;
    }

    /* Check if TCP server mode (daemon) */
    bool is_tcp_server = (strcmp(uri.scheme, "tcp") == 0 && uri.host[0] == '\0');

    if (is_tcp_server) {
        /* TCP daemon mode: accept multiple connections */
        cortex_transport_t *listener = cortex_adapter_transport_create(config_uri);
        if (!listener) {
            fprintf(stderr, "Failed to create TCP listener\n");
            return 1;
        }

        fprintf(stderr, "[adapter] TCP daemon mode active. Press Ctrl+C to exit.\n");

        /* Accept loop */
        while (!g_shutdown) {
            cortex_transport_t *conn = cortex_transport_tcp_server_accept(listener, 5000);

            if (!conn) {
                if (errno == ETIMEDOUT) {
                    continue;  /* Timeout - check shutdown flag and retry */
                }
                fprintf(stderr, "[adapter] Accept error: %d\n", errno);
                break;
            }

            fprintf(stderr, "[adapter] Connection established, running session...\n");

            int ret = run_session(conn, boot_id);
            cortex_transport_destroy(conn);

            if (ret < 0) {
                fprintf(stderr, "[adapter] Session failed, waiting for next connection...\n");
                /* Continue loop - bad session doesn't kill daemon */
            } else {
                fprintf(stderr, "[adapter] Session completed normally.\n");
            }
        }

        cortex_transport_destroy(listener);
        fprintf(stderr, "[adapter] Shutdown requested, exiting.\n");

    } else {
        /* Local/serial: single session */
        cortex_transport_t *tp = cortex_adapter_transport_create(config_uri);
        if (!tp) {
            fprintf(stderr, "Failed to create transport from URI: %s\n", config_uri);
            return 1;
        }

        int ret = run_session(tp, boot_id);
        cortex_transport_destroy(tp);

        return (ret < 0) ? 1 : 0;
    }

    return 0;
}
