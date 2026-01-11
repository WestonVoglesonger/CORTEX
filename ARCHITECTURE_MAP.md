# CORTEX Adapter System - Complete Architecture Map

## Overview

The CORTEX adapter system is a distributed benchmarking framework that separates kernel execution from measurement infrastructure. The **harness** (measurement orchestrator) communicates with device **adapters** (kernel runners) via a byte-stream protocol that works over multiple transport layers (local socketpair, TCP, serial UART, shared memory).

This design enables:
- **Local testing**: harness spawns native adapter as child process
- **Remote execution**: harness connects to adapter on Jetson/RPi over TCP
- **Embedded targets**: harness connects to STM32 firmware over UART or TCP
- **Distributed isolation**: Each kernel runs in dedicated process, no contention

---

## 1. COMPONENT HIERARCHY

### 1.1 Harness Layer (src/engine/harness/)

**Device Communication** (device_comm.h/c):
- Lines 61-112: device_comm_init() - spawn adapter + complete handshake
- Lines 141-150: device_comm_execute_window() - send window, receive result
- Lines 167: device_comm_teardown() - cleanup adapter process
- Lines 49-127: spawn_adapter() - fork + exec, create socketpair

### 1.2 Protocol Layer (sdk/adapter/lib/protocol/)

Protocol provides frame-based communication with:
- Hunt MAGIC: detect frame start in byte stream
- Read header: 16 bytes (magic, version, type, length, CRC)
- Verify CRC: crc32(header[0:12] + payload)
- Chunking: 8KB chunks for large windows

### 1.3 Transport Layer (sdk/adapter/include/cortex_transport.h)

