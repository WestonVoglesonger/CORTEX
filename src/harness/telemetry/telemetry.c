#include "telemetry.h"
#include "../util/util.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int cortex_telemetry_init(cortex_telemetry_buffer_t *tb, size_t initial_capacity) {
    if (!tb) return -1;
    memset(tb, 0, sizeof(*tb));
    if (initial_capacity == 0) initial_capacity = 1024;
    tb->records = (cortex_telemetry_record_t *)calloc(initial_capacity, sizeof(*tb->records));
    if (!tb->records) return -1;
    tb->capacity = initial_capacity;
    tb->count = 0;
    return 0;
}

void cortex_telemetry_free(cortex_telemetry_buffer_t *tb) {
    if (!tb) return;
    free(tb->records);
    memset(tb, 0, sizeof(*tb));
}

int cortex_telemetry_add(cortex_telemetry_buffer_t *tb, const cortex_telemetry_record_t *rec) {
    if (!tb || !rec) return -1;
    if (tb->count >= tb->capacity) {
        size_t new_cap = tb->capacity * 2;
        cortex_telemetry_record_t *new_recs = (cortex_telemetry_record_t *)realloc(tb->records, new_cap * sizeof(*new_recs));
        if (!new_recs) return -1;
        tb->records = new_recs;
        tb->capacity = new_cap;
    }
    tb->records[tb->count++] = *rec;
    return 0;
}

int cortex_telemetry_write_csv(const char *path, const cortex_telemetry_buffer_t *tb) {
    if (!path || !tb) return -1;

    /* Create parent directories */
    if (cortex_create_directories(path) != 0) {
        return -1;
    }

    FILE *f = fopen(path, "w");
    if (!f) return -1;
    fprintf(f, "run_id,plugin,window_index,release_ts_ns,deadline_ts_ns,start_ts_ns,end_ts_ns,deadline_missed,W,H,C,Fs,warmup,repeat\n");
    for (size_t i = 0; i < tb->count; i++) {
        const cortex_telemetry_record_t *r = &tb->records[i];
        fprintf(f, "%s,%s,%u,%llu,%llu,%llu,%llu,%u,%u,%u,%u,%u,%u,%u\n",
                r->run_id,
                r->plugin_name,
                r->window_index,
                (unsigned long long)r->release_ts_ns,
                (unsigned long long)r->deadline_ts_ns,
                (unsigned long long)r->start_ts_ns,
                (unsigned long long)r->end_ts_ns,
                (unsigned)r->deadline_missed,
                r->W, r->H, r->C, r->Fs,
                (unsigned)r->warmup,
                r->repeat);
    }
    fclose(f);
    return 0;
}




