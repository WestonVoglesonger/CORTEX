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

    memcpy(out_plugin_name, frame_buf + 20, 64);
    out_plugin_name[63] = '\0';  /* Ensure null termination */

    memcpy(out_plugin_params, frame_buf + 84, 256);
    out_plugin_params[255] = '\0';  /* Ensure null termination */

    /* NOTE: Calibration state extraction not implemented yet (Phase 2) */

    return 0;
}

int cortex_adapter_send_ack(cortex_transport_t *transport)
{
    /* Backward compat: send zeros for output dimensions */
    return cortex_adapter_send_ack_with_dims(transport, 0, 0);
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
    cortex_write_u32_le(payload + 32, tfirst_tx);
    cortex_write_u32_le(payload + 40, tlast_tx);
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
