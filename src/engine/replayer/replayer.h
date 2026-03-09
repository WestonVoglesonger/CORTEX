/*
 * Copyright (c) 2025 Weston Voglesonger
 *
 * Dataset replayer interface for the CORTEX benchmarking harness.
 *
 * Minimal data source that delivers packets of packet_samples x C float32
 * values at real-time cadence (packet_samples/Fs seconds per emission).
 * The scheduler receives these packets and forms overlapping windows of
 * length W via its internal sliding buffer.
 *
 * INSTANCE-BASED DESIGN:
 * ----------------------
 * The replayer uses an instance-based API pattern with explicit lifecycle
 * management (create/start/stop/destroy). This design:
 * - Eliminates global state for replayer-specific configuration
 * - Enables clean test isolation (each test gets a fresh instance)
 * - Follows standard C idioms (FILE*, pthread_t, malloc/free)
 * - Allows re-entrancy and clean sequential execution
 *
 * TYPICAL USAGE:
 * --------------
 *   cortex_replayer_config_t cfg = { ... };
 *   cortex_replayer_t *replayer = cortex_replayer_create(&cfg);
 *
 *   // Start streaming
 *   cortex_replayer_start(replayer, my_callback, user_data);
 *
 *   // ... application runs ...
 *
 *   // Cleanup (automatically stops thread)
 *   cortex_replayer_destroy(replayer);
 *
 * STRING LIFETIME REQUIREMENTS:
 * -----------------------------
 * Configuration strings (dataset_path) are stored BY REFERENCE,
 * not copied. The caller MUST ensure these strings remain valid for the
 * lifetime of the replayer instance.
 */
#ifndef CORTEX_HARNESS_REPLAYER_H
#define CORTEX_HARNESS_REPLAYER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Opaque replayer instance. Encapsulates replayer-specific state including
 * configuration, thread handle, callbacks, and runtime flags.
 */
typedef struct cortex_replayer cortex_replayer_t;

/*
 * Replayer configuration. Callers must zero-initialize before use.
 */
typedef struct cortex_replayer_config {
    const char *dataset_path;    /* File path (NULL for future generation mode) */
    uint32_t sample_rate_hz;     /* Fs -- used to compute packet period */
    uint32_t channels;           /* C -- channel count */
    uint32_t packet_samples;     /* Samples per packet per channel */
} cortex_replayer_config_t;

/*
 * Callback signature invoked for each packet of samples.
 *
 * The replayer streams packets at real-time cadence (packet_samples/Fs seconds).
 * The scheduler receives these packets and forms overlapping windows internally.
 *
 * Parameters:
 *  - packet_data: pointer to interleaved float32 samples (packet_samples x C).
 *  - packet_samples: number of elements in the packet_data array (packet_samples x C).
 *  - user_data: opaque pointer forwarded from cortex_replayer_start().
 */
typedef void (*cortex_replayer_packet_callback)(const void *packet_data,
                                                size_t packet_samples,
                                                void *user_data);

/*
 * Create a new replayer instance with the given configuration.
 *
 * Allocates and initializes a replayer instance. The configuration struct is
 * copied internally, so the caller may free config after this call returns.
 * However, string pointers (dataset_path) are stored by reference
 * and must remain valid for the lifetime of the replayer instance.
 *
 * Parameters:
 *  - config: runtime configuration (struct copied, strings stored by reference).
 *
 * Returns:
 *  - Pointer to new replayer instance on success, NULL on failure (sets errno).
 */
cortex_replayer_t *cortex_replayer_create(const cortex_replayer_config_t *config);

/*
 * Start the dataset replayer thread.
 *
 * The replayer streams packets at the configured sample rate,
 * emulating real-time hardware data acquisition. The callback is invoked
 * every packet_samples/Fs seconds.
 *
 * Parameters:
 *  - replayer: replayer instance.
 *  - callback: invoked for each packet produced.
 *  - user_data: forwarded to the callback.
 *
 * Returns:
 *  - 0 on success, negative errno-style value on failure.
 */
int cortex_replayer_start(cortex_replayer_t *replayer,
                          cortex_replayer_packet_callback callback,
                          void *user_data);

/*
 * Request the replayer thread to stop and wait for completion.
 * Safe to call multiple times. Does not free the replayer instance.
 *
 * Parameters:
 *  - replayer: replayer instance.
 *
 * Returns:
 *  - 0 on success, negative errno-style value on failure.
 */
int cortex_replayer_stop(cortex_replayer_t *replayer);

/*
 * Destroy a replayer instance and free all resources.
 * Automatically stops the replayer thread if still running.
 * Safe to call with NULL.
 *
 * Parameters:
 *  - replayer: replayer instance to destroy (may be NULL).
 */
void cortex_replayer_destroy(cortex_replayer_t *replayer);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* CORTEX_HARNESS_REPLAYER_H */
