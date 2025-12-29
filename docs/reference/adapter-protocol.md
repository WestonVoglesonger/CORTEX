# CORTEX Device Adapter Protocol - Wire Format Specification

**Version:** 1.0 (ABI v1)
**Status:** Stable (Phase 1 Complete)
**Last Updated:** 2025-12-29

---

## Overview

The CORTEX adapter protocol defines the wire format for communication between the harness and device adapters. It enables reliable kernel execution across different hardware platforms (x86, Jetson Nano, STM32, etc.) via standardized framing over byte-stream transports (TCP, UART, socketpair).

### Key Features

- **Reliable framing** over unreliable byte streams
- **CRC32 validation** on every frame (IEEE 802.3 polynomial)
- **Little-endian wire format** (platform-independent)
- **Chunked transfer** for large data windows (8KB chunks)
- **Session/boot ID tracking** for restart detection
- **Timeout-based error handling** (no infinite hangs)

### Protocol Stack

```
┌──────────────────────────────────────────┐
│  Application Layer                       │
│  (Handshake, Kernel Execution, Timing)   │
├──────────────────────────────────────────┤
│  Protocol Layer (This Spec)              │
│  - Framing (MAGIC hunting)               │
│  - CRC32 validation                      │
│  - Endianness conversion                 │
│  - Chunking (8KB max per frame)          │
├──────────────────────────────────────────┤
│  Transport Layer                         │
│  - TCP (network)                         │
│  - UART (serial)                         │
│  - Socketpair (local loopback)           │
└──────────────────────────────────────────┘
```

---

## Wire Format

All multi-byte values are transmitted in **little-endian** byte order.

### Frame Structure

Every frame consists of a 16-byte header followed by a variable-length payload:

```
┌────────────────────────────────────────────────────────────┐
│                 Universal Frame Header (16 bytes)          │
├────────────┬────────┬───────────┬────────┬────────┬────────┤
│   MAGIC    │Version │Frame Type │ Flags  │Payload │  CRC32 │
│  (4 bytes) │(1 byte)│  (1 byte) │(2 bytes│  Len   │(4 bytes│
│ 0x43525458 │   1    │  0x01-06  │  0x00  │  N     │  ....  │
└────────────┴────────┴───────────┴────────┴────────┴────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│                   Payload (N bytes)                        │
│  Content depends on frame type (see Frame Types below)     │
└────────────────────────────────────────────────────────────┘
```

### Header Fields

| Field | Bytes | Offset | Value | Description |
|-------|-------|--------|-------|-------------|
| `magic` | 4 | 0 | `0x43525458` | Frame start marker ("CRTX" in ASCII) |
| `version` | 1 | 4 | `1` | Protocol version (must match) |
| `frame_type` | 1 | 5 | `0x01`-`0x06` | Message type (see table below) |
| `flags` | 2 | 6 | `0x0000` | Reserved (always 0 in Phase 1) |
| `payload_length` | 4 | 8 | `0`-`65536` | Payload size in bytes |
| `crc32` | 4 | 12 | computed | CRC32 over header[0:12] + payload |

**Total header size:** 16 bytes (aligned for ARM compatibility)

### MAGIC Constant

**Value:** `0x43525458` (ASCII "CRTX")
**Wire bytes (little-endian):** `0x58, 0x54, 0x52, 0x43`

The MAGIC constant serves as a frame boundary marker in byte streams. Receivers use sliding-window search to locate frame starts.

### CRC32 Computation

**Algorithm:** IEEE 802.3 polynomial (same as Ethernet, ZIP, PNG)

**Computation:**
1. Initialize CRC to 0
2. Compute over header bytes [0:12] (excludes CRC field)
3. Continue computation over entire payload
4. Write result to header bytes [12:16]

**Validation:**
- Read CRC from wire (header[12:16])
- Recompute CRC over header[0:12] + payload
- Compare: if mismatch, discard frame and return `CORTEX_EPROTO_CRC_MISMATCH`

