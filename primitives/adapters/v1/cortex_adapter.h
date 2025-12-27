/*
 * CORTEX Device Adapter Interface v1
 *
 * This header defines the device adapter ABI for running CORTEX kernels on
 * different hardware targets. Device adapters are primitives - once v1 is
 * released, this entire directory is frozen and immutable.
 *
 * Design goals:
 *  - Platform portability: same kernels run on x86, ARM, FPGA, ASIC
 *  - Minimal complexity: simple for end users, moderate for adapter developers
 *  - Forward compatible: struct size versioning enables future extensions
 *  - Measurement validity: clock metadata enables timestamp interpretation
 *  - Buffer reuse: single allocation in init(), reused across process_window()
 *
 * Adapter implementations handle:
 *  - Kernel loading (dlopen or static registry)
 *  - Memory management and buffer allocation
 *  - Timestamp generation with appropriate clock source
 *  - Optional capabilities (governor control, performance counters, etc.)
 *
 * See PROTOCOL.md for wire format specification.
 * See README.md for implementation examples.
 */

#ifndef CORTEX_ADAPTER_H
#define CORTEX_ADAPTER_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stddef.h>

/*
 * ABI version for adapter interface. Increment on breaking changes.
 */
#define CORTEX_ADAPTER_ABI_VERSION 1u

/*
 * ABI version discovery function (REQUIRED export for dlsym).
 * Returns the adapter ABI version this implementation was compiled against.
 * Harness uses dlsym() to discover this symbol before calling cortex_adapter_get_v1().
 */
uint32_t cortex_adapter_abi_version(void);

/*
 * Sentinel values for special cases
 */
#define CORTEX_TIMESTAMP_ADAPTER_STAMPS UINT64_MAX  /* Adapter will stamp t_in */
#define CORTEX_STRING_NULL_SENTINEL 0xFFFFFFFFu     /* NULL string encoding */

/*
 * Adapter capability flags (bitmask).
 * Bits 0-3 are defined in v1, bits 4+ reserved for future versions.
 */
typedef enum {
    CORTEX_CAP_GOVERNOR  = 1u << 0,  /* CPU frequency/governor control */
    CORTEX_CAP_PMC       = 1u << 1,  /* Performance counter access */
    CORTEX_CAP_REALTIME  = 1u << 2,  /* Real-time scheduling support */
    CORTEX_CAP_THERMAL   = 1u << 3,  /* Temperature sensor reading */
    /* Bits 4-31 reserved for future capabilities (e.g., energy in v2) */
} cortex_capability_flags_t;

/*
 * Timestamp structure with clock metadata.
 * Enables harness to interpret raw uint64_t values correctly.
 */
typedef struct {
    uint64_t value;         /* Raw timestamp value */
    uint64_t freq_hz;       /* 0 = nanoseconds, >0 = cycle counter frequency */
    const char *source;     /* Human-readable clock source ("CLOCK_MONOTONIC", "DWT_CYCCNT", etc.) */
} cortex_timestamp_t;

/* Forward declarations */
typedef struct cortex_adapter cortex_adapter_t;
typedef struct cortex_adapter_config cortex_adapter_config_t;
typedef struct cortex_adapter_result cortex_adapter_result_t;
typedef struct cortex_adapter_counters cortex_adapter_counters_t;

/*
 * Configuration passed to adapter->init().
 * The harness populates this from the run configuration.
 */
struct cortex_adapter_config {
    /* ABI handshake */
    uint32_t abi_version;   /* Must be CORTEX_ADAPTER_ABI_VERSION */
    uint32_t struct_size;   /* sizeof(cortex_adapter_config_t) from harness */

    /* Kernel loading - EXACTLY ONE must be non-NULL (XOR constraint) */
    const char *kernel_path;  /* Path to .so/.dylib for dlopen() */
    const char *kernel_id;    /* Static registry identifier */

    /* Runtime window configuration */
    uint32_t sample_rate_hz;        /* Fs: samples per second */
    uint32_t window_length_samples; /* W: samples per window */
    uint32_t hop_samples;           /* H: samples to advance per window */
    uint32_t channels;              /* C: number of input channels */
    uint32_t dtype;                 /* One of CORTEX_DTYPE_* (one-hot enforced) */

    /* Kernel-specific parameters (opaque to adapter) */
    const void *kernel_params;      /* Pointer to plugin-defined params structure */
    uint32_t kernel_params_size;    /* Size of kernel params in bytes */

