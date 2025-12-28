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
 * Mock Transport (POSIX socketpair-based)
 *
 * Used for loopback adapter (harness ↔ adapter on same machine).
 * Uses poll() for recv() timeouts.
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
 * UART Transport (POSIX)
 *
 * Phase 2 implementation (stub for Phase 1)
 */
cortex_transport_t* cortex_transport_uart_posix_create(const char *device, int baud_rate);

/*
 * TCP Client Transport
 *
 * Phase 2 implementation (stub for Phase 1)
 */
cortex_transport_t* cortex_transport_tcp_client_create(const char *host, uint16_t port);

/*
 * TCP Server Transport
 *
 * Phase 2 implementation (stub for Phase 1)
 */
cortex_transport_t* cortex_transport_tcp_server_create(int listen_fd);

#endif /* CORTEX_TRANSPORT_H */
