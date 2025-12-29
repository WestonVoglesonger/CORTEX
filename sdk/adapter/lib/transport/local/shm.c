/*
 * Shared Memory Transport for CORTEX Device Adapters
 *
 * High-performance local transport using POSIX shared memory and semaphores.
 * Ideal for benchmarking adapter overhead without network/serial latency.
 *
 * Use cases:
 * - Performance testing (measure pure protocol overhead)
 * - Local development/debugging
 * - High-throughput local processing
 *
 * Architecture:
 * - Two ring buffers (harness→adapter, adapter→harness)
 * - Semaphore synchronization (data_ready, space_avail)
 * - Lock-free single-producer/single-consumer queues
 *
 * Performance: ~10x faster than socketpair, ~100x faster than TCP
 */

#define _POSIX_C_SOURCE 200809L

#include "cortex_transport.h"

#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <unistd.h>
#include <semaphore.h>
#include <errno.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>

#define RING_BUFFER_SIZE (256 * 1024)  /* 256KB per direction */

/* Ring buffer (single producer, single consumer) */
typedef struct {
    uint8_t data[RING_BUFFER_SIZE];
    volatile uint32_t write_pos;  /* Producer writes here */
    volatile uint32_t read_pos;   /* Consumer reads here */
    uint32_t pad[14];  /* Cache line padding (64 bytes total) */
} ring_buffer_t;

/* Shared memory layout */
typedef struct {
    ring_buffer_t harness_to_adapter;  /* Harness writes, adapter reads */
    ring_buffer_t adapter_to_harness;  /* Adapter writes, harness reads */
} shm_region_t;

/* Transport context */
typedef struct {
    shm_region_t *shm;
    int shm_fd;
    sem_t *data_ready_sem;   /* Signals data available for recv */
    sem_t *space_avail_sem;  /* Signals space available for send */
    ring_buffer_t *recv_ring;
    ring_buffer_t *send_ring;
    char shm_name[64];
    int is_harness;  /* 1 if harness side, 0 if adapter side */
} shm_ctx_t;

/*
 * ring_available_read - Bytes available to read
 */
static inline uint32_t ring_available_read(ring_buffer_t *ring)
{
    uint32_t write_pos = ring->write_pos;
    uint32_t read_pos = ring->read_pos;

    if (write_pos >= read_pos) {
        return write_pos - read_pos;
    } else {
        return RING_BUFFER_SIZE - read_pos + write_pos;
    }
}

/*
 * ring_available_write - Space available for writing
 */
static inline uint32_t ring_available_write(ring_buffer_t *ring)
{
    return RING_BUFFER_SIZE - ring_available_read(ring) - 1;  /* -1 to distinguish full/empty */
}

/*
 * ring_read - Read bytes from ring buffer
 */
static uint32_t ring_read(ring_buffer_t *ring, void *buf, uint32_t len)
{
    uint32_t avail = ring_available_read(ring);
    if (len > avail) {
        len = avail;
    }

    uint32_t read_pos = ring->read_pos;
    uint32_t to_end = RING_BUFFER_SIZE - read_pos;

    if (len <= to_end) {
        /* Single contiguous read */
        memcpy(buf, ring->data + read_pos, len);
    } else {
        /* Wrap-around read */
        memcpy(buf, ring->data + read_pos, to_end);
        memcpy((uint8_t *)buf + to_end, ring->data, len - to_end);
    }

    ring->read_pos = (read_pos + len) % RING_BUFFER_SIZE;
    return len;
}

/*
 * ring_write - Write bytes to ring buffer
 */
static uint32_t ring_write(ring_buffer_t *ring, const void *buf, uint32_t len)
{
    uint32_t avail = ring_available_write(ring);
    if (len > avail) {
        len = avail;
    }

    uint32_t write_pos = ring->write_pos;
    uint32_t to_end = RING_BUFFER_SIZE - write_pos;

    if (len <= to_end) {
        /* Single contiguous write */
        memcpy(ring->data + write_pos, buf, len);
    } else {
        /* Wrap-around write */
        memcpy(ring->data + write_pos, buf, to_end);
        memcpy(ring->data, (const uint8_t *)buf + to_end, len - to_end);
    }

    ring->write_pos = (write_pos + len) % RING_BUFFER_SIZE;
    return len;
}

/*
 * sem_timedwait_compat - macOS-compatible timed semaphore wait
 *
 * macOS doesn't support sem_timedwait, so we use sem_trywait + nanosleep.
 */
