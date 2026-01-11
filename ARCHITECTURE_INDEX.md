# CORTEX Adapter Architecture - Complete Documentation Index

## Document Overview

This folder contains comprehensive documentation of the CORTEX adapter system architecture. Three complementary documents cover different aspects:

### 1. **ARCHITECTURE_MAP.md** (710 lines)
**Comprehensive reference guide covering all architectural aspects**

Sections:
- Component Hierarchy (6 subsystems)
- Data Flow (3 detailed flows: init, window processing, shutdown)
- Protocol Layers (wire format, frames, reception, chunking)
- Transport Abstraction (5 implementations with characteristics)
- Lifecycle & State Machines (adapter, harness, session tracking)
- Deployment Models (local, SSH/auto-deploy)
- Key Interfaces (kernel ABI, device comm, protocol, helpers)
- File Path Reference (14 core components with line numbers)

**Use when**: You need detailed understanding of how a specific component works, or exploring implementation details with line numbers.

---

### 2. **ARCHITECTURE_DIAGRAM.txt** (900+ lines)
**Visual ASCII representation with detailed flow diagrams**

Sections:
- Layer Stack (Application → Protocol → Transport visualization)
- Data Flow: Local Execution (detailed box diagram, parent-child processes)
- Data Flow: Remote SSH Execution (deployment → harness → cleanup)
- Protocol Frame Structure (wire format, WINDOW_CHUNK, RESULT examples)
- Transport Abstraction Stack (API functions, implementations, bandwidth)
- Component Integration Map (execution flows, harness & adapter)
- Error Handling & Recovery (error codes, session tracking, timeouts)

**Use when**: You want visual understanding of how components interact, or need quick reference to specific timings/characteristics.

---

### 3. **ARCHITECTURE_INDEX.md** (this file)
**Navigation guide and quick reference**

Provides:
- Document overview (what each file covers)
- Quick lookup tables (file paths, line numbers, interfaces)
- Search guide (how to find specific topics)
- Summary of key design decisions
- Links to source code by functionality

---

## Quick Navigation

### By Topic

**Understanding Harness → Adapter Communication**
1. Read: ARCHITECTURE_DIAGRAM.txt, "Layer Stack" section
2. Read: ARCHITECTURE_MAP.md, section "2. DATA FLOW"
3. Reference: ARCHITECTURE_MAP.md, section "7. KEY INTERFACES"

**Setting Up Remote Execution (SSH)**
1. Read: ARCHITECTURE_DIAGRAM.txt, "Data Flow: Remote Execution"
2. Read: ARCHITECTURE_MAP.md, "6. Deployment Models"
3. File: `src/cortex/deploy/ssh_deployer.py` (lines 79-150)

**Understanding Frame Protocol**
1. Read: ARCHITECTURE_MAP.md, "3. Protocol Layers"
2. Reference: ARCHITECTURE_DIAGRAM.txt, "Protocol Frame Structure"
3. File: `sdk/adapter/include/cortex_wire.h` (frame definitions)

**Implementing New Transport**
1. Read: ARCHITECTURE_MAP.md, "4. Multi-Transport Architecture"
2. Reference: `sdk/adapter/include/cortex_transport.h` (API)
3. Example: `sdk/adapter/lib/transport/local/mock.c`

**Understanding Kernel Execution Timing**
1. Read: ARCHITECTURE_DIAGRAM.txt, "Component Integration Map"
2. Reference: ARCHITECTURE_MAP.md, "5. Lifecycle & State Machines"
3. File: `primitives/adapters/v1/native/adapter.c` (lines 237+)

**Debugging Protocol Issues**
1. Reference: ARCHITECTURE_MAP.md, "3. Protocol Layers"
2. Error codes: `sdk/adapter/include/cortex_wire.h` (lines 191-199)
3. Implementation: `sdk/adapter/lib/protocol/protocol.c` (lines 133-205)

---

## File Path Reference (with line numbers)

