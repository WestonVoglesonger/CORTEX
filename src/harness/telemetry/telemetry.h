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
} cortex_telemetry_record_t;

typedef struct cortex_telemetry_buffer {
    cortex_telemetry_record_t *records;
    size_t count;
    size_t capacity;
} cortex_telemetry_buffer_t;

int cortex_telemetry_init(cortex_telemetry_buffer_t *tb, size_t initial_capacity);
void cortex_telemetry_free(cortex_telemetry_buffer_t *tb);
int cortex_telemetry_add(cortex_telemetry_buffer_t *tb, const cortex_telemetry_record_t *rec);
int cortex_telemetry_write_csv(const char *path, const cortex_telemetry_buffer_t *tb);
int cortex_telemetry_write_csv_filtered(const char *path, const cortex_telemetry_buffer_t *tb, 
                                         size_t start_idx, size_t end_idx);

#endif /* CORTEX_HARNESS_TELEMETRY_H */




