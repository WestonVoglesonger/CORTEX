#ifndef CORTEX_TRANSPORT_H
#define CORTEX_TRANSPORT_H

#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

/*
 * CORTEX Device Adapter Transport Layer
 *
 * Provides abstraction for byte-stream communication with device adapters.
 * Implementations: mock (socketpair), UART (POSIX/STM32), TCP (client/server)
 *
 * Key features:
 * - Timeout-based recv() to prevent hangs on adapter death
 * - Platform-specific timestamp functions
 * - Error codes for timeout and connection reset detection
 */

/* Transport error codes (negative values, distinct from errno) */
#define CORTEX_ETIMEDOUT   -1000  /* Operation timed out */
#define CORTEX_ECONNRESET  -1001  /* Connection reset (EOF/adapter died) */

/*
 * Transport API
 *
 * All transports implement this interface. Context (ctx) holds transport-specific
 * state (e.g., file descriptors, socket handles, UART handles).
 *
 * Memory ownership:
 * - Caller owns transport struct (must call close() before free)
 * - Transport owns ctx (freed in close())
 */
typedef struct cortex_transport_api {
    void *ctx;  /* Transport-specific context */

    /*
     * Send data (blocking)
     *
     * Returns:
     *   >0: Number of bytes sent
     *   <0: Error (negative errno or CORTEX_E* code)
     */
    ssize_t (*send)(void *ctx, const void *buf, size_t len);

    /*
     * Receive data (blocking with timeout)
     *
     * Args:
     *   timeout_ms: Timeout in milliseconds (0 = non-blocking, >0 = timeout)
     *
     * Returns:
     *   >0: Number of bytes received
     *    0: EOF (connection closed)
     *   CORTEX_ETIMEDOUT: Timeout occurred (no data available)
     *   CORTEX_ECONNRESET: Connection reset
     *   <0 (other): Error (negative errno)
     *
     * IMPORTANT: May return partial data (< len). Caller must handle.
     */
    ssize_t (*recv)(void *ctx, void *buf, size_t len, uint32_t timeout_ms);

    /*
     * Close transport and free resources
     *
     * After close(), transport struct is invalid (caller must free).
     */
    void (*close)(void *ctx);

    /*
     * Get nanosecond timestamp (platform-specific)
     *
     * POSIX: CLOCK_MONOTONIC
     * STM32: DWT cycle counter
     *
     * Returns: Nanoseconds since arbitrary epoch (monotonic, no wraparound)
     */
    uint64_t (*get_timestamp_ns)(void);
} cortex_transport_api_t;

/* Convenience typedef */
typedef cortex_transport_api_t cortex_transport_t;

/*
 * Transport Configuration URI
 *
 * Parsed adapter configuration URI for selecting transport type.
 *
 * Supported formats:
 *   local://                                    → Local spawn (socketpair)
 *   tcp://host:port                             → TCP client (connect to host)
 *   tcp://host:port?timeout_ms=500              → TCP client with custom timeout
 *   tcp://:port                                 → TCP server (listen on INADDR_ANY)
 *   tcp://:port?accept_timeout_ms=5000          → TCP server with custom timeout
 *   serial:///dev/ttyUSB0?baud=115200           → UART/serial port
 *   shm://bench01                               → Shared memory IPC
 */
typedef struct {
    char scheme[16];        /* "local", "tcp", "serial", "shm" */

    /* TCP fields */
    char host[256];         /* "10.0.1.42" or "" (empty = server/listen mode) */
    uint16_t port;          /* 9000 (0 = not applicable) */
    uint32_t timeout_ms;    /* Query param timeout (0 = use default) */

    /* UART/Serial fields */
    char device_path[256];  /* "/dev/ttyUSB0", "/dev/cu.usbserial-*" */
    uint32_t baud_rate;     /* 115200, 921600, etc. (0 = use default 115200) */

    /* Shared Memory fields */
    char shm_name[64];      /* "bench01", "test", etc. */
} cortex_uri_t;

/**
 * Parse adapter configuration URI
 *
 * @param uri Input URI string (NULL or empty defaults to "local://")
 * @param out Parsed URI structure
 * @return 0 on success, -1 on error
 */
int cortex_parse_adapter_uri(const char *uri, cortex_uri_t *out);

/**
 * Destroy transport and free all resources
 *
 * OWNERSHIP CONTRACT:
 *   - transport->close(ctx) MUST free ctx
 *   - This function only frees the transport struct itself
 *
 * Safe to call with NULL.
 *
 * @param transport Transport to destroy (may be NULL)
 */
void cortex_transport_destroy(cortex_transport_t *transport);

/*
 * ============================================================================
 * Production Transports (URI-accessible, fully integrated)
 * ============================================================================
 */

