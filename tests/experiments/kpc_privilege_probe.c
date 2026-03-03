/*
 * kpc_privilege_probe.c — Test whether unprivileged processes can read
 * kpc thread counters after a root process enables them system-wide.
 *
 * Run with: sudo ./kpc_privilege_probe
 *
 * This answers: "Can we use a root daemon to enable counters once,
 * then let unprivileged benchmark processes read their own counters?"
 *
 * Expected output shows PASS/FAIL for each privilege level.
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <dlfcn.h>
#include <unistd.h>
#include <sys/wait.h>

#define KPC_CLASS_FIXED_MASK        (1u << 0)
#define KPC_CLASS_CONFIGURABLE_MASK (1u << 1)
#define KPC_MAX_COUNTERS 32

/* Function pointer types */
typedef int (*kpc_force_all_ctrs_set_fn)(int);
typedef int (*kpc_set_counting_fn)(uint32_t);
typedef int (*kpc_set_thread_counting_fn)(uint32_t);
typedef int (*kpc_get_thread_counters_fn)(int, unsigned int, uint64_t *);
typedef uint32_t (*kpc_get_counter_count_fn)(uint32_t);

static kpc_force_all_ctrs_set_fn    kpc_force_all_ctrs_set;
static kpc_set_counting_fn          kpc_set_counting;
static kpc_set_thread_counting_fn   kpc_set_thread_counting;
static kpc_get_thread_counters_fn   kpc_get_thread_counters;
static kpc_get_counter_count_fn     kpc_get_counter_count;

static int load_kpc(void)
{
    void *h = dlopen("/System/Library/PrivateFrameworks/kperf.framework/kperf", RTLD_LAZY);
    if (!h) h = dlopen("/usr/lib/libkperf.dylib", RTLD_LAZY);
    if (!h) { fprintf(stderr, "Cannot load kperf: %s\n", dlerror()); return -1; }

    kpc_force_all_ctrs_set = (kpc_force_all_ctrs_set_fn)dlsym(h, "kpc_force_all_ctrs_set");
    kpc_set_counting       = (kpc_set_counting_fn)dlsym(h, "kpc_set_counting");
    kpc_set_thread_counting = (kpc_set_thread_counting_fn)dlsym(h, "kpc_set_thread_counting");
    kpc_get_thread_counters = (kpc_get_thread_counters_fn)dlsym(h, "kpc_get_thread_counters");
    kpc_get_counter_count   = (kpc_get_counter_count_fn)dlsym(h, "kpc_get_counter_count");

    if (!kpc_force_all_ctrs_set || !kpc_set_counting ||
        !kpc_set_thread_counting || !kpc_get_thread_counters ||
        !kpc_get_counter_count) {
        fprintf(stderr, "Failed to resolve kpc symbols\n");
        return -1;
    }
    return 0;
}

/* Do some work so counters have something to count */
static volatile uint64_t sink;
static void burn_cycles(void)
{
    uint64_t acc = 0;
    for (int i = 0; i < 10000000; i++) acc += (uint64_t)i * 7;
    sink = acc;
}

/* Try to read thread counters. Returns 0 on success with valid values. */
static int try_read_counters(const char *label)
{
    uint64_t before[KPC_MAX_COUNTERS] = {0};
    uint64_t after[KPC_MAX_COUNTERS] = {0};

    printf("\n--- %s (uid=%d, euid=%d) ---\n", label, getuid(), geteuid());

    /* Step 1: Try kpc_set_thread_counting */
    int rc = kpc_set_thread_counting(KPC_CLASS_FIXED_MASK);
    printf("  kpc_set_thread_counting: %s (rc=%d)\n", rc == 0 ? "OK" : "FAILED", rc);
    if (rc != 0) {
        printf("  RESULT: FAIL — cannot enable thread counting\n");
        return -1;
    }

    /* Step 2: Read baseline */
    uint32_t count = kpc_get_counter_count(KPC_CLASS_FIXED_MASK);
    printf("  counter_count: %u\n", count);
    if (count == 0 || count > KPC_MAX_COUNTERS) {
        printf("  RESULT: FAIL — invalid counter count\n");
        return -1;
    }

    rc = kpc_get_thread_counters(0, count, before);
    printf("  kpc_get_thread_counters (before): %s (rc=%d)\n", rc == 0 ? "OK" : "FAILED", rc);
    if (rc != 0) {
        printf("  RESULT: FAIL — cannot read counters\n");
        return -1;
    }

    /* Step 3: Do work */
    burn_cycles();

    /* Step 4: Read after */
    rc = kpc_get_thread_counters(0, count, after);
    printf("  kpc_get_thread_counters (after):  %s (rc=%d)\n", rc == 0 ? "OK" : "FAILED", rc);
    if (rc != 0) {
        printf("  RESULT: FAIL — cannot read counters after work\n");
        return -1;
    }

    /* Step 5: Check deltas */
    uint64_t cycles = after[0] - before[0];
    uint64_t insns  = after[1] - before[1];
    printf("  cycles:       %llu\n", cycles);
    printf("  instructions: %llu\n", insns);

    if (cycles > 0 && insns > 0) {
        printf("  IPC:          %.2f\n", (double)insns / (double)cycles);
        printf("  RESULT: PASS — valid counter deltas\n");
        return 0;
    } else {
        printf("  RESULT: FAIL — zero deltas (counters not counting)\n");
        return -1;
    }
}

