#ifndef CORTEX_SIGNAL_HANDLER_H
#define CORTEX_SIGNAL_HANDLER_H

/**
 * Install signal handlers for graceful shutdown on SIGINT (Ctrl+C) and SIGTERM.
 *
 * This function sets up handlers that set a shutdown flag when signals are
 * received, allowing the harness to clean up resources before exiting.
 *
 * Must be called early in main(), before starting any benchmark operations.
 */
void cortex_install_signal_handlers(void);

/**
 * Check if a shutdown signal (SIGINT or SIGTERM) has been received.
 *
 * Returns:
 *   1 if shutdown was requested
 *   0 otherwise
 *
 * This should be checked in the main benchmark loop to enable graceful
 * shutdown and proper cleanup of resources (replayer, telemetry, etc.).
 */
int cortex_should_shutdown(void);

#endif /* CORTEX_SIGNAL_HANDLER_H */
