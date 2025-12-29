#define _POSIX_C_SOURCE 200809L

#include "cortex_protocol.h"
#include "crc32.h"
#include "endian.h"

#include <string.h>
#include <stdlib.h>

/*
 * read_exact - Read exactly N bytes with timeout
 *
 * Handles partial reads, accumulating bytes until N received or timeout.
 *
 * Returns:
 *    0: Success (N bytes read)
 *   <0: Error (timeout, connection reset, or other transport error)
 */
static int read_exact(cortex_transport_t *transport, void *buf, size_t n, uint32_t timeout_ms)
{
    uint8_t *p = (uint8_t *)buf;
    size_t remaining = n;
    uint64_t deadline = transport->get_timestamp_ns() + ((uint64_t)timeout_ms * 1000000ULL);

    while (remaining > 0) {
        /* Calculate time left */
        uint64_t now = transport->get_timestamp_ns();
        if (now >= deadline) {
            return CORTEX_ETIMEDOUT;
        }

        uint32_t time_left_ms = (uint32_t)((deadline - now) / 1000000ULL);
        if (time_left_ms == 0) {
            time_left_ms = 1;  /* Ensure at least 1ms timeout */
        }

        /* Try to read remaining bytes */
        ssize_t got = transport->recv(transport->ctx, p, remaining, time_left_ms);

        if (got == CORTEX_ETIMEDOUT) {
            return CORTEX_ETIMEDOUT;
        }

        if (got == CORTEX_ECONNRESET || got == 0) {
            return CORTEX_ECONNRESET;
        }

        if (got < 0) {
            /* Other transport error */
            return (int)got;
        }

        p += got;
        remaining -= got;
    }

    return 0;
}

/*
 * hunt_magic - Hunt for MAGIC in byte stream
 *
 * Reads bytes one at a time, maintaining sliding window, until MAGIC found.
 *
 * Returns:
 *    0: Success (MAGIC found)
 *   <0: Error (timeout or transport error)
 *
 * IMPORTANT: Wire format is little-endian, so MAGIC bytes arrive as:
 *   0x58, 0x54, 0x52, 0x43 (little-endian representation of 0x43525458)
 * We reconstruct by shifting RIGHT and inserting new bytes at the top.
 */
static int hunt_magic(cortex_transport_t *transport, uint32_t timeout_ms)
{
    uint32_t window = 0;
    uint64_t deadline = transport->get_timestamp_ns() + ((uint64_t)timeout_ms * 1000000ULL);

    while (1) {
        /* Calculate time left */
        uint64_t now = transport->get_timestamp_ns();
        if (now >= deadline) {
            return CORTEX_EPROTO_MAGIC_NOT_FOUND;
        }

        uint32_t time_left_ms = (uint32_t)((deadline - now) / 1000000ULL);
        if (time_left_ms == 0) {
            time_left_ms = 1;
        }

        /* Read one byte */
        uint8_t byte;
        ssize_t got = transport->recv(transport->ctx, &byte, 1, time_left_ms);

        if (got == CORTEX_ETIMEDOUT) {
            continue;  /* Keep trying until deadline */
        }

        if (got == CORTEX_ECONNRESET || got == 0) {
            return CORTEX_ECONNRESET;
        }

        if (got < 0) {
            return (int)got;
        }

        /* Shift window RIGHT and add new byte at top (little-endian order)
         * Example: MAGIC bytes arrive as 0x58, 0x54, 0x52, 0x43
         *   After 0x58: window = 0x00000058
         *   After 0x54: window = 0x00005458
         *   After 0x52: window = 0x00525458
         *   After 0x43: window = 0x43525458 ✓ matches CORTEX_PROTOCOL_MAGIC
         */
        window = (window >> 8) | ((uint32_t)byte << 24);

        /* Check if MAGIC found */
        if (window == CORTEX_PROTOCOL_MAGIC) {
            return 0;
        }
    }
}

/*
 * cortex_protocol_recv_frame - Receive one complete frame
 *
 * Implementation:
 *   1. Hunt for MAGIC (4 bytes)
 *   2. Read rest of header (12 bytes: version, type, flags, payload_len, crc32)
 *   3. Validate version and payload_len
 *   4. Read payload
 *   5. Compute CRC and verify
 *   6. Return payload to caller
 */
