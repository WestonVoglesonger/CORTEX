/*
 * CORTEX Calibration State I/O Tests (ABI v3)
 *
 * Tests cortex_state_save(), cortex_state_load(), and cortex_state_validate()
 * from sdk/kernel/lib/state_io/state_io.c
 *
 * Coverage:
 *   1. Basic Save/Load (3 tests)
 *   2. Corrupt File Handling (6 tests)
 *   3. Security (2 tests)
 *   4. Endianness (2 tests)
 *   5. State Version Evolution (2 tests)
 */

#include "test_common.h"  /* MUST be first - defines feature test macros */
#include "cortex_state_io.h"
#include "cortex_plugin.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <sys/stat.h>

/* Test data directory (created in /tmp to avoid polluting source tree) */
#define TEST_DIR "/tmp/cortex_test_state_io"
#define TEST_FILE(name) TEST_DIR "/" name

/* Helper: Create test directory */
static void setup_test_dir(void) {
    mkdir(TEST_DIR, 0755);
}

/* Helper: Clean up test directory */
static void cleanup_test_dir(void) {
    system("rm -rf " TEST_DIR);
}

/* Helper: Create mock calibration state */
static uint8_t *create_mock_state(uint32_t size) {
    uint8_t *state = (uint8_t *)malloc(size);
    if (!state) return NULL;

    /* Fill with pattern: byte[i] = i % 256 */
    for (uint32_t i = 0; i < size; i++) {
        state[i] = (uint8_t)(i % 256);
    }

    return state;
}

/* Helper: Verify mock state pattern */
static int verify_mock_state(const uint8_t *state, uint32_t size) {
    for (uint32_t i = 0; i < size; i++) {
        if (state[i] != (uint8_t)(i % 256)) {
            return -1;
        }
    }
    return 0;
}

/* Helper: Write corrupt file manually */
static void write_corrupt_file(const char *path, const uint8_t *data, size_t size) {
    FILE *f = fopen(path, "wb");
    if (f) {
        fwrite(data, 1, size, f);
        fclose(f);
    }
}

/*
 * ========================================
 * 1. Basic Save/Load Tests
 * ========================================
 */

/* Test 1: Save small state (100B) → load → verify round-trip */
static int test_save_load_small(void) {
    printf("[TEST] save/load small state (100B)...\n");

    const uint32_t state_size = 100;
    const uint32_t state_version = 1;
    const char *path = TEST_FILE("small.cortex_state");

    /* Create mock state */
    uint8_t *original = create_mock_state(state_size);
    ASSERT(original != NULL, "Failed to allocate original state");

    /* Save */
    int ret = cortex_state_save(path, original, state_size, state_version);
    ASSERT(ret == 0, "Save should succeed");

    /* Load */
    void *loaded = NULL;
    uint32_t loaded_size = 0;
    uint32_t loaded_version = 0;
    ret = cortex_state_load(path, &loaded, &loaded_size, &loaded_version);
    ASSERT(ret == 0, "Load should succeed");
    ASSERT(loaded != NULL, "Loaded payload should not be NULL");
    ASSERT(loaded_size == state_size, "Loaded size should match");
    ASSERT(loaded_version == state_version, "Loaded version should match");

    /* Verify contents */
    ret = verify_mock_state((uint8_t *)loaded, loaded_size);
    ASSERT(ret == 0, "Loaded data should match original pattern");

    /* Cleanup */
    free(original);
    free(loaded);

    printf("  PASS\n");
    return 0;
}

