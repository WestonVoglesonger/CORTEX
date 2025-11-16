/*
 * CORTEX benchmarking harness scheduler interface.
 *
 * The scheduler receives streams of interleaved samples from the dataset
 * replayer, forms overlapping windows of length W with hop H, and dispatches
 * those windows to each registered plugin.  All runtime parameters are derived
 * from docs/RUN_CONFIG.md and propagated via cortex_plugin_config_t defined in
 * include/cortex_plugin.h.
 */
#ifndef CORTEX_HARNESS_SCHEDULER_H
#define CORTEX_HARNESS_SCHEDULER_H

#include <stddef.h>
#include <stdint.h>

#include "cortex_plugin.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Scheduler configuration derived from the YAML run configuration.  The
 * structure is designed for forward compatibility; new fields should be
 * appended and callers must zero-initialize the struct before use.
 */
typedef struct cortex_scheduler_config {
    uint32_t sample_rate_hz;         /* Fs (Hz); see docs/RUN_CONFIG.md */
    uint32_t window_length_samples;  /* W (samples) */
    uint32_t hop_samples;            /* H (samples) */
    uint32_t channels;               /* C (channels) */
    uint32_t dtype;                  /* mirrors cortex_plugin_config_t::dtype */
    uint32_t warmup_seconds;         /* benchmark.parameters.warmup_seconds */
    uint32_t realtime_priority;      /* realtime.priority */
    uint64_t cpu_affinity_mask;      /* realtime.cpu_affinity bitmask */
    const char *scheduler_policy;    /* "fifo", "rr", or NULL for default */
    const char *telemetry_path;      /* optional path for CSV/JSON telemetry */
    void *telemetry_buffer;          /* optional buffer for metrics (cortex_telemetry_buffer_t *) */
    const char *run_id;              /* run identifier for telemetry records */
    uint32_t current_repeat;         /* which repeat iteration (0 = warmup, 1+ = measurement) */
} cortex_scheduler_config_t;

/* Opaque scheduler object. */
typedef struct cortex_scheduler_t cortex_scheduler_t;

/*
 * Wrapper around the plugin ABI entry points.  The harness will typically load
 * these functions from a shared object (dlopen/dlsym) and forward them here.
 */
typedef struct cortex_scheduler_plugin_api {
    cortex_init_result_t (*init)(const cortex_plugin_config_t *config);
    void (*process)(void *handle, const void *input, void *output);
    void (*teardown)(void *handle);
} cortex_scheduler_plugin_api_t;

/*
 * Create a scheduler instance with the provided configuration.  Returns NULL
 * on allocation failure or invalid parameters.
 */
cortex_scheduler_t *cortex_scheduler_create(const cortex_scheduler_config_t *config);

/*
 * Destroy a scheduler instance, tearing down any registered plugins and
 * releasing buffers.
 */
void cortex_scheduler_destroy(cortex_scheduler_t *scheduler);

/*
 * Register a plugin with the scheduler.  The scheduler copies the provided
 * cortex_plugin_config_t before calling init().  Returns 0 on success, negative
 * errno on failure.
 */
int cortex_scheduler_register_plugin(cortex_scheduler_t *scheduler,
                                     const cortex_scheduler_plugin_api_t *api,
                                     const cortex_plugin_config_t *plugin_config,
                                     const char *plugin_name);

/*
 * Feed interleaved samples (float32 frames of size C) into the scheduler.
 * Samples are queued until enough data is available to form a window.  The
 * function returns the number of frames consumed or a negative errno value.
 *
 * TODO: add support for Q15/Q7 datasets when dtype parsing is implemented in
 * the replayer.
 */
int cortex_scheduler_feed_samples(cortex_scheduler_t *scheduler,
                                  const float *samples,
                                  size_t sample_count);

/*
 * Force the scheduler to flush any buffered samples.  Typically used at the
 * end of a dataset replay to ensure trailing windows are processed.  Returns 0
 * on success.
 */
int cortex_scheduler_flush(cortex_scheduler_t *scheduler);

/*
 * Set telemetry buffer for the scheduler.  If provided, telemetry records will
 * be added to this buffer instead of (or in addition to) direct file output.
 */
void cortex_scheduler_set_telemetry_buffer(cortex_scheduler_t *scheduler, void *telemetry_buffer);

/*
 * Set run ID for telemetry records.
 */
void cortex_scheduler_set_run_id(cortex_scheduler_t *scheduler, const char *run_id);

/*
 * Set current repeat number for telemetry records.
 */
void cortex_scheduler_set_current_repeat(cortex_scheduler_t *scheduler, uint32_t repeat);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* CORTEX_HARNESS_SCHEDULER_H */