**Error Detection:**
- Detects: bit flips, byte corruption, truncation, reordering
- False acceptance rate: ~1 in 4 billion
- Performance: ~1 GB/s with table lookup

---

## Frame Types

### Summary

| Type | Value | Direction | Payload Size | Purpose |
|------|-------|-----------|--------------|---------|
| **HELLO** | `0x01` | Adapter → Harness | 48 + (N×32) bytes | Advertise capabilities |
| **CONFIG** | `0x02` | Harness → Adapter | 332 + state_size | Configure kernel |
| **ACK** | `0x03` | Adapter → Harness | 32 bytes | Acknowledge CONFIG |
| **WINDOW_CHUNK** | `0x04` | Harness → Adapter | 32 + sample_data | Send input chunk |
| **RESULT** | `0x05` | Adapter → Harness | 112 + output_data | Return kernel output |
| **ERROR** | `0x06` | Either direction | 32 bytes | Report error |

---

### HELLO Frame (0x01)

**Direction:** Adapter → Harness
**Purpose:** Advertise adapter capabilities and available kernels
**When:** First message after transport connection established

**Payload:**
```c
struct {
    uint32_t adapter_boot_id;      // Random on adapter start
    char     adapter_name[32];     // "x86@loopback", "jetson@tcp"
    uint8_t  adapter_abi_version;  // Must be 1
    uint8_t  num_kernels;          // Count of available kernels
    uint16_t reserved;             // Padding (0)
    uint32_t max_window_samples;   // Memory constraint
    uint32_t max_channels;         // Hardware limit
    // Followed by: num_kernels × char[32] kernel names
} __attribute__((packed));

// Total payload: 48 + (num_kernels × 32) bytes
```

**Example:**
```
adapter_boot_id:     0x12345678
adapter_name:        "x86@loopback"
adapter_abi_version: 1
num_kernels:         2
max_window_samples:  512
max_channels:        64

Kernel names:
  [0] "bandpass_fir@f32"
  [1] "car@f32"

Payload size: 48 + (2 × 32) = 112 bytes
```

---

### CONFIG Frame (0x02)

**Direction:** Harness → Adapter
**Purpose:** Select kernel, send parameters, provide calibration state
**When:** After receiving HELLO

**Payload:**
```c
struct {
    uint32_t session_id;              // Random per handshake
    uint32_t sample_rate_hz;          // 160, 250, 500, etc.
    uint32_t window_length_samples;   // W (e.g., 160)
    uint32_t hop_samples;             // H (e.g., 80)
    uint32_t channels;                // C (e.g., 64)
    char     plugin_name[64];         // "primitives/kernels/v1/ica@f32"
    char     plugin_params[256];      // "lowcut=8,highcut=30"
    uint32_t calibration_state_size;  // Bytes of state (0 if not trainable)
    // Followed by: calibration_state_size bytes of state data
} __attribute__((packed));

// Total payload: 340 + calibration_state_size bytes
```

**Validation:**
- `session_id` must be non-zero
- `sample_rate_hz` > 0
- `window_length_samples` ≤ `max_window_samples` from HELLO
- `channels` ≤ `max_channels` from HELLO
- `plugin_name` must match advertised kernel in HELLO
- `calibration_state_size` ≤ 64KB

---

### ACK Frame (0x03)

**Direction:** Adapter → Harness
**Purpose:** Acknowledge CONFIG and report output dimensions
**When:** After successfully loading kernel

**Payload:**
```c
struct {
    uint32_t session_id;         // Echo from CONFIG
    uint32_t error_code;         // 0 = success
    uint32_t output_width;       // Kernel output W (may differ from input)
    uint32_t output_height;      // Kernel output H (may differ from input)
    uint32_t output_dtype;       // Data type bitmask
    uint32_t reserved[3];        // Padding (0)
} __attribute__((packed));

// Total payload: 32 bytes
```

**Notes:**
- Most kernels: `output_width == input W`, `output_height == input C`
- Dimension-changing kernels (e.g., Welch PSD): advertise new dimensions here
- Harness dynamically allocates output buffer based on these values

