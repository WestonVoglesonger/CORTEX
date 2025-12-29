/*
 * Harness configuration loader for CORTEX.
 * Minimal YAML reader tailored to primitives/configs/cortex.yaml structure.
 */

#ifndef CORTEX_HARNESS_CONFIG_H
#define CORTEX_HARNESS_CONFIG_H

#include <stddef.h>
#include <stdint.h>

#define CORTEX_MAX_PLUGINS 16

typedef struct cortex_plugin_runtime_cfg {
    uint32_t window_length_samples;         /* Input W */
    uint32_t hop_samples;                   /* H */
    uint32_t channels;                      /* Input C */
    uint32_t dtype;                         /* maps to cortex_dtype_bitmask_t */
    uint8_t allow_in_place;                 /* 0/1 */
    uint32_t output_window_length_samples;  /* Output W (from spec.yaml or ACK override) */
    uint32_t output_channels;               /* Output C (from spec.yaml or ACK override) */
} cortex_plugin_runtime_cfg_t;

typedef struct cortex_plugin_entry_cfg {
    char name[64];
    char status[16];
    char spec_uri[256];
    char spec_version[32];
    cortex_plugin_runtime_cfg_t runtime;
    /* Kernel-specific parameters (optional) */
    char params[1024];                 /* JSON-like string for kernel params */
    char calibration_state[512];       /* Path to .cortex_state file (v3 trainable kernels) */
    char adapter_path[256];            /* Path to adapter binary (defaults to x86@loopback) */
} cortex_plugin_entry_cfg_t;

typedef struct cortex_dataset_cfg {
    char path[512];
    char format[32];
    uint32_t channels;
    uint32_t sample_rate_hz;
} cortex_dataset_cfg_t;

typedef struct cortex_realtime_cfg {
    char scheduler[16];    /* "fifo", "rr", "deadline", "other" */
    int priority;          /* 1-99 for FIFO/RR */
    uint64_t cpu_affinity_mask; /* bitmask of cores */
    uint32_t deadline_ms;  /* nominal window deadline */
} cortex_realtime_cfg_t;

typedef struct cortex_benchmark_params {
    uint32_t duration_seconds;
    uint32_t repeats;
    uint32_t warmup_seconds;
} cortex_benchmark_params_t;

typedef struct cortex_benchmark_cfg {
    char load_profile[16]; /* "idle", "medium", "heavy" */
    cortex_benchmark_params_t parameters;
} cortex_benchmark_cfg_t;

typedef struct cortex_output_cfg {
    char directory[512];
    char format[16];      /* "ndjson" (default) or "csv" */
    int include_raw_data; /* bool */
} cortex_output_cfg_t;

typedef struct cortex_run_config {
    int cortex_version;
    cortex_dataset_cfg_t dataset;
    cortex_realtime_cfg_t realtime;
    cortex_benchmark_cfg_t benchmark;
    cortex_output_cfg_t output;
    cortex_plugin_entry_cfg_t plugins[CORTEX_MAX_PLUGINS];
    size_t plugin_count;
    int auto_detect_kernels;  /* 1 if no plugins: section in YAML, 0 otherwise */
} cortex_run_config_t;

/* Load kernel spec from spec.yaml. Returns 0 on success. */
int cortex_load_kernel_spec(const char *spec_uri, uint32_t dataset_channels, cortex_plugin_runtime_cfg_t *runtime);

/* Load config from YAML-like file. Returns 0 on success. */
int cortex_config_load(const char *path, cortex_run_config_t *out);

/* Validate required invariants; returns 0 on success, -1 on error. */
int cortex_config_validate(const cortex_run_config_t *cfg, char *err, size_t err_sz);

/* Auto-detect and populate built kernels. Returns number of kernels found, -1 on error. */
int cortex_discover_kernels(cortex_run_config_t *cfg);

/**
 * Apply kernel filter from environment variable.
 * Filters the plugin list to only include specified kernels.
 * Works on ANY plugin source (discovery OR explicit config).
 *
 * @param cfg Run configuration with plugins array
 * @param filter Comma-separated kernel names (e.g., "goertzel,car")
 * @return 0 on success, -1 on error (zero kernels after filtering)
 */
int cortex_apply_kernel_filter(cortex_run_config_t *cfg, const char *filter);

#endif /* CORTEX_HARNESS_CONFIG_H */




