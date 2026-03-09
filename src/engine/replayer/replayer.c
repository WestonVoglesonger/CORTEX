/*
 * Replayer: streams dataset samples at real-time cadence into a user callback.
 *
 * Minimal data source that emits packets of packet_samples x C float32 values
 * at real-time cadence (packet_samples/Fs seconds per emission). The scheduler
 * receives these packets and forms overlapping windows internally via its
 * sliding buffer mechanism.
 *
 * - Core timing loop uses CLOCK_MONOTONIC + nanosleep.
 * - Handles EOF by rewind for endless replay.
 * - Clean resource lifecycle (alloc/free, fopen/fclose, pthread join).
 */

#ifdef __APPLE__
#define _DARWIN_C_SOURCE
#endif
#define _POSIX_C_SOURCE 200809L

#include "replayer.h"
#include "../harness/util/util.h"

#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#ifndef CLOCK_MONOTONIC
#error "CLOCK_MONOTONIC not available on this platform"
#endif

#define NSEC_PER_SEC 1000000000LL

/* Replayer instance definition - encapsulates replayer-specific state. */
struct cortex_replayer {
    /* Thread management */
    pthread_t thread;
    volatile sig_atomic_t running;  /* 1 if thread is active, 0 otherwise */

    /* Configuration */
    cortex_replayer_config_t config;

    /* Callback state */
    cortex_replayer_packet_callback callback;
    void *callback_user_data;
};

/* Internal helpers. */
static void *replayer_thread_main(void *arg);
static int read_next_chunk(FILE *stream, float *buffer, size_t samples_per_chunk);
static void sleep_until(const struct timespec *target);

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

cortex_replayer_t *cortex_replayer_create(const cortex_replayer_config_t *config) {
    if (!config) {
        errno = EINVAL;
        return NULL;
    }

    /* Validate required string fields */
    if (!config->dataset_path) {
        fprintf(stderr, "[replayer] dataset_path cannot be NULL\n");
        errno = EINVAL;
        return NULL;
    }

    cortex_replayer_t *replayer = calloc(1, sizeof(cortex_replayer_t));
    if (!replayer) {
        return NULL;  /* errno set by calloc */
    }

    /* Copy configuration (strings stored by reference - see header docs) */
    replayer->config = *config;

    /* Initialize state */
    replayer->running = 0;
    replayer->callback = NULL;
    replayer->callback_user_data = NULL;

    return replayer;
}

void cortex_replayer_destroy(cortex_replayer_t *replayer) {
    if (!replayer) {
        return;
    }

    /* Stop thread if still running */
    cortex_replayer_stop(replayer);

    /* Free the instance */
    free(replayer);
}

int cortex_replayer_start(cortex_replayer_t *replayer,
                          cortex_replayer_packet_callback callback,
                          void *user_data) {
    if (!replayer || !callback) {
        return -EINVAL;
    }

    if (replayer->running) {
        fprintf(stderr, "replayer already running\n");
        return -EALREADY;
    }

    /* Validate configuration to fail fast (before starting thread) */
    size_t packet_total;
    if (cortex_mul_size_overflow(replayer->config.packet_samples, replayer->config.channels, &packet_total)) {
        fprintf(stderr, "[replayer] Integer overflow: packet_samples=%u * channels=%u exceeds SIZE_MAX\n",
                replayer->config.packet_samples, replayer->config.channels);
        errno = EOVERFLOW;
        return -EOVERFLOW;
    }

    replayer->callback = callback;
    replayer->callback_user_data = user_data;
    replayer->running = 1;

    int rc = pthread_create(&replayer->thread, NULL, replayer_thread_main, replayer);
    if (rc != 0) {
        replayer->running = 0;
        return -rc;
    }
    return 0;
}

int cortex_replayer_stop(cortex_replayer_t *replayer) {
    if (!replayer) {
        return -EINVAL;
    }

    if (!replayer->running) {
        return 0;  /* Already stopped */
    }

    replayer->running = 0;
    int rc = pthread_join(replayer->thread, NULL);
    if (rc != 0) {
        fprintf(stderr, "[replayer] pthread_join failed: %d\n", rc);
        return -rc;
    }
    return 0;
}

static void *replayer_thread_main(void *arg) {
    cortex_replayer_t *replayer = (cortex_replayer_t *)arg;

    /* Calculate packet size (overflow already checked in start()) */
    size_t packet_total = (size_t)replayer->config.packet_samples * replayer->config.channels;

    float *packet_buffer = (float *)calloc(packet_total, sizeof(float));
    if (!packet_buffer) {
        perror("calloc packet buffer");
        replayer->running = 0;
        return NULL;
    }

    FILE *stream = fopen(replayer->config.dataset_path, "rb");
    if (!stream) {
        perror("failed to open dataset");
        free(packet_buffer);
        replayer->running = 0;
        return NULL;
    }

    struct timespec next_emit = {0};
    clock_gettime(CLOCK_MONOTONIC, &next_emit);

    const double packet_period_sec = (double)replayer->config.packet_samples / (double)replayer->config.sample_rate_hz;
    const long packet_period_nsec = (long)(packet_period_sec * NSEC_PER_SEC);

    fprintf(stdout, "[replayer] streaming %u samples/channel x %u channels = %zu packet every %.1f ms (%.2f Hz packet rate)\n",
            replayer->config.packet_samples,
            replayer->config.channels,
            packet_total,
            packet_period_sec * 1000.0,
            1.0 / packet_period_sec);

    while (replayer->running) {
        int read_status = read_next_chunk(stream, packet_buffer, packet_total);
        if (read_status <= 0) {
            rewind(stream);
            continue;
        }

        if (replayer->callback) {
            replayer->callback(packet_buffer, packet_total, replayer->callback_user_data);
        }

        next_emit.tv_nsec += packet_period_nsec;
        normalize_timespec(&next_emit);
        sleep_until(&next_emit);
    }

    fclose(stream);
    free(packet_buffer);
    return NULL;
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
