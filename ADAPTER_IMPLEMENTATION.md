# Device Adapter Infrastructure - Implementation Tracking

**Last Updated**: 2025-12-28
**Status**: Phase 1 - Planning Complete, Ready to Implement
**Owner**: CORTEX Development Team

---

## Executive Summary

### What
Device adapter infrastructure enabling Hardware-In-the-Loop (HIL) testing for CORTEX BCI kernels across multiple platforms (x86, Jetson Nano, STM32H7).

### Why
- **Unified execution model**: Harness ALWAYS uses adapters (no mode switching)
- **Consistent telemetry**: Same metrics for local and remote execution
- **Platform validation**: Verify kernels work identically on embedded targets
- **Real-world testing**: Measure actual hardware latency, not just simulation

### Architecture
```
Harness (scheduler → device_comm)
    ↓
SDK Protocol (framing, chunking, CRC, serialization)
    ↓
SDK Transport (mock/TCP/UART with timeouts)
    ↓
Device Adapter (x86@loopback, jetson@tcp, stm32@uart)
    ↓
Kernel Execution
```

### Timeline
- **Estimated**: 8-10 days total
- **Phase 1**: 3-4 days (loopback foundation)
- **Phase 2**: 1-2 days (TCP for Jetson)
- **Phase 3**: 3-4 days (STM32 firmware)
- **Start Date**: TBD
- **Target Completion**: TBD

---

## Critical Technical Decisions

These corrections were made after initial plan review:

| # | Issue | Decision | Rationale |
|---|-------|----------|-----------|
| 1 | **Frame size bug** | WINDOW uses chunking (5×8KB for 40KB window) | Max frame was 17KB but typical window is 40KB |
| 2 | **Header alignment** | 16-byte aligned header with version/flags | ARM requires alignment; need versioning |
| 3 | **CRC definition** | Computed over first 12 header bytes + payload | CRC can't be computed over itself |
| 4 | **Missing sequences** | Added to WINDOW_CHUNK and RESULT | Enables ordering validation, debugging |
| 5 | **No timeouts** | All recv() operations have timeout_ms param | Prevents hangs on adapter death |
| 6 | **Handshake direction** | Adapter advertises first (HELLO), harness selects (CONFIG) | Matches "device tells host capabilities" pattern |
| 7 | **UART throughput** | Phase 2 uses TCP for Jetson (UART only for STM32) | 40KB windows over UART at 921,600 baud too fragile |

---

## Wire Format Specification

### Endianness and Encoding

**ALL wire format data uses:**
- **Integers**: Little-endian (uint8_t, uint16_t, uint32_t, uint64_t)
- **Floats**: IEEE-754 float32, little-endian byte order
- **Strings**: UTF-8, null-terminated (fixed-length buffers)

**Conversion helpers** (even if no-ops on x86, mandatory for STM32):
```c
uint32_t cortex_read_u32_le(const uint8_t *buf);
void cortex_write_u32_le(uint8_t *buf, uint32_t value);
uint64_t cortex_read_u64_le(const uint8_t *buf);
void cortex_write_u64_le(uint8_t *buf, uint64_t value);
float cortex_read_f32_le(const uint8_t *buf);
void cortex_write_f32_le(uint8_t *buf, float value);
```

**⚠️ CRITICAL - ARM/STM32 Implementation**:
```c
// WRONG (on ARM - can fault or be slow):
cortex_wire_header_t *hdr = (cortex_wire_header_t*)buf;
uint32_t magic = hdr->magic;

// RIGHT (always safe):
cortex_wire_header_t hdr;
memcpy(&hdr, buf, sizeof(hdr));
hdr.magic = le32toh(hdr.magic);          // Convert from wire to host
hdr.payload_length = le32toh(hdr.payload_length);
```

Never cast packed structs directly from wire buffers on ARM. Always `memcpy` then convert endianness.

---

### Constants
```c
#define CORTEX_PROTOCOL_MAGIC 0x43525458        // "CRTX"
#define CORTEX_PROTOCOL_VERSION 1

// Frame size limits
#define CORTEX_MAX_SINGLE_FRAME (64 * 1024)     // 64KB for CONFIG/RESULT
#define CORTEX_CHUNK_SIZE (8 * 1024)            // 8KB chunks for WINDOW
#define CORTEX_MAX_WINDOW_SIZE (256 * 1024)     // 256KB max (future-proof)

// CONFIG validation
#define CORTEX_MAX_CALIBRATION_STATE (CORTEX_MAX_SINGLE_FRAME - sizeof(cortex_wire_config_t))

// Timeouts
#define CORTEX_HANDSHAKE_TIMEOUT_MS 5000
#define CORTEX_WINDOW_TIMEOUT_MS 10000
#define CORTEX_CHUNK_TIMEOUT_MS 1000

// WINDOW_CHUNK flags
#define CORTEX_CHUNK_FLAG_LAST (1 << 0)  // Last chunk in sequence
```

