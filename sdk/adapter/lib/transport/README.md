# CORTEX Transport Layer

**Purpose:** Abstract communication channel between harness and device adapter
**Location:** `sdk/adapter/lib/transport/`
**API:** `cortex_transport_t` interface defined in `include/cortex_transport.h`

The transport layer decouples the adapter protocol from the physical communication medium, enabling adapters to run on different platforms (local processes, network devices, embedded systems) without changing protocol code.

---

## Quick Reference

| Transport | Latency | Throughput | Setup | Use When... |
|-----------|---------|------------|-------|-------------|
| **[Mock](local/)** (socketpair) | ~50µs | 500 MB/s | Trivial | Testing locally, development |
| **[Shared Memory](local/)** | ~5µs | 2 GB/s | Easy | Benchmarking overhead, performance testing |
| **[TCP](network/)** | ~500µs | 100 MB/s | Easy | Jetson, Pi, remote x86 hosts |
| **[UART](serial/)** | ~10ms | 11 KB/s @ 115200 | Moderate | Embedded dev, STM32, ESP32 |
| **Custom** | Varies | Varies | Advanced | Special hardware, proprietary protocols |

---

## Transport Interface

All transports implement this unified API:

```c
typedef struct cortex_transport_api {
    void *ctx;  /* Transport-specific context (opaque) */

    /* Send data (blocking until complete) */
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

**Transport Errors:**
```c
CORTEX_ETIMEDOUT   = -1000  /* recv() timeout expired */
CORTEX_ECONNRESET  = -1001  /* Connection closed/reset */
```

**Negative errno values:**
Functions may also return `-errno` for platform-specific errors (e.g., `-EPIPE`, `-ECONNREFUSED`).

### recv() Contract

```c
ssize_t (*recv)(void *ctx, void *buf, size_t len, uint32_t timeout_ms);
```

**Returns:**
- `> 0`: Number of bytes read (may be less than `len`)
- `0`: Connection closed gracefully (EOF)
- `CORTEX_ETIMEDOUT (-1000)`: Timeout expired, no data available
- `CORTEX_ECONNRESET (-1001)`: Connection reset
- `< 0` (other): Platform-specific error (negative errno)

**Behavior:**
- **MUST block** until data arrives or timeout expires
- **MAY return partial reads** (caller handles reassembly)
- **MUST respect timeout** (milliseconds, 0 = non-blocking)

**Example:**
```c
uint8_t buf[256];
ssize_t n = transport->recv(transport->ctx, buf, sizeof(buf), 5000);  /* 5s timeout */

if (n > 0) {
    /* Successfully received n bytes */
} else if (n == CORTEX_ETIMEDOUT) {
    /* No data after 5 seconds */
} else if (n == CORTEX_ECONNRESET || n == 0) {
    /* Connection closed */
} else {
    /* Other error: check errno or -n */
}
```

### send() Contract

```c
ssize_t (*send)(void *ctx, const void *buf, size_t len);
```

**Returns:**
- `> 0`: Number of bytes written
- `< 0`: Error (CORTEX_ECONNRESET or negative errno)

**Behavior:**
- **MAY block** until all bytes are written
- **MAY return partial writes** (caller handles retries)
- For most transports, sends all bytes or fails

**Example:**
```c
const uint8_t data[] = {1, 2, 3, 4};
ssize_t n = transport->send(transport->ctx, data, sizeof(data));

