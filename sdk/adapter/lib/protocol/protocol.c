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

        /* Shift window and add new byte */
        window = (window << 8) | byte;

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