int cortex_protocol_recv_frame(
    cortex_transport_t *transport,
    cortex_frame_type_t *out_type,
    void *payload_buf,
    size_t payload_buf_size,
    size_t *out_payload_len,
    uint32_t timeout_ms
)
{
    uint8_t header_buf[16];  /* cortex_wire_header_t is 16 bytes */
    int ret;

    /* 1. Hunt for MAGIC */
    ret = hunt_magic(transport, timeout_ms);
    if (ret < 0) {
        return ret;
    }

    /* MAGIC found - store in header buffer */
    cortex_write_u32_le(header_buf, CORTEX_PROTOCOL_MAGIC);

    /* 2. Read rest of header (12 bytes after MAGIC) */
    ret = read_exact(transport, header_buf + 4, 12, timeout_ms);
    if (ret < 0) {
        return ret;
    }

    /* 3. Parse header fields (convert from little-endian) */
    uint8_t version = header_buf[4];
    uint8_t frame_type = header_buf[5];
    uint16_t flags = cortex_read_u16_le(header_buf + 6);
    uint32_t payload_length = cortex_read_u32_le(header_buf + 8);
    uint32_t wire_crc32 = cortex_read_u32_le(header_buf + 12);

    (void)flags;  /* Unused in Phase 1 */

    /* 4. Validate version */
    if (version != CORTEX_PROTOCOL_VERSION) {
        return CORTEX_EPROTO_VERSION_MISMATCH;
    }

    /* 5. Validate payload length */
    if (payload_length > CORTEX_MAX_SINGLE_FRAME) {
        return CORTEX_EPROTO_FRAME_TOO_LARGE;
    }

    if (payload_length > payload_buf_size) {
        return CORTEX_EPROTO_BUFFER_TOO_SMALL;
    }

    /* 6. Read payload */
    if (payload_length > 0) {
        ret = read_exact(transport, payload_buf, payload_length, timeout_ms);
        if (ret < 0) {
            return ret;
        }
    }

    /* 7. Compute CRC (over first 12 bytes of header + payload) */
    uint32_t computed_crc = cortex_crc32(0, header_buf, 12);
    if (payload_length > 0) {
        computed_crc = cortex_crc32(computed_crc, (const uint8_t *)payload_buf, payload_length);
    }

    /* 8. Verify CRC */
    if (computed_crc != wire_crc32) {
        return CORTEX_EPROTO_CRC_MISMATCH;
    }

    /* Success - return frame info */
    *out_type = (cortex_frame_type_t)frame_type;
    *out_payload_len = payload_length;

    return 0;
}

/*
 * cortex_protocol_send_frame - Send one complete frame
 *
 * Implementation:
 *   1. Build header with MAGIC, version, type, payload_len
 *   2. Compute CRC over header (first 12 bytes) + payload
 *   3. Write CRC into header
 *   4. Send header + payload
 */
int cortex_protocol_send_frame(
    cortex_transport_t *transport,
    cortex_frame_type_t frame_type,
    const void *payload,
    size_t payload_len
)
{
    uint8_t header_buf[16];  /* cortex_wire_header_t is 16 bytes */

    /* 1. Build header (little-endian) */
    cortex_write_u32_le(header_buf + 0, CORTEX_PROTOCOL_MAGIC);
    header_buf[4] = CORTEX_PROTOCOL_VERSION;
    header_buf[5] = (uint8_t)frame_type;
    cortex_write_u16_le(header_buf + 6, 0);  /* flags = 0 for Phase 1 */
    cortex_write_u32_le(header_buf + 8, (uint32_t)payload_len);

    /* 2. Compute CRC over header (first 12 bytes) + payload */
    uint32_t crc = cortex_crc32(0, header_buf, 12);
    if (payload_len > 0 && payload != NULL) {
        crc = cortex_crc32(crc, (const uint8_t *)payload, payload_len);
    }

    /* 3. Write CRC into header */
    cortex_write_u32_le(header_buf + 12, crc);

    /* 4. Send header */
    ssize_t sent = transport->send(transport->ctx, header_buf, sizeof(header_buf));
    if (sent < 0) {
        return (int)sent;
    }

    if (sent != sizeof(header_buf)) {
        /* Partial send - this shouldn't happen with blocking send, but handle it */
        return -1;
    }

    /* 5. Send payload (if any) */
    if (payload_len > 0 && payload != NULL) {
        sent = transport->send(transport->ctx, payload, payload_len);
        if (sent < 0) {
            return (int)sent;
        }

        if ((size_t)sent != payload_len) {
            return -1;
        }
    }

    return 0;
}