int main(void)
{
    if (geteuid() != 0) {
        fprintf(stderr, "ERROR: Must run with sudo.\n");
        fprintf(stderr, "Usage: sudo ./kpc_privilege_probe\n");
        return 1;
    }

    if (load_kpc() != 0) return 1;

    uid_t real_uid = getuid();  /* The user who ran sudo */
    /* If run via `sudo`, SUDO_UID has the original user's UID */
    const char *sudo_uid_str = getenv("SUDO_UID");
    uid_t target_uid = sudo_uid_str ? (uid_t)atoi(sudo_uid_str) : real_uid;

    printf("=== kpc Privilege Probe ===\n");
    printf("Real UID: %d, Effective UID: %d, Target unprivileged UID: %d\n",
           getuid(), geteuid(), target_uid);

    /* Phase 1: Enable counters as root */
    printf("\n=== Phase 1: Root enables counters system-wide ===\n");

    int rc = kpc_force_all_ctrs_set(1);
    printf("  kpc_force_all_ctrs_set(1): %s (rc=%d)\n", rc == 0 ? "OK" : "FAILED", rc);
    if (rc != 0) {
        fprintf(stderr, "Cannot enable counters even as root!\n");
        return 1;
    }

    rc = kpc_set_counting(KPC_CLASS_FIXED_MASK);
    printf("  kpc_set_counting: %s (rc=%d)\n", rc == 0 ? "OK" : "FAILED", rc);
    if (rc != 0) {
        fprintf(stderr, "Cannot set counting even as root!\n");
        return 1;
    }

    /* Phase 2: Read counters as root (sanity check) */
    printf("\n=== Phase 2: Read counters as root (sanity check) ===\n");
    try_read_counters("Root process");

    /* Phase 3: Fork child, drop privileges, try to read counters */
    printf("\n=== Phase 3: Fork unprivileged child ===\n");

    pid_t pid = fork();
    if (pid < 0) {
        perror("fork");
        return 1;
    }

    if (pid == 0) {
        /* Child process — drop privileges */
        if (setuid(target_uid) != 0) {
            perror("setuid");
            _exit(1);
        }

        /* Reload kpc symbols in child (dlopen state inherited but be safe) */
        if (load_kpc() != 0) _exit(1);

        /* Test A: Can unprivileged child read thread counters? */
        int result = try_read_counters("Unprivileged child (counters already enabled)");

        /* Test B: What if we try kpc_force_all_ctrs_set as non-root? */
        printf("\n--- Bonus: Can unprivileged child call kpc_force_all_ctrs_set? ---\n");
        rc = kpc_force_all_ctrs_set(1);
        printf("  kpc_force_all_ctrs_set(1): %s (rc=%d)\n",
               rc == 0 ? "OK (surprising!)" : "FAILED (expected)", rc);

        _exit(result == 0 ? 0 : 1);
    }

    /* Parent waits for child */
    int status;
    waitpid(pid, &status, 0);

    printf("\n=== Summary ===\n");
    if (WIFEXITED(status) && WEXITSTATUS(status) == 0) {
        printf("VERDICT: Unprivileged counter reading WORKS.\n");
        printf("  → A root daemon can enable counters once,\n");
        printf("    then unprivileged processes read their own thread counters.\n");
        printf("  → The launchd daemon approach is VIABLE.\n");
    } else {
        printf("VERDICT: Unprivileged counter reading DOES NOT WORK.\n");
        printf("  → Each process needs root for the full kpc lifecycle.\n");
        printf("  → The launchd daemon approach is NOT viable.\n");
        printf("  → sudo every time is the only option on macOS.\n");
    }

    /* Clean up */
    kpc_force_all_ctrs_set(0);
    return 0;
}
