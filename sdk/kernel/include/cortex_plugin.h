/*
 * CORTEX Plugin Interface (ABI v3)
 *
 * This header defines the C Application Binary Interface (ABI) between the
 * CORTEX benchmarking harness and kernel plugins.  Each kernel (e.g. CAR,
 * notch IIR, FIR band-pass, Goertzel, ICA) is built as a shared library and
 * exposes a small set of functions with C linkage.  The harness never
 * reads YAML directly—run configurations are parsed by the harness and
 * translated into the structures defined here.  Plugins receive only the
 * numeric runtime parameters and any kernel-specific configuration via
 * cortex_plugin_config_t.
 *
 * Design goals:
 *  - Simple and deterministic: no hidden allocations or blocking calls in
 *    process().
 *  - Forward compatible: the first two fields of cortex_plugin_config_t
 *    encode the ABI version and struct size so that new fields can be
 *    appended without breaking existing plugins.
 *  - Modality agnostic: while v1 targets EEG (Fs=160 Hz, W=160, H=80, C=64)
 *    this ABI can support other sampling rates, window sizes and channel
 *    counts.
 *  - Quantization aware: plugins can advertise supported numeric types
 *    (float32 today, Q15/Q7 in future versions) and allocate state/work
 *    buffers accordingly.
 *  - Simple initialization: init() returns both handle and output dimensions,
 *    eliminating the need for separate query functions.
 *  - Calibration support (v3): trainable kernels can export cortex_calibrate()
 *    for offline batch training, returning state that is passed to init().
 *
 * See docs/reference/plugin-interface.md for complete specification and
 * docs/architecture/abi_evolution.md for version history.
 */

#ifndef CORTEX_PLUGIN_H
#define CORTEX_PLUGIN_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>

/*
 * ABI version.  Increment this value when making breaking changes to
 * cortex_plugin_config_t or function signatures.  Plugins should refuse
 * initialization if the provided abi_version does not match this constant.
 *
 * Version History:
 *  - v1: Initial ABI with cortex_get_info()
 *  - v2: Eliminated get_info(), unified init/shape query
 *  - v3: Added calibration support (cortex_calibrate, capability flags)
 */
#define CORTEX_ABI_VERSION 3u

/*
 * Numeric data type supported by the plugin. Dtypes are
 * communicated in the config (desired dtype for this run).
 */
typedef enum {
    CORTEX_DTYPE_FLOAT32 = 1u << 0, /* 32-bit IEEE 754 floating point */
    CORTEX_DTYPE_Q15     = 1u << 1, /* 16-bit fixed-point (signed Q1.15) */
    CORTEX_DTYPE_Q7      = 1u << 2  /* 8-bit fixed-point (signed Q0.7) */
} cortex_dtype_bitmask_t;

/*
 * Kernel capability flags (v3+).
 *
 * Kernels advertise capabilities via cortex_init_result_t.capabilities.
 * Harness uses these flags to determine which optional functions exist.
 *
 * Design Note: Flags are future-proof for v4 (online adaptation) and v5 (hybrid).
 */
typedef enum {
    CORTEX_CAP_OFFLINE_CALIB  = 1u << 0,  /* Supports cortex_calibrate() - batch training */
    CORTEX_CAP_ONLINE_ADAPT   = 1u << 1,  /* Reserved for v4 - per-window adaptation */
    CORTEX_CAP_FEEDBACK_LEARN = 1u << 2,  /* Reserved for v5 - reinforcement learning */
} cortex_capability_flags_t;

/*
 * Generic configuration passed to cortex_init().  The harness fills this
 * structure from the run configuration (YAML) before calling any plugin
 * functions.  The struct may be extended in future revisions by
 * increasing struct_size and appending new fields; plugins must ignore
 * unknown trailing bytes.
 *
 * Extended in v3 with calibration_state fields (appended for backward compatibility).
 */
typedef struct {
    /* ========== ABI Handshake (v1+) ========== */
    uint32_t abi_version;   /* Must be CORTEX_ABI_VERSION (now 3) */
    uint32_t struct_size;   /* sizeof(cortex_plugin_config_t) supplied by harness */

    /* ========== Runtime Configuration (v1+) ========== */
    uint32_t sample_rate_hz;        /* Fs: samples per second (e.g., 160 Hz) */
    uint32_t window_length_samples; /* W: samples per window (e.g., 160) */
    uint32_t hop_samples;           /* H: samples to advance per window (e.g., 80) */
    uint32_t channels;              /* C: number of input channels (e.g., 64) */
    uint32_t dtype;                 /* One of cortex_dtype_bitmask_t values; only one bit should be set */
    uint8_t  allow_in_place;        /* Non-zero: process() may read/write the same buffer */
    uint8_t  reserved0[3];          /* Reserved for alignment/future flags */

    /* ========== Kernel Parameters (v1+) ========== */
    const void *kernel_params;      /* String: "param1: val1, param2: val2, ..." */
    uint32_t   kernel_params_size;  /* Size of parameters string in bytes */

    /* ========== Calibration State (v3+) ========== */
    const void *calibration_state;   /* Pre-trained state (e.g., ICA unmixing matrix W) */
    uint32_t calibration_state_size; /* Size of calibration_state in bytes */

    /* Future fields can be appended here.  Use struct_size to safely
     * determine how many bytes are available.  Do not remove or change
     * existing fields without bumping CORTEX_ABI_VERSION.
     */
} cortex_plugin_config_t;

