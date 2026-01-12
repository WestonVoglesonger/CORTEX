#ifndef CORTEX_WIRE_H
#define CORTEX_WIRE_H

#include <stdint.h>

/*
 * CORTEX Device Adapter Wire Format Definitions
 *
 * ALL data on the wire is little-endian:
 * - Integers: uint8_t, uint16_t, uint32_t, uint64_t (little-endian)
 * - Floats: IEEE-754 float32 (little-endian)
 * - Strings: UTF-8, null-terminated
 *
 * CRITICAL - ARM/STM32 Safety:
 * NEVER cast packed structs directly from wire buffers:
 *   WRONG: hdr = *(cortex_wire_header_t*)buf;
 *   RIGHT: memcpy(&hdr, buf, sizeof(hdr)); convert_endianness(&hdr);
 *
 * Use endian.h conversion helpers (cortex_read_u32_le, etc.)
 */

/* Protocol constants */
#define CORTEX_PROTOCOL_MAGIC   0x43525458  /* "CRTX" */
#define CORTEX_PROTOCOL_VERSION 1

/* Frame size limits */
#define CORTEX_MAX_SINGLE_FRAME (64 * 1024)   /* 64KB for CONFIG/RESULT */
#define CORTEX_CHUNK_SIZE       (8 * 1024)    /* 8KB chunks for WINDOW */
#define CORTEX_MAX_WINDOW_SIZE  (256 * 1024)  /* 256KB max window */

/* Calibration state validation */
#define CORTEX_MAX_PLUGIN_NAME   64  /* Increased to 64 for full spec_uri paths */
#define CORTEX_MAX_PLUGIN_PARAMS 256
#define CORTEX_MAX_ERROR_MESSAGE 256

/* CONFIG calibration state limit */
#define CORTEX_MAX_CALIBRATION_STATE \
    (CORTEX_MAX_SINGLE_FRAME - sizeof(cortex_wire_config_t))

/* Timeouts (milliseconds) */
#define CORTEX_HANDSHAKE_TIMEOUT_MS 5000
#define CORTEX_WINDOW_TIMEOUT_MS    10000
#define CORTEX_CHUNK_TIMEOUT_MS     1000
#define CORTEX_ACCEPT_TIMEOUT_MS    30000  /* TCP server accept timeout (30s for network) */

/* WINDOW_CHUNK flags */
#define CORTEX_CHUNK_FLAG_LAST (1U << 0)  /* Last chunk in sequence */

/*
 * Frame Types
 */
typedef enum {
    CORTEX_FRAME_HELLO        = 0x01,  /* Adapter → Harness (capabilities) */
    CORTEX_FRAME_CONFIG       = 0x02,  /* Harness → Adapter (kernel selection) */
    CORTEX_FRAME_ACK          = 0x03,  /* Adapter → Harness (ready) */
    CORTEX_FRAME_WINDOW_CHUNK = 0x04,  /* Harness → Adapter (input chunk) */
    CORTEX_FRAME_RESULT       = 0x05,  /* Adapter → Harness (output + timing) */
    CORTEX_FRAME_ERROR        = 0x06,  /* Either direction (error report) */
} cortex_frame_type_t;

/*
 * Universal Frame Header (16 bytes, aligned)
 *
 * All frames start with this header.
 *
 * CRC computation:
 *   crc = crc32(0, &header, 12);  // First 12 bytes (excludes crc32 field)
 *   crc = crc32(crc, payload, payload_length);
 */
typedef struct __attribute__((packed)) {
    uint32_t magic;           /* Always CORTEX_PROTOCOL_MAGIC (0x43525458, "CRTX") */
    uint8_t  version;         /* Protocol version (1) */
    uint8_t  frame_type;      /* cortex_frame_type_t */
    uint16_t flags;           /* Reserved (0 for Phase 1) */
    uint32_t payload_length;  /* Bytes following this header */
    uint32_t crc32;           /* CRC over (magic...payload_length) + payload */
} cortex_wire_header_t;

/*
 * HELLO Frame Payload (Adapter → Harness)
 *
 * Adapter advertises capabilities. Boot ID detects adapter restarts.
 *
 * Followed by: num_kernels × char[32] kernel names
 */
typedef struct __attribute__((packed)) {
    uint32_t adapter_boot_id;      /* Random on adapter start */
    char     adapter_name[32];     /* "native", "stm32-h7@uart" */
    uint8_t  adapter_abi_version;  /* 1 */
    uint8_t  num_kernels;          /* Available kernel count */
    uint16_t reserved;             /* Padding */
    uint32_t max_window_samples;   /* Memory constraint */
    uint32_t max_channels;         /* Hardware limit */
    char     device_hostname[32];  /* Device hostname (uname -n) */
    char     device_cpu[32];       /* Device CPU (e.g., "Apple M1", "ARM Cortex-A57") */
    char     device_os[32];        /* Device OS (uname -s -r, e.g., "Darwin 23.2.0") */
} cortex_wire_hello_t;