if (n == sizeof(data)) {
    /* All bytes sent successfully */
} else if (n > 0) {
    /* Partial write - rare, but handle it */
} else {
    /* Error */
}
```

### close() Contract

```c
void (*close)(void *ctx);
```

- Closes underlying connection/file descriptor
- Frees transport context memory
- **After calling close(), transport pointer is invalid**

### get_timestamp_ns() Contract

```c
uint64_t (*get_timestamp_ns)(void);
```

**Returns:** Nanoseconds since arbitrary epoch (monotonic, no wraparound)

**Platforms:**
- Linux/macOS: `CLOCK_MONOTONIC` via `clock_gettime()`
- STM32: DWT cycle counter
- ESP32: `esp_timer_get_time()`

---

## Transport Implementations

### Local Transports (`local/`)

#### Mock (Socketpair)

**File:** `local/mock.c`
**Constructor:** `cortex_transport_mock_create(int fd)`
**Use Case:** Local testing, same-machine adapters

**How it works:**
- Uses POSIX `socketpair()` for bidirectional IPC
- Harness creates socketpair, passes one FD to adapter via fork/exec
- Adapter reads/writes to inherited FD (stdin/stdout)

**Performance:**
- Latency: ~50µs (context switch overhead)
- Throughput: ~500 MB/s
- No network stack overhead

**Example:**
```c
/* Harness side */
int sv[2];
socketpair(AF_UNIX, SOCK_STREAM, 0, sv);

pid_t pid = fork();
if (pid == 0) {
    /* Child: exec adapter with socketpair FD */
    dup2(sv[1], STDIN_FILENO);
    dup2(sv[1], STDOUT_FILENO);
    execl("./my_adapter", "my_adapter", NULL);
}

/* Parent: communicate via sv[0] */
cortex_transport_t *transport = cortex_transport_mock_create(sv[0]);
```

**Limitations:**
- Single machine only
- Requires fork()/exec() capability

**See:** [local/README.md](local/README.md)

---

#### Shared Memory (SHM)

**File:** `local/shm.c`
**Constructors:**
- `cortex_transport_shm_create_harness(const char *name)` (harness side)
- `cortex_transport_shm_create_adapter(const char *name)` (adapter side)

**Use Case:** Performance testing, measuring pure adapter overhead

**How it works:**
- POSIX `shm_open()` + `mmap()` for shared memory region
- Two lock-free ring buffers (256KB each direction)
- POSIX named semaphores for producer/consumer signaling
- macOS compatibility layer for `sem_timedwait()`

**Performance:**
- Latency: ~5µs (memory copy + semaphore)
- Throughput: ~2 GB/s
- **Fastest transport** - ideal for overhead measurement

**Example:**
```c
/* Harness side */
cortex_transport_t *transport = cortex_transport_shm_create_harness("bench01");

/* Adapter side (separate process) */
cortex_transport_t *transport = cortex_transport_shm_create_adapter("bench01");
```

**Platform Notes:**
- macOS: Uses sem_trywait() + polling (no sem_timedwait support)
- Linux: Native sem_timedwait()
- Both sides must use **same name** to connect

**Limitations:**
- Single machine only
- Requires POSIX shared memory support
- Fixed buffer size (256KB per direction)

**See:** [local/README.md](local/README.md)

---

### Network Transports (`network/`)

#### TCP Client

**File:** `network/tcp_client.c`
**Constructor:** `cortex_transport_tcp_client_create(const char *host, uint16_t port, uint32_t timeout_ms)`
**Use Case:** Jetson Nano, Raspberry Pi, remote x86 hosts

**How it works:**
- Standard TCP sockets (BSD sockets API)
- Non-blocking connect with timeout
- `poll()` for recv timeout support
- TCP_NODELAY enabled (disables Nagle's algorithm for low latency)

**Performance:**
- Latency: ~500µs (localhost), ~1-5ms (LAN), ~50-200ms (WAN)
- Throughput: ~100 MB/s (GigE), ~12 MB/s (100Mbps)
- Network stack overhead

**Example:**
```c
/* Connect to Jetson Nano at 192.168.1.100:8080 */
cortex_transport_t *transport = cortex_transport_tcp_client_create(
    "192.168.1.100", 8080, 5000  /* 5 second connect timeout */
);

