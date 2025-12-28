#define _POSIX_C_SOURCE 200809L

#include "cortex_transport.h"

#include <errno.h>
#include <poll.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/*
 * Mock Transport Context
 *
 * Wraps file descriptors for byte-stream I/O. Used with socketpair for
 * loopback adapter communication (harness ↔ adapter on same machine).
 */
typedef struct {
    int read_fd;   /* FD for reading (recv) */
    int write_fd;  /* FD for writing (send) */
} mock_transport_ctx_t;

/* Forward declarations */
static ssize_t mock_send(void *ctx, const void *buf, size_t len);
static ssize_t mock_recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms);
static void mock_close(void *ctx);
static uint64_t mock_timestamp_ns(void);

/*
 * mock_send - Write data to write_fd
 *
 * Returns:
 *   >0: Bytes written
 *   <0: Negative errno
 */
static ssize_t mock_send(void *ctx, const void *buf, size_t len)
{
    mock_transport_ctx_t *mock = (mock_transport_ctx_t *)ctx;

    ssize_t n = write(mock->write_fd, buf, len);
    if (n < 0) {
        return -errno;  /* Return negative errno */
    }

    return n;
}

/*
 * mock_recv - Read data from read_fd with timeout
 *
 * Uses poll() to implement timeout. Returns CORTEX_ETIMEDOUT if no data
 * arrives within timeout_ms milliseconds.
 *
 * Returns:
 *   >0: Bytes read
 *    0: EOF (connection closed)
 *   CORTEX_ETIMEDOUT: Timeout (no data available)
 *   CORTEX_ECONNRESET: EOF detected
 *   <0: Negative errno
 */
static ssize_t mock_recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms)
{
    mock_transport_ctx_t *mock = (mock_transport_ctx_t *)ctx;

    /* Use poll() for timeout */
    struct pollfd pfd;
    pfd.fd = mock->read_fd;
    pfd.events = POLLIN;
    pfd.revents = 0;

    int ready = poll(&pfd, 1, (int)timeout_ms);

    if (ready == 0) {
        /* Timeout */
        return CORTEX_ETIMEDOUT;
    }

    if (ready < 0) {
        /* poll() error */
        return -errno;
    }

    /* Data ready or EOF */
    ssize_t n = read(mock->read_fd, buf, len);

    if (n == 0) {
        /* EOF - connection closed (adapter died) */
        return CORTEX_ECONNRESET;
    }

    if (n < 0) {
        /* read() error */
        return -errno;
    }

    return n;
}

/*
 * mock_close - Close file descriptors and free context
 *
 * IMPORTANT: Only closes FDs that are not stdin/stdout/stderr (0, 1, 2).
 * Adapter processes use stdin/stdout, which should not be closed here.
 */
static void mock_close(void *ctx)
{
    mock_transport_ctx_t *mock = (mock_transport_ctx_t *)ctx;

    /* Close read_fd if not stdin/stdout/stderr */
    if (mock->read_fd > 2) {
        close(mock->read_fd);
    }

    /* Close write_fd if not stdin/stdout/stderr and different from read_fd */
    if (mock->write_fd > 2 && mock->write_fd != mock->read_fd) {
        close(mock->write_fd);
    }

    free(mock);
}

/*
 * mock_timestamp_ns - Get nanosecond timestamp using CLOCK_MONOTONIC
 *
 * Returns nanoseconds since arbitrary epoch (monotonic, no wraparound).
 */
static uint64_t mock_timestamp_ns(void)
{
    struct timespec ts;

    if (clock_gettime(CLOCK_MONOTONIC, &ts) < 0) {
        /* Should never fail, but return 0 if it does */
        return 0;
    }

    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/*
 * cortex_transport_mock_create - Create from bidirectional FD
 *
 * Use case: socketpair(2) creates bidirectional socket pair.
 * Harness uses one end (fd), adapter uses the other.
 */
cortex_transport_t* cortex_transport_mock_create(int fd)
{
    return cortex_transport_mock_create_from_fds(fd, fd);
}

/*
 * cortex_transport_mock_create_from_fds - Create from separate read/write FDs
 *
 * Use case: Adapter reads from stdin (0), writes to stdout (1).
 */
cortex_transport_t* cortex_transport_mock_create_from_fds(int read_fd, int write_fd)
{
    /* Allocate context */
    mock_transport_ctx_t *mock = (mock_transport_ctx_t *)calloc(1, sizeof(*mock));
    if (!mock) {
        return NULL;
    }

    mock->read_fd = read_fd;
    mock->write_fd = write_fd;

    /* Allocate transport API struct */
    cortex_transport_t *transport = (cortex_transport_t *)calloc(1, sizeof(*transport));
    if (!transport) {
        free(mock);
        return NULL;
    }

    /* Wire up function pointers */
    transport->ctx = mock;
    transport->send = mock_send;
    transport->recv = mock_recv;
    transport->close = mock_close;
    transport->get_timestamp_ns = mock_timestamp_ns;

    return transport;
}

/*
 * Stub implementations for future transports (Phase 2/3)
 */

cortex_transport_t* cortex_transport_uart_posix_create(const char *device, int baud_rate)
{
    (void)device;
    (void)baud_rate;
    errno = ENOSYS;  /* Not implemented */
    return NULL;
}

cortex_transport_t* cortex_transport_tcp_client_create(const char *host, uint16_t port)
{
    (void)host;
    (void)port;
    errno = ENOSYS;  /* Not implemented */
    return NULL;
}

cortex_transport_t* cortex_transport_tcp_server_create(int listen_fd)
{
    (void)listen_fd;
    errno = ENOSYS;  /* Not implemented */
    return NULL;
}