/* Test 2: Save medium state (16KB, typical ICA for C=64) → verify */
static int test_save_load_medium(void) {
    printf("[TEST] save/load medium state (16KB)...\n");

    const uint32_t state_size = 16 * 1024;  /* 16 KB (typical ICA) */
    const uint32_t state_version = 1;
    const char *path = TEST_FILE("medium.cortex_state");

    uint8_t *original = create_mock_state(state_size);
    ASSERT(original != NULL, "Failed to allocate original state");

    int ret = cortex_state_save(path, original, state_size, state_version);
    ASSERT(ret == 0, "Save should succeed");

    void *loaded = NULL;
    uint32_t loaded_size = 0;
    ret = cortex_state_load(path, &loaded, &loaded_size, NULL);
    ASSERT(ret == 0, "Load should succeed");
    ASSERT(loaded_size == state_size, "Loaded size should match");

    ret = verify_mock_state((uint8_t *)loaded, loaded_size);
    ASSERT(ret == 0, "Loaded data should match original pattern");

    free(original);
    free(loaded);

    printf("  PASS\n");
    return 0;
}

/* Test 3: Save large state (1MB) → verify */
static int test_save_load_large(void) {
    printf("[TEST] save/load large state (1MB)...\n");

    const uint32_t state_size = 1024 * 1024;  /* 1 MB */
    const uint32_t state_version = 2;
    const char *path = TEST_FILE("large.cortex_state");

    uint8_t *original = create_mock_state(state_size);
    ASSERT(original != NULL, "Failed to allocate original state");

    int ret = cortex_state_save(path, original, state_size, state_version);
    ASSERT(ret == 0, "Save should succeed");

    void *loaded = NULL;
    uint32_t loaded_size = 0;
    uint32_t loaded_version = 0;
    ret = cortex_state_load(path, &loaded, &loaded_size, &loaded_version);
    ASSERT(ret == 0, "Load should succeed");
    ASSERT(loaded_size == state_size, "Loaded size should match");
    ASSERT(loaded_version == state_version, "Loaded version should match");

    ret = verify_mock_state((uint8_t *)loaded, loaded_size);
    ASSERT(ret == 0, "Loaded data should match original pattern");

    free(original);
    free(loaded);

    printf("  PASS\n");
    return 0;
}

/*
 * ========================================
 * 2. Corrupt File Handling Tests
 * ========================================
 */

/* Test 4: Bad magic number (not 0x434F5254) */
static int test_corrupt_bad_magic(void) {
    printf("[TEST] corrupt file: bad magic number...\n");

    const char *path = TEST_FILE("bad_magic.cortex_state");
    uint8_t corrupt[16] = {
        0xFF, 0xFF, 0xFF, 0xFF,  /* Bad magic */
        0x03, 0x00, 0x00, 0x00,  /* ABI v3 */
        0x01, 0x00, 0x00, 0x00,  /* state_version=1 */
        0x64, 0x00, 0x00, 0x00   /* state_size=100 */
    };
    write_corrupt_file(path, corrupt, sizeof(corrupt));

    void *loaded = NULL;
    uint32_t loaded_size = 0;
    int ret = cortex_state_load(path, &loaded, &loaded_size, NULL);
    ASSERT(ret != 0, "Load should fail with bad magic");
    ASSERT(loaded == NULL, "Payload should be NULL on failure");

    printf("  PASS\n");
    return 0;
}

/* Test 5: Wrong ABI version (v2 state file, v3 runtime) */
static int test_corrupt_wrong_abi_version(void) {
    printf("[TEST] corrupt file: wrong ABI version...\n");

    const char *path = TEST_FILE("wrong_abi.cortex_state");
    uint8_t corrupt[16] = {
        0x54, 0x52, 0x4F, 0x43,  /* CORT */
        0x02, 0x00, 0x00, 0x00,  /* ABI v2 (wrong!) */
        0x01, 0x00, 0x00, 0x00,  /* state_version=1 */
        0x64, 0x00, 0x00, 0x00   /* state_size=100 */
    };
    write_corrupt_file(path, corrupt, sizeof(corrupt));

    void *loaded = NULL;
    uint32_t loaded_size = 0;
    int ret = cortex_state_load(path, &loaded, &loaded_size, NULL);
    ASSERT(ret != 0, "Load should fail with wrong ABI version");

    printf("  PASS\n");
    return 0;
}