---

### WINDOW_CHUNK Frame (0x04)

**Direction:** Harness → Adapter
**Purpose:** Send input window data (chunked for large windows)
**When:** After receiving ACK, for each window to process

**Payload:**
```c
struct {
    uint32_t sequence;           // Increments per window
    uint32_t chunk_offset;       // Byte offset in full window
    uint32_t chunk_total;        // Total window size in bytes
    uint8_t  flags;              // CORTEX_WINDOW_CHUNK_LAST if final chunk
    uint8_t  reserved[15];       // Padding (0)
    // Followed by: chunk_data (≤8KB per chunk)
} __attribute__((packed));

// Total payload: 32 + chunk_data_size bytes
```

**Chunking:**
- Max chunk size: 8KB (8192 bytes)
- Large windows split across multiple WINDOW_CHUNK frames
- Example: 40KB window → 5 chunks of 8KB each
- Adapter reassembles chunks by tracking `chunk_offset` and `chunk_total`
- Last chunk has `flags & CORTEX_WINDOW_CHUNK_LAST` set

---

### RESULT Frame (0x05)

**Direction:** Adapter → Harness
**Purpose:** Return kernel output and timing data
**When:** After processing complete window

**Payload:**
```c
struct {
    uint32_t session_id;         // Must match CONFIG
    uint32_t sequence;           // Must match WINDOW sequence
    uint32_t error_code;         // 0 = success
    uint32_t reserved1;          // Padding (0)

    // Device-side timing (nanoseconds since adapter boot)
    uint64_t device_tin_ns;      // Time adapter received last chunk
    uint64_t device_tstart_ns;   // Time kernel execution started
    uint64_t device_tend_ns;     // Time kernel execution finished
    uint64_t device_tfirst_tx_ns; // Time first RESULT byte sent
    uint64_t device_tlast_tx_ns;  // Time last RESULT byte sent

    uint32_t output_size;        // Bytes of output data
    uint32_t output_width;       // Echo from ACK
    uint32_t output_height;      // Echo from ACK
    uint32_t reserved2[9];       // Padding (0)

    // Followed by: output_size bytes of kernel output
} __attribute__((packed));

// Total payload: 112 + output_size bytes
```

**Timing Fields:**
- All timestamps are **relative to adapter boot** (not wall clock)
- Harness uses these to compute adapter overhead
- Processing latency = `device_tend_ns - device_tstart_ns`

---

### ERROR Frame (0x06)

**Direction:** Either (usually Adapter → Harness)
**Purpose:** Report error condition
**When:** Any time an error occurs

**Payload:**
```c
struct {
    uint32_t error_code;         // CORTEX_E* error code
    uint32_t sequence;           // Window sequence if applicable (else 0)
    char     error_message[512]; // Human-readable description
} __attribute__((packed));

// Total payload: 520 bytes
```

**Common Error Codes:**
- `CORTEX_EPROTO_MAGIC_NOT_FOUND` - Invalid frame header
- `CORTEX_EPROTO_CRC_MISMATCH` - Frame corruption detected
- `CORTEX_EPROTO_VERSION_MISMATCH` - Protocol version incompatible
- `CORTEX_E_KERNEL_NOT_FOUND` - Requested kernel unavailable
- `CORTEX_E_KERNEL_INIT_FAILED` - Kernel initialization failed
- `CORTEX_ETIMEDOUT` - recv() timeout expired

---

## Communication Protocol (Sequence Diagrams)

### Handshake Sequence

```
Harness                                    Adapter
   │                                          │
   │◄──────────── HELLO ────────────────────│  (Advertise capabilities)
   │                                          │
   │────────────► CONFIG ───────────────────►│  (Select kernel, send params)
   │                                          │
   │                                          │  [Load kernel, allocate buffers]
   │                                          │
   │◄──────────── ACK ──────────────────────│  (Report output dimensions)
   │                                          │
   │  [Handshake complete - ready for windows]
```

### Window Execution Sequence

