/*
 * Unit tests for the CORTEX telemetry module.
 *
 * These tests verify that the telemetry system:
 * 1. Initializes buffers and adds records correctly
 * 2. Grows buffer capacity dynamically (doubling)
 * 3. Protects against integer overflow (CRIT-002)
 * 4. Writes valid CSV output with system info
 * 5. Writes valid NDJSON output
 */

#define _DEFAULT_SOURCE  /* For gethostname and other POSIX/BSD functions */
#define _POSIX_C_SOURCE 200112L

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <unistd.h>

#include "telemetry.h"
#include "util.h"

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

/* Helper: Create a test record */
static cortex_telemetry_record_t make_test_record(uint32_t window_index) {
    cortex_telemetry_record_t rec = {0};
    snprintf(rec.run_id, sizeof(rec.run_id), "test-run");
    snprintf(rec.plugin_name, sizeof(rec.plugin_name), "test_plugin");
    rec.window_index = window_index;
    rec.release_ts_ns = 1000000 * window_index;
    rec.deadline_ts_ns = 2000000 * window_index;
    rec.start_ts_ns = 1000100 * window_index;
    rec.end_ts_ns = 1000200 * window_index;
    rec.deadline_missed = 0;
    rec.W = 256;
    rec.H = 128;
    rec.C = 1;
    rec.Fs = 250;
    rec.warmup = 0;
    rec.repeat = 0;
    return rec;
}

/* Test 1: Basic initialization and record addition */
static int test_init_and_add(void) {
    printf("Running: test_init_and_add...\n");

    cortex_telemetry_buffer_t tb = {0};

    /* Test initialization with explicit capacity */
    int ret = cortex_telemetry_init(&tb, 10);
    TEST_ASSERT(ret == 0, "Init should succeed");
    TEST_ASSERT(tb.capacity == 10, "Capacity should be 10");
    TEST_ASSERT(tb.count == 0, "Count should be 0");
    TEST_ASSERT(tb.records != NULL, "Records pointer should be allocated");

    /* Test adding a single record */
    cortex_telemetry_record_t rec = make_test_record(0);
    ret = cortex_telemetry_add(&tb, &rec);
    TEST_ASSERT(ret == 0, "Add should succeed");
    TEST_ASSERT(tb.count == 1, "Count should be 1");

    /* Verify the record was stored correctly */
    TEST_ASSERT(strcmp(tb.records[0].run_id, "test-run") == 0, "run_id should match");
    TEST_ASSERT(tb.records[0].window_index == 0, "window_index should match");

    /* Test adding multiple records within capacity */
    for (uint32_t i = 1; i < 5; i++) {
        cortex_telemetry_record_t r = make_test_record(i);
        ret = cortex_telemetry_add(&tb, &r);
        TEST_ASSERT(ret == 0, "Add should succeed");
    }
    TEST_ASSERT(tb.count == 5, "Count should be 5");
    TEST_ASSERT(tb.capacity == 10, "Capacity should still be 10");

    /* Test NULL pointer handling */
    ret = cortex_telemetry_add(NULL, &rec);
    TEST_ASSERT(ret == -1, "Add with NULL buffer should fail");

    ret = cortex_telemetry_add(&tb, NULL);
    TEST_ASSERT(ret == -1, "Add with NULL record should fail");

    /* Cleanup */
    cortex_telemetry_free(&tb);
    TEST_ASSERT(tb.records == NULL, "Records should be freed");
    TEST_ASSERT(tb.count == 0, "Count should be reset");
    TEST_ASSERT(tb.capacity == 0, "Capacity should be reset");

    printf("PASS: test_init_and_add\n");
    return 0;
}

