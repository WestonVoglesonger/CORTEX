# CORTEX Device Adapter SDK

**Version**: 1.0 (Phase 1)
**Status**: Production-ready
**Last Updated**: 2025-12-28

The CORTEX Device Adapter SDK enables you to run BCI signal processing kernels on different hardware platforms (x86, Jetson Nano, STM32, etc.) with unified telemetry and consistent performance measurements.

---

## Quick Start

### 1. Understand the Architecture

The SDK has three layers:

```
┌─────────────────────────────────────────┐
│  Your Adapter (main.c)                  │
│  - Handshake logic                      │
│  - Window loop                          │
│  - Kernel loading (platform-specific)   │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  SDK Helper Layer (optional)            │
│  - cortex_adapter_send_hello()          │
│  - cortex_adapter_recv_config()         │
│  - cortex_adapter_send_ack()            │
│  - cortex_adapter_send_result()         │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  SDK Protocol Layer                     │
│  - cortex_protocol_send_frame()         │
│  - cortex_protocol_recv_frame()         │
│  - cortex_protocol_send_window_chunked()│
│  - cortex_protocol_recv_window_chunked()│
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  SDK Transport Layer (you implement)    │
│  - recv(buf, len, timeout_ms)           │
│  - send(buf, len)                       │
│  - close()                              │
│  - get_timestamp_ns()                   │
└─────────────────────────────────────────┘
```

**Key Insight**: The SDK provides **mechanism** (framing, serialization), you provide **policy** (transport I/O, kernel loading).

---

### 2. Include Headers

```c
#include "cortex_transport.h"        /* Transport API */
#include "cortex_protocol.h"          /* Protocol/framing API */
#include "cortex_wire.h"              /* Wire format structs */
#include "cortex_endian.h"            /* Serialization helpers */
#include "cortex_adapter_helpers.h"   /* Optional boilerplate reducers */
```

**What each header provides:**

| Header | Purpose | Required? |
|--------|---------|-----------|
| `cortex_transport.h` | Transport interface (recv/send/close/timestamp) | ✅ Yes |
| `cortex_protocol.h` | Frame I/O functions | ✅ Yes |
| `cortex_wire.h` | Wire format structs (HELLO, CONFIG, EXECUTE, RESULT) | Recommended |
| `cortex_endian.h` | Little-endian serialization helpers | Recommended |
| `cortex_adapter_helpers.h` | Convenience wrappers for common patterns | Optional |

---

### 3. Minimal Adapter Example

Here's a complete adapter in ~50 lines using SDK helpers:

```c
#include "cortex_transport.h"
#include "cortex_protocol.h"
#include "cortex_adapter_helpers.h"

int main(void) {
    /* 1. Create transport (platform-specific) */
    cortex_transport_t *transport = my_transport_create();

    /* 2. Handshake */
    uint32_t boot_id = rand();
    cortex_adapter_send_hello(transport, boot_id, "myplatform@mytransport",
                               "noop@f32", 1024, 64);

    uint32_t session_id, sr, window, hop, ch;
    char plugin[64], params[256];
    cortex_adapter_recv_config(transport, &session_id, &sr, &window, &hop, &ch,
                                plugin, params);

    /* 3. Load kernel (platform-specific) */
    void *kernel = my_load_kernel(plugin, sr, window, hop, ch, params);
    cortex_adapter_send_ack(transport);

    /* 4. Window loop */
    float *input = malloc(window * ch * sizeof(float));
    float *output = malloc(window * ch * sizeof(float));
    uint32_t seq = 0;

    while (1) {
        /* Receive window */
        uint32_t recv_window, recv_ch;
        cortex_protocol_recv_window_chunked(transport, seq, input,
                                             window * ch * sizeof(float),
                                             &recv_window, &recv_ch, 5000);
        uint64_t tin = my_get_timestamp_ns();

        /* Execute kernel */
        uint64_t tstart = my_get_timestamp_ns();
        my_kernel_process(kernel, input, output);
        uint64_t tend = my_get_timestamp_ns();

        /* Send result */
        uint64_t tfirst_tx = my_get_timestamp_ns();
        cortex_adapter_send_result(transport, session_id, seq,
                                    tin, tstart, tend, tfirst_tx, tfirst_tx,
                                    output, window, ch);
        seq++;
    }
}
```

---

## API Reference

### Transport Layer (You Implement)

Create a `cortex_transport_t` struct with these function pointers:

