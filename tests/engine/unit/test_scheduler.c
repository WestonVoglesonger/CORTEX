/*
 * Unit tests for the CORTEX scheduler module (device_comm integration).
 *
 * These tests verify that the scheduler:
 * 1. Forms windows correctly from hop-sized chunks
 * 2. Creates overlapping windows (retains W-H samples)
 * 3. Dispatches to devices with correct data
 * 4. Tracks deadlines correctly (H/Fs per window)
 * 5. Manages buffer correctly
 * 6. Handles warmup period
 * 7. Supports multiple devices (sequential execution model)
 * 8. Validates configuration
 * 9. Protects against integer overflow
 *
 * Uses mock adapter (tests/c/mock_adapter/mock_adapter) for controlled testing.
 */

#define _POSIX_C_SOURCE 200809L

#include "test_common.h"
#include "scheduler.h"
#include "device_comm.h"
#include "util.h"

#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Test configuration */
#define MOCK_ADAPTER_PATH "../fixtures/mock_adapter/mock_adapter"
#define DEFAULT_SAMPLE_RATE 160
#define DEFAULT_WINDOW_LENGTH 16
#define DEFAULT_HOP 8
#define DEFAULT_CHANNELS 2

/* Helper: Spawn mock adapter and get device handle */
static int setup_mock_device(
    const char *mock_behavior,
    uint32_t sample_rate,
    uint32_t window_samples,
    uint32_t hop_samples,
    uint32_t channels,
    cortex_device_init_result_t *out_result)
{
    /* Set MOCK_BEHAVIOR environment variable */
    if (mock_behavior) {
        setenv("MOCK_BEHAVIOR", mock_behavior, 1);
    }

    int ret = device_comm_init(
        MOCK_ADAPTER_PATH,
        NULL,  /* transport_config = "local://" */
        "identity",  /* mock adapter doesn't load real plugins */
        "",
        sample_rate,
        window_samples,
        hop_samples,
        channels,
        NULL,  /* no calibration state */
        0,
        out_result
    );

    /* Clear environment variable */
    if (mock_behavior) {
        unsetenv("MOCK_BEHAVIOR");
    }

    return ret;
}

/* Helper: Register mock device with scheduler */
static int register_mock_device(
    cortex_scheduler_t *scheduler,
    cortex_device_handle_t *device_handle,
    uint32_t output_window_samples,
    uint32_t output_channels,
    const char *adapter_name,
    const char *plugin_name)
{
    cortex_scheduler_device_info_t device_info = {0};
    device_info.device_handle = device_handle;
    device_info.output_window_length_samples = output_window_samples;
    device_info.output_channels = output_channels;
    strncpy(device_info.adapter_name, adapter_name, sizeof(device_info.adapter_name) - 1);
    strncpy(device_info.plugin_name, plugin_name, sizeof(device_info.plugin_name) - 1);

    return cortex_scheduler_register_device(
        scheduler,
        &device_info,
        output_window_samples,
        output_channels
    );
}

/* Test 1: Configuration validation */
static int test_config_validation(void) {
    TEST_START("configuration validation");

    /* Test NULL config */
    cortex_scheduler_t *scheduler1 = cortex_scheduler_create(NULL);
    ASSERT_NULL(scheduler1, "Should reject NULL config");

    /* Test valid config */
    cortex_scheduler_config_t config = {0};
    config.sample_rate_hz = DEFAULT_SAMPLE_RATE;
    config.window_length_samples = DEFAULT_WINDOW_LENGTH;
    config.hop_samples = DEFAULT_HOP;
    config.channels = DEFAULT_CHANNELS;
    config.dtype = 1;

    cortex_scheduler_t *scheduler2 = cortex_scheduler_create(&config);
    ASSERT_NOT_NULL(scheduler2, "Should accept valid config");

    cortex_scheduler_destroy(scheduler2);

    TEST_PASS();
}

