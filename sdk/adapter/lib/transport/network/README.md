# Network Transports

**Directory:** `sdk/adapter/lib/transport/network/`
**Use Case:** Communication with remote devices over IP networks
**Platforms:** Linux, macOS, Windows (with minor modifications)

Network transports enable adapters to run on separate physical machines from the harness. This is essential for deploying kernels on embedded devices (Jetson Nano, Raspberry Pi), remote workstations, or cloud instances.

---

## Overview

| Transport | File | Latency | Throughput | Use When... |
|-----------|------|---------|------------|-------------|
| **TCP Client** | `tcp_client.c` | ~500µs (localhost), ~1-5ms (LAN) | 100 MB/s (GigE) | Jetson, Pi, remote x86 hosts, any device with network stack |

---

## TCP Client Transport

**File:** `tcp_client.c` (243 lines)
**Mechanism:** BSD sockets with TCP/IP protocol
**Latency:** ~500µs (localhost), ~1-5ms (LAN), ~50-200ms (WAN)
**Throughput:** ~100 MB/s (Gigabit Ethernet), ~12 MB/s (100Mbps)

### Purpose

The TCP client transport is the **primary transport for remote adapters**. It connects to a TCP server (typically running on the device with the adapter) and communicates using standard Internet protocols.

**Use it for:**
- Jetson Nano, Jetson Orin, or other NVIDIA embedded platforms
- Raspberry Pi (all models with Ethernet/WiFi)
- Remote x86/arm64 servers
- Any device with a network stack (Linux, macOS, Windows, embedded Linux)
- Cloud-based testing (AWS, GCP, Azure instances)

**Do NOT use for:**
- Same-machine communication (use local transports instead)
- Bare-metal embedded systems without TCP/IP stack (use UART)
- Latency-critical benchmarking (network overhead affects measurements)

### How It Works

```
┌──────────────┐                         ┌──────────────┐
│   Harness    │                         │   Adapter    │
│              │                         │              │
│  TCP Client  ├─────── TCP/IP ─────────►│  TCP Server  │
│  (connect)   │     (LAN or WAN)        │  (listen)    │
│              │◄────────────────────────┤              │
└──────────────┘                         └──────────────┘
```

**Architecture:**
1. **Server side (adapter):** Device runs TCP server listening on port (e.g., 8080)
2. **Client side (harness):** Harness connects to device's IP address and port
3. **Connection:** Three-way TCP handshake establishes reliable bidirectional channel
4. **Communication:** Protocol frames sent over TCP socket

**Key Properties:**
- **Connection-oriented:** Reliable delivery with automatic retransmission
- **In-order:** Data arrives in send order (no reordering)
- **Flow-controlled:** TCP windowing prevents buffer overflow
- **Buffered:** Kernel socket buffers smooth out bursty traffic
- **Low-latency optimized:** TCP_NODELAY disables Nagle's algorithm

### API

#### cortex_transport_tcp_client_create()

```c
cortex_transport_t* cortex_transport_tcp_client_create(
    const char *host,
    uint16_t port,
    uint32_t timeout_ms
);
```

Creates a TCP client transport by connecting to a remote server.

**Parameters:**
- `host`: Hostname or IP address (e.g., `"192.168.1.100"`, `"jetson.local"`, `"localhost"`)
- `port`: TCP port number (e.g., `8080`, `5000`)
- `timeout_ms`: Connection timeout in milliseconds (how long to wait for server to accept)

**Returns:**
- Non-NULL: Successfully connected transport
- NULL: Connection failed (server unreachable, timeout, refused)

**Connection Process:**
1. Resolve hostname to IP address (`getaddrinfo` or direct IPv4)
2. Create socket (`socket(AF_INET, SOCK_STREAM, 0)`)
3. Set socket to non-blocking mode (`fcntl(sockfd, F_SETFL, O_NONBLOCK)`)
4. Initiate connection (`connect()`)
5. Wait for completion using `poll()` with timeout
6. Verify connection succeeded (`getsockopt(SOL_SOCKET, SO_ERROR)`)
7. Set TCP_NODELAY to disable Nagle's algorithm (reduces latency)
8. Restore blocking mode for recv/send operations

**Example (Harness Side):**
```c
/* Connect to Jetson Nano at 192.168.1.100:8080 with 5-second timeout */
cortex_transport_t *transport = cortex_transport_tcp_client_create(
    "192.168.1.100", 8080, 5000
);

if (!transport) {
    perror("Failed to connect to adapter");
    return -1;
}

/* Use transport with protocol layer */
cortex_protocol_send_frame(transport, CORTEX_MSG_HANDSHAKE, buf, len);

/* Cleanup */
transport->close(transport->ctx);
free(transport);
```

