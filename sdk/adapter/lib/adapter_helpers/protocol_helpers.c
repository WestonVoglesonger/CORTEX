#include "cortex_adapter_helpers.h"
#include "cortex_protocol.h"
#include "cortex_endian.h"
#include "cortex_wire.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

int cortex_adapter_send_hello(
    cortex_transport_t *transport,
    uint32_t boot_id,
    const char *adapter_name,
    const char *kernel_name,
    uint32_t max_window_samples,
    uint32_t max_channels
)
{
    /* Build HELLO payload */
    uint8_t payload[sizeof(cortex_wire_hello_t) + 32];  /* header + 1 kernel name */

    /* cortex_wire_hello_t fields (little-endian) */
    cortex_write_u32_le(payload + 0, boot_id);
    memset(payload + 4, 0, 32);  /* adapter_name[32] */
    snprintf((char *)(payload + 4), 32, "%s", adapter_name);
    payload[36] = 1;  /* adapter_abi_version */
    payload[37] = 1;  /* num_kernels (Phase 1: single kernel only) */
    cortex_write_u16_le(payload + 38, 0);  /* reserved */
    cortex_write_u32_le(payload + 40, max_window_samples);
    cortex_write_u32_le(payload + 44, max_channels);

    /* Device system info (bytes 48-143) */
    char device_hostname[32];
    char device_cpu[32];
    char device_os[32];
    cortex_get_device_hostname(device_hostname);
    cortex_get_device_cpu(device_cpu);
    cortex_get_device_os(device_os);

    memset(payload + 48, 0, 32);  /* device_hostname[32] */
    snprintf((char *)(payload + 48), 32, "%s", device_hostname);
    memset(payload + 80, 0, 32);  /* device_cpu[32] */
    snprintf((char *)(payload + 80), 32, "%s", device_cpu);
    memset(payload + 112, 0, 32);  /* device_os[32] */
    snprintf((char *)(payload + 112), 32, "%s", device_os);

    /* Kernel name */
    memset(payload + sizeof(cortex_wire_hello_t), 0, 32);
    snprintf((char *)(payload + sizeof(cortex_wire_hello_t)), 32, "%s", kernel_name);

    return cortex_protocol_send_frame(transport, CORTEX_FRAME_HELLO, payload, sizeof(payload));
}

int cortex_adapter_recv_config(
    cortex_transport_t *transport,
    uint32_t *out_session_id,
    uint32_t *out_sample_rate_hz,
    uint32_t *out_window_samples,
    uint32_t *out_hop_samples,
    uint32_t *out_channels,
    char *out_plugin_name,
    char *out_plugin_params,
    void **out_calibration_state,
    uint32_t *out_calibration_state_size
)
{
    /* Allocate buffer for CONFIG frame (header + calibration state up to 16MB) */
    size_t frame_buf_size = sizeof(cortex_wire_config_t) + CORTEX_MAX_CALIBRATION_STATE;
    uint8_t *frame_buf = (uint8_t *)malloc(frame_buf_size);
    if (!frame_buf) {
        return -1;  /* Out of memory */
    }

    cortex_frame_type_t frame_type;
    size_t payload_len;

    int ret = cortex_protocol_recv_frame(
        transport,
        &frame_type,
        frame_buf,
        frame_buf_size,
        &payload_len,
        CORTEX_HANDSHAKE_TIMEOUT_MS
    );

    if (ret < 0) {
        free(frame_buf);
        return ret;
    }

    if (frame_type != CORTEX_FRAME_CONFIG) {
        free(frame_buf);
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    if (payload_len < sizeof(cortex_wire_config_t)) {
        free(frame_buf);
        return CORTEX_EPROTO_INVALID_FRAME;
    }

    /* Parse CONFIG payload (convert from little-endian) */
    *out_session_id = cortex_read_u32_le(frame_buf + 0);
    *out_sample_rate_hz = cortex_read_u32_le(frame_buf + 4);
    *out_window_samples = cortex_read_u32_le(frame_buf + 8);
    *out_hop_samples = cortex_read_u32_le(frame_buf + 12);
    *out_channels = cortex_read_u32_le(frame_buf + 16);

    memcpy(out_plugin_name, frame_buf + 20, 64);
    out_plugin_name[63] = '\0';  /* Ensure null termination */

    memcpy(out_plugin_params, frame_buf + 84, 256);
    out_plugin_params[255] = '\0';  /* Ensure null termination */

    /* Extract calibration state size */
    uint32_t calib_size = cortex_read_u32_le(frame_buf + 340);
    *out_calibration_state_size = calib_size;

    /* Extract calibration state data if present */
    if (calib_size > 0) {
        /* Validate size */
        if (calib_size > CORTEX_MAX_CALIBRATION_STATE) {
            fprintf(stderr, "[adapter_recv_config] Calibration state too large: %u bytes (max %lu)\n",
                    calib_size, (unsigned long)CORTEX_MAX_CALIBRATION_STATE);
            free(frame_buf);
            return CORTEX_EPROTO_INVALID_FRAME;
        }

        /* Verify payload contains the calibration state */
        if (payload_len < sizeof(cortex_wire_config_t) + calib_size) {
            fprintf(stderr, "[adapter_recv_config] Payload too small for calibration state\n");
            free(frame_buf);
            return CORTEX_EPROTO_INVALID_FRAME;
        }

        /* Allocate buffer for calibration state */
        void *calib_buffer = malloc(calib_size);
        if (!calib_buffer) {
            fprintf(stderr, "[adapter_recv_config] Failed to allocate calibration state buffer\n");
            free(frame_buf);
            return -1;
        }

        /* Copy calibration state data (starts after cortex_wire_config_t) */
        memcpy(calib_buffer, frame_buf + sizeof(cortex_wire_config_t), calib_size);
        *out_calibration_state = calib_buffer;
    } else {
        *out_calibration_state = NULL;
    }

    free(frame_buf);
    return 0;
}

int cortex_adapter_send_ack_with_dims(cortex_transport_t *transport,
                                      uint32_t output_window_length,
                                      uint32_t output_channels)
{
    uint8_t payload[12];  /* ack_type (4) + output_window_length (4) + output_channels (4) */
    cortex_write_u32_le(payload + 0, 0);  /* ack_type = 0 (CONFIG) */
    cortex_write_u32_le(payload + 4, output_window_length);
    cortex_write_u32_le(payload + 8, output_channels);

    return cortex_protocol_send_frame(transport, CORTEX_FRAME_ACK, payload, sizeof(payload));
}

int cortex_adapter_send_result(
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
    /* Use chunked protocol for all results (no size limits) */
    return cortex_protocol_send_result_chunked(
        transport,
        session_id,
        sequence,
        tin,
        tstart,
        tend,
        tfirst_tx,
        tlast_tx,
        output_samples,
        output_length,
        output_channels
    );
}

int cortex_adapter_send_error(
    cortex_transport_t *transport,
    uint32_t error_code,
    const char *error_message
)
{
    uint8_t payload[sizeof(cortex_wire_error_t)];  /* error_code (4) + error_message[256] = 260 bytes */

    /* Build ERROR payload (little-endian) */
    cortex_write_u32_le(payload + 0, error_code);
    memset(payload + 4, 0, CORTEX_MAX_ERROR_MESSAGE);
    if (error_message) {
        snprintf((char *)(payload + 4), CORTEX_MAX_ERROR_MESSAGE, "%s", error_message);
    }

    return cortex_protocol_send_frame(transport, CORTEX_FRAME_ERROR, payload, sizeof(cortex_wire_error_t));
}
