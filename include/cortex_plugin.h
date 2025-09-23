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
 *  - Discoverable: the harness can query basic metadata (name, version,
 *    supported dtypes, I/O shapes and memory requirements) without
 *    instantiating a plugin.
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
 
 /*
  * ABI version.  Increment this value when making breaking changes to
  * cortex_plugin_config_t or function signatures.  Plugins should refuse
  * initialization if the provided abi_version does not match this constant.
  */
 #define CORTEX_ABI_VERSION 1u
 
 /*
  * Numeric data type supported by the plugin. Dtypes are
  * communicated both in the config (desired dtype for this run) and
  * aggregated in cortex_plugin_info_t::supported_dtypes as a bitmask.
  */
 typedef enum {
     CORTEX_DTYPE_FLOAT32 = 1u << 0, /* 32‑bit IEEE 754 floating point */
     CORTEX_DTYPE_Q15     = 1u << 1, /* 16‑bit fixed‑point (signed Q1.15) */
     CORTEX_DTYPE_Q7      = 1u << 2  /* 8‑bit fixed‑point (signed Q0.7) */
 } cortex_dtype_bitmask_t;
 
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
  * Metadata describing a plugin’s capabilities.  Returned by
  * cortex_get_info() prior to instantiation.  All pointers must remain
  * valid for the lifetime of the plugin binary (static storage).  Fields
  * that are not applicable should be set to zero or NULL.
  */
 typedef struct {
     const char *name;          /* short name (e.g., "car", "notch_iir") */
     const char *description;   /* human‑readable description */
     const char *version;       /* semantic version string for this plugin */
 
     /* Supported dtypes bitmask; see cortex_dtype_bitmask_t. */
     uint32_t supported_dtypes;
 
     /* Input and output shapes.  For most kernels the input and output
      * shapes match (e.g., notch, car, FIR).  For kernels that produce
      * aggregated outputs (e.g., Goertzel bandpower), output_channels may
      * differ.  The harness allocates output buffers of size
      * output_window_length_samples × output_channels × sizeof(dtype). */
     uint32_t input_window_length_samples;
     uint32_t input_channels;
     uint32_t output_window_length_samples;
     uint32_t output_channels;
 
     /* Memory footprint hints.  These values help the harness pre‑allocate
      * state and scratch buffers.  state_bytes is the size of the plugin’s
      * persistent state per instance (allocated in cortex_init() and freed in
      * cortex_teardown()).  workspace_bytes is the transient scratch space
      * required in process(); if zero, the plugin allocates no per‑call
      * workspace. */
     uint32_t state_bytes;
     uint32_t workspace_bytes;
 
     /* Reserved for future extensions (e.g., supported window sizes,
      * quantization tolerances).  Set to zero/NULL. */
     const void *reserved[4];
 } cortex_plugin_info_t;
 
 /*
  * Initialize a plugin instance.
  *
  * The harness must call cortex_get_info() before calling cortex_init() to
  * verify that the plugin supports the requested dtype and shapes.  The
  * config->abi_version field must match CORTEX_ABI_VERSION and
  * config->struct_size must be at least sizeof(cortex_plugin_config_t).
  * The plugin may allocate persistent state based on config and return a
  * handle pointer.  If initialization fails (unsupported parameters or
  * allocation failure), the function should return NULL.
  *
  * Parameters:
  *  - config: pointer to configuration structure populated by the harness.
  *
  * Returns:
  *  - opaque handle pointer to be passed to process() and teardown(), or
  *    NULL on error.
  */
 void *cortex_init(const cortex_plugin_config_t *config);
 
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
  *            info.output_window_length_samples × info.output_channels
  *            samples of the same data type.
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
 
 /*
  * Retrieve static metadata about the plugin.  This function must be
  * callable at any time (even before cortex_init()) and must not
  * allocate or perform side effects.  All returned pointers must be
  * constant for the lifetime of the shared library.
  *
  * Returns:
  *  - cortex_plugin_info_t structure describing the plugin’s capabilities.
  */
 cortex_plugin_info_t cortex_get_info(void);
 
 #ifdef __cplusplus
 } /* extern "C" */
 #endif
 
 #endif /* CORTEX_PLUGIN_H */