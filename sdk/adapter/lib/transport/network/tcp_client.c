/*
 * TCP Client Transport for CORTEX Device Adapters
 *
 * Provides TCP socket-based communication for network-connected devices
 * (e.g., Jetson Nano, Raspberry Pi, remote x86 hosts).
 *
 * Features:
 * - Non-blocking connect with timeout
 * - poll()-based recv() with timeout support
 * - Graceful connection teardown
 * - Platform-independent timestamp
 */

#ifdef __APPLE__
#define _DARWIN_C_SOURCE  /* Enable SO_NOSIGPIPE on macOS */
#endif
#define _POSIX_C_SOURCE 200809L

#include "cortex_transport.h"

#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <errno.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>

/* TCP client context */
typedef struct {
    int sockfd;
    char host[256];
    uint16_t port;
} tcp_client_ctx_t;

/*
 * tcp_client_recv - Receive data with timeout
 *
 * Uses poll() to implement timeout semantics on blocking socket.
 */
static ssize_t tcp_client_recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms)
{
    tcp_client_ctx_t *tcp = (tcp_client_ctx_t *)ctx;

    struct pollfd pfd = {
        .fd = tcp->sockfd,
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
    ssize_t n = recv(tcp->sockfd, buf, len, 0);

    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return CORTEX_ETIMEDOUT;
        }
        return -errno;
    }

    if (n == 0) {
        return CORTEX_ECONNRESET;  /* Connection closed */
    }

    return (ssize_t)n;
}

/*
 * tcp_client_send - Send data (blocking)
 */
static ssize_t tcp_client_send(void *ctx, const void *buf, size_t len)
{
    tcp_client_ctx_t *tcp = (tcp_client_ctx_t *)ctx;

    /* Use MSG_NOSIGNAL on Linux to prevent SIGPIPE (macOS uses SO_NOSIGPIPE socket option) */
#ifdef __linux__
    ssize_t n = send(tcp->sockfd, buf, len, MSG_NOSIGNAL);
#else
    ssize_t n = send(tcp->sockfd, buf, len, 0);
#endif

    if (n < 0) {
        return (errno == EPIPE || errno == ECONNRESET) ? CORTEX_ECONNRESET : -errno;
    }

    return (ssize_t)n;
}

/*
 * tcp_client_close - Close connection and cleanup
 */
static void tcp_client_close(void *ctx)
{
    tcp_client_ctx_t *tcp = (tcp_client_ctx_t *)ctx;

    if (tcp->sockfd >= 0) {
        shutdown(tcp->sockfd, SHUT_RDWR);
        close(tcp->sockfd);
        tcp->sockfd = -1;
    }

    free(tcp);
}

/*
 * tcp_client_get_timestamp_ns - Platform timestamp
 */
static uint64_t tcp_client_get_timestamp_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/*
 * cortex_transport_tcp_client_create - Create TCP client transport
 *
 * Connects to remote host:port and returns configured transport.
 *
 * Args:
 *   host:        Hostname or IP address (e.g., "192.168.1.100", "localhost")
 *   port:        TCP port (e.g., 8080)
 *   timeout_ms:  Connection timeout in milliseconds
 *
 * Returns:
 *   Configured transport, or NULL on failure
 *
 * Example:
 *   cortex_transport_t *t = cortex_transport_tcp_client_create("192.168.1.100", 8080, 5000);
 */
cortex_transport_t *cortex_transport_tcp_client_create(
    const char *host,
    uint16_t port,
    uint32_t timeout_ms
)
{
    /* Allocate context */
    tcp_client_ctx_t *tcp = (tcp_client_ctx_t *)malloc(sizeof(tcp_client_ctx_t));
    if (!tcp) {
        return NULL;
    }

    tcp->sockfd = -1;
    tcp->port = port;
    strncpy(tcp->host, host, sizeof(tcp->host) - 1);
    tcp->host[sizeof(tcp->host) - 1] = '\0';

    /* Create socket */
    tcp->sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (tcp->sockfd < 0) {
        free(tcp);
        return NULL;
    }

    /* Configure socket for low latency and reliability */
    int flag = 1;

    /* TCP_NODELAY: Disable Nagle's algorithm for low latency */
    setsockopt(tcp->sockfd, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(flag));

    /* SO_KEEPALIVE: Keep connection alive for long runs */
    setsockopt(tcp->sockfd, SOL_SOCKET, SO_KEEPALIVE, &flag, sizeof(flag));

#ifdef __APPLE__
    /* SO_NOSIGPIPE: Don't send SIGPIPE on broken connection (macOS) */
    setsockopt(tcp->sockfd, SOL_SOCKET, SO_NOSIGPIPE, &flag, sizeof(flag));
#endif

    /* Set socket to non-blocking for timeout connect */
    int flags = fcntl(tcp->sockfd, F_GETFL, 0);
    fcntl(tcp->sockfd, F_SETFL, flags | O_NONBLOCK);

    /* Setup server address */
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);

    if (inet_pton(AF_INET, host, &addr.sin_addr) <= 0) {
        close(tcp->sockfd);
        free(tcp);
        return NULL;
    }

    /* Non-blocking connect */
    int ret = connect(tcp->sockfd, (struct sockaddr *)&addr, sizeof(addr));

    if (ret < 0 && errno != EINPROGRESS) {
        close(tcp->sockfd);
        free(tcp);
        return NULL;
    }

    /* Wait for connection with timeout */
    if (errno == EINPROGRESS) {
        struct pollfd pfd = {
            .fd = tcp->sockfd,
            .events = POLLOUT,
            .revents = 0
        };

        int poll_ret = poll(&pfd, 1, (int)timeout_ms);

        if (poll_ret <= 0) {
            close(tcp->sockfd);
            free(tcp);
            return NULL;  /* Timeout or error */
        }

        /* Check if connection succeeded */
        int err;
        socklen_t len = sizeof(err);
        getsockopt(tcp->sockfd, SOL_SOCKET, SO_ERROR, &err, &len);

        if (err != 0) {
            close(tcp->sockfd);
            free(tcp);
            return NULL;  /* Connection failed */
        }
    }

    /* Set socket back to blocking mode */
    fcntl(tcp->sockfd, F_SETFL, flags);

    /* Allocate transport */
    cortex_transport_t *transport = (cortex_transport_t *)malloc(sizeof(cortex_transport_t));
    if (!transport) {
        close(tcp->sockfd);
        free(tcp);
        return NULL;
    }

    transport->ctx = tcp;
    transport->recv = tcp_client_recv;
    transport->send = tcp_client_send;
    transport->close = tcp_client_close;
    transport->get_timestamp_ns = tcp_client_get_timestamp_ns;

    return transport;
}
