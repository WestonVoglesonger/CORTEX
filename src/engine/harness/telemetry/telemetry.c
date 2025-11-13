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
    fprintf(f, "run_id,plugin,window_index,release_ts_ns,deadline_ts_ns,start_ts_ns,end_ts_ns,deadline_missed,W,H,C,Fs,warmup,repeat,flops_per_window,bytes_per_window\n");
    for (size_t i = 0; i < tb->count; i++) {
        const cortex_telemetry_record_t *r = &tb->records[i];
        fprintf(f, "%s,%s,%u,%llu,%llu,%llu,%llu,%u,%u,%u,%u,%u,%u,%u,%llu,%llu\n",
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
                r->repeat,
                (unsigned long long)r->flops_per_window,
                (unsigned long long)r->bytes_per_window);
    }
    fclose(f);
    return 0;
}

int cortex_telemetry_write_csv_filtered(const char *path, const cortex_telemetry_buffer_t *tb,
                                         size_t start_idx, size_t end_idx) {
    if (!path || !tb) return -1;
    if (start_idx > end_idx || end_idx > tb->count) return -1;

    /* Create parent directories */
    if (cortex_create_directories(path) != 0) {
        return -1;
    }

    FILE *f = fopen(path, "w");
    if (!f) return -1;
    fprintf(f, "run_id,plugin,window_index,release_ts_ns,deadline_ts_ns,start_ts_ns,end_ts_ns,deadline_missed,W,H,C,Fs,warmup,repeat,flops_per_window,bytes_per_window\n");
    for (size_t i = start_idx; i < end_idx; i++) {
        const cortex_telemetry_record_t *r = &tb->records[i];
        fprintf(f, "%s,%s,%u,%llu,%llu,%llu,%llu,%u,%u,%u,%u,%u,%u,%u,%llu,%llu\n",
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
                r->repeat,
                (unsigned long long)r->flops_per_window,
                (unsigned long long)r->bytes_per_window);
    }
    fclose(f);
    return 0;
}

/* Helper: Escape JSON string characters (", \, control chars) */
static void json_escape_string(char *dest, size_t dest_size, const char *src) {
    size_t j = 0;
    for (size_t i = 0; src[i] && j < dest_size - 2; i++) {
        if (src[i] == '"' || src[i] == '\\') {
            if (j < dest_size - 3) {
                dest[j++] = '\\';
                dest[j++] = src[i];
            }
        } else if (src[i] == '\n') {
            if (j < dest_size - 3) {
                dest[j++] = '\\';
                dest[j++] = 'n';
            }
        } else if (src[i] == '\r') {
            if (j < dest_size - 3) {
                dest[j++] = '\\';
                dest[j++] = 'r';
            }
        } else if (src[i] == '\t') {
            if (j < dest_size - 3) {
                dest[j++] = '\\';
                dest[j++] = 't';
            }
        } else if ((unsigned char)src[i] < 32) {
            /* Skip other control characters */
            continue;
        } else {
            dest[j++] = src[i];
        }
    }
    dest[j] = '\0';
}

int cortex_telemetry_write_ndjson(const char *path, const cortex_telemetry_buffer_t *tb) {
    if (!path || !tb) return -1;

    /* Create parent directories */
    if (cortex_create_directories(path) != 0) {
        return -1;
    }

    FILE *f = fopen(path, "w");
    if (!f) return -1;

    char run_id_esc[128], plugin_esc[256];

    /* Write each record as one JSON object per line (NDJSON format) */
    for (size_t i = 0; i < tb->count; i++) {
        const cortex_telemetry_record_t *r = &tb->records[i];

        /* Escape string fields for JSON */
        json_escape_string(run_id_esc, sizeof(run_id_esc), r->run_id);
        json_escape_string(plugin_esc, sizeof(plugin_esc), r->plugin_name);

        /* Write JSON object (compact, one line per record) */
        fprintf(f,
            "{\"run_id\":\"%s\","
            "\"plugin\":\"%s\","
            "\"window_index\":%u,"
            "\"release_ts_ns\":%llu,"
            "\"deadline_ts_ns\":%llu,"
            "\"start_ts_ns\":%llu,"
            "\"end_ts_ns\":%llu,"
            "\"deadline_missed\":%u,"
            "\"W\":%u,"
            "\"H\":%u,"
            "\"C\":%u,"
            "\"Fs\":%u,"
            "\"warmup\":%u,"
            "\"repeat\":%u,"
            "\"flops_per_window\":%llu,"
            "\"bytes_per_window\":%llu}\n",
            run_id_esc,
            plugin_esc,
            r->window_index,
            (unsigned long long)r->release_ts_ns,
            (unsigned long long)r->deadline_ts_ns,
            (unsigned long long)r->start_ts_ns,
            (unsigned long long)r->end_ts_ns,
            (unsigned)r->deadline_missed,
            r->W, r->H, r->C, r->Fs,
            (unsigned)r->warmup,
            r->repeat,
            (unsigned long long)r->flops_per_window,
            (unsigned long long)r->bytes_per_window);
    }

    fclose(f);
    return 0;
}

int cortex_telemetry_write_ndjson_filtered(const char *path, const cortex_telemetry_buffer_t *tb,
                                            size_t start_idx, size_t end_idx) {
    if (!path || !tb) return -1;
    if (start_idx > end_idx || end_idx > tb->count) return -1;

    /* Create parent directories */
    if (cortex_create_directories(path) != 0) {
        return -1;
    }

    FILE *f = fopen(path, "w");
    if (!f) return -1;

    char run_id_esc[128], plugin_esc[256];

    /* Write only records in range [start_idx, end_idx) */
    for (size_t i = start_idx; i < end_idx; i++) {
        const cortex_telemetry_record_t *r = &tb->records[i];

        /* Escape string fields for JSON */
        json_escape_string(run_id_esc, sizeof(run_id_esc), r->run_id);
        json_escape_string(plugin_esc, sizeof(plugin_esc), r->plugin_name);

        /* Write JSON object (compact, one line per record) */
        fprintf(f,
            "{\"run_id\":\"%s\","
            "\"plugin\":\"%s\","
            "\"window_index\":%u,"
            "\"release_ts_ns\":%llu,"
            "\"deadline_ts_ns\":%llu,"
            "\"start_ts_ns\":%llu,"
            "\"end_ts_ns\":%llu,"
            "\"deadline_missed\":%u,"
            "\"W\":%u,"
            "\"H\":%u,"
            "\"C\":%u,"
            "\"Fs\":%u,"
            "\"warmup\":%u,"
            "\"repeat\":%u,"
            "\"flops_per_window\":%llu,"
            "\"bytes_per_window\":%llu}\n",
            run_id_esc,
            plugin_esc,
            r->window_index,
            (unsigned long long)r->release_ts_ns,
            (unsigned long long)r->deadline_ts_ns,
            (unsigned long long)r->start_ts_ns,
            (unsigned long long)r->end_ts_ns,
            (unsigned)r->deadline_missed,
            r->W, r->H, r->C, r->Fs,
            (unsigned)r->warmup,
            r->repeat,
            (unsigned long long)r->flops_per_window,
            (unsigned long long)r->bytes_per_window);
    }

    fclose(f);
    return 0;
}