### Frame Types
```c
typedef enum {
    CORTEX_FRAME_HELLO        = 0x01,  // Adapter → Harness (capabilities)
    CORTEX_FRAME_CONFIG       = 0x02,  // Harness → Adapter (kernel selection)
    CORTEX_FRAME_ACK          = 0x03,  // Adapter → Harness (ready)
    CORTEX_FRAME_WINDOW_CHUNK = 0x04,  // Harness → Adapter (input chunk)
    CORTEX_FRAME_RESULT       = 0x05,  // Adapter → Harness (output + timing)
    CORTEX_FRAME_ERROR        = 0x06,  // Either direction (error report)
} cortex_frame_type_t;
```

### Universal Header (16 bytes, aligned)
```c
typedef struct __attribute__((packed)) {
    uint32_t magic;           // Always 0x43525458
    uint8_t  version;         // Protocol version (1)
    uint8_t  frame_type;      // cortex_frame_type_t
    uint16_t flags;           // Reserved (0 for Phase 1)
    uint32_t payload_length;  // Bytes following this header
    uint32_t crc32;           // CRC over (magic...payload_length) + payload
} cortex_wire_header_t;

// CRC computation:
// crc = crc32(0, &header, 12);  // First 12 bytes (excludes crc32 field)
// crc = crc32(crc, payload, payload_length);
```

---

### Frame Payloads

**⚠️ IMPORTANT**: All structs below are wire format (packed, little-endian). Use conversion helpers when reading/writing fields.

#### HELLO: Adapter → Harness (capabilities)
```c
typedef struct __attribute__((packed)) {
    uint32_t adapter_boot_id;      // Random on adapter start (detects restarts)
    char     adapter_name[32];     // "x86@loopback", "stm32-h7@uart"
    uint8_t  adapter_abi_version;  // 1
    uint8_t  num_kernels;          // Available kernel count
    uint16_t reserved;             // Padding
    uint32_t max_window_samples;   // Memory constraint
    uint32_t max_channels;         // Hardware limit
    // Followed by: num_kernels × char[32] kernel names
} cortex_wire_hello_t;
```

**Purpose**: Adapter advertises what it can do. Boot ID lets harness detect adapter restarts.

#### CONFIG: Harness → Adapter (kernel selection)
```c
typedef struct __attribute__((packed)) {
    uint32_t session_id;              // Random per handshake (ties RESULT to session)
    uint32_t sample_rate_hz;
    uint32_t window_length_samples;
    uint32_t hop_samples;
    uint32_t channels;
    char     plugin_name[32];
    char     plugin_params[256];
    uint32_t calibration_state_size;  // 0 if not trainable
    // Followed by: calibration_state_size bytes
} cortex_wire_config_t;

// ⚠️ VALIDATION REQUIRED:
// if (calibration_state_size > CORTEX_MAX_CALIBRATION_STATE) {
//     return ERROR("Calibration state too large");
// }
```

**Purpose**: Harness selects kernel and sends configuration. Session ID ties this run to subsequent RESULTs.

#### ACK: Adapter → Harness (ready)
```c
typedef struct __attribute__((packed)) {
    uint32_t ack_type;  // What is being ACKed (0 = CONFIG)
} cortex_wire_ack_t;
```

#### WINDOW_CHUNK: Harness → Adapter (input data chunk)
```c
typedef struct __attribute__((packed)) {
    uint32_t sequence;         // Window sequence number
    uint32_t total_bytes;      // Total window size (W×C×4 bytes)
    uint32_t offset_bytes;     // Offset of this chunk in window
    uint32_t chunk_length;     // Bytes in this chunk
    uint32_t flags;            // CORTEX_CHUNK_FLAG_LAST, etc.
    // Followed by: chunk_length bytes of float32 data
} cortex_wire_window_chunk_t;
```

**Purpose**: Window data chunked to fit in frame size limits. Offset/total allow:
- Completeness verification
- Duplicate detection
- Future reordering/retry without protocol rewrite

**Flags**:
- `CORTEX_CHUNK_FLAG_LAST (1<<0)`: Final chunk in sequence (tin timestamp set after this)

#### RESULT: Adapter → Harness (output + timing)
```c
typedef struct __attribute__((packed)) {
    uint32_t session_id;              // Must match CONFIG session_id
    uint32_t sequence;                // Must match WINDOW sequence
    uint64_t tin;                     // Device: input complete timestamp
    uint64_t tstart;                  // Device: kernel start
    uint64_t tend;                    // Device: kernel end
    uint64_t tfirst_tx;               // Device: first result byte tx
    uint64_t tlast_tx;                // Device: last result byte tx
    uint32_t output_length_samples;
    uint32_t output_channels;
    // Followed by: (output_length × output_channels × 4) bytes
} cortex_wire_result_t;
```

**Purpose**: Return kernel output and device-side timing. Session ID detects adapter restart/reconnect.

#### ERROR: Either direction (error report)
```c
typedef struct __attribute__((packed)) {
    uint32_t error_code;       // Enum: timeout, invalid, overflow, etc.
    char     error_message[256];
} cortex_wire_error_t;
```

