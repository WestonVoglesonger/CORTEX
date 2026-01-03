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
| **Shared Memory** | `shm.c` | ~5µs | 2 GB/s | Performance benchmarking, overhead measurement |

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
- Use shared memory if latency critical
- Profile with `strace -tt`

---

## Shared Memory Transport

**File:** `shm.c` (540 lines)
**Mechanism:** POSIX `shm_open()` + `mmap()` + ring buffers + semaphores
**Latency:** ~5µs (P50)
**Throughput:** ~2 GB/s

### Purpose

The shared memory transport is the **fastest local transport** available. It minimizes overhead to measure pure adapter/kernel performance without transport interference.

**Use it for:**
- Performance benchmarking (baseline measurements)
- Overhead analysis (isolate kernel vs transport latency)
- High-throughput scenarios (large windows, high sample rates)
- Latency-critical development

**Do NOT use for:**
- Production deployments (too complex)
- Remote devices (local-only)
- General development (mock is easier)

### How It Works

```
┌──────────────────────────────────────────────────────────┐
│               POSIX Shared Memory Region                 │
│  (/cortex_shm_<name>)                                    │
│                                                          │
│  ┌─────────────────────┐  ┌─────────────────────┐      │
│  │  Ring Buffer (H→A)  │  │  Ring Buffer (A→H)  │      │
│  │  256KB              │  │  256KB              │      │
│  │  write_pos, read_pos│  │  write_pos, read_pos│      │
│  └─────────────────────┘  └─────────────────────┘      │
└──────────────────────────────────────────────────────────┘
            ▲                           ▲
            │                           │
    ┌───────┴────────┐         ┌────────┴────────┐
    │  Harness       │         │  Adapter        │
    │  send → H→A    │         │  recv ← H→A     │
    │  recv ← A→H    │         │  send → A→H     │
    └────────────────┘         └─────────────────┘

Synchronization:
  /cortex_sem_h2a_<name>  → Harness posts when data ready (H→A)
  /cortex_sem_a2h_<name>  → Adapter posts when data ready (A→H)
```

**Architecture:**
1. **Shared memory region:** Contains two ring buffers (one per direction)
2. **Ring buffers:** Lock-free single-producer/single-consumer queues
3. **Semaphores:** Signal data availability (avoid polling)

**Key Properties:**
- **Zero-copy:** Data written directly to shared memory
- **Lock-free:** No mutexes (only atomic read/write pointers)
- **Bi-directional:** Independent ring buffers per direction
- **Flow-controlled:** Ring buffers prevent overflow

### API

#### cortex_transport_shm_create_harness()

```c
cortex_transport_t* cortex_transport_shm_create_harness(const char *name);
```

Creates shared memory region and semaphores (**harness side only**).

**Parameters:**
- `name`: Unique name for this SHM region (e.g., `"bench01"`, `"test"`)

**Returns:**
- Non-NULL: Successfully created transport
- NULL: Failure (shm_open, mmap, or sem_open failed)

**Side effects:**
- Creates `/cortex_shm_<name>` shared memory object
- Creates `/cortex_sem_h2a_<name>` semaphore
- Creates `/cortex_sem_a2h_<name>` semaphore
- Allocates and zero-initializes 512KB+ region

**Example:**
```c
cortex_transport_t *transport = cortex_transport_shm_create_harness("bench01");
if (!transport) {
    perror("Failed to create SHM transport");
    return -1;
}

/* Harness can now communicate */
cortex_protocol_send_frame(transport, ...);
```

**Cleanup:**
When harness calls `transport->close()`, it automatically:
- Unlinks shared memory (`shm_unlink`)
- Unlinks semaphores (`sem_unlink`)
- Frees all resources

---

#### cortex_transport_shm_create_adapter()

```c
cortex_transport_t* cortex_transport_shm_create_adapter(const char *name);
```

Connects to **existing** shared memory region created by harness (**adapter side only**).

**Parameters:**
- `name`: Same name used by harness (must match exactly)