/* Test 6: Truncated header (only 12 bytes instead of 16) */
static int test_corrupt_truncated_header(void) {
    printf("[TEST] corrupt file: truncated header...\n");

    const char *path = TEST_FILE("truncated_header.cortex_state");
    uint8_t corrupt[12] = {
        0x54, 0x52, 0x4F, 0x43,  /* CORT */
        0x03, 0x00, 0x00, 0x00,  /* ABI v3 */
        0x01, 0x00, 0x00, 0x00   /* state_version=1 (missing state_size) */
    };
    write_corrupt_file(path, corrupt, sizeof(corrupt));

    void *loaded = NULL;
    uint32_t loaded_size = 0;
    int ret = cortex_state_load(path, &loaded, &loaded_size, NULL);
    ASSERT(ret != 0, "Load should fail with truncated header");

    printf("  PASS\n");
    return 0;
}

/* Test 7: Truncated payload (header says 16KB, file has 8KB) */
static int test_corrupt_truncated_payload(void) {
    printf("[TEST] corrupt file: truncated payload...\n");

    const char *path = TEST_FILE("truncated_payload.cortex_state");

    /* Write valid header claiming 16KB, but only write 8KB */
    FILE *f = fopen(path, "wb");
    ASSERT(f != NULL, "Failed to create test file");

    uint8_t header[16] = {
        0x54, 0x52, 0x4F, 0x43,  /* CORT */
        0x03, 0x00, 0x00, 0x00,  /* ABI v3 */
        0x01, 0x00, 0x00, 0x00,  /* state_version=1 */
        0x00, 0x40, 0x00, 0x00   /* state_size=16384 (16KB) */
    };
    fwrite(header, 1, 16, f);

    /* Write only 8KB of payload instead of claimed 16KB */
    uint8_t *partial_payload = create_mock_state(8 * 1024);
    fwrite(partial_payload, 1, 8 * 1024, f);
    fclose(f);
    free(partial_payload);

    void *loaded = NULL;
    uint32_t loaded_size = 0;
    int ret = cortex_state_load(path, &loaded, &loaded_size, NULL);
    ASSERT(ret != 0, "Load should fail with truncated payload");

    printf("  PASS\n");
    return 0;
}

/* Test 8: Empty file (0 bytes) */
static int test_corrupt_empty_file(void) {
    printf("[TEST] corrupt file: empty file...\n");

    const char *path = TEST_FILE("empty.cortex_state");

    /* Create empty file */
    FILE *f = fopen(path, "wb");
    ASSERT(f != NULL, "Failed to create test file");
    fclose(f);

    void *loaded = NULL;
    uint32_t loaded_size = 0;
    int ret = cortex_state_load(path, &loaded, &loaded_size, NULL);
    ASSERT(ret != 0, "Load should fail with empty file");

    printf("  PASS\n");
    return 0;
}

/* Test 9: File doesn't exist */
static int test_corrupt_file_not_found(void) {
    printf("[TEST] corrupt file: file not found...\n");

    const char *path = TEST_FILE("nonexistent.cortex_state");

    void *loaded = NULL;
    uint32_t loaded_size = 0;
    int ret = cortex_state_load(path, &loaded, &loaded_size, NULL);
    ASSERT(ret != 0, "Load should fail with nonexistent file");

    printf("  PASS\n");
    return 0;
}

/*
 * ========================================
 * 3. Security Tests
 * ========================================
 */

/* Test 10: Path traversal attempt (../../etc/passwd) */
static int test_security_path_traversal(void) {
    printf("[TEST] security: path traversal attempt...\n");

    const char *malicious_path = "../../etc/passwd";
    uint8_t mock_state[100];
    memset(mock_state, 0xAA, sizeof(mock_state));

    int ret = cortex_state_save(malicious_path, mock_state, sizeof(mock_state), 1);
    ASSERT(ret != 0, "Save should reject path traversal");

    printf("  PASS\n");
    return 0;
}

