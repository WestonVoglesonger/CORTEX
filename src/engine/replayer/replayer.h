/*
 * Copyright (c) 2025 Weston Voglesonger
 *
 * Dataset replayer interface for the CORTEX benchmarking harness.
 *
 * This component streams hop-sized chunks of samples from disk at the target
 * sample rate (H samples every H/Fs seconds), emulating hardware data acquisition.
 * The scheduler receives these chunks and forms overlapping windows of length W
 * via its internal sliding buffer. This design adheres to the principles outlined
 * in docs/PLUGIN_INTERFACE.md and docs/RUN_CONFIG.md by maintaining clear
 * separation of concerns: replayer = data source, scheduler = windowing logic.
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
 *   // Optionally start background load (system-wide resource)
 *   cortex_replayer_start_background_load(replayer, "heavy");
 *
 *   // Start streaming
 *   cortex_replayer_start(replayer, my_callback, user_data);
 *
 *   // ... application runs ...
 *
 *   // Cleanup (automatically stops thread and background load if owner)
 *   cortex_replayer_destroy(replayer);
 *
 * BACKGROUND LOAD (SYSTEM-WIDE RESOURCE):
 * ----------------------------------------
 * Background CPU load (stress-ng) is a GLOBAL system-wide resource shared
 * across all replayer instances:
 * - Only ONE stress-ng process can run at a time (singleton)
 * - Ownership tracking prevents cross-instance interference
 * - Only the instance that started the load can stop it
 * - destroy() safely stops load only if the instance owns it
 *
 * Example with multiple instances:
 *   cortex_replayer_t *r1 = cortex_replayer_create(&cfg);
 *   cortex_replayer_start_background_load(r1, "heavy");  // r1 owns load
 *
 *   cortex_replayer_t *r2 = cortex_replayer_create(&cfg);
 *   cortex_replayer_destroy(r2);  // Does NOT stop r1's background load
 *
 *   cortex_replayer_destroy(r1);  // Stops background load (owner)
 *
 * STRING LIFETIME REQUIREMENTS:
 * -----------------------------
 * Configuration strings (dataset_path, load_profile) are stored BY REFERENCE,
 * not copied. The caller MUST ensure these strings remain valid for the
 * lifetime of the replayer instance:
 *
 *   // GOOD - static string
 *   cfg.dataset_path = "/path/to/data.bin";
 *   replayer = cortex_replayer_create(&cfg);
 *
 *   // GOOD - long-lived allocation
 *   char *path = strdup("/path/to/data.bin");
 *   cfg.dataset_path = path;
 *   replayer = cortex_replayer_create(&cfg);
 *   // ... use replayer ...
 *   cortex_replayer_destroy(replayer);
 *   free(path);  // OK - freed after replayer destroyed
 *
 *   // BAD - stack-allocated string goes out of scope
 *   {
 *       char path[256];
 *       snprintf(path, sizeof(path), "/tmp/data.bin");
 *       cfg.dataset_path = path;
 *       replayer = cortex_replayer_create(&cfg);
 *   }  // path goes out of scope - UNDEFINED BEHAVIOR
 *   cortex_replayer_start(replayer, ...);  // Crash!
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
 *
 * Note: Background load (stress-ng) is a global system-wide resource, not
 * per-instance. See header comments for ownership tracking details.
 */
typedef struct cortex_replayer cortex_replayer_t;

/*
 * Runtime parameters sourced from docs/RUN_CONFIG.md.  Callers must
 * zero-initialize this struct before use.  New fields should always be
 * appended to preserve forward compatibility.
 */
typedef struct cortex_replayer_config {
    const char *dataset_path;
    uint32_t sample_rate_hz;
    uint32_t channels;
    uint32_t dtype; /* maps to cortex_dtype_bitmask_t; currently expect float32 */
    uint32_t window_length_samples;
    uint32_t hop_samples;
    uint8_t enable_dropouts;
    uint8_t reserved[3];
    const char *load_profile; /* "idle", "medium", "heavy" per docs/RUN_CONFIG.md */
} cortex_replayer_config_t;

/*
 * Callback signature invoked for each chunk of samples.
 *
 * The replayer streams hop-sized chunks (H samples) at real-time cadence.
 * The scheduler receives these chunks and forms overlapping windows internally.
 *
 * Parameters:
 *  - chunk_data: pointer to interleaved samples (H × C) in float32 format.
 *  - chunk_samples: number of samples in the chunk_data array (typically H × C).
 *  - user_data: opaque pointer forwarded from cortex_replayer_run().
 */
typedef void (*cortex_replayer_window_callback)(const float *chunk_data,
                                                size_t chunk_samples,
                                                void *user_data);

/*
 * Create a new replayer instance with the given configuration.
 *
 * Allocates and initializes a replayer instance. The configuration struct is
 * copied internally, so the caller may free config after this call returns.
 * However, string pointers (dataset_path, load_profile) are stored by reference
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
 * The replayer streams hop-sized chunks at the configured sample rate,
 * emulating real-time hardware data acquisition. The callback is invoked
 * every H/Fs seconds with H samples.
 *
 * Parameters:
 *  - replayer: replayer instance.
 *  - callback: invoked for each chunk produced (typically H samples).
 *  - user_data: forwarded to the callback.
 *
 * Returns:
 *  - 0 on success, negative errno-style value on failure.
 */
int cortex_replayer_start(cortex_replayer_t *replayer,
                          cortex_replayer_window_callback callback,
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

/*
 * Enable or disable controlled dropouts/gaps.
 * The actual dropout behaviour is currently implemented as a TODO stub.
 *
 * Parameters:
 *  - replayer: replayer instance.
 *  - enabled: 1 to enable dropouts, 0 to disable.
 */
void cortex_replayer_enable_dropouts(cortex_replayer_t *replayer, int enabled);

/*
 * Set the background load profile name for validation and logging.
 * Valid profiles: "idle" (no load), "medium" (50% CPU), "heavy" (90% CPU).
 * Invalid profiles default to "idle". This is informational only;
 * actual load is controlled by start_background_load().
 *
 * Parameters:
 *  - replayer: replayer instance.
 *  - profile_name: profile name ("idle", "medium", or "heavy").
 */
void cortex_replayer_set_load_profile(cortex_replayer_t *replayer, const char *profile_name);

/*
 * Start background system load using stress-ng.
 *
 * Spawns stress-ng process with CPU workers based on profile:
 *   - "idle":   No load (returns success without spawning)
 *   - "medium": N/2 CPU workers at 50% load
 *   - "heavy":  N CPU workers at 90% load
 *
 * Returns 0 on success, -1 if already running or fork fails.
 * Gracefully falls back to idle if stress-ng not found in PATH.
 * Thread safety: Must be called from main thread only.
 *
 * Parameters:
 *  - replayer: replayer instance.
 *  - profile_name: profile name ("idle", "medium", or "heavy").
 *
 * Returns:
 *  - 0 on success, negative value on failure.
 */
int cortex_replayer_start_background_load(cortex_replayer_t *replayer, const char *profile_name);

/*
 * Stop background load and terminate stress-ng process.
 *
 * Sends SIGTERM with 2-second grace period, then SIGKILL if needed.
 * Reaps zombie process with waitpid() to prevent resource leaks.
 * Safe to call multiple times or when no load is running.
 *
 * Thread safety: Must be called from main thread only.
 *
 * Parameters:
 *  - replayer: replayer instance.
 */
void cortex_replayer_stop_background_load(cortex_replayer_t *replayer);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* CORTEX_HARNESS_REPLAYER_H */