/*
 * cortex_protocol_send_window_chunked - Send window as multiple WINDOW_CHUNK frames
 *
 * Implementation:
 *   1. Calculate total_bytes = window_samples × channels × sizeof(float)
 *   2. Loop over window in CORTEX_CHUNK_SIZE chunks
 *   3. For each chunk:
 *      - Build cortex_wire_window_chunk_t header (sequence, total_bytes, offset, chunk_len, flags)
 *      - Convert float samples to little-endian
 *      - Send WINDOW_CHUNK frame
 *   4. Mark last chunk with CORTEX_CHUNK_FLAG_LAST
 */
int cortex_protocol_send_window_chunked(
    cortex_transport_t *transport,
    uint32_t sequence,
    const float *samples,
    uint32_t window_samples,
    uint32_t channels
)
{
    uint32_t total_bytes = window_samples * channels * sizeof(float);
    uint32_t offset = 0;

    /* Allocate buffer for chunk payload (header + data) */
    uint8_t *chunk_buf = (uint8_t *)malloc(sizeof(cortex_wire_window_chunk_t) + CORTEX_CHUNK_SIZE);
    if (!chunk_buf) {
        return -1;
    }

    int ret = 0;

    while (offset < total_bytes) {
        /* Calculate chunk length (last chunk may be smaller) */
        uint32_t remaining = total_bytes - offset;
        uint32_t chunk_len = (remaining > CORTEX_CHUNK_SIZE) ? CORTEX_CHUNK_SIZE : remaining;

        /* Determine flags */
        uint32_t flags = 0;
        if (offset + chunk_len >= total_bytes) {
            flags |= CORTEX_CHUNK_FLAG_LAST;
        }

        /* Build chunk header (in little-endian wire format) */
        cortex_write_u32_le(chunk_buf + 0, sequence);
        cortex_write_u32_le(chunk_buf + 4, total_bytes);
        cortex_write_u32_le(chunk_buf + 8, offset);
        cortex_write_u32_le(chunk_buf + 12, chunk_len);
        cortex_write_u32_le(chunk_buf + 16, flags);

        /* Convert float samples to little-endian and copy to chunk buffer */
        uint8_t *chunk_data = chunk_buf + sizeof(cortex_wire_window_chunk_t);
        const uint8_t *sample_bytes = (const uint8_t *)samples + offset;

        for (uint32_t i = 0; i < chunk_len; i += sizeof(float)) {
            float sample;
            memcpy(&sample, sample_bytes + i, sizeof(sample));
            cortex_write_f32_le(chunk_data + i, sample);
        }

        /* Send WINDOW_CHUNK frame */
        ret = cortex_protocol_send_frame(
            transport,
            CORTEX_FRAME_WINDOW_CHUNK,
            chunk_buf,
            sizeof(cortex_wire_window_chunk_t) + chunk_len
        );

        if (ret < 0) {
            break;
        }

        offset += chunk_len;
    }

    free(chunk_buf);
    return ret;
}

/*
 * cortex_protocol_recv_window_chunked - Receive and reassemble WINDOW_CHUNK frames
 *
 * Implementation:
 *   1. Allocate temporary buffer for complete window
 *   2. Loop receiving WINDOW_CHUNK frames until CORTEX_CHUNK_FLAG_LAST
 *   3. For each chunk:
 *      - Validate sequence matches expected
 *      - Validate offset + chunk_len <= total_bytes
 *      - Copy chunk data to window buffer at offset
 *      - Track bytes received
 *   4. Validate completeness (all bytes received, no gaps)
 *   5. Convert window from little-endian to host format
 *   6. Return window to caller
 */
