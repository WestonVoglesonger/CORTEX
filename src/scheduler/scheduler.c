#ifdef __linux__
#define _GNU_SOURCE
#endif

#include "scheduler.h"

#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef __linux__
#include <sched.h>
#endif

#ifdef __APPLE__
#include <mach/mach_time.h>
#endif

#define NSEC_PER_SEC 1000000000LL

typedef struct cortex_scheduler_plugin_entry {
    cortex_scheduler_plugin_api_t api;
    cortex_plugin_info_t info;
    void *handle;
    void *output_buffer;
    size_t output_bytes;
    void *config_blob;
    size_t config_size;
} cortex_scheduler_plugin_entry_t;

struct cortex_scheduler_t {
    cortex_scheduler_config_t config;
    float *buffer;
    size_t buffer_capacity;
    size_t buffer_fill;
    size_t window_samples;
    size_t hop_samples;

    cortex_scheduler_plugin_entry_t *plugins;
    size_t plugin_count;
    size_t plugin_capacity;

    uint64_t window_count;
    uint64_t warmup_windows_remaining;
    int realtime_applied;

    /* Telemetry CSV (Week 3 basic) */
    FILE *telemetry_file;
    int telemetry_header_written;
};

static int ensure_plugin_capacity(cortex_scheduler_t *scheduler);
static int apply_realtime_attributes(cortex_scheduler_t *scheduler);
static void normalize_timespec(struct timespec *ts);
static void timespec_add_seconds(struct timespec *ts, double seconds);
static void dispatch_window(cortex_scheduler_t *scheduler, const float *window_data);
static void record_window_metrics(const cortex_scheduler_t *scheduler,
                                  const cortex_scheduler_plugin_entry_t *plugin,
                                  const struct timespec *release_ts,
                                  const struct timespec *deadline_ts,
                                  const struct timespec *start_ts,
                                  const struct timespec *end_ts,
                                  int deadline_missed);
static void teardown_plugin(cortex_scheduler_plugin_entry_t *entry);

cortex_scheduler_t *cortex_scheduler_create(const cortex_scheduler_config_t *config) {
    if (!config) {
        errno = EINVAL;
        return NULL;
    }

    cortex_scheduler_t *scheduler = calloc(1, sizeof(*scheduler));
    if (!scheduler) {
        return NULL;
    }

    scheduler->config = *config;

    scheduler->window_samples = (size_t)config->window_length_samples * config->channels;
    scheduler->hop_samples = (size_t)config->hop_samples * config->channels;
    scheduler->buffer_capacity = scheduler->window_samples;
    scheduler->buffer = calloc(scheduler->buffer_capacity, sizeof(float));
    if (!scheduler->buffer) {
        free(scheduler);
        return NULL;
    }

    scheduler->plugin_capacity = 4;
    scheduler->plugins = calloc(scheduler->plugin_capacity, sizeof(*scheduler->plugins));
    if (!scheduler->plugins) {
        free(scheduler->buffer);
        free(scheduler);
        return NULL;
    }

    if (scheduler->config.warmup_seconds > 0 && scheduler->config.sample_rate_hz > 0 && scheduler->config.hop_samples > 0) {
        const uint64_t frames_per_second = scheduler->config.sample_rate_hz;
        const uint64_t frames_per_window = scheduler->config.hop_samples;
        scheduler->warmup_windows_remaining = (scheduler->config.warmup_seconds * frames_per_second) / frames_per_window;
    }

    /* Open telemetry CSV if requested. */
    scheduler->telemetry_file = NULL;
    scheduler->telemetry_header_written = 0;
    if (config->telemetry_path && config->telemetry_path[0] != '\0') {
        scheduler->telemetry_file = fopen(config->telemetry_path, "w");
        if (!scheduler->telemetry_file) {
            fprintf(stderr, "[scheduler] warning: failed to open telemetry file '%s'\n", config->telemetry_path);
        }
    }

    return scheduler;
}