    /* Timestamp control - if CORTEX_TIMESTAMP_ADAPTER_STAMPS, adapter stamps t_in */
    uint64_t t_in;                  /* Harness-provided or sentinel */

    /* Reserved for future fields - use struct_size to safely extend */
};

/*
 * Result structure returned by adapter->process_window().
 * Contains processed data and timing metadata.
 */
struct cortex_adapter_result {
    void *output;           /* Processed window data (owned by adapter until next call) */
    size_t output_bytes;    /* Size of output buffer in bytes */

    /* Timing metadata (all timestamps use adapter's clock domain) */
    uint64_t t_in;          /* Input arrival timestamp */
    uint64_t t_start;       /* Processing start timestamp */
    uint64_t t_end;         /* Processing end timestamp */
    uint64_t deadline;      /* Deadline timestamp (t_in + period) */

    /* Reserved for future fields */
};

/*
 * Performance counter snapshot (CORTEX_CAP_PMC capability).
 * Platform-specific - values are meaningful only in diff form.
 */
struct cortex_adapter_counters {
    uint64_t instructions;  /* Instructions retired */
    uint64_t cycles;        /* CPU cycles elapsed */
    uint64_t cache_misses;  /* Last-level cache misses */
    uint64_t branches;      /* Branch instructions */
    uint64_t branch_misses; /* Branch mispredictions */
    /* Reserved for future counters */
};

/*
 * Device adapter interface.
 * Adapters implement this struct and export via cortex_adapter_get_v1().
 */
struct cortex_adapter {
    /* Adapter identification (immutable after init) */
    const char *device_id;  /* e.g., "x86_64-linux-native", "stm32h7-cortex-m7" */
    const char *arch;       /* e.g., "x86_64", "armv7m", "riscv32" */
    const char *os;         /* e.g., "linux", "freertos", "baremetal" */

    /* Core functions (REQUIRED) */
    cortex_timestamp_t (*now)(void *ctx);
    int32_t (*init)(void *ctx, const cortex_adapter_config_t *cfg);
    int32_t (*process_window)(void *ctx, const void *in, size_t in_bytes,
                              cortex_adapter_result_t *out);
    void (*cleanup)(void *ctx);

    /* Capabilities (bitmask of cortex_capability_flags_t) */
    uint32_t capabilities;

    /* Optional capability hooks (non-NULL only if capability bit set) */
    int32_t (*set_governor)(void *ctx, const char *mode);
    int32_t (*read_counters)(void *ctx, cortex_adapter_counters_t *out);
    int32_t (*set_rt_priority)(void *ctx, int32_t priority);
    int32_t (*read_thermal)(void *ctx, float *temp_celsius);

    /* Adapter-specific context (opaque to harness) */
    void *context;

    /* Reserved for future function pointers - extend by appending */
};

/*
 * Adapter discovery function (REQUIRED export).
 * Each adapter .so/.dylib must export this symbol.
 *
 * Parameters:
 *  - out: pointer to cortex_adapter_t struct to populate
 *  - out_size: sizeof(cortex_adapter_t) from caller (for forward compat)
 *
 * Returns:
 *  - 0 on success
 *  - <0 on error (e.g., out_size too small, unsupported ABI version)
 *
 * Adapters should:
 *  1. Verify out_size >= sizeof(cortex_adapter_t) from adapter's perspective
 *  2. Populate all required fields (device_id, arch, os, core functions)
 *  3. Set capabilities bitmask and corresponding function pointers
 *  4. Initialize adapter context if needed
 */
int32_t cortex_adapter_get_v1(cortex_adapter_t *out, size_t out_size);

/*
 * HELLO message structure (wire protocol initialization).
 * Sent from adapter to harness during connection establishment.
 * Contains adapter metadata and clock configuration.
 */
typedef struct {
    /* Adapter identification (fixed-size for wire format) */
    char device_id[64];     /* Logical max, wire uses [length][bytes] */
    char arch[16];          /* Logical max, wire uses [length][bytes] */
    char os[32];            /* Logical max, wire uses [length][bytes] */

    /* Capabilities and protocol */
    uint32_t capabilities;      /* Bitmask of supported features */
    uint32_t protocol_version;  /* Wire protocol version (1 for v1) */

    /* Clock metadata for timestamp interpretation */
    uint64_t timestamp_freq_hz;  /* 0 = nanoseconds, >0 = cycle frequency */
    char timestamp_source[32];   /* "CLOCK_MONOTONIC", "DWT_CYCCNT", etc. */

    /* Reserved for future fields */
} cortex_hello_msg_t;

