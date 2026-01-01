/*
 * TCP Server Transport for CORTEX Device Adapters
 *
 * Provides TCP socket-based server for adapter-side listening.
 * Used when adapter runs on remote device (e.g., Jetson) and harness connects to it.
 *
 * Features:
 * - Listen on specified port (INADDR_ANY)
 * - Accept with timeout using poll()
 * - TCP_NODELAY for low latency
 * - SO_KEEPALIVE for long-running connections
 * - Graceful teardown
 */

#define _POSIX_C_SOURCE 200809L

#include "cortex_transport.h"
#include "cortex_wire.h"

#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <unistd.h>
#include <poll.h>
#include <errno.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include <stdio.h>

/* TCP server context (listening socket) */
typedef struct {
    int listen_fd;
    uint16_t port;
} tcp_server_ctx_t;

/* TCP connected client context (same as tcp_client after accept) */
typedef struct {
    int client_fd;
} tcp_connected_ctx_t;

/*
 * tcp_server_recv - Receive data with timeout (same as tcp_client)
 */
static ssize_t tcp_server_recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms)
{
    tcp_connected_ctx_t *conn = (tcp_connected_ctx_t *)ctx;

    struct pollfd pfd = {
        .fd = conn->client_fd,
        .events = POLLIN,
        .revents = 0
    };

    int poll_ret = poll(&pfd, 1, (int)timeout_ms);

    if (poll_ret < 0) {
        return (errno == EINTR) ? CORTEX_ETIMEDOUT : -errno;
    }

    if (poll_ret == 0) {
        return CORTEX_ETIMEDOUT;
    }

    if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) {
        return CORTEX_ECONNRESET;
    }

    ssize_t n = recv(conn->client_fd, buf, len, 0);

    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return CORTEX_ETIMEDOUT;
        }
        return -errno;
    }

    if (n == 0) {
        return CORTEX_ECONNRESET;
    }

    return n;
}

/*
 * tcp_server_send - Send data (blocking, same as tcp_client)
 */
static ssize_t tcp_server_send(void *ctx, const void *buf, size_t len)
{
    tcp_connected_ctx_t *conn = (tcp_connected_ctx_t *)ctx;

    /* Use MSG_NOSIGNAL on Linux to prevent SIGPIPE (macOS uses SO_NOSIGPIPE socket option) */
#ifdef __linux__
    ssize_t n = send(conn->client_fd, buf, len, MSG_NOSIGNAL);
#else
    ssize_t n = send(conn->client_fd, buf, len, 0);
#endif

    if (n < 0) {
        return (errno == EPIPE || errno == ECONNRESET) ? CORTEX_ECONNRESET : -errno;
    }

    return n;
}

/*
 * tcp_server_close - Close connection and cleanup
 */
static void tcp_server_close(void *ctx)
{
    tcp_server_ctx_t *srv = (tcp_server_ctx_t *)ctx;

    if (srv->listen_fd >= 0) {
        close(srv->listen_fd);
        srv->listen_fd = -1;
    }

    free(srv);
}

/*
 * tcp_connected_close - Close connected client and cleanup
 */
static void tcp_connected_close(void *ctx)
{
    tcp_connected_ctx_t *conn = (tcp_connected_ctx_t *)ctx;

    if (conn->client_fd >= 0) {
        shutdown(conn->client_fd, SHUT_RDWR);
        close(conn->client_fd);
        conn->client_fd = -1;
    }

    free(conn);
}

/*
 * tcp_server_get_timestamp_ns - Platform timestamp
 */
static uint64_t tcp_server_get_timestamp_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/*
 * cortex_transport_tcp_server_create - Create TCP server (listening socket)
 *
 * Creates listening socket on specified port (INADDR_ANY).
 * Does NOT accept connections - call cortex_transport_tcp_server_accept() for that.
 *
 * Args:
 *   port: TCP port to listen on (e.g., 9000)
 *
 * Returns:
 *   Server transport (listening socket), or NULL on failure
 *
 * Example:
 *   cortex_transport_t *server = cortex_transport_tcp_server_create(9000);
 *   cortex_transport_t *client = cortex_transport_tcp_server_accept(server, 30000);
 *   cortex_transport_destroy(server);  // Close listening socket
 */
