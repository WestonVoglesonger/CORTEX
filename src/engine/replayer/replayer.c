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
 * - Dropouts API is stub; controlled dropout/delay simulation not yet implemented.
 * - Mark g_replayer_running volatile/atomic if used cross-thread.
 * - Document callback contract: runs on replayer thread, must not block.
 * - Dataset path semantics: assumes float32 file; enforce or validate.
 */

#ifdef __APPLE__
#define _DARWIN_C_SOURCE
#endif
#define _POSIX_C_SOURCE 200809L

#include "replayer.h"
#include "../harness/util/util.h"

#include <errno.h>
#include <math.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifdef __APPLE__
#include <sys/sysctl.h>
#endif

#ifndef CLOCK_MONOTONIC
#error "CLOCK_MONOTONIC not available on this platform"
#endif

#define NSEC_PER_SEC 1000000000LL

/* Background load tracking (shared across all instances - system-wide resource)
 *
 * Design rationale:
 * - Background load (stress-ng) is a SYSTEM-WIDE resource, not per-replayer
 * - Only ONE stress-ng process should run at a time
 * - Multiple replayer instances must coordinate access to this singleton
 *
 * Ownership tracking:
 * - g_background_load_owner: Points to the instance that started the load
 * - Only the owner can stop the load (prevents cross-instance interference)
 * - Example: Instance A starts load, Instance B created/destroyed → B doesn't stop A's load
 *
 * This design allows:
 * - Production: Single instance owns load for entire execution
 * - Tests: Sequential instances each get clean ownership (no interference)
 * - Edge cases: Multiple instances won't conflict (only owner can stop)
 */
static pid_t g_stress_ng_pid = 0;
static cortex_replayer_t *g_background_load_owner = NULL;

/* Replayer instance definition - encapsulates replayer-specific state. */
struct cortex_replayer {
    /* Thread management */
    pthread_t thread;
    volatile sig_atomic_t running;  /* 1 if thread is active, 0 otherwise (volatile for thread safety) */

    /* Configuration */
    cortex_replayer_config_t config;

    /* Callback state */
    cortex_replayer_window_callback callback;
    void *callback_user_data;

    /* Runtime flags */
    int dropouts_enabled;
};

/* Internal helpers. */
static void *replayer_thread_main(void *arg);
static int read_next_chunk(FILE *stream, float *buffer, size_t samples_per_chunk);
static void sleep_until(const struct timespec *target);
static int prepare_background_load(cortex_replayer_t *replayer, const char *profile_name);
static float *allocate_window_buffer(size_t samples_per_window);

/* Background load helpers. */
static int get_cpu_count(void);
static const char *find_stress_ng(void);
static char **build_stress_ng_args(const char *profile_name, int num_cpus);

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

    /* Initialize state (calloc zeros everything, but explicit init for clarity) */
    replayer->running = 0;
    replayer->callback = NULL;
    replayer->callback_user_data = NULL;
    replayer->dropouts_enabled = 0;

    return replayer;
}

void cortex_replayer_destroy(cortex_replayer_t *replayer) {
    if (!replayer) {
        return;
    }

    /* Stop thread if still running */
    cortex_replayer_stop(replayer);

    /* Stop background load if running */
    cortex_replayer_stop_background_load(replayer);

    /* Free the instance */
    free(replayer);
}

