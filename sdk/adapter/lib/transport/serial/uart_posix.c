/*
 * UART POSIX Transport for CORTEX Device Adapters
 *
 * Provides serial port communication using POSIX termios API.
 * Works on Linux, macOS, and other POSIX systems.
 *
 * Use cases:
 * - Development/debugging with USB-to-serial adapters
 * - Raspberry Pi, Jetson Nano serial ports
 * - Testing serial protocol before deploying to embedded targets
 *
 * Features:
 * - Configurable baud rate (115200 default)
 * - 8N1 (8 data bits, no parity, 1 stop bit)
 * - select()-based recv() with timeout
 * - Flow control disabled (for simplicity)
 */

#define _POSIX_C_SOURCE 200809L

#include "cortex_transport.h"

#include <termios.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <stdlib.h>
#include <sys/select.h>
#include <time.h>

/* UART context */
typedef struct {
    int fd;
    char device[256];
    speed_t baud_rate;
} uart_posix_ctx_t;

/*
 * uart_posix_recv - Receive data with timeout
 *
 * Uses select() to implement timeout semantics.
 */
static ssize_t uart_posix_recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms)
{
    uart_posix_ctx_t *uart = (uart_posix_ctx_t *)ctx;

    /* Setup timeout */
    struct timeval tv;
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;

    /* Setup fd_set */
    fd_set readfds;
    FD_ZERO(&readfds);
    FD_SET(uart->fd, &readfds);

    /* Wait for data */
    int select_ret = select(uart->fd + 1, &readfds, NULL, NULL, &tv);

    if (select_ret < 0) {
        return (errno == EINTR) ? CORTEX_ETIMEDOUT : -errno;
    }

    if (select_ret == 0) {
        return CORTEX_ETIMEDOUT;  /* Timeout expired */
    }

    /* Data available - read it */
    ssize_t n = read(uart->fd, buf, len);

    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return CORTEX_ETIMEDOUT;
        }
        return -errno;
    }

    if (n == 0) {
        return CORTEX_ECONNRESET;  /* Device disconnected */
    }

    return n;
}

/*
 * uart_posix_send - Send data (blocking)
 */
static ssize_t uart_posix_send(void *ctx, const void *buf, size_t len)
{
    uart_posix_ctx_t *uart = (uart_posix_ctx_t *)ctx;

    ssize_t n = write(uart->fd, buf, len);

    if (n < 0) {
        return -errno;
    }

    /* Ensure data is transmitted (flush) */
    tcdrain(uart->fd);

    return n;
}

/*
 * uart_posix_close - Close serial port
 */
static void uart_posix_close(void *ctx)
{
    uart_posix_ctx_t *uart = (uart_posix_ctx_t *)ctx;

    if (uart->fd >= 0) {
        close(uart->fd);
        uart->fd = -1;
    }

    free(uart);
}

/*
 * uart_posix_get_timestamp_ns - Platform timestamp
 */
static uint64_t uart_posix_get_timestamp_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/*
 * speed_from_baud - Convert baud rate to termios speed_t
 */
static speed_t speed_from_baud(uint32_t baud)
{
    switch (baud) {
        case 9600:   return B9600;
        case 19200:  return B19200;
        case 38400:  return B38400;
#ifdef B57600
        case 57600:  return B57600;
#endif
#ifdef B115200
        case 115200: return B115200;
#endif
#ifdef B230400
        case 230400: return B230400;
#endif
#ifdef B460800
        case 460800: return B460800;
#endif
#ifdef B921600
        case 921600: return B921600;
#endif
        default:     return B38400;  /* Default fallback */
    }
}

/*
 * cortex_transport_uart_posix_create - Create UART transport
 *
 * Opens serial port with specified configuration.
 *
 * Args:
 *   device:    Serial device path (e.g., "/dev/ttyUSB0", "/dev/cu.usbserial")
 *   baud_rate: Baud rate (9600, 115200, etc.)
 *
 * Returns:
 *   Configured transport, or NULL on failure
 *
 * Configuration:
 *   - 8 data bits
 *   - No parity
 *   - 1 stop bit
 *   - No flow control
 *   - Raw mode (no line processing)
 *
 * Example:
 *   cortex_transport_t *t = cortex_transport_uart_posix_create("/dev/ttyUSB0", 115200);
 */
cortex_transport_t *cortex_transport_uart_posix_create(const char *device, uint32_t baud_rate)
{
    /* Allocate context */
    uart_posix_ctx_t *uart = (uart_posix_ctx_t *)malloc(sizeof(uart_posix_ctx_t));
    if (!uart) {
        return NULL;
    }

    uart->fd = -1;
    uart->baud_rate = speed_from_baud(baud_rate);
    strncpy(uart->device, device, sizeof(uart->device) - 1);
    uart->device[sizeof(uart->device) - 1] = '\0';

    /* Open serial port */
    uart->fd = open(device, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (uart->fd < 0) {
        free(uart);
        return NULL;
    }

    /* Configure serial port */
    struct termios options;
    memset(&options, 0, sizeof(options));

    /* Get current options */
    if (tcgetattr(uart->fd, &options) < 0) {
        close(uart->fd);
        free(uart);
        return NULL;
    }

    /* Set baud rate */
    cfsetispeed(&options, uart->baud_rate);
    cfsetospeed(&options, uart->baud_rate);

    /* 8N1 configuration */
    options.c_cflag &= ~PARENB;  /* No parity */
    options.c_cflag &= ~CSTOPB;  /* 1 stop bit */
    options.c_cflag &= ~CSIZE;
    options.c_cflag |= CS8;      /* 8 data bits */

    /* Disable hardware flow control */
#ifdef CRTSCTS
    options.c_cflag &= ~CRTSCTS;
#elif defined(CNEW_RTSCTS)
    options.c_cflag &= ~CNEW_RTSCTS;
#endif

    /* Enable receiver, ignore modem control lines */
    options.c_cflag |= (CLOCAL | CREAD);

    /* Raw input mode (no line processing) */
    options.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);

    /* Raw output mode */
    options.c_oflag &= ~OPOST;

    /* Disable software flow control */
    options.c_iflag &= ~(IXON | IXOFF | IXANY);

    /* Non-blocking reads (handled by select) */
    options.c_cc[VMIN] = 0;
    options.c_cc[VTIME] = 0;

    /* Apply configuration */
    if (tcsetattr(uart->fd, TCSANOW, &options) < 0) {
        close(uart->fd);
        free(uart);
        return NULL;
    }

    /* Flush any existing data */
    tcflush(uart->fd, TCIOFLUSH);

    /* Set blocking mode (select will handle timeout) */
    int flags = fcntl(uart->fd, F_GETFL, 0);
    fcntl(uart->fd, F_SETFL, flags & ~O_NONBLOCK);

    /* Allocate transport */
    cortex_transport_t *transport = (cortex_transport_t *)malloc(sizeof(cortex_transport_t));
    if (!transport) {
        close(uart->fd);
        free(uart);
        return NULL;
    }

    transport->ctx = uart;
    transport->recv = uart_posix_recv;
    transport->send = uart_posix_send;
    transport->close = uart_posix_close;
    transport->get_timestamp_ns = uart_posix_get_timestamp_ns;

    return transport;
}