/*
 * CONFIG Frame Payload (Harness → Adapter)
 *
 * Harness selects kernel and sends configuration. Session ID ties this
 * run to subsequent RESULTs (detects adapter restart/reconnect).
 *
 * Followed by: calibration_state_size bytes of state data
 *
 * VALIDATION REQUIRED:
 *   if (calibration_state_size > CORTEX_MAX_CALIBRATION_STATE) {
 *       return ERROR("Calibration state too large");
 *   }
 */
typedef struct __attribute__((packed)) {
    uint32_t session_id;              /* Random per handshake */
    uint32_t sample_rate_hz;
    uint32_t window_length_samples;
    uint32_t hop_samples;
    uint32_t channels;
    char     plugin_name[CORTEX_MAX_PLUGIN_NAME];
    char     plugin_params[CORTEX_MAX_PLUGIN_PARAMS];
    uint32_t calibration_state_size;  /* 0 if not trainable */
} cortex_wire_config_t;

/*
 * ACK Frame Payload (Adapter → Harness)
 *
 * Acknowledgment with optional output dimension override.
 * If output dimensions are 0, harness uses config dimensions (backward compat).
 */
typedef struct __attribute__((packed)) {
    uint32_t ack_type;                     /* What is being ACKed (0 = CONFIG) */
    uint32_t output_window_length_samples; /* Output W (0 = use config) */
    uint32_t output_channels;              /* Output C (0 = use config) */
} cortex_wire_ack_t;

/*
 * WINDOW_CHUNK Frame Payload (Harness → Adapter)
 *
 * Window data chunked to fit frame size limits. Offset/total allow
 * completeness verification, duplicate detection, future reordering.
 *
 * Followed by: chunk_length bytes of float32 data (little-endian)
 *
 * Flags:
 *   CORTEX_CHUNK_FLAG_LAST: Final chunk in sequence (tin set after this)
 */
typedef struct __attribute__((packed)) {
    uint32_t sequence;         /* Window sequence number */
    uint32_t total_bytes;      /* Total window size (W×C×4 bytes) */
    uint32_t offset_bytes;     /* Offset of this chunk in window */
    uint32_t chunk_length;     /* Bytes in this chunk */
    uint32_t flags;            /* CORTEX_CHUNK_FLAG_LAST, etc. */
} cortex_wire_window_chunk_t;

/*
 * RESULT Frame Payload (Adapter → Harness)
 *
 * Return kernel output and device-side timing. Session ID must match
 * CONFIG session_id (detects adapter restart).
 *
 * Followed by: (output_length_samples × output_channels × 4) bytes
 *
 * Timestamps (nanoseconds, device clock):
 *   tin:       Last input sample arrived and decoded
 *   tstart:    Kernel process() invoked
 *   tend:      Kernel process() returned
 *   tfirst_tx: First result byte transmitted
 *   tlast_tx:  Last result byte transmitted
 */
typedef struct __attribute__((packed)) {
    uint32_t session_id;              /* Must match CONFIG session_id */
    uint32_t sequence;                /* Must match WINDOW sequence */
    uint64_t tin;                     /* Input complete timestamp */
    uint64_t tstart;                  /* Kernel start */
    uint64_t tend;                    /* Kernel end */
    uint64_t tfirst_tx;               /* First result byte tx */
    uint64_t tlast_tx;                /* Last result byte tx */
    uint32_t output_length_samples;
    uint32_t output_channels;
} cortex_wire_result_t;

/*
 * ERROR Frame Payload (Either direction)
 *
 * Error report.
 */
typedef struct __attribute__((packed)) {
    uint32_t error_code;       /* Enum: timeout, invalid, overflow, etc. */
    char     error_message[CORTEX_MAX_ERROR_MESSAGE];
} cortex_wire_error_t;

/* Error codes */
#define CORTEX_ERROR_TIMEOUT            1
#define CORTEX_ERROR_INVALID_FRAME      2
#define CORTEX_ERROR_CALIBRATION_TOOBIG 3
#define CORTEX_ERROR_KERNEL_INIT_FAILED 4
#define CORTEX_ERROR_KERNEL_EXEC_FAILED 5
#define CORTEX_ERROR_SESSION_MISMATCH   6
#define CORTEX_ERROR_VERSION_MISMATCH   7
#define CORTEX_ERROR_SHUTDOWN           8

#endif /* CORTEX_WIRE_H */