---

### Handshake Flow
```
Adapter                          Harness
   │                                │
   ├─────── HELLO ──────────────────> (Advertise: kernels, memory limits)
   <────── CONFIG ──────────────────┤ (Select kernel, send 16KB state)
   ├─────── ACK ────────────────────> (Ready for windows)
   │                                │
```

### Window Chunking Flow (40KB window)
```
Harness                          Adapter
   │                                │
   ├─── WINDOW_CHUNK (seq=0, 0-8K) ──>
   ├─── WINDOW_CHUNK (seq=0, 8-16K) ─>
   ├─── WINDOW_CHUNK (seq=0, 16-24K) >
   ├─── WINDOW_CHUNK (seq=0, 24-32K) >
   ├─── WINDOW_CHUNK (seq=0, 32-40K) >
   │                                │
   │                        [Reassemble → set tin → execute]
   │                                │
   <────── RESULT (seq=0) ──────────┤ (Output + 5 timestamps)
   │                                │
```

---

## Phase 1: Loopback Foundation

**Status**: ⬜ Not Started
**Blocker**: None (ready to start)

### Components Checklist

#### SDK Protocol Library
- ⬜ **`sdk/adapter/lib/protocol/wire_format.h`**
  - Frame type enums
  - All wire format structs (packed, fixed-width)
  - Constants (MAGIC, VERSION, sizes, timeouts)

- ⬜ **`sdk/adapter/include/cortex_protocol.h`**
  - Public API function declarations
  - In-memory API types (with pointers for convenience)
  - Documentation comments

- ⬜ **`sdk/adapter/lib/protocol/protocol.c`**
  - `recv_frame()` with timeout and MAGIC hunting
  - `send_frame()` with CRC computation
  - `send_window_chunked()` (breaks 40KB into 5×8KB)
  - `recv_window_chunked()` (reassembles chunks)
  - Serialize/deserialize helpers

- ⬜ **`sdk/adapter/lib/protocol/crc32.c`**
  - CRC32 implementation (can use zlib or custom)

- ⬜ **`sdk/adapter/lib/protocol/Makefile`**
  - Builds protocol.o, crc32.o

#### SDK Transport Library
- ⬜ **`sdk/adapter/include/cortex_transport.h`**
  - Transport API struct (send, recv with timeout, close, get_timestamp_ns)
  - Error codes (CORTEX_ETIMEDOUT, CORTEX_ECONNRESET)

- ⬜ **`sdk/adapter/lib/transport/mock.c`**
  - Full implementation for socketpair
  - `mock_recv()` with poll() timeout
  - `mock_send()` using write()
  - `mock_timestamp_ns()` using CLOCK_MONOTONIC
  - Create functions: `_create(fd)`, `_create_from_fds(read_fd, write_fd)`

- ⬜ **`sdk/adapter/lib/transport/tcp_client.c`**
  - Stub (returns ENOSYS for Phase 1)

- ⬜ **`sdk/adapter/lib/transport/uart_posix.c`**
  - Stub (Phase 2)

- ⬜ **`sdk/adapter/lib/transport/uart_stm32.c`**
  - Stub (Phase 3)

- ⬜ **`sdk/adapter/lib/transport/Makefile`**
  - Builds all transport .o files

#### SDK Adapter Library Build
- ⬜ **`sdk/adapter/lib/Makefile`**
  - Combines protocol/ and transport/ objects
  - Produces `libcortex_adapter.a`

- ⬜ **`sdk/adapter/Makefile`**
  - Calls lib/Makefile

- ⬜ **`sdk/Makefile`**
  - Add adapter/ subdirectory target

#### Harness Device Comm Layer
- ⬜ **`src/engine/harness/device/device_comm.h`**
  - Public API: `device_comm_init()`, `device_comm_execute_window()`, `device_comm_teardown()`
  - `cortex_device_handle_t` opaque struct
  - `cortex_device_timing_t` struct (tin, tstart, tend, tfirst_tx, tlast_tx)

- ⬜ **`src/engine/harness/device/device_comm.c`**
  - `spawn_loopback_adapter()` using socketpair + fork + exec
  - `device_comm_handshake()` (recv HELLO, send CONFIG, recv ACK)
  - `device_comm_execute_window()` (send chunked WINDOW, recv RESULT)
  - Error handling with timeouts

- ⬜ **`src/engine/harness/device/Makefile`**
  - Links against `-lcortex_adapter`

#### Scheduler Integration
- ⬜ **Modify `src/engine/scheduler/scheduler.c`**
  - Line ~444: `dispatch_window()` routing logic
  - Check `entry->device_handle` → route to device_comm
  - Use device timing for telemetry
  - Keep direct execution as fallback

#### Configuration Extension
- ⬜ **Modify `src/engine/harness/config/config.h`**
  - Add fields to `cortex_plugin_entry_t`:
    - `char adapter_path[256]`
    - `char adapter_config[256]`
    - `cortex_device_handle_t *device_handle`

