/*
 * x86@loopback adapter - Phase 1 minimal adapter
 *
 * Runs kernels on local x86 host, communicating via stdin/stdout.
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
#include "cortex_protocol.h"

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

/* Send HELLO frame advertising noop kernel */
static int send_hello(cortex_transport_t *transport, uint32_t boot_id)
{
    /* Build HELLO payload */
    uint8_t payload[sizeof(cortex_wire_hello_t) + 32];  /* header + 1 kernel name */

    /* cortex_wire_hello_t fields (little-endian) */
    cortex_write_u32_le(payload + 0, boot_id);
    memset(payload + 4, 0, 32);  /* adapter_name[32] */
    snprintf((char *)(payload + 4), 32, "x86@loopback");
    payload[36] = 1;  /* adapter_abi_version */
    payload[37] = 1;  /* num_kernels */
    cortex_write_u16_le(payload + 38, 0);  /* reserved */
    cortex_write_u32_le(payload + 40, 1024);  /* max_window_samples (arbitrary) */
    cortex_write_u32_le(payload + 44, 64);    /* max_channels */

    /* Kernel name: "noop@f32" */
    memset(payload + sizeof(cortex_wire_hello_t), 0, 32);
    snprintf((char *)(payload + sizeof(cortex_wire_hello_t)), 32, "noop@f32");

    return cortex_protocol_send_frame(transport, CORTEX_FRAME_HELLO, payload, sizeof(payload));
}

