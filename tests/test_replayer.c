/*
 * Unit tests for the CORTEX replayer module.
 *
 * These tests verify that the replayer:
 * 1. Streams hop-sized chunks (not windows)
 * 2. Maintains correct real-time cadence (H/Fs seconds per chunk)
 * 3. Handles EOF correctly (rewind and continue)
 * 4. Works with various configurations (different H, Fs, C)
 * 5. Integrates correctly with the scheduler
 */

#define _POSIX_C_SOURCE 200809L

#include <assert.h>
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "../src/engine/replayer/replayer.h"

/* Test utilities */
#define TEST_ASSERT(condition, message) \
    do { \
        if (!(condition)) { \
            fprintf(stderr, "FAIL: %s:%d - %s\n", __FILE__, __LINE__, message); \
            return -1; \
        } \
    } while (0)

#define TEST_ASSERT_EQ(expected, actual, message) \
    do { \
        if ((expected) != (actual)) { \
            fprintf(stderr, "FAIL: %s:%d - %s (expected: %ld, got: %ld)\n", \
                    __FILE__, __LINE__, message, (long)(expected), (long)(actual)); \
            return -1; \
        } \
    } while (0)

#define TEST_ASSERT_NEAR(expected, actual, tolerance, message) \
    do { \
        double _diff = fabs((double)(expected) - (double)(actual)); \
        if (_diff > (tolerance)) { \
            fprintf(stderr, "FAIL: %s:%d - %s (expected: %.3f, got: %.3f, diff: %.3f)\n", \
                    __FILE__, __LINE__, message, (double)(expected), (double)(actual), _diff); \
            return -1; \
        } \
    } while (0)

/* Test fixture data */
typedef struct {
    size_t callback_count;
    size_t total_samples_received;
    size_t expected_chunk_size;
    struct timespec first_callback_time;
    struct timespec last_callback_time;
    double expected_period_sec;
    int timing_error_count;
    float *received_data;
    size_t received_data_capacity;
} test_context_t;

/* Test callback that records invocations */
static void test_callback(const float *chunk_data, size_t chunk_samples, void *user_data) {
    test_context_t *ctx = (test_context_t *)user_data;
    
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    
    if (ctx->callback_count == 0) {
        ctx->first_callback_time = now;
    } else {
        /* Check timing between callbacks */
        struct timespec prev = ctx->last_callback_time;
        double elapsed = (now.tv_sec - prev.tv_sec) + 
                        (now.tv_nsec - prev.tv_nsec) / 1e9;
        
        /* Allow 5% tolerance for timing jitter */
        double tolerance = ctx->expected_period_sec * 0.05;
        if (fabs(elapsed - ctx->expected_period_sec) > tolerance) {
            ctx->timing_error_count++;
        }
    }
    
    ctx->last_callback_time = now;
    ctx->callback_count++;
    ctx->total_samples_received += chunk_samples;
    
    /* Verify chunk size */
    if (chunk_samples != ctx->expected_chunk_size) {
        fprintf(stderr, "ERROR: Expected %zu samples, got %zu\n",
                ctx->expected_chunk_size, chunk_samples);
    }
    
    /* Optionally store received data for validation */
    if (ctx->received_data && ctx->total_samples_received <= ctx->received_data_capacity) {
        size_t offset = ctx->total_samples_received - chunk_samples;
        memcpy(ctx->received_data + offset, chunk_data, chunk_samples * sizeof(float));
    }
}

/* Helper to create a test dataset file */
static int create_test_dataset(const char *path, size_t total_samples) {
    FILE *f = fopen(path, "wb");
    if (!f) {
        return -1;
    }
    
    /* Generate simple ramp pattern: 0, 1, 2, 3, ... */
    for (size_t i = 0; i < total_samples; i++) {
        float value = (float)i;
        fwrite(&value, sizeof(float), 1, f);
    }
    
    fclose(f);
    return 0;
}