/*
 * Result structure returned by cortex_init() containing both the plugin handle
 * and output dimensions.  The handle is NULL if initialization fails.
 *
 * Extended in v3 with capability flags (appended for backward compatibility).
 */
typedef struct {
    void *handle;                        /* Opaque instance handle (NULL on error) */
    uint32_t output_window_length_samples; /* Actual output W (may differ from input) */
    uint32_t output_channels;            /* Actual output C (may differ from input) */

    /* ========== Capability Flags (v3+) ========== */
    uint32_t capabilities;               /* Bitmask of cortex_capability_flags_t */
} cortex_init_result_t;

/*
 * Result structure returned by cortex_calibrate() (v3+).
 *
 * Contains trained state (e.g., ICA unmixing matrix, CSP filters, LDA weights).
 * Harness serializes this state to .cortex_state files for later use.
 */
typedef struct {
    void *calibration_state;       /* Opaque trained state (NULL on error) */
    uint32_t state_size_bytes;     /* Size of state for serialization */
    uint32_t state_version;        /* Kernel-specific state version (for evolution) */
} cortex_calibration_result_t;

/*
 * Calibrate kernel on batch data (optional - trainable kernels only, v3+).
 *
 * The harness provides multiple windows of calibration data. The kernel
 * performs batch training (e.g., FastICA, CSP eigendecomposition, LDA fit)
 * and returns learned state.
 *
 * If kernel doesn't export this symbol, harness assumes:
 * - Kernel is stateless (e.g., CAR, bandpass_fir), OR
 * - Kernel requires pre-calibrated state via config->calibration_state
 *
 * Parameters:
 *  - config: Same as cortex_init (channels, sample_rate, etc.)
 *  - calibration_data: Pointer to (num_windows × W × C) float32 array
 *  - num_windows: Number of windows in calibration data
 *
 * Returns:
 *  - {state, size, version} on success
 *  - {NULL, 0, 0} on failure (harness logs error)
 *
 * Constraints:
 *  - MAY allocate memory (this is a one-time operation)
 *  - MAY perform expensive computation (iterative convergence)
 *  - MUST be deterministic (same input → same output, for reproducibility)
 *  - MUST handle NaN inputs gracefully
 *
 * Design Notes:
 *  - This function is called ONCE per calibration session
 *  - Result is serialized to .cortex_state file
 *  - State format is kernel-specific (use state_version for evolution)
 *  - Harness detects this function via dlsym() at runtime
 */
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
);

/*
 * Initialize a plugin instance.
 *
 * The config->abi_version field must match CORTEX_ABI_VERSION and
 * config->struct_size must be at least sizeof(cortex_plugin_config_t).
 * The plugin validates the requested dtype and other parameters, allocates
 * persistent state based on config, and returns both a handle and output
 * dimensions.  If initialization fails (unsupported dtype/parameters or
 * allocation failure), the function returns {NULL, 0, 0, 0}.
 *
 * MODIFIED in v3: Now accepts optional calibration_state via config.
 * If config->calibration_state is non-NULL, kernel uses pre-trained state.
 * Otherwise, kernel may use hardcoded defaults or return error if calibration required.
 *
 * Parameters:
 *  - config: Pointer to configuration structure populated by the harness.
 *
 * Returns:
 *  - cortex_init_result_t containing handle, output dimensions, and capabilities.
 *    Handle is NULL on error.
 */
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);

/*
 * Process one window of data.  The harness guarantees that input and
 * output pointers point to non-overlapping buffers unless allow_in_place
 * was set in the config.  Buffers are tightly packed in row-major order
 * (channels × samples).  The plugin must not perform any heap
 * allocations, blocking I/O, or take excessive locks in this function.
 *
 * UNCHANGED from v2 - same signature and constraints.
 *
 * Parameters:
 *  - handle: The opaque instance pointer returned by cortex_init().
 *  - input:  Pointer to the input buffer of length
 *            config->window_length_samples × config->channels samples.
 *            The data type matches config->dtype.
 *  - output: Pointer to the output buffer.  Must have space for
 *            output_window_length_samples × output_channels samples
 *            of the same data type (as returned by cortex_init()).
 */
void cortex_process(void *handle, const void *input, void *output);

/*
 * Free all resources associated with a plugin instance.  After this
 * returns, the handle must not be used again.  The plugin must free
 * any memory it allocated in cortex_init().
 *
 * UNCHANGED from v2 - same signature and constraints.
 *
 * Parameters:
 *  - handle: The opaque instance pointer returned by cortex_init().
 */
void cortex_teardown(void *handle);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* CORTEX_PLUGIN_H */
