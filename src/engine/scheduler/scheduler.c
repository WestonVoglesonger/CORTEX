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

#include "../telemetry/telemetry.h"
#include "../harness/util/util.h"
#include "../harness/device/device_comm.h"

#ifdef __linux__
#include <sched.h>
#endif

#ifdef __APPLE__
#include <mach/mach_time.h>
#endif

#define NSEC_PER_SEC 1000000000LL

typedef struct cortex_scheduler_plugin_entry {
    const char *plugin_name;  /* For logging/telemetry */
    char adapter_name[32];    /* Adapter name from HELLO */
    void *device_handle;      /* Device adapter handle (borrowed from harness) */
    void *output_buffer;      /* Output buffer for kernel results */
    size_t output_bytes;      /* Size of output buffer */
    uint32_t output_window_length_samples;  /* Output W (from ACK or config) */
    uint32_t output_channels;               /* Output C (from ACK or config) */
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
    
    /* Telemetry buffer integration */
    char run_id[32];  /* Store run_id for telemetry records */
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
                                  int deadline_missed,
                                  uint64_t device_tin_ns,
                                  uint64_t device_tstart_ns,
                                  uint64_t device_tend_ns,
                                  uint64_t device_tfirst_tx_ns,
                                  uint64_t device_tlast_tx_ns,
                                  uint8_t window_failed,
                                  int32_t error_code);
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

    /* Check for integer overflow in buffer size calculations */
    size_t window_samples, hop_samples;
    if (cortex_mul_size_overflow(config->window_length_samples, config->channels, &window_samples)) {
        fprintf(stderr, "[scheduler] Integer overflow: window_length=%u * channels=%u exceeds SIZE_MAX\n",
                config->window_length_samples, config->channels);
        errno = EOVERFLOW;
        free(scheduler);
        return NULL;
    }
    if (cortex_mul_size_overflow(config->hop_samples, config->channels, &hop_samples)) {
        fprintf(stderr, "[scheduler] Integer overflow: hop_samples=%u * channels=%u exceeds SIZE_MAX\n",
                config->hop_samples, config->channels);
        errno = EOVERFLOW;
        free(scheduler);
        return NULL;
    }

    scheduler->window_samples = window_samples;
    scheduler->hop_samples = hop_samples;
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

    /* Store run_id for telemetry records */
    if (config->run_id) {
        strncpy(scheduler->run_id, config->run_id, sizeof(scheduler->run_id) - 1);
        scheduler->run_id[sizeof(scheduler->run_id) - 1] = '\0';
    } else {
        scheduler->run_id[0] = '\0';
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

int cortex_scheduler_register_device(cortex_scheduler_t *scheduler,
                                     const cortex_scheduler_device_info_t *device_info,
                                     uint32_t config_window_length,
                                     uint32_t config_channels) {
    if (!scheduler || !device_info || !device_info->device_handle) {
        return -EINVAL;
    }

    /* Ensure we have capacity for the new device (may return -EOVERFLOW or -ENOMEM) */
    int capacity_rc = ensure_plugin_capacity(scheduler);
    if (capacity_rc != 0) {
        return capacity_rc;  /* Propagate the actual error (-EOVERFLOW or -ENOMEM) */
    }

    cortex_scheduler_plugin_entry_t *entry = &scheduler->plugins[scheduler->plugin_count];
    memset(entry, 0, sizeof(*entry));

    /* Store plugin name (duplicate string to avoid lifetime issues) */
    entry->plugin_name = strdup(device_info->plugin_name);
    if (!entry->plugin_name) {
        return -ENOMEM;
    }

    /* Copy adapter name */
    strncpy(entry->adapter_name, device_info->adapter_name, sizeof(entry->adapter_name) - 1);
    entry->adapter_name[sizeof(entry->adapter_name) - 1] = '\0';

    /* Borrow device handle (harness owns lifecycle) */
    entry->device_handle = device_info->device_handle;

    /* Determine output dimensions (ACK override or config) */
    entry->output_window_length_samples = (device_info->output_window_length_samples > 0)
        ? device_info->output_window_length_samples
        : config_window_length;
    entry->output_channels = (device_info->output_channels > 0)
        ? device_info->output_channels
        : config_channels;

    /* Allocate output buffer */
    const size_t element_size = sizeof(float); /* TODO: support Q15/Q7 */

    /* Check for overflow in output buffer size calculation */
    size_t temp, output_bytes;
    if (cortex_mul_size_overflow(entry->output_window_length_samples,
                                 entry->output_channels, &temp)) {
        fprintf(stderr, "[scheduler] Integer overflow: output dimensions %u * %u exceed SIZE_MAX\n",
                entry->output_window_length_samples, entry->output_channels);
        free((char*)entry->plugin_name);
        entry->plugin_name = NULL;
        errno = EOVERFLOW;
        return -EOVERFLOW;
    }
    if (cortex_mul_size_overflow(temp, element_size, &output_bytes)) {
        fprintf(stderr, "[scheduler] Integer overflow: output size %zu * %zu exceeds SIZE_MAX\n",
                temp, element_size);
        free((char*)entry->plugin_name);
        entry->plugin_name = NULL;
        errno = EOVERFLOW;
        return -EOVERFLOW;
    }
    entry->output_bytes = output_bytes;

    entry->output_buffer = calloc(1, entry->output_bytes);
    if (!entry->output_buffer) {
        free((char*)entry->plugin_name);
        entry->plugin_name = NULL;
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

void cortex_scheduler_set_telemetry_buffer(cortex_scheduler_t *scheduler, void *telemetry_buffer) {
    if (scheduler) {
        scheduler->config.telemetry_buffer = telemetry_buffer;
    }
}

void cortex_scheduler_set_run_id(cortex_scheduler_t *scheduler, const char *run_id) {
    if (scheduler && run_id) {
        strncpy(scheduler->run_id, run_id, sizeof(scheduler->run_id) - 1);
        scheduler->run_id[sizeof(scheduler->run_id) - 1] = '\0';
    }
}

void cortex_scheduler_set_current_repeat(cortex_scheduler_t *scheduler, uint32_t repeat) {
    if (scheduler) {
        scheduler->config.current_repeat = repeat;
    }
}

static int ensure_plugin_capacity(cortex_scheduler_t *scheduler) {
    if (scheduler->plugin_count < scheduler->plugin_capacity) {
        return 0;
    }

    /* Check for overflow in capacity doubling */
    size_t new_capacity, alloc_size;
    if (cortex_mul_size_overflow(scheduler->plugin_capacity, 2, &new_capacity)) {
        fprintf(stderr, "[scheduler] Integer overflow: plugin_capacity=%zu * 2 exceeds SIZE_MAX\n",
                scheduler->plugin_capacity);
        errno = EOVERFLOW;
        return -EOVERFLOW;  /* Return distinct error code for overflow */
    }
    /* Check for overflow in allocation size calculation */
    if (cortex_mul_size_overflow(new_capacity, sizeof(*scheduler->plugins), &alloc_size)) {
        fprintf(stderr, "[scheduler] Integer overflow: new_capacity=%zu * sizeof(entry)=%zu exceeds SIZE_MAX\n",
                new_capacity, sizeof(*scheduler->plugins));
        errno = EOVERFLOW;
        return -EOVERFLOW;  /* Return distinct error code for overflow */
    }

    cortex_scheduler_plugin_entry_t *new_entries = realloc(scheduler->plugins, alloc_size);
    if (!new_entries) {
        return -ENOMEM;  /* Return distinct error code for allocation failure */
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

        /* Device timing */
        uint64_t device_tin_ns = 0;
        uint64_t device_tstart_ns = 0;
        uint64_t device_tend_ns = 0;
        uint64_t device_tfirst_tx_ns = 0;
        uint64_t device_tlast_tx_ns = 0;

        /* Window failure tracking */
        uint8_t window_failed = 0;
        int32_t error_code = 0;

        clock_gettime(CLOCK_MONOTONIC, &start_ts);

        /* Execute via device adapter (universal adapter model) */
        cortex_device_handle_t *device = (cortex_device_handle_t *)entry->device_handle;
        cortex_device_timing_t device_timing;

        int ret = device_comm_execute_window(
            device,
            (uint32_t)scheduler->window_count,  /* sequence */
            input,
            (uint32_t)scheduler->config.window_length_samples,
            (uint32_t)scheduler->config.channels,
            (float *)output,
            entry->output_bytes,
            &device_timing
        );

        if (ret < 0) {
            fprintf(stderr, "[scheduler] device_comm_execute_window failed: %d (plugin=%s, window=%llu)\n",
                    ret, entry->plugin_name, (unsigned long long)scheduler->window_count);
            window_failed = 1;
            error_code = ret;
        } else {
            /* Extract device timing */
            device_tin_ns = device_timing.tin;
            device_tstart_ns = device_timing.tstart;
            device_tend_ns = device_timing.tend;
            device_tfirst_tx_ns = device_timing.tfirst_tx;
            device_tlast_tx_ns = device_timing.tlast_tx;
        }

        clock_gettime(CLOCK_MONOTONIC, &end_ts);

        int deadline_missed = 0;
        if ((end_ts.tv_sec > deadline_ts.tv_sec) ||
            (end_ts.tv_sec == deadline_ts.tv_sec && end_ts.tv_nsec > deadline_ts.tv_nsec)) {
            deadline_missed = 1;
        }

        if (scheduler->warmup_windows_remaining > 0) {
            continue;
        }

        record_window_metrics(scheduler, entry, &release_ts, &deadline_ts, &start_ts, &end_ts, deadline_missed,
                              device_tin_ns, device_tstart_ns, device_tend_ns, device_tfirst_tx_ns, device_tlast_tx_ns,
                              window_failed, error_code);
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
                                  int deadline_missed,
                                  uint64_t device_tin_ns,
                                  uint64_t device_tstart_ns,
                                  uint64_t device_tend_ns,
                                  uint64_t device_tfirst_tx_ns,
                                  uint64_t device_tlast_tx_ns,
                                  uint8_t window_failed,
                                  int32_t error_code) {
    uint64_t rel_ns = (uint64_t)release_ts->tv_sec * (uint64_t)NSEC_PER_SEC + (uint64_t)release_ts->tv_nsec;
    uint64_t ddl_ns = (uint64_t)deadline_ts->tv_sec * (uint64_t)NSEC_PER_SEC + (uint64_t)deadline_ts->tv_nsec;
    uint64_t sta_ns = (uint64_t)start_ts->tv_sec * (uint64_t)NSEC_PER_SEC + (uint64_t)start_ts->tv_nsec;
    uint64_t end_ns = (uint64_t)end_ts->tv_sec * (uint64_t)NSEC_PER_SEC + (uint64_t)end_ts->tv_nsec;
    uint64_t latency_ns = (uint64_t)((end_ts->tv_sec - start_ts->tv_sec) * NSEC_PER_SEC) +
                          (uint64_t)(end_ts->tv_nsec - start_ts->tv_nsec);

    /* Print log with failure status */
    if (window_failed) {
        fprintf(stdout,
                "[telemetry] plugin=%s latency_ns=%llu deadline_missed=%d FAILED (error=%d)\n",
                plugin->plugin_name ? plugin->plugin_name : "(unnamed)",
                (unsigned long long)latency_ns,
                deadline_missed,
                error_code);
    } else {
        fprintf(stdout,
                "[telemetry] plugin=%s latency_ns=%llu deadline_missed=%d\n",
                plugin->plugin_name ? plugin->plugin_name : "(unnamed)",
                (unsigned long long)latency_ns,
                deadline_missed);
    }

    /* If buffer is provided, add record to buffer */
    if (scheduler->config.telemetry_buffer) {
        cortex_telemetry_buffer_t *buffer = (cortex_telemetry_buffer_t *)scheduler->config.telemetry_buffer;
        cortex_telemetry_record_t rec = {0};
        strncpy(rec.run_id, scheduler->run_id, sizeof(rec.run_id)-1);
        strncpy(rec.plugin_name, plugin->plugin_name ? plugin->plugin_name : "(unnamed)", sizeof(rec.plugin_name)-1);
        rec.window_index = scheduler->window_count;
        rec.release_ts_ns = rel_ns;
        rec.deadline_ts_ns = ddl_ns;
        rec.start_ts_ns = sta_ns;
        rec.end_ts_ns = end_ns;
        rec.deadline_missed = deadline_missed;
        rec.W = scheduler->config.window_length_samples;
        rec.H = scheduler->config.hop_samples;
        rec.C = scheduler->config.channels;
        rec.Fs = scheduler->config.sample_rate_hz;
        rec.warmup = (scheduler->warmup_windows_remaining > 0) ? 1 : 0;
        rec.repeat = scheduler->config.current_repeat;

        /* Populate device-side timing */
        rec.device_tin_ns = device_tin_ns;
        rec.device_tstart_ns = device_tstart_ns;
        rec.device_tend_ns = device_tend_ns;
        rec.device_tfirst_tx_ns = device_tfirst_tx_ns;
        rec.device_tlast_tx_ns = device_tlast_tx_ns;

        /* Copy adapter name from entry */
        strncpy(rec.adapter_name, plugin->adapter_name, sizeof(rec.adapter_name)-1);
        rec.adapter_name[sizeof(rec.adapter_name)-1] = '\0';

        /* Record failure status */
        rec.window_failed = window_failed;
        rec.error_code = error_code;

        cortex_telemetry_add(buffer, &rec);
    }

    /* Write CSV if enabled (keep for backward compatibility) */
    if (scheduler->telemetry_file) {
        FILE *f = scheduler->telemetry_file;
        if (!scheduler->telemetry_header_written) {
            fprintf(f, "plugin,window_index,release_ts_ns,deadline_ts_ns,start_ts_ns,end_ts_ns,deadline_missed,W,H,C,Fs\n");
            ((cortex_scheduler_t *)scheduler)->telemetry_header_written = 1;
        }
        fprintf(f, "%s,%llu,%llu,%llu,%llu,%llu,%d,%u,%u,%u,%u\n",
                plugin->plugin_name ? plugin->plugin_name : "(unnamed)",
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

    /* NOTE: device_handle is borrowed from harness - do NOT teardown here */
    /* Harness owns device lifecycle and will call device_comm_teardown() */

    free(entry->output_buffer);
    entry->output_buffer = NULL;
    entry->output_bytes = 0;

    /* Free duplicated plugin name */
    if (entry->plugin_name) {
        free((char*)entry->plugin_name);
        entry->plugin_name = NULL;
    }
}
