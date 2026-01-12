/*
 * TCP Common Helpers - Shared recv/send/timestamp logic
 *
 * Eliminates code duplication between tcp_client.c and tcp_server.c
 * by extracting shared poll()-based recv and platform-specific send.
 */

#define _POSIX_C_SOURCE 200809L

#include "tcp_common.h"
#include "cortex_transport.h"

#include <sys/socket.h>
#include <poll.h>
#include <errno.h>
#include <time.h>
#include <unistd.h>

/*
 * cortex_tcp_recv - Receive data with timeout (shared implementation)
 *
 * Uses poll() to implement timeout semantics on blocking socket.
 *
 * Args:
 *   sockfd:      Socket file descriptor
 *   buf:         Destination buffer
 *   len:         Maximum bytes to receive
 *   timeout_ms:  Timeout in milliseconds
 *
 * Returns:
 *   >0: Number of bytes received
 *    0: Connection closed
 *   <0: Error code (CORTEX_ETIMEDOUT, CORTEX_ECONNRESET, etc.)
 */
ssize_t cortex_tcp_recv(int sockfd, void *buf, size_t len, uint32_t timeout_ms)
{
    struct pollfd pfd = {
        .fd = sockfd,
        .events = POLLIN,
        .revents = 0
    };

    /* Wait for data with timeout */
    int poll_ret = poll(&pfd, 1, (int)timeout_ms);

    if (poll_ret < 0) {
        return (errno == EINTR) ? CORTEX_ETIMEDOUT : -errno;
    }

    if (poll_ret == 0) {
        return CORTEX_ETIMEDOUT;  /* Timeout expired */
    }

    /* Data available or connection closed */
    if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) {
        return CORTEX_ECONNRESET;
    }

    /* Read data */
    ssize_t n = recv(sockfd, buf, len, 0);

    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return CORTEX_ETIMEDOUT;
        }
        return -errno;
    }

    if (n == 0) {
        return CORTEX_ECONNRESET;  /* Connection closed */
    }

    return n;
}

/*
 * cortex_tcp_send - Send data (blocking, shared implementation)
 *
 * Handles platform-specific SIGPIPE protection:
 * - Linux: MSG_NOSIGNAL flag
 * - macOS: SO_NOSIGPIPE socket option (set by caller)
 *
 * Args:
 *   sockfd:  Socket file descriptor
 *   buf:     Data to send
 *   len:     Number of bytes to send
 *
 * Returns:
 *   >=0: Number of bytes sent
 *   <0: Error code (CORTEX_ECONNRESET on broken pipe, -errno otherwise)
 */
ssize_t cortex_tcp_send(int sockfd, const void *buf, size_t len)
{
    /* Use MSG_NOSIGNAL on Linux to prevent SIGPIPE (macOS uses SO_NOSIGPIPE socket option) */
#ifdef __linux__
    ssize_t n = send(sockfd, buf, len, MSG_NOSIGNAL);
#else
    ssize_t n = send(sockfd, buf, len, 0);
#endif

    if (n < 0) {
        return (errno == EPIPE || errno == ECONNRESET) ? CORTEX_ECONNRESET : -errno;
    }

    return n;
}

/*
 * cortex_tcp_close - Close socket with graceful shutdown
 *
 * Args:
 *   sockfd: Socket file descriptor to close
 */
void cortex_tcp_close(int sockfd)
{
    if (sockfd >= 0) {
        shutdown(sockfd, SHUT_RDWR);
        close(sockfd);
    }
}

/*
 * cortex_tcp_get_timestamp_ns - Platform-independent monotonic timestamp
 *
 * Returns:
 *   Nanosecond timestamp (CLOCK_MONOTONIC)
 */
uint64_t cortex_tcp_get_timestamp_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}