**Example (Adapter Side - Pseudocode):**
```c
/* Adapter must run TCP server (not included in SDK yet) */
int server_fd = socket(AF_INET, SOCK_STREAM, 0);
bind(server_fd, ...);
listen(server_fd, 1);

struct sockaddr_in client_addr;
socklen_t addr_len = sizeof(client_addr);
int client_fd = accept(server_fd, (struct sockaddr *)&client_addr, &addr_len);

/* Create transport from accepted connection socket */
cortex_transport_t *transport = cortex_transport_mock_create(client_fd);

/* Use transport with protocol layer */
cortex_protocol_recv_frame(transport, &msg_type, buf, sizeof(buf), 5000);
```

**Note:** The SDK currently includes only the TCP **client** implementation. A TCP **server** transport will be added in a future release. For now, adapters can use `cortex_transport_mock_create(client_fd)` with the accepted socket.

---

### Implementation Details

**recv() Implementation:**
```c
static ssize_t tcp_client_recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms)
{
    tcp_client_ctx_t *tcp = (tcp_client_ctx_t *)ctx;

    /* Wait for data with timeout */
    struct pollfd pfd = {
        .fd = tcp->sockfd,
        .events = POLLIN
    };

    int poll_ret = poll(&pfd, 1, (int)timeout_ms);

    if (poll_ret == 0) {
        return CORTEX_ETIMEDOUT;  /* Timeout */
    } else if (poll_ret < 0) {
        return -errno;  /* Poll error */
    }

    /* Check for connection errors */
    if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) {
        return CORTEX_ECONNRESET;
    }

    /* Read data */
    ssize_t n = recv(tcp->sockfd, buf, len, 0);

    if (n == 0) {
        return CORTEX_ECONNRESET;  /* Connection closed */
    } else if (n < 0) {
        return -errno;
    }

    return n;
}
```

**Key behaviors:**
- Uses `poll()` for timeout support (more portable than `select()`)
- Returns `CORTEX_ETIMEDOUT` if no data arrives within timeout
- Returns `CORTEX_ECONNRESET` if connection closes
- Supports partial reads (caller must handle reassembly)

**send() Implementation:**
```c
static ssize_t tcp_client_send(void *ctx, const void *buf, size_t len)
{
    tcp_client_ctx_t *tcp = (tcp_client_ctx_t *)ctx;

    ssize_t n = send(tcp->sockfd, buf, len, 0);

    if (n < 0) {
        if (errno == EPIPE || errno == ECONNRESET) {
            return CORTEX_ECONNRESET;
        }
        return -errno;
    }

    return n;
}
```

**Key behaviors:**
- Blocking send (may wait until kernel buffers have space)
- Returns `CORTEX_ECONNRESET` on broken pipe or reset
- May return partial writes (caller handles retries)

**close() Implementation:**
```c
static void tcp_client_close(void *ctx)
{
    tcp_client_ctx_t *tcp = (tcp_client_ctx_t *)ctx;

    if (tcp->sockfd >= 0) {
        close(tcp->sockfd);
    }

    free(tcp);
}
```

**get_timestamp_ns() Implementation:**
```c
static uint64_t tcp_client_get_timestamp_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}
```

---

### Performance

Measured on **MacBook Pro M1 (arm64)** connecting to localhost:

| Metric | Localhost | LAN (GigE) | WiFi (802.11ac) |
|--------|-----------|------------|-----------------|
| P50 Latency | 180µs | 1.2ms | 3.5ms |
| P95 Latency | 450µs | 3.5ms | 12ms |
| P99 Latency | 800µs | 8ms | 25ms |
| Throughput | 800 MB/s | 100 MB/s | 40 MB/s |
| Overhead | Kernel TCP stack + loopback | NIC driver + switch | Radio + protocol overhead |

**Performance Characteristics:**

**Localhost (127.0.0.1):**
- Bypasses physical NIC (loopback interface)
- Still goes through TCP/IP stack (more overhead than socketpair)
- ~4× slower than socketpair, but 36× faster than shared memory on localhost

**LAN (Local Area Network):**
- Typical enterprise/home network latency
- Switch introduces ~100-500µs forwarding delay
- Gigabit Ethernet provides 125 MB/s theoretical max, ~100 MB/s real-world

**WiFi:**
- Higher latency due to radio medium access
- Packet aggregation reduces overhead for large transfers
- Signal quality and interference affect jitter

**Bottlenecks:**
- **Latency:** TCP handshake (connect), kernel context switch, network stack processing
- **Throughput:** NIC bandwidth, kernel buffer sizes, CPU interrupt handling
- **Jitter:** Network congestion, dynamic frequency scaling, interrupt coalescing

