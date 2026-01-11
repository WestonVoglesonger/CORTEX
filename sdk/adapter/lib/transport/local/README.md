# Local IPC Transports

**Directory:** `sdk/adapter/lib/transport/local/`
**Use Case:** Same-machine communication between harness and adapter
**Platforms:** Linux, macOS (POSIX-compliant systems)

Local transports enable high-performance communication when the harness and adapter run on the same machine. They bypass the network stack and use OS-provided IPC mechanisms for minimal latency.

---

## Overview

| Transport | File | Latency | Throughput | Use When... |
|-----------|------|---------|------------|-------------|
| **Mock** | `mock.c` | ~50µs | 500 MB/s | Development, testing, debugging |

---

## Mock Transport (Socketpair)

**File:** `mock.c` (182 lines)
**Mechanism:** POSIX `socketpair(AF_UNIX, SOCK_STREAM, 0)`
**Latency:** ~45-50µs (P50)
**Throughput:** ~500 MB/s

### Purpose

The mock transport is the **default transport for local development**. It's called "mock" not because it's fake, but because it simulates a real transport using standard Unix IPC primitives (socketpair).

**Use it for:**
- Local development and testing
- Quick iteration on adapter code
- Debugging protocol implementation
- CI/CD integration tests
- Cross-platform development (works everywhere)

### How It Works

```
┌──────────────┐                     ┌──────────────┐
│   Harness    │                     │   Adapter    │
│              │                     │              │
│  sv[0] ◄─────┼─────socketpair()────┼─────► sv[1] │
│  (FD 3)      │                     │  (stdin/out) │
└──────────────┘                     └──────────────┘
```

1. Harness creates a socketpair: `socketpair(AF_UNIX, SOCK_STREAM, 0, sv)`
2. Harness forks and execs adapter, passing `sv[1]` as stdin/stdout
3. Harness keeps `sv[0]` for communication
4. Both sides read/write to their respective FDs

**Key Properties:**
- **Bidirectional:** Full-duplex communication
- **Reliable:** Guaranteed delivery (no packet loss)
- **In-order:** Messages arrive in send order
- **Flow-controlled:** Kernel buffers prevent overflow

### API

#### cortex_transport_mock_create()

```c
cortex_transport_t* cortex_transport_mock_create(int fd);
```

Creates a mock transport from a **bidirectional file descriptor** (e.g., socketpair).

**Parameters:**
- `fd`: File descriptor for bidirectional communication

**Returns:**
- Non-NULL: Successfully created transport
- NULL: Allocation failure

**Example (Harness Side):**
```c
int sv[2];
if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) < 0) {
    perror("socketpair");
    return -1;
}

pid_t pid = fork();
if (pid == 0) {
    /* Child: exec adapter */
    close(sv[0]);
    dup2(sv[1], STDIN_FILENO);
    dup2(sv[1], STDOUT_FILENO);
    close(sv[1]);
    execl("./my_adapter", "my_adapter", NULL);
    _exit(1);
}

/* Parent: communicate via sv[0] */
close(sv[1]);
cortex_transport_t *transport = cortex_transport_mock_create(sv[0]);
```

**Example (Adapter Side):**
```c
/* Adapter reads from stdin, writes to stdout */
cortex_transport_t *transport = cortex_transport_mock_create(STDIN_FILENO);

/* Or equivalently: */
cortex_transport_t *transport = cortex_transport_mock_create_from_fds(STDIN_FILENO, STDOUT_FILENO);
```

---

#### cortex_transport_mock_create_from_fds()

```c
cortex_transport_t* cortex_transport_mock_create_from_fds(int read_fd, int write_fd);
```

Creates a mock transport from **separate read/write file descriptors**.

**Parameters:**
- `read_fd`: File descriptor for reading (e.g., stdin)
- `write_fd`: File descriptor for writing (e.g., stdout)

**Returns:**
- Non-NULL: Successfully created transport
- NULL: Allocation failure

**Use case:** Adapters that communicate via stdin/stdout separately.

**Example:**
```c
/* Adapter using stdin for receive, stdout for send */
cortex_transport_t *transport = cortex_transport_mock_create_from_fds(
    STDIN_FILENO,   /* read from stdin */
    STDOUT_FILENO   /* write to stdout */
);
```

---

### Implementation Details

**recv() Implementation:**
- Uses `poll()` with timeout for blocking recv
- Returns `CORTEX_ETIMEDOUT` on timeout
- Returns `CORTEX_ECONNRESET` on EOF
- Supports partial reads

**send() Implementation:**
- Uses `write()` (may block until complete)
- Returns number of bytes written
- Returns `CORTEX_ECONNRESET` on broken pipe

**close() Implementation:**
- Closes file descriptor(s)
- Frees transport context

**get_timestamp_ns() Implementation:**
- Uses `clock_gettime(CLOCK_MONOTONIC, ...)`
- Returns nanoseconds since arbitrary epoch

---

### Performance

Measured on **MacBook Pro M1 (arm64)**:

| Metric | Value |
|--------|-------|
| P50 Latency | 45µs |
| P95 Latency | 95µs |
| P99 Latency | 120µs |
| Throughput | ~500 MB/s |
| Overhead | Context switch + kernel copy |

**Bottlenecks:**
- Context switch overhead (~20µs)
- Kernel buffer copy (~25µs)
- Poll syscall overhead (~5µs)

---

### Troubleshooting

**"Broken pipe" error:**
- Adapter exited unexpectedly
- Check adapter logs for crashes
- Verify handshake completes

**recv() blocks forever:**
- Adapter isn't sending data
- Check adapter is running (`ps aux | grep adapter`)
- Verify protocol frame format

**High latency:**
- Expected for socketpair (~50µs baseline)
- Profile with `strace -tt`
- For lower latency, consider TCP over localhost or wait for future optimizations

---

## Best Practices

✅ **Use mock transport for:**
- Local development and testing
- Running CI/CD tests
- Debugging protocol issues
- Cross-platform development

❌ **Don't use mock when:**
- Need absolute minimum latency (<10µs) - wait for future optimizations
- Remote devices (use TCP transport instead)

---

## See Also

- **Transport Selection Guide:** [`../README.md`](../README.md)
- **Example Usage:** `primitives/adapters/v1/native/adapter.c`
- **Protocol Layer:** `../protocol/README.md`
- **Transport API:** `../../include/cortex_transport.h`
