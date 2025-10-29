/*
 * Replayer: streams dataset samples at real-time cadence into a user callback.
 *
 * The replayer emulates hardware data acquisition by streaming hop-sized chunks
 * of samples at the true sample rate. The scheduler receives these chunks and
 * forms overlapping windows internally via its sliding buffer mechanism.
 *
 * CURRENT STATUS:
 * - Core timing loop is solid (CLOCK_MONOTONIC + nanosleep).
 * - Streams hop-sized chunks at correct real-time cadence (H samples every H/Fs seconds).
 * - Handles EOF by rewind for endless replay.
 * - Clean resource lifecycle (alloc/free, fopen/fclose, pthread join).
 *
 * TODO / CLEANUP:
 * - Kill unused globals (g_dtype) or implement proper dtype handling.
 * - Dropouts + background load APIs are stubs; either implement or remove.
 * - Mark g_replayer_running volatile/atomic if used cross-thread.
 * - Document callback contract: runs on replayer thread, must not block.
 * - Dataset path semantics: assumes float32 file; enforce or validate.
 */

#define _POSIX_C_SOURCE 200809L

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
static cortex_replayer_window_callback g_callback = NULL;
static uint32_t g_dtype = 0;
static void *g_callback_user_data = NULL;
static cortex_replayer_config_t g_config;

/* Internal helpers. */
static void *replayer_thread_main(void *arg);
static int read_next_chunk(FILE *stream, float *buffer, size_t samples_per_chunk);
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
    g_dtype = config->dtype;

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
    const size_t hop_samples = (size_t)g_config.hop_samples * g_config.channels;
    float *chunk_buffer = allocate_window_buffer(hop_samples);
    if (!chunk_buffer) {
        g_replayer_running = 0;
        return NULL;
    }

    FILE *stream = fopen(g_config.dataset_path, "rb");
    if (!stream) {
        perror("failed to open dataset");
        free(chunk_buffer);
        g_replayer_running = 0;
        return NULL;
    }

    struct timespec next_emit = {0};
    clock_gettime(CLOCK_MONOTONIC, &next_emit);

    const double hop_period_sec = (double)g_config.hop_samples / (double)g_config.sample_rate_hz;
    const long hop_period_nsec = (long)(hop_period_sec * NSEC_PER_SEC);

    fprintf(stdout, "[replayer] streaming %u samples every %.1f ms (%.2f Hz)\n",
            g_config.hop_samples, 
            hop_period_sec * 1000.0,
            1.0 / hop_period_sec);

    while (g_replayer_running) {
        int read_status = read_next_chunk(stream, chunk_buffer, hop_samples);
        if (read_status <= 0) {
            rewind(stream);
            continue;
        }

        if (g_dropouts_enabled) {
            /* TODO: randomly skip or delay this chunk based on configuration. */
        }

        if (g_callback) {
            g_callback(chunk_buffer, hop_samples, g_callback_user_data);
        }

        next_emit.tv_nsec += hop_period_nsec;
        normalize_timespec(&next_emit);
        sleep_until(&next_emit);
    }

    fclose(stream);
    free(chunk_buffer);
    return NULL;
}

static float *allocate_window_buffer(size_t samples_per_window) {
    float *buffer = (float *)calloc(samples_per_window, sizeof(float));
    if (!buffer) {
        perror("calloc window buffer");
    }
    return buffer;
}

static int read_next_chunk(FILE *stream, float *buffer, size_t samples_per_chunk) {
    size_t read_elems = fread(buffer, sizeof(float), samples_per_chunk, stream);
    if (read_elems < samples_per_chunk) {
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
