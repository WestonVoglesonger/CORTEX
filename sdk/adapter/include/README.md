# CORTEX Adapter SDK - API Reference

**Directory:** `sdk/adapter/include/`
**Purpose:** Public API headers for building device adapters
**Version:** 1.0 (Adapter Protocol ABI v1)

This directory contains the **complete public API** for the CORTEX Device Adapter SDK. These headers define the interfaces for communication between harness and adapters across different platforms (x86, Jetson, STM32, etc.).

---

## Header Files

| Header | Purpose | Key Types | Documentation |
|--------|---------|-----------|---------------|
| **[cortex_transport.h](#cortex_transporth)** | Transport layer abstraction | `cortex_transport_t` | [Transport Layer Guide](../lib/transport/README.md) |
| **[cortex_protocol.h](#cortex_protocolh)** | Protocol frame I/O | `cortex_frame_type_t` | [Protocol Spec](../lib/protocol/README.md) |
| **[cortex_wire.h](#cortex_wireh)** | Wire format definitions | `cortex_wire_header_t` | [Protocol Spec](../lib/protocol/README.md) |
| **[cortex_endian.h](#cortex_endianh)** | Endianness conversion | `cortex_read_u32_le()` | [Protocol Spec](../lib/protocol/README.md) |
| **[cortex_adapter_helpers.h](#cortex_adapter_helpersh)** | High-level helpers | `cortex_adapter_send_hello()` | [Helpers Guide](#adapter-helpers-api) |

---

## cortex_transport.h

**Purpose:** Platform-independent I/O abstraction for byte streams (socketpair, TCP, UART, etc.)

### Key Type

```c
typedef struct cortex_transport_api {
    void *ctx;  /* Transport-specific context (opaque) */

    /* Send data (blocking until complete or error) */
    ssize_t (*send)(void *ctx, const void *buf, size_t len);

    /* Receive data (blocking with timeout) */
    ssize_t (*recv)(void *ctx, void *buf, size_t len, uint32_t timeout_ms);

    /* Close transport and free resources */
    void (*close)(void *ctx);

    /* Get high-precision timestamp (nanoseconds, monotonic) */
    uint64_t (*get_timestamp_ns)(void);
} cortex_transport_api_t;

typedef cortex_transport_api_t cortex_transport_t;  /* Convenience alias */
```

### Error Codes

```c
#define CORTEX_ETIMEDOUT   -1000  /* recv() timeout expired */
#define CORTEX_ECONNRESET  -1001  /* Connection closed/reset */
```

### Available Transports

**Local (same machine):**
```c
/* Socketpair (stdin/stdout) - for loopback adapters */
cortex_transport_t* cortex_transport_mock_create(int fd);
cortex_transport_t* cortex_transport_mock_create_from_fds(int read_fd, int write_fd);

/* Shared memory (POSIX shm_open) - for benchmarking */
cortex_transport_t* cortex_transport_shm_create_harness(const char *name);
cortex_transport_t* cortex_transport_shm_create_adapter(const char *name);
```

**Network:**
```c
/* TCP client - for Jetson, Pi, remote hosts */
cortex_transport_t* cortex_transport_tcp_client_create(
    const char *host, uint16_t port, uint32_t timeout_ms);
```

**Serial:**
```c
/* UART POSIX (termios) - for USB-to-serial, Raspberry Pi GPIO */
cortex_transport_t* cortex_transport_uart_posix_create(
    const char *device, uint32_t baud_rate);
```

**Complete documentation:** [`../lib/transport/README.md`](../lib/transport/README.md)

---

## cortex_protocol.h

**Purpose:** Frame-based communication over byte-stream transports (framing, CRC, chunking)

### Key Functions

#### Send/Receive Single Frame

```c
/* Send one complete frame with CRC */
int cortex_protocol_send_frame(
    cortex_transport_t *transport,
    cortex_frame_type_t frame_type,
    const void *payload,        /* MUST be little-endian wire format */
    size_t payload_len
);

/* Receive one complete frame with MAGIC hunting and CRC validation */
int cortex_protocol_recv_frame(
    cortex_transport_t *transport,
    cortex_frame_type_t *out_type,
    void *payload_buf,           /* Filled with little-endian wire format */
    size_t payload_buf_size,
    size_t *out_payload_len,
    uint32_t timeout_ms
);
```

#### Chunked Window Transfer

```c
/* Send large window as multiple 8KB chunks */
int cortex_protocol_send_window_chunked(
    cortex_transport_t *transport,
    uint32_t sequence,
    const float *samples,        /* Host format (NOT little-endian) */
    uint32_t window_samples,
    uint32_t channels
);

/* Receive and reassemble window from chunks */
int cortex_protocol_recv_window_chunked(
    cortex_transport_t *transport,
    uint32_t expected_sequence,
    float *out_samples,          /* Host format output */
    size_t samples_buf_size,
    uint32_t *out_window_samples,
    uint32_t *out_channels,
    uint32_t timeout_ms
);
```

### Error Codes

```c
/* Protocol errors */
#define CORTEX_EPROTO_MAGIC_NOT_FOUND  -2000
#define CORTEX_EPROTO_CRC_MISMATCH     -2001
#define CORTEX_EPROTO_VERSION_MISMATCH -2002
#define CORTEX_EPROTO_FRAME_TOO_LARGE  -2003
#define CORTEX_EPROTO_BUFFER_TOO_SMALL -2004
#define CORTEX_EPROTO_INVALID_FRAME    -2005

/* Chunking errors */
#define CORTEX_ECHUNK_SEQUENCE_MISMATCH -2100
#define CORTEX_ECHUNK_INCOMPLETE        -2101
#define CORTEX_ECHUNK_BUFFER_TOO_SMALL  -2102
```

**Complete documentation:** [`../lib/protocol/README.md`](../lib/protocol/README.md)

---

## cortex_wire.h

**Purpose:** Wire format definitions (frame types, payload structures, constants)

### Frame Types

```c
typedef enum {
    CORTEX_FRAME_HELLO        = 0x01,  /* Adapter → Harness (capabilities) */
    CORTEX_FRAME_CONFIG       = 0x02,  /* Harness → Adapter (kernel selection) */
    CORTEX_FRAME_ACK          = 0x03,  /* Adapter → Harness (ready) */
    CORTEX_FRAME_WINDOW_CHUNK = 0x04,  /* Harness → Adapter (input chunk) */
    CORTEX_FRAME_RESULT       = 0x05,  /* Adapter → Harness (output + timing) */
    CORTEX_FRAME_ERROR        = 0x06,  /* Either direction (error report) */
} cortex_frame_type_t;
```

### Wire Format Structs

**All structs are `__attribute__((packed))` and use little-endian byte order.**

```c
/* Universal header (16 bytes) */
typedef struct __attribute__((packed)) {
    uint32_t magic;           /* 0x43525458 ("CRTX") */
    uint8_t  version;         /* Protocol version (1) */
    uint8_t  frame_type;      /* cortex_frame_type_t */
    uint16_t flags;           /* Reserved (0 for Phase 1) */
    uint32_t payload_length;  /* Bytes following this header */
    uint32_t crc32;           /* CRC over header[0:12] + payload */
} cortex_wire_header_t;

/* HELLO payload */
typedef struct __attribute__((packed)) {
    uint32_t adapter_boot_id;      /* Random on adapter start */
    char     adapter_name[32];     /* "x86@loopback" */
    uint8_t  adapter_abi_version;  /* 1 */
    uint8_t  num_kernels;          /* Available kernel count */
    uint16_t reserved;
    uint32_t max_window_samples;
    uint32_t max_channels;
    /* Followed by: num_kernels × char[32] kernel names */
} cortex_wire_hello_t;

/* CONFIG payload */
typedef struct __attribute__((packed)) {
    uint32_t session_id;              /* Random per handshake */
    uint32_t sample_rate_hz;
    uint32_t window_length_samples;
    uint32_t hop_samples;
    uint32_t channels;
    char     plugin_name[32];
    char     plugin_params[256];
    uint32_t calibration_state_size;
    /* Followed by: calibration_state_size bytes */
} cortex_wire_config_t;

/* WINDOW_CHUNK payload */
typedef struct __attribute__((packed)) {
    uint32_t sequence;
    uint32_t total_bytes;
    uint32_t offset_bytes;
    uint32_t chunk_length;
    uint32_t flags;          /* CORTEX_CHUNK_FLAG_LAST (1<<0) */
    /* Followed by: chunk_length bytes of float32 data */
} cortex_wire_window_chunk_t;

/* RESULT payload */
typedef struct __attribute__((packed)) {
    uint32_t session_id;
    uint32_t sequence;
    uint64_t tin;                     /* Device: input complete */
    uint64_t tstart;                  /* Device: kernel start */
    uint64_t tend;                    /* Device: kernel end */
    uint64_t tfirst_tx;               /* Device: first result byte tx */
    uint64_t tlast_tx;                /* Device: last result byte tx */
    uint32_t output_length_samples;
    uint32_t output_channels;
    /* Followed by: (output_length × output_channels × 4) bytes */
} cortex_wire_result_t;
```

### Constants

```c
#define CORTEX_PROTOCOL_MAGIC   0x43525458        /* "CRTX" */
#define CORTEX_PROTOCOL_VERSION 1

#define CORTEX_MAX_SINGLE_FRAME (64 * 1024)       /* 64KB */
#define CORTEX_CHUNK_SIZE       (8 * 1024)        /* 8KB */
#define CORTEX_MAX_WINDOW_SIZE  (256 * 1024)      /* 256KB */

#define CORTEX_HANDSHAKE_TIMEOUT_MS 5000
#define CORTEX_WINDOW_TIMEOUT_MS    10000
#define CORTEX_CHUNK_TIMEOUT_MS     1000
```

**Complete documentation:** [`../lib/protocol/README.md`](../lib/protocol/README.md)

---

## cortex_endian.h

**Purpose:** Safe endianness conversion (wire format ↔ host format)

### Why Little-Endian?

**ALL wire format data uses little-endian byte order:**
- x86/x86_64 is little-endian (most dev/test platforms)
- ARM Cortex-M is little-endian by default (STM32, ESP32)
- Conversion is no-op on little-endian hosts (compiler optimizes away)

### Conversion Functions

**Read from wire (little-endian → host):**
```c
uint16_t cortex_read_u16_le(const uint8_t *buf);
uint32_t cortex_read_u32_le(const uint8_t *buf);
uint64_t cortex_read_u64_le(const uint8_t *buf);
float    cortex_read_f32_le(const uint8_t *buf);
```

**Write to wire (host → little-endian):**
```c
void cortex_write_u16_le(uint8_t *buf, uint16_t val);
void cortex_write_u32_le(uint8_t *buf, uint32_t val);
void cortex_write_u64_le(uint8_t *buf, uint64_t val);
void cortex_write_f32_le(uint8_t *buf, float val);
```

### Critical Safety Rule

**NEVER cast packed structs directly on ARM:**

```c
/* WRONG (causes alignment fault on ARM Cortex-M): */
cortex_wire_header_t *hdr = (cortex_wire_header_t *)buf;
uint32_t magic = hdr->magic;  /* FAULT: buf may not be 4-byte aligned */

/* RIGHT (always safe): */
uint32_t magic = cortex_read_u32_le(buf + 0);
uint8_t version = buf[4];
uint32_t payload_len = cortex_read_u32_le(buf + 8);
```

**Why:**
- ARM Cortex-M requires 4-byte alignment for 32-bit loads
- Unaligned access causes **hard fault** (crash)
- `memcpy()` handles unaligned buffers correctly
- Compiler optimizes `memcpy()` to single instruction on aligned buffers

**Complete documentation:** [`../lib/protocol/README.md`](../lib/protocol/README.md)

---

## cortex_adapter_helpers.h

**Purpose:** High-level convenience functions for common adapter operations

### Handshake Helpers

```c
/* Send HELLO frame (adapter → harness) */
int cortex_adapter_send_hello(
    cortex_transport_t *transport,
    uint32_t boot_id,
    const char *adapter_name,       /* "x86@loopback" */
    const char *kernel_names,       /* "noop@f32,car@f32" (comma-separated) */
    uint32_t max_window_samples,
    uint32_t max_channels
);

/* Receive CONFIG frame (harness → adapter) */
int cortex_adapter_recv_config(
    cortex_transport_t *transport,
    uint32_t *out_session_id,       /* Random session ID */
    uint32_t *out_sample_rate_hz,
    uint32_t *out_window_samples,
    uint32_t *out_hop_samples,
    uint32_t *out_channels,
    char *out_plugin_name,          /* Buffer size: 32 bytes */
    char *out_plugin_params         /* Buffer size: 256 bytes */
);

/* Send ACK frame (adapter → harness) */
int cortex_adapter_send_ack(cortex_transport_t *transport);
```

### Result Helper

```c
/* Send RESULT frame (adapter → harness) */
int cortex_adapter_send_result(
    cortex_transport_t *transport,
    uint32_t session_id,
    uint32_t sequence,
    uint64_t tin,
    uint64_t tstart,
    uint64_t tend,
    uint64_t tfirst_tx,
    uint64_t tlast_tx,
    const float *output_samples,    /* Host format */
    uint32_t output_length_samples,
    uint32_t output_channels
);
```

### Typical Usage (Adapter Main Loop)

```c
#include "cortex_transport.h"
#include "cortex_protocol.h"
#include "cortex_adapter_helpers.h"

int main(void) {
    /* 1. Create transport */
    cortex_transport_t *transport = cortex_transport_mock_create_from_fds(
        STDIN_FILENO, STDOUT_FILENO
    );

    /* 2. Send HELLO */
    uint32_t boot_id = generate_boot_id();
    cortex_adapter_send_hello(transport, boot_id, "x86@loopback", "noop@f32", 1024, 64);

    /* 3. Receive CONFIG */
    uint32_t session_id, sample_rate, window_samples, hop_samples, channels;
    char plugin_name[64], plugin_params[256];
    cortex_adapter_recv_config(transport, &session_id, &sample_rate,
                               &window_samples, &hop_samples, &channels,
                               plugin_name, plugin_params);

    /* 4. Load kernel (platform-specific) */
    kernel_handle = load_kernel(plugin_name, sample_rate, window_samples, ...);

    /* 5. Send ACK */
    cortex_adapter_send_ack(transport);

    /* 6. Window loop */
    uint32_t sequence = 0;
    float *window_buf = malloc(window_samples * channels * sizeof(float));
    float *output_buf = malloc(...);

    while (1) {
        /* Receive WINDOW */
        int ret = cortex_protocol_recv_window_chunked(
            transport, sequence, window_buf, ...
        );
        if (ret < 0) break;  /* Timeout or error */

        /* Process */
        uint64_t tin = get_timestamp_ns();
        uint64_t tstart = get_timestamp_ns();
        kernel_process(kernel_handle, window_buf, output_buf);
        uint64_t tend = get_timestamp_ns();

        /* Send RESULT */
        uint64_t tfirst_tx = get_timestamp_ns();
        cortex_adapter_send_result(transport, session_id, sequence,
                                   tin, tstart, tend, tfirst_tx, tfirst_tx,
                                   output_buf, output_length, output_channels);

        sequence++;
    }

    /* Cleanup */
    free(window_buf);
    free(output_buf);
    kernel_teardown(kernel_handle);
    transport->close(transport->ctx);
    free(transport);

    return 0;
}
```

---

## Building with the SDK

### Compiler Flags

```makefile
CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11

# Include SDK headers
INCLUDES = -I../../../sdk/adapter/include -I../../../sdk/kernel/include
```

### Linking

```makefile
# SDK object files (not yet built as static library)
PROTOCOL_OBJS = ../../../sdk/adapter/lib/protocol/protocol.o \
                ../../../sdk/adapter/lib/protocol/crc32.o

TRANSPORT_OBJS = ../../../sdk/adapter/lib/transport/local/mock.o
# Or: ../../../sdk/adapter/lib/transport/network/tcp_client.o
# Or: ../../../sdk/adapter/lib/transport/serial/uart_posix.o

ADAPTER_HELPERS_OBJS = ../../../sdk/adapter/lib/adapter_helpers/adapter_helpers.o

$(TARGET): adapter.o $(PROTOCOL_OBJS) $(TRANSPORT_OBJS) $(ADAPTER_HELPERS_OBJS)
	$(CC) -o $@ $^ -ldl -lpthread
```

### Example: x86@loopback Adapter

**Complete example:** [`../../../primitives/adapters/v1/x86@loopback/`](../../../primitives/adapters/v1/x86@loopback/)

---

## Platform Compatibility

| Feature | macOS | Linux | STM32 (bare-metal) |
|---------|-------|-------|-------------------|
| **mock transport** | ✅ Yes | ✅ Yes | ❌ No (no fork/exec) |
| **tcp_client** | ✅ Yes | ✅ Yes | ⚠️ With lwIP stack |
| **uart_posix** | ✅ Yes | ✅ Yes | ❌ No (use uart_stm32) |
| **shm transport** | ✅ Yes | ✅ Yes | ❌ No (no POSIX SHM) |
| **Endian helpers** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Protocol layer** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Dynamic loading** | ✅ dlopen | ✅ dlopen | ❌ Static linking |

---

## Troubleshooting

### "undefined reference to cortex_protocol_send_frame"

**Cause:** Not linking against protocol object files

**Fix:**
```makefile
PROTOCOL_OBJS = ../../../sdk/adapter/lib/protocol/protocol.o \
                ../../../sdk/adapter/lib/protocol/crc32.o

$(TARGET): adapter.o $(PROTOCOL_OBJS)
	$(CC) -o $@ $^ -ldl -lpthread
```

### "cortex_transport.h: No such file or directory"

**Cause:** Missing include path

**Fix:**
```makefile
INCLUDES = -I../../../sdk/adapter/include

%.o: %.c
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@
```

### "Segmentation fault in cortex_read_u32_le"

**Cause:** Passing NULL pointer or invalid buffer

**Debug:**
```c
/* Add bounds checking */
if (!buf) {
    fprintf(stderr, "NULL buffer in cortex_read_u32_le\n");
    abort();
}
```

### "CORTEX_EPROTO_CRC_MISMATCH on every frame"

**Cause:** Endianness bug (writing host format instead of little-endian)

**Fix:** Use `cortex_write_*_le()` helpers:
```c
/* WRONG: */
memcpy(buf, &value, sizeof(value));  /* Host byte order */

/* RIGHT: */
cortex_write_u32_le(buf, value);  /* Little-endian wire format */
```

---

## See Also

- **Detailed Protocol Specification:** [`../lib/protocol/README.md`](../lib/protocol/README.md)
- **Transport Layer Guide:** [`../lib/transport/README.md`](../lib/transport/README.md)
- **Adapter Examples:** [`../../../primitives/adapters/v1/`](../../../primitives/adapters/v1/)
- **SDK Overview:** [`../README.md`](../README.md)
- **Implementation Plan:** [`../../../ADAPTER_IMPLEMENTATION.md`](../../../ADAPTER_IMPLEMENTATION.md)
