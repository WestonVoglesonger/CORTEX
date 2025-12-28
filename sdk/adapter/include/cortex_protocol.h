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
 * Wire format is defined in lib/protocol/wire_format.h
 */

/* Re-export frame types from wire_format.h */
#include "../lib/protocol/wire_format.h"

/* Protocol error codes (negative, distinct from transport errors) */
#define CORTEX_EPROTO_MAGIC_NOT_FOUND  -2000  /* MAGIC not found in stream */
#define CORTEX_EPROTO_CRC_MISMATCH     -2001  /* CRC verification failed */
#define CORTEX_EPROTO_VERSION_MISMATCH -2002  /* Protocol version mismatch */
#define CORTEX_EPROTO_FRAME_TOO_LARGE  -2003  /* Payload exceeds max frame size */
#define CORTEX_EPROTO_BUFFER_TOO_SMALL -2004  /* Caller's buffer too small */

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

#endif /* CORTEX_PROTOCOL_H */
