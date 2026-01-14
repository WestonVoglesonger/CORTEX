#ifndef CORTEX_PROTOCOL_H
#define CORTEX_PROTOCOL_H

#include "cortex_transport.h"
#include <stddef.h>
#include <stdint.h>

/*
 * CORTEX Device Adapter Protocol Layer
 *
 * Provides frame-based communication over byte-stream transports.
 * Handles framing, CRC validation, MAGIC hunting, and timeout management.
 *
 * Wire format is defined in cortex_wire.h
 */

/* Re-export wire format definitions and endian helpers */
#include "cortex_wire.h"
#include "cortex_endian.h"

/* Protocol error codes (negative, distinct from transport errors) */
#define CORTEX_EPROTO_MAGIC_NOT_FOUND  -2000  /* MAGIC not found in stream */
#define CORTEX_EPROTO_CRC_MISMATCH     -2001  /* CRC verification failed */
#define CORTEX_EPROTO_VERSION_MISMATCH -2002  /* Protocol version mismatch */
#define CORTEX_EPROTO_FRAME_TOO_LARGE  -2003  /* Payload exceeds max frame size */
#define CORTEX_EPROTO_BUFFER_TOO_SMALL -2004  /* Caller's buffer too small */
#define CORTEX_EPROTO_INVALID_FRAME    -2005  /* Invalid frame structure */

/*
 * cortex_protocol_recv_frame - Receive one complete frame
 *
 * Hunts for MAGIC, reads header, reads payload, verifies CRC.
 * Handles fragmented stream (may need multiple recv() calls).
 *
 * Args:
 *   transport:        Transport to read from
 *   out_type:         Pointer to store frame type
 *   payload_buf:      Buffer to store payload (excluding header)
 *   payload_buf_size: Size of payload_buf
 *   out_payload_len:  Pointer to store actual payload length
 *   timeout_ms:       Total timeout for entire frame reception
 *
 * Returns:
 *    0: Success (frame received and validated)
 *   <0: Error (transport error, timeout, protocol error)
 *
 * Errors:
 *   CORTEX_ETIMEDOUT:           Timeout waiting for data
 *   CORTEX_ECONNRESET:          Connection closed
 *   CORTEX_EPROTO_MAGIC_NOT_FOUND:   MAGIC not found
 *   CORTEX_EPROTO_CRC_MISMATCH:      CRC verification failed
 *   CORTEX_EPROTO_VERSION_MISMATCH:  Protocol version != 1
 *   CORTEX_EPROTO_FRAME_TOO_LARGE:   Payload > CORTEX_MAX_SINGLE_FRAME
 *   CORTEX_EPROTO_BUFFER_TOO_SMALL:  payload_buf too small for payload
 *
 * IMPORTANT:
 *   - Payload is raw wire format (little-endian). Use endian.h helpers to parse.
 *   - May block for extended time if transport is slow.
 *   - timeout_ms is for ENTIRE frame (hunt + header + payload), not per recv().
 */
int cortex_protocol_recv_frame(
    cortex_transport_t *transport,
    cortex_frame_type_t *out_type,
    void *payload_buf,
    size_t payload_buf_size,
    size_t *out_payload_len,
    uint32_t timeout_ms
);

/*
 * cortex_protocol_send_frame - Send one complete frame
 *
 * Builds header with MAGIC/version/type/length, computes CRC, sends frame.
 *
 * Args:
 *   transport:    Transport to send on
 *   frame_type:   Frame type (HELLO, CONFIG, WINDOW_CHUNK, etc.)
 *   payload:      Payload data (wire format, little-endian)
 *   payload_len:  Payload length in bytes
 *
 * Returns:
 *    0: Success
 *   <0: Error (transport send failure)
 *
 * IMPORTANT:
 *   - Payload must already be in wire format (little-endian).
 *   - Use endian.h helpers to serialize payload before calling.
 *   - Entire frame sent in single send() call (header + payload).
 */
int cortex_protocol_send_frame(
    cortex_transport_t *transport,
    cortex_frame_type_t frame_type,
    const void *payload,
    size_t payload_len
);

/*
 * cortex_protocol_send_window_chunked - Send window as multiple WINDOW_CHUNK frames
 *
 * Breaks large window (W×C float32 samples) into 8KB chunks and sends as
 * separate WINDOW_CHUNK frames. Last chunk has CORTEX_CHUNK_FLAG_LAST set.
 *
 * Args:
 *   transport:     Transport to send on
 *   sequence:      Window sequence number
 *   samples:       Float32 sample buffer (W×C samples)
 *   window_samples: Number of samples per channel (W)
 *   channels:      Number of channels (C)
 *
 * Returns:
 *    0: Success (all chunks sent)
 *   <0: Error (transport send failure)
 *
 * Example: 160×64 window = 40,960 bytes → 5 chunks (4×8KB + 1×8KB)
 *
 * IMPORTANT:
 *   - samples buffer is float32 array in host format (NOT little-endian yet)
 *   - This function handles conversion to little-endian wire format
 *   - Chunks sent sequentially (not parallel)
 */
int cortex_protocol_send_window_chunked(
    cortex_transport_t *transport,
    uint32_t sequence,
    const float *samples,
    uint32_t window_samples,
    uint32_t channels
);

