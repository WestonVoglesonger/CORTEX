/*
 * Device Communication Layer Implementation
 *
 * Spawns device adapter processes and manages communication via socketpair.
 */

#define _POSIX_C_SOURCE 200809L

#include "device_comm.h"
#include "../../../../sdk/adapter/include/cortex_transport.h"
#include "../../../../sdk/adapter/include/cortex_protocol.h"

#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

/*
 * Device handle (opaque to caller)
 */
struct cortex_device_handle {
    pid_t adapter_pid;           /* Adapter process ID */
    cortex_transport_t *transport; /* Transport to adapter */
    uint32_t session_id;         /* Current session ID */
    uint32_t adapter_boot_id;    /* Adapter boot ID (from HELLO) */
    char adapter_name[32];       /* Adapter name (from HELLO) */
};

/*
 * spawn_adapter - Fork and exec adapter process
 *
 * Creates socketpair, forks, connects adapter stdin/stdout to socket,
 * then execs adapter binary.
 *
 * Returns:
 *    0: Success (adapter spawned, harness_fd valid)
 *   <0: Error (fork/exec failed)
 */
static int spawn_adapter(const char *adapter_path, int *harness_fd, pid_t *adapter_pid)
{
    int sv[2];  /* socketpair */

    /* Create bidirectional socketpair */
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) < 0) {
        return -errno;
    }

    /* Fork adapter process */
    pid_t pid = fork();
    if (pid < 0) {
        close(sv[0]);
        close(sv[1]);
        return -errno;
    }

    if (pid == 0) {
        /* Child process (adapter) */

        /* Close harness end of socketpair */
        close(sv[0]);

        /* Redirect stdin/stdout to adapter end of socketpair */
        if (dup2(sv[1], STDIN_FILENO) < 0) {
            perror("dup2 stdin");
            _exit(1);
        }

        if (dup2(sv[1], STDOUT_FILENO) < 0) {
            perror("dup2 stdout");
            _exit(1);
        }

        /* Close original socket (now dup'd to stdin/stdout) */
        if (sv[1] > STDERR_FILENO) {
            close(sv[1]);
        }

        /* Exec adapter binary */
        execl(adapter_path, adapter_path, (char *)NULL);

        /* If exec returns, it failed */
        perror("execl");
        _exit(1);
    }

    /* Parent process (harness) */

    /* Close adapter end of socketpair */
    close(sv[1]);

    *harness_fd = sv[0];
    *adapter_pid = pid;

    return 0;
}

/*
 * recv_hello - Receive HELLO frame from adapter
 *
 * Returns:
 *    0: Success
 *   <0: Error
 */