| Functionality | Path | Key Lines |
|---------------|------|-----------|
| **Harness Communication** | | |
| Spawn adapter | src/engine/harness/device/device_comm.c | 49-127 |
| Init handshake | src/engine/harness/device/device_comm.c | 359-548 |
| Execute window | src/engine/harness/device/device_comm.c | 553-664 |
| Cleanup | src/engine/harness/device/device_comm.c | 669-689 |
| Receive HELLO | src/engine/harness/device/device_comm.c | 170-234 |
| Send CONFIG | src/engine/harness/device/device_comm.c | 243-286 |
| Receive ACK | src/engine/harness/device/device_comm.c | 298-351 |
| **Protocol** | | |
| Frame reception | sdk/adapter/lib/protocol/protocol.c | 133-205 |
| MAGIC hunting | sdk/adapter/lib/protocol/protocol.c | 73-120 |
| Exact read | sdk/adapter/lib/protocol/protocol.c | 19-58 |
| Frame definitions | sdk/adapter/include/cortex_wire.h | 52-200 |
| Endian helpers | sdk/adapter/include/cortex_endian.h | 20-176 |
| **Adapter** | | |
| Kernel loading | primitives/adapters/v1/native/adapter.c | 102-215 |
| Session loop | primitives/adapters/v1/native/adapter.c | 237+ |
| ABI detection | primitives/adapters/v1/native/adapter.c | 177-178 |
| Signal handler | primitives/adapters/v1/native/adapter.c | 35-41 |
| **Transport** | | |
| Transport API | sdk/adapter/include/cortex_transport.h | 34-79 |
| URI parsing | sdk/adapter/include/cortex_transport.h | 98-112 |
| Transport selection | src/engine/harness/device/device_comm.c | 395-493 |
| Mock (socketpair) | sdk/adapter/lib/transport/local/mock.c | - |
| TCP Client | sdk/adapter/lib/transport/network/tcp_client.c | - |
| TCP Server | sdk/adapter/lib/transport/network/tcp_server.c | - |
| Serial/UART | sdk/adapter/lib/transport/serial/uart_posix.c | - |
| Shared Memory | sdk/adapter/lib/transport/local/shm.c | - |
| **Deployment** | | |
| Deployer protocol | src/cortex/deploy/base.py | 49-142 |
| SSH deployer | src/cortex/deploy/ssh_deployer.py | - |
| Check SSH | src/cortex/deploy/ssh_deployer.py | 79-118 |
| Detect platform | src/cortex/deploy/ssh_deployer.py | 120-150 |
| **Helpers** | | |
| Adapter helpers | sdk/adapter/include/cortex_adapter_helpers.h | 38-195 |
| Protocol helpers | sdk/adapter/lib/adapter_helpers/protocol_helpers.c | 10-196 |

---

## Key Data Structures

### Device Communication

```c
/* From device_comm.h */
cortex_device_init_result_t {
    cortex_device_handle_t *handle;
    uint32_t output_window_length_samples;
    uint32_t output_channels;
    char adapter_name[32];
    char device_hostname[32];
    char device_cpu[32];
    char device_os[32];
};

cortex_device_timing_t {
    uint64_t tin;        /* Input complete */
    uint64_t tstart;     /* Kernel start */
    uint64_t tend;       /* Kernel end */
    uint64_t tfirst_tx;  /* First tx byte */
    uint64_t tlast_tx;   /* Last tx byte */
};
```

### Wire Format

```c
/* From cortex_wire.h */
cortex_wire_header_t {
    uint32_t magic;      /* 0x43525458 */
    uint8_t version;     /* 1 */
    uint8_t frame_type;  /* HELLO/CONFIG/ACK/WINDOW/RESULT/ERROR */
    uint16_t flags;      /* 0 */
    uint32_t payload_length;
    uint32_t crc32;
};

cortex_wire_config_t {
    uint32_t session_id;
    uint32_t sample_rate_hz;
    uint32_t window_length_samples;
    uint32_t hop_samples;
    uint32_t channels;
    char plugin_name[64];
    char plugin_params[256];
    uint32_t calibration_state_size;
    /* Followed by calibration_state data */
};

cortex_wire_result_t {
    uint32_t session_id;
    uint32_t sequence;
    uint64_t tin, tstart, tend, tfirst_tx, tlast_tx;
    uint32_t output_length_samples;
    uint32_t output_channels;
    /* Followed by output samples */
};
```