void cortex_scheduler_destroy(cortex_scheduler_t *scheduler) {
    if (!scheduler) {
        return;
    }

    for (size_t i = 0; i < scheduler->plugin_count; ++i) {
        teardown_plugin(&scheduler->plugins[i]);
    }

    free(scheduler->plugins);
    free(scheduler->buffer);
    if (scheduler->telemetry_file) {
        fclose(scheduler->telemetry_file);
        scheduler->telemetry_file = NULL;
    }
    free(scheduler);
}

int cortex_scheduler_register_plugin(cortex_scheduler_t *scheduler,
                                     const cortex_scheduler_plugin_api_t *api,
                                     const cortex_plugin_config_t *plugin_config) {
    if (!scheduler || !api || !api->init || !api->process || !api->teardown || !api->get_info || !plugin_config) {
        return -EINVAL;
    }

    if (ensure_plugin_capacity(scheduler) != 0) {
        return -ENOMEM;
    }

    cortex_scheduler_plugin_entry_t *entry = &scheduler->plugins[scheduler->plugin_count];
    memset(entry, 0, sizeof(*entry));

    entry->api = *api;
    entry->info = entry->api.get_info();

    if (!(entry->info.supported_dtypes & plugin_config->dtype)) {
        fprintf(stderr, "[scheduler] plugin '%s' missing requested dtype support\n",
                entry->info.name ? entry->info.name : "(unnamed)");
        return -EINVAL;
    }

    entry->config_size = plugin_config->struct_size;
    entry->config_blob = calloc(1, entry->config_size);
    if (!entry->config_blob) {
        return -ENOMEM;
    }
    memcpy(entry->config_blob, plugin_config, entry->config_size);

    entry->handle = entry->api.init((const cortex_plugin_config_t *)entry->config_blob);
    if (!entry->handle) {
        fprintf(stderr, "[scheduler] plugin '%s' failed init()\n",
                entry->info.name ? entry->info.name : "(unnamed)");
        free(entry->config_blob);
        entry->config_blob = NULL;
        return -EINVAL;
    }

    const uint32_t out_w = entry->info.output_window_length_samples ?
                           entry->info.output_window_length_samples : scheduler->config.window_length_samples;
    const uint32_t out_c = entry->info.output_channels ?
                           entry->info.output_channels : scheduler->config.channels;
    const size_t element_size = sizeof(float); /* TODO: support Q15/Q7 */
    entry->output_bytes = (size_t)out_w * out_c * element_size;
    entry->output_buffer = calloc(1, entry->output_bytes);
    if (!entry->output_buffer) {
        entry->api.teardown(entry->handle);
        free(entry->config_blob);
        entry->config_blob = NULL;
        entry->handle = NULL;
        return -ENOMEM;
    }

    scheduler->plugin_count += 1;
    return 0;
}

int cortex_scheduler_feed_samples(cortex_scheduler_t *scheduler,
                                  const float *samples,
                                  size_t sample_count) {
    if (!scheduler || !samples) {
        return -EINVAL;
    }

    if (!scheduler->realtime_applied) {
        if (apply_realtime_attributes(scheduler) == 0) {
            scheduler->realtime_applied = 1;
        }
    }

    size_t consumed = 0;
    while (consumed < sample_count) {
        size_t space = scheduler->buffer_capacity - scheduler->buffer_fill;
        if (space == 0) {
            fprintf(stderr, "[scheduler] buffer overflow risk; dropping samples\n");
            break;
        }
        size_t to_copy = sample_count - consumed;
        if (to_copy > space) {
            to_copy = space;
        }
        memcpy(scheduler->buffer + scheduler->buffer_fill, samples + consumed, to_copy * sizeof(float));
        scheduler->buffer_fill += to_copy;
        consumed += to_copy;

        while (scheduler->buffer_fill >= scheduler->window_samples && scheduler->hop_samples > 0) {
            dispatch_window(scheduler, scheduler->buffer);
            size_t remaining = scheduler->buffer_fill - scheduler->hop_samples;
            memmove(scheduler->buffer, scheduler->buffer + scheduler->hop_samples, remaining * sizeof(float));
            scheduler->buffer_fill = remaining;
        }
    }

    return (int)consumed;
}