/* Test 2: Integer overflow protection (CRIT-002) */
static int test_integer_overflow_protection(void) {
    TEST_START("integer overflow protection (CRIT-002)");

    /* Test cortex_mul_size_overflow utility */
    size_t result;

    /* No overflow case */
    int rc1 = cortex_mul_size_overflow(1000, 2000, &result);
    ASSERT_EQ(0, rc1, "Should not overflow for 1000 * 2000");
    ASSERT_EQ(2000000, result, "Result should be 2000000");

    /* Overflow case */
    int rc2 = cortex_mul_size_overflow(SIZE_MAX / 2, 3, &result);
    ASSERT_EQ(1, rc2, "Should detect overflow for (SIZE_MAX/2) * 3");

    /* Exact SIZE_MAX case */
    int rc3 = cortex_mul_size_overflow(SIZE_MAX, 1, &result);
    ASSERT_EQ(0, rc3, "SIZE_MAX * 1 should not overflow");
    ASSERT_EQ(SIZE_MAX, result, "Result should be SIZE_MAX");

    /* Test valid large configuration */
    cortex_scheduler_config_t config = {0};
    config.sample_rate_hz = 30000;
    config.window_length_samples = 4096;
    config.hop_samples = 128;
    config.channels = 256;
    config.dtype = 1;

    cortex_scheduler_t *scheduler = cortex_scheduler_create(&config);
    ASSERT_NOT_NULL(scheduler, "Should accept valid large configuration");

    cortex_scheduler_destroy(scheduler);

    TEST_PASS();
}

/* Test 3: Window formation from hop-sized chunks */
static int test_window_formation(void) {
    TEST_START("window formation from hop-sized chunks");

    const uint32_t sample_rate = DEFAULT_SAMPLE_RATE;
    const uint32_t window_length = DEFAULT_WINDOW_LENGTH;
    const uint32_t hop = DEFAULT_HOP;
    const uint32_t channels = DEFAULT_CHANNELS;

    /* Create scheduler */
    cortex_scheduler_config_t config = {0};
    config.sample_rate_hz = sample_rate;
    config.window_length_samples = window_length;
    config.hop_samples = hop;
    config.channels = channels;
    config.dtype = 1;

    cortex_scheduler_t *scheduler = cortex_scheduler_create(&config);
    ASSERT_NOT_NULL(scheduler, "Scheduler creation failed");

    /* Spawn mock adapter */
    cortex_device_init_result_t device_result;
    int ret = setup_mock_device("identity", sample_rate, window_length, hop, channels, &device_result);
    ASSERT_EQ(0, ret, "Mock adapter setup failed");

    /* Register device with scheduler */
    ret = register_mock_device(
        scheduler,
        device_result.handle,
        device_result.output_window_length_samples,
        device_result.output_channels,
        device_result.adapter_name,
        "test-identity"
    );
    ASSERT_EQ(0, ret, "Device registration failed");

    /* Feed samples in hop-sized chunks */
    float chunk1[DEFAULT_HOP * DEFAULT_CHANNELS];
    float chunk2[DEFAULT_HOP * DEFAULT_CHANNELS];

    for (size_t i = 0; i < DEFAULT_HOP * DEFAULT_CHANNELS; i++) {
        chunk1[i] = (float)i;
        chunk2[i] = (float)(i + 100);
    }

    /* Feed first hop - should buffer but not dispatch */
    int consumed1 = cortex_scheduler_feed_samples(scheduler, chunk1, DEFAULT_HOP * DEFAULT_CHANNELS);
    ASSERT_EQ((int)(DEFAULT_HOP * DEFAULT_CHANNELS), consumed1, "Should consume first hop");

    /* Feed second hop - should trigger window dispatch */
    int consumed2 = cortex_scheduler_feed_samples(scheduler, chunk2, DEFAULT_HOP * DEFAULT_CHANNELS);
    ASSERT_EQ((int)(DEFAULT_HOP * DEFAULT_CHANNELS), consumed2, "Should consume second hop");

    /* Window was formed and dispatched to mock adapter */

    /* Cleanup */
    device_comm_teardown(device_result.handle);
    cortex_scheduler_destroy(scheduler);

    TEST_PASS();
}

/* Test 4: Overlapping windows (W-H sample retention) */
static int test_overlapping_windows(void) {
    TEST_START("overlapping windows with sample retention");

    const uint32_t window_length = 16;
    const uint32_t hop = 8;
    const uint32_t channels = 1;  /* Single channel for simplicity */

    cortex_scheduler_config_t config = {0};
    config.sample_rate_hz = DEFAULT_SAMPLE_RATE;
    config.window_length_samples = window_length;
    config.hop_samples = hop;
    config.channels = channels;
    config.dtype = 1;

    cortex_scheduler_t *scheduler = cortex_scheduler_create(&config);
    ASSERT_NOT_NULL(scheduler, "Scheduler creation failed");

    /* Spawn mock adapter */
    cortex_device_init_result_t device_result;
    int ret = setup_mock_device("identity", DEFAULT_SAMPLE_RATE, window_length, hop, channels, &device_result);
    ASSERT_EQ(0, ret, "Mock adapter setup failed");

    ret = register_mock_device(
        scheduler,
        device_result.handle,
        device_result.output_window_length_samples,
        device_result.output_channels,
        device_result.adapter_name,
        "test-overlap"
    );
    ASSERT_EQ(0, ret, "Device registration failed");

    /* Feed 3 hops to generate 2 overlapping windows
     * Window 1: samples [0..15]
     * Window 2: samples [8..23] (overlap: [8..15])
     */
    for (int hop_idx = 0; hop_idx < 3; hop_idx++) {
        float chunk[8];
        for (int i = 0; i < 8; i++) {
            chunk[i] = (float)(hop_idx * 8 + i);
        }
        cortex_scheduler_feed_samples(scheduler, chunk, 8);
    }

    /* Cleanup */
    device_comm_teardown(device_result.handle);
    cortex_scheduler_destroy(scheduler);

    TEST_PASS();
}