#### x86@loopback Adapter
- ⬜ **`primitives/adapters/v1/x86@loopback/adapter.c`**
  - Main loop: stdin/stdout as transport
  - Send HELLO (advertise 6 kernels)
  - Receive CONFIG, dlopen kernel
  - Call kernel init(), send ACK
  - Window loop: recv chunked WINDOW, set tin, process, send RESULT
  - Timestamp placement: tin AFTER reassembly, tstart/tend around process()

- ⬜ **`primitives/adapters/v1/x86@loopback/config.yaml`**
  - Metadata (name, version, transport type)

- ⬜ **`primitives/adapters/v1/x86@loopback/README.md`**
  - Usage documentation

- ⬜ **`primitives/adapters/v1/x86@loopback/Makefile`**
  - Builds `cortex_adapter_x86_loopback` binary
  - Links against SDK libraries

#### Telemetry Extension
- ⬜ **Modify `src/engine/telemetry/telemetry.h`**
  - Add fields to `cortex_telemetry_record_t`:
    - `uint64_t device_tin_ns`
    - `uint64_t device_tstart_ns`
    - `uint64_t device_tend_ns`
    - `uint64_t device_tfirst_tx_ns`
    - `uint64_t device_tlast_tx_ns`
    - `char adapter_name[32]`

- ⬜ **Update CSV/NDJSON output** to include new fields

### Test Checklist

- ⬜ **`tests/test_protocol.c`**
  - `test_recv_frame_fragmentation()` (1-byte writes)
  - `test_window_chunking()` (40KB → 5 chunks → reassemble)
  - `test_timeout()` (recv_frame with 100ms timeout)
  - `test_sequence_validation()` (reject wrong sequence)
  - `test_crc_verification()` (detect corruption)
  - `test_max_frame_size()` (reject oversized frames)

- ⬜ **`tests/test_transport_mock.c`**
  - `test_socketpair_io()` (bidirectional communication)
  - `test_timeout()` (poll() timeout works)
  - `test_eof_detection()` (recv returns ECONNRESET on close)

- ⬜ **`tests/test_device_comm.c`**
  - `test_spawn_adapter()` (fork/exec succeeds)
  - `test_handshake()` (HELLO/CONFIG/ACK exchange)
  - `test_window_execution()` (WINDOW chunks → RESULT)
  - `test_adapter_death_recovery()` (kill adapter, timeout detected, respawn)
  - `test_calibration_state_transfer()` (16KB state in CONFIG)

- ⬜ **`tests/test_loopback_adapter.c`**
  - `test_noop_kernel()` (end-to-end with simplest kernel)
  - `test_all_kernels()` (all 6 kernels execute)
  - `test_sequential_execution()` (no pipelining)
  - `test_timing_breakdown()` (tin, tstart, tend are sane)

### Gating Criteria (ALL must pass)

1. ⬜ **Wire format uses fixed-width types**
   - No `size_t`, no pointers in wire structs
   - All structs are `__attribute__((packed))`

2. ⬜ **Header is 16-byte aligned**
   - `sizeof(cortex_wire_header_t) == 16`
   - Fields: magic(4), version(1), type(1), flags(2), payload_len(4), crc32(4)

3. ⬜ **CRC computed correctly**
   - CRC over first 12 bytes of header (excludes CRC field)
   - CRC continues over payload
   - Corruption test detects bit flips

4. ⬜ **recv_frame() survives forced fragmentation**
   - Test with 1-byte write wrapper passes
   - Frame reconstructs correctly

5. ⬜ **recv_frame() has timeouts**
   - 100ms timeout test passes
   - No infinite hangs on dead adapter
   - Returns CORTEX_ETIMEDOUT

6. ⬜ **WINDOW chunking works**
   - 40KB window splits into 5×8KB chunks
   - Reassembly produces identical data
   - All 10,240 floats verified

7. ⬜ **Sequences validated**
   - WINDOW_CHUNK carries sequence number
   - RESULT must match WINDOW sequence
   - Out-of-order RESULT rejected

8. ⬜ **Loopback fork/exec survives restart**
   - Kill adapter process (SIGKILL)
   - Harness detects timeout
   - Respawn succeeds
   - Handshake completes

9. ⬜ **Telemetry timing sane** (loopback only)
   - Kernel time (tend - tstart) matches direct execution ±10%
   - tin timestamp set AFTER reassembly complete
   - No NaN or zero values
   - Timing breakdown visible in CSV output

10. ⬜ **CONFIG with 16KB calibration state**
    - ICA kernel loads state blob via adapter
    - State transferred in single CONFIG frame
    - Kernel receives correct data

11. ⬜ **All 6 kernels execute through loopback**
    - car, notch_iir, bandpass_fir, goertzel, welch_psd, noop
    - Each produces correct output vs oracle
    - Telemetry captured for each

12. ⬜ **Adapter death detected**
    - Kill adapter mid-window
    - recv_frame() times out (not hangs)
    - Harness transitions to error state
    - Error logged in telemetry

