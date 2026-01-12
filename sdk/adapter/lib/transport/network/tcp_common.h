/*
 * TCP Common Helpers - Shared recv/send/timestamp declarations
 *
 * Shared between tcp_client.c and tcp_server.c to eliminate code duplication.
 */

#ifndef TCP_COMMON_H
#define TCP_COMMON_H

#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

/*
 * cortex_tcp_recv - Receive data with timeout
 *
 * Shared implementation for both client and server transports.
 * Uses poll() for timeout semantics.
 *
 * Args:
 *   sockfd:      Socket file descriptor
 *   buf:         Destination buffer
 *   len:         Maximum bytes to receive
 *   timeout_ms:  Timeout in milliseconds
 *
 * Returns:
 *   >0: Number of bytes received
 *   <0: Error (CORTEX_ETIMEDOUT, CORTEX_ECONNRESET, -errno)
 */
ssize_t cortex_tcp_recv(int sockfd, void *buf, size_t len, uint32_t timeout_ms);

/*
 * cortex_tcp_send - Send data (blocking)
 *
 * Shared implementation for both client and server transports.
 * Handles platform-specific SIGPIPE protection.
 *
 * Args:
 *   sockfd:  Socket file descriptor
 *   buf:     Data to send
 *   len:     Number of bytes to send
 *
 * Returns:
 *   >=0: Number of bytes sent
 *   <0: Error (CORTEX_ECONNRESET, -errno)
 */
ssize_t cortex_tcp_send(int sockfd, const void *buf, size_t len);

/*
 * cortex_tcp_close - Close socket with graceful shutdown
 *
 * Args:
 *   sockfd: Socket file descriptor to close
 */
void cortex_tcp_close(int sockfd);

/*
 * cortex_tcp_get_timestamp_ns - Platform-independent monotonic timestamp
 *
 * Returns:
 *   Nanosecond timestamp (CLOCK_MONOTONIC)
 */
uint64_t cortex_tcp_get_timestamp_ns(void);

#endif /* TCP_COMMON_H */