if (!transport) {
    perror("Failed to connect");
    return -1;
}
```

**Platform Notes:**
- Works on Linux, macOS, Windows (with Winsock)
- Firewall rules may block connections
- NAT traversal may require port forwarding

**Limitations:**
- Higher latency than local transports
- Network reliability affects measurements
- Requires network stack on embedded targets

**See:** [network/README.md](network/README.md)

---

### Serial Transports (`serial/`)

#### UART POSIX

**File:** `serial/uart_posix.c`
**Constructor:** `cortex_transport_uart_posix_create(const char *device, uint32_t baud_rate)`
**Use Case:** Development with USB-to-serial adapters, embedded Linux (Pi, Jetson)

**How it works:**
- POSIX termios API for serial port configuration
- Configures 8N1 (8 data bits, no parity, 1 stop bit)
- `select()` for recv timeout support
- Raw mode (no line processing)

**Performance:**
- Latency: ~10ms @ 115200 baud
- Throughput: ~11 KB/s @ 115200, ~44 KB/s @ 460800, ~88 KB/s @ 921600
- Limited by serial baud rate

**Example:**
```c
/* Connect to USB-to-serial adapter at 115200 baud */
cortex_transport_t *transport = cortex_transport_uart_posix_create(
    "/dev/ttyUSB0", 115200
);

if (!transport) {
    perror("Failed to open serial port");
    return -1;
}
```

**Supported Baud Rates:**
- Standard: 9600, 19200, 38400, 57600, 115200, 230400
- Extended (platform-dependent): 460800, 921600

**Platform Notes:**
- Linux: `/dev/ttyUSB*`, `/dev/ttyACM*`
- macOS: `/dev/cu.usbserial-*`
- Requires read/write permissions (add user to `dialout` group on Linux)

**Limitations:**
- Slow compared to network transports
- Sensitive to noise/interference
- Buffer overruns at high data rates

**See:** [serial/README.md](serial/README.md)

---

### Embedded Transports (`embedded/`)

**Status:** Planned for Phase 2+

**Future implementations:**
- STM32 UART (HAL-based, DMA)
- STM32 SPI (high-speed, full-duplex)
- ESP32 UART (ESP-IDF)
- CAN bus (automotive/industrial)

**See:** [embedded/README.md](embedded/README.md)

---

## Choosing a Transport

### Development Workflow

```
1. Start with Mock        → Verify protocol implementation locally
2. Test with SHM          → Measure adapter overhead (baseline)
3. Deploy with TCP/UART   → Validate on target platform
```

### Decision Matrix

**Question 1: Is your adapter on the same machine as the harness?**
- **Yes** → Use **Mock** (easy) or **SHM** (fast)
- **No** → Go to Question 2

**Question 2: Does the target device have a network stack?**
- **Yes** (Jetson, Pi, x86) → Use **TCP**
- **No** (bare-metal embedded) → Use **UART** or custom transport

**Question 3: Are you benchmarking transport overhead?**
- **Yes** → Use **SHM** (minimizes transport latency)
- **No** → Use most convenient transport

**Question 4: Is latency critical?**
- **Very critical** (<100µs) → **SHM** only
- **Somewhat critical** (<5ms) → **Mock** or **TCP** (localhost)
- **Not critical** (>10ms) → **TCP** or **UART**

---

## Performance Comparison

Measured on **MacBook Pro M1 (arm64)**, loopback configuration:

| Transport | Latency (P50) | Latency (P99) | Throughput | Jitter |
|-----------|---------------|---------------|------------|--------|
| SHM       | 5µs           | 15µs          | 2 GB/s     | Low    |
| Mock      | 45µs          | 120µs         | 500 MB/s   | Low    |
| TCP (localhost) | 180µs   | 450µs         | 800 MB/s   | Medium |
| TCP (LAN) | 1.2ms         | 3.5ms         | 100 MB/s   | Medium |
| UART (115200) | 12ms      | 25ms          | 11 KB/s    | High   |
| UART (921600) | 1.8ms     | 4.2ms         | 88 KB/s    | High   |

**Note:** Real-world performance varies by platform, network conditions, and workload.

---

## Creating a Custom Transport

### Step 1: Implement the Interface

```c
#include "cortex_transport.h"