---

### Implementation Order (Day 0 → Phase 1 Complete)

**Follow this order to avoid churn and rework:**

#### Step 1: Transport/Mock (Foundation)
Build the lowest layer first with timeouts:
- ⬜ `cortex_transport.h` API definition
- ⬜ `mock.c` with `poll()`-based `recv()` timeout
- ⬜ Test: Basic send/recv with timeout

**Why first**: Everything depends on transport; getting timeouts right prevents hangs later.

#### Step 2: Protocol Frame I/O (No Chunking Yet)
Basic frame send/receive:
- ⬜ `wire_format.h` with all structs
- ⬜ `recv_frame()` with MAGIC hunt, header parse, CRC, payload length checks
- ⬜ `send_frame()` with CRC computation
- ⬜ Endianness conversion helpers (`cortex_read_u32_le`, etc.)
- ⬜ Test: Send/recv HELLO frame, fragmentation test, CRC corruption detection

**Why second**: Validates framing works before adding chunking complexity.

#### Step 3: WINDOW_CHUNK Encode/Decode + Reassembly
Add chunking logic:
- ⬜ `send_window_chunked()` (40KB → 5×8KB chunks with offset/total/flags)
- ⬜ `recv_window_chunked()` (reassemble chunks, validate sequence/offset/total)
- ⬜ Test: 40KB window → chunk → reassemble → verify data integrity

**Why third**: Chunking is complex; isolate it before integrating with adapter.

#### Step 4: Loopback Adapter Binary (Minimal)
Standalone binary that can handshake and noop:
- ⬜ `adapter.c` main loop (stdin/stdout transport)
- ⬜ HELLO with boot_id
- ⬜ CONFIG with session_id, calibration state validation
- ⬜ ACK
- ⬜ Single WINDOW → RESULT loop with noop kernel (identity function)
- ⬜ Test: Manual run (pipe data to stdin, read from stdout)

**Why fourth**: Validates protocol implementation from adapter perspective before harness integration.

#### Step 5: Device Comm Layer (Harness Side)
Spawning and communication:
- ⬜ `device_comm.c` with `spawn_loopback_adapter()` (socketpair + fork/exec)
- ⬜ `device_comm_handshake()` (HELLO/CONFIG/ACK exchange with session_id validation)
- ⬜ `device_comm_execute_window()` (send chunked WINDOW, recv RESULT with session_id check)
- ⬜ Test: Spawn adapter, handshake, single window execute, teardown

**Why fifth**: Now we can test full harness → adapter communication.

#### Step 6: Critical Tests
Validate failure modes:
- ⬜ Fragmentation test (1-byte writes)
- ⬜ Timeout test (dead adapter → ETIMEDOUT, no hang)
- ⬜ Chunking test (40KB window integrity)
- ⬜ CRC corruption test (detect bit flips)
- ⬜ Session ID mismatch test (reject RESULT from old session)
- ⬜ Calibration state >16KB test (ERROR returned)

**Why sixth**: Find bugs before integrating with scheduler.

#### Step 7: Scheduler Integration
Route execution through device_comm:
- ⬜ Modify `scheduler.c` `dispatch_window()` line ~444
- ⬜ Add device_handle routing logic
- ⬜ Use device timing for telemetry
- ⬜ Test: Run single kernel through adapter, verify telemetry

**Why seventh**: Minimal scheduler changes, easy to debug.

#### Step 8: Full Kernel Coverage
Expand to all kernels:
- ⬜ Adapter: dlopen kernel plugins dynamically
- ⬜ Test each kernel: car, notch_iir, bandpass_fir, goertzel, welch_psd, noop
- ⬜ Oracle validation: outputs match Python reference
- ⬜ Telemetry validation: kernel latency matches direct execution ±10%

**Why last**: Proves system works across all kernel types.

---

**Checkpoint**: After Step 8, all 12 gating criteria should pass. Do NOT proceed to Phase 2 until **every checkbox above is checked**.

---

### Implementation Notes

**Mantra**: "Everything on the wire is bytes; everything else is a convenience."

**Key Lessons**:
- Use `memcpy` + `le32toh`, never cast packed structs on ARM
- Validate `calibration_state_size` before allocating (prevent overflow)
- Set `tin` timestamp AFTER final WINDOW_CHUNK decoded (not before)
- Check `session_id` in RESULT matches CONFIG (detects adapter restart)
- Use `flags & CORTEX_CHUNK_FLAG_LAST` to know when to set `tin`

[Add notes here as development progresses]

---

## Phase 2: TCP Transport (Jetson Nano)

**Status**: ⬜ Blocked (Phase 1 incomplete)
**Blocker**: Phase 1 gating criteria must all pass

### Components Checklist

- ⬜ **`sdk/adapter/lib/transport/tcp_client.c`**
  - `tcp_connect()` to host:port
  - `tcp_recv()` with poll() timeout
  - `tcp_send()` using send()
  - Error handling for ECONNRESET