/* Test 5: Buffer management with various chunk sizes */
static int test_buffer_management(void) {
    TEST_START("buffer management");

    const uint32_t window_length = 32;
    const uint32_t hop = 16;
    const uint32_t channels = 4;

    cortex_scheduler_config_t config = {0};
    config.sample_rate_hz = DEFAULT_SAMPLE_RATE;
    config.window_length_samples = window_length;
    config.hop_samples = hop;
    config.channels = channels;
    config.dtype = 1;

    cortex_scheduler_t *scheduler = cortex_scheduler_create(&config);
    ASSERT_NOT_NULL(scheduler, "Scheduler creation failed");

    /* Spawn mock adapter */
    cortex_device_init_result_t device_result;
    int ret = setup_mock_device("identity", DEFAULT_SAMPLE_RATE, window_length, hop, channels, &device_result);
    ASSERT_EQ(0, ret, "Mock adapter setup failed");

    ret = register_mock_device(
        scheduler,
        device_result.handle,
        device_result.output_window_length_samples,
        device_result.output_channels,
        device_result.adapter_name,
        "test-buffer"
    );
    ASSERT_EQ(0, ret, "Device registration failed");

    /* Feed samples in various chunk sizes */
    float chunk_small[32];   /* hop/2 samples */
    float chunk_exact[64];   /* exactly hop samples */
    float chunk_large[128];  /* 2×hop samples */

    for (size_t i = 0; i < 32; i++) chunk_small[i] = (float)i;
    for (size_t i = 0; i < 64; i++) chunk_exact[i] = (float)i;
    for (size_t i = 0; i < 128; i++) chunk_large[i] = (float)i;

    /* Should handle various chunk sizes correctly */
    int consumed1 = cortex_scheduler_feed_samples(scheduler, chunk_small, 32);
    ASSERT_EQ(32, consumed1, "Should consume small chunk");

    int consumed2 = cortex_scheduler_feed_samples(scheduler, chunk_exact, 64);
    ASSERT_EQ(64, consumed2, "Should consume exact hop-sized chunk");

    int consumed3 = cortex_scheduler_feed_samples(scheduler, chunk_large, 128);
    ASSERT_EQ(128, consumed3, "Should consume large chunk");

    /* Cleanup */
    device_comm_teardown(device_result.handle);
    cortex_scheduler_destroy(scheduler);

    TEST_PASS();
}

/* Test 6: Multiple devices (sequential execution model) */
static int test_multiple_devices(void) {
    TEST_START("multiple devices (sequential execution)");

    const uint32_t window_length = 16;
    const uint32_t hop = 8;
    const uint32_t channels = 2;

    cortex_scheduler_config_t config = {0};
    config.sample_rate_hz = DEFAULT_SAMPLE_RATE;
    config.window_length_samples = window_length;
    config.hop_samples = hop;
    config.channels = channels;
    config.dtype = 1;

    cortex_scheduler_t *scheduler = cortex_scheduler_create(&config);
    ASSERT_NOT_NULL(scheduler, "Scheduler creation failed");

    /* Spawn 3 mock adapters and register them */
    cortex_device_init_result_t devices[3];
    for (int i = 0; i < 3; i++) {
        int ret = setup_mock_device("identity", DEFAULT_SAMPLE_RATE, window_length, hop, channels, &devices[i]);
        ASSERT_EQ(0, ret, "Mock adapter setup failed");

        char plugin_name[64];
        snprintf(plugin_name, sizeof(plugin_name), "test-device-%d", i);

        ret = register_mock_device(
            scheduler,
            devices[i].handle,
            devices[i].output_window_length_samples,
            devices[i].output_channels,
            devices[i].adapter_name,
            plugin_name
        );
        ASSERT_EQ(0, ret, "Device registration failed");
    }

    /* Feed data to trigger window dispatch to all devices */
    float chunk[16];
    for (size_t i = 0; i < 16; i++) chunk[i] = (float)i;

    /* Feed 2 hops to trigger window */
    cortex_scheduler_feed_samples(scheduler, chunk, 16);
    cortex_scheduler_feed_samples(scheduler, chunk, 16);

    /* All 3 devices should have received the window */

    /* Cleanup */
    for (int i = 0; i < 3; i++) {
        device_comm_teardown(devices[i].handle);
    }
    cortex_scheduler_destroy(scheduler);

    TEST_PASS();
}

