# CORTEX Adapter Wire Protocol v1

This document specifies the binary wire format for communication between CORTEX harness and device adapters. Local adapters (in-process function calls) can ignore this and use struct passing directly. Remote adapters (network, serial, etc.) MUST implement this protocol exactly.

---

## Design Principles

1. **Field-by-field serialization**: NOT `sizeof(struct)` dumps (padding varies across compilers/platforms)
2. **Little-endian**: All multi-byte integers use little-endian byte order
3. **Explicit lengths**: All variable-length data prefixed with `uint32_t` length
4. **No null terminators**: Strings use `[length][bytes]` format (NOT C-style null-terminated)
5. **Sentinel values**: NULL strings use `length = 0xFFFFFFFF`

---

## Primitive Encoding

### Fixed-Width Integers
- `uint8_t`: 1 byte
- `uint16_t`: 2 bytes, little-endian
- `uint32_t`: 4 bytes, little-endian
- `uint64_t`: 8 bytes, little-endian
- `int32_t`: 4 bytes, two's complement, little-endian
- `float`: 4 bytes, IEEE 754 single precision

### Strings
**Format**: `[uint32_t length][bytes...]`

- **Non-NULL string**: `length = N`, followed by `N` bytes (NO null terminator)
  ```
  Example: "hello"
  Wire: [0x05 0x00 0x00 0x00][0x68 0x65 0x6C 0x6C 0x6F]
        └─ length=5       └─ "hello" (5 bytes)
  ```

- **NULL string**: `length = 0xFFFFFFFF`, NO bytes follow
  ```
  Example: NULL
  Wire: [0xFF 0xFF 0xFF 0xFF]
  ```

- **Empty string**: `length = 0`, NO bytes follow
  ```
  Example: ""
  Wire: [0x00 0x00 0x00 0x00]
  ```

### Fixed-Size Char Arrays
Struct fields like `char device_id[64]` are **logical maxima**. Wire encoding uses the variable-length string format above.

**Example**:
```c
// Struct field
char device_id[64] = "x86_64-native";

// Wire encoding (NOT 64 bytes of padding!)
[0x0D 0x00 0x00 0x00]["x86_64-native"]
└─ length=13         └─ 13 bytes (no padding, no null)
```

### Opaque Byte Blobs
**Format**: `[uint32_t size][bytes...]`

Similar to strings but for arbitrary binary data (e.g., kernel params).

---

## ABI Version Discovery

Before any wire protocol communication, the harness MUST verify the adapter's ABI version using dlsym().

**Discovery Sequence:**
```c
/* 1. Load adapter shared library */
void *handle = dlopen("adapter.so", RTLD_NOW | RTLD_LOCAL);
if (!handle) {
    /* dlopen failed */
    return -6;
}

/* 2. Discover ABI version symbol */
uint32_t (*abi_version_fn)(void) = dlsym(handle, "cortex_adapter_abi_version");
if (!abi_version_fn) {
    dlclose(handle);
    return -6;  /* Missing ABI symbol */
}

/* 3. Verify version matches */
uint32_t adapter_abi = abi_version_fn();
if (adapter_abi != CORTEX_ADAPTER_ABI_VERSION) {
    dlclose(handle);
    return -2;  /* ABI version mismatch */
}

/* 4. Version OK - proceed to cortex_adapter_get_v1() */
int32_t (*get_adapter)(cortex_adapter_t *, size_t) =
    dlsym(handle, "cortex_adapter_get_v1");
```

**Why This Matters:**
- Early version check BEFORE calling any adapter functions
- Prevents crashes from incompatible struct layouts
- Enables graceful error handling with descriptive messages
- Matches kernel plugin ABI discovery pattern

**Implementation Note:**
All adapters MUST link `cortex_adapter_abi.o` to export the `cortex_adapter_abi_version` symbol. This object is compiled once by the top-level CORTEX Makefile and linked into every adapter shared library.

---

## Message Types

### 1. HELLO (Adapter → Harness)
Sent immediately after connection establishment.

**Fields** (in order):
```
uint32_t  protocol_version      (must be 1)
[string]  device_id             (var-length)
[string]  arch                  (var-length)
[string]  os                    (var-length)
uint32_t  capabilities          (bitmask)
uint64_t  timestamp_freq_hz     (0 = ns, >0 = cycle freq)
[string]  timestamp_source      (var-length, e.g., "CLOCK_MONOTONIC")
```