int cortex_replayer_start(cortex_replayer_t *replayer,
                          cortex_replayer_window_callback callback,
                          void *user_data) {
    if (!replayer || !callback) {
        return -EINVAL;
    }

    if (replayer->running) {
        fprintf(stderr, "replayer already running\n");
        return -EALREADY;
    }

    /* Validate configuration to fail fast (before starting thread) */
    size_t hop_samples;
    if (cortex_mul_size_overflow(replayer->config.hop_samples, replayer->config.channels, &hop_samples)) {
        fprintf(stderr, "[replayer] Integer overflow: hop_samples=%u * channels=%u exceeds SIZE_MAX\n",
                replayer->config.hop_samples, replayer->config.channels);
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

void cortex_replayer_enable_dropouts(cortex_replayer_t *replayer, int enabled) {
    if (!replayer) {
        return;
    }
    replayer->dropouts_enabled = enabled ? 1 : 0;
}

int cortex_replayer_start_background_load(cortex_replayer_t *replayer, const char *profile_name) {
    if (!replayer) {
        return -EINVAL;
    }
    return prepare_background_load(replayer, profile_name);
}

void cortex_replayer_stop_background_load(cortex_replayer_t *replayer) {
    if (!replayer) {
        return;
    }

    if (g_stress_ng_pid <= 0) {
        return;  /* No background load running */
    }

    /* Only stop if this instance owns the background load (prevents cross-instance interference) */
    if (g_background_load_owner != NULL && g_background_load_owner != replayer) {
        return;  /* Different instance started the load, don't stop it */
    }

    fprintf(stdout, "[load] stopping background load (PID %d)\n", (int)g_stress_ng_pid);
    fflush(stdout);

    /* Send SIGTERM for graceful shutdown */
    if (kill(g_stress_ng_pid, SIGTERM) != 0) {
        if (errno == ESRCH) {
            /* Process already dead, but still need to reap it */
            waitpid(g_stress_ng_pid, NULL, WNOHANG);
            g_stress_ng_pid = 0;
            g_background_load_owner = NULL;
            fprintf(stdout, "[load] background load already exited\n");
            fflush(stdout);
            return;
        }
        perror("[load] failed to send SIGTERM");
        g_stress_ng_pid = 0;
        g_background_load_owner = NULL;
        return;
    }

    /* Wait up to 2 seconds for process to exit */
    int status;
    pid_t result;
    int exited = 0;

    for (int i = 0; i < 20; i++) {  /* 20 * 100ms = 2 seconds */
        result = waitpid(g_stress_ng_pid, &status, WNOHANG);
        if (result > 0) {
            /* Log abnormal exit */
            if (WIFEXITED(status) && WEXITSTATUS(status) != 0) {
                fprintf(stderr, "[load] stress-ng exited with code %d\n", WEXITSTATUS(status));
            } else if (WIFSIGNALED(status)) {
                fprintf(stderr, "[load] stress-ng killed by signal %d\n", WTERMSIG(status));
            }
            exited = 1;
            break;
        } else if (result < 0 && errno != EINTR) {
            perror("[load] waitpid failed");
            break;
        }

        /* Sleep 100ms before checking again */
        struct timespec sleep_time = {.tv_sec = 0, .tv_nsec = 100000000};
        nanosleep(&sleep_time, NULL);
    }

    if (!exited) {
        /* Process didn't exit gracefully, send SIGKILL */
        fprintf(stderr, "[load] stress-ng didn't exit after 2s, sending SIGKILL\n");
        kill(g_stress_ng_pid, SIGKILL);

        /* Blocking wait to reap zombie */
        waitpid(g_stress_ng_pid, NULL, 0);
    }

    fprintf(stdout, "[load] background load stopped\n");
    fflush(stdout);
    g_stress_ng_pid = 0;
    g_background_load_owner = NULL;  /* Clear ownership */
}

static void *replayer_thread_main(void *arg) {
    cortex_replayer_t *replayer = (cortex_replayer_t *)arg;

    /* Calculate chunk size (overflow already checked in start()) */
    size_t hop_samples = (size_t)replayer->config.hop_samples * replayer->config.channels;

    float *chunk_buffer = allocate_window_buffer(hop_samples);
    if (!chunk_buffer) {
        replayer->running = 0;
        return NULL;
    }

    FILE *stream = fopen(replayer->config.dataset_path, "rb");
    if (!stream) {
        perror("failed to open dataset");
        free(chunk_buffer);
        replayer->running = 0;
        return NULL;
    }

    struct timespec next_emit = {0};
    clock_gettime(CLOCK_MONOTONIC, &next_emit);

    const double hop_period_sec = (double)replayer->config.hop_samples / (double)replayer->config.sample_rate_hz;
    const long hop_period_nsec = (long)(hop_period_sec * NSEC_PER_SEC);

    fprintf(stdout, "[replayer] streaming %u samples/channel × %u channels = %zu total samples every %.1f ms (%.2f Hz chunk rate, %.0f samples/s total)\n",
            replayer->config.hop_samples,
            replayer->config.channels,
            hop_samples,
            hop_period_sec * 1000.0,
            1.0 / hop_period_sec,
            (double)hop_samples / hop_period_sec);

    while (replayer->running) {
        int read_status = read_next_chunk(stream, chunk_buffer, hop_samples);
        if (read_status <= 0) {
            rewind(stream);
            continue;
        }

        if (replayer->dropouts_enabled) {
            /* TODO: randomly skip or delay this chunk based on configuration. */
        }

        if (replayer->callback) {
            replayer->callback(chunk_buffer, hop_samples, replayer->callback_user_data);
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

/* Detect number of CPUs on the system. */
static int get_cpu_count(void) {
#ifdef __APPLE__
    int nprocs;
    size_t len = sizeof(nprocs);
    if (sysctlbyname("hw.ncpu", &nprocs, &len, NULL, 0) == 0 && nprocs > 0) {
        return nprocs;
    }
#else
    long nprocs = sysconf(_SC_NPROCESSORS_ONLN);
    if (nprocs > 0) {
        return (int)nprocs;
    }
#endif
    fprintf(stderr, "[load] failed to detect CPU count, defaulting to 4\n");
    return 4;
}

/* Find stress-ng executable in common paths. Returns NULL if not found. */
static const char *find_stress_ng(void) {
    static const char *paths[] = {
        "/usr/bin/stress-ng",
        "/usr/local/bin/stress-ng",
        "/opt/homebrew/bin/stress-ng",
        "/usr/local/opt/stress-ng/bin/stress-ng",
        NULL
    };

    for (int i = 0; paths[i] != NULL; i++) {
        if (access(paths[i], X_OK) == 0) {
            return paths[i];
        }
    }
    return NULL;
}

/* Build argv array for stress-ng based on profile. Returns NULL for "idle".
 * Caller must free the returned array and its strings. */
static char **build_stress_ng_args(const char *profile_name, int num_cpus) {
    if (!profile_name || strcmp(profile_name, "idle") == 0) {
        return NULL;
    }

    int cpu_count;
    int cpu_load;

    if (strcmp(profile_name, "medium") == 0) {
        cpu_count = num_cpus / 2;
        if (cpu_count < 1) cpu_count = 1;
        cpu_load = 50;
    } else if (strcmp(profile_name, "heavy") == 0) {
        cpu_count = num_cpus;
        cpu_load = 90;
    } else {
        fprintf(stderr, "[load] unknown profile '%s', using idle\n", profile_name);
        return NULL;
    }

    /* Allocate argv array: ["stress-ng", "--cpu", "N", "--cpu-load", "X", "--timeout", "0", NULL] */
    char **argv = calloc(8, sizeof(char *));
    if (!argv) return NULL;

    argv[0] = strdup("stress-ng");
    argv[1] = strdup("--cpu");
    argv[2] = malloc(16);
    argv[3] = strdup("--cpu-load");
    argv[4] = malloc(16);
    argv[5] = strdup("--timeout");
    argv[6] = strdup("0");
    argv[7] = NULL;

    if (!argv[0] || !argv[1] || !argv[2] || !argv[3] || !argv[4] || !argv[5] || !argv[6]) {
        for (int i = 0; i < 7; i++) free(argv[i]);
        free(argv);
        return NULL;
    }

    snprintf(argv[2], 16, "%d", cpu_count);
    snprintf(argv[4], 16, "%d", cpu_load);

    return argv;
}

static int prepare_background_load(cortex_replayer_t *replayer, const char *profile_name) {
    if (g_stress_ng_pid > 0) {
        fprintf(stderr, "[load] background load already running (PID %d)\n", (int)g_stress_ng_pid);
        return -1;
    }

    /* Check if profile needs stress before looking for stress-ng */
    if (!profile_name || strcmp(profile_name, "idle") == 0) {
        fprintf(stdout, "[load] profile 'idle' - no background load\n");
        fflush(stdout);
        return 0;
    }

    /* Validate profile */
    if (strcmp(profile_name, "medium") != 0 && strcmp(profile_name, "heavy") != 0) {
        fprintf(stderr, "[load] unknown profile '%s', treating as idle\n", profile_name);
        return 0;
    }

    const char *stress_ng_path = find_stress_ng();
    if (!stress_ng_path) {
        fprintf(stderr, "[load] stress-ng not found in PATH, running without background load\n");
        return 0;  /* Not an error - graceful fallback */
    }

    int num_cpus = get_cpu_count();
    char **args = build_stress_ng_args(profile_name, num_cpus);

    if (!args) {
        /* Shouldn't happen since we validated profile above */
        fprintf(stderr, "[load] failed to build stress-ng arguments\n");
        return 0;
    }

    pid_t pid = fork();
    if (pid == 0) {
        /* Child process: exec stress-ng */
        execv(stress_ng_path, args);
        /* If exec fails, exit immediately */
        perror("[load] execv failed");
        exit(1);
    } else if (pid > 0) {
        /* Parent process: store PID in global and record ownership */
        g_stress_ng_pid = pid;
        g_background_load_owner = replayer;  /* Track which instance started the load */
        fprintf(stdout, "[load] started background load: %s (PID %d, %s CPUs @ %s%% load)\n",
                profile_name, (int)pid, args[2], args[4]);
        fflush(stdout);

        /* Free args array */
        for (int i = 0; args[i] != NULL; i++) {
            free(args[i]);
        }
        free(args);
        return 0;
    } else {
        /* Fork failed */
        perror("[load] fork failed");
        for (int i = 0; args[i] != NULL; i++) {
            free(args[i]);
        }
        free(args);
        return -1;
    }
}