/* Test 11: Max size enforcement (try to save 300MB, enforce 256MB limit) */
static int test_security_max_size(void) {
    printf("[TEST] security: max size enforcement...\n");

    const char *path = TEST_FILE("oversized.cortex_state");
    const uint32_t oversized = 300 * 1024 * 1024;  /* 300 MB */

    /* Don't actually allocate 300MB - just test rejection */
    uint8_t dummy[100];
    int ret = cortex_state_save(path, dummy, oversized, 1);
    ASSERT(ret != 0, "Save should reject oversized state");

    printf("  PASS\n");
    return 0;
}

/*
 * ========================================
 * 4. Endianness Tests
 * ========================================
 */

/* Test 12: Write uint32 on little-endian system, verify bytes */
static int test_endianness_write(void) {
    printf("[TEST] endianness: verify little-endian write...\n");

    const char *path = TEST_FILE("endian_test.cortex_state");
    uint8_t state[4] = {0x12, 0x34, 0x56, 0x78};

    int ret = cortex_state_save(path, state, sizeof(state), 0xDEADBEEF);
    ASSERT(ret == 0, "Save should succeed");

    /* Manually read file and verify state_version bytes (offset 8-11) */
    FILE *f = fopen(path, "rb");
    ASSERT(f != NULL, "File should exist");

    fseek(f, 8, SEEK_SET);  /* Skip magic (4B) + abi_version (4B) */
    uint8_t version_bytes[4];
    size_t n = fread(version_bytes, 1, 4, f);
    fclose(f);

    ASSERT(n == 4, "Should read 4 bytes");
    ASSERT(version_bytes[0] == 0xEF, "Byte 0 should be 0xEF (little-endian)");
    ASSERT(version_bytes[1] == 0xBE, "Byte 1 should be 0xBE");
    ASSERT(version_bytes[2] == 0xAD, "Byte 2 should be 0xAD");
    ASSERT(version_bytes[3] == 0xDE, "Byte 3 should be 0xDE");

    printf("  PASS\n");
    return 0;
}

/* Test 13: Simulate big-endian read (manual byte swap, verify detection) */
static int test_endianness_read(void) {
    printf("[TEST] endianness: verify little-endian read...\n");

    const char *path = TEST_FILE("endian_read.cortex_state");

    /* Manually write file with known byte patterns */
    FILE *f = fopen(path, "wb");
    ASSERT(f != NULL, "File creation should succeed");

    /* Write magic as little-endian bytes: CORT = 0x434F5254 */
    uint8_t header[16] = {
        0x54, 0x52, 0x4F, 0x43,  /* CORT in little-endian */
        0x03, 0x00, 0x00, 0x00,  /* ABI v3 = 3 */
        0x01, 0x00, 0x00, 0x00,  /* state_version = 1 */
        0x04, 0x00, 0x00, 0x00   /* state_size = 4 */
    };
    fwrite(header, 1, 16, f);

    uint8_t payload[4] = {0xAA, 0xBB, 0xCC, 0xDD};
    fwrite(payload, 1, 4, f);
    fclose(f);

    /* Load and verify */
    void *loaded = NULL;
    uint32_t loaded_size = 0;
    uint32_t loaded_version = 0;
    int ret = cortex_state_load(path, &loaded, &loaded_size, &loaded_version);
    ASSERT(ret == 0, "Load should succeed");
    ASSERT(loaded_size == 4, "Size should be 4");
    ASSERT(loaded_version == 1, "Version should be 1");
    ASSERT(((uint8_t *)loaded)[0] == 0xAA, "Payload byte 0 should match");
    ASSERT(((uint8_t *)loaded)[1] == 0xBB, "Payload byte 1 should match");
    ASSERT(((uint8_t *)loaded)[2] == 0xCC, "Payload byte 2 should match");
    ASSERT(((uint8_t *)loaded)[3] == 0xDD, "Payload byte 3 should match");

    free(loaded);

    printf("  PASS\n");
    return 0;
}

