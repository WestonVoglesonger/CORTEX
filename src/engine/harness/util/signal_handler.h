#ifndef CORTEX_SIGNAL_HANDLER_H
#define CORTEX_SIGNAL_HANDLER_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Install signal handlers for graceful shutdown on SIGINT (Ctrl+C) and SIGTERM.
 *
 * This function sets up POSIX signal handlers that set a shutdown flag when
 * signals are received, allowing the harness to clean up resources before exiting.
 *
 * Implementation notes:
 * - Uses sigaction() for POSIX-compliant signal handling
 * - Handler is async-signal-safe (only sets a volatile sig_atomic_t flag)
 * - If sigaction() fails, prints a warning to stderr but continues
 * - Safe to call multiple times (reinstalls handlers)
 *
 * Must be called early in main(), before starting any benchmark operations.
 * Typically called immediately after telemetry initialization.
 *
 * Error handling:
 * - Does not return error codes (uses silent degradation)
 * - Prints warning to stderr if sigaction() fails
 * - Failure to install handlers means Ctrl+C will terminate immediately
 *   (default signal behavior) rather than gracefully
 */
void cortex_install_signal_handlers(void);

/**
 * Check if a shutdown signal (SIGINT or SIGTERM) has been received.
 *
 * Returns:
 *   1 if shutdown was requested (Ctrl+C pressed or SIGTERM received)
 *   0 otherwise
 *
 * This function is async-signal-safe and can be called from any context.
 * It should be checked at strategic points in the benchmark loop:
 * - Before starting each plugin
 * - After plugin execution fails
 * - Before report generation
 * - After report generation
 *
 * Once the shutdown flag is set, it cannot be reset. The harness must
 * exit and restart to run another benchmark after receiving a signal.
 *
 * Thread safety: Safe to call from multiple threads (reads volatile flag).
 */
int cortex_should_shutdown(void);

#ifdef __cplusplus
}
#endif

#endif /* CORTEX_SIGNAL_HANDLER_H */