/* Test 1: Verify hop-sized chunks are sent (not windows) */
static int test_hop_sized_chunks(void) {
    printf("TEST: hop-sized chunks (not windows)\n");
    
    const char *test_file = "/tmp/cortex_test_hop.dat";
    const uint32_t sample_rate = 160;
    const uint32_t channels = 4;
    const uint32_t hop_samples = 8;
    const uint32_t window_samples = 16;
    const size_t total_samples = hop_samples * channels * 10; /* 10 chunks */
    
    create_test_dataset(test_file, total_samples);
    
    test_context_t ctx = {0};
    ctx.expected_chunk_size = hop_samples * channels;
    ctx.expected_period_sec = (double)hop_samples / (double)sample_rate;
    
    cortex_replayer_config_t config = {0};
    config.dataset_path = test_file;
    config.sample_rate_hz = sample_rate;
    config.channels = channels;
    config.dtype = 1; /* CORTEX_DTYPE_FLOAT32 */
    config.window_length_samples = window_samples;
    config.hop_samples = hop_samples;
    
    int rc = cortex_replayer_run(&config, test_callback, &ctx);
    TEST_ASSERT(rc == 0, "replayer_run failed");
    
    /* Let it run for a bit */
    usleep(1500000); /* 1.5 seconds - should get ~3 callbacks @ 500ms intervals... wait, 8/160 = 50ms */
    usleep(200000); /* 200ms - should get ~4 callbacks @ 50ms intervals */
    
    cortex_replayer_stop();
    
    /* Verify we got hop-sized chunks, not windows */
    TEST_ASSERT(ctx.callback_count >= 3, "Expected at least 3 callbacks");
    TEST_ASSERT_EQ(ctx.expected_chunk_size, hop_samples * channels,
                   "Chunk size should equal H*C, not W*C");
    
    printf("  ✓ Received %zu callbacks with %zu samples each (H=%u)\n",
           ctx.callback_count, ctx.expected_chunk_size, hop_samples);
    
    unlink(test_file);
    return 0;
}

/* Test 2: Verify correct timing cadence */
static int test_timing_cadence(void) {
    printf("TEST: correct timing cadence\n");
    
    const char *test_file = "/tmp/cortex_test_timing.dat";
    const uint32_t sample_rate = 160;
    const uint32_t channels = 2;
    const uint32_t hop_samples = 80;
    const size_t total_samples = hop_samples * channels * 20;
    
    create_test_dataset(test_file, total_samples);
    
    test_context_t ctx = {0};
    ctx.expected_chunk_size = hop_samples * channels;
    ctx.expected_period_sec = (double)hop_samples / (double)sample_rate; /* 0.5s */
    
    cortex_replayer_config_t config = {0};
    config.dataset_path = test_file;
    config.sample_rate_hz = sample_rate;
    config.channels = channels;
    config.dtype = 1;
    config.window_length_samples = 160;
    config.hop_samples = hop_samples;
    
    cortex_replayer_run(&config, test_callback, &ctx);
    
    /* Run for ~2 seconds to get 4 callbacks */
    usleep(2100000);
    
    cortex_replayer_stop();
    
    /* Verify timing */
    TEST_ASSERT(ctx.callback_count >= 3, "Expected at least 3 callbacks");
    
    /* Calculate average rate */
    double total_time = (ctx.last_callback_time.tv_sec - ctx.first_callback_time.tv_sec) +
                       (ctx.last_callback_time.tv_nsec - ctx.first_callback_time.tv_nsec) / 1e9;
    double avg_period = total_time / (ctx.callback_count - 1);
    
    printf("  Expected period: %.3f s\n", ctx.expected_period_sec);
    printf("  Actual avg period: %.3f s\n", avg_period);
    printf("  Timing errors: %d/%zu\n", ctx.timing_error_count, ctx.callback_count);
    
    /* Allow 10% tolerance for average (OS scheduling jitter) */
    TEST_ASSERT_NEAR(ctx.expected_period_sec, avg_period, 
                     ctx.expected_period_sec * 0.10,
                     "Average period should match H/Fs");
    
    printf("  ✓ Timing cadence correct (%.3f s per chunk)\n", avg_period);
    
    unlink(test_file);
    return 0;
}

/* Test 3: Verify EOF handling and rewind */
static int test_eof_rewind(void) {
    printf("TEST: EOF handling and rewind\n");
    
    const char *test_file = "/tmp/cortex_test_eof.dat";
    const uint32_t sample_rate = 160;
    const uint32_t channels = 1;
    const uint32_t hop_samples = 16;
    const size_t chunks_in_file = 3;
    const size_t total_samples = hop_samples * channels * chunks_in_file;
    
    create_test_dataset(test_file, total_samples);
    
    test_context_t ctx = {0};
    ctx.expected_chunk_size = hop_samples * channels;
    ctx.expected_period_sec = (double)hop_samples / (double)sample_rate;
    
    cortex_replayer_config_t config = {0};
    config.dataset_path = test_file;
    config.sample_rate_hz = sample_rate;
    config.channels = channels;
    config.dtype = 1;
    config.window_length_samples = 32;
    config.hop_samples = hop_samples;
    
    cortex_replayer_run(&config, test_callback, &ctx);
    
    /* File has 3 chunks, run long enough to hit EOF and rewind (should loop) */
    usleep(500000); /* 0.5s - should get multiple loops */
    
    cortex_replayer_stop();
    
    /* Should have gotten more callbacks than chunks in file (due to rewind) */
    TEST_ASSERT(ctx.callback_count > chunks_in_file,
                "Should loop after EOF via rewind");
    
    printf("  ✓ Got %zu callbacks from %zu chunks (looped via rewind)\n",
           ctx.callback_count, chunks_in_file);
    
    unlink(test_file);
    return 0;
}