/* Test 2: Buffer growth (capacity doubling) */
static int test_buffer_growth(void) {
    printf("Running: test_buffer_growth...\n");

    cortex_telemetry_buffer_t tb = {0};

    /* Initialize with small capacity */
    int ret = cortex_telemetry_init(&tb, 4);
    TEST_ASSERT(ret == 0, "Init should succeed");
    TEST_ASSERT(tb.capacity == 4, "Initial capacity should be 4");

    /* Fill to capacity */
    for (uint32_t i = 0; i < 4; i++) {
        cortex_telemetry_record_t rec = make_test_record(i);
        ret = cortex_telemetry_add(&tb, &rec);
        TEST_ASSERT(ret == 0, "Add should succeed");
    }
    TEST_ASSERT(tb.count == 4, "Count should be 4");
    TEST_ASSERT(tb.capacity == 4, "Capacity should still be 4");

    /* Add one more record - should trigger growth */
    cortex_telemetry_record_t rec = make_test_record(4);
    ret = cortex_telemetry_add(&tb, &rec);
    TEST_ASSERT(ret == 0, "Add should succeed and trigger growth");
    TEST_ASSERT(tb.count == 5, "Count should be 5");
    TEST_ASSERT(tb.capacity == 8, "Capacity should double to 8");

    /* Verify all records are still intact after growth */
    for (uint32_t i = 0; i < 5; i++) {
        TEST_ASSERT(tb.records[i].window_index == i, "Record should be preserved");
    }

    /* Fill to new capacity and trigger another growth */
    for (uint32_t i = 5; i < 8; i++) {
        cortex_telemetry_record_t r = make_test_record(i);
        cortex_telemetry_add(&tb, &r);
    }
    TEST_ASSERT(tb.capacity == 8, "Capacity should still be 8");

    rec = make_test_record(8);
    ret = cortex_telemetry_add(&tb, &rec);
    TEST_ASSERT(ret == 0, "Add should succeed and trigger second growth");
    TEST_ASSERT(tb.capacity == 16, "Capacity should double to 16");

    cortex_telemetry_free(&tb);

    printf("PASS: test_buffer_growth\n");
    return 0;
}

/* Test 3: Integer overflow protection (CRIT-002) */
static int test_overflow_protection(void) {
    printf("Running: test_overflow_protection...\n");

    /* Test the overflow detection utility function directly */
    size_t result;
    int overflow;

    /* Safe multiplication */
    overflow = cortex_mul_size_overflow(100, 200, &result);
    TEST_ASSERT(overflow == 0, "Safe multiplication should not overflow");
    TEST_ASSERT(result == 20000, "Result should be correct");

    /* Overflow case: SIZE_MAX / 2 + 1 * 2 should overflow */
    size_t large = SIZE_MAX / 2 + 1;
    overflow = cortex_mul_size_overflow(large, 2, &result);
    TEST_ASSERT(overflow != 0, "Large multiplication should detect overflow");

    /* Test telemetry buffer overflow protection
     * Note: We can't easily trigger this in a real scenario without allocating
     * huge amounts of memory, so we verify the utility function works correctly.
     * The telemetry_add function uses cortex_mul_size_overflow on lines 44 and 50.
     */

    /* Verify that attempting to double SIZE_MAX/2+1 would be caught */
    size_t new_cap;
    overflow = cortex_mul_size_overflow(SIZE_MAX / 2 + 1, 2, &new_cap);
    TEST_ASSERT(overflow != 0, "Capacity doubling overflow should be detected");

    /* Verify that sizeof(record) * huge_capacity would be caught */
    size_t alloc_size;
    overflow = cortex_mul_size_overflow(SIZE_MAX / sizeof(cortex_telemetry_record_t) + 1,
                                        sizeof(cortex_telemetry_record_t), &alloc_size);
    TEST_ASSERT(overflow != 0, "Allocation size overflow should be detected");

    printf("PASS: test_overflow_protection\n");
    return 0;
}

/* Test 4: CSV output generation */
static int test_write_csv(void) {
    printf("Running: test_write_csv...\n");

    cortex_telemetry_buffer_t tb = {0};
    cortex_telemetry_init(&tb, 10);

    /* Add some test records */
    for (uint32_t i = 0; i < 3; i++) {
        cortex_telemetry_record_t rec = make_test_record(i);
        cortex_telemetry_add(&tb, &rec);
    }

    /* Create system info */
    cortex_system_info_t sysinfo = {0};
    snprintf(sysinfo.os, sizeof(sysinfo.os), "TestOS 1.0");
    snprintf(sysinfo.cpu_model, sizeof(sysinfo.cpu_model), "Test CPU");
    snprintf(sysinfo.hostname, sizeof(sysinfo.hostname), "test-host");
    sysinfo.cpu_count = 4;
    sysinfo.total_ram_mb = 8192;
    sysinfo.thermal_celsius = 42.5f;

    /* Write CSV to temporary file */
    const char *test_path = "/tmp/cortex_test_telemetry.csv";
    int ret = cortex_telemetry_write_csv(test_path, &tb, &sysinfo);
    TEST_ASSERT(ret == 0, "CSV write should succeed");

    /* Verify file exists and has content */
    FILE *f = fopen(test_path, "r");
    TEST_ASSERT(f != NULL, "CSV file should exist");

    char line[512];
    int has_sysinfo = 0;
    int has_header = 0;
    int record_count = 0;

    while (fgets(line, sizeof(line), f)) {
        if (strstr(line, "# System Information")) has_sysinfo = 1;
        if (strstr(line, "run_id,plugin,window_index")) has_header = 1;
        if (strstr(line, "test-run,test_plugin")) record_count++;
    }

    fclose(f);
    unlink(test_path);  /* Clean up */

    TEST_ASSERT(has_sysinfo == 1, "CSV should contain system info");
    TEST_ASSERT(has_header == 1, "CSV should contain header");
    TEST_ASSERT(record_count == 3, "CSV should contain 3 records");

    /* Test NULL pointer handling */
    ret = cortex_telemetry_write_csv(NULL, &tb, &sysinfo);
    TEST_ASSERT(ret == -1, "Write with NULL path should fail");

    ret = cortex_telemetry_write_csv(test_path, NULL, &sysinfo);
    TEST_ASSERT(ret == -1, "Write with NULL buffer should fail");

    cortex_telemetry_free(&tb);

    printf("PASS: test_write_csv\n");
    return 0;
}