/*
 * LOAD_KERNEL command structure (wire protocol).
 * Harness sends this to adapter to initialize a kernel.
 */
typedef struct {
    /* Kernel loading - XOR constraint: exactly one must be non-NULL */
    char kernel_path[256];  /* Logical max, wire uses [length][bytes] or NULL sentinel */
    char kernel_id[64];     /* Logical max, wire uses [length][bytes] or NULL sentinel */

    /* Window configuration */
    uint32_t sample_rate_hz;
    uint32_t window_length_samples;
    uint32_t hop_samples;
    uint32_t channels;
    uint32_t dtype;

    /* Kernel parameters (opaque blob) */
    uint32_t kernel_params_size;
    uint8_t kernel_params[4096];  /* Logical max, wire uses actual size */

    /* Reserved for future fields */
} cortex_load_kernel_msg_t;

/*
 * PROCESS_WINDOW command structure (wire protocol).
 * Harness sends input window for processing.
 */
typedef struct {
    uint64_t t_in;          /* Input timestamp or CORTEX_TIMESTAMP_ADAPTER_STAMPS */
    uint32_t input_bytes;   /* Size of input buffer */
    /* Followed by input_bytes of raw data in wire format */
} cortex_process_window_msg_t;

/*
 * RESULT response structure (wire protocol).
 * Adapter sends processing results back to harness.
 */
typedef struct {
    uint32_t output_bytes;  /* Size of output buffer */
    uint64_t t_in;          /* Input timestamp (adapter's clock) */
    uint64_t t_start;       /* Processing start (adapter's clock) */
    uint64_t t_end;         /* Processing end (adapter's clock) */
    uint64_t deadline;      /* Deadline (adapter's clock) */
    /* Followed by output_bytes of raw data in wire format */
} cortex_result_msg_t;

/*
 * Buffer lifetime semantics:
 *
 * - Adapters MUST allocate buffers once in init() and reuse across process_window() calls
 * - cortex_adapter_result_t.output points to adapter-owned memory
 * - Buffer contents are valid until next process_window() OR cleanup()
 * - Harness MUST copy result data before next call
 * - Adapters MUST NOT free buffers until cleanup()
 *
 * This design enables zero-copy for local adapters while preserving
 * correctness for remote adapters with serialization overhead.
 */

/*
 * Clock domain consistency:
 *
 * - All timestamps (t_in, t_start, t_end, deadline) MUST use adapter->now()
 * - If t_in == CORTEX_TIMESTAMP_ADAPTER_STAMPS, adapter stamps input arrival
 * - Otherwise, harness provides t_in using adapter->now() from previous call
 * - Mixing clock domains (e.g., CLOCK_REALTIME vs CLOCK_MONOTONIC) breaks telemetry
 *
 * This ensures all timing measurements are comparable within a single run.
 */

/*
 * String encoding (wire protocol):
 *
 * - Fixed-size char arrays in structs are logical maxima
 * - Wire format uses [uint32_t length][bytes] with NO null terminator
 * - NULL strings encoded as length = CORTEX_STRING_NULL_SENTINEL (0xFFFFFFFF)
 * - Empty strings encoded as length = 0 (no following bytes)
 *
 * Example:
 *   char device_id[64] in struct → wire: [0x0000000A]["x86_native"]
 *   NULL kernel_path → wire: [0xFFFFFFFF] (no bytes follow)
 */

/*
 * XOR constraint validation (kernel loading):
 *
 * Adapters MUST verify exactly one of kernel_path or kernel_id is non-NULL:
 *
 *   if ((cfg->kernel_path == NULL) == (cfg->kernel_id == NULL)) {
 *       return -1; // Error: both NULL or both non-NULL
 *   }
 *
 * This prevents ambiguous kernel loading scenarios.
 */

/*
 * Dtype one-hot enforcement:
 *
 * Adapters SHOULD use cortex_dtype_size_bytes() from cortex_plugin.h:
 *
 *   size_t elem_size = cortex_dtype_size_bytes(cfg->dtype);
 *   if (elem_size == 0) {
 *       return -1; // Error: invalid dtype (not one-hot)
 *   }
 *
 * This prevents multiple dtype bits being set simultaneously.
 */

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* CORTEX_ADAPTER_H */