### Transport API

```c
/* From cortex_transport.h */
typedef struct cortex_transport_api {
    void *ctx;
    ssize_t (*send)(void *ctx, const void *buf, size_t len);
    ssize_t (*recv)(void *ctx, void *buf, size_t len, uint32_t timeout_ms);
    void (*close)(void *ctx);
    uint64_t (*get_timestamp_ns)(void);
} cortex_transport_api_t;

typedef struct {
    char scheme[16];           /* "local", "tcp", "serial", "shm" */
    char host[256];
    uint16_t port;
    char device_path[256];
    uint32_t baud_rate;
    char shm_name[64];
} cortex_uri_t;
```

### Kernel ABI

```c
/* From cortex_plugin.h */
typedef struct cortex_plugin_config {
    uint32_t abi_version;      /* 2 or 3 */
    uint32_t sample_rate_hz;
    uint32_t window_length_samples;
    uint32_t hop_samples;
    uint32_t channels;
    const void *kernel_params;
    const void *calibration_state;
    uint32_t calibration_state_size;
} cortex_plugin_config_t;

typedef struct {
    void *handle;
    uint32_t output_window_length_samples;  /* 0 = same as input */
    uint32_t output_channels;               /* 0 = same as input */
} cortex_init_result_t;

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
void cortex_process(void *handle, const void *input, void *output);
void cortex_teardown(void *handle);
```

---

## Protocol Frame Types

| Type | Value | Direction | Purpose |
|------|-------|-----------|---------|
| HELLO | 0x01 | Adapter → Harness | Advertise capabilities, boot_id, device info |
| CONFIG | 0x02 | Harness → Adapter | Select kernel, send parameters, calibration state |
| ACK | 0x03 | Adapter → Harness | Acknowledge CONFIG, report output dimensions |
| WINDOW_CHUNK | 0x04 | Harness → Adapter | Input data chunk (8KB max) |
| RESULT | 0x05 | Adapter → Harness | Output + timing data |
| ERROR | 0x06 | Either | Error report with code and message |

---

## Transport Characteristics

| Transport | URI | Bandwidth | Latency | Use Case | Status |
|-----------|-----|-----------|---------|----------|--------|
| Mock (socketpair) | local:// | ~500 MB/s | ~50 µs | Development, CI/CD | Production |
| TCP Client | tcp://host:port | ~50 MB/s | 1-5 ms | Remote (Jetson, RPi) | Production |
| TCP Server | tcp://:port | ~50 MB/s | 1-5 ms | Adapter listening | Implemented |
| Serial/UART | serial:///dev/ttyUSB0 | 11 KB/s @ 115200 | 90 µs/byte | Debug console | Slow for BCI |
| Shared Memory | shm://name | 2 GB/s | ~5 µs | Pure performance baseline | Fast, local only |

---

## Error Codes

| Code | Value | Meaning |
|------|-------|---------|
| CORTEX_ETIMEDOUT | -1000 | Operation timed out |
| CORTEX_ECONNRESET | -1001 | Connection closed |
| CORTEX_EPROTO_MAGIC_NOT_FOUND | -2000 | MAGIC not found in stream |
| CORTEX_EPROTO_CRC_MISMATCH | -2001 | CRC verification failed |
| CORTEX_EPROTO_VERSION_MISMATCH | -2002 | Protocol version mismatch |
| CORTEX_EPROTO_FRAME_TOO_LARGE | -2003 | Payload > 64KB |
| CORTEX_EPROTO_BUFFER_TOO_SMALL | -2004 | Caller buffer too small |
| CORTEX_EPROTO_INVALID_FRAME | -2005 | Invalid frame structure |
| CORTEX_ECHUNK_SEQUENCE_MISMATCH | -2100 | Chunk sequence mismatch |
| CORTEX_ECHUNK_INCOMPLETE | -2101 | Missing chunks (gaps) |
| CORTEX_ECHUNK_BUFFER_TOO_SMALL | -2102 | Output buffer too small |