/*
 * ========================================
 * 5. State Version Evolution Tests
 * ========================================
 */

/* Test 14: Save state_version=1, load and verify returned version */
static int test_version_evolution_v1(void) {
    printf("[TEST] version evolution: save v1, verify load returns v1...\n");

    const char *path = TEST_FILE("version_v1.cortex_state");
    uint8_t state[100];
    memset(state, 0x42, sizeof(state));

    int ret = cortex_state_save(path, state, sizeof(state), 1);
    ASSERT(ret == 0, "Save should succeed");

    void *loaded = NULL;
    uint32_t loaded_size = 0;
    uint32_t loaded_version = 0;
    ret = cortex_state_load(path, &loaded, &loaded_size, &loaded_version);
    ASSERT(ret == 0, "Load should succeed");
    ASSERT(loaded_version == 1, "Version should be 1");

    free(loaded);

    printf("  PASS\n");
    return 0;
}

/* Test 15: Save state_version=2, verify loader returns correct version */
static int test_version_evolution_v2(void) {
    printf("[TEST] version evolution: save v2, verify load returns v2...\n");

    const char *path = TEST_FILE("version_v2.cortex_state");
    uint8_t state[200];
    memset(state, 0x88, sizeof(state));

    int ret = cortex_state_save(path, state, sizeof(state), 2);
    ASSERT(ret == 0, "Save should succeed");

    void *loaded = NULL;
    uint32_t loaded_size = 0;
    uint32_t loaded_version = 0;
    ret = cortex_state_load(path, &loaded, &loaded_size, &loaded_version);
    ASSERT(ret == 0, "Load should succeed");
    ASSERT(loaded_version == 2, "Version should be 2");

    /* Also test validate() */
    ret = cortex_state_validate(path);
    ASSERT(ret == 0, "Validate should succeed");

    free(loaded);

    printf("  PASS\n");
    return 0;
}

/*
 * ========================================
 * Test Runner
 * ========================================
 */

int main(void) {
    printf("\n");
    printf("===========================================\n");
    printf("CORTEX State I/O Tests (ABI v3)\n");
    printf("===========================================\n");
    printf("\n");

    setup_test_dir();

    int passed = 0;
    int failed = 0;

    /* Basic Save/Load */
    if (test_save_load_small() == 0) passed++; else failed++;
    if (test_save_load_medium() == 0) passed++; else failed++;
    if (test_save_load_large() == 0) passed++; else failed++;

    /* Corrupt File Handling */
    if (test_corrupt_bad_magic() == 0) passed++; else failed++;
    if (test_corrupt_wrong_abi_version() == 0) passed++; else failed++;
    if (test_corrupt_truncated_header() == 0) passed++; else failed++;
    if (test_corrupt_truncated_payload() == 0) passed++; else failed++;
    if (test_corrupt_empty_file() == 0) passed++; else failed++;
    if (test_corrupt_file_not_found() == 0) passed++; else failed++;

    /* Security */
    if (test_security_path_traversal() == 0) passed++; else failed++;
    if (test_security_max_size() == 0) passed++; else failed++;

    /* Endianness */
    if (test_endianness_write() == 0) passed++; else failed++;
    if (test_endianness_read() == 0) passed++; else failed++;

    /* State Version Evolution */
    if (test_version_evolution_v1() == 0) passed++; else failed++;
    if (test_version_evolution_v2() == 0) passed++; else failed++;

    cleanup_test_dir();

    printf("\n");
    printf("===========================================\n");
    printf("Test Results\n");
    printf("===========================================\n");
    printf("Passed: %d\n", passed);
    printf("Failed: %d\n", failed);
    printf("Total:  %d\n", passed + failed);
    printf("\n");

    return (failed == 0) ? 0 : 1;
}