cortex_transport_t *cortex_transport_tcp_server_create(uint16_t port)
{
    /* Allocate server context */
    tcp_server_ctx_t *srv = (tcp_server_ctx_t *)malloc(sizeof(tcp_server_ctx_t));
    if (!srv) {
        return NULL;
    }

    srv->listen_fd = -1;
    srv->port = port;

    /* Create socket */
    srv->listen_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (srv->listen_fd < 0) {
        free(srv);
        return NULL;
    }

    /* SO_REUSEADDR: Allow quick restart (avoid TIME_WAIT) */
    int opt = 1;
    setsockopt(srv->listen_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    /* Bind to INADDR_ANY:port */
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;  /* Listen on all interfaces */
    addr.sin_port = htons(port);

    if (bind(srv->listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(srv->listen_fd);
        free(srv);
        return NULL;
    }

    /* Listen with backlog=1 (only one pending connection) */
    if (listen(srv->listen_fd, 1) < 0) {
        close(srv->listen_fd);
        free(srv);
        return NULL;
    }

    /* Allocate transport (NOTE: send/recv not valid until accept) */
    cortex_transport_t *transport = (cortex_transport_t *)malloc(sizeof(cortex_transport_t));
    if (!transport) {
        close(srv->listen_fd);
        free(srv);
        return NULL;
    }

    transport->ctx = srv;
    transport->recv = NULL;  /* Not valid until accept */
    transport->send = NULL;
    transport->close = tcp_server_close;
    transport->get_timestamp_ns = tcp_server_get_timestamp_ns;

    return transport;
}

/*
 * cortex_transport_tcp_server_accept - Accept connection with timeout
 *
 * Blocks waiting for client connection. Uses poll() to implement timeout.
 *
 * Args:
 *   server:      Server transport (from cortex_transport_tcp_server_create)
 *   timeout_ms:  Accept timeout in milliseconds
 *
 * Returns:
 *   Connected client transport, or NULL on timeout/error
 *
 * Example:
 *   cortex_transport_t *server = cortex_transport_tcp_server_create(9000);
 *   cortex_transport_t *client = cortex_transport_tcp_server_accept(server, 30000);
 *   if (!client) {
 *       fprintf(stderr, "Accept timeout\n");
 *   }
 *   cortex_transport_destroy(server);  // Close listening socket
 */
cortex_transport_t *cortex_transport_tcp_server_accept(
    cortex_transport_t *server,
    uint32_t timeout_ms
)
{
    if (!server || !server->ctx) {
        return NULL;
    }

    tcp_server_ctx_t *srv = (tcp_server_ctx_t *)server->ctx;

    /* Poll for incoming connection with timeout */
    struct pollfd pfd = {
        .fd = srv->listen_fd,
        .events = POLLIN,
        .revents = 0
    };

    int poll_ret = poll(&pfd, 1, (int)timeout_ms);

    if (poll_ret < 0) {
        return NULL;  /* poll error */
    }

    if (poll_ret == 0) {
        errno = ETIMEDOUT;
        return NULL;  /* Timeout */
    }

    /* Accept connection */
    int client_fd = accept(srv->listen_fd, NULL, NULL);
    if (client_fd < 0) {
        return NULL;
    }

    /* Configure socket for low latency */
    int opt = 1;

    /* TCP_NODELAY: Disable Nagle's algorithm */
    setsockopt(client_fd, IPPROTO_TCP, TCP_NODELAY, &opt, sizeof(opt));

    /* SO_KEEPALIVE: Keep connection alive for long runs */
    setsockopt(client_fd, SOL_SOCKET, SO_KEEPALIVE, &opt, sizeof(opt));

    /* Allocate connected client context */
    tcp_connected_ctx_t *conn = (tcp_connected_ctx_t *)malloc(sizeof(tcp_connected_ctx_t));
    if (!conn) {
        close(client_fd);
        return NULL;
    }

    conn->client_fd = client_fd;

    /* Allocate transport */
    cortex_transport_t *transport = (cortex_transport_t *)malloc(sizeof(cortex_transport_t));
    if (!transport) {
        close(client_fd);
        free(conn);
        return NULL;
    }

    transport->ctx = conn;
    transport->recv = tcp_server_recv;
    transport->send = tcp_server_send;
    transport->close = tcp_connected_close;
    transport->get_timestamp_ns = tcp_server_get_timestamp_ns;

    return transport;
}
