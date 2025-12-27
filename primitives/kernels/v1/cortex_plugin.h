/*
 * CORTEX Plugin Interface
 *
 * This header defines the C Application Binary Interface (ABI) between the
 * CORTEX benchmarking harness and kernel plugins.  Each kernel (e.g. CAR,
 * notch IIR, FIR band‑pass, Goertzel) is built as a shared library and
 * exposes a small set of functions with C linkage.  The harness never
 * reads YAML directly—run configurations are parsed by the harness and
 * translated into the structures defined here.  Plugins receive only the
 * numeric runtime parameters and any kernel‑specific configuration via
 * cortex_plugin_config_t.
 *
 * Design goals:
 *  - Simple and deterministic: no hidden allocations or blocking calls in
 *    process().
 *  - Forward compatible: the first two fields of cortex_plugin_config_t
 *    encode the ABI version and struct size so that new fields can be
 *    appended without breaking existing plugins.
 *  - Modality agnostic: while v1 targets EEG (Fs=160 Hz, W=160, H=80, C=64)
 *    this ABI can support other sampling rates, window sizes and channel
 *    counts.
 *  - Quantization aware: plugins can advertise supported numeric types
 *    (float32 today, Q15/Q7 in future versions) and allocate state/work
 *    buffers accordingly.
 *  - Simple initialization: init() returns both handle and output dimensions,
 *    eliminating the need for separate query functions.
 *
 * See docs/PLUGIN_INTERFACE.md for a human‑readable description and
 * docs/RUN_CONFIG.md for how YAML fields map into this interface.
 */

 #ifndef CORTEX_PLUGIN_H
 #define CORTEX_PLUGIN_H
 
 #ifdef __cplusplus
 extern "C" {
 #endif
 
 #include <stdint.h>
 #include <stddef.h>  /* for size_t */

 /*
  * ABI version.  Increment this value when making breaking changes to
  * cortex_plugin_config_t or function signatures.  Plugins should refuse
  * initialization if the provided abi_version does not match this constant.
  */
 #define CORTEX_ABI_VERSION 2u

/*
 * ABI version function - real symbol for dlsym() discovery
 * Implementation in cortex_plugin_abi.c (compiled once at top level)
 *
 * Adapters call this function to verify kernel ABI compatibility.
 *
 * Returns: CORTEX_ABI_VERSION (currently 2)
 */
uint32_t cortex_plugin_abi_version(void);

/*
 * Numeric data type supported by the plugin. Dtypes are
 * communicated in the config (desired dtype for this run).
 */
typedef enum {
     CORTEX_DTYPE_FLOAT32 = 1u << 0, /* 32‑bit IEEE 754 floating point */
     CORTEX_DTYPE_Q15     = 1u << 1, /* 16‑bit fixed‑point (signed Q1.15) */
     CORTEX_DTYPE_Q7      = 1u << 2  /* 8‑bit fixed‑point (signed Q0.7) */
 } cortex_dtype_bitmask_t;

/*
 * Dtype size helper with one-hot enforcement
 * Used by adapters to compute buffer sizes
 *
 * Enforces exactly one dtype bit set (one-hot).
 * Returns: bytes per element, or 0 if invalid/multiple bits set
 */
static inline size_t cortex_dtype_size_bytes(uint32_t dtype) {
    /* Enforce exactly one dtype bit set (one-hot) */
    if (__builtin_popcount(dtype) != 1) {
        return 0; /* Error: must be exactly one dtype */
    }

    if (dtype == CORTEX_DTYPE_FLOAT32) return 4;
    if (dtype == CORTEX_DTYPE_Q15) return 2;
    if (dtype == CORTEX_DTYPE_Q7) return 1;
    return 0; /* Should never reach */
}
 
 /*
  * Generic configuration passed to cortex_init().  The harness fills this
  * structure from the run configuration (YAML) before calling any plugin
  * functions.  The struct may be extended in future revisions by
  * increasing struct_size and appending new fields; plugins must ignore
  * unknown trailing bytes.
  */
 typedef struct {
     /* ABI handshake */
     uint32_t abi_version;   /* must be CORTEX_ABI_VERSION */
     uint32_t struct_size;   /* sizeof(cortex_plugin_config_t) supplied by harness */
 
     /* Runtime configuration common to all kernels */
     uint32_t sample_rate_hz;        /* Fs: samples per second */
     uint32_t window_length_samples; /* W: samples per window */
     uint32_t hop_samples;           /* H: samples to advance per window */
     uint32_t channels;              /* C: number of input channels */
     uint32_t dtype;                 /* one of cortex_dtype_bitmask_t values; only one bit should be set */
     uint8_t  allow_in_place;        /* if non‑zero, process() may read/write the same buffer */
     uint8_t  reserved0[3];          /* reserved for alignment/future flags */
 
     /* Kernel‑specific parameters */
     const void *kernel_params;      /* pointer to plugin‑defined parameters structure */
     uint32_t   kernel_params_size;  /* size of the plugin‑defined parameters structure in bytes */
 
     /* Future fields can be appended here.  Use struct_size to safely
      * determine how many bytes are available.  Do not remove or change
      * existing fields without bumping CORTEX_ABI_VERSION.
      */
 } cortex_plugin_config_t;
 
/*
 * Result structure returned by cortex_init() containing both the plugin handle
 * and output dimensions.  The handle is NULL if initialization fails.
 */
typedef struct {
    void *handle;                        /* Opaque handle (NULL on error) */
    uint32_t output_window_length_samples;
    uint32_t output_channels;
} cortex_init_result_t;

/*
 * Initialize a plugin instance.
 *
 * The config->abi_version field must match CORTEX_ABI_VERSION and
 * config->struct_size must be at least sizeof(cortex_plugin_config_t).
 * The plugin validates the requested dtype and other parameters, allocates
 * persistent state based on config, and returns both a handle and output
 * dimensions.  If initialization fails (unsupported dtype/parameters or
 * allocation failure), the function returns {NULL, 0, 0}.
 *
 * Parameters:
 *  - config: pointer to configuration structure populated by the harness.
 *
 * Returns:
 *  - cortex_init_result_t containing handle and output dimensions.
 *    Handle is NULL on error.
 */
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
 
 /*
  * Process one window of data.  The harness guarantees that input and
  * output pointers point to non‑overlapping buffers unless allow_in_place
  * was set in the config.  Buffers are tightly packed in row‑major order
  * (channels × samples).  The plugin must not perform any heap
  * allocations, blocking I/O, or take excessive locks in this function.
  *
  * Parameters:
  *  - handle: the opaque instance pointer returned by cortex_init().
  *  - input:  pointer to the input buffer of length
  *            config->window_length_samples × config->channels samples.
  *            The data type matches config->dtype.
 *  - output: pointer to the output buffer.  Must have space for
 *            output_window_length_samples × output_channels samples
 *            of the same data type (as returned by cortex_init()).
 */
void cortex_process(void *handle, const void *input, void *output);
 
 /*
  * Free all resources associated with a plugin instance.  After this
  * returns, the handle must not be used again.  The plugin must free
  * any memory it allocated in cortex_init().
  *
  * Parameters:
  *  - handle: the opaque instance pointer returned by cortex_init().
  */
 void cortex_teardown(void *handle);
 
#ifdef __cplusplus
 } /* extern "C" */
 #endif
 
 #endif /* CORTEX_PLUGIN_H */