static int sem_timedwait_compat(sem_t *sem, const struct timespec *abs_timeout)
{
#ifdef __APPLE__
    /* macOS: Use sem_trywait with polling */
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);

    while (1) {
        /* Try to acquire */
        if (sem_trywait(sem) == 0) {
            return 0;  /* Success */
        }

        if (errno != EAGAIN) {
            return -1;  /* Error */
        }

        /* Check timeout */
        clock_gettime(CLOCK_REALTIME, &now);
        if (now.tv_sec > abs_timeout->tv_sec ||
            (now.tv_sec == abs_timeout->tv_sec && now.tv_nsec >= abs_timeout->tv_nsec)) {
            errno = ETIMEDOUT;
            return -1;
        }

        /* Sleep 1ms before retry */
        struct timespec sleep_time = {0, 1000000};  /* 1ms */
        nanosleep(&sleep_time, NULL);
    }
#else
    /* Linux: Use native sem_timedwait */
    return sem_timedwait(sem, abs_timeout);
#endif
}

/*
 * shm_recv - Receive data with timeout
 */
static ssize_t shm_recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms)
{
    shm_ctx_t *shm = (shm_ctx_t *)ctx;

    /* Check if data already available */
    uint32_t avail = ring_available_read(shm->recv_ring);
    if (avail > 0) {
        uint32_t n = ring_read(shm->recv_ring, buf, (uint32_t)len);
        return (ssize_t)n;
    }

    /* Wait for sender to signal data ready */
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    ts.tv_sec += timeout_ms / 1000;
    ts.tv_nsec += (timeout_ms % 1000) * 1000000;
    if (ts.tv_nsec >= 1000000000) {
        ts.tv_sec += 1;
        ts.tv_nsec -= 1000000000;
    }

    if (sem_timedwait_compat(shm->data_ready_sem, &ts) < 0) {
        return (errno == ETIMEDOUT) ? CORTEX_ETIMEDOUT : -errno;
    }

    /* Data available now */
    avail = ring_available_read(shm->recv_ring);
    if (avail == 0) {
        return CORTEX_ECONNRESET;
    }

    uint32_t n = ring_read(shm->recv_ring, buf, (uint32_t)len);
    return (ssize_t)n;
}

/*
 * shm_send - Send data (blocking until space available)
 */
static ssize_t shm_send(void *ctx, const void *buf, size_t len)
{
    shm_ctx_t *shm = (shm_ctx_t *)ctx;
    uint32_t sent = 0;

    while (sent < len) {
        uint32_t avail = ring_available_write(shm->send_ring);
        if (avail == 0) {
            /* Buffer full - wait */
            continue;
        }

        uint32_t to_send = (uint32_t)(len - sent);
        uint32_t n = ring_write(shm->send_ring, (const uint8_t *)buf + sent, to_send);
        sent += n;

        /* Signal reader that data is ready */
        sem_post(shm->data_ready_sem);
    }

    return (ssize_t)sent;
}

/*
 * shm_close - Cleanup shared memory
 */
static void shm_close(void *ctx)
{
    shm_ctx_t *shm = (shm_ctx_t *)ctx;

    if (shm->shm) {
        munmap(shm->shm, sizeof(shm_region_t));
    }

    if (shm->shm_fd >= 0) {
        close(shm->shm_fd);
        if (shm->is_harness) {
            shm_unlink(shm->shm_name);
        }
    }

    if (shm->data_ready_sem != SEM_FAILED) {
        sem_close(shm->data_ready_sem);
        if (shm->is_harness) {
            /* Harness created h2a and a2h semaphores, so unlink them */
            char sem_name[128];
            snprintf(sem_name, sizeof(sem_name), "/cortex_sem_h2a_%s",
                     shm->shm_name + strlen("/cortex_shm_"));
            sem_unlink(sem_name);
        }
    }

    if (shm->space_avail_sem != SEM_FAILED) {
        sem_close(shm->space_avail_sem);
        if (shm->is_harness) {
            char sem_name[128];
            snprintf(sem_name, sizeof(sem_name), "/cortex_sem_a2h_%s",
                     shm->shm_name + strlen("/cortex_shm_"));
            sem_unlink(sem_name);
        }
    }

    free(shm);
}

/*
 * shm_get_timestamp_ns - Platform timestamp
 */
