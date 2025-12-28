#include "cortex_state_io.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <limits.h>

#include "cortex_plugin.h"  /* For CORTEX_ABI_VERSION */

#define CORTEX_MAX_STATE_SIZE (256 * 1024 * 1024)  /* 256 MB limit */

/* Validate path to prevent directory traversal attacks */
static int validate_path(const char *path) {
    if (!path || strlen(path) == 0) {
        return -1;
    }

    /* Check for directory traversal attempts (../) */
    const char *p = path;
    while (*p) {
        if (p[0] == '.' && p[1] == '.' && (p[2] == '/' || p[2] == '\\' || p[2] == '\0')) {
            fprintf(stderr, "[state_io] ERROR: Path contains directory traversal (..)\n");
            return -1;
        }
        p++;
    }

    return 0;
}

/* Write uint32_t in little-endian format */
static int write_le32(FILE *f, uint32_t val) {
    uint8_t bytes[4];
    bytes[0] = (val >> 0) & 0xFF;
    bytes[1] = (val >> 8) & 0xFF;
    bytes[2] = (val >> 16) & 0xFF;
    bytes[3] = (val >> 24) & 0xFF;
    if (fwrite(bytes, 1, 4, f) != 4) {
        return -1;  /* Write failed (disk full, I/O error, etc.) */
    }
    return 0;
}

/* Read uint32_t in little-endian format */
static uint32_t read_le32(FILE *f) {
    uint8_t bytes[4];
    if (fread(bytes, 1, 4, f) != 4) return 0;
    return ((uint32_t)bytes[0] << 0)  |
           ((uint32_t)bytes[1] << 8)  |
           ((uint32_t)bytes[2] << 16) |
           ((uint32_t)bytes[3] << 24);
}

int cortex_state_save(const char *path,
                     const void *state_payload,
                     uint32_t state_size,
                     uint32_t state_version) {
    if (!path || !state_payload || state_size == 0) {
        fprintf(stderr, "[state_io] Invalid parameters for save\n");
        return -1;
    }

    /* Validate path for security */
    if (validate_path(path) < 0) {
        return -1;
    }

    /* Enforce maximum state size */
    if (state_size > CORTEX_MAX_STATE_SIZE) {
        fprintf(stderr, "[state_io] State size %u exceeds maximum %d bytes\n",
                state_size, CORTEX_MAX_STATE_SIZE);
        return -1;
    }

    FILE *f = fopen(path, "wb");
    if (!f) {
        fprintf(stderr, "[state_io] Failed to open %s for writing\n", path);
        return -1;
    }

    /* Write header (16 bytes, little-endian) */
    if (write_le32(f, CORTEX_STATE_MAGIC) < 0 ||
        write_le32(f, CORTEX_ABI_VERSION) < 0 ||  /* Current ABI version (3) */
        write_le32(f, state_version) < 0 ||
        write_le32(f, state_size) < 0) {
        fprintf(stderr, "[state_io] Failed to write header\n");
        fclose(f);
        return -1;
    }

    /* Write payload */
    size_t written = fwrite(state_payload, 1, state_size, f);
    fclose(f);

    if (written != state_size) {
        fprintf(stderr, "[state_io] Failed to write full payload (wrote %zu/%u bytes)\n",
                written, state_size);
        return -1;
    }

    fprintf(stderr, "[state_io] Saved calibration state: %s (%u bytes, version %u)\n",
            path, state_size, state_version);
    return 0;
}

int cortex_state_load(const char *path,
                     void **out_payload,
                     uint32_t *out_size,
                     uint32_t *out_version) {
    if (!path || !out_payload || !out_size) {
        fprintf(stderr, "[state_io] Invalid parameters for load\n");
        return -1;
    }

    /* Validate path for security */
    if (validate_path(path) < 0) {
        return -1;
    }

    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "[state_io] Failed to open %s for reading\n", path);
        return -1;
    }

    /* Read and validate header */
    uint32_t magic = read_le32(f);
    uint32_t abi_version = read_le32(f);
    uint32_t state_version = read_le32(f);
    uint32_t state_size = read_le32(f);

    if (magic != CORTEX_STATE_MAGIC) {
        fprintf(stderr, "[state_io] Invalid magic number: 0x%08X (expected 0x%08X)\n",
                magic, CORTEX_STATE_MAGIC);
        fclose(f);
        return -1;
    }

    if (abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[state_io] ABI version mismatch: file has %u, harness expects %u\n",
                abi_version, CORTEX_ABI_VERSION);
        fclose(f);
        return -1;
    }

    if (state_size == 0 || state_size > CORTEX_MAX_STATE_SIZE) {
        fprintf(stderr, "[state_io] Invalid state size: %u bytes (max %d)\n",
                state_size, CORTEX_MAX_STATE_SIZE);
        fclose(f);
        return -1;
    }

    /* Allocate buffer for payload */
    void *payload = malloc(state_size);
    if (!payload) {
        fprintf(stderr, "[state_io] Failed to allocate %u bytes for state payload\n", state_size);
        fclose(f);
        return -1;
    }

    /* Read payload */
    size_t read_bytes = fread(payload, 1, state_size, f);
    fclose(f);

    if (read_bytes != state_size) {
        fprintf(stderr, "[state_io] Failed to read full payload (read %zu/%u bytes)\n",
                read_bytes, state_size);
        free(payload);
        return -1;
    }

    /* Success - return payload to caller */
    *out_payload = payload;
    *out_size = state_size;
    if (out_version) *out_version = state_version;

    fprintf(stderr, "[state_io] Loaded calibration state: %s (%u bytes, version %u)\n",
            path, state_size, state_version);
    return 0;
}

int cortex_state_validate(const char *path) {
    if (!path) return -1;

    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "[state_io] File not found: %s\n", path);
        return -1;
    }

    /* Read header only */
    uint32_t magic = read_le32(f);
    uint32_t abi_version = read_le32(f);
    uint32_t state_version = read_le32(f);
    uint32_t state_size = read_le32(f);
    fclose(f);

    if (magic != CORTEX_STATE_MAGIC) {
        fprintf(stderr, "[state_io] Invalid magic number\n");
        return -1;
    }

    if (abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[state_io] ABI version mismatch: %u vs %u\n",
                abi_version, CORTEX_ABI_VERSION);
        return -1;
    }

    if (state_size == 0 || state_size > 100 * 1024 * 1024) {
        fprintf(stderr, "[state_io] Invalid state size: %u\n", state_size);
        return -1;
    }

    fprintf(stderr, "[state_io] Valid state file: %s (%u bytes, version %u)\n",
            path, state_size, state_version);
    return 0;
}