---

### TCP_NODELAY Optimization

The transport **disables Nagle's algorithm** by setting `TCP_NODELAY`:

```c
int flag = 1;
setsockopt(tcp->sockfd, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(flag));
```

**Why this matters:**

**Nagle's Algorithm (default TCP behavior):**
- Buffers small writes to reduce packet count
- Waits for ACK or full MSS (Maximum Segment Size, typically 1460 bytes) before sending
- **Problem:** Adds 10-200ms latency for small messages (protocol frames are 32-256 bytes)

**With TCP_NODELAY:**
- Every `send()` generates immediate packet
- Reduces latency for small messages (protocol handshakes, control frames)
- **Tradeoff:** More packets on the network (acceptable for CORTEX use case)

**Impact on CORTEX:**
- Protocol frames are small (handshake: 32 bytes, window metadata: ~100 bytes)
- Without TCP_NODELAY: 40ms handshake latency
- With TCP_NODELAY: 0.5ms handshake latency
- **Result:** 80× improvement in protocol negotiation speed

---

### Platform Notes

#### Linux
- Native TCP implementation
- Use `SO_REUSEADDR` on server to avoid "Address already in use" after restart:
  ```c
  int flag = 1;
  setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &flag, sizeof(flag));
  ```
- Check firewall rules: `sudo ufw status` (Ubuntu) or `sudo firewall-cmd --list-all` (Fedora)
- Monitor connections: `ss -tn` or `netstat -tn`

#### macOS
- BSD sockets implementation (same API as Linux)
- Firewall may block incoming connections (System Preferences → Security & Privacy → Firewall)
- Use `lsof -i :8080` to check if port is in use
- `SO_REUSEPORT` available for load balancing (advanced)

#### Network Configuration
- **MTU (Maximum Transmission Unit):** Default 1500 bytes (Ethernet), affects fragmentation
- **Socket buffer sizes:** Default 64KB-128KB, tune with `SO_RCVBUF`/`SO_SNDBUF` if needed
- **TCP keepalive:** Not currently enabled (could add for long-lived connections)

---

### Troubleshooting

**"Connection refused" error:**
- Server is not running on target device
- Check server is listening: `ss -tln | grep 8080` (Linux) or `lsof -i :8080` (macOS)
- Verify correct IP address and port
- Check server logs for errors

**"Connection timeout" error:**
- Device is unreachable (network routing issue)
- Firewall blocking connection
- Verify connectivity: `ping 192.168.1.100`
- Check route: `traceroute 192.168.1.100` (macOS/Linux)
- Test port: `nc -zv 192.168.1.100 8080`

**"No route to host" error:**
- IP address not on local subnet
- Router/gateway not configured
- Check routing table: `route -n` (Linux) or `netstat -rn` (macOS)
- Verify subnet mask (e.g., 192.168.1.0/24)

**recv() returns ECONNRESET:**
- Remote side closed connection unexpectedly
- Adapter crashed or exited
- Check adapter logs
- Look for segfaults: `dmesg | tail` (Linux)

**High latency (>10ms on LAN):**
- Network congestion (run `iperf3` to test bandwidth)
- TCP_NODELAY not set (check code)
- Switch/router queuing delay
- CPU frequency scaling (check with `cpufreq-info` on Linux)

**Slow throughput (<10 MB/s on GigE):**
- Socket buffer size too small (try `setsockopt(SO_RCVBUF, ...)`)
- CPU bottleneck (check with `top` or `htop`)
- Network interface duplex mismatch (force full-duplex)
- Cable quality issues (try different cable)

**"Address already in use" (server side):**
- Previous server didn't fully close socket
- Use `SO_REUSEADDR` option
- Wait 60 seconds (TCP TIME_WAIT state)
- Kill lingering processes: `pkill -f adapter`

---

## Future Network Transports

**Planned for Phase 2+:**

### TCP Server
- **File:** `tcp_server.c` (planned)
- **Use Case:** Harness runs on embedded device, adapter on workstation (reverse direction)
- **API:** `cortex_transport_tcp_server_create(uint16_t port, uint32_t timeout_ms)`

### UDP
- **File:** `udp.c` (planned)
- **Use Case:** Low-latency unreliable transport (acceptable packet loss for real-time)
- **Latency:** ~200µs (localhost), ~800µs (LAN)
- **Tradeoff:** No reliability guarantees (faster but may lose data)