static uint64_t shm_get_timestamp_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/*
 * cortex_transport_shm_create_harness - Create harness side of SHM transport
 *
 * Creates shared memory region and semaphores.
 *
 * Args:
 *   name: Unique name for this transport (e.g., "cortex_adapter_0")
 *
 * Returns:
 *   Configured transport, or NULL on failure
 *
 * NOTE: Call this on harness side FIRST, then adapter side connects.
 */
cortex_transport_t *cortex_transport_shm_create_harness(const char *name)
{
    shm_ctx_t *shm = (shm_ctx_t *)calloc(1, sizeof(shm_ctx_t));
    if (!shm) {
        return NULL;
    }

    shm->shm_fd = -1;
    shm->data_ready_sem = SEM_FAILED;
    shm->space_avail_sem = SEM_FAILED;
    shm->is_harness = 1;
    snprintf(shm->shm_name, sizeof(shm->shm_name), "/cortex_shm_%s", name);

    /* Create shared memory */
    shm->shm_fd = shm_open(shm->shm_name, O_CREAT | O_RDWR, 0600);
    if (shm->shm_fd < 0) {
        perror("cortex_transport_shm_create_harness: shm_open failed");
        free(shm);
        return NULL;
    }

    if (ftruncate(shm->shm_fd, sizeof(shm_region_t)) < 0) {
        perror("cortex_transport_shm_create_harness: ftruncate failed");
        close(shm->shm_fd);
        shm_unlink(shm->shm_name);
        free(shm);
        return NULL;
    }

    shm->shm = (shm_region_t *)mmap(NULL, sizeof(shm_region_t),
                                     PROT_READ | PROT_WRITE, MAP_SHARED,
                                     shm->shm_fd, 0);
    if (shm->shm == MAP_FAILED) {
        perror("cortex_transport_shm_create_harness: mmap failed");
        close(shm->shm_fd);
        shm_unlink(shm->shm_name);
        free(shm);
        return NULL;
    }

    /* Initialize ring buffers */
    memset(shm->shm, 0, sizeof(shm_region_t));

    /* Create semaphores */
    char sem_name[128];
    snprintf(sem_name, sizeof(sem_name), "/cortex_sem_h2a_%s", name);
    shm->data_ready_sem = sem_open(sem_name, O_CREAT, 0600, 0);

    if (shm->data_ready_sem == SEM_FAILED) {
        perror("cortex_transport_shm_create_harness: sem_open(h2a) failed");
        munmap(shm->shm, sizeof(shm_region_t));
        close(shm->shm_fd);
        shm_unlink(shm->shm_name);
        free(shm);
        return NULL;
    }

    snprintf(sem_name, sizeof(sem_name), "/cortex_sem_a2h_%s", name);
    shm->space_avail_sem = sem_open(sem_name, O_CREAT, 0600, 0);

    if (shm->space_avail_sem == SEM_FAILED) {
        perror("cortex_transport_shm_create_harness: sem_open(a2h) failed");
        sem_close(shm->data_ready_sem);
        char sem_unlink_name[128];
        snprintf(sem_unlink_name, sizeof(sem_unlink_name), "/cortex_sem_h2a_%s", name);
        sem_unlink(sem_unlink_name);
        munmap(shm->shm, sizeof(shm_region_t));
        close(shm->shm_fd);
        shm_unlink(shm->shm_name);
        free(shm);
        return NULL;
    }

    /* Setup ring pointers (harness perspective) */
    shm->send_ring = &shm->shm->harness_to_adapter;
    shm->recv_ring = &shm->shm->adapter_to_harness;

    /* Allocate transport */
    cortex_transport_t *transport = (cortex_transport_t *)malloc(sizeof(cortex_transport_t));
    if (!transport) {
        shm_close(shm);
        return NULL;
    }

    transport->ctx = shm;
    transport->recv = shm_recv;
    transport->send = shm_send;
    transport->close = shm_close;
    transport->get_timestamp_ns = shm_get_timestamp_ns;

    return transport;
}

/*
 * cortex_transport_shm_create_adapter - Connect to existing SHM transport
 *
 * Connects to shared memory region created by harness.
 *
 * Args:
 *   name: Same name used by harness
 *
 * Returns:
 *   Configured transport, or NULL on failure
 */
