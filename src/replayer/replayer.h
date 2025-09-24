/*
 * Copyright (c) 2025 Weston Voglesonger
 *
 * Dataset replayer interface for the CORTEX benchmarking harness.
 *
 * This component streams samples from disk at a target sample rate and
 * forwards them to the scheduler for windowing.  It adheres to the design
 * principles outlined in docs/PLUGIN_INTERFACE.md and docs/RUN_CONFIG.md
 * by avoiding allocations within hot paths and exposing configuration via
 * simple C structs.
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
 * Callback signature invoked for each fully populated window.
 *
 * Parameters:
 *  - window_data: pointer to interleaved samples (W × C) in float32 format.
 *  - window_samples: number of samples in the window_data array.
 *  - user_data: opaque pointer forwarded from cortex_replayer_run().
 */
typedef void (*cortex_replayer_window_callback)(const float *window_data,
                                                size_t window_samples,
                                                void *user_data);

/*
 * Start the dataset replayer thread.
 *
 * Parameters:
 *  - config: runtime configuration; values are copied on entry.
 *  - callback: invoked for each window produced.
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
 * Record the desired background load profile.  The profile is interpreted when
 * starting stress-ng or other load generators (TODO).
 */
void cortex_replayer_set_load_profile(const char *profile_name);

/*
 * Start a background load generator (stub).  Intended to spawn stress-ng with
 * parameters derived from docs/RUN_CONFIG.md.  Returns 0 on success.
 */
int cortex_replayer_start_background_load(const char *profile_name);

/*
 * Stop the background load generator (stub).  TODO: actually terminate
 * stress-ng and clean up OS resources.
 */
void cortex_replayer_stop_background_load(void);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* CORTEX_HARNESS_REPLAYER_H */