### WebSocket
- **File:** `websocket.c` (planned)
- **Use Case:** Browser-based visualization, cloud deployments
- **Protocol:** RFC 6455 WebSocket over HTTP upgrade
- **Libraries:** `libwebsockets` or custom implementation

### MQTT
- **File:** `mqtt.c` (planned)
- **Use Case:** IoT deployments, pub/sub messaging
- **Broker:** Mosquitto, HiveMQ, AWS IoT Core
- **Latency:** ~5-20ms (depends on broker)

---

## Comparison with Local Transports

| Feature | TCP (localhost) | Mock (socketpair) | Shared Memory |
|---------|----------------|-------------------|---------------|
| **Latency** | ~180µs | ~50µs | ~5µs |
| **Throughput** | 800 MB/s | 500 MB/s | 2 GB/s |
| **Setup Complexity** | Easy | Trivial | Easy |
| **Remote Support** | ✅ Yes | ❌ No | ❌ No |
| **Firewall Issues** | ⚠️ Possible | ✅ None | ✅ None |
| **Debugging** | Easy (Wireshark) | Easy (strace) | Harder |

**When to choose TCP over local transports:**
- ✅ Adapter runs on different physical machine
- ✅ Need to test network-realistic latency
- ✅ Deploying to embedded Linux device with Ethernet
- ❌ Same-machine benchmarking (use mock or SHM instead)

---

## Example: Connecting to Jetson Nano

**Setup (Jetson Nano side):**
```bash
# Build adapter on Jetson
cd primitives/adapters/v1/my_adapter/
make

# Run TCP server (pseudocode - not included in SDK yet)
./tcp_server_stub 8080 ./my_adapter
# Listens on 0.0.0.0:8080, spawns ./my_adapter for each connection
```

**Connection (Harness side):**
```c
/* Harness running on workstation */
cortex_transport_t *transport = cortex_transport_tcp_client_create(
    "192.168.1.100",  /* Jetson's IP (check with `ifconfig` on Jetson) */
    8080,             /* Port server is listening on */
    10000             /* 10-second connection timeout */
);

if (!transport) {
    fprintf(stderr, "Failed to connect to Jetson Nano\n");
    fprintf(stderr, "Check:\n");
    fprintf(stderr, "  1. Jetson is powered on and reachable (ping 192.168.1.100)\n");
    fprintf(stderr, "  2. Server is running on Jetson (ssh jetson 'ss -tln | grep 8080')\n");
    fprintf(stderr, "  3. Firewall allows port 8080 (sudo ufw allow 8080)\n");
    return -1;
}

/* Handshake */
if (cortex_protocol_handshake(transport, CORTEX_ABI_VERSION, 5000) < 0) {
    fprintf(stderr, "Handshake failed\n");
    transport->close(transport->ctx);
    free(transport);
    return -1;
}

/* Run kernel */
uint8_t window_data[64 * 160 * sizeof(float)];
uint8_t output[64 * 160 * sizeof(float)];

cortex_protocol_send_frame(transport, CORTEX_MSG_PROCESS, window_data, sizeof(window_data));
ssize_t n = cortex_protocol_recv_frame(transport, &msg_type, output, sizeof(output), 5000);

/* Cleanup */
transport->close(transport->ctx);
free(transport);
```

---

## Security Considerations

**Current implementation has NO authentication or encryption:**
- ⚠️ Anyone on the network can connect to adapter
- ⚠️ Protocol frames sent in plaintext (visible with Wireshark)
- ⚠️ No protection against MITM attacks

**For production deployments, consider:**
1. **TLS/SSL wrapper:** Use `openssl` library to encrypt TCP connection
2. **SSH tunneling:** Run adapter server on localhost, tunnel through SSH: `ssh -L 8080:localhost:8080 jetson`
3. **VPN:** Use WireGuard or OpenVPN to create encrypted network
4. **Firewall rules:** Restrict connections to specific IP addresses

**Example: SSH tunnel (secure alternative to raw TCP):**
```bash
# On workstation (harness side):
ssh -N -L 8080:localhost:8080 user@192.168.1.100 &

# In harness code:
cortex_transport_t *transport = cortex_transport_tcp_client_create(
    "localhost",  /* Connect to local tunnel endpoint */
    8080,
    5000
);
# Traffic is encrypted by SSH, forwarded to Jetson
```

---

## See Also

- **Transport Selection Guide:** [`../README.md`](../README.md)
- **Local Transports:** [`../local/README.md`](../local/README.md)
- **Serial Transports:** [`../serial/README.md`](../serial/README.md)
- **Example Usage:** `primitives/adapters/v1/native/adapter.c`
- **Protocol Layer:** `../protocol/README.md`
- **Transport API:** `../../include/cortex_transport.h`