**Example**:
```hex
Offset | Bytes                      | Field
-------|----------------------------|-------------------------------
0x0000 | 01 00 00 00                | protocol_version = 1
0x0004 | 0D 00 00 00                | device_id length = 13
0x0008 | 78 36 36 5F 36 34 2D ...   | "x86_64-native" (13 bytes)
0x0015 | 06 00 00 00                | arch length = 6
0x0019 | 78 38 36 5F 36 34          | "x86_64" (6 bytes)
0x001F | 05 00 00 00                | os length = 5
0x0023 | 6C 69 6E 75 78             | "linux" (5 bytes)
0x0028 | 0F 00 00 00                | capabilities = 0x0F (all v1 caps)
0x002C | 00 00 00 00 00 00 00 00    | timestamp_freq_hz = 0 (nanoseconds)
0x0034 | 10 00 00 00                | source length = 16
0x0038 | 43 4C 4F 43 4B 5F 4D ...   | "CLOCK_MONOTONIC" (16 bytes)
```

---

### 2. LOAD_KERNEL (Harness → Adapter)
Initializes a kernel instance.

**Fields** (in order):
```
[string]  kernel_path            (var-length or NULL sentinel)
[string]  kernel_id              (var-length or NULL sentinel)
uint32_t  sample_rate_hz
uint32_t  window_length_samples
uint32_t  hop_samples
uint32_t  channels
uint32_t  dtype
uint32_t  kernel_params_size
[blob]    kernel_params          (kernel_params_size bytes)
```

**XOR Constraint**: Exactly one of `kernel_path` or `kernel_id` MUST be NULL (encoded as `0xFFFFFFFF`).

**Example** (using kernel_path):
```hex
Offset | Bytes                      | Field
-------|----------------------------|-------------------------------
0x0000 | 1E 00 00 00                | kernel_path length = 30
0x0004 | 2E 2E 2F 6B 65 72 6E ...   | "../kernels/libcar.so" (30 bytes)
0x0022 | FF FF FF FF                | kernel_id = NULL
0x0026 | A0 00 00 00                | sample_rate_hz = 160
0x002A | A0 00 00 00                | window_length_samples = 160
0x002E | 50 00 00 00                | hop_samples = 80
0x0032 | 40 00 00 00                | channels = 64
0x0036 | 01 00 00 00                | dtype = CORTEX_DTYPE_FLOAT32
0x003A | 00 00 00 00                | kernel_params_size = 0 (no params)
```

**Example** (using kernel_id with params):
```hex
Offset | Bytes                      | Field
-------|----------------------------|-------------------------------
0x0000 | FF FF FF FF                | kernel_path = NULL
0x0004 | 09 00 00 00                | kernel_id length = 9
0x0008 | 6E 6F 74 63 68 5F 69 ...   | "notch_iir" (9 bytes)
0x0011 | A0 00 00 00                | sample_rate_hz = 160
0x0015 | A0 00 00 00                | window_length_samples = 160
0x0019 | 50 00 00 00                | hop_samples = 80
0x001D | 40 00 00 00                | channels = 64
0x0021 | 01 00 00 00                | dtype = CORTEX_DTYPE_FLOAT32
0x0025 | 10 00 00 00                | kernel_params_size = 16
0x0029 | 66 30 5F 68 7A 3D 36 ...   | "f0_hz=60.0&Q=30" (16 bytes)
```

---

### 3. PROCESS_WINDOW (Harness → Adapter)
Sends input window for processing.

**Fields** (in order):
```
uint64_t  t_in                  (or CORTEX_TIMESTAMP_ADAPTER_STAMPS)
uint32_t  input_bytes
[blob]    input_data            (input_bytes of raw samples)
```

**Example** (160 samples × 64 channels × 4 bytes = 40960 bytes):
```hex
Offset | Bytes                      | Field
-------|----------------------------|-------------------------------
0x0000 | 10 27 00 00 00 00 00 00    | t_in = 10000 (ns)
0x0008 | 00 A0 00 00                | input_bytes = 40960
0x000C | [40960 bytes of float32 data in channel-major order]
```

**t_in sentinel** (adapter will stamp):
```hex
0x0000 | FF FF FF FF FF FF FF FF    | t_in = CORTEX_TIMESTAMP_ADAPTER_STAMPS
0x0008 | 00 A0 00 00                | input_bytes = 40960
0x000C | [40960 bytes of float32 data]
```

---

### 4. RESULT (Adapter → Harness)
Returns processing results.

**Fields** (in order):
```
uint32_t  output_bytes
uint64_t  t_in                  (adapter's clock)
uint64_t  t_start               (adapter's clock)
uint64_t  t_end                 (adapter's clock)
uint64_t  deadline              (adapter's clock)
[blob]    output_data           (output_bytes of processed samples)
```

