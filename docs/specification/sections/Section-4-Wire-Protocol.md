# Section 4: Wire Protocol Specification

## 4.1 Transport Layer

### 4.1.1 Overview

The CORTEX wire protocol operates over a reliable byte-stream transport abstraction that provides ordered, lossless delivery of data between the harness and device adapter. The protocol is transport-agnostic, supporting multiple physical transports through a unified API.

The transport layer abstracts platform-specific communication mechanisms while providing essential primitives for protocol correctness: timeout-based receive operations to detect adapter failure, monotonic timestamps for latency measurement, and standardized error codes for common failure modes.

### 4.1.2 Transport Abstraction Requirements

All transport implementations MUST provide the following operations:

**Send Operation**

A conformant transport SHALL implement a blocking send operation with the following signature:

```c
ssize_t send(void *ctx, const void *buf, size_t len);
```

The send operation:
- MUST transmit exactly `len` bytes from `buf` or return an error
- MAY block until the entire buffer is transmitted
- MUST return the number of bytes sent on success (equal to `len`)
- MUST return a negative error code on failure

**Receive Operation**

A conformant transport SHALL implement a blocking receive operation with timeout:

```c
ssize_t recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms);
```

The receive operation:
- MUST wait up to `timeout_ms` milliseconds for data to arrive
- MAY return partial data (fewer than `len` bytes)
- MUST return the number of bytes received on success
- MUST return 0 if the connection is closed (EOF)
- MUST return `CORTEX_ETIMEDOUT` (-1000) if the timeout expires with no data
- MUST return `CORTEX_ECONNRESET` (-1001) if the connection is reset
- MUST return other negative error codes for platform-specific failures

**Timestamp Operation**

A conformant transport SHALL provide monotonic nanosecond timestamps:

```c
uint64_t get_timestamp_ns(void);
```

The timestamp operation:
- MUST return nanoseconds since an arbitrary epoch
- MUST use a monotonic clock source (immune to system time changes)
- MUST NOT wrap around during reasonable execution periods
- SHOULD use CLOCK_MONOTONIC on POSIX systems
- SHOULD use DWT cycle counters on ARM Cortex-M systems

### 4.1.3 Timeout Requirements

All receive operations MUST specify explicit timeouts to prevent infinite hangs on adapter failure. A conformant implementation SHALL use the following timeout values:

| Phase | Timeout (ms) | Rationale |
|-------|--------------|-----------|
| Handshake (HELLO, ACK) | 5000 | Adapter may be loading kernels, initializing hardware |
| Window processing (WINDOW_CHUNK, RESULT) | 10000 | Kernel execution + large data transfer |
| Per-chunk receive | 1000 | Single 8KB chunk transfer time |
| Error frames | 500 | Fast failure detection |
| TCP server accept | 30000 | Network connection establishment |

These values are defined as constants in `cortex_wire.h`:

```c
#define CORTEX_HANDSHAKE_TIMEOUT_MS 5000
#define CORTEX_WINDOW_TIMEOUT_MS    10000
#define CORTEX_CHUNK_TIMEOUT_MS     1000
#define CORTEX_ACCEPT_TIMEOUT_MS    30000
```

**Rationale**: Explicit timeouts prevent deadlock when an adapter crashes or hangs. The handshake timeout is longer because adapters may perform expensive initialization (loading shared libraries, allocating large buffers, calibrating hardware). Window processing timeouts accommodate both computation time and large data transfers (e.g., 40KB window at 1 MB/s requires 40ms transfer time plus kernel execution).

### 4.1.4 Supported Transports

The specification defines three standard transport types:

**Native Transport (local://)**

The native transport uses POSIX `socketpair(2)` to create a bidirectional byte stream between the harness and a locally-spawned adapter process. This is the default transport for development and testing.

URI format: `local://`

A conformant harness implementation:
- SHALL create a UNIX domain socket pair using `socketpair(AF_UNIX, SOCK_STREAM, 0)`
- SHALL spawn the adapter process via `fork(2)` and `execl(3)`
- SHALL redirect the adapter's stdin/stdout to one end of the socket pair
- SHALL use the other end for protocol communication
- SHALL set close-on-exec flags to prevent fd leakage
- SHALL use `poll(2)` or `select(2)` to implement receive timeouts

**TCP Transport (tcp://)**

The TCP transport provides network connectivity for remote adapters (e.g., Jetson Nano over Ethernet, cloud GPUs).

URI format: `tcp://host:port` (client mode) or `tcp://:port` (server mode)

Query parameters:
- `timeout_ms=N`: Override default timeout (5000ms)
- `accept_timeout_ms=N`: Server accept timeout (30000ms)

Example: `tcp://jetson.local:9000?timeout_ms=2000`

A conformant TCP transport:
- MUST use IPv4 or IPv6 TCP sockets
- MUST support both client (connect) and server (listen) modes
- MUST implement receive timeouts using `setsockopt(SO_RCVTIMEO)` or `poll(2)`
- SHOULD enable TCP_NODELAY to reduce latency
- SHOULD set SO_KEEPALIVE for connection health monitoring

**Serial/UART Transport (serial://)**

The UART transport enables communication with embedded adapters via RS-232, USB-serial, or native UART ports.

URI format: `serial:///dev/device?baud=115200`

Query parameters:
- `baud=N`: Baud rate (default: 115200)

Common baud rates: 115200, 230400, 460800, 921600

Example: `serial:///dev/ttyUSB0?baud=921600`

A conformant UART transport:
- MUST configure the serial port for 8N1 mode (8 data bits, no parity, 1 stop bit)
- MUST disable hardware flow control (RTS/CTS) unless explicitly enabled
- MUST use VTIME/VMIN settings to implement receive timeouts
- SHOULD flush buffers on initialization to discard stale data
- SHOULD support common POSIX device paths (/dev/ttyUSB*, /dev/cu.*, /dev/ttyS*)

### 4.1.5 Transport Error Handling

All transport implementations MUST distinguish between temporary and permanent errors:

**Temporary Errors** (retry possible):
- `CORTEX_ETIMEDOUT`: No data available within timeout period
- `EINTR`: System call interrupted by signal

A conformant protocol implementation MAY retry operations that fail with temporary errors.

**Permanent Errors** (connection lost):
- `CORTEX_ECONNRESET`: Connection closed by peer
- `EPIPE`: Broken pipe (adapter terminated)
- `ECONNREFUSED`: Connection refused (TCP only)

A conformant protocol implementation MUST abort operations and return to the caller when permanent errors occur.

---

## 4.2 Binary Frame Format

### 4.2.1 Overview

All protocol messages are encapsulated in binary frames consisting of a fixed 16-byte header, variable-length payload, and CRC32 checksum. Frames are self-delimiting and can be transmitted over unreliable byte streams with corruption detection and resynchronization.

### 4.2.2 Frame Structure

A conformant frame SHALL have the following byte layout:

```
Offset | Size | Field          | Endianness | Description
-------|------|----------------|------------|---------------------------
0      | 4    | MAGIC          | LE         | 0x43525458 ("CRTX")
4      | 1    | VERSION        | N/A        | Protocol version (0x01)
5      | 1    | TYPE           | N/A        | Frame type (0x01-0x07)
6      | 2    | FLAGS          | LE         | Reserved (MUST be 0x0000)
8      | 4    | LENGTH         | LE         | Payload length in bytes
12     | 4    | CRC32          | LE         | IEEE 802.3 checksum
16     | N    | PAYLOAD        | LE         | Frame-specific payload
16+N   | 0    | (end)          |            | Total frame size: 16+N
```

All multi-byte integers SHALL be transmitted in little-endian byte order. The header size is fixed at 16 bytes to enable efficient parsing (read header, extract LENGTH, read LENGTH bytes of payload).

**Alignment Requirement**: The header struct is 16 bytes to ensure natural alignment on ARM platforms (avoiding unaligned access faults on ARMv7 and earlier).

### 4.2.3 MAGIC Constant

The MAGIC field MUST be 0x43525458 (ASCII "CRTX" interpreted as a little-endian 32-bit integer).

On the wire, the MAGIC bytes appear in little-endian order:
```
Wire bytes: 0x58 0x54 0x52 0x43
            ^    ^    ^    ^
            |    |    |    +--- 'C' (0x43)
            |    |    +-------- 'R' (0x52)
            |    +------------- 'T' (0x54)
            +------------------ 'X' (0x58)
```

The MAGIC constant serves three purposes:

1. **Frame boundary detection**: Enables receivers to locate the start of a frame in a byte stream
2. **Protocol identification**: Distinguishes CORTEX frames from other data on shared transports
3. **Resynchronization**: Allows recovery from corruption or partial frame loss

A conformant receiver SHALL reject any frame that does not begin with the MAGIC constant.

### 4.2.4 VERSION Field

The VERSION field MUST be 0x01 for protocol version 1.

A conformant implementation:
- SHALL reject frames with VERSION != 0x01
- SHALL return error code `CORTEX_EPROTO_VERSION_MISMATCH` (-2002)
- SHOULD log the received version number for debugging

**Rationale**: Strict version checking prevents subtle incompatibilities between harness and adapter builds. Protocol version increments indicate breaking wire format changes.

### 4.2.5 TYPE Field

The TYPE field specifies the frame type (message category). Valid values are defined in Section 4.3.

A conformant implementation SHALL validate that the TYPE field contains a recognized frame type value. Unknown TYPE values SHOULD be treated as protocol errors.

### 4.2.6 FLAGS Field

The FLAGS field is reserved for future protocol extensions. In protocol version 1, this field MUST be 0x0000.

A conformant implementation:
- MUST set FLAGS to 0x0000 when sending frames
- SHOULD ignore the FLAGS field when receiving frames (forward compatibility)

Future protocol versions may define flag bits for optional features (compression, encryption, fragmentation control).

### 4.2.7 LENGTH Field

The LENGTH field specifies the payload size in bytes (excluding the 16-byte header).

A conformant implementation:
- MUST set LENGTH to the exact payload size
- MUST validate that LENGTH does not exceed available buffer space before reading payload
- SHALL return `CORTEX_EPROTO_BUFFER_TOO_SMALL` (-2004) if the caller's buffer is insufficient

**No Maximum Frame Size**: Protocol version 1 imposes no hardcoded maximum frame size. Frames are limited only by available RAM. Large payloads (windows, results) are automatically chunked using WINDOW_CHUNK and RESULT_CHUNK frame types (see Section 4.5).

### 4.2.8 CRC32 Checksum

The CRC32 field contains a 32-bit checksum computed over the frame header (bytes 0-11, excluding the CRC32 field itself) and the entire payload.

**Algorithm**: IEEE 802.3 CRC32 (polynomial 0xEDB88320, same as Ethernet, ZIP, PNG)

**Computation**:
```c
uint32_t crc = crc32(0, header_bytes_0_to_11, 12);
crc = crc32(crc, payload, payload_length);
// Store 'crc' in header[12:16] (little-endian)
```

The CRC32 function uses the following parameters:
- Initial value: 0xFFFFFFFF (inverted)
- Polynomial: 0xEDB88320 (reflected)
- Final XOR: 0xFFFFFFFF (inverted)

A conformant implementation:
- MUST compute the CRC over header bytes [0:12] followed by payload bytes [0:N]
- MUST use the IEEE 802.3 polynomial (table lookup or bitwise algorithm)
- MUST reject frames where computed CRC != wire CRC
- SHALL return `CORTEX_EPROTO_CRC_MISMATCH` (-2001) on CRC validation failure

**Error Detection Properties**:
- Detects all single-bit errors
- Detects all double-bit errors
- Detects all burst errors up to 32 bits
- Detects 99.9999998% of longer bursts
- Performance: ~1 GB/s with table lookup on modern CPUs

**Rationale**: CRC32 provides strong error detection for bit flips, truncation, and reordering. The false acceptance rate (~1 in 4 billion) is acceptable for intra-system communication. The IEEE 802.3 polynomial is hardware-accelerated on many platforms and well-tested.

### 4.2.9 Endianness Conversion

All multi-byte values on the wire use little-endian byte order. A conformant implementation MUST convert between host byte order and wire byte order using explicit conversion functions.

**Reading from wire**:
```c
uint32_t value = cortex_read_u32_le(buffer);
uint64_t timestamp = cortex_read_u64_le(buffer + 8);
float sample = cortex_read_f32_le(buffer + 16);
```

**Writing to wire**:
```c
cortex_write_u32_le(buffer, value);
cortex_write_u64_le(buffer + 8, timestamp);
cortex_write_f32_le(buffer + 16, sample);
```

On little-endian hosts (x86, most ARM), these functions compile to no-ops (direct memory access). On big-endian hosts, they perform byte swapping.

**CRITICAL**: Implementations MUST NOT cast packed structs directly from wire buffers:

```c
// WRONG (undefined behavior, alignment faults on ARM):
header = *(cortex_wire_header_t*)buffer;

// CORRECT:
cortex_wire_header_t header;
memcpy(&header, buffer, sizeof(header));
header.magic = cortex_le32toh(header.magic);
header.payload_length = cortex_le32toh(header.payload_length);
// ... convert other fields ...
```

**Rationale**: Little-endian is the native byte order of x86 and modern ARM platforms. Using little-endian wire format avoids byte swapping overhead on 99% of deployed hardware. Explicit conversion functions prevent alignment faults on ARMv7 and endianness bugs on rare big-endian platforms.

### 4.2.10 MAGIC Hunting (Resynchronization)

When a receiver starts or detects corruption, it MUST perform MAGIC hunting to locate the next frame boundary.

**Algorithm**:

A conformant receiver SHALL use a sliding-window search:

```c
uint32_t window = 0;
while (true) {
    uint8_t byte;
    if (recv_one_byte(&byte, timeout_ms) != 0)
        return CORTEX_ETIMEDOUT;

    // Shift window right, insert new byte at top (LE order)
    window = (window >> 8) | ((uint32_t)byte << 24);

    if (window == CORTEX_PROTOCOL_MAGIC)
        break;  // Frame start found
}
```

**Byte order note**: Because MAGIC is transmitted in little-endian order (0x58, 0x54, 0x52, 0x43), the sliding window must shift right and insert new bytes at the top to reconstruct the 32-bit value in host byte order.

**Rationale**: MAGIC hunting enables recovery from partial frame corruption, adapter restarts, or mid-stream synchronization. The 4-byte MAGIC constant has low probability of false matches in random data (~1 in 4 billion).

---

## 4.3 Message Types

### 4.3.1 Overview

The CORTEX protocol defines 7 frame types for handshake, execution, and error handling. Each frame type has a unique TYPE value and payload structure.

| Type | Value | Direction | Purpose |
|------|-------|-----------|---------|
| HELLO | 0x01 | Adapter → Harness | Advertise capabilities |
| CONFIG | 0x02 | Harness → Adapter | Configure kernel |
| ACK | 0x03 | Adapter → Harness | Acknowledge configuration |
| WINDOW_CHUNK | 0x04 | Harness → Adapter | Send input data (chunked) |
| RESULT | 0x05 | Adapter → Harness | Return output (legacy, deprecated) |
| ERROR | 0x06 | Either direction | Report error |
| RESULT_CHUNK | 0x07 | Adapter → Harness | Return output data (chunked) |

**Note**: RESULT (0x05) is deprecated in favor of RESULT_CHUNK (0x07) for consistent chunking support. Both are supported for backward compatibility.

### 4.3.2 HELLO Frame (0x01)

**Direction**: Adapter → Harness

**Purpose**: The adapter advertises its capabilities, available kernels, and system information immediately after transport connection establishment.

**When sent**: First message from adapter after spawn/connect

**Payload structure**:

```
Offset | Size | Field                | Endianness | Description
-------|------|----------------------|------------|---------------------------
0      | 4    | adapter_boot_id      | LE         | Random ID on adapter start
4      | 32   | adapter_name         | N/A        | Adapter name (null-term)
36     | 1    | adapter_abi_version  | N/A        | ABI version (MUST be 1)
37     | 1    | num_kernels          | N/A        | Count of available kernels
38     | 2    | reserved             | LE         | Padding (MUST be 0)
40     | 4    | max_window_samples   | LE         | Memory constraint
44     | 4    | max_channels         | LE         | Hardware channel limit
48     | 32   | device_hostname      | N/A        | Device hostname (uname -n)
80     | 32   | device_cpu           | N/A        | CPU model (e.g., "Apple M1")
112    | 32   | device_os            | N/A        | OS version (uname -s -r)
144    | N×32 | kernel_names         | N/A        | num_kernels × 32-byte names
```

**Total payload size**: 144 + (num_kernels × 32) bytes

**Field descriptions**:

- `adapter_boot_id`: Random 32-bit value generated on adapter process start. Used to detect adapter restarts (harness can compare against previous session).

- `adapter_name`: Human-readable adapter identifier (e.g., "native", "jetson@tcp", "stm32-h7@uart"). NULL-terminated string up to 32 bytes.

- `adapter_abi_version`: Binary compatibility version. MUST be 1 for protocol version 1. If harness receives a different ABI version, it MUST reject the connection.

- `num_kernels`: Count of available kernel implementations. Harness uses this to allocate buffer space for kernel names.

- `max_window_samples`: Maximum window length the adapter can process (in samples). Constrained by adapter RAM. Harness MUST NOT send windows larger than this limit.

- `max_channels`: Maximum channel count supported by adapter hardware. Harness MUST NOT configure more channels than this limit.

- `device_hostname`: Device hostname from `uname(2)` or equivalent (e.g., "jetson-01", "MacBook-Pro.local"). Used for telemetry tagging.

- `device_cpu`: CPU model string (e.g., "Apple M1", "ARM Cortex-A57", "Intel Core i7-9700K"). Used for performance analysis.

- `device_os`: Operating system name and version (e.g., "Darwin 23.2.0", "Linux 5.10.104-tegra"). Used for compatibility diagnostics.

- `kernel_names`: Array of NULL-terminated kernel names (32 bytes each). Each name is a kernel identifier (e.g., "bandpass_fir@f32", "ica@f32").

**Example**:

```
adapter_boot_id:     0x8F3A21C7
adapter_name:        "native"
adapter_abi_version: 1
num_kernels:         3
max_window_samples:  512
max_channels:        64
device_hostname:     "MacBook-Pro.local"
device_cpu:          "Apple M1"
device_os:           "Darwin 23.2.0"

Kernel names:
  [0] "bandpass_fir@f32"
  [1] "car@f32"
  [2] "ica@f32"

Payload size: 144 + (3 × 32) = 240 bytes
```

**Hex dump** (first 64 bytes):

```
00000000: c7 21 3a 8f 6e 61 74 69  76 65 00 00 00 00 00 00  |.!:.native......|
00000010: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
00000020: 00 00 00 00 01 03 00 00  00 02 00 00 40 00 00 00  |............@...|
00000030: 4d 61 63 42 6f 6f 6b 2d  50 72 6f 2e 6c 6f 63 61  |MacBook-Pro.loca|
        boot_id ^adapter_name                 ^abi ^nk ^res
                                               ^max_win ^max_ch
                                                       ^device_hostname
```

**Validation requirements**:

A conformant harness:
- MUST verify `adapter_abi_version == 1`
- MUST verify `num_kernels >= 1`
- MUST verify payload size == 144 + (num_kernels × 32)
- SHOULD verify that requested kernel name appears in `kernel_names` array

### 4.3.3 CONFIG Frame (0x02)

**Direction**: Harness → Adapter

**Purpose**: Configure the adapter with kernel selection, execution parameters, and optional calibration state.

**When sent**: After receiving HELLO

**Payload structure**:

```
Offset | Size | Field                   | Endianness | Description
-------|------|-------------------------|------------|---------------------------
0      | 4    | session_id              | LE         | Random session identifier
4      | 4    | sample_rate_hz          | LE         | Sample rate (e.g., 250 Hz)
8      | 4    | window_length_samples   | LE         | Window length (W)
12     | 4    | hop_samples             | LE         | Hop size (H)
16     | 4    | channels                | LE         | Channel count (C)
20     | 64   | plugin_name             | N/A        | Kernel spec URI (null-term)
84     | 256  | plugin_params           | N/A        | Params string (null-term)
340    | 4    | calibration_state_size  | LE         | State size (0 if none)
344    | N    | calibration_state       | (opaque)   | Binary state blob
```

**Total payload size**: 344 + calibration_state_size bytes

**Field descriptions**:

- `session_id`: Random 32-bit identifier for this execution session. MUST be non-zero. Used to detect adapter restarts (if adapter reboots, it won't match the session_id in subsequent RESULT frames).

- `sample_rate_hz`: Sampling frequency in Hz (e.g., 250 for 250 Hz EEG). Used for time-domain calculations.

- `window_length_samples`: Number of samples per channel in each window (W). MUST be <= max_window_samples from HELLO.

- `hop_samples`: Number of samples to advance between consecutive windows (H). Typically W/2 for 50% overlap.

- `channels`: Number of input channels (C). MUST be <= max_channels from HELLO.

- `plugin_name`: Kernel specifier URI (e.g., "primitives/kernels/v1/ica@f32"). NULL-terminated string up to 64 bytes. MUST match a kernel advertised in HELLO.

- `plugin_params`: Kernel-specific configuration string (e.g., "lowcut=8,highcut=30"). Format is kernel-dependent. NULL-terminated string up to 256 bytes.

- `calibration_state_size`: Size of calibration state blob in bytes. MUST be 0 for stateless kernels. MUST be <= 16 MB for trainable kernels.

- `calibration_state`: Opaque binary state blob for trainable kernels (e.g., ICA unmixing matrix). Format is kernel-specific.

**Validation requirements**:

A conformant adapter:
- MUST verify `session_id != 0`
- MUST verify `sample_rate_hz > 0`
- MUST verify `window_length_samples <= max_window_samples` (from HELLO)
- MUST verify `channels <= max_channels` (from HELLO)
- MUST verify `plugin_name` matches an advertised kernel
- MUST verify `calibration_state_size <= 16777216` (16 MB)
- SHALL return ERROR frame if validation fails

**Example**:

```
session_id:              0x4A7F3C21
sample_rate_hz:          250
window_length_samples:   160
hop_samples:             80
channels:                64
plugin_name:             "primitives/kernels/v1/ica@f32"
plugin_params:           "whiten=true,maxiter=100"
calibration_state_size:  16384  (64×64 matrix × 4 bytes)

Payload size: 344 + 16384 = 16728 bytes
```

### 4.3.4 ACK Frame (0x03)

**Direction**: Adapter → Harness

**Purpose**: Acknowledge CONFIG and report actual output dimensions (for dimension-changing kernels).

**When sent**: After successfully loading kernel and allocating buffers

**Payload structure**:

```
Offset | Size | Field                          | Endianness | Description
-------|------|--------------------------------|------------|---------------------------
0      | 4    | ack_type                       | LE         | What is ACKed (0 = CONFIG)
4      | 4    | output_window_length_samples   | LE         | Output W (0 = use input W)
8      | 4    | output_channels                | LE         | Output C (0 = use input C)
```

**Total payload size**: 12 bytes

**Field descriptions**:

- `ack_type`: Type of acknowledgment. MUST be 0 (CONFIG) in protocol version 1.

- `output_window_length_samples`: Output window length in samples. If 0, harness SHOULD use input window_length_samples from CONFIG. If non-zero, indicates kernel changes window length (e.g., Welch PSD reduces time resolution).

- `output_channels`: Output channel count. If 0, harness SHOULD use input channels from CONFIG. If non-zero, indicates kernel changes channel count (e.g., ICA unmixing).

**Rationale**: Most kernels preserve dimensions (input W×C = output W×C). For these kernels, the adapter sets output dimensions to 0, and the harness reuses CONFIG dimensions. This provides backward compatibility and simplifies common cases.

Dimension-changing kernels (e.g., PSD estimation, channel reduction) explicitly report output dimensions in ACK. The harness dynamically allocates output buffers based on these values.

**Example (dimension-preserving kernel)**:

```
ack_type:                        0
output_window_length_samples:    0  (use CONFIG: 160)
output_channels:                 0  (use CONFIG: 64)
```

**Example (dimension-changing kernel - Welch PSD)**:

```
ack_type:                        0
output_window_length_samples:    65  (FFT: 160 → 65 freq bins)
output_channels:                 64  (unchanged)
```

### 4.3.5 WINDOW_CHUNK Frame (0x04)

**Direction**: Harness → Adapter

**Purpose**: Send input window data, potentially split across multiple chunks for large windows.

**When sent**: After receiving ACK, for each window to process

**Payload structure**:

```
Offset | Size | Field          | Endianness | Description
-------|------|----------------|------------|---------------------------
0      | 4    | sequence       | LE         | Window sequence number
4      | 4    | total_bytes    | LE         | Total window size (W×C×4)
8      | 4    | offset_bytes   | LE         | Offset of this chunk
12     | 4    | chunk_length   | LE         | Bytes in this chunk
16     | 4    | flags          | LE         | CORTEX_CHUNK_FLAG_LAST
20     | N    | sample_data    | LE         | Float32 samples (LE)
```

**Total payload size**: 20 + chunk_length bytes

**Field descriptions**:

- `sequence`: Monotonically increasing window sequence number. Starts at 1. Used to match WINDOW_CHUNK with corresponding RESULT.

- `total_bytes`: Total size of the complete window in bytes (window_length_samples × channels × 4). Same value in all chunks for a given window.

- `offset_bytes`: Byte offset of this chunk's data within the complete window. First chunk has offset 0. Subsequent chunks have offset = previous_offset + previous_chunk_length.

- `chunk_length`: Number of bytes in this chunk's `sample_data` field. SHOULD be <= 8192 (8KB) for optimal performance.

- `flags`: Bit flags. Bit 0 (CORTEX_CHUNK_FLAG_LAST) MUST be set on the final chunk of a window. All other bits MUST be 0.

- `sample_data`: Float32 sample data in little-endian IEEE-754 format. Samples are stored in row-major order (all channels for sample 0, then all channels for sample 1, etc.).

**Chunking behavior**:

A conformant harness:
- SHOULD split windows larger than 8KB into multiple WINDOW_CHUNK frames
- MUST set `sequence` to the same value for all chunks of a window
- MUST set `offset_bytes` and `chunk_length` such that chunks cover [0, total_bytes) without gaps or overlaps
- MUST set CORTEX_CHUNK_FLAG_LAST only on the final chunk
- SHOULD use chunk_length <= 8192 bytes (optimal for network MTU and memory cache)

A conformant adapter:
- MUST reassemble chunks into a complete window buffer
- MUST validate that `offset_bytes + chunk_length <= total_bytes`
- MUST NOT begin processing until CORTEX_CHUNK_FLAG_LAST is received
- SHOULD timestamp window arrival (tin) when CORTEX_CHUNK_FLAG_LAST is received

**Example (small window, single chunk)**:

```
sequence:     1
total_bytes:  2560  (160 samples × 4 channels × 4 bytes)
offset_bytes: 0
chunk_length: 2560
flags:        0x00000001  (CORTEX_CHUNK_FLAG_LAST)

Payload size: 20 + 2560 = 2580 bytes
```

**Example (large window, chunked)**:

```
Window: 160 samples × 64 channels × 4 bytes = 40960 bytes
Chunk size: 8192 bytes
Number of chunks: 5

Chunk 1:
  sequence:     2
  total_bytes:  40960
  offset_bytes: 0
  chunk_length: 8192
  flags:        0x00000000

Chunk 2:
  sequence:     2
  total_bytes:  40960
  offset_bytes: 8192
  chunk_length: 8192
  flags:        0x00000000

Chunk 3:
  sequence:     2
  total_bytes:  40960
  offset_bytes: 16384
  chunk_length: 8192
  flags:        0x00000000

Chunk 4:
  sequence:     2
  total_bytes:  40960
  offset_bytes: 24576
  chunk_length: 8192
  flags:        0x00000000

Chunk 5:
  sequence:     2
  total_bytes:  40960
  offset_bytes: 32768
  chunk_length: 8192
  flags:        0x00000001  (CORTEX_CHUNK_FLAG_LAST)
```

**Rationale**: Chunking enables transmission of arbitrarily large windows without requiring large contiguous frame buffers. The 8KB chunk size is chosen to fit within typical network MTU sizes (jumbo frames: 9KB) and CPU cache lines (L2: 256KB can hold ~32 chunks).

### 4.3.6 RESULT_CHUNK Frame (0x07)

**Direction**: Adapter → Harness

**Purpose**: Return kernel output data and device-side timing information, potentially split across multiple chunks for large outputs.

**When sent**: After processing a complete window

**Payload structure**:

```
Offset | Size | Field                   | Endianness | Description
-------|------|-------------------------|------------|---------------------------
0      | 4    | session_id              | LE         | Must match CONFIG
4      | 4    | sequence                | LE         | Must match WINDOW_CHUNK
8      | 8    | tin                     | LE         | Input complete (ns)
16     | 8    | tstart                  | LE         | Kernel start (ns)
24     | 8    | tend                    | LE         | Kernel end (ns)
32     | 8    | tfirst_tx               | LE         | First result byte tx (ns)
40     | 8    | tlast_tx                | LE         | Last result byte tx (ns)
48     | 4    | output_length_samples   | LE         | Output W
52     | 4    | output_channels         | LE         | Output C
56     | 4    | total_bytes             | LE         | Total result size (W×C×4)
60     | 4    | offset_bytes            | LE         | Offset of this chunk
64     | 4    | chunk_length            | LE         | Bytes in this chunk
68     | 4    | flags                   | LE         | CORTEX_CHUNK_FLAG_LAST
72     | N    | sample_data             | LE         | Float32 samples (LE)
```

**Total payload size**: 72 + chunk_length bytes

**Field descriptions**:

- `session_id`: Session identifier from CONFIG. Harness MUST verify this matches. Mismatch indicates adapter restart.

- `sequence`: Window sequence number from WINDOW_CHUNK. Harness uses this to match results with inputs.

- `tin`: Device timestamp (nanoseconds) when final WINDOW_CHUNK was received and decoded. Relative to adapter boot time.

- `tstart`: Device timestamp when kernel `process()` function was invoked.

- `tend`: Device timestamp when kernel `process()` function returned.

- `tfirst_tx`: Device timestamp when first byte of result was transmitted (start of first RESULT_CHUNK send).

- `tlast_tx`: Device timestamp when last byte of result was transmitted (end of final RESULT_CHUNK send).

- `output_length_samples`: Output window length (W). SHOULD match ACK dimensions unless kernel is adaptive.

- `output_channels`: Output channel count (C). SHOULD match ACK dimensions unless kernel is adaptive.

- `total_bytes`, `offset_bytes`, `chunk_length`, `flags`: Same semantics as WINDOW_CHUNK (see Section 4.3.5).

- `sample_data`: Float32 output samples in little-endian IEEE-754 format. Row-major order (all channels for sample 0, then all channels for sample 1, etc.).

**Timing field semantics**:

All timestamps are nanoseconds since an arbitrary epoch (typically adapter boot time). They are NOT wall-clock times.

The harness computes adapter overhead as:
```
processing_latency = tend - tstart
transmission_latency = tlast_tx - tfirst_tx
total_device_latency = tlast_tx - tin
```

See Section 6 (Telemetry) for complete latency decomposition.

**Chunking behavior**:

Identical to WINDOW_CHUNK. Large results (> 8KB) are split across multiple RESULT_CHUNK frames. All chunks for a given result share the same `session_id` and `sequence`.

**Metadata redundancy**: All chunks include the full metadata fields (session_id, timestamps, dimensions). The receiver extracts metadata from the first chunk (offset == 0) and ignores it in subsequent chunks. This redundancy simplifies parsing (no special-case logic for first chunk).

**Example (single chunk)**:

```
session_id:              0x4A7F3C21
sequence:                1
tin:                     1234567890123456  (ns)
tstart:                  1234567890123500
tend:                    1234567890123600
tfirst_tx:               1234567890123650
tlast_tx:                1234567890123700
output_length_samples:   160
output_channels:         64
total_bytes:             40960
offset_bytes:            0
chunk_length:            40960
flags:                   0x00000001  (CORTEX_CHUNK_FLAG_LAST)

Payload size: 72 + 40960 = 41032 bytes
```

**Validation requirements**:

A conformant harness:
- MUST verify `session_id` matches CONFIG
- MUST verify `sequence` matches expected value (monotonic)
- SHOULD verify timestamps are monotonic: tin <= tstart <= tend <= tfirst_tx <= tlast_tx
- MUST verify output dimensions match ACK (or CONFIG if ACK was 0)

### 4.3.7 ERROR Frame (0x06)

**Direction**: Either (typically Adapter → Harness)

**Purpose**: Report error conditions (protocol errors, kernel failures, validation errors).

**When sent**: Any time an error occurs

**Payload structure**:

```
Offset | Size | Field          | Endianness | Description
-------|------|----------------|------------|---------------------------
0      | 4    | error_code     | LE         | CORTEX_ERROR_* constant
4      | 256  | error_message  | N/A        | Human-readable (null-term)
```

**Total payload size**: 260 bytes

**Field descriptions**:

- `error_code`: Numeric error code (see table below). Used for programmatic error handling.

- `error_message`: Human-readable error description. NULL-terminated string up to 256 bytes. Used for logging and debugging.

**Standard error codes**:

| Code | Name                        | Description |
|------|-----------------------------|-------------|
| 1    | CORTEX_ERROR_TIMEOUT        | Operation timed out |
| 2    | CORTEX_ERROR_INVALID_FRAME  | Malformed frame received |
| 3    | CORTEX_ERROR_CALIBRATION_TOOBIG | Calibration state exceeds 16 MB |
| 4    | CORTEX_ERROR_KERNEL_INIT_FAILED | Kernel initialization failed |
| 5    | CORTEX_ERROR_KERNEL_EXEC_FAILED | Kernel execution failed |
| 6    | CORTEX_ERROR_SESSION_MISMATCH   | Session ID doesn't match CONFIG |
| 7    | CORTEX_ERROR_VERSION_MISMATCH   | Protocol version incompatible |
| 8    | CORTEX_ERROR_SHUTDOWN           | Adapter shutting down |

**Example**:

```
error_code:    4  (CORTEX_ERROR_KERNEL_INIT_FAILED)
error_message: "Failed to load kernel 'ica@f32': library not found"
```

**Hex dump**:

```
00000000: 04 00 00 00 46 61 69 6c  65 64 20 74 6f 20 6c 6f  |....Failed to lo|
00000010: 61 64 20 6b 65 72 6e 65  6c 20 27 69 63 61 40 66  |ad kernel 'ica@f|
00000020: 33 32 27 3a 20 6c 69 62  72 61 72 79 20 6e 6f 74  |32': library not|
00000030: 20 66 6f 75 6e 64 00 00  00 00 00 00 00 00 00 00  | found..........|
```

**Error handling**:

A conformant implementation:
- MAY send ERROR at any time after transport connection
- SHOULD include diagnostic information in `error_message` (file paths, system errors, etc.)
- MAY close the transport after sending ERROR (graceful shutdown)
- MUST NOT send additional frames after ERROR (protocol ends)

A conformant receiver:
- MUST handle ERROR frames at any point in the protocol state machine
- SHOULD log the error message for debugging
- SHOULD close the transport connection after receiving ERROR

---

## 4.4 Protocol State Machine

### 4.4.1 Overview

The CORTEX protocol follows a strict state machine with well-defined transitions. This ensures predictable error handling, prevents message reordering, and enables timeout-based failure detection.

### 4.4.2 States

A conformant implementation SHALL track the following protocol states:

**INIT**
- Initial state after transport connection established
- Waiting for HELLO from adapter
- Valid transitions: → HANDSHAKE (on HELLO), → ERROR (on timeout/error)

**HANDSHAKE**
- CONFIG sent, waiting for ACK
- Valid transitions: → READY (on ACK), → ERROR (on timeout/error)

**READY**
- Configuration complete, ready to process windows
- Valid transitions: → EXECUTING (on WINDOW_CHUNK), → ERROR (on error)

**EXECUTING**
- Window sent, waiting for RESULT
- Valid transitions: → READY (on RESULT), → ERROR (on timeout/error)

**ERROR**
- Error occurred, protocol terminated
- Valid transitions: (terminal state)

### 4.4.3 State Diagram

```
                      ┌──────┐
                      │ INIT │
                      └───┬──┘
                          │ HELLO received
                          ▼
                    ┌─────────────┐
                    │  HANDSHAKE  │
                    └──────┬──────┘
                           │ CONFIG sent, ACK received
                           ▼
                    ┌────────────┐
          ┌─────────┤   READY    │◄─────────┐
          │         └────────────┘          │
          │ WINDOW_CHUNK sent               │ RESULT received
          ▼                                 │
    ┌──────────────┐                        │
    │  EXECUTING   │────────────────────────┘
    └──────────────┘

    Any state can transition to ERROR on:
      - Timeout
      - Protocol error (CRC, MAGIC, VERSION mismatch)
      - Adapter error (ERROR frame received)
```

### 4.4.4 Handshake Sequence

The handshake establishes protocol compatibility and configures the kernel.

```
Harness                                    Adapter
   │                                          │
   │ [Transport connected]                    │ [Adapter process starts]
   │                                          │
   │◄──────────── HELLO ────────────────────│  STATE: INIT
   │                                          │  - Advertise capabilities
   │ [Validate ABI version]                   │  - List available kernels
   │ [Select kernel from list]                │
   │                                          │
   │────────────► CONFIG ───────────────────►│  STATE: HANDSHAKE
   │              - session_id                │
   │              - kernel name               │  [Load kernel library]
   │              - dimensions (W, H, C)      │  [Allocate buffers]
   │              - calibration state         │  [Initialize kernel]
   │                                          │
   │                                          │  [Determine output dims]
   │◄──────────── ACK ──────────────────────│  STATE: READY
   │              - output_window_length      │
   │              - output_channels           │
   │                                          │
   │ [Allocate output buffer]                 │
   │ [STATE: READY]                           │
```

**Timeout**: 5000ms (CORTEX_HANDSHAKE_TIMEOUT_MS)

A conformant implementation:
- MUST send HELLO immediately after transport connection
- MUST wait for CONFIG before sending ACK
- MUST NOT process windows before receiving CONFIG and sending ACK
- SHALL return to ERROR state if any handshake frame is malformed or times out

### 4.4.5 Window Execution Sequence

After successful handshake, the harness sends windows and receives results.

```
Harness                                    Adapter
   │                                          │
   │ [STATE: READY]                           │ [STATE: READY]
   │                                          │
   │────► WINDOW_CHUNK (seq=1, chunk 1/5) ──►│
   │────► WINDOW_CHUNK (seq=1, chunk 2/5) ──►│
   │────► WINDOW_CHUNK (seq=1, chunk 3/5) ──►│  [Reassemble chunks]
   │────► WINDOW_CHUNK (seq=1, chunk 4/5) ──►│
   │────► WINDOW_CHUNK (seq=1, chunk 5/5) ──►│  [CORTEX_CHUNK_FLAG_LAST]
   │                                          │
   │ [STATE: EXECUTING]                       │  timestamp tin
   │                                          │
   │                                          │  timestamp tstart
   │                                          │  kernel.process(input, output)
   │                                          │  timestamp tend
   │                                          │
   │                                          │  timestamp tfirst_tx
   │◄──── RESULT_CHUNK (seq=1, chunk 1/5) ───│
   │◄──── RESULT_CHUNK (seq=1, chunk 2/5) ───│
   │◄──── RESULT_CHUNK (seq=1, chunk 3/5) ───│  [Send chunks]
   │◄──── RESULT_CHUNK (seq=1, chunk 4/5) ───│
   │◄──── RESULT_CHUNK (seq=1, chunk 5/5) ───│  timestamp tlast_tx
   │                                          │
   │ [Reassemble chunks]                      │
   │ [Validate session_id, sequence]          │
   │ [Extract timing data]                    │
   │ [STATE: READY]                           │ [STATE: READY]
   │                                          │
   │  [Repeat for next window...]             │
```

**Timeout**: 10000ms per window (CORTEX_WINDOW_TIMEOUT_MS)

A conformant implementation:
- MUST increment `sequence` for each new window
- MUST match RESULT `sequence` with WINDOW_CHUNK `sequence`
- MUST NOT send the next window until receiving the previous RESULT
- SHALL return to ERROR state if sequence mismatch or timeout occurs

### 4.4.6 Error Handling Sequence

Error frames can be sent at any time to report failures.

```
Harness                                    Adapter
   │                                          │
   │────► WINDOW_CHUNK (seq=1) ─────────────►│
   │                                          │
   │                                          │  [Kernel execution fails]
   │                                          │
   │◄───────── ERROR (code=5) ───────────────│
   │           "Kernel NaN detected"          │
   │                                          │
   │ [Log error]                              │
   │ [STATE: ERROR]                           │ [STATE: ERROR]
   │ [Close transport]                        │ [Close transport]
```

A conformant implementation:
- MAY send ERROR at any state
- SHOULD include detailed error_message for diagnostics
- MUST transition to ERROR state after sending ERROR
- MUST close transport connection after ERROR (no recovery)

---

## 4.5 Chunking

### 4.5.1 Overview

Large data payloads (input windows, output results) are split into fixed-size chunks to avoid requiring large contiguous frame buffers and to optimize network transmission. Chunking is transparent to the application layer (callers send/receive complete buffers; the protocol layer handles chunking automatically).

### 4.5.2 Chunk Size

A conformant implementation SHOULD use a chunk size of 8192 bytes (8 KB).

This value is defined as `CORTEX_CHUNK_SIZE` in `cortex_wire.h`:

```c
#define CORTEX_CHUNK_SIZE (8 * 1024)
```

**Rationale**:

- **Network MTU**: 8KB fits within jumbo frame MTU (9000 bytes) with room for protocol overhead
- **Cache efficiency**: 8KB aligns with typical L1/L2 cache line sizes (64-256 bytes)
- **Memory fragmentation**: Smaller chunks reduce heap fragmentation on embedded systems
- **Latency**: Not too small (excessive overhead) or too large (head-of-line blocking)

Implementations MAY use different chunk sizes based on platform constraints, but 8KB is RECOMMENDED for interoperability and performance.

### 4.5.3 Chunking Algorithm (Sender)

A conformant sender SHALL split data larger than CORTEX_CHUNK_SIZE as follows:

```
Input: data buffer (size N bytes), sequence number

1. total_bytes = N
2. offset_bytes = 0
3. while (offset_bytes < total_bytes):
4.     chunk_length = min(CORTEX_CHUNK_SIZE, total_bytes - offset_bytes)
5.     is_last = (offset_bytes + chunk_length == total_bytes)
6.     flags = is_last ? CORTEX_CHUNK_FLAG_LAST : 0
7.
8.     Send frame:
9.         sequence       = sequence
10.        total_bytes    = N
11.        offset_bytes   = offset_bytes
12.        chunk_length   = chunk_length
13.        flags          = flags
14.        sample_data    = data[offset_bytes : offset_bytes + chunk_length]
15.
16.    offset_bytes += chunk_length
```

**Example**: 40KB window, 8KB chunks

```
Chunk 1: offset=0,     length=8192, flags=0x0
Chunk 2: offset=8192,  length=8192, flags=0x0
Chunk 3: offset=16384, length=8192, flags=0x0
Chunk 4: offset=24576, length=8192, flags=0x0
Chunk 5: offset=32768, length=8192, flags=0x1  (LAST)
```

### 4.5.4 Reassembly Algorithm (Receiver)

A conformant receiver SHALL reassemble chunks as follows:

```
Input: reassembly buffer (allocated to size from first chunk)

1. Wait for first chunk (offset == 0)
2. Extract total_bytes, allocate buffer if needed
3.
4. received_bytes = 0
5. while (true):
6.     Receive chunk frame
7.     Validate:
8.         - sequence matches expected
9.         - offset_bytes + chunk_length <= total_bytes
10.        - offset_bytes == received_bytes  (no gaps)
11.
12.    memcpy(buffer + offset_bytes, chunk_data, chunk_length)
13.    received_bytes += chunk_length
14.
15.    if (flags & CORTEX_CHUNK_FLAG_LAST):
16.        if (received_bytes != total_bytes):
17.            return ERROR_INCOMPLETE
18.        return SUCCESS
```

**Validation requirements**:

A conformant receiver:
- MUST verify chunks arrive in order (offset_bytes increases monotonically)
- MUST verify no gaps exist (offset_bytes == previous_offset + previous_length)
- MUST verify no overlaps exist (offset + length <= total_bytes)
- MUST verify CORTEX_CHUNK_FLAG_LAST is set on the final chunk
- MUST verify received_bytes == total_bytes when LAST flag is set
- SHALL return `CORTEX_ECHUNK_INCOMPLETE` (-2101) if validation fails

### 4.5.5 Chunk Sequence Numbering

The `sequence` field in WINDOW_CHUNK and RESULT_CHUNK frames identifies which window the chunk belongs to. All chunks for a given window share the same sequence number.

A conformant implementation:
- MUST use monotonically increasing sequence numbers (starts at 1)
- MUST use the same sequence for all chunks of a window
- MUST increment sequence for each new window
- SHOULD use uint32_t for sequence (wraps after 4 billion windows, acceptable)

**Sequence matching**: The adapter MUST return RESULT with the same sequence number as the corresponding WINDOW_CHUNK. This allows the harness to match results with inputs, even if windows are processed out of order (future extension for pipelining).

### 4.5.6 Error Handling

**Chunk timeout**:

If a chunk does not arrive within CORTEX_CHUNK_TIMEOUT_MS (1000ms), the receiver:
- MUST abort reassembly
- SHOULD discard partial window/result
- SHOULD transition to ERROR state
- MAY attempt to resynchronize by hunting for MAGIC

**Sequence mismatch**:

If a chunk arrives with an unexpected sequence number:
- MUST return `CORTEX_ECHUNK_SEQUENCE_MISMATCH` (-2100)
- SHOULD transition to ERROR state
- SHOULD NOT attempt to buffer multiple windows (no reordering support in protocol v1)

**Incomplete transfer**:

If the final chunk is received but `received_bytes != total_bytes`:
- MUST return `CORTEX_ECHUNK_INCOMPLETE` (-2101)
- SHOULD log offset/length values for debugging
- MUST discard partial data

### 4.5.7 Optimization Notes

**Zero-copy transmission**: Implementations MAY use scatter-gather I/O (e.g., `writev(2)`) to avoid copying chunk headers and data:

```c
struct iovec iov[2];
iov[0].iov_base = &chunk_header;
iov[0].iov_len = sizeof(chunk_header);
iov[1].iov_base = data + offset;
iov[1].iov_len = chunk_length;
writev(fd, iov, 2);
```

**Pipelining**: Protocol v1 does NOT support sending multiple windows before receiving results (no pipelining). The harness MUST wait for RESULT before sending the next WINDOW_CHUNK. Future protocol versions may relax this constraint.

**Adaptive chunk size**: Implementations MAY dynamically adjust chunk size based on transport characteristics (e.g., 16KB chunks for high-bandwidth TCP, 1KB chunks for UART). However, all chunks MUST include accurate offset_bytes and chunk_length fields.

---

## 4.6 Cross-References

**Related sections**:
- Section 2.2.2 (Adapter Lifecycle): Describes adapter spawn/shutdown behavior
- Section 3.4.3 (Calibration State Transfer): Defines calibration_state blob format
- Section 5.3 (Error Codes): Complete error code enumeration
- Section 6 (Telemetry and Timing): Device-side timestamp semantics and latency decomposition

**Implementation references**:
- `sdk/adapter/include/cortex_wire.h`: Wire format struct definitions
- `sdk/adapter/include/cortex_protocol.h`: Protocol API (send/recv frame functions)
- `sdk/adapter/include/cortex_endian.h`: Endianness conversion helpers
- `sdk/adapter/lib/protocol/protocol.c`: Protocol layer implementation (MAGIC hunting, CRC validation)
- `sdk/adapter/lib/protocol/crc32.c`: IEEE 802.3 CRC32 implementation
- `docs/reference/adapter-protocol.md`: Wire format reference documentation (477 lines)

---

## 4.7 Conformance Testing

To verify wire protocol conformance, implementations MUST pass the following test suites:

**CRC validation**:
```bash
make -C tests test-protocol
```

Tests verify:
- CRC32 computation correctness (IEEE 802.3 polynomial)
- CRC detection of single-bit errors, multi-bit errors, truncation
- Endianness conversion (little-endian wire format on all platforms)

**Frame parsing**:
```bash
make -C tests test-adapter-smoke
```

Tests verify:
- MAGIC hunting in corrupt streams
- Version mismatch detection
- Payload length validation
- Chunk reassembly correctness

**End-to-end protocol**:
```bash
make -C tests test-adapter-all-kernels
```

Tests verify:
- Complete handshake sequence (HELLO → CONFIG → ACK)
- Window execution (WINDOW_CHUNK → RESULT_CHUNK)
- Error frame handling
- Session ID validation
- Timeout behavior

All tests MUST pass before an adapter implementation is considered conformant with this specification.

---

**End of Section 4**