/* Receive CONFIG frame */
static int recv_config(
    cortex_transport_t *transport,
    uint32_t *out_session_id,
    uint32_t *out_sample_rate_hz,
    uint32_t *out_window_samples,
    uint32_t *out_hop_samples,
    uint32_t *out_channels,
    char *out_plugin_name,
    char *out_plugin_params
)
{
    uint8_t frame_buf[CORTEX_MAX_SINGLE_FRAME];
    cortex_frame_type_t frame_type;
    size_t payload_len;

    int ret = cortex_protocol_recv_frame(
        transport,
        &frame_type,
        frame_buf,
        sizeof(frame_buf),
        &payload_len,
        CORTEX_HANDSHAKE_TIMEOUT_MS
    );

    if (ret < 0) {
        return ret;
    }

    if (frame_type != CORTEX_FRAME_CONFIG) {
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    if (payload_len < sizeof(cortex_wire_config_t)) {
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    /* Parse CONFIG payload (convert from little-endian) */
    *out_session_id = cortex_read_u32_le(frame_buf + 0);
    *out_sample_rate_hz = cortex_read_u32_le(frame_buf + 4);
    *out_window_samples = cortex_read_u32_le(frame_buf + 8);
    *out_hop_samples = cortex_read_u32_le(frame_buf + 12);
    *out_channels = cortex_read_u32_le(frame_buf + 16);

    memcpy(out_plugin_name, frame_buf + 20, 32);
    out_plugin_name[31] = '\0';  /* Ensure null termination */

    memcpy(out_plugin_params, frame_buf + 52, 256);
    out_plugin_params[255] = '\0';  /* Ensure null termination */

    /* Calibration state ignored for noop */

    return 0;
}

/* Send ACK frame */
static int send_ack(cortex_transport_t *transport)
{
    uint8_t payload[4];
    cortex_write_u32_le(payload, 0);  /* ack_type = 0 (CONFIG) */

    return cortex_protocol_send_frame(transport, CORTEX_FRAME_ACK, payload, sizeof(payload));
}

/* Send RESULT frame */
static int send_result(
    cortex_transport_t *transport,
    uint32_t session_id,
    uint32_t sequence,
    uint64_t tin,
    uint64_t tstart,
    uint64_t tend,
    uint64_t tfirst_tx,
    uint64_t tlast_tx,
    const float *output_samples,
    uint32_t output_length,
    uint32_t output_channels
)
{
    size_t output_bytes = output_length * output_channels * sizeof(float);
    size_t payload_len = sizeof(cortex_wire_result_t) + output_bytes;

    uint8_t *payload = (uint8_t *)malloc(payload_len);
    if (!payload) {
        return -1;
    }

    /* Build RESULT header (little-endian) */
    cortex_write_u32_le(payload + 0, session_id);
    cortex_write_u32_le(payload + 4, sequence);
    cortex_write_u64_le(payload + 8, tin);
    cortex_write_u64_le(payload + 16, tstart);
    cortex_write_u64_le(payload + 24, tend);
    cortex_write_u64_le(payload + 32, tfirst_tx);
    cortex_write_u64_le(payload + 40, tlast_tx);
    cortex_write_u32_le(payload + 48, output_length);
    cortex_write_u32_le(payload + 52, output_channels);

    /* Convert output samples to little-endian */
    uint8_t *sample_buf = payload + sizeof(cortex_wire_result_t);
    for (size_t i = 0; i < output_length * output_channels; i++) {
        cortex_write_f32_le(sample_buf + (i * sizeof(float)), output_samples[i]);
    }

    int ret = cortex_protocol_send_frame(transport, CORTEX_FRAME_RESULT, payload, payload_len);

    free(payload);
    return ret;
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
    /* Construct library path: primitives/kernels/v1/{plugin_name}/lib{base}.dylib */
    /* plugin_name format: "car@f32" → libcar.dylib */

    char lib_name[64];
    const char *at_sign = strchr(plugin_name, '@');
    if (at_sign) {
        size_t base_len = (size_t)(at_sign - plugin_name);
        if (base_len >= sizeof(lib_name) - 3) {
            fprintf(stderr, "Plugin name too long: %s\n", plugin_name);
            return -1;
        }
        memcpy(lib_name, plugin_name, base_len);
        lib_name[base_len] = '\0';
    } else {
        snprintf(lib_name, sizeof(lib_name), "%s", plugin_name);
    }

    char lib_path[512];
#ifdef __APPLE__
    snprintf(lib_path, sizeof(lib_path),
             "primitives/kernels/v1/%s/lib%s.dylib",
             plugin_name, lib_name);
#else
    snprintf(lib_path, sizeof(lib_path),
             "primitives/kernels/v1/%s/lib%s.so",
             plugin_name, lib_name);
#endif

    /* Load library */
    fprintf(stderr, "[DEBUG] Loading kernel from: %s\n", lib_path);
    void *dl = dlopen(lib_path, RTLD_NOW | RTLD_LOCAL);
    if (!dl) {
        fprintf(stderr, "dlopen failed: %s\n", dlerror());
        return -1;
    }
    fprintf(stderr, "[DEBUG] Kernel library loaded successfully\n");

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
    fprintf(stderr, "[DEBUG] Detected kernel ABI version: %u\n", kernel_abi_version);

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

    fprintf(stderr, "[DEBUG] Calling cortex_init() with config: abi=%u, window=%u, channels=%u\n",
            config.abi_version, config.window_length_samples, config.channels);
    cortex_init_result_t result = init_fn(&config);
    if (!result.handle) {
        fprintf(stderr, "[ERROR] Kernel init failed (returned NULL handle)\n");
        dlclose(dl);
        return -1;
    }
    fprintf(stderr, "[DEBUG] Kernel init succeeded, handle=%p, output_channels=%u\n",
            result.handle, result.output_channels);

    void *kernel_handle = result.handle;

    /* Populate output */
    out_plugin->dl_handle = dl;
    out_plugin->init = init_fn;
    out_plugin->process = process_fn;
    out_plugin->teardown = teardown_fn;
    out_plugin->kernel_handle = kernel_handle;

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
int main(void)
{
    uint32_t boot_id = generate_boot_id();
    uint32_t session_id = 0;
    uint32_t sequence = 0;

    /* Create transport from stdin/stdout */
    cortex_transport_t transport = {
        .ctx = NULL,  /* Will be set by mock transport */
        .send = NULL,
        .recv = NULL,
        .close = NULL,
        .get_timestamp_ns = get_timestamp_ns
    };

    /* Initialize mock transport with stdin/stdout */
    cortex_transport_t *tp = cortex_transport_mock_create_from_fds(STDIN_FILENO, STDOUT_FILENO);
    if (!tp) {
        fprintf(stderr, "Failed to create transport\n");
        return 1;
    }

    transport = *tp;  /* Copy transport */

    /* 1. Send HELLO */
    if (send_hello(&transport, boot_id) < 0) {
        fprintf(stderr, "Failed to send HELLO\n");
        return 1;
    }

    /* 2. Receive CONFIG */
    uint32_t sample_rate_hz, window_samples, hop_samples, channels;
    char plugin_name[32], plugin_params[256];

    if (recv_config(&transport, &session_id, &sample_rate_hz, &window_samples,
                    &hop_samples, &channels, plugin_name, plugin_params) < 0) {
        fprintf(stderr, "Failed to receive CONFIG\n");
        return 1;
    }

    /* 3. Load kernel plugin */
    kernel_plugin_t kernel_plugin = {0};
    if (load_kernel_plugin(plugin_name, sample_rate_hz, window_samples, hop_samples,
                           channels, plugin_params, NULL, 0, &kernel_plugin) < 0) {
        fprintf(stderr, "Failed to load kernel: %s\n", plugin_name);
        return 1;
    }

    /* 4. Send ACK (kernel ready) */
    if (send_ack(&transport) < 0) {
        fprintf(stderr, "Failed to send ACK\n");
        unload_kernel_plugin(&kernel_plugin);
        return 1;
    }

    /* 4. Window loop */
    float *window_buf = (float *)malloc(window_samples * channels * sizeof(float));
    float *output_buf = (float *)malloc(window_samples * channels * sizeof(float));

    if (!window_buf || !output_buf) {
        fprintf(stderr, "Failed to allocate window buffers\n");
        return 1;
    }

    while (1) {
        /* Receive chunked WINDOW */
        uint32_t received_window_samples = 0;
        uint32_t received_channels = 0;

        int ret = cortex_protocol_recv_window_chunked(
            &transport,
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

        /* Debug: Check first few input samples */
        fprintf(stderr, "Adapter: First 5 input samples: %.2f %.2f %.2f %.2f %.2f\n",
                window_buf[0], window_buf[1], window_buf[2], window_buf[3], window_buf[4]);

        /* Debug: Check pointers before calling process */
        fprintf(stderr, "[DEBUG] Calling process: handle=%p, input=%p, output=%p\n",
                kernel_plugin.kernel_handle, (void*)window_buf, (void*)output_buf);

        /* Process window with loaded kernel */
        uint64_t tstart = get_timestamp_ns();
        kernel_plugin.process(kernel_plugin.kernel_handle, window_buf, output_buf);
        uint64_t tend = get_timestamp_ns();

        /* Debug: Check first few output samples */
        fprintf(stderr, "Adapter: First 5 output samples: %.2f %.2f %.2f %.2f %.2f\n",
                output_buf[0], output_buf[1], output_buf[2], output_buf[3], output_buf[4]);

        /* Send RESULT */
        uint64_t tfirst_tx = get_timestamp_ns();
        ret = send_result(
            &transport,
            session_id,
            sequence,
            tin,
            tstart,
            tend,
            tfirst_tx,
            tfirst_tx,  /* tlast_tx = tfirst_tx for now (approximate) */
            output_buf,
            window_samples,
            channels
        );
        uint64_t tlast_tx = get_timestamp_ns();

        (void)tlast_tx;  /* TODO: Update send_result to capture actual tlast_tx */

        if (ret < 0) {
            fprintf(stderr, "Failed to send RESULT\n");
            break;
        }

        sequence++;
    }

    free(window_buf);
    free(output_buf);
    unload_kernel_plugin(&kernel_plugin);
    transport.close(transport.ctx);
    free(tp);

    return 0;
}