- ⬜ **`sdk/adapter/lib/transport/tcp_server.c`**
  - `tcp_listen()` on port
  - `tcp_accept()` for incoming connections
  - Same recv/send as client

- ⬜ **`primitives/adapters/v1/jetson-nano@tcp/daemon/adapter_daemon.c`**
  - Listen on port 8000
  - Accept harness connection
  - Run same protocol as loopback
  - Use TCP transport instead of mock

- ⬜ **`primitives/adapters/v1/jetson-nano@tcp/daemon/Makefile`**
  - Cross-compile for aarch64 (or build on Jetson)

- ⬜ **`primitives/adapters/v1/jetson-nano@tcp/config.yaml`**
  - Transport config: host, port
  - Jetson-specific settings

- ⬜ **Harness config extension**
  - Parse TCP host/port from adapter config YAML

### Test Checklist

- ⬜ **TCP loopback test** (127.0.0.1:8000)
- ⬜ **Connection stability** (1000+ windows, no drops)
- ⬜ **Throughput test** (measure actual bytes/sec)
- ⬜ **Network error handling** (disconnect, reconnect)

### Gating Criteria (ALL must pass)

1. ⬜ **TCP connection stable**
   - No drops over 1000 windows
   - Graceful reconnect after network hiccup

2. ⬜ **Throughput adequate**
   - 80KB/sec sustained (40KB window × 2 Hz)
   - TCP easily handles this (much better than UART)

3. ⬜ **Jetson daemon runs stable**
   - No crashes over extended run
   - No memory leaks (check with valgrind)
   - CPU usage reasonable

4. ⬜ **Timing shows realistic network latency**
   - Kernel time: same as loopback
   - Network RTT: 1-10ms typical LAN
   - Telemetry captures network overhead

5. ⬜ **All 6 kernels execute on Jetson**
   - Same validation as Phase 1
   - Cross-platform kernel behavior verified

### Implementation Notes

**Why TCP instead of UART for Jetson?**
- Jetson has Ethernet (Gigabit on Nano)
- 40KB windows at 2 Hz = 80KB/sec (trivial for TCP, painful for UART)
- UART at 921,600 baud = 92KB/sec theoretical max, no headroom
- TCP allows flow control, error detection, easier debugging

---

## Phase 3: STM32 Bare-Metal (UART)

**Status**: ⬜ Blocked (Phase 2 incomplete)
**Blocker**: Phase 2 gating criteria must all pass

### Components Checklist

- ⬜ **`sdk/adapter/lib/transport/uart_stm32.c`**
  - HAL-based UART (HAL_UART_Transmit/Receive)
  - DWT cycle counter for timestamps
  - Timeout implementation using HAL_GetTick()
  - Baud rate: 921,600

- ⬜ **`primitives/adapters/v1/stm32-h7@uart/firmware/main.c`**
  - System init (clocks, UART, DWT)
  - Same protocol as loopback/Jetson
  - Static kernel table (no dlopen)

- ⬜ **`primitives/adapters/v1/stm32-h7@uart/firmware/kernel_registry.c`**
  - Static array of kernel entries
  - Lookup by name
  - Link all 6 kernels into firmware

- ⬜ **`primitives/adapters/v1/stm32-h7@uart/firmware/stm32h7xx_hal_conf.h`**
  - HAL configuration
  - Enable UART, DWT, FPU

- ⬜ **`primitives/adapters/v1/stm32-h7@uart/firmware/linker.ld`**
  - STM32H7 memory layout
  - Flash, RAM sections

- ⬜ **`primitives/adapters/v1/stm32-h7@uart/firmware/Makefile`**
  - ARM GCC cross-compile
  - Link all kernels statically
  - Produce .elf and .bin

### Test Checklist

- ⬜ **Firmware flash** (ST-Link)
- ⬜ **UART loopback** (physical wire test)
- ⬜ **DWT timestamp resolution** (verify sub-microsecond)
- ⬜ **Float math verification** (M7 FPU)
- ⬜ **Memory usage** (verify fits in 512KB RAM)

### Gating Criteria (ALL must pass)

1. ⬜ **Firmware builds and flashes**
   - No linker errors
   - Binary size reasonable (<512KB flash)
   - Flashing succeeds via ST-Link

2. ⬜ **UART stable at 921,600 baud**
   - No frame corruption over 1000 windows
   - CRC detects any transmission errors
   - Flow control works (chunking prevents overflow)

3. ⬜ **Float math works**
   - M7 hardware FPU enabled
   - Kernel results match x86 oracle
   - Performance acceptable

4. ⬜ **DWT timestamps sub-microsecond**
   - Resolution better than 1µs
   - Monotonic increasing
   - Accurate measurement of kernel time

5. ⬜ **At least 3 kernels execute correctly**
   - Minimum: noop, car, notch_iir
   - Outputs match oracle within tolerance
   - Telemetry shows expected latency

### Implementation Notes

**Memory constraints**: STM32H7 has 512KB RAM, 2MB Flash
- Window buffer: 40KB (fits)
- Kernel state: varies (check each kernel)
- Static linking: all kernels in firmware (no dynamic loading)

