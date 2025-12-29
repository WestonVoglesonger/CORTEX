#ifndef CORTEX_ADAPTER_HELPERS_H
#define CORTEX_ADAPTER_HELPERS_H

#include "cortex_transport.h"
#include <stdint.h>

/*
 * CORTEX Device Adapter Helper Functions
 *
 * Optional convenience functions that reduce boilerplate when implementing
 * new device adapters. These handle the protocol handshake and common message
 * exchange patterns.
 *
 * Usage: Include this header if you want to simplify your adapter implementation.
 *        You can still use the low-level cortex_protocol_* functions directly
 *        if you need custom behavior.
 */

/*
 * cortex_adapter_send_hello - Send HELLO frame to harness
 *
 * Sends adapter capabilities and supported kernels. This is the first message
 * in the handshake sequence.
 *
 * Args:
 *   transport:     Transport to send on
 *   boot_id:       Random boot ID (use random number generator)
 *   adapter_name:  Adapter identifier (e.g., "x86@loopback", "stm32@uart")
 *   kernel_name:   Name of kernel plugin (e.g., "noop@f32", "car@f32")
 *                  NOTE: Phase 1 supports single kernel only
 *   max_window_samples: Maximum window length this adapter can handle
 *   max_channels:  Maximum channel count this adapter can handle
 *
 * Returns:
 *    0: Success
 *   <0: Transport error
 */
int cortex_adapter_send_hello(
    cortex_transport_t *transport,
    uint32_t boot_id,
    const char *adapter_name,
    const char *kernel_name,
    uint32_t max_window_samples,
    uint32_t max_channels
);

/*
 * cortex_adapter_recv_config - Receive CONFIG frame from harness
 *
 * Receives kernel configuration parameters. This is the second message
 * in the handshake sequence.
 *
 * Args:
 *   transport:           Transport to receive from
 *   out_session_id:      Pointer to store session ID
 *   out_sample_rate_hz:  Pointer to store sample rate (Hz)
 *   out_window_samples:  Pointer to store window length (W)
 *   out_hop_samples:     Pointer to store hop size (H)
 *   out_channels:        Pointer to store channel count (C)
 *   out_plugin_name:     Buffer to store plugin name (must be [32] bytes)
 *   out_plugin_params:   Buffer to store plugin params (must be [256] bytes)
 *
 * Returns:
 *    0: Success (CONFIG received and parsed)
 *   <0: Error (timeout, protocol error, invalid frame)
 */
int cortex_adapter_recv_config(
    cortex_transport_t *transport,
    uint32_t *out_session_id,
    uint32_t *out_sample_rate_hz,
    uint32_t *out_window_samples,
    uint32_t *out_hop_samples,
    uint32_t *out_channels,
    char *out_plugin_name,     /* [32] */
    char *out_plugin_params    /* [256] */
);

/*
 * cortex_adapter_send_ack - Send ACK frame to harness
 *
 * Acknowledges successful kernel initialization. This is the third message
 * in the handshake sequence.
 *
 * Args:
 *   transport: Transport to send on
 *
 * Returns:
 *    0: Success
 *   <0: Transport error
 */
int cortex_adapter_send_ack(cortex_transport_t *transport);

/*
 * cortex_adapter_send_result - Send RESULT frame to harness
 *
 * Sends kernel execution results with timing telemetry and output samples.
 *
 * Args:
 *   transport:       Transport to send on
 *   session_id:      Session ID (from recv_config)
 *   sequence:        Window sequence number
 *   tin:             Timestamp when window reassembly completed (ns)
 *   tstart:          Timestamp before kernel execution (ns)
 *   tend:            Timestamp after kernel execution (ns)
 *   tfirst_tx:       Timestamp before first send() call (ns)
 *   tlast_tx:        Timestamp after last send() call (ns)
 *   output_samples:  Float32 output buffer (kernel output)
 *   output_length:   Output window length (samples per channel)
 *   output_channels: Output channel count
 *
 * Returns:
 *    0: Success
 *   <0: Error (allocation failure, transport error)
 *
 * NOTE: This function allocates temporary memory for serialization.
 */
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
);

#endif /* CORTEX_ADAPTER_HELPERS_H */
