/*
 * Unit tests for RESULT frame chunking protocol.
 *
 * Tests send/recv of large RESULT frames via 8KB chunking mechanism.
 * Critical for high-channel-count scenarios (512ch+) where RESULT frames
 * exceed single-frame limits.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <unistd.h>
#include <sys/socket.h>

#include "cortex_protocol.h"
#include "cortex_transport.h"
#include "cortex_wire.h"

/* Test helper: Create a mock socketpair transport */
static int create_mock_transport_pair(cortex_transport_t **client, cortex_transport_t **server) {
    int sv[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) < 0) {
        return -1;
    }

    /* Increase socket buffer sizes to handle large RESULT frames (>640KB)
     * without blocking. Default socket buffers (~16KB on macOS) cause deadlock
     * in single-threaded send→recv tests. */
    int buf_size = 1024 * 1024;  /* 1MB */
    setsockopt(sv[0], SOL_SOCKET, SO_SNDBUF, &buf_size, sizeof(buf_size));
    setsockopt(sv[0], SOL_SOCKET, SO_RCVBUF, &buf_size, sizeof(buf_size));
    setsockopt(sv[1], SOL_SOCKET, SO_SNDBUF, &buf_size, sizeof(buf_size));
    setsockopt(sv[1], SOL_SOCKET, SO_RCVBUF, &buf_size, sizeof(buf_size));

    *client = cortex_transport_mock_create(sv[0]);
    *server = cortex_transport_mock_create(sv[1]);

    if (!*client || !*server) {
        close(sv[0]);
        close(sv[1]);
        return -1;
    }

    return 0;
}

/* Test helper: Generate test data */
static void fill_test_data(float *data, size_t num_samples, uint32_t seed) {
    for (size_t i = 0; i < num_samples; i++) {
        data[i] = (float)(seed + i);
    }
}

/* Test 1: Small RESULT (fits in single chunk) */
static void test_result_single_chunk(void) {
    printf("TEST: Single chunk RESULT (<8KB)...\n");

    cortex_transport_t *client, *server;
    assert(create_mock_transport_pair(&client, &server) == 0);

    /* Small result: 64ch × 160 samples = 10,240 samples = 40KB */
    uint32_t channels = 64;
    uint32_t length = 160;
    uint32_t total_samples = channels * length;

    float *send_data = (float *)malloc(total_samples * sizeof(float));
    float *recv_data = (float *)malloc(total_samples * sizeof(float));
    assert(send_data && recv_data);

    fill_test_data(send_data, total_samples, 42);

    /* Send */
    int ret = cortex_protocol_send_result_chunked(
        client, 1, 0, 100, 200, 300, 400, 500,
        send_data, length, channels
    );
    assert(ret == 0);

    /* Receive */
    uint32_t recv_session, recv_length, recv_channels;
    uint64_t tin, tstart, tend, tfirst_tx, tlast_tx;
    ret = cortex_protocol_recv_result_chunked(
        server, 0, recv_data, total_samples * sizeof(float), 5000,
        &recv_session, &tin, &tstart, &tend, &tfirst_tx, &tlast_tx,
        &recv_length, &recv_channels
    );
    assert(ret == 0);

    /* Verify metadata */
    assert(recv_session == 1);
    assert(recv_length == length);
    assert(recv_channels == channels);
    assert(tin == 100);
    assert(tstart == 200);
    assert(tend == 300);
    assert(tfirst_tx == 400);
    assert(tlast_tx == 500);

    /* Verify data */
    for (size_t i = 0; i < total_samples; i++) {
        assert(recv_data[i] == send_data[i]);
    }

    free(send_data);
    free(recv_data);
    client->close(client->ctx);
    free(client);
    server->close(server->ctx);
    free(server);

    printf("  ✓ Single chunk test passed\n");
}

/* Test 2: Large RESULT requiring multiple chunks (512ch) */
static void test_result_multiple_chunks_512ch(void) {
    printf("TEST: Multiple chunks RESULT (512ch × 160 = 320KB)...\n");

    cortex_transport_t *client, *server;
    assert(create_mock_transport_pair(&client, &server) == 0);

    /* 512ch × 160 samples = 81,920 samples = 327,680 bytes = 40 chunks */
    uint32_t channels = 512;
    uint32_t length = 160;
    uint32_t total_samples = channels * length;

    float *send_data = (float *)malloc(total_samples * sizeof(float));
    float *recv_data = (float *)malloc(total_samples * sizeof(float));
    assert(send_data && recv_data);

    fill_test_data(send_data, total_samples, 12345);

    /* Send */
    int ret = cortex_protocol_send_result_chunked(
        client, 2, 5, 1000, 2000, 3000, 4000, 5000,
        send_data, length, channels
    );
    assert(ret == 0);

    /* Receive */
    uint32_t recv_session, recv_length, recv_channels;
    uint64_t tin, tstart, tend, tfirst_tx, tlast_tx;
    ret = cortex_protocol_recv_result_chunked(
        server, 5, recv_data, total_samples * sizeof(float), 5000,
        &recv_session, &tin, &tstart, &tend, &tfirst_tx, &tlast_tx,
        &recv_length, &recv_channels
    );
    assert(ret == 0);

    /* Verify metadata */
    assert(recv_session == 2);
    assert(recv_length == length);
    assert(recv_channels == channels);

    /* Verify data integrity */
    for (size_t i = 0; i < total_samples; i++) {
        assert(recv_data[i] == send_data[i]);
    }

    free(send_data);
    free(recv_data);
    client->close(client->ctx);
    free(client);
    server->close(server->ctx);
    free(server);

    printf("  ✓ 512ch chunking test passed\n");
}

