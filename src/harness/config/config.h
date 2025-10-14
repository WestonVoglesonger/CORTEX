/*
 * Harness configuration loader for CORTEX.
 * Minimal YAML reader tailored to configs/cortex.yaml structure.
 */

#ifndef CORTEX_HARNESS_CONFIG_H
#define CORTEX_HARNESS_CONFIG_H

#include <stddef.h>
#include <stdint.h>

#define CORTEX_MAX_PLUGINS 16

typedef struct cortex_plugin_runtime_cfg {
    uint32_t window_length_samples;  /* W */
    uint32_t hop_samples;            /* H */
    uint32_t channels;               /* C */
    uint32_t dtype;                  /* maps to cortex_dtype_bitmask_t */
    uint8_t allow_in_place;          /* 0/1 */
} cortex_plugin_runtime_cfg_t;

typedef struct cortex_plugin_entry_cfg {
    char name[64];
    char status[16];
    char spec_uri[256];
    char spec_version[32];
    cortex_plugin_runtime_cfg_t runtime;
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
    char format[16];      /* "csv" or "json" (csv used for week 3) */
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
} cortex_run_config_t;

/* Load config from YAML-like file. Returns 0 on success. */
int cortex_config_load(const char *path, cortex_run_config_t *out);

/* Validate required invariants; returns 0 on success, -1 on error. */
int cortex_config_validate(const cortex_run_config_t *cfg, char *err, size_t err_sz);

#endif /* CORTEX_HARNESS_CONFIG_H */




