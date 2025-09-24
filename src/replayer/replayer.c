#include "replayer.h"

#include <errno.h>
#include <math.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#ifndef CLOCK_MONOTONIC
#error "CLOCK_MONOTONIC not available on this platform"
#endif

#define NSEC_PER_SEC 1000000000LL

/* Global state guarded by the assumption that only one replayer runs at once. */
static pthread_t g_replayer_thread;
static int g_replayer_running = 0;
static int g_dropouts_enabled = 0;
static uint32_t g_last_dtype = 0;
static cortex_replayer_window_callback g_callback = NULL;
static void *g_callback_user_data = NULL;
static cortex_replayer_config_t g_config;

/* Internal helpers. */
static void *replayer_thread_main(void *arg);
static int read_next_window(FILE *stream, float *buffer, size_t samples_per_window);
static void sleep_until(const struct timespec *target);
static int prepare_background_load(const char *profile_name);
static float *allocate_window_buffer(size_t samples_per_window);

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

int cortex_replayer_run(const cortex_replayer_config_t *config,
                        cortex_replayer_window_callback callback,
                        void *user_data) {
    if (g_replayer_running) {
        fprintf(stderr, "replayer already running\n");
        return -1;
    }
    if (!config || !callback) {
        return -EINVAL;
    }
    memset(&g_config, 0, sizeof(g_config));
    g_config = *config;
    g_callback = callback;
    g_callback_user_data = user_data;
    g_last_dtype = config->dtype;

    g_replayer_running = 1;
    int rc = pthread_create(&g_replayer_thread, NULL, replayer_thread_main, NULL);
    if (rc != 0) {
        g_replayer_running = 0;
        return -rc;
    }
    return 0;
}

int cortex_replayer_stop(void) {
    if (!g_replayer_running) {
        return 0;
    }
    g_replayer_running = 0;
    pthread_join(g_replayer_thread, NULL);
    return 0;
}

void cortex_replayer_enable_dropouts(int enabled) {
    g_dropouts_enabled = enabled ? 1 : 0;
}

void cortex_replayer_set_load_profile(const char *profile_name) {
    (void)profile_name;
    /* TODO: read per-profile parameters from docs/RUN_CONFIG.md mappings. */
}

int cortex_replayer_start_background_load(const char *profile_name) {
    return prepare_background_load(profile_name);
}

void cortex_replayer_stop_background_load(void) {
    /* TODO: terminate stress-ng or other load generator gracefully. */
}

static void *replayer_thread_main(void *arg) {
    (void)arg;
    const size_t window_samples = (size_t)g_config.window_length_samples * g_config.channels;
    const size_t hop_samples = (size_t)g_config.hop_samples * g_config.channels;
    float *window_buffer = allocate_window_buffer(window_samples);
    if (!window_buffer) {
        g_replayer_running = 0;
        return NULL;
    }

    FILE *stream = fopen(g_config.dataset_path, "rb");
    if (!stream) {
        perror("failed to open dataset");
        free(window_buffer);
        g_replayer_running = 0;
        return NULL;
    }

    struct timespec next_emit = {0};
    clock_gettime(CLOCK_MONOTONIC, &next_emit);

    const double sample_period_sec = 1.0 / (double)g_config.sample_rate_hz;
    const double window_period_sec = sample_period_sec * (double)g_config.hop_samples;
    const long window_period_nsec = (long)(window_period_sec * NSEC_PER_SEC);

    while (g_replayer_running) {
        int read_status = read_next_window(stream, window_buffer, window_samples);
        if (read_status <= 0) {
            rewind(stream);
            continue;
        }

        if (g_dropouts_enabled) {
            /* TODO: randomly skip or delay this window based on configuration. */
        }

        if (g_callback) {
            g_callback(window_buffer, window_samples, g_callback_user_data);
        }

        next_emit.tv_nsec += window_period_nsec;
        normalize_timespec(&next_emit);
        sleep_until(&next_emit);
    }

    fclose(stream);
    free(window_buffer);
    return NULL;
}

static float *allocate_window_buffer(size_t samples_per_window) {
    float *buffer = (float *)calloc(samples_per_window, sizeof(float));
    if (!buffer) {
        perror("calloc window buffer");
    }
    return buffer;
}

static int read_next_window(FILE *stream, float *buffer, size_t samples_per_window) {
    size_t read_elems = fread(buffer, sizeof(float), samples_per_window, stream);
    if (read_elems < samples_per_window) {
        if (feof(stream)) {
            return 0;
        }
        if (ferror(stream)) {
            perror("dataset read error");
            clearerr(stream);
            return -1;
        }
    }
    return (int)read_elems;
}

static void sleep_until(const struct timespec *target) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);

    struct timespec delta = {
        .tv_sec = target->tv_sec - now.tv_sec,
        .tv_nsec = target->tv_nsec - now.tv_nsec
    };
    normalize_timespec(&delta);

    while ((delta.tv_sec > 0) || (delta.tv_sec == 0 && delta.tv_nsec > 0)) {
        if (nanosleep(&delta, &delta) == 0) {
            break;
        }
        if (errno != EINTR) {
            break;
        }
    }
}

static int prepare_background_load(const char *profile_name) {
    (void)profile_name;
    /* TODO: spawn stress-ng with appropriate parameters based on profile. */
    return 0;
}