/* Test 3: Very large RESULT (1024ch) */
static void test_result_very_large_1024ch(void) {
    printf("TEST: Very large RESULT (1024ch × 160 = 640KB)...\n");

    cortex_transport_t *client, *server;
    assert(create_mock_transport_pair(&client, &server) == 0);

    /* 1024ch × 160 samples = 163,840 samples = 655,360 bytes = 80 chunks */
    uint32_t channels = 1024;
    uint32_t length = 160;
    uint32_t total_samples = channels * length;

    float *send_data = (float *)malloc(total_samples * sizeof(float));
    float *recv_data = (float *)malloc(total_samples * sizeof(float));
    assert(send_data && recv_data);

    fill_test_data(send_data, total_samples, 99999);

    /* Send */
    int ret = cortex_protocol_send_result_chunked(
        client, 3, 10, 10000, 20000, 30000, 40000, 50000,
        send_data, length, channels
    );
    assert(ret == 0);

    /* Receive */
    uint32_t recv_session, recv_length, recv_channels;
    uint64_t tin, tstart, tend, tfirst_tx, tlast_tx;
    ret = cortex_protocol_recv_result_chunked(
        server, 10, recv_data, total_samples * sizeof(float), 10000,
        &recv_session, &tin, &tstart, &tend, &tfirst_tx, &tlast_tx,
        &recv_length, &recv_channels
    );
    assert(ret == 0);

    /* Verify */
    assert(recv_session == 3);
    assert(recv_length == length);
    assert(recv_channels == channels);

    for (size_t i = 0; i < total_samples; i++) {
        assert(recv_data[i] == send_data[i]);
    }

    free(send_data);
    free(recv_data);
    client->close(client->ctx);
    free(client);
    server->close(server->ctx);
    free(server);

    printf("  ✓ 1024ch chunking test passed\n");
}

/* Test 4: Edge case - exactly 8KB */
static void test_result_exactly_one_chunk(void) {
    printf("TEST: RESULT exactly 8KB (edge case)...\n");

    cortex_transport_t *client, *server;
    assert(create_mock_transport_pair(&client, &server) == 0);

    /* 8KB = 2048 float32 samples */
    uint32_t channels = 16;
    uint32_t length = 128;  /* 16 × 128 = 2048 samples = 8192 bytes */
    uint32_t total_samples = channels * length;

    float *send_data = (float *)malloc(total_samples * sizeof(float));
    float *recv_data = (float *)malloc(total_samples * sizeof(float));
    assert(send_data && recv_data);

    fill_test_data(send_data, total_samples, 7777);

    /* Send */
    int ret = cortex_protocol_send_result_chunked(
        client, 4, 20, 100, 200, 300, 400, 500,
        send_data, length, channels
    );
    assert(ret == 0);

    /* Receive */
    uint32_t recv_session, recv_length, recv_channels;
    uint64_t tin, tstart, tend, tfirst_tx, tlast_tx;
    ret = cortex_protocol_recv_result_chunked(
        server, 20, recv_data, total_samples * sizeof(float), 5000,
        &recv_session, &tin, &tstart, &tend, &tfirst_tx, &tlast_tx,
        &recv_length, &recv_channels
    );
    assert(ret == 0);

    /* Verify */
    for (size_t i = 0; i < total_samples; i++) {
        assert(recv_data[i] == send_data[i]);
    }

    free(send_data);
    free(recv_data);
    client->close(client->ctx);
    free(client);
    server->close(server->ctx);
    free(server);

    printf("  ✓ Exactly 8KB test passed\n");
}

/* Test 5: Sequence mismatch detection */
static void test_result_sequence_mismatch(void) {
    printf("TEST: Sequence mismatch detection...\n");

    cortex_transport_t *client, *server;
    assert(create_mock_transport_pair(&client, &server) == 0);

    uint32_t channels = 64;
    uint32_t length = 160;
    uint32_t total_samples = channels * length;

    float *send_data = (float *)malloc(total_samples * sizeof(float));
    float *recv_data = (float *)malloc(total_samples * sizeof(float));
    assert(send_data && recv_data);

    fill_test_data(send_data, total_samples, 1111);

    /* Send with sequence 5 */
    int ret = cortex_protocol_send_result_chunked(
        client, 1, 5, 100, 200, 300, 400, 500,
        send_data, length, channels
    );
    assert(ret == 0);

    /* Try to receive expecting sequence 10 (wrong!) */
    uint32_t recv_session, recv_length, recv_channels;
    uint64_t tin, tstart, tend, tfirst_tx, tlast_tx;
    ret = cortex_protocol_recv_result_chunked(
        server, 10, recv_data, total_samples * sizeof(float), 5000,
        &recv_session, &tin, &tstart, &tend, &tfirst_tx, &tlast_tx,
        &recv_length, &recv_channels
    );

    /* Should fail with sequence mismatch */
    assert(ret == CORTEX_ECHUNK_SEQUENCE_MISMATCH);

    free(send_data);
    free(recv_data);
    client->close(client->ctx);
    free(client);
    server->close(server->ctx);
    free(server);

    printf("  ✓ Sequence mismatch detection passed\n");
}

int main(void) {
    printf("================================================================================\n");
    printf("RESULT Chunking Protocol Tests\n");
    printf("================================================================================\n\n");

    test_result_single_chunk();
    test_result_multiple_chunks_512ch();
    test_result_very_large_1024ch();
    test_result_exactly_one_chunk();
    test_result_sequence_mismatch();

    printf("\n✓ All RESULT chunking tests passed\n");
    return 0;
}
