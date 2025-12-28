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

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>

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

/* Noop kernel: identity function */
static void noop_process(
    const float *input,
    uint32_t window_samples,
    uint32_t channels,
    float *output
)
{
    size_t total_samples = window_samples * channels;
    memcpy(output, input, total_samples * sizeof(float));
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

    /* Validate kernel is noop */
    if (strcmp(plugin_name, "noop@f32") != 0) {
        fprintf(stderr, "Unsupported kernel: %s\n", plugin_name);
        return 1;
    }

    /* 3. Send ACK */
    if (send_ack(&transport) < 0) {
        fprintf(stderr, "Failed to send ACK\n");
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

        /* Process window with noop kernel */
        uint64_t tstart = get_timestamp_ns();
        noop_process(window_buf, window_samples, channels, output_buf);
        uint64_t tend = get_timestamp_ns();

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
    transport.close(transport.ctx);

    return 0;
}