static int recv_hello(
    cortex_transport_t *transport,
    uint32_t *out_boot_id,
    char *out_adapter_name
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

    if (frame_type != CORTEX_FRAME_HELLO) {
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    if (payload_len < sizeof(cortex_wire_hello_t)) {
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    /* Parse HELLO payload (convert from little-endian) */
    *out_boot_id = cortex_read_u32_le(frame_buf + 0);
    memcpy(out_adapter_name, frame_buf + 4, 32);
    out_adapter_name[31] = '\0';  /* Ensure null termination */

    /* TODO: Validate adapter_abi_version, num_kernels, etc. */

    return 0;
}

/*
 * send_config - Send CONFIG frame to adapter
 *
 * Returns:
 *    0: Success
 *   <0: Error
 */
static int send_config(
    cortex_transport_t *transport,
    uint32_t session_id,
    uint32_t sample_rate_hz,
    uint32_t window_samples,
    uint32_t hop_samples,
    uint32_t channels,
    const char *plugin_name,
    const char *plugin_params,
    const void *calib_state,
    size_t calib_state_size
)
{
    size_t payload_len = sizeof(cortex_wire_config_t) + calib_state_size;
    uint8_t *payload = (uint8_t *)malloc(payload_len);
    if (!payload) {
        return -ENOMEM;
    }

    /* Build CONFIG payload (little-endian) */
    cortex_write_u32_le(payload + 0, session_id);
    cortex_write_u32_le(payload + 4, sample_rate_hz);
    cortex_write_u32_le(payload + 8, window_samples);
    cortex_write_u32_le(payload + 12, hop_samples);
    cortex_write_u32_le(payload + 16, channels);

    memset(payload + 20, 0, 32);
    snprintf((char *)(payload + 20), 32, "%s", plugin_name);

    memset(payload + 52, 0, 256);
    snprintf((char *)(payload + 52), 256, "%s", plugin_params);

    cortex_write_u32_le(payload + 308, (uint32_t)calib_state_size);

    /* Append calibration state */
    if (calib_state_size > 0 && calib_state != NULL) {
        memcpy(payload + sizeof(cortex_wire_config_t), calib_state, calib_state_size);
    }

    int ret = cortex_protocol_send_frame(transport, CORTEX_FRAME_CONFIG, payload, payload_len);

    free(payload);
    return ret;
}

/*
 * recv_ack - Receive ACK frame from adapter
 *
 * Extracts optional output dimensions from ACK frame.
 * If dimensions are 0, caller should use config dimensions.
 *
 * Returns:
 *    0: Success
 *   <0: Error
 */
static int recv_ack(cortex_transport_t *transport,
                    uint32_t *out_output_window_length,
                    uint32_t *out_output_channels)
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

    if (frame_type != CORTEX_FRAME_ACK) {
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    if (payload_len < sizeof(cortex_wire_ack_t)) {
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    /* Parse ACK payload */
    cortex_wire_ack_t *ack = (cortex_wire_ack_t *)frame_buf;

    /* Extract output dimensions (0 = use config) */
    *out_output_window_length = cortex_read_u32_le((uint8_t *)&ack->output_window_length_samples);
    *out_output_channels = cortex_read_u32_le((uint8_t *)&ack->output_channels);

    /* TODO: Validate ack_type */

    return 0;
}

/*
 * device_comm_init - Spawn adapter and perform complete handshake
 *
 * This is ATOMIC and SYNCHRONOUS - all handshake frames sent/received
 * before return. Caller may free calib_state immediately after return.
 */
int device_comm_init(
    const char *adapter_path,
    const char *plugin_name,
    const char *plugin_params,
    uint32_t sample_rate_hz,
    uint32_t window_samples,
    uint32_t hop_samples,
    uint32_t channels,
    const void *calib_state,
    size_t calib_state_size,
    cortex_device_init_result_t *out_result
)
{
    if (!out_result) {
        return -EINVAL;
    }

    /* Allocate device handle */
    cortex_device_handle_t *handle = (cortex_device_handle_t *)calloc(1, sizeof(*handle));
    if (!handle) {
        return -ENOMEM;
    }

    /* Spawn adapter process */
    int harness_fd;
    int ret = spawn_adapter(adapter_path, &harness_fd, &handle->adapter_pid);
    if (ret < 0) {
        free(handle);
        return ret;
    }

    /* Create transport from socketpair */
    handle->transport = cortex_transport_mock_create(harness_fd);
    if (!handle->transport) {
        close(harness_fd);
        /* Kill adapter process */
        kill(handle->adapter_pid, SIGTERM);
        waitpid(handle->adapter_pid, NULL, 0);
        free(handle);
        return -ENOMEM;
    }

    /* Receive HELLO */
    ret = recv_hello(handle->transport, &handle->adapter_boot_id, handle->adapter_name);
    if (ret < 0) {
        device_comm_teardown(handle);
        return ret;
    }

    /* Generate session ID */
    handle->session_id = (uint32_t)rand();

    /* Send CONFIG (serializes calib_state into wire format) */
    ret = send_config(
        handle->transport,
        handle->session_id,
        sample_rate_hz,
        window_samples,
        hop_samples,
        channels,
        plugin_name,
        plugin_params,
        calib_state,
        calib_state_size
    );

    if (ret < 0) {
        device_comm_teardown(handle);
        return ret;
    }

    /* Receive ACK (with optional output dimension override) */
    uint32_t output_window_length = 0;
    uint32_t output_channels = 0;
    ret = recv_ack(handle->transport, &output_window_length, &output_channels);
    if (ret < 0) {
        device_comm_teardown(handle);
        return ret;
    }

    /* Populate result struct */
    out_result->handle = handle;
    out_result->output_window_length_samples = output_window_length;  /* 0 = use config */
    out_result->output_channels = output_channels;                     /* 0 = use config */
    strncpy(out_result->adapter_name, handle->adapter_name, sizeof(out_result->adapter_name) - 1);
    out_result->adapter_name[sizeof(out_result->adapter_name) - 1] = '\0';

    return 0;
}

/*
 * device_comm_execute_window - Send window and receive result
 */
int device_comm_execute_window(
    cortex_device_handle_t *handle,
    uint32_t sequence,
    const float *input_samples,
    uint32_t window_samples,
    uint32_t channels,
    float *output_samples,
    size_t output_buf_size,
    cortex_device_timing_t *out_timing
)
{
    /* Send chunked WINDOW */
    int ret = cortex_protocol_send_window_chunked(
        handle->transport,
        sequence,
        input_samples,
        window_samples,
        channels
    );

    if (ret < 0) {
        return ret;
    }

    /* Receive RESULT */
    uint8_t frame_buf[CORTEX_MAX_SINGLE_FRAME];
    cortex_frame_type_t frame_type;
    size_t payload_len;

    ret = cortex_protocol_recv_frame(
        handle->transport,
        &frame_type,
        frame_buf,
        sizeof(frame_buf),
        &payload_len,
        CORTEX_WINDOW_TIMEOUT_MS
    );

    if (ret < 0) {
        return ret;
    }

    if (frame_type != CORTEX_FRAME_RESULT) {
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    if (payload_len < sizeof(cortex_wire_result_t)) {
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    /* Parse RESULT header (convert from little-endian) */
    uint32_t result_session_id = cortex_read_u32_le(frame_buf + 0);
    uint32_t result_sequence = cortex_read_u32_le(frame_buf + 4);
    uint64_t tin = cortex_read_u64_le(frame_buf + 8);
    uint64_t tstart = cortex_read_u64_le(frame_buf + 16);
    uint64_t tend = cortex_read_u64_le(frame_buf + 24);
    uint64_t tfirst_tx = cortex_read_u64_le(frame_buf + 32);
    uint64_t tlast_tx = cortex_read_u64_le(frame_buf + 40);
    uint32_t output_length = cortex_read_u32_le(frame_buf + 48);
    uint32_t output_channels = cortex_read_u32_le(frame_buf + 52);

    /* Validate session ID */
    if (result_session_id != handle->session_id) {
        return CORTEX_ECHUNK_SEQUENCE_MISMATCH;  /* Reuse error code */
    }

    /* Validate sequence */
    if (result_sequence != sequence) {
        return CORTEX_ECHUNK_SEQUENCE_MISMATCH;
    }

    /* Validate output dimensions */
    size_t output_bytes = output_length * output_channels * sizeof(float);
    if (output_bytes > output_buf_size) {
        return CORTEX_ECHUNK_BUFFER_TOO_SMALL;
    }

    if (payload_len != sizeof(cortex_wire_result_t) + output_bytes) {
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    /* Convert output samples from little-endian */
    const uint8_t *sample_buf = frame_buf + sizeof(cortex_wire_result_t);
    for (uint32_t i = 0; i < output_length * output_channels; i++) {
        output_samples[i] = cortex_read_f32_le(sample_buf + (i * sizeof(float)));
    }

    /* Return timing */
    if (out_timing) {
        out_timing->tin = tin;
        out_timing->tstart = tstart;
        out_timing->tend = tend;
        out_timing->tfirst_tx = tfirst_tx;
        out_timing->tlast_tx = tlast_tx;
    }

    return 0;
}

/*
 * device_comm_teardown - Cleanup adapter process
 */
void device_comm_teardown(cortex_device_handle_t *handle)
{
    if (!handle) {
        return;
    }

    /* Close transport (adapter will see EOF and exit) */
    if (handle->transport) {
        handle->transport->close(handle->transport->ctx);
        free(handle->transport);
        handle->transport = NULL;
    }

    /* Wait for adapter process (reap zombie) */
    if (handle->adapter_pid > 0) {
        int status;
        waitpid(handle->adapter_pid, &status, 0);
        handle->adapter_pid = 0;
    }

    free(handle);
}