/*
 * Mock Transport (POSIX socketpair-based)
 *
 * Used for loopback adapter (harness ↔ adapter on same machine).
 * Uses poll() for recv() timeouts.
 *
 * URI: local://
 * Status: ✅ Production-ready
 * Use: Development, testing, CI/CD
 */

/*
 * Create mock transport from bidirectional FD (e.g., socketpair)
 *
 * Args:
 *   fd: Bidirectional file descriptor (read and write)
 *
 * Returns: Transport or NULL on allocation failure
 *
 * Ownership: Caller must call close() then free() when done
 */
cortex_transport_t* cortex_transport_mock_create(int fd);

/*
 * Create mock transport from separate read/write FDs
 *
 * Args:
 *   read_fd: FD for reading (e.g., stdin)
 *   write_fd: FD for writing (e.g., stdout)
 *
 * Returns: Transport or NULL on allocation failure
 *
 * Use case: Adapter reads from stdin, writes to stdout
 *
 * Ownership: Caller must call close() then free() when done
 */
cortex_transport_t* cortex_transport_mock_create_from_fds(int read_fd, int write_fd);

/*
 * ============================================================================
 * Development/Debugging Transports (implemented but not URI-accessible)
 * ============================================================================
 */

/*
 * UART Transport (POSIX)
 *
 * Opens serial port with specified baud rate.
 *
 * URI: Not yet implemented (manual create only)
 * Status: ⚠️ Implemented but not wired to URI factory
 * Use: Debug console, initial hardware bring-up, low-bandwidth telemetry
 * Bandwidth: ~11 KB/s @ 115200 baud (insufficient for typical BCI data rates)
 * Note: For production BCI on STM32, use TCP over Ethernet instead
 *
 * Args:
 *   device:    Serial device path (e.g., "/dev/ttyUSB0", "/dev/cu.usbserial")
 *   baud_rate: Baud rate (9600, 115200, etc.)
 *
 * Returns: Transport or NULL on failure
 */
cortex_transport_t* cortex_transport_uart_posix_create(const char *device, uint32_t baud_rate);

/*
 * TCP Client Transport
 *
 * Connects to remote host:port with timeout.
 *
 * URI: tcp://192.168.1.100:9000
 * Status: ✅ Production-ready
 * Use: Harness connecting to remote adapter (STM32, Raspberry Pi, etc.)
 *
 * Args:
 *   host:        Hostname or IP address (e.g., "192.168.1.100", "localhost")
 *   port:        TCP port
 *   timeout_ms:  Connection timeout in milliseconds
 *
 * Returns: Transport or NULL on failure
 */
cortex_transport_t* cortex_transport_tcp_client_create(const char *host, uint16_t port, uint32_t timeout_ms);

/*
 * TCP Server Transport
 *
 * Creates listening socket on specified port (INADDR_ANY).
 *
 * URI: tcp://:9000
 * Status: ✅ Production-ready
 * Use: Adapter listening for harness connection (STM32 with Ethernet, etc.)
 *
 * Two-phase setup:
 *   1. Create listening socket: cortex_transport_tcp_server_create(port)
 *   2. Accept connection: cortex_transport_tcp_server_accept(server, timeout_ms)
 *
 * Args:
 *   port: TCP port to listen on (e.g., 9000)
 *
 * Returns: Server transport (listening socket) or NULL on failure
 */
cortex_transport_t* cortex_transport_tcp_server_create(uint16_t port);

/**
 * Accept client connection with timeout
 *
 * Blocks waiting for connection. Uses poll() for timeout.
 *
 * Args:
 *   server:      Server transport from cortex_transport_tcp_server_create()
 *   timeout_ms:  Accept timeout in milliseconds
 *
 * Returns: Connected client transport or NULL on timeout/error
 */
cortex_transport_t* cortex_transport_tcp_server_accept(
    cortex_transport_t *server,
    uint32_t timeout_ms
);

/*
 * Shared Memory Transport (POSIX)
 *
 * High-performance local IPC using POSIX shared memory and semaphores.
 * ~10x faster than socketpair, ~100x faster than TCP.
 *
 * URI: Not yet implemented (manual create only)
 * Status: ⚠️ Implemented but not wired to URI factory
 * Use: Performance benchmarking, overhead measurement, latency baseline
 * Bandwidth: ~2 GB/s
 * Latency: ~5µs (vs 50µs for socketpair, 1ms for TCP)
 * Note: Local-only (same machine), use for benchmarking pure kernel performance
 *
 * Two-phase setup:
 *   1. Harness creates shared memory region (calls create_harness)
 *   2. Adapter connects to existing region (calls create_adapter)
 *
 * Args:
 *   name: Unique name for this transport (e.g., "cortex_adapter_0")
 *
 * Returns: Transport or NULL on failure
 */
cortex_transport_t* cortex_transport_shm_create_harness(const char *name);
cortex_transport_t* cortex_transport_shm_create_adapter(const char *name);

#endif /* CORTEX_TRANSPORT_H */
