/*
 * CORTEX Transport Helpers
 *
 * Complete transport layer utilities:
 * - URI parsing (local://, tcp://host:port, query params)
 * - Adapter-side transport creation factory
 * - Transport lifecycle management (destroy)
 */

#include "cortex_transport.h"
#include "cortex_wire.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* ========================================================================
 * URI Parsing
 * ======================================================================== */

int cortex_parse_adapter_uri(const char *uri, cortex_uri_t *out) {
    if (!out) {
        return -1;
    }

    /* Default to local if NULL or empty */
    if (!uri || uri[0] == '\0') {
        memcpy(out->scheme, "local", 5);
        out->scheme[5] = '\0';
        out->host[0] = '\0';
        out->port = 0;
        out->timeout_ms = 0;
        return 0;
    }

    /* Find scheme:// separator */
    const char *scheme_end = strstr(uri, "://");
    if (!scheme_end) {
        fprintf(stderr, "URI missing scheme:// separator: %s\n", uri);
        return -1;
    }

    /* Extract scheme */
    size_t scheme_len = scheme_end - uri;
    if (scheme_len >= sizeof(out->scheme)) {
        fprintf(stderr, "Scheme too long: %s\n", uri);
        return -1;
    }

    memcpy(out->scheme, uri, scheme_len);
    out->scheme[scheme_len] = '\0';

    const char *rest = scheme_end + 3;  /* Skip "://" */

    /* Handle local:// */
    if (strcmp(out->scheme, "local") == 0) {
        out->host[0] = '\0';
        out->port = 0;
        out->timeout_ms = 0;
        out->device_path[0] = '\0';
        out->baud_rate = 0;
        out->shm_name[0] = '\0';
        return 0;
    }

    /* Handle serial:// */
    if (strcmp(out->scheme, "serial") == 0) {
        /* Split at '?' for query params */
        const char *query = strchr(rest, '?');
        size_t path_len = query ? (size_t)(query - rest) : strlen(rest);

        if (path_len >= sizeof(out->device_path)) {
            fprintf(stderr, "Device path too long: %s\n", uri);
            return -1;
        }

        memcpy(out->device_path, rest, path_len);
        out->device_path[path_len] = '\0';

        /* Parse baud rate from query param (default: 115200) */
        out->baud_rate = 115200;
        if (query) {
            const char *baud_param = strstr(query, "baud=");
            if (baud_param) {
                char *endptr;
                unsigned long baud = strtoul(baud_param + 5, &endptr, 10);
                /* Validate: must have parsed something, stopped at valid delimiter, and in range */
                if (endptr == baud_param + 5 || (*endptr != '\0' && *endptr != '&')) {
                    fprintf(stderr, "Invalid baud rate format in URI\n");
                    return -1;
                }
                if (baud == 0 || baud > 921600) {
                    fprintf(stderr, "Invalid baud rate: %lu (must be 1-921600)\n", baud);
                    return -1;
                }
                out->baud_rate = (uint32_t)baud;
            }
        }

        /* Clear unused fields */
        out->host[0] = '\0';
        out->port = 0;
        out->timeout_ms = 0;
        out->shm_name[0] = '\0';
        return 0;
    }

    /* Handle tcp:// */
    if (strcmp(out->scheme, "tcp") == 0) {
        /* Split at '?' for query params */
        const char *query = strchr(rest, '?');
        size_t hostport_len = query ? (size_t)(query - rest) : strlen(rest);

        char hostport[512];
        if (hostport_len >= sizeof(hostport)) {
            fprintf(stderr, "Host:port too long: %s\n", uri);
            return -1;
        }

        memcpy(hostport, rest, hostport_len);
        hostport[hostport_len] = '\0';

        /* Find colon separator for port */
        const char *colon = strchr(hostport, ':');
        if (!colon) {
            fprintf(stderr, "TCP URI missing port: %s\n", uri);
            return -1;
        }

        /* Extract host (may be empty for server mode) */
        size_t host_len = colon - hostport;
        if (host_len >= sizeof(out->host)) {
            fprintf(stderr, "Hostname too long: %s\n", uri);
            return -1;
        }

        memcpy(out->host, hostport, host_len);
        out->host[host_len] = '\0';

        /* Parse port */
        int port = atoi(colon + 1);
        if (port <= 0 || port > 65535) {
            fprintf(stderr, "Invalid port number: %s\n", colon + 1);
            return -1;
        }
        out->port = (uint16_t)port;

        /* Parse query params */
        out->timeout_ms = 0;
        if (query) {
            /* Look for timeout_ms= or accept_timeout_ms= */
            const char *timeout_param = strstr(query, "timeout_ms=");
            if (!timeout_param) {
                timeout_param = strstr(query, "accept_timeout_ms=");
            }

            if (timeout_param) {
                const char *value_start = strchr(timeout_param, '=');
                if (value_start) {
                    int timeout = atoi(value_start + 1);
                    if (timeout > 0) {
                        out->timeout_ms = (uint32_t)timeout;
                    }
                }
            }
        }

        /* Clear unused fields */
        out->device_path[0] = '\0';
        out->baud_rate = 0;
        out->shm_name[0] = '\0';
        return 0;
    }

    /* Handle shm:// */
    if (strcmp(out->scheme, "shm") == 0) {
        /* Extract SHM name (everything after "://") */
        size_t name_len = strlen(rest);

        if (name_len == 0) {
            fprintf(stderr, "SHM URI missing name: %s\n", uri);
            return -1;
        }

        if (name_len >= sizeof(out->shm_name)) {
            fprintf(stderr, "SHM name too long: %s (max %zu chars)\n",
                    rest, sizeof(out->shm_name) - 1);
            return -1;
        }

        strncpy(out->shm_name, rest, sizeof(out->shm_name) - 1);
        out->shm_name[sizeof(out->shm_name) - 1] = '\0';

        /* Clear unused fields */
        out->host[0] = '\0';
        out->port = 0;
        out->timeout_ms = 0;
        out->device_path[0] = '\0';
        out->baud_rate = 0;
        return 0;
    }

    /* Unknown scheme */
    fprintf(stderr, "Unsupported URI scheme: %s\n", out->scheme);
    fprintf(stderr, "  Supported: local://, tcp://host:port, serial:///dev/device, shm://name\n");
    return -1;
}