/*
 * cortex_protocol_recv_window_chunked - Receive window from multiple WINDOW_CHUNK frames
 *
 * Receives and reassembles WINDOW_CHUNK frames into complete window buffer.
 * Validates sequence, offset, total_bytes for completeness and correctness.
 *
 * Args:
 *   transport:         Transport to receive from
 *   expected_sequence: Expected window sequence number
 *   out_samples:       Output buffer for float32 samples (host format)
 *   samples_buf_size:  Size of out_samples buffer in bytes
 *   timeout_ms:        Total timeout for receiving ALL chunks
 *
 * Returns:
 *    0: Success (window complete and validated)
 *   <0: Error (timeout, sequence mismatch, incomplete chunks, etc.)
 *
 * Errors:
 *   CORTEX_ETIMEDOUT:               Timeout waiting for chunks
 *   CORTEX_EPROTO_*:                Protocol errors (CRC, MAGIC, etc.)
 *   CORTEX_ECHUNK_SEQUENCE_MISMATCH: Chunk has wrong sequence number
 *   CORTEX_ECHUNK_INCOMPLETE:        Missing chunks (incomplete transfer)
 *   CORTEX_ECHUNK_BUFFER_TOO_SMALL:  out_samples buffer too small
 *
 * IMPORTANT:
 *   - Blocks until ALL chunks received or timeout
 *   - Converts samples from little-endian wire format to host format
 *   - Sets tin timestamp AFTER final chunk (CORTEX_CHUNK_FLAG_LAST) received
 *   - Caller must know window dimensions (W×C) from CONFIG handshake
 */
int cortex_protocol_recv_window_chunked(
    cortex_transport_t *transport,
    uint32_t expected_sequence,
    float *out_samples,
    size_t samples_buf_size,
    uint32_t timeout_ms
);

/*
 * cortex_protocol_send_result_chunked - Send result as multiple RESULT_CHUNK frames
 *
 * Identical pattern to send_window_chunked. Breaks large result into 8KB chunks.
 * All chunks include metadata fields; receiver extracts from first chunk (offset==0).
 *
 * Args:
 *   transport:              Transport to send on
 *   session_id:             Session ID from CONFIG
 *   sequence:               Window sequence number
 *   tin:                    Input complete timestamp (ns)
 *   tstart:                 Kernel start timestamp (ns)
 *   tend:                   Kernel end timestamp (ns)
 *   tfirst_tx:              First result byte tx timestamp (ns)
 *   tlast_tx:               Last result byte tx timestamp (ns)
 *   samples:                Float32 result buffer (host format)
 *   output_length_samples:  Number of output samples per channel
 *   output_channels:        Number of output channels
 *
 * Returns:
 *    0: Success (all chunks sent)
 *   <0: Error (transport send failure)
 */
int cortex_protocol_send_result_chunked(
    cortex_transport_t *transport,
    uint32_t session_id,
    uint32_t sequence,
    uint64_t tin,
    uint64_t tstart,
    uint64_t tend,
    uint64_t tfirst_tx,
    uint64_t tlast_tx,
    const float *samples,
    uint32_t output_length_samples,
    uint32_t output_channels
);

/*
 * cortex_protocol_recv_result_chunked - Receive result from multiple RESULT_CHUNK frames
 *
 * Identical pattern to recv_window_chunked. Reassembles chunks, extracts metadata.
 * Metadata (session_id, timestamps, dimensions) extracted from first chunk.
 *
 * Args:
 *   transport:          Transport to receive from
 *   expected_sequence:  Expected window sequence number
 *   out_samples:        Output buffer for float32 samples (host format)
 *   samples_buf_size:   Size of out_samples buffer in bytes
 *   timeout_ms:         Total timeout for receiving ALL chunks
 *   out_session_id:     [OUT] Session ID from result
 *   out_tin:            [OUT] Input complete timestamp
 *   out_tstart:         [OUT] Kernel start timestamp
 *   out_tend:           [OUT] Kernel end timestamp
 *   out_tfirst_tx:      [OUT] First tx timestamp
 *   out_tlast_tx:       [OUT] Last tx timestamp
 *   out_length:         [OUT] Output length samples
 *   out_channels:       [OUT] Output channels
 *
 * Returns:
 *    0: Success (result complete and validated)
 *   <0: Error (same error codes as recv_window_chunked)
 */
int cortex_protocol_recv_result_chunked(
    cortex_transport_t *transport,
    uint32_t expected_sequence,
    float *out_samples,
    size_t samples_buf_size,
    uint32_t timeout_ms,
    uint32_t *out_session_id,
    uint64_t *out_tin,
    uint64_t *out_tstart,
    uint64_t *out_tend,
    uint64_t *out_tfirst_tx,
    uint64_t *out_tlast_tx,
    uint32_t *out_length,
    uint32_t *out_channels
);

/* Chunking error codes */
#define CORTEX_ECHUNK_SEQUENCE_MISMATCH -2100  /* Chunk sequence != expected */
#define CORTEX_ECHUNK_INCOMPLETE        -2101  /* Missing chunks (gaps) */
#define CORTEX_ECHUNK_BUFFER_TOO_SMALL  -2102  /* Buffer too small for window */
#define CORTEX_ECHUNK_INVALID_FRAME_TYPE -2103 /* Expected RESULT_CHUNK, got other type */
#define CORTEX_ECHUNK_INVALID_OFFSET    -2104  /* Chunk offset+length > total_bytes */

#endif /* CORTEX_PROTOCOL_H */
