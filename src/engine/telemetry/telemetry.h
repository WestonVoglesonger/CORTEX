/* Basic telemetry record and CSV writer (Week 3 scope) */

#ifndef CORTEX_HARNESS_TELEMETRY_H
#define CORTEX_HARNESS_TELEMETRY_H

#include <stddef.h>
#include <stdint.h>

typedef struct cortex_telemetry_record {
    char run_id[32];
    char plugin_name[64];
    uint32_t window_index;
    uint64_t release_ts_ns;
    uint64_t deadline_ts_ns;
    uint64_t start_ts_ns;
    uint64_t end_ts_ns;
    uint8_t deadline_missed;
    uint32_t W, H, C, Fs;
    uint8_t warmup;
    uint32_t repeat;

    /* Device-side timing (0 if direct execution, populated if adapter used) */
    uint64_t device_tin_ns;       /* Input complete timestamp (device clock) */
    uint64_t device_tstart_ns;    /* Kernel start (device clock) */
    uint64_t device_tend_ns;      /* Kernel end (device clock) */
    uint64_t device_tfirst_tx_ns; /* First result byte transmitted (device clock) */
    uint64_t device_tlast_tx_ns;  /* Last result byte transmitted (device clock) */
    char adapter_name[32];        /* Adapter identifier (e.g., "native@loopback") */

    /* Error tracking (distinguish transport failures from deadline misses) */
    uint8_t window_failed;        /* 1 = transport/adapter failure, 0 = success */
    int32_t error_code;           /* Error reason if window_failed=1 (cortex_error_code_t) */
} cortex_telemetry_record_t;

typedef struct cortex_telemetry_buffer {
    cortex_telemetry_record_t *records;
    size_t count;
    size_t capacity;
} cortex_telemetry_buffer_t;

/* System information for reproducibility tracking */
typedef struct cortex_system_info {
    char os[64];             /* OS name (e.g., "Darwin 23.2.0", "Linux 6.5.0") */
    char cpu_model[128];     /* CPU model string */
    char hostname[64];       /* Machine hostname */
    uint64_t total_ram_mb;   /* Total system RAM in MB */
    uint32_t cpu_count;      /* Number of CPU cores */
    float thermal_celsius;   /* Current thermal reading (-1.0 if unavailable) */
} cortex_system_info_t;

/* Collect system information for telemetry metadata */
int cortex_collect_system_info(cortex_system_info_t *info);

int cortex_telemetry_init(cortex_telemetry_buffer_t *tb, size_t initial_capacity);
void cortex_telemetry_free(cortex_telemetry_buffer_t *tb);
int cortex_telemetry_add(cortex_telemetry_buffer_t *tb, const cortex_telemetry_record_t *rec);
int cortex_telemetry_write_csv(const char *path, const cortex_telemetry_buffer_t *tb,
                                 const cortex_system_info_t *sysinfo);
int cortex_telemetry_write_csv_filtered(const char *path, const cortex_telemetry_buffer_t *tb,
                                         size_t start_idx, size_t end_idx,
                                         const cortex_system_info_t *sysinfo);

/* NDJSON (Newline-Delimited JSON) output format */
int cortex_telemetry_write_ndjson(const char *path, const cortex_telemetry_buffer_t *tb,
                                    const cortex_system_info_t *sysinfo);
int cortex_telemetry_write_ndjson_filtered(const char *path, const cortex_telemetry_buffer_t *tb,
                                            size_t start_idx, size_t end_idx,
                                            const cortex_system_info_t *sysinfo);

#endif /* CORTEX_HARNESS_TELEMETRY_H */