/* ========================================================================
 * Transport Lifecycle
 * ======================================================================== */

void cortex_transport_destroy(cortex_transport_t *transport) {
    if (!transport) {
        return;
    }

    /*
     * OWNERSHIP CONTRACT:
     * - transport->close(ctx) MUST free ctx (verified: all implementations do this)
     * - This function only frees the transport struct itself
     */
    if (transport->close) {
        transport->close(transport->ctx);
    }

    /* Free the transport struct (ctx was already freed by close()) */
    free(transport);
}

/* ========================================================================
 * Adapter-Side Transport Creation
 * ======================================================================== */

cortex_transport_t *cortex_adapter_transport_create(const char *config_uri) {
    cortex_uri_t uri;

    /* Parse URI (defaults to "local://" if NULL/empty) */
    if (cortex_parse_adapter_uri(config_uri, &uri) != 0) {
        fprintf(stderr, "Adapter: Failed to parse URI: %s\n",
                config_uri ? config_uri : "(null)");
        return NULL;
    }

    if (strcmp(uri.scheme, "local") == 0) {
        /*
         * LOCAL: stdin/stdout (harness already connected via socketpair)
         *
         * The harness sets up a socketpair, spawns the adapter with stdin/stdout
         * redirected to the socketpair ends. From adapter perspective, it just
         * reads from stdin and writes to stdout.
         */
        return cortex_transport_mock_create_from_fds(STDIN_FILENO, STDOUT_FILENO);

    } else if (strcmp(uri.scheme, "tcp") == 0) {
        /*
         * TCP: Adapter MUST be server (listen + accept)
         *
         * STRICT VALIDATION: Adapter TCP URIs must have empty host (server form).
         * Reject client form (tcp://host:port) with clear error.
         */
        if (uri.host[0] != '\0') {
            fprintf(stderr,
                    "Adapter: TCP config must be server mode (tcp://:port), got: %s\n"
                    "  Adapters listen for connections, harness connects to them.\n"
                    "  Use tcp://:9000 (not tcp://host:9000)\n",
                    config_uri);
            return NULL;
        }

        if (uri.port == 0) {
            fprintf(stderr, "Adapter: TCP server requires port (e.g., tcp://:9000)\n");
            return NULL;
        }

        /* Create TCP server (listening socket) */
        cortex_transport_t *server = cortex_transport_tcp_server_create(uri.port);
        if (!server) {
            fprintf(stderr, "Adapter: Failed to create TCP server on port %u\n", uri.port);
            return NULL;
        }

        /* Use custom timeout if specified, else default */
        uint32_t timeout_ms = uri.timeout_ms ? uri.timeout_ms : CORTEX_ACCEPT_TIMEOUT_MS;

        fprintf(stderr, "Adapter: Listening on TCP port %u (%u ms timeout)...\n",
                uri.port, timeout_ms);

        /* Accept ONE connection (blocking with timeout) */
        cortex_transport_t *client = cortex_transport_tcp_server_accept(server, timeout_ms);

        /* Close listening socket (no longer needed) */
        cortex_transport_destroy(server);

        if (!client) {
            fprintf(stderr, "Adapter: Failed to accept TCP connection (timeout or error)\n");
            return NULL;
        }

        fprintf(stderr, "Adapter: TCP connection established\n");
        return client;

    } else if (strcmp(uri.scheme, "serial") == 0) {
        /*
         * SERIAL/UART: Direct hardware connection
         *
         * Opens serial port with specified baud rate.
         * Use case: Debug console, initial hardware bring-up, low-bandwidth telemetry.
         *
         * Note: UART bandwidth (11-88 KB/s) is typically insufficient for BCI data rates.
         *       For production STM32 deployments, use tcp:// over Ethernet instead.
         */
        if (uri.device_path[0] == '\0') {
            fprintf(stderr, "Adapter: Serial URI missing device path (e.g., serial:///dev/ttyUSB0)\n");
            return NULL;
        }

        fprintf(stderr, "Adapter: Opening serial port %s @ %u baud...\n",
                uri.device_path, uri.baud_rate);

        cortex_transport_t *transport = cortex_transport_uart_posix_create(
            uri.device_path,
            uri.baud_rate
        );

        if (!transport) {
            fprintf(stderr, "Adapter: Failed to open serial port %s\n", uri.device_path);
            return NULL;
        }

        fprintf(stderr, "Adapter: Serial connection established\n");
        return transport;

    } else if (strcmp(uri.scheme, "shm") == 0) {
        /*
         * SHARED MEMORY: High-performance local IPC
         *
         * Use case: Performance benchmarking, overhead measurement, latency baseline.
         * Provides ~10x speedup over socketpair, ~100x over TCP.
         *
         * Note: Local-only (same machine). For benchmarking pure kernel performance.
         */
        if (uri.shm_name[0] == '\0') {
            fprintf(stderr, "Adapter: SHM URI missing name (e.g., shm://bench01)\n");
            return NULL;
        }

        fprintf(stderr, "Adapter: Connecting to shared memory region '%s'...\n", uri.shm_name);

        cortex_transport_t *transport = cortex_transport_shm_create_adapter(uri.shm_name);

        if (!transport) {
            fprintf(stderr, "Adapter: Failed to connect to SHM region '%s'\n", uri.shm_name);
            return NULL;
        }

        fprintf(stderr, "Adapter: SHM connection established\n");
        return transport;

    } else {
        fprintf(stderr, "Adapter: Unsupported transport scheme: %s\n", uri.scheme);
        fprintf(stderr, "  Supported: local://, tcp://:port, serial:///dev/device, shm://name\n");
        return NULL;
    }
}