---

## Timeouts

| Timeout | Value | Purpose |
|---------|-------|---------|
| CORTEX_HANDSHAKE_TIMEOUT_MS | 5000 ms | HELLO, CONFIG, ACK |
| CORTEX_WINDOW_TIMEOUT_MS | 10000 ms | WINDOW_CHUNK + RESULT |
| CORTEX_CHUNK_TIMEOUT_MS | 1000 ms | Individual chunk reception |
| CORTEX_ACCEPT_TIMEOUT_MS | 30000 ms | TCP server accept |

---

## Key Design Decisions

### 1. **Sequential Execution (No Parallelism)**
- Kernels run one-at-a-time, not parallel
- Prevents CPU contention, cache invalidation, non-reproducible measurements
- Trade-off: Slower throughput, deterministic results

### 2. **ABI Frozen at Core 3 Functions**
- `cortex_init()`, `cortex_process()`, `cortex_teardown()` - fixed forever
- Optional `cortex_calibrate()` for trainable kernels (v3+)
- Benefits: Simple, stable, backward compatible (v2→v3)

### 3. **Distributed Isolation**
- Adapter runs in separate process (local) or device (remote)
- No shared memory for data processing
- Benefits: Fault tolerance, multi-device support, clean separation

### 4. **Multi-Transport at Protocol Layer**
- Same CORTEX_PROTOCOL_* works over socketpair, TCP, serial, SHM
- Transport abstraction enables future additions
- Benefits: Flexibility, code reuse, portable

### 5. **Session + Sequence Tracking**
- session_id detects adapter restarts
- sequence detects out-of-order windows
- Benefits: Error detection, recovery capability

### 6. **Device-Side Timestamps**
- tin, tstart, tend measured on adapter (nanosecond precision)
- Eliminates harness clock jitter
- Benefits: Accurate kernel latency, cross-platform comparison

### 7. **Little-Endian Wire Format**
- All integers, floats on wire use little-endian
- Safe helpers (memcpy) prevent alignment faults on ARM
- Benefits: Portable, ARM-safe, predictable

### 8. **8KB Chunking for Large Windows**
- Windows > 8KB split into multiple WINDOW_CHUNK frames
- Prevents transport MTU issues (typical 1500 bytes)
- Benefits: Robust, transport-agnostic

---

## Architecture Principles (Lampson's STEADY)

- **Simplicity**: Core ABI = 3 functions, frozen interface
- **Timely**: Real-time kernel execution measurement
- **Dependability**: CRC validation, session tracking, error handling
- **Adaptability**: Pluggable transports, future-proof protocol
- **Decomposition**: Harness ↔ Protocol ↔ Transport ↔ Adapter
- **Yummy**: Intuitive frame types, clear data flow

---

## For First-Time Readers

**Start here** (30 minutes):
1. ARCHITECTURE_DIAGRAM.txt, "Layer Stack" section
2. ARCHITECTURE_DIAGRAM.txt, "Data Flow: Local Execution" section
3. ARCHITECTURE_MAP.md, section "1. Component Hierarchy"

**Then dive deep** (1-2 hours):
- Pick a topic from "By Topic" section above
- Read the corresponding sections
- Cross-reference source code with line numbers

**For implementation** (per-task):
- Use the "Quick Navigation" section to find relevant code
- Refer to "File Path Reference" for line numbers
- Check "Key Data Structures" for struct definitions

---

## About This Documentation

Generated by analyzing:
- 14 core component files (C headers + Python)
- 700+ lines of architecture map
- 900+ lines of visual diagrams
- Complete line-by-line references to source

Last updated: 2025 (matches commit 931b1b0: "fix: Move deployer cleanup after benchmark completion")

