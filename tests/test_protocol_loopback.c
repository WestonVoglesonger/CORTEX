/*
 * Protocol Loopback Test - Send and receive HELLO via socketpair
 *
 * This test verifies the protocol layer works correctly over socketpair.
 * Unlike test_socketpair_hello.c, this doesn't consume bytes before recv_frame().
 */

#define _POSIX_C_SOURCE 200809L

#include "../sdk/adapter/include/cortex_protocol.h"
#include "../sdk/adapter/include/cortex_transport.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/wait.h>

int main(void)
{
    printf("=== Protocol Loopback Test ===\n\n");

    int sv[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) < 0) {
        perror("socketpair");
        return 1;
    }

    pid_t pid = fork();
    if (pid < 0) {
        perror("fork");
        return 1;
    }

    if (pid == 0) {
        /* Child: Send HELLO */
        close(sv[0]);

        cortex_transport_t *transport = cortex_transport_mock_create(sv[1]);
        if (!transport) {
            fprintf(stderr, "Child: Failed to create transport\n");
            _exit(1);
        }

        /* Build minimal HELLO payload */
        uint8_t payload[sizeof(cortex_wire_hello_t) + 32];
        memset(payload, 0, sizeof(payload));

        cortex_write_u32_le(payload + 0, 12345);  /* boot_id */
        snprintf((char *)(payload + 4), 32, "test-adapter");
        payload[36] = 1;  /* abi_version */
        payload[37] = 1;  /* num_kernels */
        cortex_write_u16_le(payload + 38, 0);  /* reserved */
        cortex_write_u32_le(payload + 40, 1024);  /* max_window_samples */
        cortex_write_u32_le(payload + 44, 64);    /* max_channels */

        snprintf((char *)(payload + sizeof(cortex_wire_hello_t)), 32, "noop@f32");

        printf("Child: Sending HELLO frame...\n");
        int ret = cortex_protocol_send_frame(transport, CORTEX_FRAME_HELLO, payload, sizeof(payload));
        if (ret < 0) {
            fprintf(stderr, "Child: send_frame failed: %d\n", ret);
            _exit(1);
        }

        printf("Child: HELLO sent, waiting for parent to finish...\n");

        /* Wait for parent to read */
        char dummy;
        read(sv[1], &dummy, 1);

        _exit(0);
    }

    /* Parent: Receive HELLO */
    close(sv[1]);

    cortex_transport_t *transport = cortex_transport_mock_create(sv[0]);
    if (!transport) {
        fprintf(stderr, "Parent: Failed to create transport\n");
        close(sv[0]);
        return 1;
    }

    uint8_t frame_buf[8192];
    cortex_frame_type_t frame_type;
    size_t payload_len;

    printf("Parent: Calling recv_frame...\n");
    int ret = cortex_protocol_recv_frame(
        transport,
        &frame_type,
        frame_buf,
        sizeof(frame_buf),
        &payload_len,
        5000
    );

    if (ret < 0) {
        printf("ERROR: recv_frame failed: %d\n", ret);
        if (ret == CORTEX_ETIMEDOUT) {
            printf("  (Timeout)\n");
        } else if (ret == CORTEX_EPROTO_MAGIC_NOT_FOUND) {
            printf("  (MAGIC not found)\n");
        } else if (ret == CORTEX_EPROTO_CRC_MISMATCH) {
            printf("  (CRC mismatch)\n");
        } else if (ret == CORTEX_ECONNRESET) {
            printf("  (Connection reset)\n");
        }
        transport->close(transport->ctx);
        free(transport);
        waitpid(pid, NULL, 0);
        return 1;
    }

    if (frame_type != CORTEX_FRAME_HELLO) {
        printf("ERROR: Wrong frame type: %d (expected %d)\n", frame_type, CORTEX_FRAME_HELLO);
        transport->close(transport->ctx);
        free(transport);
        waitpid(pid, NULL, 0);
        return 1;
    }

    printf("✓ HELLO received successfully!\n");
    printf("  Frame type: CORTEX_FRAME_HELLO (%d)\n", frame_type);
    printf("  Payload length: %zu bytes\n", payload_len);

    /* Parse HELLO */
    uint32_t boot_id = cortex_read_u32_le(frame_buf + 0);
    char adapter_name[33];
    memcpy(adapter_name, frame_buf + 4, 32);
    adapter_name[32] = '\0';

    printf("  Boot ID: %u\n", boot_id);
    printf("  Adapter name: %s\n", adapter_name);

    transport->close(transport->ctx);
    free(transport);
    waitpid(pid, NULL, 0);

    printf("\n=== Test PASSED ===\n");
    return 0;
}
