#ifndef CORTEX_DEVICE_COMM_H
#define CORTEX_DEVICE_COMM_H

#include <stddef.h>
#include <stdint.h>

/*
 * Device Communication Layer
 *
 * Manages lifecycle of device adapters (spawn, handshake, execute, teardown).
 * Adapters run as separate processes communicating via socketpair.
 *
 * Lifecycle:
 *   1. device_comm_init(): Spawn adapter, perform handshake
 *   2. device_comm_execute_window(): Send window, receive result (N times)
 *   3. device_comm_teardown(): Cleanup adapter process
 *
 * Error handling:
 *   - Timeouts detect adapter death/hangs
 *   - Session ID mismatch detects adapter restarts
 *   - All functions return 0 on success, <0 on error
 */

/* Opaque device handle */
typedef struct cortex_device_handle cortex_device_handle_t;

/*
 * Device initialization result
 *
 * Returned by device_comm_init() after successful handshake.
 * Contains device handle and output dimensions from ACK frame.
 */
typedef struct cortex_device_init_result {
    cortex_device_handle_t *handle;        /* Device handle (caller must teardown) */
    uint32_t output_window_length_samples; /* Output W from ACK (0 = use config) */
    uint32_t output_channels;              /* Output C from ACK (0 = use config) */
    char adapter_name[32];                 /* Adapter name from HELLO frame */
    char device_hostname[32];              /* Device hostname (from HELLO) */
    char device_cpu[32];                   /* Device CPU (from HELLO) */
    char device_os[32];                    /* Device OS (from HELLO) */
} cortex_device_init_result_t;

/*
 * Device timing (nanoseconds, device clock)
 *
 * Captured from RESULT frame. Allows measuring:
 * - Input latency: tin - harness send start
 * - Processing latency: tend - tstart
 * - Output latency: tlast_tx - tend
 * - End-to-end: tlast_tx - harness send start
 */
typedef struct {
    uint64_t tin;        /* Input complete timestamp (after final chunk) */
    uint64_t tstart;     /* Kernel process() invoked */
    uint64_t tend;       /* Kernel process() returned */
    uint64_t tfirst_tx;  /* First result byte transmitted */
    uint64_t tlast_tx;   /* Last result byte transmitted */
} cortex_device_timing_t;

/*
 * device_comm_init - Spawn adapter and perform complete handshake
 *
 * This function is ATOMIC and SYNCHRONOUS:
 *   1. Spawn adapter process (fork + exec)
 *   2. Create socketpair for bidirectional communication
 *   3. Receive HELLO frame (adapter capabilities)
 *   4. Send CONFIG frame (serializes calib_state into wire format)
 *   5. Receive ACK frame (with output dimensions)
 *
 * When this function returns successfully, all handshake frames have been
 * sent/received. Caller may safely free calib_state immediately after return.
 *
 * CONSTRAINT: Output dimensions are constant for the lifetime of this
 * device_handle. Dimensions cannot change per-window.
 *
 * Args:
 *   adapter_path:    Path to adapter binary (e.g., "primitives/adapters/v1/native/cortex_adapter_native")
 *                    Used only for local:// transport (spawns this binary)
 *   transport_config: Transport URI (e.g., "local://", "tcp://10.0.1.42:9000")
 *                     NULL or empty defaults to "local://"
 *   plugin_name:     Kernel to load (e.g., "noop@f32")
 *   plugin_params:   Kernel parameters (e.g., "f0_hz=60.0,Q=30.0")
 *   sample_rate_hz:  Sample rate (e.g., 160)
 *   window_samples:  Window length W (e.g., 160)
 *   hop_samples:     Hop length H (e.g., 80)
 *   channels:        Channel count C (e.g., 64)
 *   calib_state:     Calibration state bytes (NULL if not trainable) - COPIED by device_comm
 *   calib_state_size: Calibration state size (0 if not trainable)
 *   out_result:      Pointer to store init result (handle + output dims + adapter name)
 *
 * Returns:
 *    0: Success (adapter spawned and ready)
 *   <0: cortex_error_code_t (spawn failed, handshake timeout, etc.)
 *
 * IMPORTANT:
 *   - Caller must call device_comm_teardown() to cleanup handle
 *   - Adapter process runs until teardown or death
 *   - device_comm COPIES calib_state (caller owns and frees original)
 */
int device_comm_init(
    const char *adapter_path,
    const char *transport_config,
    const char *plugin_name,
    const char *plugin_params,
    uint32_t sample_rate_hz,
    uint32_t window_samples,
    uint32_t hop_samples,
    uint32_t channels,
    const void *calib_state,
    size_t calib_state_size,
    cortex_device_init_result_t *out_result
);

/*
 * device_comm_execute_window - Send window and receive result
 *
 * Steps:
 *   1. Send WINDOW as chunked frames (8KB chunks)
 *   2. Receive RESULT (output samples + timing)
 *   3. Validate session_id and sequence match
 *
 * Args:
 *   handle:          Device handle from device_comm_init()
 *   sequence:        Window sequence number (incrementing)
 *   input_samples:   Input window (W×C float32)
 *   window_samples:  Window length W
 *   channels:        Channel count C
 *   output_samples:  Output buffer (W×C float32)
 *   output_buf_size: Size of output buffer (bytes)
 *   out_timing:      Pointer to store device timing
 *
 * Returns:
 *    0: Success (result received and validated)
 *   <0: Error (timeout, session mismatch, etc.)
 *
 * IMPORTANT:
 *   - Blocks until RESULT received or timeout
 *   - Timeout indicates adapter death/hang
 *   - Session mismatch indicates adapter restart
 */
int device_comm_execute_window(
    cortex_device_handle_t *handle,
    uint32_t sequence,
    const float *input_samples,
    uint32_t window_samples,
    uint32_t channels,
    float *output_samples,
    size_t output_buf_size,
    cortex_device_timing_t *out_timing
);

/*
 * device_comm_teardown - Cleanup adapter process
 *
 * Steps:
 *   1. Close transport (adapter will detect EOF and exit)
 *   2. Wait for adapter process (reap zombie)
 *   3. Free device handle
 *
 * Args:
 *   handle: Device handle from device_comm_init()
 *
 * IMPORTANT:
 *   - Always call this to prevent zombie processes
 *   - Safe to call even if adapter already died
 */
void device_comm_teardown(cortex_device_handle_t *handle);

#endif /* CORTEX_DEVICE_COMM_H */