**Example** (160 samples × 64 channels × 4 bytes = 40960 bytes):
```hex
Offset | Bytes                      | Field
-------|----------------------------|-------------------------------
0x0000 | 00 A0 00 00                | output_bytes = 40960
0x0004 | 10 27 00 00 00 00 00 00    | t_in = 10000 ns
0x000C | 50 46 00 00 00 00 00 00    | t_start = 18000 ns
0x0014 | C8 4B 00 00 00 00 00 00    | t_end = 19400 ns
0x001C | 80 96 98 00 00 00 00 00    | deadline = 10000000 ns
0x0024 | [40960 bytes of float32 output data]
```

---

## Error Codes

Adapters return `int32_t` status codes from `init()` and `process_window()`:

- `0`: Success
- `-1`: Generic error (use for unspecified failures)
- `-2`: Invalid ABI version mismatch
- `-3`: XOR constraint violation (both or neither kernel_path/kernel_id set)
- `-4`: Invalid dtype (not one-hot)
- `-5`: Unsupported configuration (e.g., sample rate too high)
- `-6`: Kernel loading failure (dlopen/registry lookup failed)
- `-7`: Buffer allocation failure
- `-8`: Kernel init() returned NULL handle
- `-9` to `-99`: Reserved for future standard errors
- `<-100`: Adapter-specific error codes