**UART bandwidth**: 921,600 baud with 8N1 = ~92KB/sec
- 40KB window × 2 Hz = 80KB/sec (tight but possible)
- Chunking helps (prevents long blocking transmits)
- May need on-device synthetic input for stress testing

**Timestamp semantics**:
- `tin`, `tstart`, `tend`: Use DWT->CYCCNT
- `tfirst_tx`, `tlast_tx`: DMA TX start/complete interrupts (Phase 3.1)

---

## Build System Changes

### Files to Modify

- ⬜ **`Makefile` (top-level)**
  - Add `sdk/adapter` to `sdk` target
  - Add `adapters` target
  - Update `all` to include `adapters`

- ⬜ **`sdk/Makefile`**
  - Add `adapter/` subdirectory

- ⬜ **`tests/Makefile`**
  - Add adapter test targets
  - Link against `-lcortex_adapter`

### New Directory Structure

```
sdk/adapter/
├── README.md
├── Makefile
├── include/
│   ├── README.md
│   ├── cortex_transport.h
│   └── cortex_protocol.h
└── lib/
    ├── Makefile
    ├── protocol/
    │   ├── wire_format.h
    │   ├── protocol.c
    │   └── crc32.c
    └── transport/
        ├── mock.c
        ├── tcp_client.c
        ├── tcp_server.c
        ├── uart_posix.c
        └── uart_stm32.c

primitives/adapters/v1/
├── README.md
├── x86@loopback/
│   ├── README.md
│   ├── config.yaml
│   ├── adapter.c
│   └── Makefile
├── jetson-nano@tcp/
│   ├── README.md
│   ├── config.yaml
│   └── daemon/
│       ├── adapter_daemon.c
│       └── Makefile
└── stm32-h7@uart/
    ├── README.md
    ├── config.yaml
    └── firmware/
        ├── main.c
        ├── kernel_registry.c
        ├── stm32h7xx_hal_conf.h
        ├── linker.ld
        └── Makefile

src/engine/harness/device/
├── device_comm.h
├── device_comm.c
└── Makefile
```

---

## Documentation Deliverables

- ⬜ **`sdk/adapter/README.md`**
  - Overview of adapter SDK
  - Building libcortex_adapter.a
  - Quick start guide

- ⬜ **`sdk/adapter/include/README.md`**
  - API reference for protocol and transport
  - Function documentation
  - Usage examples

- ⬜ **`primitives/adapters/v1/README.md`**
  - Adapter catalog (x86, Jetson, STM32)
  - Comparison table
  - When to use which adapter

- ⬜ **`docs/guides/adding-adapters.md`**
  - Step-by-step tutorial
  - Wire format specification
  - Testing requirements

- ⬜ **`docs/reference/adapter-protocol.md`**
  - Complete protocol specification
  - Frame format details
  - Sequence diagrams
  - Error handling

- ⬜ **`CHANGELOG.md`**
  - Phase 1 release notes
  - Phase 2 release notes
  - Phase 3 release notes
  - API changes, breaking changes

---

## Risk Log

| Risk | Impact | Mitigation | Status |
|------|--------|------------|--------|
| UART throughput insufficient for STM32 | Phase 3 blocked | Use 921,600 baud + chunking; fallback to on-device input generation | ⬜ Monitoring |
| STM32 float math slow | Poor performance | M7 has hardware FPU; measure early in Phase 3 | ⬜ Not yet assessed |
| Adapter crashes hard to debug | Development slowdown | Extensive logging in ERROR frames; add debug transport | ⬜ Design stage |
| Timing skew between clocks | Inaccurate telemetry | Document device timestamps as relative; consider clock sync in future | ✅ Documented |
| Calibration state >16KB | ICA blocked | Enforce 16KB limit, warn if exceeded; consider chunked CONFIG if needed | ⬜ Design stage |
| Socketpair fragility | Loopback unstable | Well-tested POSIX primitive; add robust error handling | ⬜ Design stage |
| CRC32 performance overhead | Latency increase | Use hardware CRC on STM32; optimize table-based CRC for x86 | ⬜ Design stage |
| Memory leaks in adapter | Long-run instability | Valgrind testing; careful malloc/free discipline | ⬜ Design stage |

---

## Open Questions

### Q1: tfirst_tx/tlast_tx placement
**Question**: Should these timestamps be in RESULT frame or separate TIMING frame?

**Options**:
- A) Embed in RESULT (simpler, but can't set before sending frame)
- B) Separate TIMING frame after RESULT (more accurate, more complex)
- C) Send in NEXT frame's header (pipelined, complex state management)

**Decision**: **A) Embed in RESULT for Phase 1**
- Set tfirst_tx before send_frame(), tlast_tx after
- Accept slight inaccuracy (includes serialization time)
- Phase 2/3 can use DMA interrupts for true HW timing

**Status**: ✅ Decided

---