int cortex_protocol_recv_window_chunked(
    cortex_transport_t *transport,
    uint32_t expected_sequence,
    float *out_samples,
    size_t samples_buf_size,
    uint32_t *out_window_samples,
    uint32_t *out_channels,
    uint32_t timeout_ms
)
{
    uint8_t frame_buf[CORTEX_MAX_SINGLE_FRAME];
    uint32_t total_bytes = 0;
    uint32_t bytes_received = 0;
    int got_last_chunk = 0;
    int ret;

    /* Track which bytes we've received (for gap detection) */
    uint8_t *received_mask = NULL;

    /* Allocate temporary buffer for assembling window (little-endian format) */
    uint8_t *window_buf = NULL;

    while (!got_last_chunk) {
        /* Receive one WINDOW_CHUNK frame */
        cortex_frame_type_t frame_type;
        size_t payload_len;

        ret = cortex_protocol_recv_frame(
            transport,
            &frame_type,
            frame_buf,
            sizeof(frame_buf),
            &payload_len,
            timeout_ms
        );

        if (ret < 0) {
            free(window_buf);
            free(received_mask);
            return ret;
        }

        /* Validate frame type */
        if (frame_type != CORTEX_FRAME_WINDOW_CHUNK) {
            free(window_buf);
            free(received_mask);
            return CORTEX_EPROTO_INVALID_FRAME;
        }

        /* Parse chunk header (convert from little-endian) */
        if (payload_len < sizeof(cortex_wire_window_chunk_t)) {
            free(window_buf);
            free(received_mask);
            return CORTEX_EPROTO_INVALID_FRAME;
        }

        uint32_t sequence = cortex_read_u32_le(frame_buf + 0);
        uint32_t chunk_total_bytes = cortex_read_u32_le(frame_buf + 4);
        uint32_t offset = cortex_read_u32_le(frame_buf + 8);
        uint32_t chunk_len = cortex_read_u32_le(frame_buf + 12);
        uint32_t flags = cortex_read_u32_le(frame_buf + 16);

        /* Validate sequence */
        if (sequence != expected_sequence) {
            free(window_buf);
            free(received_mask);
            return CORTEX_ECHUNK_SEQUENCE_MISMATCH;
        }

        /* First chunk: allocate buffers */
        if (total_bytes == 0) {
            total_bytes = chunk_total_bytes;

            /* Validate buffer size */
            if (total_bytes > samples_buf_size) {
                return CORTEX_ECHUNK_BUFFER_TOO_SMALL;
            }

            /* Allocate window buffer */
            window_buf = (uint8_t *)malloc(total_bytes);
            if (!window_buf) {
                return -1;
            }

            /* Allocate received mask (1 byte per byte) */
            received_mask = (uint8_t *)calloc(total_bytes, 1);
            if (!received_mask) {
                free(window_buf);
                return -1;
            }
        } else {
            /* Validate total_bytes matches across chunks */
            if (chunk_total_bytes != total_bytes) {
                free(window_buf);
                free(received_mask);
                return CORTEX_EPROTO_INVALID_FRAME;
            }
        }

        /* Validate chunk bounds */
        if (offset + chunk_len > total_bytes) {
            free(window_buf);
            free(received_mask);
            return CORTEX_EPROTO_INVALID_FRAME;
        }

        /* Validate payload contains chunk header + data */
        if (payload_len != sizeof(cortex_wire_window_chunk_t) + chunk_len) {
            free(window_buf);
            free(received_mask);
            return CORTEX_EPROTO_INVALID_FRAME;
        }

        /* Copy chunk data to window buffer */
        memcpy(window_buf + offset, frame_buf + sizeof(cortex_wire_window_chunk_t), chunk_len);

        /* Mark bytes as received */
        memset(received_mask + offset, 1, chunk_len);
        bytes_received += chunk_len;

        /* Check for LAST flag */
        if (flags & CORTEX_CHUNK_FLAG_LAST) {
            got_last_chunk = 1;
        }
    }

    /* Validate completeness (all bytes received, no gaps) */
    if (bytes_received != total_bytes) {
        free(window_buf);
        free(received_mask);
        return CORTEX_ECHUNK_INCOMPLETE;
    }

    /* Check for gaps in received_mask */
    for (uint32_t i = 0; i < total_bytes; i++) {
        if (received_mask[i] == 0) {
            free(window_buf);
            free(received_mask);
            return CORTEX_ECHUNK_INCOMPLETE;
        }
    }

    /* Convert window from little-endian to host format */
    uint32_t num_samples = total_bytes / sizeof(float);
    for (uint32_t i = 0; i < num_samples; i++) {
        out_samples[i] = cortex_read_f32_le(window_buf + (i * sizeof(float)));
    }

    /* Derive window dimensions (assuming row-major: W×C floats) */
    /* Note: This requires knowing either W or C. For now, return total samples. */
    /* Caller must know dimensions from CONFIG handshake. */
    if (out_window_samples && out_channels) {
        /* This is a placeholder - actual dimensions come from CONFIG */
        *out_window_samples = 0;  /* Caller must set based on CONFIG */
        *out_channels = 0;
    }

    free(window_buf);
    free(received_mask);

    return 0;
}