**Returns:**
- Non-NULL: Successfully connected
- NULL: Failure (shm doesn't exist, or connection error)

**Behavior:**
- Opens existing `/cortex_shm_<name>` (fails if harness hasn't created it yet)
- Opens existing semaphores
- Maps shared memory region
- **Does NOT create** - only connects

**Example:**
```c
cortex_transport_t *transport = cortex_transport_shm_create_adapter("bench01");
if (!transport) {
    perror("Failed to connect to SHM transport");
    return -1;
}

/* Adapter can now communicate */
cortex_protocol_recv_frame(transport, ...);
```

**Cleanup:**
When adapter calls `transport->close()`, it:
- Unmaps shared memory (`munmap`)
- Closes semaphores (`sem_close`)
- **Does NOT unlink** (harness owns the resources)

---

### Ring Buffer Design

**Structure:**
```c
typedef struct {
    uint8_t data[RING_BUFFER_SIZE];  /* 256KB circular buffer */
    volatile uint32_t write_pos;      /* Producer writes here */
    volatile uint32_t read_pos;       /* Consumer reads here */
    uint32_t pad[14];                 /* Cache line padding (avoid false sharing) */
} ring_buffer_t;
```

**Operations:**

1. **Write:** Producer advances `write_pos` after copying data
2. **Read:** Consumer advances `read_pos` after consuming data
3. **Available space:** `RING_BUFFER_SIZE - (write_pos - read_pos) - 1`
4. **Available data:** `write_pos - read_pos`

**Lock-free guarantee:** Single producer + single consumer = no locks needed

**Overflow handling:** Sender blocks if buffer full (waits for consumer)

---

### Implementation Details

**recv() Implementation:**
1. Check if data available in ring buffer (fast path)
2. If yes: copy data and return immediately
3. If no: wait on semaphore with timeout (`sem_timedwait_compat`)
4. When signaled: copy data from ring buffer
5. Post to sender's semaphore (signal space available)

**send() Implementation:**
1. Check space available in ring buffer
2. If full: spin-wait (TODO: wait on semaphore)
3. Copy data to ring buffer
4. Advance write pointer
5. Post to receiver's semaphore (signal data ready)

**macOS Compatibility:**
```c
static int sem_timedwait_compat(sem_t *sem, const struct timespec *abs_timeout) {
#ifdef __APPLE__
    /* macOS doesn't support sem_timedwait - use sem_trywait + polling */
    while (1) {
        if (sem_trywait(sem) == 0) return 0;
        if (errno != EAGAIN) return -1;

        struct timespec now;
        clock_gettime(CLOCK_REALTIME, &now);
        if (now >= *abs_timeout) {
            errno = ETIMEDOUT;
            return -1;
        }

        nanosleep(&(struct timespec){0, 1000000}, NULL);  /* Sleep 1ms */
    }
#else
    return sem_timedwait(sem, abs_timeout);
#endif
}
```

---

### Performance

Measured on **MacBook Pro M1 (arm64)**:

| Metric | Value |
|--------|-------|
| P50 Latency | 5µs |
| P95 Latency | 12µs |
| P99 Latency | 15µs |
| Throughput | ~2 GB/s |
| Overhead | Memory copy + semaphore signal |

**Why so fast?**
- No context switch (both processes in userspace)
- No kernel copy (direct memory access)
- Minimal syscalls (only semaphore wait/post)
- Cache-friendly (data stays in L2/L3)

**Bottlenecks:**
- Semaphore wait/post (~2-3µs on macOS)
- Memory copy (`memcpy` for large buffers)
- Cache line bouncing (mitigated by padding)

---

### Platform Notes

#### macOS
- Uses `sem_trywait()` + polling (no `sem_timedwait` support)
- Shared memory size rounded to page boundaries (4KB)
- Named semaphores have length limit (keep names short: <31 chars)
- Semaphore names: `/cortex_sem_*` (must start with `/`)

#### Linux
- Native `sem_timedwait()` support (more efficient)
- Shared memory in `/dev/shm/` (tmpfs)
- Larger semaphore name limits
- Better performance overall

---

### Troubleshooting

**"No such file or directory" (adapter side):**
- Harness hasn't created SHM yet
- Check harness started first
- Verify name matches exactly (case-sensitive)

**"File name too long" (macOS):**
- Semaphore name too long (>31 chars including `/cortex_sem_`)
- Use shorter name parameter (e.g., `"test"` not `"my_very_long_benchmark_name"`)

**recv() times out even though harness sent data:**
- Semaphore signaling issue (rare)
- Check both sides using same name
- Verify no leftover semaphores: `ipcs -s`
- Clean up: `ipcrm -S <key>` or reboot

**High latency:**
- macOS polling overhead (sem_trywait)
- Increase sleep time in compat layer (trade latency for CPU)
- Consider using Linux for production benchmarks

---

## Comparison

| Feature | Mock (Socketpair) | Shared Memory |
|---------|-------------------|---------------|
| **Latency** | ~50µs | ~5µs |
| **Throughput** | 500 MB/s | 2 GB/s |
| **Setup Complexity** | Trivial | Easy |
| **Portability** | Excellent (POSIX) | Good (POSIX, macOS quirks) |
| **Use Case** | Development, testing | Performance benchmarking |
| **Debugging** | Easy (strace works) | Harder (shared state) |
| **Resource Usage** | Low (kernel buffers) | Medium (512KB+ SHM) |

---

## Best Practices

### When to Use Mock

✅ **Use mock when:**
- Developing and testing adapters locally
- Running CI/CD tests
- Debugging protocol issues
- Latency is acceptable (>100µs)

❌ **Don't use mock when:**
- Benchmarking pure kernel performance
- Latency must be <10µs
- Measuring transport overhead

### When to Use Shared Memory

✅ **Use SHM when:**
- Benchmarking kernel performance
- Measuring adapter overhead baseline
- High-throughput scenarios (>100 MB/s)
- Latency-critical measurements (<10µs)

❌ **Don't use SHM when:**
- Just developing/testing (mock is simpler)
- Deploying to production (use network transports)
- Running on systems without POSIX SHM

---

## See Also

- **Transport Selection Guide:** [`../README.md`](../README.md)
- **Example Usage:** `primitives/adapters/v1/native/adapter.c`
- **Protocol Layer:** `../protocol/README.md`
- **Transport API:** `../../include/cortex_transport.h`
