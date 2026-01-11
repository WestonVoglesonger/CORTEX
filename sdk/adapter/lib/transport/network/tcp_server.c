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
 * - SO_NOSIGPIPE (macOS) for SIGPIPE protection
 * - Graceful teardown
 */

#ifdef __APPLE__
#define _DARWIN_C_SOURCE  /* Enable SO_NOSIGPIPE on macOS */
#endif
#define _POSIX_C_SOURCE 200809L

#include "cortex_transport.h"
#include "cortex_wire.h"
#include "tcp_common.h"

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
 * tcp_server_recv - Receive data with timeout (uses shared helper)
 */
static ssize_t tcp_server_recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms)
{
    tcp_connected_ctx_t *conn = (tcp_connected_ctx_t *)ctx;
    return cortex_tcp_recv(conn->client_fd, buf, len, timeout_ms);
}

/*
 * tcp_server_send - Send data (blocking, uses shared helper)
 */
static ssize_t tcp_server_send(void *ctx, const void *buf, size_t len)
{
    tcp_connected_ctx_t *conn = (tcp_connected_ctx_t *)ctx;
    return cortex_tcp_send(conn->client_fd, buf, len);
}

/*
 * tcp_server_close - Close listening socket and cleanup
 */
static void tcp_server_close(void *ctx)
{
    tcp_server_ctx_t *srv = (tcp_server_ctx_t *)ctx;
    if (srv->listen_fd >= 0) {
        close(srv->listen_fd);
    }
    free(srv);
}

/*
 * tcp_connected_close - Close connected client and cleanup (uses shared helper)
 */
static void tcp_connected_close(void *ctx)
{
    tcp_connected_ctx_t *conn = (tcp_connected_ctx_t *)ctx;
    cortex_tcp_close(conn->client_fd);
    free(conn);
}

/*
 * tcp_server_get_timestamp_ns - Platform timestamp (uses shared helper)
 */
static uint64_t tcp_server_get_timestamp_ns(void)
{
    return cortex_tcp_get_timestamp_ns();
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

#ifdef __APPLE__
    /* SO_NOSIGPIPE: Don't send SIGPIPE on broken connection (macOS) */
    setsockopt(client_fd, SOL_SOCKET, SO_NOSIGPIPE, &opt, sizeof(opt));
#endif

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