**Wire encoding**: `int32_t` (4 bytes, little-endian, two's complement)

---

## Data Layout (Multi-Dimensional Arrays)

Input and output buffers contain multi-channel time-series data. Layout is **channel-major** (channels × samples):

**Format**: `channels × samples` (row-major)
```
Channel 0: [s₀ s₁ s₂ ... s_{W-1}]
Channel 1: [s₀ s₁ s₂ ... s_{W-1}]
...
Channel C-1: [s₀ s₁ s₂ ... s_{W-1}]
```

**Memory layout** (linear):
```
[ch0_s0][ch0_s1]...[ch0_sW-1][ch1_s0][ch1_s1]...[ch1_sW-1]...[chC-1_sW-1]
```

**Index calculation**:
```c
offset = (channel * window_length_samples + sample_idx) * dtype_size
```

**Example**: 64 channels, 160 samples, float32 (4 bytes)
- Total size: `64 × 160 × 4 = 40960 bytes`
- Channel 0 samples: `bytes[0:639]`
- Channel 1 samples: `bytes[640:1279]`
- Channel 63 samples: `bytes[40320:40959]`

---

## Clock Domain Consistency

**Critical rule**: All timestamps MUST use the same clock source (adapter's `now()` function).

**Scenarios**:

1. **Harness stamps t_in**:
   - Harness calls `adapter->now()` when data arrives
   - Passes this value as `t_in` in PROCESS_WINDOW message
   - Adapter uses same clock for `t_start`, `t_end`, `deadline`

2. **Adapter stamps t_in**:
   - Harness sets `t_in = CORTEX_TIMESTAMP_ADAPTER_STAMPS` (0xFFFFFFFFFFFFFFFF)
   - Adapter reads its clock immediately when PROCESS_WINDOW is received
   - Adapter uses same clock for all timestamps

**Never mix**:
- ❌ `t_in` from `CLOCK_REALTIME`, `t_start` from `CLOCK_MONOTONIC`
- ❌ `t_in` from harness's TSC, `t_end` from adapter's TSC (different CPUs)

**Always use**:
- ✅ All timestamps from `adapter->now()` (same clock, same frequency)

---

## Implementation Notes

### Endianness Handling

The wire protocol uses **little-endian** byte order for all multi-byte integers.

**Endianness detection**:
```c
#include <stdint.h>

int is_little_endian(void) {
    uint32_t x = 1;
    return *(uint8_t*)&x == 1;
}

/* Byte-swap helpers for big-endian systems */
uint32_t htole32(uint32_t x) {
    if (is_little_endian()) return x;
    return ((x & 0xFF000000) >> 24) |
           ((x & 0x00FF0000) >>  8) |
           ((x & 0x0000FF00) <<  8) |
           ((x & 0x000000FF) << 24);
}

uint64_t htole64(uint64_t x) {
    if (is_little_endian()) return x;
    return ((x & 0xFF00000000000000ULL) >> 56) |
           ((x & 0x00FF000000000000ULL) >> 40) |
           ((x & 0x0000FF0000000000ULL) >> 24) |
           ((x & 0x000000FF00000000ULL) >>  8) |
           ((x & 0x00000000FF000000ULL) <<  8) |
           ((x & 0x0000000000FF0000ULL) << 24) |
           ((x & 0x000000000000FF00ULL) << 40) |
           ((x & 0x00000000000000FFULL) << 56);
}
```

**NOTE**: Many systems provide `htole32()` / `le32toh()` in `<endian.h>` (Linux) or `<sys/endian.h>` (BSD/macOS). Use platform builtins when available.

### String Serialization Example
```c
void write_string(uint8_t **buf, const char *str) {
    if (str == NULL) {
        uint32_t sentinel = htole32(CORTEX_STRING_NULL_SENTINEL);
        memcpy(*buf, &sentinel, 4);
        *buf += 4;
    } else {
        uint32_t len = htole32((uint32_t)strlen(str));
        memcpy(*buf, &len, 4);
        *buf += 4;
        memcpy(*buf, str, strlen(str));  /* String bytes are endian-agnostic */
        *buf += strlen(str);
    }
}
```

### Blob Serialization Example
```c
void write_blob(uint8_t **buf, const void *data, uint32_t size) {
    uint32_t size_le = htole32(size);
    memcpy(*buf, &size_le, 4);
    *buf += 4;
    memcpy(*buf, data, size);
    *buf += size;
}
```

---

## Versioning and Extensions

- **Protocol version**: Embedded in HELLO message (`protocol_version = 1`)
- **Struct size fields**: Enable forward compatibility (e.g., `cortex_adapter_config_t.struct_size`)
- **Reserved bits**: Capability flags 4-31 reserved for future use
- **Immutability**: v1 protocol is frozen; v2 will use new message types or version field

**Future-proofing**:
- Receivers MUST ignore unknown capability bits
- Receivers MUST skip unknown trailing bytes in variable-length messages
- Senders MUST NOT use reserved bits/fields without bumping protocol version

---

## Security Considerations

### Memory Safety
- **Buffer overflows**: Validate `input_bytes` and `output_bytes` against allocated buffer sizes
- **Integer overflows**: Use checked arithmetic for size calculations (e.g., `channels × samples × dtype_size`)
- **NULL pointer dereference**: Validate string lengths before accessing data
- **Malformed messages**: Reject if lengths exceed reasonable limits (e.g., >1GB)

**Recommended limits**:
- Maximum string length: 4096 bytes
- Maximum blob size: 1GB (platform-dependent)
- Maximum channels × samples: 2³² - 1 (uint32_t max)

### Transport Security

**CRITICAL: The wire protocol specification does NOT include encryption or authentication.**

When deploying remote adapters over a network, implementations **MUST** use one of:
- **TLS/SSL**: Wrap socket communication with TLS 1.3+ for encryption and certificate-based authentication
- **SSH Tunneling**: Run protocol over SSH tunnel (e.g., `ssh -L 9000:localhost:9000 remote-host`)
- **VPN**: Use WireGuard, IPSec, or equivalent to encrypt entire network path
- **Unix Domain Sockets**: For same-machine communication, use UDS instead of TCP

**Threat model for unauthenticated transports**:
- **Data exposure**: BCI signal data and kernel parameters transmitted in cleartext
- **Tampering**: Attacker can modify inputs/outputs, inject malicious data
- **Impersonation**: Attacker can spoof remote adapter or harness
- **Remote code execution**: Malicious adapter can send oversized buffers to trigger vulnerabilities

**Example: TLS wrapper** (production deployments):
```c
/* Use OpenSSL, mbedTLS, or similar to wrap socket communication */
SSL_CTX *ctx = SSL_CTX_new(TLS_client_method());
SSL_CTX_set_min_proto_version(ctx, TLS1_3_VERSION);
SSL_CTX_load_verify_locations(ctx, "ca-cert.pem", NULL);
SSL *ssl = SSL_new(ctx);
SSL_set_fd(ssl, sockfd);
SSL_connect(ssl);
/* Now use SSL_read/SSL_write instead of recv/send */
```

**Authentication**: Verify remote peer identity using:
- X.509 certificates (TLS)
- SSH host keys
- Pre-shared keys (PSK) for embedded systems

---

## Testing

Implementations SHOULD validate:
1. ✅ NULL string encoding/decoding
2. ✅ Empty string encoding/decoding
3. ✅ XOR constraint enforcement (kernel_path vs kernel_id)
4. ✅ Endianness handling on big-endian targets
5. ✅ Buffer size calculations with overflow checks
6. ✅ Round-trip serialization (encode → decode → verify equality)

**Reference test vectors**: See `tests/test_adapter_protocol.c` (future).

---

## Examples

See `README.md` for complete adapter implementation examples including:
- Local adapter (in-process function calls, no serialization)
- TCP adapter (remote execution over network)
- Serial adapter (embedded target over UART)