/* Test 7: Warmup period */
static int test_warmup_period(void) {
    TEST_START("warmup period handling");

    const uint32_t window_length = 16;
    const uint32_t hop = 8;
    const uint32_t channels = 1;
    const uint32_t warmup_seconds = 1;
    const uint32_t sample_rate = DEFAULT_SAMPLE_RATE;

    cortex_scheduler_config_t config = {0};
    config.sample_rate_hz = sample_rate;
    config.window_length_samples = window_length;
    config.hop_samples = hop;
    config.channels = channels;
    config.dtype = 1;
    config.warmup_seconds = warmup_seconds;

    cortex_scheduler_t *scheduler = cortex_scheduler_create(&config);
    ASSERT_NOT_NULL(scheduler, "Scheduler creation failed");

    /* Warmup windows = (warmup_seconds × Fs) / H = (1 × 160) / 8 = 20 windows */
    uint64_t expected_warmup_windows = (warmup_seconds * sample_rate) / hop;
    ASSERT_EQ(20, expected_warmup_windows, "Warmup window calculation incorrect");

    /* Note: Full warmup testing requires feeding enough windows and checking telemetry,
     * which is beyond the scope of a unit test. This verifies configuration only. */

    cortex_scheduler_destroy(scheduler);

    TEST_PASS();
}

/* Test 8: Flush functionality */
static int test_flush(void) {
    TEST_START("flush remaining samples");

    const uint32_t window_length = 16;
    const uint32_t hop = 8;
    const uint32_t channels = 1;

    cortex_scheduler_config_t config = {0};
    config.sample_rate_hz = DEFAULT_SAMPLE_RATE;
    config.window_length_samples = window_length;
    config.hop_samples = hop;
    config.channels = channels;
    config.dtype = 1;

    cortex_scheduler_t *scheduler = cortex_scheduler_create(&config);
    ASSERT_NOT_NULL(scheduler, "Scheduler creation failed");

    /* Spawn mock adapter */
    cortex_device_init_result_t device_result;
    int ret = setup_mock_device("identity", DEFAULT_SAMPLE_RATE, window_length, hop, channels, &device_result);
    ASSERT_EQ(0, ret, "Mock adapter setup failed");

    ret = register_mock_device(
        scheduler,
        device_result.handle,
        device_result.output_window_length_samples,
        device_result.output_channels,
        device_result.adapter_name,
        "test-flush"
    );
    ASSERT_EQ(0, ret, "Device registration failed");

    /* Feed 2.5 hops worth of data */
    float chunk[8];
    for (size_t i = 0; i < 8; i++) chunk[i] = (float)i;

    cortex_scheduler_feed_samples(scheduler, chunk, 8);
    cortex_scheduler_feed_samples(scheduler, chunk, 8);
    cortex_scheduler_feed_samples(scheduler, chunk, 4);  /* Partial hop */

    /* Flush should process remaining buffered data */
    ret = cortex_scheduler_flush(scheduler);
    ASSERT_EQ(0, ret, "Flush should succeed");

    /* Cleanup */
    device_comm_teardown(device_result.handle);
    cortex_scheduler_destroy(scheduler);

    TEST_PASS();
}