```
Harness                                    Adapter
   │                                          │
   │────► WINDOW_CHUNK (seq=1, chunk 1/5) ──►│
   │────► WINDOW_CHUNK (seq=1, chunk 2/5) ──►│
   │────► WINDOW_CHUNK (seq=1, chunk 3/5) ──►│
   │────► WINDOW_CHUNK (seq=1, chunk 4/5) ──►│
   │────► WINDOW_CHUNK (seq=1, chunk 5/5) ──►│  [Reassemble window]
   │                                          │
   │                                          │  [Execute kernel]
   │                                          │
   │◄───────── RESULT (seq=1) ───────────────│  (Output + timing)
   │                                          │
   │  [Repeat for each window...]
```

### Error Handling

```
Harness                                    Adapter
   │                                          │
   │────► WINDOW_CHUNK (corrupted) ─────────►│
   │                                          │  [CRC validation fails]
   │                                          │
   │◄───────── ERROR (CRC_MISMATCH) ─────────│
   │                                          │
   │  [Retry or abort based on policy]
```

---

## Implementation Notes

### Endianness Conversion

All multi-byte values must be converted to/from little-endian on the wire:

```c
// Writing to wire
void cortex_write_u32_le(uint8_t *buf, uint32_t value);
void cortex_write_u64_le(uint8_t *buf, uint64_t value);

// Reading from wire
uint32_t cortex_read_u32_le(const uint8_t *buf);
uint64_t cortex_read_u64_le(const uint8_t *buf);
```

**Why?** Ensures ARM ↔ x86 compatibility regardless of host byte order.

### MAGIC Hunting

When starting or recovering from corruption, receivers use sliding-window search:

```c
uint32_t window = 0;
for (;;) {
    uint8_t byte;
    if (recv_byte(&byte) != 0) return ETIMEDOUT;

    window = (window << 8) | byte;
    if (window == CORTEX_PROTOCOL_MAGIC) {
        // Found frame start!
        break;
    }
}
```

### Timeout Handling

**All `recv()` operations MUST have timeouts** to prevent hangs on adapter death:

```c
int cortex_transport_recv_timeout(transport_t *t, void *buf, size_t len,
                                  uint32_t timeout_ms);
```

Typical timeout values:
- **Handshake:** 5000ms (adapter may be loading kernels)
- **Window processing:** 1000ms (kernel execution + transfer)
- **Error frames:** 500ms (fast failure)

---

## Version History

### Protocol Version 1 (Current)

**Release:** v0.4.0 (2025-12-29)
**Status:** Stable

**Features:**
- 6 frame types (HELLO, CONFIG, ACK, WINDOW_CHUNK, RESULT, ERROR)
- CRC32 validation on all frames
- 8KB chunking for large windows
- Session/boot ID tracking
- Device-side timing telemetry
- Calibration state transfer (up to 64KB)
- Output dimension override support

**Limitations:**
- No authentication or encryption
- No compression
- Single kernel per session (no pipeline)
- No retransmission (relies on transport reliability)

### Future Protocol Versions (Planned)

**Version 2 (Planned - v0.5.0):**
- Compression support (optional flag)
- Multi-kernel pipeline (parallel execution)
- TLS wrapper support

**Version 3 (Planned - v0.6.0):**
- Authentication (adapter→harness verification)
- Incremental state updates (online learning)

---

## References

- **SDK Implementation:** `sdk/adapter/lib/protocol/` (protocol.c, crc32.c)
- **Wire Format Definitions:** `sdk/adapter/include/cortex_wire.h`
- **Transport Layer:** `sdk/adapter/lib/transport/README.md`
- **Adapter Catalog:** `primitives/adapters/v1/README.md`
- **Adding Adapters Guide:** `docs/guides/adding-adapters.md`

---

## Conformance Testing

To verify protocol conformance, run:

```bash
# Test CRC validation
make -C tests test-protocol

# Test end-to-end handshake
make -C tests test-adapter-smoke

# Test all frame types
make -C tests test-adapter-all-kernels
```

**All tests must pass** before an adapter implementation is considered conformant.
