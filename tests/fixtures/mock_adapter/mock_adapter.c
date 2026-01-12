/*
 * Mock Adapter for Testing
 *
 * Provides a controllable adapter for testing scheduler, device_comm, and error handling.
 * Does NOT load real kernels - implements identity function with configurable failures.
 *
 * Control via MOCK_BEHAVIOR environment variable (see mock_behaviors.h)
 */

#define _POSIX_C_SOURCE 200809L

#include "cortex_transport.h"
#include "cortex_protocol.h"
#include "cortex_wire.h"
#include "cortex_adapter_helpers.h"
#include "mock_behaviors.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <math.h>

/* Get timestamp in nanoseconds (CLOCK_MONOTONIC) */
static uint64_t get_timestamp_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/* Generate boot ID */
static uint32_t generate_boot_id(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec ^ ts.tv_nsec);
}

int main(void)
{
    /* Parse behavior from environment */
    const char *behavior_str = getenv("MOCK_BEHAVIOR");
    mock_behavior_t behavior = parse_behavior(behavior_str);

    fprintf(stderr, "[mock_adapter] Starting with behavior: %s\n",
            behavior_str ? behavior_str : "identity");

    /* Create transport from stdin/stdout (socketpair from harness) */
    cortex_transport_t *transport = cortex_transport_mock_create_from_fds(
        STDIN_FILENO, STDOUT_FILENO);
    if (!transport) {
        fprintf(stderr, "[mock_adapter] Failed to create transport\n");
        return 1;
    }

    /* Generate boot ID */
    uint32_t boot_id = generate_boot_id();

    /* Send HELLO frame */
    cortex_wire_hello_t hello = {0};
    hello.adapter_boot_id = boot_id;
    strncpy(hello.adapter_name, "mock-test-adapter", sizeof(hello.adapter_name) - 1);
    hello.adapter_abi_version = 1;
    hello.num_kernels = 1;
    hello.max_window_samples = 1024;
    hello.max_channels = 128;
    strncpy(hello.device_hostname, "mock-device", sizeof(hello.device_hostname) - 1);
    strncpy(hello.device_cpu, "test-cpu", sizeof(hello.device_cpu) - 1);
    strncpy(hello.device_os, "test-os", sizeof(hello.device_os) - 1);

    if (cortex_protocol_send_frame(transport, CORTEX_FRAME_HELLO,
                                    &hello, sizeof(hello)) < 0) {
        fprintf(stderr, "[mock_adapter] Failed to send HELLO\n");
        cortex_transport_destroy(transport);
        return 1;
    }

    fprintf(stderr, "[mock_adapter] Sent HELLO (boot_id=%u)\n", boot_id);

    /* Receive CONFIG frame */
    cortex_frame_type_t frame_type;
    cortex_wire_config_t config;
    size_t payload_len;

    if (cortex_protocol_recv_frame(transport, &frame_type, &config,
                                    sizeof(config), &payload_len, 5000) < 0) {
        fprintf(stderr, "[mock_adapter] Failed to receive CONFIG\n");
        cortex_transport_destroy(transport);
        return 1;
    }

    if (frame_type != CORTEX_FRAME_CONFIG) {
        fprintf(stderr, "[mock_adapter] Expected CONFIG, got frame type %u\n", frame_type);
        cortex_transport_destroy(transport);
        return 1;
    }

    fprintf(stderr, "[mock_adapter] Received CONFIG (session_id=%u, window=%u×%u)\n",
            config.session_id, config.window_length_samples, config.channels);

    /* Send ACK frame */
    cortex_wire_ack_t ack = {0};
    ack.ack_type = 0;  /* CONFIG acknowledgment */

    /* Handle wrong_output_size behavior */
    if (behavior == MOCK_BEHAVIOR_WRONG_OUTPUT_SIZE) {
        ack.output_window_length_samples = config.window_length_samples / 2;  /* Wrong! */
        ack.output_channels = config.channels;
    } else {
        ack.output_window_length_samples = config.window_length_samples;
        ack.output_channels = config.channels;
    }

    if (cortex_protocol_send_frame(transport, CORTEX_FRAME_ACK,
                                    &ack, sizeof(ack)) < 0) {
        fprintf(stderr, "[mock_adapter] Failed to send ACK\n");
        cortex_transport_destroy(transport);
        return 1;
    }

    fprintf(stderr, "[mock_adapter] Sent ACK (output: %u×%u)\n",
            ack.output_window_length_samples, ack.output_channels);

    /* Window processing loop */
    uint32_t window_count = 0;
    size_t window_buffer_size = config.window_length_samples * config.channels * sizeof(float);
    float *window_buf = malloc(window_buffer_size);

    if (!window_buf) {
        fprintf(stderr, "[mock_adapter] Failed to allocate window buffer\n");
        cortex_transport_destroy(transport);
        return 1;
    }

    while (1) {
        /* Receive WINDOW frame (chunked) */
        if (cortex_protocol_recv_window_chunked(transport, window_count, window_buf,
                                                window_buffer_size, 5000) < 0) {
            fprintf(stderr, "[mock_adapter] Failed to receive WINDOW (sequence=%u)\n",
                    window_count);
            break;
        }

        fprintf(stderr, "[mock_adapter] Received WINDOW (sequence=%u)\n", window_count);

        /* Apply behavior */
        if (behavior == MOCK_BEHAVIOR_CRASH_ON_WINDOW_3 && window_count == 3) {
            fprintf(stderr, "[mock_adapter] CRASH behavior triggered!\n");
            abort();  /* Simulate kernel crash */
        }

        if (behavior == MOCK_BEHAVIOR_HANG_5S) {
            fprintf(stderr, "[mock_adapter] HANG behavior: sleeping 5s\n");
            sleep(5);
        }

        /* Process: identity kernel (output = input) */
        /* window_buf already contains input, no processing needed */

        if (behavior == MOCK_BEHAVIOR_BAD_CRC) {
            /* Corrupt first sample to create CRC mismatch */
            window_buf[0] = NAN;
            fprintf(stderr, "[mock_adapter] BAD_CRC behavior: corrupted output\n");
        }

        /* Device-side timestamps */
        uint64_t now = get_timestamp_ns();

        /* Determine session_id (for wrong_session_id behavior) */
        uint32_t session_id = (behavior == MOCK_BEHAVIOR_WRONG_SESSION_ID) ?
                              (config.session_id + 1) : config.session_id;

        /* Send RESULT frame with output data */
        uint32_t output_size = ack.output_window_length_samples * ack.output_channels;
        if (cortex_adapter_send_result(transport, session_id, window_count,
                                       now, now, now, now, now,
                                       window_buf, output_size, ack.output_channels) < 0) {
            fprintf(stderr, "[mock_adapter] Failed to send RESULT\n");
            break;
        }

        fprintf(stderr, "[mock_adapter] Sent RESULT (sequence=%u)\n", window_count);

        window_count++;
    }

    /* Cleanup */
    free(window_buf);
    cortex_transport_destroy(transport);

    fprintf(stderr, "[mock_adapter] Exiting after %u windows\n", window_count);
    return 0;
}