typedef struct {
    int my_fd;
    void *my_ctx;
} my_transport_ctx_t;

static ssize_t my_recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms) {
    my_transport_ctx_t *my_ctx = (my_transport_ctx_t *)ctx;
    /* Your recv logic here */
    /* Return > 0 for success, CORTEX_ETIMEDOUT, CORTEX_ECONNRESET, or -errno */
}

static ssize_t my_send(void *ctx, const void *buf, size_t len) {
    my_transport_ctx_t *my_ctx = (my_transport_ctx_t *)ctx;
    /* Your send logic here */
    /* Return number of bytes sent or < 0 for error */
}

static void my_close(void *ctx) {
    my_transport_ctx_t *my_ctx = (my_transport_ctx_t *)ctx;
    /* Cleanup resources */
    free(my_ctx);
}

static uint64_t my_timestamp_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}
```

### Step 2: Create Constructor

```c
cortex_transport_t *my_transport_create(/* your params */) {
    my_transport_ctx_t *ctx = (my_transport_ctx_t *)malloc(sizeof(my_transport_ctx_t));
    if (!ctx) return NULL;

    /* Initialize your context */
    ctx->my_fd = /* ... */;

    cortex_transport_t *transport = (cortex_transport_t *)malloc(sizeof(cortex_transport_t));
    if (!transport) {
        free(ctx);
        return NULL;
    }

    transport->ctx = ctx;
    transport->recv = my_recv;
    transport->send = my_send;
    transport->close = my_close;
    transport->get_timestamp_ns = my_timestamp_ns;

    return transport;
}
```

### Step 3: Use in Adapter

```c
int main(void) {
    cortex_transport_t *transport = my_transport_create(/* params */);
    if (!transport) {
        fprintf(stderr, "Failed to create transport\n");
        return 1;
    }

    /* Use transport with protocol layer as normal */
    cortex_protocol_send_frame(transport, ...);

    transport->close(transport->ctx);
    free(transport);
    return 0;
}
```

---

## Testing Transports

### Unit Test Pattern

```c
void test_transport_roundtrip(cortex_transport_t *transport) {
    const uint8_t data[] = {1, 2, 3, 4, 5};

    /* Send */
    ssize_t sent = transport->send(transport->ctx, data, sizeof(data));
    assert(sent == sizeof(data));

    /* Receive */
    uint8_t buf[sizeof(data)];
    ssize_t recvd = transport->recv(transport->ctx, buf, sizeof(buf), 1000);
    assert(recvd == sizeof(data));
    assert(memcmp(buf, data, sizeof(data)) == 0);

    printf("✓ Roundtrip successful\n");
}
```

### Integration Test

```bash
# Test with harness
cd tests
make test_adapter_smoke
./test_adapter_smoke  # Uses mock transport by default
```

---

## Troubleshooting

### Common Issues

**recv() returns ETIMEDOUT immediately**
- Check timeout value (0 = non-blocking)
- Verify sender is actually sending data
- Check for clock/timing issues

**send() blocks forever**
- Check if receiver is consuming data
- Look for deadlock (both sides waiting)
- Verify buffer sizes (may be full)

**Connection refused (TCP)**
- Check firewall rules
- Verify server is listening on correct port
- Check IP address/hostname

**Permission denied (UART)**
- Add user to `dialout` group: `sudo usermod -a -G dialout $USER`
- Check device permissions: `ls -l /dev/ttyUSB0`

**High latency**
- For TCP: Check Nagle's algorithm (should be disabled via TCP_NODELAY)
- For UART: Increase baud rate if hardware supports
- For all: Profile with `strace` or similar tools

---

## See Also

- **API Header:** `include/cortex_transport.h`
- **Example Implementation:** `local/mock.c`
- **Usage Example:** `primitives/adapters/v1/x86@loopback/adapter.c`
- **Protocol Layer:** `lib/protocol/README.md`
- **SDK Overview:** `../../README.md`