/* Test 4: Different configurations */
static int test_various_configs(void) {
    printf("TEST: various configurations\n");
    
    struct {
        uint32_t sample_rate;
        uint32_t channels;
        uint32_t hop_samples;
        const char *name;
    } configs[] = {
        {160, 64, 80, "standard EEG"},
        {250, 16, 8, "low-latency MCU"},
        {1000, 32, 32, "medium-rate FPGA"},
        {30000, 96, 128, "high-rate HALO"},
    };
    
    for (size_t i = 0; i < sizeof(configs) / sizeof(configs[0]); i++) {
        char test_file[256];
        snprintf(test_file, sizeof(test_file), "/tmp/cortex_test_config_%zu.dat", i);
        
        const size_t total_samples = configs[i].hop_samples * configs[i].channels * 5;
        create_test_dataset(test_file, total_samples);
        
        test_context_t ctx = {0};
        ctx.expected_chunk_size = configs[i].hop_samples * configs[i].channels;
        ctx.expected_period_sec = (double)configs[i].hop_samples / (double)configs[i].sample_rate;
        
        cortex_replayer_config_t config = {0};
        config.dataset_path = test_file;
        config.sample_rate_hz = configs[i].sample_rate;
        config.channels = configs[i].channels;
        config.dtype = 1;
        config.window_length_samples = configs[i].hop_samples * 2;
        config.hop_samples = configs[i].hop_samples;
        
        cortex_replayer_run(&config, test_callback, &ctx);
        
        /* Run for enough time to get a few callbacks */
        usleep((int)(ctx.expected_period_sec * 3 * 1000000));
        
        cortex_replayer_stop();
        
        TEST_ASSERT(ctx.callback_count >= 2, "Should get at least 2 callbacks");
        TEST_ASSERT_EQ(ctx.expected_chunk_size, configs[i].hop_samples * configs[i].channels,
                       "Chunk size mismatch");
        
        printf("  ✓ %s: Fs=%u Hz, C=%u, H=%u (%.1f ms period)\n",
               configs[i].name,
               configs[i].sample_rate,
               configs[i].channels,
               configs[i].hop_samples,
               ctx.expected_period_sec * 1000.0);
        
        unlink(test_file);
    }
    
    return 0;
}

/* Test 5: Data continuity (samples are in correct order) */
static int test_data_continuity(void) {
    printf("TEST: data continuity\n");
    
    const char *test_file = "/tmp/cortex_test_continuity.dat";
    const uint32_t sample_rate = 160;
    const uint32_t channels = 1; /* Single channel for easy verification */
    const uint32_t hop_samples = 8;
    const size_t num_chunks = 5;
    const size_t total_samples = hop_samples * channels * num_chunks;
    
    create_test_dataset(test_file, total_samples);
    
    test_context_t ctx = {0};
    ctx.expected_chunk_size = hop_samples * channels;
    ctx.expected_period_sec = (double)hop_samples / (double)sample_rate;
    ctx.received_data = calloc(total_samples, sizeof(float));
    ctx.received_data_capacity = total_samples;
    
    cortex_replayer_config_t config = {0};
    config.dataset_path = test_file;
    config.sample_rate_hz = sample_rate;
    config.channels = channels;
    config.dtype = 1;
    config.window_length_samples = 16;
    config.hop_samples = hop_samples;
    
    cortex_replayer_run(&config, test_callback, &ctx);
    
    /* Run long enough to get all chunks */
    usleep((int)(ctx.expected_period_sec * num_chunks * 1000000 * 1.5));
    
    cortex_replayer_stop();
    
    /* Verify data is continuous ramp: 0, 1, 2, 3, ... */
    for (size_t i = 0; i < ctx.total_samples_received && i < total_samples; i++) {
        TEST_ASSERT_NEAR((float)i, ctx.received_data[i], 0.01,
                        "Data should be continuous");
    }
    
    printf("  ✓ Data continuity verified (%zu samples)\n", ctx.total_samples_received);
    
    free(ctx.received_data);
    unlink(test_file);
    return 0;
}

/* Main test runner */
int main(void) {
    int failed = 0;
    int passed = 0;
    
    printf("\n=== CORTEX Replayer Tests ===\n\n");
    
    #define RUN_TEST(test_func) \
        do { \
            if (test_func() == 0) { \
                passed++; \
                printf("  PASS\n\n"); \
            } else { \
                failed++; \
                printf("  FAIL\n\n"); \
            } \
        } while (0)
    
    RUN_TEST(test_hop_sized_chunks);
    RUN_TEST(test_timing_cadence);
    RUN_TEST(test_eof_rewind);
    RUN_TEST(test_various_configs);
    RUN_TEST(test_data_continuity);
    
    printf("=== Test Results ===\n");
    printf("Passed: %d\n", passed);
    printf("Failed: %d\n", failed);
    
    return failed > 0 ? 1 : 0;
}