int cortex_scheduler_flush(cortex_scheduler_t *scheduler) {
    if (!scheduler) {
        return -EINVAL;
    }

    while (scheduler->buffer_fill >= scheduler->window_samples && scheduler->hop_samples > 0) {
        dispatch_window(scheduler, scheduler->buffer);
        size_t remaining = scheduler->buffer_fill - scheduler->hop_samples;
        memmove(scheduler->buffer, scheduler->buffer + scheduler->hop_samples, remaining * sizeof(float));
        scheduler->buffer_fill = remaining;
    }
    return 0;
}

static int ensure_plugin_capacity(cortex_scheduler_t *scheduler) {
    if (scheduler->plugin_count < scheduler->plugin_capacity) {
        return 0;
    }

    size_t new_capacity = scheduler->plugin_capacity * 2;
    cortex_scheduler_plugin_entry_t *new_entries = realloc(scheduler->plugins, new_capacity * sizeof(*new_entries));
    if (!new_entries) {
        return -1;
    }
    memset(new_entries + scheduler->plugin_capacity, 0,
           (new_capacity - scheduler->plugin_capacity) * sizeof(*new_entries));
    scheduler->plugins = new_entries;
    scheduler->plugin_capacity = new_capacity;
    return 0;
}

static int apply_realtime_attributes(cortex_scheduler_t *scheduler) {
    if (!scheduler) {
        return -EINVAL;
    }

#if defined(__linux__)
    pthread_t thread = pthread_self();
    if (scheduler->config.cpu_affinity_mask) {
        cpu_set_t mask;
        CPU_ZERO(&mask);
        for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu) {
            if (scheduler->config.cpu_affinity_mask & (1ULL << cpu)) {
                CPU_SET(cpu, &mask);
            }
        }
        int rc = pthread_setaffinity_np(thread, sizeof(mask), &mask);
        if (rc != 0) {
            fprintf(stderr, "[scheduler] warning: pthread_setaffinity_np failed (%d)\n", rc);
        }
    }
    if (scheduler->config.scheduler_policy) {
        int policy = SCHED_OTHER;
        struct sched_param param = {0};
        if (strcmp(scheduler->config.scheduler_policy, "fifo") == 0) {
            policy = SCHED_FIFO;
        } else if (strcmp(scheduler->config.scheduler_policy, "rr") == 0) {
            policy = SCHED_RR;
        }
        param.sched_priority = (int)scheduler->config.realtime_priority;
        if (sched_setscheduler(0, policy, &param) != 0) {
            perror("sched_setscheduler");
        }
    }
    return 0;
#else
    (void)scheduler;
    fprintf(stderr, "[scheduler] realtime scheduling not supported on this platform\n");
    return 0;
#endif
}

static void normalize_timespec(struct timespec *ts) {
    while (ts->tv_nsec >= NSEC_PER_SEC) {
        ts->tv_nsec -= NSEC_PER_SEC;
        ts->tv_sec += 1;
    }
    while (ts->tv_nsec < 0) {
        ts->tv_nsec += NSEC_PER_SEC;
        ts->tv_sec -= 1;
    }
}

static void timespec_add_seconds(struct timespec *ts, double seconds) {
    long sec = (long)seconds;
    long nsec = (long)((seconds - (double)sec) * (double)NSEC_PER_SEC);
    ts->tv_sec += sec;
    ts->tv_nsec += nsec;
    normalize_timespec(ts);
}