cortex_transport_t *cortex_transport_shm_create_adapter(const char *name)
{
    shm_ctx_t *shm = (shm_ctx_t *)calloc(1, sizeof(shm_ctx_t));
    if (!shm) {
        return NULL;
    }

    shm->shm_fd = -1;
    shm->data_ready_sem = SEM_FAILED;
    shm->space_avail_sem = SEM_FAILED;
    shm->is_harness = 0;
    snprintf(shm->shm_name, sizeof(shm->shm_name), "/cortex_shm_%s", name);

    /* Open existing shared memory (use O_CREAT on macOS for compatibility) */
    shm->shm_fd = shm_open(shm->shm_name, O_CREAT | O_RDWR, 0600);
    if (shm->shm_fd < 0) {
        perror("cortex_transport_shm_create_adapter: shm_open failed");
        free(shm);
        return NULL;
    }

    /* Verify size matches expected (harness should have already set it) */
    struct stat sb;
    if (fstat(shm->shm_fd, &sb) < 0) {
        perror("cortex_transport_shm_create_adapter: fstat failed");
        close(shm->shm_fd);
        free(shm);
        return NULL;
    }

    if (sb.st_size == 0) {
        /* Harness hasn't set size yet - set it ourselves (macOS O_CREAT quirk) */
        if (ftruncate(shm->shm_fd, sizeof(shm_region_t)) < 0) {
            perror("cortex_transport_shm_create_adapter: ftruncate failed");
            close(shm->shm_fd);
            free(shm);
            return NULL;
        }
    } else if ((size_t)sb.st_size < sizeof(shm_region_t)) {
        /* Size too small - harness created wrong size */
        fprintf(stderr, "cortex_transport_shm_create_adapter: size too small (expected %zu, got %lld)\n",
                sizeof(shm_region_t), (long long)sb.st_size);
        close(shm->shm_fd);
        free(shm);
        return NULL;
    }
    /* Note: sb.st_size may be larger than sizeof(shm_region_t) due to page alignment - this is OK */

    shm->shm = (shm_region_t *)mmap(NULL, sizeof(shm_region_t),
                                     PROT_READ | PROT_WRITE, MAP_SHARED,
                                     shm->shm_fd, 0);
    if (shm->shm == MAP_FAILED) {
        perror("cortex_transport_shm_create_adapter: mmap failed");
        close(shm->shm_fd);
        free(shm);
        return NULL;
    }

    /* Open existing semaphores (harness must create them first)
     * Note: From adapter perspective:
     *   - data_ready_sem is for RECEIVING from harness (wait on h2a)
     *   - space_avail_sem is for SENDING to harness (wait on a2h if full)
     */
    char sem_name[128];

    /* Retry loop for harness to create semaphores */
    for (int retry = 0; retry < 10; retry++) {
        snprintf(sem_name, sizeof(sem_name), "/cortex_sem_h2a_%s", name);
        shm->data_ready_sem = sem_open(sem_name, 0);  /* Open existing only */

        snprintf(sem_name, sizeof(sem_name), "/cortex_sem_a2h_%s", name);
        shm->space_avail_sem = sem_open(sem_name, 0);  /* Open existing only */

        if (shm->data_ready_sem != SEM_FAILED && shm->space_avail_sem != SEM_FAILED) {
            break;  /* Success */
        }

        if (shm->data_ready_sem != SEM_FAILED) sem_close(shm->data_ready_sem);
        if (shm->space_avail_sem != SEM_FAILED) sem_close(shm->space_avail_sem);

        usleep(10000);  /* Wait 10ms and retry */
    }

    if (shm->data_ready_sem == SEM_FAILED || shm->space_avail_sem == SEM_FAILED) {
        perror("cortex_transport_shm_create_adapter: sem_open failed after retries");
        munmap(shm->shm, sizeof(shm_region_t));
        close(shm->shm_fd);
        free(shm);
        return NULL;
    }

    /* Setup ring pointers (adapter perspective - reversed from harness) */
    shm->recv_ring = &shm->shm->harness_to_adapter;
    shm->send_ring = &shm->shm->adapter_to_harness;

    /* Allocate transport */
    cortex_transport_t *transport = (cortex_transport_t *)malloc(sizeof(cortex_transport_t));
    if (!transport) {
        shm_close(shm);
        return NULL;
    }

    transport->ctx = shm;
    transport->recv = shm_recv;
    transport->send = shm_send;
    transport->close = shm_close;
    transport->get_timestamp_ns = shm_get_timestamp_ns;

    return transport;
}
