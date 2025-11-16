#define _POSIX_C_SOURCE 200809L
#include "signal_handler.h"

#include <signal.h>
#include <stdio.h>

/**
 * Global shutdown flag.
 *
 * Using sig_atomic_t ensures atomic reads/writes from signal handler context.
 * The 'volatile' qualifier prevents compiler optimizations from caching the
 * value in registers across the signal handler boundary.
 *
 * This is safe according to POSIX signal handling requirements.
 */
static volatile sig_atomic_t g_shutdown_requested = 0;

/**
 * Signal handler for SIGINT and SIGTERM.
 *
 * Sets the shutdown flag to allow the main loop to exit gracefully.
 *
 * Note: We intentionally do minimal work here (just set a flag) because
 * most functions are not async-signal-safe and should not be called from
 * a signal handler context.
 */
static void signal_handler(int signum) {
    if (signum == SIGINT || signum == SIGTERM) {
        g_shutdown_requested = 1;
    }
}

void cortex_install_signal_handlers(void) {
    struct sigaction sa;

    /* Initialize sigaction struct */
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;  /* No special flags needed */

    /* Install handler for SIGINT (Ctrl+C) */
    if (sigaction(SIGINT, &sa, NULL) == -1) {
        perror("[harness] warning: failed to install SIGINT handler");
        /* Continue anyway - this is not fatal */
    }

    /* Install handler for SIGTERM (termination request) */
    if (sigaction(SIGTERM, &sa, NULL) == -1) {
        perror("[harness] warning: failed to install SIGTERM handler");
        /* Continue anyway - this is not fatal */
    }
}

int cortex_should_shutdown(void) {
    return g_shutdown_requested;
}