```c
typedef struct {
    void *ctx;  /* Your platform-specific context */

    int (*recv)(void *ctx, void *buf, size_t len, uint32_t timeout_ms);
    int (*send)(void *ctx, const void *buf, size_t len);
    void (*close)(void *ctx);
    uint64_t (*get_timestamp_ns)(void *ctx);
} cortex_transport_t;
```

**recv() contract:**
- **Returns**: Number of bytes read (0...len), or <0 on error
- **Timeout**: Return `CORTEX_ETIMEDOUT` (-1000) if timeout expires
- **Connection closed**: Return `CORTEX_ECONNRESET` (-1001)
- **Blocking**: Must block until bytes available or timeout

**send() contract:**
- **Returns**: Number of bytes written, or <0 on error
- **Blocking**: May block until all bytes written

**See also**: `primitives/adapters/v1/native@loopback/adapter.c` for reference implementation

---

### Protocol Layer Functions

#### cortex_protocol_send_frame()
```c
int cortex_protocol_send_frame(
    cortex_transport_t *transport,
    cortex_frame_type_t frame_type,  /* HELLO, CONFIG, ACK, etc. */
    const void *payload,             /* Wire-format bytes (little-endian) */
    size_t payload_len
);
```

Sends one frame with MAGIC, CRC, and header. Returns 0 on success, <0 on error.

#### cortex_protocol_recv_frame()
```c
int cortex_protocol_recv_frame(
    cortex_transport_t *transport,
    cortex_frame_type_t *out_type,
    void *payload_buf,
    size_t payload_buf_size,
    size_t *out_payload_len,
    uint32_t timeout_ms
);
```

Hunts for MAGIC, reads header, reads payload, validates CRC. Returns 0 on success, <0 on error.

#### cortex_protocol_send_window_chunked()
```c
int cortex_protocol_send_window_chunked(
    cortex_transport_t *transport,
    uint32_t sequence,
    const float *samples,      /* W×C float32 array */
    uint32_t window_samples,
    uint32_t channels
);
```

Breaks large window into 8KB chunks, sends as WINDOW_CHUNK frames. Handles endianness automatically.

#### cortex_protocol_recv_window_chunked()
```c
int cortex_protocol_recv_window_chunked(
    cortex_transport_t *transport,
    uint32_t expected_sequence,
    float *out_samples,
    size_t samples_buf_size,
    uint32_t *out_window_samples,
    uint32_t *out_channels,
    uint32_t timeout_ms
);
```

Receives and reassembles WINDOW_CHUNK frames. Validates sequence, offsets, and completeness.

---

### Adapter Helpers (Optional)

These functions reduce boilerplate but are **entirely optional**. You can use low-level `cortex_protocol_*` functions directly if you need custom behavior.

#### cortex_adapter_send_hello()
```c
int cortex_adapter_send_hello(
    cortex_transport_t *transport,
    uint32_t boot_id,
    const char *adapter_name,        /* e.g., "jetson@tcp" */
    const char *kernel_name,         /* e.g., "noop@f32" (Phase 1: single kernel) */
    uint32_t max_window_samples,
    uint32_t max_channels
);
```

Sends HELLO frame with adapter capabilities.

#### cortex_adapter_recv_config()
```c
int cortex_adapter_recv_config(
    cortex_transport_t *transport,
    uint32_t *out_session_id,
    uint32_t *out_sample_rate_hz,
    uint32_t *out_window_samples,
    uint32_t *out_hop_samples,
    uint32_t *out_channels,
    char *out_plugin_name,      /* [32] buffer */
    char *out_plugin_params     /* [256] buffer */
);
```

Receives CONFIG frame and extracts parameters.

#### cortex_adapter_send_ack()
```c
int cortex_adapter_send_ack(cortex_transport_t *transport);
```

Sends ACK frame (kernel ready).

#### cortex_adapter_send_result()
```c
int cortex_adapter_send_result(
    cortex_transport_t *transport,
    uint32_t session_id,
    uint32_t sequence,
    uint64_t tin,          /* Window reassembly complete timestamp (ns) */
    uint64_t tstart,       /* Kernel execution start (ns) */
    uint64_t tend,         /* Kernel execution end (ns) */
    uint64_t tfirst_tx,    /* First byte transmission start (ns) */
    uint64_t tlast_tx,     /* Last byte transmission end (ns) */
    const float *output_samples,
    uint32_t output_length,
    uint32_t output_channels
);
```

Sends RESULT frame with timing telemetry and output data.

---

## Wire Format Reference

All wire structures are in `cortex_wire.h`. Key formats:

### HELLO Frame
```c
typedef struct {
    uint32_t boot_id;
    char adapter_name[32];
    uint8_t adapter_abi_version;  /* Always 1 for Phase 1 */
    uint8_t num_kernels;           /* Always 1 for Phase 1 */
    uint16_t reserved;
    uint32_t max_window_samples;
    uint32_t max_channels;
    /* Followed by num_kernels × char[32] kernel names */
} cortex_wire_hello_t;
```

### CONFIG Frame
```c
typedef struct {
    uint32_t session_id;
    uint32_t sample_rate_hz;
    uint32_t window_length_samples;
    uint32_t hop_length_samples;
    uint32_t channels;
    char plugin_name[64];
    char plugin_params[256];
    /* Optional: calibration_state_size + calibration_state */
} cortex_wire_config_t;
```

### RESULT Frame
```c
typedef struct {
    uint32_t session_id;
    uint32_t sequence;
    uint64_t tin;
    uint64_t tstart;
    uint64_t tend;
    uint64_t tfirst_tx;
    uint64_t tlast_tx;
    uint32_t output_window_length_samples;
    uint32_t output_channels;
    /* Followed by output_samples (little-endian float32) */
} cortex_wire_result_t;
```

All multi-byte fields are **little-endian**. Use `cortex_read_u32_le()`, `cortex_write_u32_le()`, etc.

---

## Build Integration

### Option 1: Link Against Object Files (Current)

```makefile
CFLAGS = -I../../../../sdk/adapter/include
LIBS = ../../../../sdk/adapter/lib/protocol/protocol.o \
       ../../../../sdk/adapter/lib/protocol/crc32.o \
       ../../../../sdk/adapter/lib/transport/mock.o \
       ../../../../sdk/adapter/lib/adapter_helpers/adapter_helpers.o

my_adapter: my_adapter.c $(LIBS)
    $(CC) $(CFLAGS) -o $@ my_adapter.c $(LIBS) -ldl -lpthread
```

### Option 2: Build as Static Library (Future)

```bash
cd sdk/adapter && make libcortex_adapter.a
gcc -o my_adapter my_adapter.c -L../../sdk/adapter -lcortex_adapter
```

---

## Error Codes

```c
/* Transport errors */
#define CORTEX_ETIMEDOUT     -1000  /* Timeout waiting for data */
#define CORTEX_ECONNRESET    -1001  /* Connection closed */

/* Protocol errors */
#define CORTEX_EPROTO_MAGIC_NOT_FOUND  -2000  /* MAGIC not found */
#define CORTEX_EPROTO_CRC_MISMATCH     -2001  /* CRC validation failed */
#define CORTEX_EPROTO_INVALID_FRAME    -2005  /* Invalid frame structure */

/* Chunking errors */
#define CORTEX_ECHUNK_SEQUENCE_MISMATCH -2100  /* Wrong sequence number */
#define CORTEX_ECHUNK_INCOMPLETE        -2101  /* Missing chunks */
#define CORTEX_ECHUNK_BUFFER_TOO_SMALL  -2102  /* Buffer overflow */
```

---

## Platform Examples

### native@loopback (stdin/stdout)
See `primitives/adapters/v1/native@loopback/adapter.c` - production reference implementation.

### Future: Jetson@TCP
```c
cortex_transport_t *transport = cortex_transport_tcp_client_create("192.168.1.100", 8080);
```

### Future: STM32@UART
```c
cortex_transport_t *transport = cortex_transport_uart_stm32_create(USART1, 115200);
```

---

## FAQ

**Q: Can I skip the helper functions?**
Yes! They're optional convenience wrappers. Use `cortex_protocol_send_frame()` directly if you need custom behavior.

**Q: Do I need to handle endianness?**
Yes - the wire format is little-endian. Use `cortex_read_*_le()` and `cortex_write_*_le()` helpers from `cortex_endian.h`.

**Q: Can I modify wire_format.h?**
No - it's part of the protocol spec. Changes break compatibility. File feature requests instead.

**Q: How do I debug protocol issues?**
Enable hex dumps in protocol.c or use Wireshark/tcpdump for TCP transports.

**Q: Where's the kernel loading code?**
Platform-specific - see `load_kernel_plugin()` in native@loopback adapter for dlopen() example.

---

## See Also

- **Wire Protocol Spec**: `ADAPTER_IMPLEMENTATION.md` (detailed protocol description)
- **Reference Adapter**: `primitives/adapters/v1/native@loopback/adapter.c`
- **Kernel ABI**: `src/engine/include/cortex_plugin.h`
- **Test Examples**: `tests/test_adapter_smoke.c`, `tests/test_adapter_all_kernels.c`

---

**Questions?** File an issue at https://github.com/WestonVoglesonger/CORTEX/issues
