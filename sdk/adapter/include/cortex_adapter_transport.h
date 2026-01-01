#ifndef CORTEX_ADAPTER_TRANSPORT_H
#define CORTEX_ADAPTER_TRANSPORT_H

#include "cortex_transport.h"

/**
 * Create adapter-side transport from URI configuration
 *
 * ADAPTER-SIDE BEHAVIOR (different from harness):
 *   local://           → stdin/stdout (pre-connected by harness via socketpair)
 *   tcp://:port        → TCP SERVER (listen on port, accept connection)
 *   tcp://:port?accept_timeout_ms=N → TCP server with custom timeout
 *
 * VALIDATION:
 *   - Adapter TCP URIs MUST be server form (empty host, e.g., tcp://:9000)
 *   - Adapter TCP URIs with host (e.g., tcp://host:port) are REJECTED
 *   - This enforces adapter=server, harness=client pattern
 *
 * @param config_uri URI string (NULL or empty defaults to "local://")
 * @return Transport handle or NULL on error
 *
 * Examples:
 *   cortex_adapter_transport_create("local://")               → stdin/stdout
 *   cortex_adapter_transport_create("tcp://:9000")            → Listen on port 9000
 *   cortex_adapter_transport_create("tcp://:9000?accept_timeout_ms=5000") → 5s timeout
 *   cortex_adapter_transport_create("tcp://10.0.1.42:9000")   → ERROR (client form)
 */
cortex_transport_t *cortex_adapter_transport_create(const char *config_uri);

#endif /* CORTEX_ADAPTER_TRANSPORT_H */