/* Test 5: NDJSON output generation */
static int test_write_ndjson(void) {
    printf("Running: test_write_ndjson...\n");

    cortex_telemetry_buffer_t tb = {0};
    cortex_telemetry_init(&tb, 10);

    /* Add some test records */
    for (uint32_t i = 0; i < 3; i++) {
        cortex_telemetry_record_t rec = make_test_record(i);
        cortex_telemetry_add(&tb, &rec);
    }

    /* Create system info */
    cortex_system_info_t sysinfo = {0};
    snprintf(sysinfo.os, sizeof(sysinfo.os), "TestOS 1.0");
    snprintf(sysinfo.cpu_model, sizeof(sysinfo.cpu_model), "Test CPU");
    snprintf(sysinfo.hostname, sizeof(sysinfo.hostname), "test-host");
    sysinfo.cpu_count = 4;
    sysinfo.total_ram_mb = 8192;
    sysinfo.thermal_celsius = -1.0f;  /* Test unavailable thermal */

    /* Write NDJSON to temporary file */
    const char *test_path = "/tmp/cortex_test_telemetry.ndjson";
    int ret = cortex_telemetry_write_ndjson(test_path, &tb, &sysinfo);
    TEST_ASSERT(ret == 0, "NDJSON write should succeed");

    /* Verify file exists and has content */
    FILE *f = fopen(test_path, "r");
    TEST_ASSERT(f != NULL, "NDJSON file should exist");

    char line[1024];
    int has_sysinfo = 0;
    int record_count = 0;

    while (fgets(line, sizeof(line), f)) {
        if (strstr(line, "\"_type\":\"system_info\"")) {
            has_sysinfo = 1;
        } else if (strstr(line, "\"run_id\"")) {
            /* This is a telemetry record (has run_id but no _type) */
            record_count++;
            TEST_ASSERT(strstr(line, "\"plugin\"") != NULL, "Record should have plugin");
            TEST_ASSERT(strstr(line, "\"window_index\"") != NULL, "Record should have window_index");
        }
    }

    fclose(f);
    unlink(test_path);  /* Clean up */

    TEST_ASSERT(has_sysinfo == 1, "NDJSON should contain system info");
    TEST_ASSERT(record_count == 3, "NDJSON should contain 3 records");

    /* Test NULL pointer handling */
    ret = cortex_telemetry_write_ndjson(NULL, &tb, &sysinfo);
    TEST_ASSERT(ret == -1, "Write with NULL path should fail");

    ret = cortex_telemetry_write_ndjson(test_path, NULL, &sysinfo);
    TEST_ASSERT(ret == -1, "Write with NULL buffer should fail");

    cortex_telemetry_free(&tb);

    printf("PASS: test_write_ndjson\n");
    return 0;
}

/* Main test runner */
int main(void) {
    int failed = 0;

    printf("=== CORTEX Telemetry Tests ===\n\n");

    failed += test_init_and_add();
    failed += test_buffer_growth();
    failed += test_overflow_protection();
    failed += test_write_csv();
    failed += test_write_ndjson();

    printf("\n=== Test Summary ===\n");
    if (failed == 0) {
        printf("All tests passed!\n");
        return 0;
    } else {
        printf("%d test(s) failed!\n", -failed);
        return 1;
    }
}