### Q2: Cross-clock timing measurements
**Question**: How to measure ingress/egress time across different clocks (Jetson/STM32 vs host)?

**Options**:
- A) Don't measure (report only kernel time from device clock)
- B) Clock sync protocol (NTP-like, complex)
- C) Estimate offset using round-trip ping

**Decision**: **A) Phase 1 loopback only (same clock)**
- Device timestamps are relative to device clock (not comparable to host)
- Defer cross-clock sync to future phase
- Document limitation in telemetry

**Status**: ✅ Decided

---

### Q3: Kernel discovery in HELLO vs CONFIG
**Question**: Should HELLO include list of available kernels, or just capabilities?

**Options**:
- A) HELLO includes kernel name list
- B) HELLO just capabilities (memory, channels), CONFIG requests specific kernel
- C) Separate DISCOVER frame

**Decision**: **A) HELLO includes kernel list**
- Adapter advertises what it can run
- Harness validates kernel availability before sending CONFIG
- Cleaner error handling (know immediately if kernel unavailable)

**Status**: ✅ Decided

---

### Q4: Graceful shutdown
**Question**: How does harness signal "done, clean up"?

**Options**:
- A) Just close transport (adapter detects EOF)
- B) Add SHUTDOWN frame
- C) Timeout-based (no activity = assume done)

**Decision**: **A) Close transport for Phase 1**
- Simplest approach
- Adapter exits on EOF/ECONNRESET
- Add explicit SHUTDOWN in Phase 2 if needed

**Status**: ✅ Decided

---

### Q5: Error recovery strategy
**Question**: When adapter returns ERROR frame, should harness retry or abort?

**Options**:
- A) Abort immediately (fail-fast)
- B) Retry N times
- C) User-configurable

**Decision**: **A) Fail-fast for Phase 1**
- ERROR frame = telemetry record with error flag
- Abort current kernel run
- Continue with next kernel (if multi-plugin run)
- Add retry logic in Phase 2 if needed

**Status**: ✅ Decided

---

## Change Log

### 2025-12-28 - Plan Finalized
**Fixed critical design issues**:
- Frame size bug: WINDOW must use chunking (40KB > 17KB max frame)
- Header alignment: Changed to 16-byte aligned with version/flags
- CRC definition: Precisely defined as CRC over first 12 header bytes + payload
- Missing sequences: Added sequence numbers to WINDOW_CHUNK and RESULT
- No timeouts: Added timeout_ms parameter to all recv operations
- Handshake direction: Reversed to adapter-advertises-first pattern
- UART throughput: Changed Phase 2 to TCP for Jetson (UART only for STM32)

**Key architectural decisions**:
- Always-through-adapter execution model
- Chunked WINDOW frames for large data
- Timeout-based error detection
- Sequence-based ordering validation

### 2025-12-28 - Final Corrections Applied (Pre-Implementation)
**Added critical missing pieces**:
- **Session/boot IDs**: Added `adapter_boot_id` to HELLO, `session_id` to CONFIG and RESULT
  - Detects adapter restarts without guessing
  - Prevents RESULT from old session being accepted
- **Endianness specification**: Defined little-endian for all integers/floats
  - Added conversion helpers (cortex_read_u32_le, cortex_write_f32_le, etc.)
  - Added ARM/STM32 warning about never casting packed structs directly
- **WINDOW_CHUNK improvements**: Added `flags` field
  - CORTEX_CHUNK_FLAG_LAST marks final chunk (tin timestamp set after this)
  - Enables future reordering/retry without protocol rewrite
- **Calibration state validation**: Added explicit validation constant
  - CORTEX_MAX_CALIBRATION_STATE = MAX_FRAME - sizeof(config)
  - Documented requirement to ERROR if state too large (not truncate)
- **Implementation order guide**: Added 8-step sequence (Day 0 → Phase 1 complete)
  - Prevents churn and rework
  - Each step builds on previous with clear rationale

**Readiness**: All critical design issues fixed. Phase 1 ready to start.

---

## How to Use This Document

### Before Starting Work
1. Review current phase's component checklist
2. Verify no blockers
3. Understand gating criteria (what "done" means)

### During Implementation
1. Check off completed components as you finish them
2. Add notes in "Implementation Notes" sections
3. Update risk log if new risks discovered
4. Add to change log for significant decisions

### Before Advancing Phases
1. **All gating criteria must pass** (no exceptions)
2. Run `make clean && make all && make tests`
3. Verify telemetry output is sane
4. Update status markers
5. Document any workarounds or deviations

### When Blocked
1. Document blocker in relevant "Notes" section
2. Update risk log if applicable
3. Decide: fix blocker, or defer to later phase?
4. Don't advance phase until blocker resolved

### Update Frequency
**Daily** during active development (minimum)

---

## Status Legend

- ⬜ Not Started / Incomplete
- 🟡 In Progress (actively working on it)
- ✅ Complete (gating criteria passed)
- ❌ Blocked / Failed (cannot proceed)
- 🔄 Under Review (awaiting validation)

---

**END OF DOCUMENT**