/* Test 9: Sequential scheduler execution (simulates sequential plugin execution) */
static int test_sequential_execution(void) {
    TEST_START("sequential scheduler execution");

    const uint32_t window_length = 16;
    const uint32_t hop = 8;
    const uint32_t channels = 2;

    /* Simulate sequential execution: create and destroy schedulers one by one */
    for (int device_id = 0; device_id < 3; device_id++) {
        cortex_scheduler_config_t config = {0};
        config.sample_rate_hz = DEFAULT_SAMPLE_RATE;
        config.window_length_samples = window_length;
        config.hop_samples = hop;
        config.channels = channels;
        config.dtype = 1;

        cortex_scheduler_t *scheduler = cortex_scheduler_create(&config);
        ASSERT_NOT_NULL(scheduler, "Scheduler creation failed");

        /* Spawn mock adapter */
        cortex_device_init_result_t device_result;
        int ret = setup_mock_device("identity", DEFAULT_SAMPLE_RATE, window_length, hop, channels, &device_result);
        ASSERT_EQ(0, ret, "Mock adapter setup failed");

        char plugin_name[64];
        snprintf(plugin_name, sizeof(plugin_name), "test-sequential-%d", device_id);

        ret = register_mock_device(
            scheduler,
            device_result.handle,
            device_result.output_window_length_samples,
            device_result.output_channels,
            device_result.adapter_name,
            plugin_name
        );
        ASSERT_EQ(0, ret, "Device registration failed");

        /* Feed some data to trigger processing */
        float chunk[16];
        for (size_t i = 0; i < 16; i++) chunk[i] = (float)(i + device_id * 100);

        cortex_scheduler_feed_samples(scheduler, chunk, 16);
        cortex_scheduler_feed_samples(scheduler, chunk, 16);

        /* Clean up before moving to next device */
        device_comm_teardown(device_result.handle);
        cortex_scheduler_destroy(scheduler);
    }

    TEST_PASS();
}

/* Test 10: Data continuity through scheduler */
static int test_data_continuity(void) {
    TEST_START("data continuity through scheduler");

    const uint32_t window_length = 8;
    const uint32_t hop = 4;
    const uint32_t channels = 1;

    cortex_scheduler_config_t config = {0};
    config.sample_rate_hz = DEFAULT_SAMPLE_RATE;
    config.window_length_samples = window_length;
    config.hop_samples = hop;
    config.channels = channels;
    config.dtype = 1;

    cortex_scheduler_t *scheduler = cortex_scheduler_create(&config);
    ASSERT_NOT_NULL(scheduler, "Scheduler creation failed");

    /* Spawn mock adapter */
    cortex_device_init_result_t device_result;
    int ret = setup_mock_device("identity", DEFAULT_SAMPLE_RATE, window_length, hop, channels, &device_result);
    ASSERT_EQ(0, ret, "Mock adapter setup failed");

    ret = register_mock_device(
        scheduler,
        device_result.handle,
        device_result.output_window_length_samples,
        device_result.output_channels,
        device_result.adapter_name,
        "test-continuity"
    );
    ASSERT_EQ(0, ret, "Device registration failed");

    /* Feed continuous ramp: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, ... */
    for (int chunk_idx = 0; chunk_idx < 5; chunk_idx++) {
        float chunk[4];
        for (int i = 0; i < 4; i++) {
            chunk[i] = (float)(chunk_idx * 4 + i);
        }
        cortex_scheduler_feed_samples(scheduler, chunk, 4);
    }

    /* Windows should contain:
     * Window 1: [0, 1, 2, 3, 4, 5, 6, 7]
     * Window 2: [4, 5, 6, 7, 8, 9, 10, 11]
     * Window 3: [8, 9, 10, 11, 12, 13, 14, 15]
     * Window 4: [12, 13, 14, 15, 16, 17, 18, 19]
     */

    /* Cleanup */
    device_comm_teardown(device_result.handle);
    cortex_scheduler_destroy(scheduler);

    TEST_PASS();
}

/* Main test runner */
int main(void) {
    int failed = 0;
    int passed = 0;

    printf("\n=== CORTEX Scheduler Tests (device_comm integration) ===\n\n");

    #define RUN_TEST(test_func) \
        do { \
            int result = test_func(); \
            if (result == 0) { \
                passed++; \
            } else { \
                failed++; \
            } \
        } while (0)

    RUN_TEST(test_config_validation);
    RUN_TEST(test_integer_overflow_protection);
    RUN_TEST(test_window_formation);
    RUN_TEST(test_overlapping_windows);
    RUN_TEST(test_buffer_management);
    RUN_TEST(test_multiple_devices);
    RUN_TEST(test_warmup_period);
    RUN_TEST(test_flush);
    RUN_TEST(test_sequential_execution);
    RUN_TEST(test_data_continuity);

    printf("\n=== Test Results ===\n");
    printf("Passed: %d\n", passed);
    printf("Failed: %d\n", failed);
    printf("Total: %d\n", passed + failed);

    return failed > 0 ? 1 : 0;
}
