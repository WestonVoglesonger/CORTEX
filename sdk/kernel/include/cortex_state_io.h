/*
 * Calibration State I/O Utilities (ABI v3)
 *
 * Handles serialization and deserialization of .cortex_state files containing
 * pre-trained kernel parameters (e.g., ICA unmixing matrices, CSP filters, LDA weights).
 *
 * File Format (.cortex_state):
 * ┌─────────────────────────────────────────────┐
 * │ Header (16 bytes)                           │
 * ├──────────────┬──────────────────────────────┤
 * │ Offset       │ Field                        │
 * ├──────────────┼──────────────────────────────┤
 * │ 0x00 (4B)    │ Magic: 0x434F5254 ("CORT")   │
 * │ 0x04 (4B)    │ ABI Version: 3               │
 * │ 0x08 (4B)    │ State Version (kernel-spec)  │
 * │ 0x0C (4B)    │ State Size (bytes)           │
 * ├──────────────┴──────────────────────────────┤
 * │ Payload (N bytes, kernel-specific)          │
 * └─────────────────────────────────────────────┘
 *
 * Endianness: Little-endian for all multi-byte fields
 */

#ifndef CORTEX_HARNESS_STATE_IO_H
#define CORTEX_HARNESS_STATE_IO_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Magic number for .cortex_state files (ASCII "CORT") */
#define CORTEX_STATE_MAGIC 0x434F5254u

/* Header structure for .cortex_state files */
typedef struct {
    uint32_t magic;          /* Must be CORTEX_STATE_MAGIC */
    uint32_t abi_version;    /* ABI version (currently 3) */
    uint32_t state_version;  /* Kernel-specific state version */
    uint32_t state_size;     /* Size of payload in bytes */
} cortex_state_header_t;

/*
 * Save calibration state to a .cortex_state file.
 *
 * Parameters:
 *   path:          Output file path
 *   state_payload: Kernel-specific calibration state (raw bytes)
 *   state_size:    Size of state_payload in bytes
 *   state_version: Kernel-specific version number (for evolution tracking)
 *
 * Returns:
 *   0 on success, -1 on failure (file I/O error)
 */
int cortex_state_save(const char *path,
                     const void *state_payload,
                     uint32_t state_size,
                     uint32_t state_version);

/*
 * Load calibration state from a .cortex_state file.
 *
 * Parameters:
 *   path:           Input file path
 *   out_payload:    Pointer to receive allocated state buffer (caller must free())
 *   out_size:       Pointer to receive state size in bytes
 *   out_version:    Pointer to receive state version (may be NULL)
 *
 * Returns:
 *   0 on success, -1 on failure (file not found, corruption, allocation failure)
 *
 * Notes:
 *   - Caller is responsible for freeing *out_payload via free()
 *   - Validates magic number and ABI version
 *   - Does NOT validate state_version (kernel-specific)
 */
int cortex_state_load(const char *path,
                     void **out_payload,
                     uint32_t *out_size,
                     uint32_t *out_version);

/*
 * Validate a .cortex_state file header without loading payload.
 *
 * Parameters:
 *   path: File path to validate
 *
 * Returns:
 *   0 if valid, -1 if invalid or corrupted
 */
int cortex_state_validate(const char *path);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* CORTEX_HARNESS_STATE_IO_H */