static void dispatch_window(cortex_scheduler_t *scheduler, const float *window_data) {
    struct timespec release_ts;
    struct timespec deadline_ts;
    clock_gettime(CLOCK_MONOTONIC, &release_ts);
    deadline_ts = release_ts;
    if (scheduler->config.sample_rate_hz > 0 && scheduler->config.hop_samples > 0) {
        double deadline_delta = (double)scheduler->config.hop_samples /
                                (double)scheduler->config.sample_rate_hz;
        timespec_add_seconds(&deadline_ts, deadline_delta);
    }

    for (size_t i = 0; i < scheduler->plugin_count; ++i) {
        cortex_scheduler_plugin_entry_t *entry = &scheduler->plugins[i];
        const float *input = window_data;
        void *output = entry->output_buffer;
        struct timespec start_ts;
        struct timespec end_ts;
        clock_gettime(CLOCK_MONOTONIC, &start_ts);
        entry->api.process(entry->handle, input, output);
        clock_gettime(CLOCK_MONOTONIC, &end_ts);

        int deadline_missed = 0;
        if ((end_ts.tv_sec > deadline_ts.tv_sec) ||
            (end_ts.tv_sec == deadline_ts.tv_sec && end_ts.tv_nsec > deadline_ts.tv_nsec)) {
            deadline_missed = 1;
        }

        if (scheduler->warmup_windows_remaining > 0) {
            continue;
        }

        record_window_metrics(scheduler, entry, &release_ts, &deadline_ts, &start_ts, &end_ts, deadline_missed);
    }

    if (scheduler->warmup_windows_remaining > 0) {
        scheduler->warmup_windows_remaining -= 1;
    }
    scheduler->window_count += 1;
}

static void record_window_metrics(const cortex_scheduler_t *scheduler,
                                  const cortex_scheduler_plugin_entry_t *plugin,
                                  const struct timespec *release_ts,
                                  const struct timespec *deadline_ts,
                                  const struct timespec *start_ts,
                                  const struct timespec *end_ts,
                                  int deadline_missed) {
    uint64_t rel_ns = (uint64_t)release_ts->tv_sec * (uint64_t)NSEC_PER_SEC + (uint64_t)release_ts->tv_nsec;
    uint64_t ddl_ns = (uint64_t)deadline_ts->tv_sec * (uint64_t)NSEC_PER_SEC + (uint64_t)deadline_ts->tv_nsec;
    uint64_t sta_ns = (uint64_t)start_ts->tv_sec * (uint64_t)NSEC_PER_SEC + (uint64_t)start_ts->tv_nsec;
    uint64_t end_ns = (uint64_t)end_ts->tv_sec * (uint64_t)NSEC_PER_SEC + (uint64_t)end_ts->tv_nsec;
    uint64_t latency_ns = (uint64_t)((end_ts->tv_sec - start_ts->tv_sec) * NSEC_PER_SEC) +
                          (uint64_t)(end_ts->tv_nsec - start_ts->tv_nsec);

    /* Print simple log */
    fprintf(stdout,
            "[telemetry] plugin=%s latency_ns=%llu deadline_missed=%d\n",
            plugin->info.name ? plugin->info.name : "(unnamed)",
            (unsigned long long)latency_ns,
            deadline_missed);

    /* Write CSV if enabled */
    if (scheduler->telemetry_file) {
        FILE *f = scheduler->telemetry_file;
        if (!scheduler->telemetry_header_written) {
            fprintf(f, "plugin,window_index,release_ts_ns,deadline_ts_ns,start_ts_ns,end_ts_ns,deadline_missed,W,H,C,Fs\n");
            ((cortex_scheduler_t *)scheduler)->telemetry_header_written = 1;
        }
        fprintf(f, "%s,%llu,%llu,%llu,%llu,%llu,%d,%u,%u,%u,%u\n",
                plugin->info.name ? plugin->info.name : "(unnamed)",
                (unsigned long long)scheduler->window_count,
                (unsigned long long)rel_ns,
                (unsigned long long)ddl_ns,
                (unsigned long long)sta_ns,
                (unsigned long long)end_ns,
                deadline_missed,
                scheduler->config.window_length_samples,
                scheduler->config.hop_samples,
                scheduler->config.channels,
                scheduler->config.sample_rate_hz);
        fflush(f);
    }
}

static void teardown_plugin(cortex_scheduler_plugin_entry_t *entry) {
    if (!entry) {
        return;
    }
    if (entry->handle && entry->api.teardown) {
        entry->api.teardown(entry->handle);
        entry->handle = NULL;
    }
    free(entry->output_buffer);
    entry->output_buffer = NULL;
    free(entry->config_blob);
    entry->config_blob = NULL;
    entry->config_size = 0;
}