Five transport implementations:
1. **Mock** (local://): POSIX socketpair, poll() timeout
2. **TCP Client** (tcp://host:port): harness connects to remote adapter
3. **TCP Server** (tcp://:port): adapter listens, harness connects
4. **UART/Serial** (serial:///dev/ttyUSB0): hardware serial connection
5. **Shared Memory** (shm://name): High-performance local IPC

### 1.4 Adapter Layer (primitives/adapters/v1/native/adapter.c)

- Lines 102-215: load_kernel_plugin() - dlopen kernel, link symbols
- Lines 237+: run_session() - handshake loop
- Kernel loading detects ABI version (v2 or v3) by checking for cortex_calibrate()

### 1.5 Adapter Helpers (sdk/adapter/lib/adapter_helpers/)

Convenience functions:
- cortex_adapter_send_hello() - advertise capabilities
- cortex_adapter_recv_config() - receive kernel selection + calibration state
- cortex_adapter_send_ack_with_dims() - acknowledge with output dimensions
- cortex_adapter_send_result() - transmit output + timing
- cortex_adapter_send_error() - error reporting

### 1.6 Deployment Layer (src/cortex/deploy/)

- **Deployer Protocol** (base.py): Abstract interface for deployment strategies
- **SSH Deployer** (ssh_deployer.py):
  - Lines 79-118: Check passwordless SSH, show setup instructions
  - Lines 120-150: Detect capabilities (OS, arch, build tools)
  - Deploy: rsync → remote build → start daemon

---

## 2. DATA FLOW

### 2.1 Initialization: Dataset → Device Comm → Adapter → Kernel

```
Harness: cortex run --kernel car
  ├─ device_comm_init(adapter_path, transport_uri, ...)
  │   ├─ Parse transport URI (e.g., "tcp://jetson:9000")
  │   │
  │   ├─ LOCAL MODE (local://):
  │   │   ├─ spawn_adapter() [lines 49-127]
  │   │   │   ├─ socketpair(AF_UNIX)
  │   │   │   ├─ fork()
  │   │   │   ├─ (child) dup2(socket → stdin/stdout), exec adapter
  │   │   │   └─ (parent) store harness_fd, adapter_pid
  │   │   └─ cortex_transport_mock_create(harness_fd)
  │   │
  │   ├─ TCP MODE (tcp://jetson:9000):
  │   │   └─ cortex_transport_tcp_client_create(host, port, timeout)
  │   │       ├─ socket(AF_INET), connect(host, port)
  │   │       └─ wrap in cortex_transport_t
  │   │
  │   ├─ HANDSHAKE PHASE:
  │   │   │
  │   │   ├─ STEP 1: Receive HELLO [lines 170-234]
  │   │   │   └─ Extract: boot_id, adapter_name, kernel_list, device_info
  │   │   │
  │   │   ├─ STEP 2: Send CONFIG [lines 243-286]
  │   │   │   ├─ Generate session_id
  │   │   │   ├─ Build payload: session_id, W, H, C, plugin_name, 
  │   │   │   │   plugin_params, calibration_state
  │   │   │   └─ Send frame (+ calibration state appended)
  │   │   │
  │   │   ├─ STEP 3: Receive ACK [lines 298-351]
  │   │   │   └─ Extract output dimensions (W_out, C_out)
  │   │   │
  │   │   └─ Return: cortex_device_init_result_t with handle, output dims, metadata
  │   │
  │   └─ Ready for window processing
```

### 2.2 Window Processing Loop

```
For each hop (80 samples @ 160Hz):
  │
  ├─ Pull window W (160×64 × 4 bytes = 40,960 bytes, host format)
  │
  └─ device_comm_execute_window(handle, sequence, input, ...)
      │
      ├─ SEND PHASE: cortex_protocol_send_window_chunked()
      │   ├─ Break 40,960 bytes into 8KB chunks (5 chunks)
      │   └─ For each chunk:
      │       ├─ Build WINDOW_CHUNK frame
      │       │   ├─ sequence, total_bytes, offset_bytes
      │       │   ├─ chunk_length, flags (LAST on final)
      │       │   └─ payload: float32 samples (little-endian)
      │       ├─ Compute CRC32
      │       └─ transport.send()
      │
      ├─ PROCESS PHASE: Adapter executes
      │   ├─ cortex_protocol_recv_window_chunked()
      │   │   ├─ Reassemble chunks by offset
      │   │   ├─ Validate no gaps
      │   │   ├─ When LAST received: tin = get_timestamp_ns()
      │   │   └─ Return window (host format)
      │   │
      │   ├─ tstart = get_timestamp_ns()
      │   ├─ cortex_process(kernel, input, output)
      │   └─ tend = get_timestamp_ns()
      │
      ├─ RESULT PHASE: Send results
      │   ├─ cortex_adapter_send_result()
      │   │   ├─ tfirst_tx = get_timestamp_ns() (before send)
      │   │   ├─ Build RESULT payload:
      │   │   │   ├─ session_id, sequence
      │   │   │   ├─ tin, tstart, tend (device-side timing)
      │   │   │   ├─ output_samples (little-endian convert)
      │   │   │   └─ output_length, output_channels
      │   │   └─ transport.send()
      │   │       └─ tlast_tx = get_timestamp_ns() (after send)
      │   │
      │   └─ Harness receives RESULT
      │       ├─ Hunt MAGIC, read header, verify CRC
      │       ├─ Parse payload (host format convert)
      │       ├─ Validate session_id, sequence
      │       ├─ Extract tin, tstart, tend, output samples
      │       └─ Store latency distribution + timing
      │
      └─ Continue until dataset exhausted
```

### 2.3 Shutdown Flow

```
Harness: End of dataset
  └─ device_comm_teardown(handle)
      ├─ cortex_transport_destroy(transport)
      │   └─ transport->close() [socket close / file close]
      │
      ├─ Adapter detects EOF on stdin
      │   ├─ cortex_teardown(kernel_handle)
      │   ├─ dlclose(dl_handle)
      │   └─ exit(0)
      │
      ├─ waitpid(adapter_pid) [reap zombie]
      │
      └─ free(handle)
```

---

## 3. PROTOCOL LAYERS

### 3.1 Wire Format (Endianness)

All multi-byte values: **little-endian**

Safe read/write (cortex_endian.h):
```
cortex_read_u32_le(buf)        → uint32_t (little-endian)
cortex_write_u32_le(buf, val)  → encode to little-endian
cortex_read_f32_le(buf)        → float32 (little-endian)
cortex_write_f32_le(buf, val)  → encode to little-endian
```

### 3.2 Frame Header (16 bytes, little-endian)

```
Offset  Type      Field           Bytes   Value/Purpose
──────  ────      ─────           ─────   ────────────
0       u32_le    magic           4       0x43525458 ("CRTX")
4       u8        version         1       1
5       u8        frame_type      1       HELLO(1), CONFIG(2), ACK(3), 
                                          WINDOW_CHUNK(4), RESULT(5), ERROR(6)
6       u16_le    flags           2       0 (reserved)
8       u32_le    payload_length  4       Payload size (bytes)
12      u32_le    crc32           4       CRC over [0:12] + payload
```

### 3.3 Frame Types

1. **HELLO** (0x01): Adapter → Harness
   - boot_id, adapter_name, num_kernels
   - max_window_samples, max_channels
   - device_hostname, device_cpu, device_os

2. **CONFIG** (0x02): Harness → Adapter
   - session_id, sample_rate_hz, window_samples, hop_samples, channels
   - plugin_name, plugin_params
   - calibration_state_size + [calibration data]

3. **ACK** (0x03): Adapter → Harness
   - output_window_length_samples, output_channels (0 = use config)

4. **WINDOW_CHUNK** (0x04): Harness → Adapter
   - sequence, total_bytes, offset_bytes, chunk_length, flags
   - [float32 samples in little-endian]

5. **RESULT** (0x05): Adapter → Harness
   - session_id, sequence
   - tin, tstart, tend, tfirst_tx, tlast_tx (nanoseconds)
   - output_length_samples, output_channels
   - [float32 output samples in little-endian]

6. **ERROR** (0x06): Either direction
   - error_code, error_message[256]

### 3.4 Protocol Reception (cortex_protocol.c:133-205)

```
recv_frame(transport, &frame_type, payload_buf, timeout_ms)
  ├─ hunt_magic(timeout)
  │   ├─ Read bytes one-at-a-time
  │   ├─ Maintain 4-byte sliding window
  │   └─ Until window == 0x43525458
  │
  ├─ read_exact(transport, 12 bytes, timeout)
  │   └─ Read: version | type | flags | length | crc32
  │
  ├─ read_exact(transport, payload_length, timeout)
  │   └─ Read payload
  │
  ├─ Compute CRC over header[0:12] + payload
  │
  ├─ Verify computed_crc == wire_crc
  │   └─ If mismatch: return CORTEX_EPROTO_CRC_MISMATCH
  │
  └─ Return: frame_type, payload_buf, actual_payload_len
```

### 3.5 Chunked Window Protocol

Windows > 8KB split into multiple WINDOW_CHUNK frames:

```
send_window_chunked(transport, sequence, samples[], W, C)
  │
  ├─ total_bytes = W × C × 4
  ├─ num_chunks = ceil(total_bytes / 8192)
  │
  └─ For each chunk:
      ├─ chunk_length = min(8192, remaining_bytes)
      ├─ offset_bytes = chunk_index × 8192
      ├─ flags = CORTEX_CHUNK_FLAG_LAST (if final chunk)
      │
      ├─ Build WINDOW_CHUNK frame:
      │   ├─ sequence, total_bytes, offset_bytes
      │   ├─ chunk_length, flags
      │   └─ payload: float32 samples (little-endian convert)
      │
      └─ send_frame(CORTEX_FRAME_WINDOW_CHUNK, ...)

recv_window_chunked(transport, expected_sequence, out_samples[], timeout)
  │
  └─ While not complete:
      ├─ Receive WINDOW_CHUNK frame
      ├─ Validate: sequence matches, offset makes sense
      ├─ Accumulate by offset
      ├─ If LAST flag: tin = get_timestamp_ns()
      └─ Check for completeness (no gaps)
```

---

## 4. TRANSPORT ABSTRACTION

### 4.1 Transport API (cortex_transport.h:34-79)

All transports implement:

```c
typedef struct cortex_transport_api {
    void *ctx;
    
    ssize_t (*send)(ctx, buf, len);              /* Send bytes */
    
    ssize_t (*recv)(ctx, buf, len, timeout_ms);  /* Recv with timeout */
    
    void (*close)(ctx);                          /* Cleanup */
    
    uint64_t (*get_timestamp_ns)(void);          /* Platform clock */
} cortex_transport_api_t;
```

### 4.2 Implementations

1. **Mock (socketpair)** - local://
   - Uses POSIX AF_UNIX socketpair
   - Recv timeout via poll()
   - Clock: CLOCK_MONOTONIC
   - Files: sdk/adapter/lib/transport/local/mock.c
   - Status: Production-ready

2. **TCP Client** - tcp://host:port
   - Harness connects to remote adapter
   - Recv timeout via select()
   - Files: sdk/adapter/lib/transport/network/tcp_client.c
   - Status: Production-ready

3. **TCP Server** - tcp://:port
   - Adapter listens, harness connects
   - Two-phase: create → accept
   - Files: sdk/adapter/lib/transport/network/tcp_server.c

4. **UART/Serial** - serial:///dev/ttyUSB0?baud=115200
   - POSIX termios configuration
   - Recv timeout via poll()
   - Files: sdk/adapter/lib/transport/serial/uart_posix.c
   - Bandwidth: ~11 KB/s @ 115200 (too slow for typical BCI data)

5. **Shared Memory** - shm://name
   - High-performance local IPC (~2 GB/s)
   - POSIX shared memory + semaphores
   - Latency: ~5µs (vs 50µs socketpair, 1ms TCP)
   - Files: sdk/adapter/lib/transport/local/shm.c
   - Use: Pure kernel performance measurement

### 4.3 URI Parsing (cortex_transport.h:98-112)

```c
typedef struct {
    char scheme[16];           /* "local", "tcp", "serial", "shm" */
    char host[256];            /* TCP host or empty for server mode */
    uint16_t port;             /* TCP port */
    char device_path[256];     /* "/dev/ttyUSB0" */
    uint32_t baud_rate;        /* 115200 */
    char shm_name[64];         /* "bench01" */
} cortex_uri_t;
```

### 4.4 Transport Selection (device_comm.c:395-493)

```c
if (strcmp(scheme, "local") == 0) {
    spawn_adapter(adapter_path, &harness_fd, &adapter_pid);
    transport = cortex_transport_mock_create(harness_fd);
}
else if (strcmp(scheme, "tcp") == 0) {
    if (host[0]) {
        /* Client mode */
        transport = cortex_transport_tcp_client_create(host, port, timeout_ms);
    }
}
else if (strcmp(scheme, "serial") == 0) {
    transport = cortex_transport_uart_posix_create(device_path, baud_rate);
}
else if (strcmp(scheme, "shm") == 0) {
    transport = cortex_transport_shm_create_harness(name);
}
```

---

## 5. LIFECYCLE & STATE MACHINES

### 5.1 Adapter State Machine

```
STARTUP
  ├─ Initialize transport (stdin/stdout)
  ├─ Register signal handler (SIGTERM)
  └─ Enter session loop

HANDSHAKE
  ├─ Send HELLO (capabilities)
  ├─ Receive CONFIG (kernel + params + calib_state)
  ├─ load_kernel_plugin() [lines 102-215]
  │   ├─ Parse spec_uri: "primitives/kernels/v1/car@f32"
  │   ├─ Build lib path: "primitives/kernels/v1/car@f32/libcar.dylib"
  │   ├─ dlopen(abs_lib_path)
  │   ├─ dlsym(cortex_init, cortex_process, cortex_teardown)
  │   ├─ dlsym(cortex_calibrate) [detect ABI v2 vs v3]
  │   └─ cortex_init(&config)
  │       ├─ Allocate state buffers
  │       ├─ Validate parameters
  │       └─ Load calibration state if trainable
  ├─ Send ACK (actual output dims from cortex_init result)
  └─ Allocate window buffers

PROCESSING LOOP (for each window)
  ├─ Receive WINDOW_CHUNK frames
  │   └─ cortex_protocol_recv_window_chunked()
  │       ├─ Reassemble chunks by offset
  │       ├─ tin = get_timestamp_ns() (after LAST received)
  │       └─ Return full window (host format)
  ├─ tstart = get_timestamp_ns()
  ├─ cortex_process(kernel, input, output)
  ├─ tend = get_timestamp_ns()
  ├─ Send RESULT
  │   └─ cortex_adapter_send_result()
  │       ├─ tfirst_tx before, tlast_tx after send()
  │       └─ Transmit output + timing
  └─ Repeat (or exit if EOF on stdin)

CLEANUP (signal or EOF)
  ├─ cortex_teardown(kernel_handle)
  ├─ dlclose(dl_handle)
  └─ exit(0)
```

### 5.2 Harness State Machine

```
INITIALIZATION
  ├─ Parse transport URI
  ├─ Spawn/connect to adapter
  └─ Establish transport layer

HANDSHAKE
  ├─ Receive HELLO
  ├─ Send CONFIG (+ calibration_state if trainable)
  └─ Receive ACK

EXECUTION LOOP (for each hop)
  ├─ Pull window (160×64 samples)
  ├─ Send WINDOW_CHUNK frames (8KB chunks)
  ├─ Receive RESULT frame
  ├─ Validate session_id, sequence
  ├─ Extract output + timing
  └─ Store in telemetry (NDJSON)

CLEANUP
  ├─ Close transport (adapter detects EOF)
  ├─ Reap adapter process (if local)
  └─ Generate results
```

### 5.3 Session Tracking

**session_id**:
- Generated random in CONFIG
- Returned in RESULT
- Mismatch indicates adapter restart
- Detected: device_comm.c:629

**sequence**:
- Incremented per window
- Returned in RESULT
- Mismatch indicates out-of-order frames
- Detected: device_comm.c:634

---

## 6. DEPLOYMENT MODELS

### 6.1 Local Execution

```
User: cortex run --kernel car

Harness Process:
  ├─ device_comm_init("primitives/adapters/v1/native/cortex_adapter_native",
  │                   "local://", ...)
  │   ├─ spawn_adapter()
  │   │   ├─ socketpair(AF_UNIX) → [harness_fd, adapter_fd]
  │   │   ├─ fork() → adapter_pid
  │   │   ├─ (child) dup2(adapter_fd → stdin/stdout)
  │   │   ├─ (child) exec("cortex_adapter_native")
  │   │   └─ (parent) store harness_fd, adapter_pid
  │   └─ Create transport from harness_fd
  │
  └─ Handshake + execute loop

Adapter Process (child):
  ├─ Inherit stdin/stdout from socketpair
  ├─ Create transport from stdin/stdout FDs
  └─ Handshake + execute loop → exit(0) on EOF
```

Advantages:
- No network setup
- Child inherits environment
- Simple socketpair communication
- Shared working directory

### 6.2 Remote SSH Execution (Auto-Deploy)

```
User: cortex run --kernel car --deploy ssh://user@jetson

SSHDeployer:
  ├─ detect_capabilities()
  │   ├─ Check passwordless SSH [lines 79-118]
  │   │   └─ If fails: show setup instructions
  │   └─ Run: uname -s, uname -m, which gcc make
  │
  ├─ deploy()
  │   ├─ rsync source to ~/cortex-temp on device
  │   ├─ Remote build: make all
  │   └─ Start daemon: adapter tcp://:9000
  │       └─ Return: transport_uri = "tcp://jetson-ip:9000"
  │
  └─ cleanup()
      ├─ Kill remote adapter
      ├─ Remove ~/cortex-temp
      └─ Release resources

Harness (after deploy):
  ├─ device_comm_init(..., "tcp://jetson-ip:9000", ...)
  │   ├─ Parse URI → scheme="tcp", host, port
  │   └─ cortex_transport_tcp_client_create()
  │       └─ socket(), connect(host, port, timeout=5s)
  └─ Proceed with normal handshake + execution
```

---

## 7. KEY INTERFACES

### 7.1 Kernel ABI (cortex_plugin.h)

**Config passed to cortex_init()**:

```c
typedef struct cortex_plugin_config {
    uint32_t abi_version;               /* 2 or 3 */
    uint32_t struct_size;               /* sizeof(...) */
    uint32_t sample_rate_hz;            /* e.g., 160 */
    uint32_t window_length_samples;     /* W = 160 */
    uint32_t hop_samples;               /* H = 80 */
    uint32_t channels;                  /* C = 64 */
    uint32_t dtype;                     /* 1 = FLOAT32 */
    uint8_t allow_in_place;
    const void *kernel_params;          /* "f0_hz=60.0,Q=30.0" */
    uint32_t kernel_params_size;
    const void *calibration_state;      /* Trainable kernel model */
    uint32_t calibration_state_size;
} cortex_plugin_config_t;
```

**Return from cortex_init()**:

```c
typedef struct {
    void *handle;       /* Opaque kernel instance */
    uint32_t output_window_length_samples;  /* W_out (0 = same as input) */
    uint32_t output_channels;               /* C_out (0 = same as input) */
    uint32_t capabilities;
} cortex_init_result_t;
```

**Core functions**:

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
void cortex_process(void *handle, const void *input, void *output);
void cortex_teardown(void *handle);
void* cortex_calibrate(const cortex_plugin_config_t *config,
                       const void *data, uint32_t data_size);  /* v3+ */
```

**ABI Detection** (adapter.c:177-178):

```c
calibrate_fn = dlsym(dl, "cortex_calibrate");
uint32_t abi_version = (calibrate_fn != NULL) ? 3 : 2;
```

### 7.2 Device Communication API

```c
int device_comm_init(
    const char *adapter_path,
    const char *transport_config,
    const char *plugin_name,
    const char *plugin_params,
    uint32_t sample_rate_hz,
    uint32_t window_samples,
    uint32_t hop_samples,
    uint32_t channels,
    const void *calib_state,
    size_t calib_state_size,
    cortex_device_init_result_t *out_result
);

int device_comm_execute_window(
    cortex_device_handle_t *handle,
    uint32_t sequence,
    const float *input_samples,
    uint32_t window_samples,
    uint32_t channels,
    float *output_samples,
    size_t output_buf_size,
    cortex_device_timing_t *out_timing
);

void device_comm_teardown(cortex_device_handle_t *handle);
```

### 7.3 Protocol API

```c
int cortex_protocol_recv_frame(cortex_transport_t *transport,
                               cortex_frame_type_t *out_type,
                               void *payload_buf,
                               size_t payload_buf_size,
                               size_t *out_payload_len,
                               uint32_t timeout_ms);

int cortex_protocol_send_frame(cortex_transport_t *transport,
                               cortex_frame_type_t frame_type,
                               const void *payload,
                               size_t payload_len);

int cortex_protocol_send_window_chunked(cortex_transport_t *transport,
                                        uint32_t sequence,
                                        const float *samples,
                                        uint32_t window_samples,
                                        uint32_t channels);

int cortex_protocol_recv_window_chunked(cortex_transport_t *transport,
                                        uint32_t expected_sequence,
                                        float *out_samples,
                                        size_t samples_buf_size,
                                        uint32_t *out_window_samples,
                                        uint32_t *out_channels,
                                        uint32_t timeout_ms);
```

### 7.4 Adapter Helpers

```c
int cortex_adapter_send_hello(...);
int cortex_adapter_recv_config(...);
int cortex_adapter_send_ack_with_dims(...);
int cortex_adapter_send_result(...);
int cortex_adapter_send_error(...);
void cortex_get_device_hostname(...);
void cortex_get_device_cpu(...);
void cortex_get_device_os(...);
```

---

## 8. FILE PATH REFERENCE

| Component | Path |
|-----------|------|
| Device Comm | src/engine/harness/device/device_comm.h/.c |
| Protocol | sdk/adapter/include/cortex_protocol.h |
| Wire Format | sdk/adapter/include/cortex_wire.h |
| Transport API | sdk/adapter/include/cortex_transport.h |
| Endian Helpers | sdk/adapter/include/cortex_endian.h |
| Adapter Helpers | sdk/adapter/include/cortex_adapter_helpers.h |
| Adapter Transport | sdk/adapter/include/cortex_adapter_transport.h |
| Native Adapter | primitives/adapters/v1/native/adapter.c |
| Protocol Impl | sdk/adapter/lib/protocol/protocol.c |
| Mock Transport | sdk/adapter/lib/transport/local/mock.c |
| TCP Client | sdk/adapter/lib/transport/network/tcp_client.c |
| TCP Server | sdk/adapter/lib/transport/network/tcp_server.c |
| UART/Serial | sdk/adapter/lib/transport/serial/uart_posix.c |
| SHM Transport | sdk/adapter/lib/transport/local/shm.c |
| Deployer Base | src/cortex/deploy/base.py |
| SSH Deployer | src/cortex/deploy/ssh_deployer.py |

---

## Summary

**CORTEX Adapter Architecture = Three-Layer Abstraction**:

1. **Application Layer** (Handshake & Window Loop)
   - Kernel execution orchestration
   - Frame types: HELLO, CONFIG, ACK, WINDOW_CHUNK, RESULT, ERROR

2. **Protocol Layer** (Frame-Based Communication)
   - MAGIC hunting + header validation + CRC32 verification
   - Chunking for large windows (8KB chunks)
   - All wire format: little-endian

3. **Transport Layer** (Byte-Stream Abstraction)
   - Five implementations (mock, TCP client/server, UART, SHM)
   - Timeout handling (poll/select)
   - Platform-specific clocks (CLOCK_MONOTONIC or DWT)

**Key Design Principles**:
- Sequential execution (no parallel kernels)
- ABI frozen at core 3 + optional calibrate function
- Distributed isolation (adapter in separate process/device)
- Multi-transport support (same protocol everywhere)
- Session + sequence tracking (detect restarts/reordering)
- Device-side timestamps (tin, tstart, tend measure kernel latency)

