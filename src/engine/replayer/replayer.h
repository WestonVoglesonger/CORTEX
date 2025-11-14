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
 */
#ifndef CORTEX_HARNESS_REPLAYER_H
#define CORTEX_HARNESS_REPLAYER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

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
 * Start the dataset replayer thread.
 *
 * The replayer streams hop-sized chunks at the configured sample rate,
 * emulating real-time hardware data acquisition. The callback is invoked
 * every H/Fs seconds with H samples.
 *
 * Parameters:
 *  - config: runtime configuration; values are copied on entry.
 *  - callback: invoked for each chunk produced (typically H samples).
 *  - user_data: forwarded to the callback.
 *
 * Returns:
 *  - 0 on success, negative errno-style value on failure.
 */
int cortex_replayer_run(const cortex_replayer_config_t *config,
                        cortex_replayer_window_callback callback,
                        void *user_data);

/*
 * Request the replayer thread to stop and wait for completion.  Safe to call
 * multiple times.
 */
int cortex_replayer_stop(void);

/*
 * Enable or disable controlled dropouts/gaps.  The actual dropout behaviour is
 * currently implemented as a TODO stub in harness/src/replayer.c.
 */
void cortex_replayer_enable_dropouts(int enabled);

/*
 * Set the background load profile name for validation and logging.
 * Valid profiles: "idle" (no load), "medium" (50% CPU), "heavy" (90% CPU).
 * Invalid profiles default to "idle". This is informational only;
 * actual load is controlled by start_background_load().
 */
void cortex_replayer_set_load_profile(const char *profile_name);

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
 */
int cortex_replayer_start_background_load(const char *profile_name);

/*
 * Stop background load and terminate stress-ng process.
 *
 * Sends SIGTERM with 2-second grace period, then SIGKILL if needed.
 * Reaps zombie process with waitpid() to prevent resource leaks.
 * Safe to call multiple times or when no load is running.
 *
 * Thread safety: Must be called from main thread only.
 */
void cortex_replayer_stop_background_load(void);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* CORTEX_HARNESS_REPLAYER_H */
