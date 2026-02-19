# CORTEX System Specification v1.0

# PART II: CORE SPECIFICATIONS

This document contains the complete technical specifications for CORTEX v1.0 core components:

- **Section 3:** Plugin ABI Specification
- **Section 4:** Wire Protocol Specification  
- **Section 5:** Configuration Schema
- **Section 6:** Telemetry Format

---

# Section 3: Plugin ABI Specification

## 3. Plugin ABI Specification

### 3.1 ABI Versioning

**Overview**

The CORTEX Plugin ABI (Application Binary Interface) defines the contract between the benchmarking harness and kernel plugins. This specification documents **ABI 1.0**, the first production release. The ABI version mechanism enables forward compatibility while detecting incompatible changes at runtime.

**Normative Requirements**

A conformant CORTEX harness and kernel plugin MUST implement ABI version negotiation as follows:

The header file `sdk/kernel/include/cortex_plugin.h` SHALL define the ABI version constant:

```c
#define CORTEX_ABI_VERSION 3u
```

**Note**: While this specification designates the production release as **ABI 1.0** for documentation purposes, the header currently defines version 3 to maintain continuity with development builds. Future releases will align this constant with specification versioning.

Every `cortex_plugin_config_t` struct passed to a kernel plugin MUST include:

```c
typedef struct {
    uint32_t abi_version;    /* Must be CORTEX_ABI_VERSION */
    uint32_t struct_size;    /* sizeof(cortex_plugin_config_t) */
    /* ... additional fields ... */
} cortex_plugin_config_t;
```

A kernel plugin's `cortex_init()` function MUST:
- Read the `abi_version` field before accessing any other configuration data
- Return `{NULL, 0, 0, 0}` if `abi_version` does not match the plugin's expected version
- Read the `struct_size` field to determine which configuration fields are available
- Safely ignore unknown trailing bytes when `struct_size` exceeds the plugin's compiled struct size

A kernel plugin SHOULD accept a range of compatible ABI versions when backward compatibility is maintained. For example, a v2 kernel MAY accept both version 2 and version 3:

```c
if (config->abi_version < 2 || config->abi_version > 3) {
    fprintf(stderr, "[kernel] ERROR: ABI version mismatch\n");
    return (cortex_init_result_t){NULL, 0, 0, 0};
}
```

**Rationale**

Explicit version checking at runtime prevents subtle bugs that would arise from struct layout mismatches. The `struct_size` field enables forward compatibility: new fields can be appended to structs without breaking existing plugins, as long as:

1. New fields are added at the end of the struct
2. The `abi_version` is incremented only for breaking changes
3. Plugins check `struct_size` before accessing new fields

This design prioritizes **fail-fast validation** over silent corruption. A kernel plugin built against ABI v2 will explicitly reject a v1 harness config rather than misinterpreting struct fields.

**ABI Version History**

| Version | Status | Key Changes |
|---------|--------|-------------|
| 1 | Deprecated | Initial ABI with `cortex_get_info()` |
| 2 | Supported | Removed `cortex_get_info()`, unified `cortex_init()` return type |
| 3 (1.0) | Current | Added `cortex_calibrate()`, calibration state fields, capability flags |

**Implementation Note**

As of this specification's publication date, only 2 of 8 production kernels (ICA, CSP) implement ABI v3 calibration features. The remaining 6 kernels (CAR, bandpass_fir, goertzel, noop, notch_iir, welch_psd) remain at ABI v2 compatibility but set `capabilities = 0` to indicate no calibration support.

---

### 3.2 Core Functions

#### 3.2.1 cortex_init()

**Overview**

The `cortex_init()` function performs one-time initialization of a kernel plugin instance. It validates runtime configuration, allocates persistent state, computes output dimensions, and returns an opaque handle for subsequent processing calls. Initialization failures MUST be signaled by returning a NULL handle, causing the benchmark to abort before any timing measurements begin.

**Normative Requirements**

A conformant kernel plugin MUST implement `cortex_init()` with the following signature:

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
```

The `cortex_init_result_t` struct SHALL be defined as:

```c
typedef struct {
    void *handle;                           /* Opaque instance handle (NULL on error) */
    uint32_t output_window_length_samples;  /* Actual output W (may differ from input) */
    uint32_t output_channels;               /* Actual output C (may differ from input) */
    uint32_t capabilities;                  /* Bitmask of cortex_capability_flags_t */
} cortex_init_result_t;
```

The function SHALL perform the following operations in order:

1. **ABI Validation**: Verify `config->abi_version` matches the kernel's supported version(s)
2. **Struct Size Validation**: Verify `config->struct_size` is at least `sizeof(cortex_plugin_config_t)` for the kernel's ABI version
3. **Data Type Validation**: Verify `config->dtype` is supported by the kernel (reject unsupported types)
4. **Parameter Extraction**: Parse `config->kernel_params` string using the parameter accessor API
5. **State Allocation**: Allocate all persistent state needed for `cortex_process()` calls
6. **Calibration State Loading** (v3+ trainable kernels): If `config->calibration_state` is non-NULL, deserialize and load pre-trained state
7. **Output Shape Calculation**: Determine output dimensions based on kernel algorithm and input configuration

The function SHALL return:
- On **success**: A result struct with `handle` pointing to allocated state, `output_window_length_samples` and `output_channels` set to actual output dimensions, and `capabilities` indicating kernel features (or 0 for stateless kernels)
- On **failure**: A zero-initialized result struct: `{NULL, 0, 0, 0}`

The function MUST NOT:
- Allocate memory intended for use only during `cortex_process()` (use `alloca()` in `process()` instead)
- Perform blocking I/O operations
- Launch background threads
- Take more than 100 milliseconds to complete (guideline for embedded targets)

The function MUST handle edge cases gracefully:
- **NULL config pointer**: Return `{NULL, 0, 0, 0}`
- **Invalid dtype**: Log error to stderr and return `{NULL, 0, 0, 0}`
- **Allocation failure**: Free any partially-allocated resources and return `{NULL, 0, 0, 0}`
- **Missing calibration state** (trainable kernels): Log helpful error message and return `{NULL, 0, 0, 0}`

**Code Example**

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    /* 1. Validate ABI */
    if (!config) return result;
    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[kernel] ERROR: ABI version mismatch (expected %u, got %u)\n",
                CORTEX_ABI_VERSION, config->abi_version);
        return result;
    }
    if (config->struct_size < sizeof(cortex_plugin_config_t)) {
        fprintf(stderr, "[kernel] ERROR: Config struct too small\n");
        return result;
    }

    /* 2. Validate dtype */
    if (config->dtype != CORTEX_DTYPE_FLOAT32) {
        fprintf(stderr, "[kernel] ERROR: Unsupported dtype (only float32 supported)\n");
        return result;
    }

    /* 3. Allocate state */
    kernel_state_t *state = (kernel_state_t *)calloc(1, sizeof(kernel_state_t));
    if (!state) {
        fprintf(stderr, "[kernel] ERROR: Memory allocation failed\n");
        return result;
    }

    /* 4. Store configuration */
    state->channels      = config->channels;
    state->window_length = config->window_length_samples;
    state->sample_rate   = config->sample_rate_hz;

    /* 5. Parse kernel parameters (example) */
    const char *params = (const char *)config->kernel_params;
    double cutoff_hz = cortex_param_float(params, "cutoff_hz", 30.0);
    if (cutoff_hz <= 0.0 || cutoff_hz >= config->sample_rate_hz / 2.0) {
        fprintf(stderr, "[kernel] ERROR: cutoff_hz must be in (0, Nyquist)\n");
        free(state);
        return result;
    }
    state->cutoff_hz = cutoff_hz;

    /* 6. Initialize kernel-specific state */
    /* ... algorithm-specific setup ... */

    /* 7. Set output shape and capabilities */
    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;
    result.capabilities = 0;  /* No calibration support */

    return result;
}
```

**Rationale**

Separating initialization from processing enables several critical features:

1. **Fail-fast validation**: Invalid configurations are detected before any benchmark timing begins, preventing corrupted measurements.

2. **Deterministic processing**: By requiring all allocations in `init()`, the `process()` function can run with zero heap allocations, eliminating non-deterministic delays from memory allocation.

3. **Shape inference**: The harness can construct processing pipelines by chaining kernels (stage N input shape = stage N-1 output shape) without executing test data through the pipeline.

4. **Resource accounting**: The harness can measure total memory footprint by querying allocator state before and after `init()` calls.

5. **Multi-instance support**: A single kernel library can be loaded once and instantiated multiple times with different configurations, sharing code but maintaining separate state.

Requiring output shape to be returned (rather than queried via a separate function) reduces ABI surface area and eliminates a potential source of harness/kernel synchronization bugs.

---

#### 3.2.2 cortex_process()

**Overview**

The `cortex_process()` function implements the kernel's signal processing algorithm on a single window of data. This function is called repeatedly (potentially thousands of times per benchmark run) and is subject to strict performance and determinism constraints. All timing, energy, and latency measurements are based on executions of this function.

**Normative Requirements**

A conformant kernel plugin MUST implement `cortex_process()` with the following signature:

```c
void cortex_process(void *handle, const void *input, void *output);
```

**Parameters:**

- `handle`: The opaque instance pointer returned by `cortex_init()`. MUST NOT be NULL when called by harness.
- `input`: Pointer to input data buffer of size `window_length_samples × channels × sizeof(dtype)`. Data layout is **row-major** (time-major, interleaved channels): `input[t * C + c]` accesses channel `c` at time `t`.
- `output`: Pointer to output data buffer. Size MUST be `output_window_length_samples × output_channels × sizeof(dtype)` as specified in the `cortex_init()` result.

**Processing Constraints (CRITICAL for fair benchmarking):**

The function MUST NOT:
- Perform **heap allocations** (`malloc`, `calloc`, `realloc`, `new`, etc.). Use `alloca()` for small scratch buffers if needed.
- Perform **blocking I/O** (file, network, pipes)
- Acquire **locks** that could block (mutex, semaphore) except brief spinlocks for lock-free data structures
- Make **system calls** except for high-precision timing (`clock_gettime` on specific platforms)
- Access **global mutable state** (all state must be in `handle`)
- Modify **input buffer** unless `config->allow_in_place == 1` was set during initialization

The function MUST:
- Handle **NaN values** gracefully in input data (typical policy: treat as 0.0)
- Handle **NULL pointers** gracefully (check and return immediately if any parameter is NULL)
- Complete processing within the **deadline**: `hop_samples / sample_rate_hz` seconds (e.g., 500ms for 80 hop @ 160 Hz)
- Produce **deterministic output**: same input data → same output data (no random number generation without fixed seeds)

**Buffer Layouts:**

Input buffer layout (row-major, tightly packed):
```
Address  | Sample
---------|--------
input[0] | t=0, c=0
input[1] | t=0, c=1
...
input[C-1] | t=0, c=C-1
input[C] | t=1, c=0
...
```

Output buffer layout (same convention):
```
Address    | Sample
-----------|--------
output[0]  | t=0, c'=0
output[1]  | t=0, c'=1
...
```

where `c'` ranges over `output_channels` (which may differ from input `channels`).

**Code Example**

```c
void cortex_process(void *handle, const void *input, void *output) {
    /* Validate parameters */
    if (!handle || !input || !output) return;

    const kernel_state_t *state = (const kernel_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    const uint32_t W = state->window_length;
    const uint32_t C = state->channels;

    /* Process each time sample */
    for (uint32_t t = 0; t < W; t++) {
        /* Example: Common Average Reference (CAR) */
        /* 1. Compute mean across channels at time t, excluding NaNs */
        double sum = 0.0;
        int count = 0;

        for (uint32_t c = 0; c < C; c++) {
            float v = in[t * C + c];
            if (v == v) {  /* NaN check: NaN != NaN */
                sum += (double)v;
                ++count;
            }
        }

        if (count == 0) {
            /* All NaN → output zeros for this time sample */
            for (uint32_t c = 0; c < C; c++) {
                out[t * C + c] = 0.0f;
            }
            continue;
        }

        float mean = (float)(sum / (double)count);

        /* 2. Subtract mean; NaNs become 0 */
        for (uint32_t c = 0; c < C; c++) {
            float v = in[t * C + c];
            out[t * C + c] = (v == v) ? (v - mean) : 0.0f;
        }
    }
}
```

**Rationale**

The strict constraints on `cortex_process()` stem from the need for fair, reproducible benchmarking:

1. **Zero-allocation rule**: Heap allocations introduce non-deterministic latency (allocator lock contention, page faults, garbage collection). By prohibiting allocations, all memory access patterns are predictable and cache behavior is deterministic.

2. **No I/O rule**: I/O operations introduce orders-of-magnitude variance in latency (disk seek times, network round-trips). BCI signal processing must operate in real-time without external dependencies.

3. **Determinism requirement**: Oracle validation (comparing C kernel output to Python reference implementation) requires bit-exact reproducibility. Non-deterministic algorithms cannot be validated automatically.

4. **In-place restrictions**: Allowing in-place processing reduces memory bandwidth but requires explicit opt-in to prevent data corruption in pipeline scenarios where output feeds into another kernel's input.

5. **NaN handling**: Real EEG hardware can produce NaN values due to electrode disconnection, amplifier saturation, or preprocessing artifacts. Production BCI systems must degrade gracefully rather than crash or propagate NaN through the pipeline.

The row-major buffer layout matches NumPy's default array layout (`np.ndarray` with `order='C'`), enabling zero-copy interop with Python oracle implementations.

---

#### 3.2.3 cortex_cleanup()

**Overview**

The `cortex_cleanup()` function (also known as `cortex_teardown()` in implementation code) releases all resources associated with a plugin instance. This function is called once at benchmark completion or when a plugin instance is no longer needed.

**Normative Requirements**

A conformant kernel plugin MUST implement resource cleanup with the following signature:

```c
void cortex_teardown(void *handle);
```

**Note**: The implementation uses the name `cortex_teardown()` but this specification refers to it as cleanup to match broader software engineering terminology.

The function SHALL:
- Free **all memory** allocated in `cortex_init()`, including the state struct itself
- Free **all memory** allocated during calibration if `cortex_calibrate()` was called
- Handle **NULL handle** safely (check `handle != NULL` before dereferencing)
- Be **idempotent** where possible (safe to call multiple times on same handle, though not required by harness)
- Complete within **100 milliseconds** (guideline for embedded targets)

The function MUST NOT:
- Access **handle contents** after freeing the state struct
- Perform **blocking I/O** operations
- Call **exit()** or **abort()** (cleanup errors should be logged but not crash the harness)

**Code Example**

```c
void cortex_teardown(void *handle) {
    if (!handle) return;

    kernel_state_t *state = (kernel_state_t *)handle;
    
    /* Free any dynamically allocated sub-structures */
    if (state->filter_coefficients) {
        free(state->filter_coefficients);
        state->filter_coefficients = NULL;
    }
    
    if (state->delay_line) {
        free(state->delay_line);
        state->delay_line = NULL;
    }

    /* Free the state struct itself */
    free(state);
}
```

**Example (Trainable Kernel with Calibration State)**

```c
void cortex_teardown(void *handle) {
    if (!handle) return;

    ica_runtime_state_t *state = (ica_runtime_state_t *)handle;
    
    /* Free calibration-derived state */
    free(state->mean);          /* Channel means */
    free(state->W_unmix);       /* Unmixing matrix */
    
    /* Free the state struct */
    free(state);
}
```

**Rationale**

Explicit resource cleanup enables:

1. **Memory leak detection**: Benchmark harnesses can use memory profiling tools (Valgrind, AddressSanitizer) to verify that all allocated memory is freed, catching resource leaks in kernel implementations.

2. **Long-running benchmarks**: Batch processing of multiple datasets or parameter sweeps requires releasing resources between runs to prevent memory exhaustion.

3. **Graceful shutdown**: Embedded targets with limited resources need deterministic cleanup paths to avoid leaving the system in an inconsistent state.

4. **Testing**: Unit tests can instantiate kernels, run synthetic data, and verify cleanup without restarting the process.

The NULL-safety requirement prevents crashes when cleanup is called on error paths where initialization may have failed partway through.

The idempotency guideline (though not strictly required) helps prevent double-free bugs in complex harness error handling scenarios.

---

### 3.3 Calibration Extension

#### 3.3.1 cortex_calibrate()

**Overview**

The `cortex_calibrate()` function (optional, ABI v3+) performs offline batch training for trainable kernels such as ICA (Independent Component Analysis) and CSP (Common Spatial Patterns). This function is called **once** during a calibration session with multiple windows of training data, returning learned parameters (e.g., unmixing matrices, spatial filters) that are subsequently used by `cortex_process()` for real-time inference.

**Normative Requirements**

A trainable kernel MAY export `cortex_calibrate()` with the following signature:

```c
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
);
```

The `cortex_calibration_result_t` struct SHALL be defined as:

```c
typedef struct {
    void *calibration_state;       /* Opaque trained state (NULL on error) */
    uint32_t state_size_bytes;     /* Size of state for serialization */
    uint32_t state_version;        /* Kernel-specific state version (for evolution) */
} cortex_calibration_result_t;
```

**Parameters:**

- `config`: Same configuration struct as `cortex_init()`, containing `channels`, `sample_rate_hz`, `window_length_samples`, and algorithm parameters in `kernel_params`
- `calibration_data`: Pointer to `(num_windows × W × C)` array of type `float32`, where `W = config->window_length_samples` and `C = config->channels`. Data layout is row-major: `calibration_data[win * W * C + t * C + c]`.
- `num_windows`: Number of training windows (trials) provided

**Returns:**

- On **success**: `{state_ptr, size, version}` where `state_ptr` points to allocated calibration state (e.g., unmixing matrix), `size` is the byte count for serialization, and `version` is a kernel-specific format version (starts at 1)
- On **failure**: `{NULL, 0, 0}` with error logged to stderr

**Operational Constraints:**

The function MAY:
- Allocate **heap memory** (this is a one-time offline operation, not subject to real-time constraints)
- Perform **expensive computation** (iterative optimization, eigendecomposition, hundreds of iterations)
- Take **several seconds** to complete (acceptable for offline training)

The function MUST:
- Be **deterministic**: same `calibration_data` → same `calibration_state` output (use fixed RNG seeds if randomization is needed for algorithm initialization)
- Handle **NaN inputs** gracefully (typical policy: replace with 0.0 or skip affected windows)
- Validate `config->abi_version` matches expected version
- Log **progress information** to stderr for long-running calibrations (recommended: iteration count, convergence status)

The function MUST NOT:
- Modify **input data** (`calibration_data` is `const`)
- Perform **blocking I/O** beyond stderr logging
- Launch **background threads** (single-threaded execution required for determinism)

**Harness Detection:**

The harness detects calibration support via runtime symbol lookup:

```c
void *calib_fn = dlsym(plugin_handle, "cortex_calibrate");
if (calib_fn != NULL) {
    /* Kernel supports calibration */
    cortex_calibration_result_t result = 
        ((cortex_calibrate_fn)calib_fn)(config, data, num_windows);
} else {
    /* Kernel is stateless (e.g., CAR, FIR filter) */
    fprintf(stderr, "[harness] Kernel does not export cortex_calibrate\n");
}
```

Kernels that do not export this symbol are assumed to be either:
1. **Stateless** (e.g., CAR, bandpass FIR filter, noop)
2. **Stateful but non-trainable** (e.g., notch IIR with hardcoded coefficients)
3. **Requiring pre-calibrated state** via `config->calibration_state` in `cortex_init()`

**Code Example (ICA Calibration)**

```c
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
) {
    /* Validate ABI */
    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[ica] ERROR: ABI version mismatch\n");
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    const uint32_t W = config->window_length_samples;
    const uint32_t C = config->channels;
    const uint32_t total_samples = num_windows * W;

    fprintf(stderr, "[ica] Calibrating: %u windows × %u samples × %u channels\n",
            num_windows, W, C);

    /* Concatenate windows into [total_samples, C] matrix */
    float *X = malloc(total_samples * C * sizeof(float));
    if (!X) {
        fprintf(stderr, "[ica] ERROR: Memory allocation failed\n");
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    const float *windows = (const float *)calibration_data;
    for (uint32_t win = 0; win < num_windows; win++) {
        for (uint32_t t = 0; t < W; t++) {
            for (uint32_t c = 0; c < C; c++) {
                uint32_t src_idx = win * (W * C) + t * C + c;
                uint32_t dst_idx = (win * W + t) * C + c;
                X[dst_idx] = windows[src_idx];
            }
        }
    }

    /* Run FastICA algorithm (example - actual implementation is more complex) */
    float *W_unmix = malloc(C * C * sizeof(float));
    if (!W_unmix || fastica_train(X, total_samples, C, W_unmix) != 0) {
        free(X);
        free(W_unmix);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    free(X);

    /* Serialize state: W_unmix matrix (C×C float32 elements) */
    uint32_t state_size = C * C * sizeof(float);

    fprintf(stderr, "[ica] Calibration complete: %u bytes\n", state_size);

    return (cortex_calibration_result_t){
        .calibration_state = W_unmix,
        .state_size_bytes = state_size,
        .state_version = 1  /* ICA state format v1 */
    };
}
```

**Rationale**

Separating calibration from inference enables:

1. **Offline training**: Expensive algorithms (FastICA: 200 iterations × eigendecomposition per iteration) can run once during setup rather than polluting real-time latency measurements.

2. **Reproducible benchmarks**: Calibration state can be saved to `.cortex_state` files and version-controlled, ensuring identical kernel parameterization across different benchmark runs and different machines.

3. **Oracle validation**: Python reference implementations can perform the same calibration and save state in the same format, enabling automated validation that C and Python implementations converge to the same solution.

4. **Deployment optimization**: Pre-calibrated kernels can be deployed to embedded targets without requiring the target hardware to perform expensive training (which may exceed memory or compute capacity).

5. **Hyperparameter sweeps**: Researchers can calibrate multiple instances with different algorithm parameters (e.g., ICA iteration count, CSP component count) and compare benchmark performance.

The determinism requirement is critical for reproducibility: running calibration twice on the same data must produce bit-identical state to enable differential debugging and regression testing.

---

#### 3.3.2 State Serialization Format

**Overview**

Calibration state is persisted to `.cortex_state` files using a binary format with a fixed header followed by kernel-specific data. This format enables cross-platform portability, version evolution, and integrity checking.

**Normative Requirements**

A `.cortex_state` file MUST begin with a 16-byte header defined as follows:

```c
struct cortex_state_header {
    uint32_t magic;         /* MUST be 0x434F5254 ("CORT" in ASCII, little-endian) */
    uint32_t abi_version;   /* ABI version that produced this state (currently 3) */
    uint32_t state_version; /* Kernel-specific state format version */
    uint32_t data_size;     /* Size of following data in bytes */
};
```

All multi-byte integers SHALL be encoded in **little-endian** byte order (matches x86-64, ARM64, and RISC-V little-endian modes).

The header SHALL be followed immediately by `data_size` bytes of kernel-specific calibration data. The interpretation of this data is determined by:
- The kernel name (from filename or external metadata)
- The `state_version` field (allows kernel authors to evolve state formats over time)

**File Naming Convention:**

State files SHALL be stored at:
```
primitives/datasets/v{version}/{dataset}/calibration_states/{kernel}_{method}.cortex_state
```

Examples:
```
primitives/datasets/v1/physionet-motor-imagery/calibration_states/ica_fastica.cortex_state
primitives/datasets/v1/physionet-motor-imagery/calibration_states/csp_default.cortex_state
```

**Validation Requirements:**

A harness loading a `.cortex_state` file MUST:
- Verify `magic == 0x434F5254` (reject file if mismatch)
- Verify `abi_version` matches harness ABI version (reject if incompatible)
- Verify `data_size > 0` and `data_size` does not exceed file size minus header size
- Allocate exactly `data_size` bytes for calibration state
- Pass `state_version` to the kernel (kernel MAY reject incompatible versions)

A kernel's `cortex_init()` receiving calibration state SHOULD:
- Validate `state_version` matches expected format(s)
- Validate `config->calibration_state_size` matches expected size for the kernel's channel count
- Return `{NULL, 0, 0, 0}` with helpful error message if validation fails

**Binary Layout Example (ICA with 64 channels):**

```
Offset | Size  | Field               | Value
-------|-------|---------------------|----------
0x00   | 4     | magic               | 0x434F5254
0x04   | 4     | abi_version         | 3
0x08   | 4     | state_version       | 1 (ICA state format v1)
0x0C   | 4     | data_size           | 16384 (64×64×4 bytes)
0x10   | 16384 | W matrix            | float32[64][64] row-major
```

Total file size: 16 + 16384 = 16400 bytes

**Loading API (Harness-Side)**

The harness SHALL provide the following utility function for loading state files:

```c
void* cortex_load_calibration_state(
    const char *path,
    uint32_t *size_out,
    uint32_t *version_out
);
```

**Returns:**
- Pointer to allocated calibration state data (caller must free)
- Sets `*size_out` to `data_size` from header
- Sets `*version_out` to `state_version` from header
- Returns NULL on error (invalid magic, read failure, allocation failure)

**Saving API (Harness-Side)**

The harness SHALL provide the following utility function for saving state files:

```c
int cortex_save_calibration_state(
    const char *path,
    const void *state,
    uint32_t size,
    uint32_t version
);
```

**Returns:**
- `0` on success
- `-1` on error (file creation failure, write failure)

**Code Example (Saving State)**

```c
int cortex_save_calibration_state(
    const char *path,
    const void *state,
    uint32_t size,
    uint32_t version
) {
    FILE *f = fopen(path, "wb");
    if (!f) {
        fprintf(stderr, "[harness] ERROR: Cannot create %s\n", path);
        return -1;
    }

    /* Write header */
    struct cortex_state_header header = {
        .magic = 0x434F5254,
        .abi_version = CORTEX_ABI_VERSION,
        .state_version = version,
        .data_size = size
    };

    if (fwrite(&header, sizeof(header), 1, f) != 1) {
        fclose(f);
        return -1;
    }

    /* Write data */
    if (fwrite(state, size, 1, f) != 1) {
        fclose(f);
        return -1;
    }

    fclose(f);
    return 0;
}
```

**Code Example (Loading State)**

```c
void* cortex_load_calibration_state(
    const char *path,
    uint32_t *size_out,
    uint32_t *version_out
) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;

    /* Read header */
    struct cortex_state_header header;
    if (fread(&header, sizeof(header), 1, f) != 1) {
        fclose(f);
        return NULL;
    }

    /* Validate magic */
    if (header.magic != 0x434F5254) {
        fprintf(stderr, "[harness] ERROR: Invalid magic in %s\n", path);
        fclose(f);
        return NULL;
    }

    /* Validate ABI version */
    if (header.abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[harness] WARNING: State ABI mismatch: file=%u, expected=%u\n",
                header.abi_version, CORTEX_ABI_VERSION);
        /* Continue anyway - kernel will validate state_version */
    }

    /* Allocate and load data */
    void *data = malloc(header.data_size);
    if (!data) {
        fclose(f);
        return NULL;
    }

    if (fread(data, header.data_size, 1, f) != 1) {
        free(data);
        fclose(f);
        return NULL;
    }

    fclose(f);
    *size_out = header.data_size;
    *version_out = header.state_version;
    return data;
}
```

**Rationale**

The binary format with versioning enables:

1. **Cross-platform deployment**: State calibrated on a high-performance server (x86-64) can be loaded on an embedded ARM target, as long as both use little-endian byte order (covers 99% of modern architectures).

2. **State format evolution**: Kernels can improve calibration algorithms over time (e.g., ICA v1: dense matrix, ICA v2: sparse matrix + metadata) while maintaining backward compatibility by checking `state_version`.

3. **Integrity checking**: The magic number prevents accidentally loading binary files that are not CORTEX state files (e.g., raw data files, model checkpoints from other frameworks).

4. **Fast loading**: Binary format loads orders of magnitude faster than text-based formats (JSON, YAML) for large matrices (64×64 float32 = 16KB).

5. **Exact reproducibility**: Binary serialization of IEEE 754 floats preserves bit-exact values, unlike text formats which introduce rounding errors during decimal conversion.

The little-endian requirement is a pragmatic choice: all major BCI target platforms (x86-64, ARM Cortex-A/R, RISC-V) default to little-endian. Big-endian platforms (PowerPC, SPARC) can byte-swap during load if needed (not currently implemented).

---

### 3.4 Memory Model

**Overview**

The CORTEX plugin ABI enforces a strict memory model to ensure deterministic performance and enable fair benchmarking. All memory allocations follow a **zero-allocation-in-hot-path** principle: state is allocated once during initialization and reused across all processing calls.

**Normative Requirements**

**State Ownership:**

Memory allocated in `cortex_init()` SHALL be:
- **Owned by the kernel**: The harness does not access or free this memory
- **Persistent**: Valid for the lifetime of the plugin instance (from `init()` return until `teardown()` call)
- **Thread-local**: Not shared between concurrent plugin instances (harness guarantees no concurrent calls to `process()` on the same handle)

Memory allocated in `cortex_calibrate()` SHALL be:
- **Returned to harness**: The `calibration_state` pointer in the result struct becomes owned by the harness
- **Serializable**: Must be a contiguous buffer of `state_size_bytes` that can be written to disk
- **Freed by harness**: The harness is responsible for calling `free(calibration_state)` after serialization

**Allocation Constraints:**

`cortex_init()` MAY:
- Allocate heap memory via `malloc()`, `calloc()`, `realloc()`
- Allocate memory proportional to input parameters (e.g., `channels × window_length × sizeof(float)` for delay lines)
- Fail gracefully by returning `{NULL, 0, 0, 0}` if allocation fails

`cortex_process()` MUST NOT:
- Call `malloc()`, `calloc()`, `realloc()`, or `free()`
- Call C++ `new` or `delete` operators
- Allocate via higher-level libraries (e.g., `std::vector::push_back()` may allocate)

`cortex_process()` MAY:
- Use `alloca()` for small scratch buffers (guideline: < 4KB to avoid stack overflow)
- Use static/global buffers if absolutely necessary (DISCOURAGED: breaks thread safety)

`cortex_teardown()` MUST:
- Free all memory allocated in `cortex_init()`
- NOT access memory after freeing

**Alignment Requirements:**

Buffers passed to `cortex_process()` SHALL be:
- Aligned to at least **64-byte boundaries** (enables SIMD operations: AVX-512, NEON)
- Padded to multiples of 64 bytes (harness responsibility)

Kernels SHOULD:
- Align internal state buffers to 64 bytes for optimal cache line utilization
- Use `aligned_alloc(64, size)` or `posix_memalign()` for SIMD-optimized buffers

**Memory Safety:**

Kernels MUST:
- NOT write beyond allocated buffer bounds (use `window_length × channels` limits)
- NOT read uninitialized memory (harness zero-initializes output buffers, but kernels should not rely on this)
- Validate array indices before access (check `t < window_length`, `c < channels`)

**Code Example (State Allocation with Alignment)**

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    kernel_state_t *state = calloc(1, sizeof(kernel_state_t));
    if (!state) return (cortex_init_result_t){0};

    state->window_length = config->window_length_samples;
    state->channels = config->channels;

    /* Allocate 64-byte aligned delay line for SIMD processing */
    size_t delay_size = config->window_length_samples * config->channels * sizeof(float);
    
#if defined(__APPLE__) || defined(__linux__)
    if (posix_memalign((void**)&state->delay_line, 64, delay_size) != 0) {
        free(state);
        return (cortex_init_result_t){0};
    }
#else
    state->delay_line = aligned_alloc(64, delay_size);
    if (!state->delay_line) {
        free(state);
        return (cortex_init_result_t){0};
    }
#endif

    memset(state->delay_line, 0, delay_size);  /* Zero-initialize */

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = config->window_length_samples,
        .output_channels = config->channels,
        .capabilities = 0
    };
}
```

**Code Example (Scratch Buffer with alloca)**

```c
void cortex_process(void *handle, const void *input, void *output) {
    const kernel_state_t *state = (const kernel_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    /* Allocate temporary buffer on stack (< 4KB guideline) */
    const uint32_t C = state->channels;
    float *means = (float *)alloca(C * sizeof(float));

    /* Compute per-channel means */
    for (uint32_t c = 0; c < C; c++) {
        double sum = 0.0;
        for (uint32_t t = 0; t < state->window_length; t++) {
            sum += in[t * C + c];
        }
        means[c] = (float)(sum / state->window_length);
    }

    /* Process data using computed means */
    for (uint32_t t = 0; t < state->window_length; t++) {
        for (uint32_t c = 0; c < C; c++) {
            out[t * C + c] = in[t * C + c] - means[c];
        }
    }
}
```

**Rationale**

The zero-allocation-in-hot-path principle enables:

1. **Deterministic latency**: Heap allocations introduce unbounded delays (allocator lock contention, page faults, cache evictions). By eliminating allocations, processing latency becomes predictable and suitable for real-time BCI applications.

2. **Fair benchmarking**: Memory allocation performance varies drastically across platforms (jemalloc vs. glibc malloc vs. tcmalloc). Measuring pure algorithm performance requires isolating memory allocation from processing.

3. **Cache optimization**: Pre-allocated buffers enable predictable cache access patterns. The harness can use techniques like cache warming and NUMA-aware allocation.

4. **Memory leak detection**: With allocation restricted to `init()`, memory leak detection tools (Valgrind, ASan) can trivially verify that all allocated memory is freed in `teardown()`.

5. **Embedded deployment**: Embedded BCI systems often use static memory partitioning. The initialization-only allocation model maps naturally to static allocation strategies.

The 64-byte alignment requirement matches modern CPU cache line sizes (x86-64: 64 bytes, ARM Cortex-A: 64 bytes) and SIMD register widths (AVX-512: 512 bits = 64 bytes). Aligning data structures to cache lines prevents false sharing and maximizes memory bandwidth.

---

### 3.5 Data Types

**Overview**

The CORTEX ABI defines a set of numeric data types optimized for embedded signal processing. The type system supports both floating-point and fixed-point representations, enabling deployment on platforms with and without hardware floating-point units.

**Normative Requirements**

**Data Type Enumeration:**

```c
typedef enum {
    CORTEX_DTYPE_FLOAT32 = 1u << 0,  /* 32-bit IEEE 754 floating point */
    CORTEX_DTYPE_Q15     = 1u << 1,  /* 16-bit fixed-point (signed Q1.15) */
    CORTEX_DTYPE_Q7      = 1u << 2   /* 8-bit fixed-point (signed Q0.7) */
} cortex_dtype_bitmask_t;
```

These are **bitmask values** (powers of 2), allowing kernels to advertise multiple supported types. However, the `config->dtype` field passed to `cortex_init()` SHALL contain exactly one bit set, indicating the runtime type for this benchmark run.

**CORTEX_DTYPE_FLOAT32:**

- **Encoding**: IEEE 754 single-precision binary floating-point
- **Range**: Approximately ±3.4 × 10³⁸ (finite values)
- **Precision**: ~7 decimal digits
- **Size**: 4 bytes
- **Alignment**: SHOULD be 4-byte aligned, MAY be 64-byte aligned for SIMD
- **Special values**: Supports NaN (Not-a-Number), ±Infinity, signed zero
- **Usage**: Primary type for all current kernel implementations

**Implementation Status**: All 8 production kernels (car@f32, bandpass_fir@f32, csp@f32, goertzel@f32, ica@f32, noop@f32, notch_iir@f32, welch_psd@f32) implement `CORTEX_DTYPE_FLOAT32` exclusively as of this specification's publication date.

**CORTEX_DTYPE_Q15:**

- **Encoding**: Signed 16-bit fixed-point with 1 integer bit and 15 fractional bits (Q1.15 format)
- **Range**: [-1.0, 0.9999694824] (−2¹⁵/2¹⁵ to (2¹⁵−1)/2¹⁵)
- **Precision**: 2⁻¹⁵ ≈ 3.05 × 10⁻⁵
- **Size**: 2 bytes
- **Usage**: Designed for embedded platforms without FPU (Cortex-M0/M3)

**Implementation Status**: Defined in ABI but no production kernels implement Q15 as of this specification's publication date. Future work.

**CORTEX_DTYPE_Q7:**

- **Encoding**: Signed 8-bit fixed-point with 0 integer bits and 7 fractional bits (Q0.7 format)
- **Range**: [-1.0, 0.9921875] (−2⁷/2⁷ to (2⁷−1)/2⁷)
- **Precision**: 2⁻⁷ ≈ 0.0078125
- **Size**: 1 byte
- **Usage**: Designed for extreme memory-constrained platforms or as input/output quantization for neural network kernels

**Implementation Status**: Defined in ABI but no production kernels implement Q7 as of this specification's publication date. Experimental feature.

**Type Validation:**

A kernel plugin's `cortex_init()` function MUST:
- Check that exactly one bit is set in `config->dtype` (reject if multiple bits set)
- Return `{NULL, 0, 0, 0}` if the requested dtype is not supported
- Log a helpful error message to stderr indicating which types are supported

**Code Example (Type Validation)**

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    /* Validate that exactly one dtype bit is set */
    if (__builtin_popcount(config->dtype) != 1) {
        fprintf(stderr, "[kernel] ERROR: Invalid dtype (multiple bits set: 0x%x)\n",
                config->dtype);
        return (cortex_init_result_t){0};
    }

    /* Check supported dtype */
    if (config->dtype != CORTEX_DTYPE_FLOAT32) {
        fprintf(stderr, "[kernel] ERROR: Unsupported dtype (0x%x)\n", config->dtype);
        fprintf(stderr, "[kernel] This kernel only supports CORTEX_DTYPE_FLOAT32\n");
        return (cortex_init_result_t){0};
    }

    /* ... rest of initialization ... */
}
```

**IEEE 754 Compliance:**

Kernels using `CORTEX_DTYPE_FLOAT32` SHALL:
- Conform to IEEE 754-2008 binary32 arithmetic rules
- Handle **NaN propagation**: `NaN + x = NaN`, `NaN * x = NaN`
- Handle **Infinity**: `±Infinity` MAY be treated as saturated values or replaced with zero (kernel-dependent policy, must be documented)
- NOT rely on specific NaN payloads (NaN equality testing: `x != x` is true if `x` is NaN)

**Capability Flags (v3+):**

While not strictly data types, capability flags indicate kernel features:

```c
typedef enum {
    CORTEX_CAP_OFFLINE_CALIB  = 1u << 0,  /* Supports cortex_calibrate() */
    CORTEX_CAP_ONLINE_ADAPT   = 1u << 1,  /* Reserved: v4 - per-window adaptation */
    CORTEX_CAP_FEEDBACK_LEARN = 1u << 2,  /* Reserved: v5 - reinforcement learning */
} cortex_capability_flags_t;
```

A kernel's `cortex_init()` return value MUST set the `capabilities` field to:
- `0` for stateless kernels (e.g., CAR, FIR filters)
- `CORTEX_CAP_OFFLINE_CALIB` for trainable kernels that export `cortex_calibrate()` (e.g., ICA, CSP)
- Reserved flags SHOULD NOT be set (reserved for future ABI versions)

**Rationale**

Supporting multiple data types enables:

1. **Embedded deployment**: Fixed-point arithmetic (Q15, Q7) runs efficiently on microcontrollers without FPUs, reducing both latency and power consumption.

2. **Quantization research**: Neural network-based BCI kernels can experiment with 8-bit quantization (Q7) to reduce memory bandwidth and accelerate matrix operations.

3. **Progressive enhancement**: Kernels can start with float32 implementation, then add fixed-point variants for specific platforms without changing the ABI.

4. **Fair comparison**: Benchmarks can compare float32 vs. Q15 implementations of the same algorithm to quantify accuracy/performance tradeoffs.

The bitmask representation allows kernels to advertise "I support float32 OR Q15" via `CORTEX_DTYPE_FLOAT32 | CORTEX_DTYPE_Q15`, enabling the harness to select the best available type for the target platform. However, the runtime config always selects exactly one type to avoid ambiguity during execution.

---

### 3.6 Error Handling

**Overview**

The CORTEX plugin ABI uses a simple, explicit error handling model based on return value checking and stderr logging. This approach prioritizes debugging clarity and fail-fast behavior over silent error propagation.

**Normative Requirements**

**Error Code Convention:**

- **Success**: Return value of `0` (integer functions) or non-NULL pointer (pointer-returning functions)
- **Failure**: Return value of non-zero error code (integer functions) or NULL pointer (pointer-returning functions)

Specifically:

- `cortex_init()`: Returns `{NULL, 0, 0, 0}` on error, `{non-NULL, W, C, capabilities}` on success
- `cortex_calibrate()`: Returns `{NULL, 0, 0}` on error, `{non-NULL, size, version}` on success
- `cortex_process()`: Has `void` return type (cannot fail once `init()` succeeds)
- `cortex_teardown()`: Has `void` return type (cannot fail)

**Initialization Errors:**

Errors in `cortex_init()` SHALL cause the benchmark to **abort immediately** before any timing measurements begin. The harness SHALL:
- Check for NULL handle in the returned `cortex_init_result_t`
- Log the kernel's stderr output (which SHOULD contain a descriptive error message)
- Exit with non-zero status code
- NOT proceed to call `cortex_process()`

Common initialization error scenarios:

| Error Condition | Kernel Response | Example |
|-----------------|-----------------|---------|
| Unsupported ABI version | Return `{NULL, 0, 0, 0}` | `config->abi_version == 1` but kernel requires v3 |
| Unsupported dtype | Return `{NULL, 0, 0, 0}` | `config->dtype == CORTEX_DTYPE_Q15` but kernel only supports float32 |
| Memory allocation failure | Return `{NULL, 0, 0, 0}` | `malloc()` returns NULL (out of memory) |
| Invalid parameters | Return `{NULL, 0, 0, 0}` | `cutoff_hz >= sample_rate_hz / 2` (exceeds Nyquist frequency) |
| Missing calibration state | Return `{NULL, 0, 0, 0}` | Trainable kernel called without `config->calibration_state` |
| Calibration state version mismatch | Return `{NULL, 0, 0, 0}` | State file has `state_version=2` but kernel expects v1 |

**Error Logging:**

Kernels SHOULD log errors to stderr with the following format:

```
[kernel_name] ERROR: <brief description>
[kernel_name] <additional context or suggestion>
```

Example:
```
[ica] ERROR: Calibration state required
[ica] Run: cortex calibrate --kernel ica@f32 --dataset <path> --output <state_file>
```

Harness implementers SHOULD capture stderr during initialization and include it in error reports.

**Processing Errors:**

Errors in `cortex_process()` SHALL mark the current window as **failed** without aborting the benchmark. The harness SHALL:
- Detect processing failures via output validation (e.g., all-NaN output, all-zero output when input is non-zero)
- Log warning to stderr
- Record window as failed in telemetry
- Continue processing subsequent windows

Kernels SHOULD handle error conditions gracefully:

- **Invalid input values**: Replace NaN with 0.0, clamp infinite values
- **Numerical overflow**: Use double-precision intermediate calculations, check for overflow before casting
- **Numerical underflow**: Treat subnormal values as 0.0 if needed

Kernels MUST NOT:
- Call `exit()` or `abort()` (would crash the harness)
- Throw C++ exceptions (ABI is C-based, exceptions may not propagate correctly)
- Return early from `process()` leaving output buffer partially filled

**Calibration Errors:**

Errors in `cortex_calibrate()` SHALL cause the calibration command to **fail** with non-zero exit status. The harness SHALL:
- Check for NULL `calibration_state` in the returned result
- Log the kernel's stderr output
- Exit with non-zero status code
- NOT save a `.cortex_state` file

Common calibration error scenarios:

| Error Condition | Kernel Response | Example |
|-----------------|-----------------|---------|
| Insufficient training data | Return `{NULL, 0, 0}` | `num_windows < 10` for algorithm requiring minimum samples |
| Convergence failure | Return `{NULL, 0, 0}` | ICA fails to converge after 200 iterations |
| Singular matrix | Return `{NULL, 0, 0}` | Covariance matrix is rank-deficient (all input data is constant) |
| Memory allocation failure | Return `{NULL, 0, 0}` | Cannot allocate temporary matrices for eigendecomposition |
| Invalid labels | Return `{NULL, 0, 0}` | CSP receives labels other than 0/1 for binary classification |

**Code Example (Initialization Error Handling)**

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    /* Validate ABI version */
    if (!config || config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[kernel] ERROR: ABI version mismatch\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    /* Validate dtype */
    if (config->dtype != CORTEX_DTYPE_FLOAT32) {
        fprintf(stderr, "[kernel] ERROR: Unsupported dtype (only float32 supported)\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    /* Allocate state */
    kernel_state_t *state = calloc(1, sizeof(kernel_state_t));
    if (!state) {
        fprintf(stderr, "[kernel] ERROR: Memory allocation failed\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    /* Parse parameters */
    const char *params = (const char *)config->kernel_params;
    double cutoff_hz = cortex_param_float(params, "cutoff_hz", 30.0);
    double nyquist = config->sample_rate_hz / 2.0;

    if (cutoff_hz <= 0.0 || cutoff_hz >= nyquist) {
        fprintf(stderr, "[kernel] ERROR: cutoff_hz (%.1f) must be in (0, %.1f)\n",
                cutoff_hz, nyquist);
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    /* ... successful initialization ... */

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = config->window_length_samples,
        .output_channels = config->channels,
        .capabilities = 0
    };
}
```

**Code Example (Calibration Error Handling)**

```c
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
) {
    /* Validate sufficient training data */
    const uint32_t MIN_WINDOWS = 20;
    if (num_windows < MIN_WINDOWS) {
        fprintf(stderr, "[ica] ERROR: Insufficient training data\n");
        fprintf(stderr, "[ica] ICA requires at least %u windows, got %u\n",
                MIN_WINDOWS, num_windows);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    /* Allocate training matrix */
    const uint32_t C = config->channels;
    const uint32_t W = config->window_length_samples;
    const uint32_t total_samples = num_windows * W;

    float *X = malloc(total_samples * C * sizeof(float));
    if (!X) {
        fprintf(stderr, "[ica] ERROR: Memory allocation failed (requested %zu bytes)\n",
                (size_t)total_samples * C * sizeof(float));
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    /* Run FastICA */
    float *W_unmix = malloc(C * C * sizeof(float));
    if (!W_unmix) {
        fprintf(stderr, "[ica] ERROR: Memory allocation failed\n");
        free(X);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    if (fastica_train(X, total_samples, C, W_unmix) != 0) {
        fprintf(stderr, "[ica] ERROR: FastICA convergence failed after %d iterations\n",
                MAX_ITERATIONS);
        free(X);
        free(W_unmix);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    free(X);

    /* Success */
    return (cortex_calibration_result_t){
        .calibration_state = W_unmix,
        .state_size_bytes = C * C * sizeof(float),
        .state_version = 1
    };
}
```

**Rationale**

The explicit error handling model enables:

1. **Fail-fast initialization**: Invalid configurations are detected before any benchmark resources (datasets, timers, telemetry) are allocated, preventing corrupt measurements.

2. **Debugging clarity**: stderr logging with kernel name prefix allows developers to immediately identify which kernel failed and why, even in complex multi-kernel pipelines.

3. **Graceful degradation**: Processing errors (NaN inputs, numerical overflow) are handled per-window rather than aborting the entire benchmark, allowing partial results to be collected for analysis.

4. **Deterministic benchmarks**: By prohibiting exceptions and `exit()` calls in `process()`, the harness maintains full control over execution flow and can implement deadline enforcement, retry logic, and statistical analysis.

5. **Oracle validation**: Returning error status enables automated testing frameworks to detect calibration failures and compare C vs. Python implementation error paths (both should fail on the same invalid inputs).

The `void` return type for `cortex_process()` reflects the design principle that if `init()` succeeds, processing **cannot fail** in a way that requires aborting execution. Kernels must handle all possible input data (including NaN, infinity, zero-variance signals) by producing valid output or logging warnings.

---

## Summary

This specification defines CORTEX Plugin ABI 1.0, a C-based interface for real-time signal processing kernels in brain-computer interface benchmarking. The ABI prioritizes:

- **Determinism**: Zero-allocation processing, IEEE 754 compliance, fixed buffer layouts
- **Forward compatibility**: ABI versioning, struct size checking, extensible configuration
- **Embedded readiness**: Multiple data types (float32, Q15, Q7), alignment requirements, resource constraints
- **Calibration support**: Offline batch training for adaptive algorithms (ICA, CSP)
- **Fair benchmarking**: Strict constraints on memory allocation, I/O, and blocking operations

Production implementations exist for 8 kernels (CAR, bandpass FIR, CSP, Goertzel, ICA, noop, notch IIR, Welch PSD), with 2 kernels (ICA, CSP) implementing full ABI v3 calibration workflow. The remaining kernels maintain ABI v2 compatibility with capability flags indicating stateless operation.

For implementation guidance, see:
- `sdk/kernel/include/cortex_plugin.h` - Authoritative ABI definition
- `primitives/kernels/v1/*/` - Reference kernel implementations
- `docs/guides/migrating-to-abi-v3.md` - Migration guide for kernel authors
- `.claude/commands/new-kernel.md` - Kernel scaffolding templates

---

**Document Version**: 1.0
**Last Updated**: 2026-02-01
**Status**: Publication-Ready

---

# Section 4: Wire Protocol Specification

## 4.1 Transport Layer

### 4.1.1 Overview

The CORTEX wire protocol operates over a reliable byte-stream transport abstraction that provides ordered, lossless delivery of data between the harness and device adapter. The protocol is transport-agnostic, supporting multiple physical transports through a unified API.

The transport layer abstracts platform-specific communication mechanisms while providing essential primitives for protocol correctness: timeout-based receive operations to detect adapter failure, monotonic timestamps for latency measurement, and standardized error codes for common failure modes.

### 4.1.2 Transport Abstraction Requirements

All transport implementations MUST provide the following operations:

**Send Operation**

A conformant transport SHALL implement a blocking send operation with the following signature:

```c
ssize_t send(void *ctx, const void *buf, size_t len);
```

The send operation:
- MUST transmit exactly `len` bytes from `buf` or return an error
- MAY block until the entire buffer is transmitted
- MUST return the number of bytes sent on success (equal to `len`)
- MUST return a negative error code on failure

**Receive Operation**

A conformant transport SHALL implement a blocking receive operation with timeout:

```c
ssize_t recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms);
```

The receive operation:
- MUST wait up to `timeout_ms` milliseconds for data to arrive
- MAY return partial data (fewer than `len` bytes)
- MUST return the number of bytes received on success
- MUST return 0 if the connection is closed (EOF)
- MUST return `CORTEX_ETIMEDOUT` (-1000) if the timeout expires with no data
- MUST return `CORTEX_ECONNRESET` (-1001) if the connection is reset
- MUST return other negative error codes for platform-specific failures

**Timestamp Operation**

A conformant transport SHALL provide monotonic nanosecond timestamps:

```c
uint64_t get_timestamp_ns(void);
```

The timestamp operation:
- MUST return nanoseconds since an arbitrary epoch
- MUST use a monotonic clock source (immune to system time changes)
- MUST NOT wrap around during reasonable execution periods
- SHOULD use CLOCK_MONOTONIC on POSIX systems
- SHOULD use DWT cycle counters on ARM Cortex-M systems

### 4.1.3 Timeout Requirements

All receive operations MUST specify explicit timeouts to prevent infinite hangs on adapter failure. A conformant implementation SHALL use the following timeout values:

| Phase | Timeout (ms) | Rationale |
|-------|--------------|-----------|
| Handshake (HELLO, ACK) | 5000 | Adapter may be loading kernels, initializing hardware |
| Window processing (WINDOW_CHUNK, RESULT) | 10000 | Kernel execution + large data transfer |
| Per-chunk receive | 1000 | Single 8KB chunk transfer time |
| Error frames | 500 | Fast failure detection |
| TCP server accept | 30000 | Network connection establishment |

These values are defined as constants in `cortex_wire.h`:

```c
#define CORTEX_HANDSHAKE_TIMEOUT_MS 5000
#define CORTEX_WINDOW_TIMEOUT_MS    10000
#define CORTEX_CHUNK_TIMEOUT_MS     1000
#define CORTEX_ACCEPT_TIMEOUT_MS    30000
```

**Rationale**: Explicit timeouts prevent deadlock when an adapter crashes or hangs. The handshake timeout is longer because adapters may perform expensive initialization (loading shared libraries, allocating large buffers, calibrating hardware). Window processing timeouts accommodate both computation time and large data transfers (e.g., 40KB window at 1 MB/s requires 40ms transfer time plus kernel execution).

### 4.1.4 Supported Transports

The specification defines three standard transport types:

**Native Transport (local://)**

The native transport uses POSIX `socketpair(2)` to create a bidirectional byte stream between the harness and a locally-spawned adapter process. This is the default transport for development and testing.

URI format: `local://`

A conformant harness implementation:
- SHALL create a UNIX domain socket pair using `socketpair(AF_UNIX, SOCK_STREAM, 0)`
- SHALL spawn the adapter process via `fork(2)` and `execl(3)`
- SHALL redirect the adapter's stdin/stdout to one end of the socket pair
- SHALL use the other end for protocol communication
- SHALL set close-on-exec flags to prevent fd leakage
- SHALL use `poll(2)` or `select(2)` to implement receive timeouts

**TCP Transport (tcp://)**

The TCP transport provides network connectivity for remote adapters (e.g., Jetson Nano over Ethernet, cloud GPUs).

URI format: `tcp://host:port` (client mode) or `tcp://:port` (server mode)

Query parameters:
- `timeout_ms=N`: Override default timeout (5000ms)
- `accept_timeout_ms=N`: Server accept timeout (30000ms)

Example: `tcp://jetson.local:9000?timeout_ms=2000`

A conformant TCP transport:
- MUST use IPv4 or IPv6 TCP sockets
- MUST support both client (connect) and server (listen) modes
- MUST implement receive timeouts using `setsockopt(SO_RCVTIMEO)` or `poll(2)`
- SHOULD enable TCP_NODELAY to reduce latency
- SHOULD set SO_KEEPALIVE for connection health monitoring

**Serial/UART Transport (serial://)**

The UART transport enables communication with embedded adapters via RS-232, USB-serial, or native UART ports.

URI format: `serial:///dev/device?baud=115200`

Query parameters:
- `baud=N`: Baud rate (default: 115200)

Common baud rates: 115200, 230400, 460800, 921600

Example: `serial:///dev/ttyUSB0?baud=921600`

A conformant UART transport:
- MUST configure the serial port for 8N1 mode (8 data bits, no parity, 1 stop bit)
- MUST disable hardware flow control (RTS/CTS) unless explicitly enabled
- MUST use VTIME/VMIN settings to implement receive timeouts
- SHOULD flush buffers on initialization to discard stale data
- SHOULD support common POSIX device paths (/dev/ttyUSB*, /dev/cu.*, /dev/ttyS*)

### 4.1.5 Transport Error Handling

All transport implementations MUST distinguish between temporary and permanent errors:

**Temporary Errors** (retry possible):
- `CORTEX_ETIMEDOUT`: No data available within timeout period
- `EINTR`: System call interrupted by signal

A conformant protocol implementation MAY retry operations that fail with temporary errors.

**Permanent Errors** (connection lost):
- `CORTEX_ECONNRESET`: Connection closed by peer
- `EPIPE`: Broken pipe (adapter terminated)
- `ECONNREFUSED`: Connection refused (TCP only)

A conformant protocol implementation MUST abort operations and return to the caller when permanent errors occur.

---

## 4.2 Binary Frame Format

### 4.2.1 Overview

All protocol messages are encapsulated in binary frames consisting of a fixed 16-byte header, variable-length payload, and CRC32 checksum. Frames are self-delimiting and can be transmitted over unreliable byte streams with corruption detection and resynchronization.

### 4.2.2 Frame Structure

A conformant frame SHALL have the following byte layout:

```
Offset | Size | Field          | Endianness | Description
-------|------|----------------|------------|---------------------------
0      | 4    | MAGIC          | LE         | 0x43525458 ("CRTX")
4      | 1    | VERSION        | N/A        | Protocol version (0x01)
5      | 1    | TYPE           | N/A        | Frame type (0x01-0x07)
6      | 2    | FLAGS          | LE         | Reserved (MUST be 0x0000)
8      | 4    | LENGTH         | LE         | Payload length in bytes
12     | 4    | CRC32          | LE         | IEEE 802.3 checksum
16     | N    | PAYLOAD        | LE         | Frame-specific payload
16+N   | 0    | (end)          |            | Total frame size: 16+N
```

All multi-byte integers SHALL be transmitted in little-endian byte order. The header size is fixed at 16 bytes to enable efficient parsing (read header, extract LENGTH, read LENGTH bytes of payload).

**Alignment Requirement**: The header struct is 16 bytes to ensure natural alignment on ARM platforms (avoiding unaligned access faults on ARMv7 and earlier).

### 4.2.3 MAGIC Constant

The MAGIC field MUST be 0x43525458 (ASCII "CRTX" interpreted as a little-endian 32-bit integer).

On the wire, the MAGIC bytes appear in little-endian order:
```
Wire bytes: 0x58 0x54 0x52 0x43
            ^    ^    ^    ^
            |    |    |    +--- 'C' (0x43)
            |    |    +-------- 'R' (0x52)
            |    +------------- 'T' (0x54)
            +------------------ 'X' (0x58)
```

The MAGIC constant serves three purposes:

1. **Frame boundary detection**: Enables receivers to locate the start of a frame in a byte stream
2. **Protocol identification**: Distinguishes CORTEX frames from other data on shared transports
3. **Resynchronization**: Allows recovery from corruption or partial frame loss

A conformant receiver SHALL reject any frame that does not begin with the MAGIC constant.

### 4.2.4 VERSION Field

The VERSION field MUST be 0x01 for protocol version 1.

A conformant implementation:
- SHALL reject frames with VERSION != 0x01
- SHALL return error code `CORTEX_EPROTO_VERSION_MISMATCH` (-2002)
- SHOULD log the received version number for debugging

**Rationale**: Strict version checking prevents subtle incompatibilities between harness and adapter builds. Protocol version increments indicate breaking wire format changes.

### 4.2.5 TYPE Field

The TYPE field specifies the frame type (message category). Valid values are defined in Section 4.3.

A conformant implementation SHALL validate that the TYPE field contains a recognized frame type value. Unknown TYPE values SHOULD be treated as protocol errors.

### 4.2.6 FLAGS Field

The FLAGS field is reserved for future protocol extensions. In protocol version 1, this field MUST be 0x0000.

A conformant implementation:
- MUST set FLAGS to 0x0000 when sending frames
- SHOULD ignore the FLAGS field when receiving frames (forward compatibility)

Future protocol versions may define flag bits for optional features (compression, encryption, fragmentation control).

### 4.2.7 LENGTH Field

The LENGTH field specifies the payload size in bytes (excluding the 16-byte header).

A conformant implementation:
- MUST set LENGTH to the exact payload size
- MUST validate that LENGTH does not exceed available buffer space before reading payload
- SHALL return `CORTEX_EPROTO_BUFFER_TOO_SMALL` (-2004) if the caller's buffer is insufficient

**No Maximum Frame Size**: Protocol version 1 imposes no hardcoded maximum frame size. Frames are limited only by available RAM. Large payloads (windows, results) are automatically chunked using WINDOW_CHUNK and RESULT_CHUNK frame types (see Section 4.5).

### 4.2.8 CRC32 Checksum

The CRC32 field contains a 32-bit checksum computed over the frame header (bytes 0-11, excluding the CRC32 field itself) and the entire payload.

**Algorithm**: IEEE 802.3 CRC32 (polynomial 0xEDB88320, same as Ethernet, ZIP, PNG)

**Computation**:
```c
uint32_t crc = crc32(0, header_bytes_0_to_11, 12);
crc = crc32(crc, payload, payload_length);
// Store 'crc' in header[12:16] (little-endian)
```

The CRC32 function uses the following parameters:
- Initial value: 0xFFFFFFFF (inverted)
- Polynomial: 0xEDB88320 (reflected)
- Final XOR: 0xFFFFFFFF (inverted)

A conformant implementation:
- MUST compute the CRC over header bytes [0:12] followed by payload bytes [0:N]
- MUST use the IEEE 802.3 polynomial (table lookup or bitwise algorithm)
- MUST reject frames where computed CRC != wire CRC
- SHALL return `CORTEX_EPROTO_CRC_MISMATCH` (-2001) on CRC validation failure

**Error Detection Properties**:
- Detects all single-bit errors
- Detects all double-bit errors
- Detects all burst errors up to 32 bits
- Detects 99.9999998% of longer bursts
- Performance: ~1 GB/s with table lookup on modern CPUs

**Rationale**: CRC32 provides strong error detection for bit flips, truncation, and reordering. The false acceptance rate (~1 in 4 billion) is acceptable for intra-system communication. The IEEE 802.3 polynomial is hardware-accelerated on many platforms and well-tested.

### 4.2.9 Endianness Conversion

All multi-byte values on the wire use little-endian byte order. A conformant implementation MUST convert between host byte order and wire byte order using explicit conversion functions.

**Reading from wire**:
```c
uint32_t value = cortex_read_u32_le(buffer);
uint64_t timestamp = cortex_read_u64_le(buffer + 8);
float sample = cortex_read_f32_le(buffer + 16);
```

**Writing to wire**:
```c
cortex_write_u32_le(buffer, value);
cortex_write_u64_le(buffer + 8, timestamp);
cortex_write_f32_le(buffer + 16, sample);
```

On little-endian hosts (x86, most ARM), these functions compile to no-ops (direct memory access). On big-endian hosts, they perform byte swapping.

**CRITICAL**: Implementations MUST NOT cast packed structs directly from wire buffers:

```c
// WRONG (undefined behavior, alignment faults on ARM):
header = *(cortex_wire_header_t*)buffer;

// CORRECT:
cortex_wire_header_t header;
memcpy(&header, buffer, sizeof(header));
header.magic = cortex_le32toh(header.magic);
header.payload_length = cortex_le32toh(header.payload_length);
// ... convert other fields ...
```

**Rationale**: Little-endian is the native byte order of x86 and modern ARM platforms. Using little-endian wire format avoids byte swapping overhead on 99% of deployed hardware. Explicit conversion functions prevent alignment faults on ARMv7 and endianness bugs on rare big-endian platforms.

### 4.2.10 MAGIC Hunting (Resynchronization)

When a receiver starts or detects corruption, it MUST perform MAGIC hunting to locate the next frame boundary.

**Algorithm**:

A conformant receiver SHALL use a sliding-window search:

```c
uint32_t window = 0;
while (true) {
    uint8_t byte;
    if (recv_one_byte(&byte, timeout_ms) != 0)
        return CORTEX_ETIMEDOUT;

    // Shift window right, insert new byte at top (LE order)
    window = (window >> 8) | ((uint32_t)byte << 24);

    if (window == CORTEX_PROTOCOL_MAGIC)
        break;  // Frame start found
}
```

**Byte order note**: Because MAGIC is transmitted in little-endian order (0x58, 0x54, 0x52, 0x43), the sliding window must shift right and insert new bytes at the top to reconstruct the 32-bit value in host byte order.

**Rationale**: MAGIC hunting enables recovery from partial frame corruption, adapter restarts, or mid-stream synchronization. The 4-byte MAGIC constant has low probability of false matches in random data (~1 in 4 billion).

---

## 4.3 Message Types

### 4.3.1 Overview

The CORTEX protocol defines 7 frame types for handshake, execution, and error handling. Each frame type has a unique TYPE value and payload structure.

| Type | Value | Direction | Purpose |
|------|-------|-----------|---------|
| HELLO | 0x01 | Adapter → Harness | Advertise capabilities |
| CONFIG | 0x02 | Harness → Adapter | Configure kernel |
| ACK | 0x03 | Adapter → Harness | Acknowledge configuration |
| WINDOW_CHUNK | 0x04 | Harness → Adapter | Send input data (chunked) |
| RESULT | 0x05 | Adapter → Harness | Return output (legacy, deprecated) |
| ERROR | 0x06 | Either direction | Report error |
| RESULT_CHUNK | 0x07 | Adapter → Harness | Return output data (chunked) |

**Note**: RESULT (0x05) is deprecated in favor of RESULT_CHUNK (0x07) for consistent chunking support. Both are supported for backward compatibility.

### 4.3.2 HELLO Frame (0x01)

**Direction**: Adapter → Harness

**Purpose**: The adapter advertises its capabilities, available kernels, and system information immediately after transport connection establishment.

**When sent**: First message from adapter after spawn/connect

**Payload structure**:

```
Offset | Size | Field                | Endianness | Description
-------|------|----------------------|------------|---------------------------
0      | 4    | adapter_boot_id      | LE         | Random ID on adapter start
4      | 32   | adapter_name         | N/A        | Adapter name (null-term)
36     | 1    | adapter_abi_version  | N/A        | ABI version (MUST be 1)
37     | 1    | num_kernels          | N/A        | Count of available kernels
38     | 2    | reserved             | LE         | Padding (MUST be 0)
40     | 4    | max_window_samples   | LE         | Memory constraint
44     | 4    | max_channels         | LE         | Hardware channel limit
48     | 32   | device_hostname      | N/A        | Device hostname (uname -n)
80     | 32   | device_cpu           | N/A        | CPU model (e.g., "Apple M1")
112    | 32   | device_os            | N/A        | OS version (uname -s -r)
144    | N×32 | kernel_names         | N/A        | num_kernels × 32-byte names
```

**Total payload size**: 144 + (num_kernels × 32) bytes

**Field descriptions**:

- `adapter_boot_id`: Random 32-bit value generated on adapter process start. Used to detect adapter restarts (harness can compare against previous session).

- `adapter_name`: Human-readable adapter identifier (e.g., "native", "jetson@tcp", "stm32-h7@uart"). NULL-terminated string up to 32 bytes.

- `adapter_abi_version`: Binary compatibility version. MUST be 1 for protocol version 1. If harness receives a different ABI version, it MUST reject the connection.

- `num_kernels`: Count of available kernel implementations. Harness uses this to allocate buffer space for kernel names.

- `max_window_samples`: Maximum window length the adapter can process (in samples). Constrained by adapter RAM. Harness MUST NOT send windows larger than this limit.

- `max_channels`: Maximum channel count supported by adapter hardware. Harness MUST NOT configure more channels than this limit.

- `device_hostname`: Device hostname from `uname(2)` or equivalent (e.g., "jetson-01", "MacBook-Pro.local"). Used for telemetry tagging.

- `device_cpu`: CPU model string (e.g., "Apple M1", "ARM Cortex-A57", "Intel Core i7-9700K"). Used for performance analysis.

- `device_os`: Operating system name and version (e.g., "Darwin 23.2.0", "Linux 5.10.104-tegra"). Used for compatibility diagnostics.

- `kernel_names`: Array of NULL-terminated kernel names (32 bytes each). Each name is a kernel identifier (e.g., "bandpass_fir@f32", "ica@f32").

**Example**:

```
adapter_boot_id:     0x8F3A21C7
adapter_name:        "native"
adapter_abi_version: 1
num_kernels:         3
max_window_samples:  512
max_channels:        64
device_hostname:     "MacBook-Pro.local"
device_cpu:          "Apple M1"
device_os:           "Darwin 23.2.0"

Kernel names:
  [0] "bandpass_fir@f32"
  [1] "car@f32"
  [2] "ica@f32"

Payload size: 144 + (3 × 32) = 240 bytes
```

**Hex dump** (first 64 bytes):

```
00000000: c7 21 3a 8f 6e 61 74 69  76 65 00 00 00 00 00 00  |.!:.native......|
00000010: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
00000020: 00 00 00 00 01 03 00 00  00 02 00 00 40 00 00 00  |............@...|
00000030: 4d 61 63 42 6f 6f 6b 2d  50 72 6f 2e 6c 6f 63 61  |MacBook-Pro.loca|
        boot_id ^adapter_name                 ^abi ^nk ^res
                                               ^max_win ^max_ch
                                                       ^device_hostname
```

**Validation requirements**:

A conformant harness:
- MUST verify `adapter_abi_version == 1`
- MUST verify `num_kernels >= 1`
- MUST verify payload size == 144 + (num_kernels × 32)
- SHOULD verify that requested kernel name appears in `kernel_names` array

### 4.3.3 CONFIG Frame (0x02)

**Direction**: Harness → Adapter

**Purpose**: Configure the adapter with kernel selection, execution parameters, and optional calibration state.

**When sent**: After receiving HELLO

**Payload structure**:

```
Offset | Size | Field                   | Endianness | Description
-------|------|-------------------------|------------|---------------------------
0      | 4    | session_id              | LE         | Random session identifier
4      | 4    | sample_rate_hz          | LE         | Sample rate (e.g., 250 Hz)
8      | 4    | window_length_samples   | LE         | Window length (W)
12     | 4    | hop_samples             | LE         | Hop size (H)
16     | 4    | channels                | LE         | Channel count (C)
20     | 64   | plugin_name             | N/A        | Kernel spec URI (null-term)
84     | 256  | plugin_params           | N/A        | Params string (null-term)
340    | 4    | calibration_state_size  | LE         | State size (0 if none)
344    | N    | calibration_state       | (opaque)   | Binary state blob
```

**Total payload size**: 344 + calibration_state_size bytes

**Field descriptions**:

- `session_id`: Random 32-bit identifier for this execution session. MUST be non-zero. Used to detect adapter restarts (if adapter reboots, it won't match the session_id in subsequent RESULT frames).

- `sample_rate_hz`: Sampling frequency in Hz (e.g., 250 for 250 Hz EEG). Used for time-domain calculations.

- `window_length_samples`: Number of samples per channel in each window (W). MUST be <= max_window_samples from HELLO.

- `hop_samples`: Number of samples to advance between consecutive windows (H). Typically W/2 for 50% overlap.

- `channels`: Number of input channels (C). MUST be <= max_channels from HELLO.

- `plugin_name`: Kernel specifier URI (e.g., "primitives/kernels/v1/ica@f32"). NULL-terminated string up to 64 bytes. MUST match a kernel advertised in HELLO.

- `plugin_params`: Kernel-specific configuration string (e.g., "lowcut=8,highcut=30"). Format is kernel-dependent. NULL-terminated string up to 256 bytes.

- `calibration_state_size`: Size of calibration state blob in bytes. MUST be 0 for stateless kernels. MUST be <= 16 MB for trainable kernels.

- `calibration_state`: Opaque binary state blob for trainable kernels (e.g., ICA unmixing matrix). Format is kernel-specific.

**Validation requirements**:

A conformant adapter:
- MUST verify `session_id != 0`
- MUST verify `sample_rate_hz > 0`
- MUST verify `window_length_samples <= max_window_samples` (from HELLO)
- MUST verify `channels <= max_channels` (from HELLO)
- MUST verify `plugin_name` matches an advertised kernel
- MUST verify `calibration_state_size <= 16777216` (16 MB)
- SHALL return ERROR frame if validation fails

**Example**:

```
session_id:              0x4A7F3C21
sample_rate_hz:          250
window_length_samples:   160
hop_samples:             80
channels:                64
plugin_name:             "primitives/kernels/v1/ica@f32"
plugin_params:           "whiten=true,maxiter=100"
calibration_state_size:  16384  (64×64 matrix × 4 bytes)

Payload size: 344 + 16384 = 16728 bytes
```

### 4.3.4 ACK Frame (0x03)

**Direction**: Adapter → Harness

**Purpose**: Acknowledge CONFIG and report actual output dimensions (for dimension-changing kernels).

**When sent**: After successfully loading kernel and allocating buffers

**Payload structure**:

```
Offset | Size | Field                          | Endianness | Description
-------|------|--------------------------------|------------|---------------------------
0      | 4    | ack_type                       | LE         | What is ACKed (0 = CONFIG)
4      | 4    | output_window_length_samples   | LE         | Output W (0 = use input W)
8      | 4    | output_channels                | LE         | Output C (0 = use input C)
```

**Total payload size**: 12 bytes

**Field descriptions**:

- `ack_type`: Type of acknowledgment. MUST be 0 (CONFIG) in protocol version 1.

- `output_window_length_samples`: Output window length in samples. If 0, harness SHOULD use input window_length_samples from CONFIG. If non-zero, indicates kernel changes window length (e.g., Welch PSD reduces time resolution).

- `output_channels`: Output channel count. If 0, harness SHOULD use input channels from CONFIG. If non-zero, indicates kernel changes channel count (e.g., ICA unmixing).

**Rationale**: Most kernels preserve dimensions (input W×C = output W×C). For these kernels, the adapter sets output dimensions to 0, and the harness reuses CONFIG dimensions. This provides backward compatibility and simplifies common cases.

Dimension-changing kernels (e.g., PSD estimation, channel reduction) explicitly report output dimensions in ACK. The harness dynamically allocates output buffers based on these values.

**Example (dimension-preserving kernel)**:

```
ack_type:                        0
output_window_length_samples:    0  (use CONFIG: 160)
output_channels:                 0  (use CONFIG: 64)
```

**Example (dimension-changing kernel - Welch PSD)**:

```
ack_type:                        0
output_window_length_samples:    65  (FFT: 160 → 65 freq bins)
output_channels:                 64  (unchanged)
```

### 4.3.5 WINDOW_CHUNK Frame (0x04)

**Direction**: Harness → Adapter

**Purpose**: Send input window data, potentially split across multiple chunks for large windows.

**When sent**: After receiving ACK, for each window to process

**Payload structure**:

```
Offset | Size | Field          | Endianness | Description
-------|------|----------------|------------|---------------------------
0      | 4    | sequence       | LE         | Window sequence number
4      | 4    | total_bytes    | LE         | Total window size (W×C×4)
8      | 4    | offset_bytes   | LE         | Offset of this chunk
12     | 4    | chunk_length   | LE         | Bytes in this chunk
16     | 4    | flags          | LE         | CORTEX_CHUNK_FLAG_LAST
20     | N    | sample_data    | LE         | Float32 samples (LE)
```

**Total payload size**: 20 + chunk_length bytes

**Field descriptions**:

- `sequence`: Monotonically increasing window sequence number. Starts at 1. Used to match WINDOW_CHUNK with corresponding RESULT.

- `total_bytes`: Total size of the complete window in bytes (window_length_samples × channels × 4). Same value in all chunks for a given window.

- `offset_bytes`: Byte offset of this chunk's data within the complete window. First chunk has offset 0. Subsequent chunks have offset = previous_offset + previous_chunk_length.

- `chunk_length`: Number of bytes in this chunk's `sample_data` field. SHOULD be <= 8192 (8KB) for optimal performance.

- `flags`: Bit flags. Bit 0 (CORTEX_CHUNK_FLAG_LAST) MUST be set on the final chunk of a window. All other bits MUST be 0.

- `sample_data`: Float32 sample data in little-endian IEEE-754 format. Samples are stored in row-major order (all channels for sample 0, then all channels for sample 1, etc.).

**Chunking behavior**:

A conformant harness:
- SHOULD split windows larger than 8KB into multiple WINDOW_CHUNK frames
- MUST set `sequence` to the same value for all chunks of a window
- MUST set `offset_bytes` and `chunk_length` such that chunks cover [0, total_bytes) without gaps or overlaps
- MUST set CORTEX_CHUNK_FLAG_LAST only on the final chunk
- SHOULD use chunk_length <= 8192 bytes (optimal for network MTU and memory cache)

A conformant adapter:
- MUST reassemble chunks into a complete window buffer
- MUST validate that `offset_bytes + chunk_length <= total_bytes`
- MUST NOT begin processing until CORTEX_CHUNK_FLAG_LAST is received
- SHOULD timestamp window arrival (tin) when CORTEX_CHUNK_FLAG_LAST is received

**Example (small window, single chunk)**:

```
sequence:     1
total_bytes:  2560  (160 samples × 4 channels × 4 bytes)
offset_bytes: 0
chunk_length: 2560
flags:        0x00000001  (CORTEX_CHUNK_FLAG_LAST)

Payload size: 20 + 2560 = 2580 bytes
```

**Example (large window, chunked)**:

```
Window: 160 samples × 64 channels × 4 bytes = 40960 bytes
Chunk size: 8192 bytes
Number of chunks: 5

Chunk 1:
  sequence:     2
  total_bytes:  40960
  offset_bytes: 0
  chunk_length: 8192
  flags:        0x00000000

Chunk 2:
  sequence:     2
  total_bytes:  40960
  offset_bytes: 8192
  chunk_length: 8192
  flags:        0x00000000

Chunk 3:
  sequence:     2
  total_bytes:  40960
  offset_bytes: 16384
  chunk_length: 8192
  flags:        0x00000000

Chunk 4:
  sequence:     2
  total_bytes:  40960
  offset_bytes: 24576
  chunk_length: 8192
  flags:        0x00000000

Chunk 5:
  sequence:     2
  total_bytes:  40960
  offset_bytes: 32768
  chunk_length: 8192
  flags:        0x00000001  (CORTEX_CHUNK_FLAG_LAST)
```

**Rationale**: Chunking enables transmission of arbitrarily large windows without requiring large contiguous frame buffers. The 8KB chunk size is chosen to fit within typical network MTU sizes (jumbo frames: 9KB) and CPU cache lines (L2: 256KB can hold ~32 chunks).

### 4.3.6 RESULT_CHUNK Frame (0x07)

**Direction**: Adapter → Harness

**Purpose**: Return kernel output data and device-side timing information, potentially split across multiple chunks for large outputs.

**When sent**: After processing a complete window

**Payload structure**:

```
Offset | Size | Field                   | Endianness | Description
-------|------|-------------------------|------------|---------------------------
0      | 4    | session_id              | LE         | Must match CONFIG
4      | 4    | sequence                | LE         | Must match WINDOW_CHUNK
8      | 8    | tin                     | LE         | Input complete (ns)
16     | 8    | tstart                  | LE         | Kernel start (ns)
24     | 8    | tend                    | LE         | Kernel end (ns)
32     | 8    | tfirst_tx               | LE         | First result byte tx (ns)
40     | 8    | tlast_tx                | LE         | Last result byte tx (ns)
48     | 4    | output_length_samples   | LE         | Output W
52     | 4    | output_channels         | LE         | Output C
56     | 4    | total_bytes             | LE         | Total result size (W×C×4)
60     | 4    | offset_bytes            | LE         | Offset of this chunk
64     | 4    | chunk_length            | LE         | Bytes in this chunk
68     | 4    | flags                   | LE         | CORTEX_CHUNK_FLAG_LAST
72     | N    | sample_data             | LE         | Float32 samples (LE)
```

**Total payload size**: 72 + chunk_length bytes

**Field descriptions**:

- `session_id`: Session identifier from CONFIG. Harness MUST verify this matches. Mismatch indicates adapter restart.

- `sequence`: Window sequence number from WINDOW_CHUNK. Harness uses this to match results with inputs.

- `tin`: Device timestamp (nanoseconds) when final WINDOW_CHUNK was received and decoded. Relative to adapter boot time.

- `tstart`: Device timestamp when kernel `process()` function was invoked.

- `tend`: Device timestamp when kernel `process()` function returned.

- `tfirst_tx`: Device timestamp when first byte of result was transmitted (start of first RESULT_CHUNK send).

- `tlast_tx`: Device timestamp when last byte of result was transmitted (end of final RESULT_CHUNK send).

- `output_length_samples`: Output window length (W). SHOULD match ACK dimensions unless kernel is adaptive.

- `output_channels`: Output channel count (C). SHOULD match ACK dimensions unless kernel is adaptive.

- `total_bytes`, `offset_bytes`, `chunk_length`, `flags`: Same semantics as WINDOW_CHUNK (see Section 4.3.5).

- `sample_data`: Float32 output samples in little-endian IEEE-754 format. Row-major order (all channels for sample 0, then all channels for sample 1, etc.).

**Timing field semantics**:

All timestamps are nanoseconds since an arbitrary epoch (typically adapter boot time). They are NOT wall-clock times.

The harness computes adapter overhead as:
```
processing_latency = tend - tstart
transmission_latency = tlast_tx - tfirst_tx
total_device_latency = tlast_tx - tin
```

See Section 6 (Telemetry) for complete latency decomposition.

**Chunking behavior**:

Identical to WINDOW_CHUNK. Large results (> 8KB) are split across multiple RESULT_CHUNK frames. All chunks for a given result share the same `session_id` and `sequence`.

**Metadata redundancy**: All chunks include the full metadata fields (session_id, timestamps, dimensions). The receiver extracts metadata from the first chunk (offset == 0) and ignores it in subsequent chunks. This redundancy simplifies parsing (no special-case logic for first chunk).

**Example (single chunk)**:

```
session_id:              0x4A7F3C21
sequence:                1
tin:                     1234567890123456  (ns)
tstart:                  1234567890123500
tend:                    1234567890123600
tfirst_tx:               1234567890123650
tlast_tx:                1234567890123700
output_length_samples:   160
output_channels:         64
total_bytes:             40960
offset_bytes:            0
chunk_length:            40960
flags:                   0x00000001  (CORTEX_CHUNK_FLAG_LAST)

Payload size: 72 + 40960 = 41032 bytes
```

**Validation requirements**:

A conformant harness:
- MUST verify `session_id` matches CONFIG
- MUST verify `sequence` matches expected value (monotonic)
- SHOULD verify timestamps are monotonic: tin <= tstart <= tend <= tfirst_tx <= tlast_tx
- MUST verify output dimensions match ACK (or CONFIG if ACK was 0)

### 4.3.7 ERROR Frame (0x06)

**Direction**: Either (typically Adapter → Harness)

**Purpose**: Report error conditions (protocol errors, kernel failures, validation errors).

**When sent**: Any time an error occurs

**Payload structure**:

```
Offset | Size | Field          | Endianness | Description
-------|------|----------------|------------|---------------------------
0      | 4    | error_code     | LE         | CORTEX_ERROR_* constant
4      | 256  | error_message  | N/A        | Human-readable (null-term)
```

**Total payload size**: 260 bytes

**Field descriptions**:

- `error_code`: Numeric error code (see table below). Used for programmatic error handling.

- `error_message`: Human-readable error description. NULL-terminated string up to 256 bytes. Used for logging and debugging.

**Standard error codes**:

| Code | Name                        | Description |
|------|-----------------------------|-------------|
| 1    | CORTEX_ERROR_TIMEOUT        | Operation timed out |
| 2    | CORTEX_ERROR_INVALID_FRAME  | Malformed frame received |
| 3    | CORTEX_ERROR_CALIBRATION_TOOBIG | Calibration state exceeds 16 MB |
| 4    | CORTEX_ERROR_KERNEL_INIT_FAILED | Kernel initialization failed |
| 5    | CORTEX_ERROR_KERNEL_EXEC_FAILED | Kernel execution failed |
| 6    | CORTEX_ERROR_SESSION_MISMATCH   | Session ID doesn't match CONFIG |
| 7    | CORTEX_ERROR_VERSION_MISMATCH   | Protocol version incompatible |
| 8    | CORTEX_ERROR_SHUTDOWN           | Adapter shutting down |

**Example**:

```
error_code:    4  (CORTEX_ERROR_KERNEL_INIT_FAILED)
error_message: "Failed to load kernel 'ica@f32': library not found"
```

**Hex dump**:

```
00000000: 04 00 00 00 46 61 69 6c  65 64 20 74 6f 20 6c 6f  |....Failed to lo|
00000010: 61 64 20 6b 65 72 6e 65  6c 20 27 69 63 61 40 66  |ad kernel 'ica@f|
00000020: 33 32 27 3a 20 6c 69 62  72 61 72 79 20 6e 6f 74  |32': library not|
00000030: 20 66 6f 75 6e 64 00 00  00 00 00 00 00 00 00 00  | found..........|
```

**Error handling**:

A conformant implementation:
- MAY send ERROR at any time after transport connection
- SHOULD include diagnostic information in `error_message` (file paths, system errors, etc.)
- MAY close the transport after sending ERROR (graceful shutdown)
- MUST NOT send additional frames after ERROR (protocol ends)

A conformant receiver:
- MUST handle ERROR frames at any point in the protocol state machine
- SHOULD log the error message for debugging
- SHOULD close the transport connection after receiving ERROR

---

## 4.4 Protocol State Machine

### 4.4.1 Overview

The CORTEX protocol follows a strict state machine with well-defined transitions. This ensures predictable error handling, prevents message reordering, and enables timeout-based failure detection.

### 4.4.2 States

A conformant implementation SHALL track the following protocol states:

**INIT**
- Initial state after transport connection established
- Waiting for HELLO from adapter
- Valid transitions: → HANDSHAKE (on HELLO), → ERROR (on timeout/error)

**HANDSHAKE**
- CONFIG sent, waiting for ACK
- Valid transitions: → READY (on ACK), → ERROR (on timeout/error)

**READY**
- Configuration complete, ready to process windows
- Valid transitions: → EXECUTING (on WINDOW_CHUNK), → ERROR (on error)

**EXECUTING**
- Window sent, waiting for RESULT
- Valid transitions: → READY (on RESULT), → ERROR (on timeout/error)

**ERROR**
- Error occurred, protocol terminated
- Valid transitions: (terminal state)

### 4.4.3 State Diagram

```
                      ┌──────┐
                      │ INIT │
                      └───┬──┘
                          │ HELLO received
                          ▼
                    ┌─────────────┐
                    │  HANDSHAKE  │
                    └──────┬──────┘
                           │ CONFIG sent, ACK received
                           ▼
                    ┌────────────┐
          ┌─────────┤   READY    │◄─────────┐
          │         └────────────┘          │
          │ WINDOW_CHUNK sent               │ RESULT received
          ▼                                 │
    ┌──────────────┐                        │
    │  EXECUTING   │────────────────────────┘
    └──────────────┘

    Any state can transition to ERROR on:
      - Timeout
      - Protocol error (CRC, MAGIC, VERSION mismatch)
      - Adapter error (ERROR frame received)
```

### 4.4.4 Handshake Sequence

The handshake establishes protocol compatibility and configures the kernel.

```
Harness                                    Adapter
   │                                          │
   │ [Transport connected]                    │ [Adapter process starts]
   │                                          │
   │◄──────────── HELLO ────────────────────│  STATE: INIT
   │                                          │  - Advertise capabilities
   │ [Validate ABI version]                   │  - List available kernels
   │ [Select kernel from list]                │
   │                                          │
   │────────────► CONFIG ───────────────────►│  STATE: HANDSHAKE
   │              - session_id                │
   │              - kernel name               │  [Load kernel library]
   │              - dimensions (W, H, C)      │  [Allocate buffers]
   │              - calibration state         │  [Initialize kernel]
   │                                          │
   │                                          │  [Determine output dims]
   │◄──────────── ACK ──────────────────────│  STATE: READY
   │              - output_window_length      │
   │              - output_channels           │
   │                                          │
   │ [Allocate output buffer]                 │
   │ [STATE: READY]                           │
```

**Timeout**: 5000ms (CORTEX_HANDSHAKE_TIMEOUT_MS)

A conformant implementation:
- MUST send HELLO immediately after transport connection
- MUST wait for CONFIG before sending ACK
- MUST NOT process windows before receiving CONFIG and sending ACK
- SHALL return to ERROR state if any handshake frame is malformed or times out

### 4.4.5 Window Execution Sequence

After successful handshake, the harness sends windows and receives results.

```
Harness                                    Adapter
   │                                          │
   │ [STATE: READY]                           │ [STATE: READY]
   │                                          │
   │────► WINDOW_CHUNK (seq=1, chunk 1/5) ──►│
   │────► WINDOW_CHUNK (seq=1, chunk 2/5) ──►│
   │────► WINDOW_CHUNK (seq=1, chunk 3/5) ──►│  [Reassemble chunks]
   │────► WINDOW_CHUNK (seq=1, chunk 4/5) ──►│
   │────► WINDOW_CHUNK (seq=1, chunk 5/5) ──►│  [CORTEX_CHUNK_FLAG_LAST]
   │                                          │
   │ [STATE: EXECUTING]                       │  timestamp tin
   │                                          │
   │                                          │  timestamp tstart
   │                                          │  kernel.process(input, output)
   │                                          │  timestamp tend
   │                                          │
   │                                          │  timestamp tfirst_tx
   │◄──── RESULT_CHUNK (seq=1, chunk 1/5) ───│
   │◄──── RESULT_CHUNK (seq=1, chunk 2/5) ───│
   │◄──── RESULT_CHUNK (seq=1, chunk 3/5) ───│  [Send chunks]
   │◄──── RESULT_CHUNK (seq=1, chunk 4/5) ───│
   │◄──── RESULT_CHUNK (seq=1, chunk 5/5) ───│  timestamp tlast_tx
   │                                          │
   │ [Reassemble chunks]                      │
   │ [Validate session_id, sequence]          │
   │ [Extract timing data]                    │
   │ [STATE: READY]                           │ [STATE: READY]
   │                                          │
   │  [Repeat for next window...]             │
```

**Timeout**: 10000ms per window (CORTEX_WINDOW_TIMEOUT_MS)

A conformant implementation:
- MUST increment `sequence` for each new window
- MUST match RESULT `sequence` with WINDOW_CHUNK `sequence`
- MUST NOT send the next window until receiving the previous RESULT
- SHALL return to ERROR state if sequence mismatch or timeout occurs

### 4.4.6 Error Handling Sequence

Error frames can be sent at any time to report failures.

```
Harness                                    Adapter
   │                                          │
   │────► WINDOW_CHUNK (seq=1) ─────────────►│
   │                                          │
   │                                          │  [Kernel execution fails]
   │                                          │
   │◄───────── ERROR (code=5) ───────────────│
   │           "Kernel NaN detected"          │
   │                                          │
   │ [Log error]                              │
   │ [STATE: ERROR]                           │ [STATE: ERROR]
   │ [Close transport]                        │ [Close transport]
```

A conformant implementation:
- MAY send ERROR at any state
- SHOULD include detailed error_message for diagnostics
- MUST transition to ERROR state after sending ERROR
- MUST close transport connection after ERROR (no recovery)

---

## 4.5 Chunking

### 4.5.1 Overview

Large data payloads (input windows, output results) are split into fixed-size chunks to avoid requiring large contiguous frame buffers and to optimize network transmission. Chunking is transparent to the application layer (callers send/receive complete buffers; the protocol layer handles chunking automatically).

### 4.5.2 Chunk Size

A conformant implementation SHOULD use a chunk size of 8192 bytes (8 KB).

This value is defined as `CORTEX_CHUNK_SIZE` in `cortex_wire.h`:

```c
#define CORTEX_CHUNK_SIZE (8 * 1024)
```

**Rationale**:

- **Network MTU**: 8KB fits within jumbo frame MTU (9000 bytes) with room for protocol overhead
- **Cache efficiency**: 8KB aligns with typical L1/L2 cache line sizes (64-256 bytes)
- **Memory fragmentation**: Smaller chunks reduce heap fragmentation on embedded systems
- **Latency**: Not too small (excessive overhead) or too large (head-of-line blocking)

Implementations MAY use different chunk sizes based on platform constraints, but 8KB is RECOMMENDED for interoperability and performance.

### 4.5.3 Chunking Algorithm (Sender)

A conformant sender SHALL split data larger than CORTEX_CHUNK_SIZE as follows:

```
Input: data buffer (size N bytes), sequence number

1. total_bytes = N
2. offset_bytes = 0
3. while (offset_bytes < total_bytes):
4.     chunk_length = min(CORTEX_CHUNK_SIZE, total_bytes - offset_bytes)
5.     is_last = (offset_bytes + chunk_length == total_bytes)
6.     flags = is_last ? CORTEX_CHUNK_FLAG_LAST : 0
7.
8.     Send frame:
9.         sequence       = sequence
10.        total_bytes    = N
11.        offset_bytes   = offset_bytes
12.        chunk_length   = chunk_length
13.        flags          = flags
14.        sample_data    = data[offset_bytes : offset_bytes + chunk_length]
15.
16.    offset_bytes += chunk_length
```

**Example**: 40KB window, 8KB chunks

```
Chunk 1: offset=0,     length=8192, flags=0x0
Chunk 2: offset=8192,  length=8192, flags=0x0
Chunk 3: offset=16384, length=8192, flags=0x0
Chunk 4: offset=24576, length=8192, flags=0x0
Chunk 5: offset=32768, length=8192, flags=0x1  (LAST)
```

### 4.5.4 Reassembly Algorithm (Receiver)

A conformant receiver SHALL reassemble chunks as follows:

```
Input: reassembly buffer (allocated to size from first chunk)

1. Wait for first chunk (offset == 0)
2. Extract total_bytes, allocate buffer if needed
3.
4. received_bytes = 0
5. while (true):
6.     Receive chunk frame
7.     Validate:
8.         - sequence matches expected
9.         - offset_bytes + chunk_length <= total_bytes
10.        - offset_bytes == received_bytes  (no gaps)
11.
12.    memcpy(buffer + offset_bytes, chunk_data, chunk_length)
13.    received_bytes += chunk_length
14.
15.    if (flags & CORTEX_CHUNK_FLAG_LAST):
16.        if (received_bytes != total_bytes):
17.            return ERROR_INCOMPLETE
18.        return SUCCESS
```

**Validation requirements**:

A conformant receiver:
- MUST verify chunks arrive in order (offset_bytes increases monotonically)
- MUST verify no gaps exist (offset_bytes == previous_offset + previous_length)
- MUST verify no overlaps exist (offset + length <= total_bytes)
- MUST verify CORTEX_CHUNK_FLAG_LAST is set on the final chunk
- MUST verify received_bytes == total_bytes when LAST flag is set
- SHALL return `CORTEX_ECHUNK_INCOMPLETE` (-2101) if validation fails

### 4.5.5 Chunk Sequence Numbering

The `sequence` field in WINDOW_CHUNK and RESULT_CHUNK frames identifies which window the chunk belongs to. All chunks for a given window share the same sequence number.

A conformant implementation:
- MUST use monotonically increasing sequence numbers (starts at 1)
- MUST use the same sequence for all chunks of a window
- MUST increment sequence for each new window
- SHOULD use uint32_t for sequence (wraps after 4 billion windows, acceptable)

**Sequence matching**: The adapter MUST return RESULT with the same sequence number as the corresponding WINDOW_CHUNK. This allows the harness to match results with inputs, even if windows are processed out of order (future extension for pipelining).

### 4.5.6 Error Handling

**Chunk timeout**:

If a chunk does not arrive within CORTEX_CHUNK_TIMEOUT_MS (1000ms), the receiver:
- MUST abort reassembly
- SHOULD discard partial window/result
- SHOULD transition to ERROR state
- MAY attempt to resynchronize by hunting for MAGIC

**Sequence mismatch**:

If a chunk arrives with an unexpected sequence number:
- MUST return `CORTEX_ECHUNK_SEQUENCE_MISMATCH` (-2100)
- SHOULD transition to ERROR state
- SHOULD NOT attempt to buffer multiple windows (no reordering support in protocol v1)

**Incomplete transfer**:

If the final chunk is received but `received_bytes != total_bytes`:
- MUST return `CORTEX_ECHUNK_INCOMPLETE` (-2101)
- SHOULD log offset/length values for debugging
- MUST discard partial data

### 4.5.7 Optimization Notes

**Zero-copy transmission**: Implementations MAY use scatter-gather I/O (e.g., `writev(2)`) to avoid copying chunk headers and data:

```c
struct iovec iov[2];
iov[0].iov_base = &chunk_header;
iov[0].iov_len = sizeof(chunk_header);
iov[1].iov_base = data + offset;
iov[1].iov_len = chunk_length;
writev(fd, iov, 2);
```

**Pipelining**: Protocol v1 does NOT support sending multiple windows before receiving results (no pipelining). The harness MUST wait for RESULT before sending the next WINDOW_CHUNK. Future protocol versions may relax this constraint.

**Adaptive chunk size**: Implementations MAY dynamically adjust chunk size based on transport characteristics (e.g., 16KB chunks for high-bandwidth TCP, 1KB chunks for UART). However, all chunks MUST include accurate offset_bytes and chunk_length fields.

---

## 4.6 Cross-References

**Related sections**:
- Section 2.2.2 (Adapter Lifecycle): Describes adapter spawn/shutdown behavior
- Section 3.4.3 (Calibration State Transfer): Defines calibration_state blob format
- Section 5.3 (Error Codes): Complete error code enumeration
- Section 6 (Telemetry and Timing): Device-side timestamp semantics and latency decomposition

**Implementation references**:
- `sdk/adapter/include/cortex_wire.h`: Wire format struct definitions
- `sdk/adapter/include/cortex_protocol.h`: Protocol API (send/recv frame functions)
- `sdk/adapter/include/cortex_endian.h`: Endianness conversion helpers
- `sdk/adapter/lib/protocol/protocol.c`: Protocol layer implementation (MAGIC hunting, CRC validation)
- `sdk/adapter/lib/protocol/crc32.c`: IEEE 802.3 CRC32 implementation
- `docs/reference/adapter-protocol.md`: Wire format reference documentation (477 lines)

---

## 4.7 Conformance Testing

To verify wire protocol conformance, implementations MUST pass the following test suites:

**CRC validation**:
```bash
make -C tests test-protocol
```

Tests verify:
- CRC32 computation correctness (IEEE 802.3 polynomial)
- CRC detection of single-bit errors, multi-bit errors, truncation
- Endianness conversion (little-endian wire format on all platforms)

**Frame parsing**:
```bash
make -C tests test-adapter-smoke
```

Tests verify:
- MAGIC hunting in corrupt streams
- Version mismatch detection
- Payload length validation
- Chunk reassembly correctness

**End-to-end protocol**:
```bash
make -C tests test-adapter-all-kernels
```

Tests verify:
- Complete handshake sequence (HELLO → CONFIG → ACK)
- Window execution (WINDOW_CHUNK → RESULT_CHUNK)
- Error frame handling
- Session ID validation
- Timeout behavior

All tests MUST pass before an adapter implementation is considered conformant with this specification.

---

**End of Section 4**

---

# **Section 5: Configuration Schema**

## **5.1 Overview**

CORTEX v1.0 uses YAML-based configuration files to define benchmark runs. A conformant implementation MUST support YAML 1.2 syntax and MUST validate configurations against the schema defined in this section. Configuration files specify dataset parameters, real-time constraints, kernel selection, and telemetry output settings.

### **5.1.1 Design Rationale**

YAML was selected for the following reasons:

1. **Human Readability**: Research users can read and modify configurations without specialized tools
2. **Comment Support**: Inline documentation of parameter choices (critical for reproducibility)
3. **Complex Nesting**: Natural representation of hierarchical structures (kernel parameters, runtime constraints)
4. **Industry Adoption**: Proven standard in infrastructure automation (Kubernetes, Ansible, CI/CD)

The schema balances **verbosity** and **usability** through automatic kernel discovery (Section 5.1.7) while preserving explicit control when needed.

### **5.1.2 Versioning**

Configuration files MUST include a `cortex_version` field. This specification defines version `1`. Implementations MUST reject configurations with unrecognized versions.

Future versions MAY introduce breaking changes to field names, semantics, or validation rules. Minor extensions (new optional fields) SHOULD NOT increment the version number.

### **5.1.3 Platform-Specific Fields**

Some fields are **parsed but unused** on certain platforms due to OS limitations:

- `power.governor`, `power.turbo`: Ignored on macOS (no userspace CPU frequency control)
- `realtime.scheduler: "rr"`: Not supported on macOS (only `fifo`, `deadline`, `other`)
- `realtime.deadline.*`: Linux `SCHED_DEADLINE` parameters (not available on macOS)

Implementations MUST parse these fields without error but MAY log warnings when they have no effect. This design preserves cross-platform configuration portability.

### **5.1.4 Future Extensibility**

The following fields are **parsed but not currently used** by the harness:

- `system.name`, `system.description`: Run metadata (no database storage in v1.0)
- `benchmark.metrics`: Metric selection array (v1.0 collects all metrics)
- `output.include_raw_data`: Raw telemetry export flag (reserved for future use)

Implementations MUST accept these fields without error. They are reserved for future functionality and MUST NOT be repurposed for other uses.

---

## **5.2 YAML Structure**

### **5.2.1 Schema Definition**

A conformant run configuration MUST be valid YAML 1.2 with the following structure:

```yaml
cortex_version: 1                    # REQUIRED

system:                              # OPTIONAL
  name: string                       # Human-readable identifier
  description: string                # Run purpose or notes

dataset:                             # REQUIRED
  path: string                       # Filesystem path to dataset
  format: "float32"                  # Data type (only float32 in v1.0)
  channels: integer                  # Number of input channels (C)
  sample_rate_hz: integer            # Sampling rate in Hz (Fs)

realtime:                            # REQUIRED
  scheduler: string                  # "fifo" | "rr" | "deadline" | "other"
  priority: integer                  # Real-time priority (1-99)
  cpu_affinity: [integer, ...]       # CPU core IDs for pinning
  deadline_ms: integer               # Per-window deadline (milliseconds)
  deadline:                          # OPTIONAL (Linux SCHED_DEADLINE)
    runtime_us: integer              # Runtime budget (microseconds)
    period_us: integer               # Period (microseconds)
    deadline_us: integer             # Relative deadline (microseconds)

power:                               # OPTIONAL
  governor: string                   # "performance" | "powersave" | "ondemand"
  turbo: boolean                     # Disable turbo boost for stability

benchmark:                           # REQUIRED
  metrics: [string, ...]             # OPTIONAL: Metric selection (future)
  parameters:                        # REQUIRED
    duration_seconds: integer        # Total benchmark duration
    repeats: integer                 # Number of repetitions
    warmup_seconds: integer          # Warmup period before measurements
  load_profile: string               # "idle" | "medium" | "heavy"

output:                              # REQUIRED
  directory: string                  # Output directory path
  format: string                     # "ndjson" | "csv"
  include_raw_data: boolean          # OPTIONAL: Export raw telemetry (future)

plugins:                             # OPTIONAL (see Section 5.1.7)
  - name: string                     # Kernel name
    status: string                   # "draft" | "ready"
    spec_uri: string                 # Path to kernel spec directory
    spec_version: string             # OPTIONAL: Kernel version
    adapter_path: string             # Path to adapter binary (REQUIRED)
    params:                          # OPTIONAL: Kernel-specific parameters
      key: value                     # Arbitrary key-value pairs
    calibration_state: string        # OPTIONAL: Path to .cortex_state file
```

### **5.2.2 Field Semantics**

#### **cortex_version**
- **Type**: Integer
- **Requirement**: REQUIRED
- **Valid Values**: `1` for this specification
- **Purpose**: Schema version identification

Implementations MUST reject files with `cortex_version != 1`.

#### **system**
- **Type**: Object
- **Requirement**: OPTIONAL
- **Fields**:
  - `name` (string): Short identifier for the run
  - `description` (string): Free-text description

These fields are parsed but not used in v1.0. They are reserved for future run tracking and metadata export.

#### **dataset**
- **Type**: Object
- **Requirement**: REQUIRED
- **Fields**:
  - `path` (string): Absolute or relative path to dataset file or directory
  - `format` (string): Data encoding. MUST be `"float32"` in v1.0
  - `channels` (integer): Number of input channels. MUST be > 0
  - `sample_rate_hz` (integer): Sampling rate in Hz. MUST be > 0

The `path` field MUST refer to a readable file or directory. Implementations MUST verify accessibility during validation.

#### **realtime**
- **Type**: Object
- **Requirement**: REQUIRED
- **Fields**:
  - `scheduler` (string): Scheduling policy. Valid values:
    - `"fifo"`: SCHED_FIFO (Linux), TIME_CONSTRAINT_POLICY (macOS)
    - `"rr"`: SCHED_RR (Linux only, not supported on macOS)
    - `"deadline"`: SCHED_DEADLINE (Linux only, requires `deadline.*` fields)
    - `"other"`: SCHED_OTHER (Linux), THREAD_STANDARD_POLICY (macOS)
  - `priority` (integer): Real-time priority. MUST be in range [1, 99] for FIFO/RR. Ignored for `other` scheduler
  - `cpu_affinity` (array of integers): List of CPU core IDs for thread pinning. Empty array means no affinity
  - `deadline_ms` (integer): Window processing deadline in milliseconds. MUST be > 0

**SCHED_DEADLINE Parameters** (Linux only, OPTIONAL):
- `deadline.runtime_us`: CPU time budget per period (microseconds)
- `deadline.period_us`: Scheduling period (microseconds)
- `deadline.deadline_us`: Relative deadline (microseconds)

If `scheduler: "deadline"`, implementations MUST validate that all three `deadline.*` fields are present. On platforms without `SCHED_DEADLINE` support, implementations MUST reject this configuration.

The `cpu_affinity` array is converted to a bitmask internally. For example, `[0, 2]` becomes bitmask `0x5` (cores 0 and 2 enabled).

#### **power**
- **Type**: Object
- **Requirement**: OPTIONAL
- **Fields**:
  - `governor` (string): CPU frequency governor. Common values: `"performance"`, `"powersave"`, `"ondemand"`. Platform-specific
  - `turbo` (boolean): If `false`, disable turbo boost for measurement stability

These fields are **parsed but not used** on macOS. Linux implementations MAY use them to configure CPU power management if running with sufficient privileges.

#### **benchmark**
- **Type**: Object
- **Requirement**: REQUIRED
- **Fields**:
  - `metrics` (array of strings): OPTIONAL. Reserved for future metric selection. Valid values: `"latency"`, `"jitter"`, `"throughput"`, `"memory_usage"`, `"energy_consumption"`. Currently ignored (all metrics collected)
  - `parameters` (object): REQUIRED
    - `duration_seconds` (integer): Total benchmark duration. MUST be > 0
    - `repeats` (integer): Number of independent runs. MUST be ≥ 1
    - `warmup_seconds` (integer): Initial warmup period to discard. MUST be ≥ 0
  - `load_profile` (string): Background CPU load. Valid values:
    - `"idle"`: No artificial load (default)
    - `"medium"`: Moderate load (N/2 CPUs at 50% utilization)
    - `"heavy"`: High load (N CPUs at 90% utilization)

The `load_profile` feature requires the `stress-ng` system utility. If not available, implementations MUST fall back to `idle` mode with a warning message.

**Platform-Specific Recommendation**: On macOS, `load_profile: "medium"` is RECOMMENDED for reproducible results due to dynamic frequency scaling. See Section 5.2.3 for details.

#### **output**
- **Type**: Object
- **Requirement**: REQUIRED
- **Fields**:
  - `directory` (string): Output directory path. Created if it does not exist
  - `format` (string): Telemetry output format. Valid values: `"ndjson"` (default), `"csv"`
  - `include_raw_data` (boolean): OPTIONAL. Reserved for future raw telemetry export. Currently ignored

Implementations MUST create the output directory if it does not exist. If creation fails due to permissions or filesystem errors, validation MUST fail.

#### **plugins**
- **Type**: Array of objects
- **Requirement**: OPTIONAL (see Section 5.1.7)
- **Maximum Length**: 16 (defined by `CORTEX_MAX_PLUGINS`)

Each plugin entry MUST have the following fields:
- `name` (string): Kernel identifier. MUST match kernel directory name
- `status` (string): Kernel maturity level. Valid values: `"draft"`, `"ready"`
- `spec_uri` (string): Path to kernel specification directory (e.g., `primitives/kernels/v1/notch_iir@f32`)
- `adapter_path` (string): Path to device adapter binary. REQUIRED in explicit mode

Optional fields:
- `spec_version` (string): Kernel version (e.g., `"1.0.0"`). Parsed but not validated in v1.0
- `params` (object): Kernel-specific runtime parameters (see Section 5.3.4)
- `calibration_state` (string): Path to calibration state file for trainable kernels (ABI v3)

### **5.2.3 Platform-Specific Guidance**

#### **macOS Frequency Scaling**

On macOS, dynamic voltage and frequency scaling (DVFS) causes up to **49% performance variance** in idle mode. This degrades reproducibility of benchmark results.

**Recommended Configuration for macOS**:
```yaml
benchmark:
  load_profile: "medium"  # Forces frequency to remain elevated
```

**Empirical Evidence** (Fall 2025 validation on M1 MacBook Pro):

| Kernel | Idle Mean (µs) | Medium Mean (µs) | Variance |
|--------|----------------|------------------|----------|
| bandpass_fir | 4969 | 2554 | -48.6% |
| car | 36 | 20 | -45.5% |
| goertzel | 417 | 196 | -53.0% |
| notch_iir | 115 | 61 | -47.4% |

The `medium` load profile sustains background CPU activity sufficient to prevent frequency downscaling, improving measurement stability.

**Linux Alternative**: Users with root privileges MAY manually set the CPU governor:
```bash
sudo cpupower frequency-set --governor performance
```
Then use `load_profile: "idle"` in the configuration. This achieves equivalent stability without artificial load.

### **5.2.4 Validation Rules**

Implementations MUST enforce the following validation rules before executing a benchmark:

1. **Required Fields**:
   - `cortex_version`, `dataset`, `realtime`, `benchmark`, `output` MUST be present
   - `dataset.path`, `dataset.format`, `dataset.channels`, `dataset.sample_rate_hz` MUST be present
   - `realtime.scheduler`, `realtime.priority`, `realtime.cpu_affinity`, `realtime.deadline_ms` MUST be present
   - `benchmark.parameters.duration_seconds`, `benchmark.parameters.repeats`, `benchmark.parameters.warmup_seconds` MUST be present
   - `output.directory`, `output.format` MUST be present

2. **Type Validation**:
   - All integer fields MUST be integers (not floats or strings)
   - All string fields MUST be strings
   - All boolean fields MUST be booleans
   - `cpu_affinity` MUST be an array of integers
   - `plugins` MUST be an array of objects

3. **Range Validation**:
   - `cortex_version` MUST equal 1
   - `dataset.channels` MUST be > 0
   - `dataset.sample_rate_hz` MUST be > 0
   - `realtime.priority` MUST be in [1, 99] if scheduler is `fifo` or `rr`
   - `realtime.deadline_ms` MUST be > 0
   - `benchmark.parameters.duration_seconds` MUST be > 0
   - `benchmark.parameters.repeats` MUST be ≥ 1
   - `benchmark.parameters.warmup_seconds` MUST be ≥ 0
   - `plugins` array length MUST be ≤ 16 (CORTEX_MAX_PLUGINS)

4. **Enum Validation**:
   - `dataset.format` MUST be `"float32"` in v1.0
   - `realtime.scheduler` MUST be `"fifo"`, `"rr"`, `"deadline"`, or `"other"`
   - `benchmark.load_profile` MUST be `"idle"`, `"medium"`, or `"heavy"`
   - `output.format` MUST be `"ndjson"` or `"csv"`
   - `plugins[i].status` MUST be `"draft"` or `"ready"`

5. **Semantic Validation**:
   - `dataset.path` MUST refer to an accessible file or directory
   - If `realtime.scheduler` is `"deadline"`, all `deadline.*` fields MUST be present
   - Each `plugins[i].spec_uri` MUST point to a valid kernel specification directory
   - If plugins are specified, each entry MUST include `adapter_path`

6. **Cross-Field Validation**:
   - For each plugin, `runtime.channels` (from kernel spec) MUST equal `dataset.channels`
   - CPU core IDs in `cpu_affinity` MUST be valid for the target system

Implementations MUST report validation errors with the field path and reason (e.g., `"realtime.priority: value 150 exceeds maximum 99"`).

### **5.2.5 Default Values**

If the `plugins` section is omitted, implementations MUST enable auto-detection mode (see Section 5.1.7). All other top-level sections are REQUIRED and have no defaults.

Within the `benchmark` section:
- If `load_profile` is omitted, default to `"idle"`

### **5.2.6 Example Configurations**

#### **Example 1: Auto-Detection Mode**
```yaml
cortex_version: 1

dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  format: "float32"
  channels: 64
  sample_rate_hz: 160

realtime:
  scheduler: fifo
  priority: 90
  cpu_affinity: [0]
  deadline_ms: 500

benchmark:
  parameters:
    duration_seconds: 120
    repeats: 5
    warmup_seconds: 10
  load_profile: "medium"

output:
  directory: "results"
  format: "ndjson"

# No plugins section - automatically discover all built kernels
```

This configuration runs all built kernels from `primitives/kernels/v1/` in alphabetical order.

#### **Example 2: Explicit Plugin Selection**
```yaml
cortex_version: 1

system:
  name: "notch-filter-test"
  description: "Test notch filter with European power line frequency"

dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  format: "float32"
  channels: 64
  sample_rate_hz: 160

realtime:
  scheduler: fifo
  priority: 85
  cpu_affinity: [0]
  deadline_ms: 500

power:
  governor: "performance"
  turbo: false

benchmark:
  metrics: [latency, jitter, throughput]
  parameters:
    duration_seconds: 60
    repeats: 3
    warmup_seconds: 5
  load_profile: "idle"

output:
  directory: "results/notch-test"
  format: "ndjson"
  include_raw_data: false

plugins:
  - name: "notch_iir"
    status: ready
    spec_uri: "primitives/kernels/v1/notch_iir@f32"
    spec_version: "1.0.0"
    adapter_path: "primitives/adapters/v1/native/cortex_adapter_native"
    params:
      f0_hz: 50.0  # European power line (50Hz)
      Q: 35.0      # Narrow notch
```

This configuration runs a single kernel with custom parameters.

### **5.2.7 Kernel Auto-Detection**

When the `plugins` section is **omitted** from the configuration file, implementations MUST automatically discover and run all built kernels.

**Discovery Algorithm**:
1. Scan directories matching pattern `primitives/kernels/v{N}/{name}@{dtype}/`
2. For each directory, check for:
   - Implementation file `{name}.c`
   - Compiled shared library `lib{name}.dylib` (macOS) or `lib{name}.so` (Linux)
3. If both exist, include the kernel in the run
4. Load runtime configuration from `spec.yaml` if present
5. If `spec.yaml` is missing, use default configuration (W=160, H=80, C from dataset, dtype=float32)
6. Sort discovered kernels alphabetically by name for reproducibility

**Auto-Detection vs. Explicit Mode**:

| Feature | Auto-Detection | Explicit |
|---------|----------------|----------|
| Configuration verbosity | Minimal (no `plugins:` section) | Full specification required |
| Kernel selection | All built kernels | User-specified subset |
| Parameter customization | Defaults from `spec.yaml` | Custom `params` per kernel |
| Use case | Comprehensive benchmarking | Focused testing, production |

**Empty Plugins Array**: If the configuration includes an empty `plugins: []` array, implementations MUST run zero kernels. This is valid for testing the harness infrastructure without kernel execution.

**Kernel Filtering**: Implementations MAY provide a runtime mechanism (e.g., environment variable `CORTEX_KERNEL_FILTER`) to filter auto-detected kernels without modifying the configuration file. This is OPTIONAL and not part of the normative schema.

---

## **5.3 Kernel Specification Format**

Each kernel MUST provide a `spec.yaml` file in its directory (e.g., `primitives/kernels/v1/notch_iir@f32/spec.yaml`). This file defines the kernel's ABI contract, numerical tolerances, and validation requirements.

### **5.3.1 Schema Definition**

CORTEX v1.0 supports **two specification formats**:

1. **Modern Format** (RECOMMENDED): Kernel metadata nested under `kernel:` key
2. **Legacy Format**: Flat structure with top-level `name`, `version`, `dtype`

Implementations MUST support both formats for backward compatibility. The legacy format is deprecated and SHOULD NOT be used for new kernels.

#### **Modern Format**
```yaml
kernel:
  name: string                       # Kernel identifier
  version: string                    # Semantic version
  dtype: string                      # Data type (e.g., "float32")
  description: string                # OPTIONAL: Brief description
  trainable: boolean                 # OPTIONAL: Requires calibration (default: false)

abi:
  version: integer                   # OPTIONAL: ABI version (default: 1)
  capabilities: [string, ...]        # OPTIONAL: Required capabilities
  input_shape: [integer, integer]    # [window_length, channels]
  output_shape: [integer, integer]   # [window_length, channels]
  stateful: boolean                  # OPTIONAL: Maintains state (default: false)

numerical:
  tolerances:
    float32:                         # Per-dtype tolerances
      rtol: float                    # Relative tolerance
      atol: float                    # Absolute tolerance
    quantized:                       # OPTIONAL: For q15/q7 variants
      rtol: float
      atol: float

oracle:
  path: string                       # Path to oracle script (e.g., "oracle.py")
  function: string                   # Oracle function name
  dependencies: [string, ...]        # OPTIONAL: Required packages

calibration:                         # OPTIONAL: For trainable kernels
  min_windows: integer               # Minimum calibration data
  recommended_windows: integer
  max_duration_sec: integer

algorithm:                           # OPTIONAL: Algorithm metadata
  family: string
  variant: string
  # ... kernel-specific fields

references:                          # OPTIONAL: Citations
  - string                           # Bibliography entries
```

#### **Legacy Format**
```yaml
name: string
version: string
dtype: string
description: string                  # OPTIONAL

runtime:
  window_length_samples: integer
  hop_samples: integer
  channels: integer
  allow_in_place: boolean

params: {}                           # Kernel-specific parameters

tolerances:
  rtol: float
  atol: float

author: string                       # OPTIONAL
purpose: string                      # OPTIONAL
category: string                     # OPTIONAL
complexity: string                   # OPTIONAL
```

The legacy format is simpler but lacks per-dtype tolerances and trainability support. Implementations MUST detect the format by checking for the presence of a top-level `kernel:` key.

### **5.3.2 Field Semantics**

#### **kernel** (Modern Format)
- `name`: MUST match the kernel directory name
- `version`: SHOULD follow semantic versioning (e.g., `"1.0.0"`)
- `dtype`: Data type identifier. Valid values in v1.0: `"float32"`
- `description`: OPTIONAL human-readable description
- `trainable`: If `true`, kernel requires offline calibration (ABI v3 feature)

#### **abi**
- `version`: ABI version. MUST be `1` or `3`. Default is `1`
- `capabilities`: Array of required capabilities. Valid values:
  - `"offline_calibration"`: Requires `cortex_calibrate()` before use
- `input_shape`: `[W, C]` where W is window length and C is channels. Use `null` for runtime-determined values (e.g., `[160, null]` means W=160, C from dataset)
- `output_shape`: `[W_out, C_out]`. Output dimensions. Use `null` for runtime-determined values
- `stateful`: If `true`, kernel maintains internal state across windows

**Shape Inference Rules**:
- If `input_shape[1]` is `null`, implementations MUST substitute `dataset.channels`
- If `output_shape[1]` is `null`, implementations MUST substitute `dataset.channels`
- Window length (`input_shape[0]`) MUST be specified explicitly in v1.0

#### **numerical**
- `tolerances.float32.rtol`: Relative tolerance for floating-point validation (typically 1.0e-5)
- `tolerances.float32.atol`: Absolute tolerance for near-zero values (typically 1.0e-6)
- `tolerances.quantized`: OPTIONAL. Tolerances for quantized variants (q15, q7)

Tolerances define acceptable error when comparing kernel output to oracle output. See Section 6 (Validation Protocol) for usage.

#### **oracle**
- `path`: Relative path to oracle implementation (e.g., `"oracle.py"`)
- `function`: Oracle function name. The oracle module MUST export this function
- `dependencies`: OPTIONAL. List of Python packages required to run the oracle

Implementations MUST resolve `path` relative to the kernel directory.

#### **calibration** (Trainable Kernels Only)
- `min_windows`: Minimum number of training windows for convergence
- `recommended_windows`: Recommended training set size
- `max_duration_sec`: Typical calibration duration

This section is REQUIRED if `trainable: true`.

#### **algorithm** (Optional Metadata)
- `family`: Algorithm family (e.g., `"Independent Component Analysis"`)
- `variant`: Specific variant (e.g., `"FastICA with symmetric decorrelation"`)
- Additional fields MAY be included for documentation purposes

#### **references** (Optional Metadata)
- Array of bibliography entries (typically academic papers)

### **5.3.3 Runtime Parameters**

Kernels MAY accept runtime parameters specified in the run configuration `plugins[i].params` object. Parameters are kernel-specific and defined by the kernel developer.

**Common Parameter Patterns**:

| Kernel | Parameters | Description |
|--------|------------|-------------|
| `notch_iir` | `f0_hz`, `Q` | Notch frequency (Hz) and quality factor |
| `goertzel` | `alpha_low`, `alpha_high`, `beta_low`, `beta_high` | Frequency bands for power estimation |
| `car` | `exclude_channels` | Channel indices to exclude from reference |

Implementations MUST pass parameters to the kernel via the accessor API defined in `sdk/kernel/lib/params/README.md`. Parameters are serialized as JSON and made available through `cortex_params_get_*()` functions.

**Example Parameter Usage**:
```yaml
plugins:
  - name: "notch_iir"
    params:
      f0_hz: 60.0  # Notch at 60Hz
      Q: 30.0      # Quality factor
```

The kernel accesses parameters in C:
```c
double f0_hz = cortex_params_get_double(params, "f0_hz", 60.0);  // Default 60.0
double Q = cortex_params_get_double(params, "Q", 30.0);
```

If a parameter is not provided, implementations MUST use the kernel's default value. Kernels MUST document available parameters in their README files.

### **5.3.4 Validation Rules**

Implementations MUST validate kernel specifications during configuration loading:

1. **Required Fields** (Modern Format):
   - `kernel.name`, `kernel.version`, `kernel.dtype` MUST be present
   - `abi.input_shape`, `abi.output_shape` MUST be present
   - `numerical.tolerances.float32.rtol`, `numerical.tolerances.float32.atol` MUST be present
   - `oracle.path`, `oracle.function` MUST be present

2. **Required Fields** (Legacy Format):
   - `name`, `version`, `dtype` MUST be present
   - `runtime.window_length_samples`, `runtime.hop_samples`, `runtime.channels` MUST be present
   - `tolerances.rtol`, `tolerances.atol` MUST be present

3. **Type Validation**:
   - All integer fields MUST be integers
   - All float fields MUST be floats or integers
   - All boolean fields MUST be booleans
   - `abi.input_shape`, `abi.output_shape` MUST be 2-element arrays

4. **Semantic Validation**:
   - `oracle.path` MUST point to an existing file
   - If `trainable: true`, `calibration` section MUST be present
   - If `abi.version: 3`, `capabilities` MUST include `"offline_calibration"`

5. **Cross-Field Validation**:
   - `kernel.name` MUST match the kernel directory name
   - `kernel.dtype` MUST match the directory suffix (e.g., `@f32` → `dtype: "float32"`)

Implementations MUST report validation errors with the file path and specific issue.

### **5.3.5 Example Specifications**

#### **Example 1: Stateless Kernel (Modern Format)**
```yaml
kernel:
  name: "goertzel"
  version: "1.0.0"
  dtype: "float32"

abi:
  input_shape: [160, null]  # W=160, C from dataset
  output_shape: [2, null]   # 2 frequency bands, C from dataset
  stateful: false

numerical:
  tolerances:
    float32:
      rtol: 1.0e-5
      atol: 1.0e-6

oracle:
  path: "oracle.py"
  function: "goertzel_bandpower_ref"
  dependencies: ["numpy"]
```

#### **Example 2: Stateful Kernel (Modern Format)**
```yaml
kernel:
  name: "notch_iir"
  version: "1.0.0"
  dtype: "float32"

abi:
  input_shape: [160, null]
  output_shape: [160, null]
  stateful: true            # IIR filter maintains state

numerical:
  tolerances:
    float32:
      rtol: 1.0e-5
      atol: 1.0e-6
    quantized:
      rtol: 1.0e-3
      atol: 1.0e-3

oracle:
  path: "oracle.py"
  function: "notch_ref"
  dependencies: ["scipy"]
```

#### **Example 3: Trainable Kernel (Modern Format)**
```yaml
kernel:
  name: "ica"
  version: "v1"
  dtype: "float32"
  description: "Independent Component Analysis for artifact removal"
  trainable: true

abi:
  version: 3
  capabilities:
    - offline_calibration
  input_shape:
    window_length: 160
    channels: 64
  output_shape:
    window_length: 160
    channels: 64
  stateful: false

calibration:
  min_windows: 100
  recommended_windows: 500
  max_duration_sec: 300

algorithm:
  family: "Independent Component Analysis"
  variant: "FastICA (symmetric decorrelation)"
  nonlinearity: "tanh"
  max_iterations: 200
  tolerance: 1.0e-4

numerical:
  tolerance:
    rtol: 1.0e-4
    atol: 1.0e-5

oracle:
  calibrate_function: "calibrate_ica"
  apply_function: "apply_ica"
  path: "oracle.py"
  dependencies: ["numpy", "scipy", "sklearn"]

references:
  - "Hyvärinen, A., & Oja, E. (2000). Independent component analysis: algorithms and applications. Neural networks, 13(4-5), 411-430."
```

#### **Example 4: No-Op Kernel (Legacy Format)**
```yaml
name: "noop"
version: "1.0.0"
dtype: "float32"
description: "Identity function for measuring harness overhead"

runtime:
  window_length_samples: 160
  hop_samples: 80
  channels: 64
  allow_in_place: true

params: {}

tolerances:
  rtol: 1.0e-7
  atol: 1.0e-9

author: "Weston Voglesonger"
purpose: "Harness overhead measurement"
category: "benchmark"
complexity: "O(1)"
```

---

## **5.4 Rationale**

### **5.4.1 Why YAML Over JSON/TOML?**

**JSON** lacks comment support, making it unsuitable for research configurations where parameter choices require documentation for reproducibility.

**TOML** has inconsistent complex nesting support and less ecosystem adoption in infrastructure tools.

**YAML** provides:
- Rich comment syntax for inline documentation
- Natural hierarchical structure for kernel parameters
- Wide tool support (editors, validators, parsers)
- Industry standard status (Kubernetes, CI/CD, Ansible)

### **5.4.2 Why Auto-Detection?**

Manual kernel listing in configurations creates maintenance burden:
1. New kernels require configuration updates
2. "Run all benchmarks" workflows are verbose
3. Risk of forgetting to include kernels in comprehensive tests

Auto-detection:
- Reduces configuration verbosity
- Ensures new built kernels are automatically included
- Preserves explicit control when needed (researchers can still list specific kernels)

The design trades configuration explicitness for usability. The trade-off is appropriate for research prototyping while preserving production use cases.

### **5.4.3 Why Parsed-But-Unused Fields?**

Three categories justify accepting unused fields:

1. **Platform Differences**: `power.governor` works on Linux but not macOS. Rejecting it on macOS breaks cross-platform configurations
2. **Future Extensibility**: `system.name`, `benchmark.metrics` are reserved for planned features. Accepting them now avoids migration pain
3. **Documentation Value**: Even if unused, fields like `system.description` provide context for human readers

Implementations SHOULD log warnings for unused fields to inform users, but MUST NOT reject configurations.

### **5.4.4 Why Two Kernel Spec Formats?**

The **legacy format** predates multi-dtype support and trainable kernels. It remains in use for the `noop` kernel (a simple benchmark primitive).

The **modern format** supports:
- Per-dtype tolerances (necessary for quantized variants)
- Trainability metadata (ABI v3 calibration requirements)
- Structured ABI versioning

Supporting both formats:
- Preserves backward compatibility with existing kernels
- Avoids forcing immediate migration of simple kernels
- Documents recommended practice (modern format) while accepting legacy

Future versions MAY deprecate the legacy format after all kernels migrate.

### **5.4.5 Why Maximum 16 Plugins?**

The `CORTEX_MAX_PLUGINS` limit (16) reflects:
1. **Stack Allocation**: Plugin metadata is stack-allocated for simplicity. Large arrays risk stack overflow
2. **Practical Constraints**: Current repository has 8 kernels. 16 provides 2× headroom
3. **Performance**: More plugins increase benchmark duration linearly. 16 is reasonable for overnight runs

The limit MAY be increased in future versions if workloads demand it. The static limit simplifies implementation and avoids dynamic allocation in performance-critical paths.

---

## **5.5 Conformance**

An implementation conforms to this specification if:

1. It accepts all valid YAML files matching the schema in Section 5.2
2. It rejects invalid files with descriptive error messages
3. It enforces all validation rules in Sections 5.2.4 and 5.3.4
4. It supports both modern and legacy kernel specification formats
5. It implements auto-detection mode when `plugins` is omitted
6. It handles platform-specific fields gracefully (parse but may ignore)
7. It respects the `CORTEX_MAX_PLUGINS` limit

Implementations MAY provide extensions (e.g., environment variable overrides, additional output formats) as long as they remain compatible with this specification.

---

**End of Section 5**

---

# 6. Telemetry Format

## 6.1 Overview

This section defines the telemetry record schema, timestamp semantics, and output format specifications for CORTEX v1.0. Telemetry records capture per-window execution metrics, enabling latency analysis, deadline tracking, and performance profiling of BCI signal processing kernels.

The telemetry subsystem provides:
- High-resolution timing measurements (nanosecond precision)
- Deadline miss detection
- Device-side timing instrumentation for remote execution
- Structured output in NDJSON and CSV formats
- System metadata for reproducibility

**Conformance Levels:**

A **basic conformant implementation** MUST support:
- Core timing fields (release, deadline, start, end timestamps)
- Deadline miss tracking
- NDJSON output format

A **fully conformant implementation** MUST additionally support:
- Device timing fields for remote execution
- Error tracking (window failure and error codes)
- CSV output format
- System metadata recording

**Implementation Status:**

This specification documents both implemented and planned features. Energy and memory measurement fields are defined in the schema (§6.1.2) but are NOT REQUIRED in v1.0 implementations. Implementations MAY return zero or omit these fields until full instrumentation is available (planned v1.1, Spring 2026).

---

## 6.2 Record Schema

### 6.2.1 Core Telemetry Record

A conformant telemetry record MUST contain the following fields:

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| `run_id` | string | REQUIRED | Unique run identifier (millisecond timestamp) |
| `plugin_name` | string | REQUIRED | Kernel name (e.g., `bandpass_fir`, `car`) |
| `window_index` | uint32 | REQUIRED | Window sequence number (0-indexed) |
| `release_ts_ns` | uint64 | REQUIRED | Window release time (nanoseconds, monotonic clock) |
| `deadline_ts_ns` | uint64 | REQUIRED | Deadline timestamp (release + H/Fs, nanoseconds) |
| `start_ts_ns` | uint64 | REQUIRED | Actual execution start time (nanoseconds, monotonic clock) |
| `end_ts_ns` | uint64 | REQUIRED | Actual execution end time (nanoseconds, monotonic clock) |
| `deadline_missed` | uint8 | REQUIRED | 1 if end > deadline, 0 otherwise |
| `W` | uint32 | REQUIRED | Window length (samples) |
| `H` | uint32 | REQUIRED | Hop length (samples) |
| `C` | uint32 | REQUIRED | Input channel count |
| `Fs` | uint32 | REQUIRED | Sample rate (Hz) |
| `warmup` | uint8 | REQUIRED | 1 if warmup window (excluded from statistics), 0 otherwise |
| `repeat` | uint32 | REQUIRED | Repeat iteration number (1-indexed) |

**Rationale:**

The core schema captures the minimum information needed to compute latency distributions, deadline miss rates, and throughput. The `window_index` provides temporal ordering, while `warmup` enables statistical exclusion of cache-cold executions. The `repeat` field supports multi-trial averaging for statistical robustness.

**Normative Requirements:**

1. Implementations MUST populate all REQUIRED fields for every window.
2. Timestamp fields MUST use nanosecond precision (uint64).
3. The `run_id` MUST be unique across runs on the same system.
4. The `window_index` MUST increment sequentially starting from 0.

### 6.2.2 Device Timing Fields

For implementations supporting remote execution via device adapters, the following fields SHOULD be populated:

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| `device_tin_ns` | uint64 | SHOULD | Time adapter received window data (device clock) |
| `device_tstart_ns` | uint64 | SHOULD | Time kernel execution started (device clock) |
| `device_tend_ns` | uint64 | SHOULD | Time kernel execution finished (device clock) |
| `device_tfirst_tx_ns` | uint64 | SHOULD | Time first output byte transmitted (device clock) |
| `device_tlast_tx_ns` | uint64 | SHOULD | Time last output byte transmitted (device clock) |
| `adapter_name` | string | SHOULD | Adapter identifier (e.g., `native`, `jetson@tcp`) |

**Rationale:**

Device timing fields enable decomposition of end-to-end latency into:
- **Adapter overhead:** Time spent marshaling data and managing transport
- **Network latency:** Time spent in serialization and transmission
- **Kernel execution time:** Pure computational latency on the device

For local execution (native adapter), device timestamps approximate harness timestamps within socketpair overhead (~microseconds). For remote execution (TCP, UART), device timing reveals transport bottlenecks.

**Normative Requirements:**

1. Implementations using the `native` adapter SHOULD populate device timing fields.
2. Implementations using remote adapters (TCP, UART) MUST populate device timing fields.
3. Device timestamps MUST use the device's monotonic clock (not synchronized with harness clock).
4. The `adapter_name` field MUST match the adapter identifier in the configuration.

**Clock Synchronization:**

Device clocks and harness clocks are NOT synchronized. Device timing fields are measured relative to an arbitrary device monotonic reference. Interval durations (e.g., `device_tend_ns - device_tstart_ns`) are valid; absolute comparisons between device and harness timestamps are NOT valid.

### 6.2.3 Error Tracking Fields

For implementations supporting error detection and recovery, the following fields SHOULD be populated:

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| `window_failed` | uint8 | SHOULD | 1 if transport/adapter failure occurred, 0 otherwise |
| `error_code` | int32 | SHOULD | Error reason code (implementation-defined) |

**Rationale:**

Error tracking distinguishes transport failures (network timeout, serialization error) from deadline misses (computation too slow). This enables root cause analysis of benchmark anomalies.

**Normative Requirements:**

1. Implementations MUST set `window_failed = 1` if the window could not be processed due to adapter or transport failure.
2. Implementations MUST set `window_failed = 0` for successful windows, even if the deadline was missed.
3. The `error_code` field SHOULD use a documented error taxonomy (e.g., POSIX errno codes or adapter-specific error enumeration).

### 6.2.4 Planned Fields (Not Required in v1.0)

The following fields are defined in the schema but are NOT REQUIRED in v1.0 implementations. Implementations MAY omit these fields or return zero values.

| Field | Type | Planned Version | Description |
|-------|------|-----------------|-------------|
| `energy_j` | float | v1.1 (Spring 2026) | Energy consumption during kernel execution (joules) |
| `power_mw` | float | v1.1 (Spring 2026) | Average power consumption (milliwatts) |
| `rss_bytes` | uint64 | v1.1 (Spring 2026) | Resident set size at window completion (bytes) |
| `state_bytes` | uint64 | v1.1 (Spring 2026) | Kernel state memory allocation (bytes, runtime measurement) |
| `workspace_bytes` | uint64 | v1.1 (Spring 2026) | Kernel workspace memory allocation (bytes, runtime measurement) |

**Implementation Notes:**

- **Energy measurement:** Requires RAPL (Running Average Power Limit) instrumentation on Linux x86_64 platforms. Planned for v1.1.
- **Memory measurement:** Requires runtime RSS tracking and heap instrumentation. Current implementations report static metadata from `cortex_get_info()`, not actual allocations.

**Normative Requirements:**

1. Implementations claiming full telemetry conformance MUST provide energy and memory fields in v1.1+.
2. Implementations MAY omit unimplemented fields from output (NDJSON: omit key, CSV: empty cell).
3. Implementations MUST NOT emit misleading values (e.g., random data) for unimplemented fields. Zero or null MUST indicate unavailability.

---

## 6.3 Timestamp Semantics

### 6.3.1 Clock Source

Timestamp fields MUST use a monotonic clock source:

- **Linux:** `CLOCK_MONOTONIC` (nanosecond resolution, immune to NTP adjustments)
- **macOS:** `clock_gettime(CLOCK_MONOTONIC, ...)` (microsecond quantization on some systems)
- **Other POSIX platforms:** POSIX monotonic clock (`CLOCK_MONOTONIC` or equivalent)

**Rationale:**

Wall clock timestamps (`CLOCK_REALTIME`) are unsuitable for interval measurement because they are subject to:
- NTP adjustments (forward/backward jumps)
- Leap second corrections
- Manual time changes

Monotonic clocks provide strictly increasing timestamps, ensuring valid interval calculations.

**Normative Requirements:**

1. Implementations MUST use a monotonic clock for all timestamp fields.
2. Implementations MUST NOT use wall clock time for latency measurement.
3. Implementations SHOULD document the clock source and resolution in system metadata.

### 6.3.2 Timestamp Precision

All timestamp fields MUST use **nanosecond precision** (uint64, nanoseconds since an arbitrary monotonic reference).

**Rationale:**

BCI kernels execute in the 10µs–1ms range. Microsecond precision (1000ns quantization) provides only 10–100 samples per kernel execution, insufficient for percentile analysis. Nanosecond precision matches the resolution of modern timing APIs (`CLOCK_MONOTONIC`, `clock_gettime`).

**Normative Requirements:**

1. Timestamp fields MUST store values in nanoseconds (not milliseconds or microseconds).
2. Implementations MAY experience quantization depending on platform clock resolution (e.g., macOS quantizes to 1µs increments).
3. Implementations MUST NOT artificially inflate precision (e.g., multiplying microsecond timestamps by 1000 does not create nanosecond precision).

### 6.3.3 Timestamp Zero Point

The monotonic clock zero point is **arbitrary and platform-dependent**. Timestamps represent nanoseconds since an unspecified reference (e.g., system boot, arbitrary epoch).

**Normative Requirements:**

1. Implementations MUST NOT assume timestamps represent wall clock time.
2. Implementations MUST NOT compare absolute timestamps across runs or systems.
3. Interval durations (e.g., `end_ts_ns - start_ts_ns`) are valid; absolute timestamp values have no universal interpretation.

### 6.3.4 Deadline Calculation

The deadline timestamp SHALL be computed as:

```
deadline_ts_ns = release_ts_ns + (hop_samples / sample_rate_hz) × 1,000,000,000
```

Where:
- `hop_samples` (H): Hop length in samples
- `sample_rate_hz` (Fs): Sample rate in Hz
- Result: Deadline in nanoseconds (same clock domain as `release_ts_ns`)

**Example:**

Given:
- Hop (H) = 80 samples
- Sample rate (Fs) = 160 Hz
- Release time = 1,000,000,000 ns

Computation:
```
deadline_delta_s = 80 / 160 = 0.5 seconds
deadline_delta_ns = 0.5 × 1,000,000,000 = 500,000,000 ns
deadline_ts_ns = 1,000,000,000 + 500,000,000 = 1,500,000,000 ns
```

The deadline is 500ms after release (the next window arrives every H/Fs seconds).

**Rationale:**

In overlapping windowed processing, windows arrive every **hop** samples (H), not window samples (W). For a sample rate Fs, a new window arrives every H/Fs seconds. Processing must complete before the next window arrival, establishing the deadline.

**Why deadline uses hop, not window:**

For 50% overlapping windows (W=160, H=80, Fs=160 Hz):
- Window 0 arrives at t=0.0s (samples 0–159)
- Window 1 arrives at t=0.5s (samples 80–239, overlaps 80 samples with window 0)
- Window 2 arrives at t=1.0s (samples 160–319, overlaps 80 samples with window 1)

If window 0 processing finishes at t=0.6s, it has **missed the deadline** (window 1 already arrived at t=0.5s). The hop determines the inter-arrival interval, not the window length.

**Normative Requirements:**

1. Implementations MUST compute deadlines using the hop length (H), not window length (W).
2. Implementations MUST use floating-point division to avoid integer truncation: `(H / Fs)` computed as `(double)H / (double)Fs`.
3. Implementations MUST convert the deadline delta to nanoseconds (multiply by 10^9) before adding to the release timestamp.

### 6.3.5 Deadline Miss Detection

A deadline miss occurs when the execution end time exceeds the deadline:

```
deadline_missed = (end_ts_ns > deadline_ts_ns) ? 1 : 0
```

**Normative Requirements:**

1. Implementations MUST set `deadline_missed = 1` if `end_ts_ns > deadline_ts_ns`.
2. Implementations MUST set `deadline_missed = 0` otherwise.
3. Implementations MUST compare nanosecond timestamps directly (not converted to other units).

---

## 6.4 Output Formats

### 6.4.1 NDJSON Format (Default)

NDJSON (Newline-Delimited JSON) is the **default output format** for telemetry records.

**Specification:** https://github.com/ndjson/ndjson-spec

**Format Characteristics:**

1. Each line contains ONE complete JSON object (no outer array brackets).
2. Lines are separated by newline characters (`\n`, ASCII 0x0A).
3. Each object is a complete, self-describing telemetry record.
4. Files use the `.ndjson` extension.
5. Encoding is UTF-8.

**Example:**

```json
{"run_id":"1762310612183","plugin":"goertzel","window_index":0,"release_ts_ns":21194971498000,"deadline_ts_ns":21195471498000,"start_ts_ns":21194971498000,"end_ts_ns":21194971740000,"deadline_missed":0,"W":160,"H":80,"C":64,"Fs":160,"warmup":0,"repeat":1,"device_tin_ns":429226466336,"device_tstart_ns":429226466496,"device_tend_ns":429226817216,"device_tfirst_tx_ns":429226817312,"device_tlast_tx_ns":429226817312,"adapter_name":"native","window_failed":0,"error_code":0}
{"run_id":"1762310612183","plugin":"goertzel","window_index":1,"release_ts_ns":21195476495000,"deadline_ts_ns":21195976495000,"start_ts_ns":21195476495000,"end_ts_ns":21195476742000,"deadline_missed":0,"W":160,"H":80,"C":64,"Fs":160,"warmup":0,"repeat":1,"device_tin_ns":429226817500,"device_tstart_ns":429226817650,"device_tend_ns":429227168400,"device_tfirst_tx_ns":429227168500,"device_tlast_tx_ns":429227168500,"adapter_name":"native","window_failed":0,"error_code":0}
```

**Rationale:**

NDJSON provides significant advantages over JSON arrays or CSV for telemetry:

1. **Streaming:** Append-only writes without re-parsing the entire file. New records are appended as they arrive.
2. **Line-oriented processing:** Compatible with Unix tools (`grep`, `tail -f`, `awk`, `jq`). Each record is a complete line.
3. **Partial reads:** Incomplete runs (e.g., benchmark crashed mid-execution) are still parseable. No closing bracket required.
4. **Self-describing:** Schema is embedded in every record (field names present). No separate header required.
5. **Standard format:** Widely supported in log aggregation systems (Elasticsearch, Splunk, etc.).

**Normative Requirements:**

1. Implementations MUST support NDJSON output.
2. Each JSON object MUST occupy exactly one line (no embedded newlines in values).
3. Each line MUST contain a complete, valid JSON object.
4. Implementations MUST use UTF-8 encoding.
5. Implementations MUST use the `.ndjson` file extension.

**System Metadata:**

The first line of an NDJSON file SHOULD contain a system metadata record with `"_type": "system_info"`:

```json
{"_type":"system_info","os":"Darwin 23.2.0","cpu":"Apple M1","hostname":"Westons-MacBook-Air-2.local","cpu_count":8,"total_ram_mb":8192,"thermal_celsius":null,"device_hostname":"weston-desktop","device_cpu":"ARMv8 Processor rev 1 (v8l)","device_os":"Linux 5.15.148-tegra"}
```

**Normative Requirements:**

1. Implementations SHOULD emit a system metadata record as the first line.
2. The system metadata record MUST include the field `"_type": "system_info"` to distinguish it from telemetry records.
3. Parsing tools SHOULD skip records with `"_type"` ≠ null.

### 6.4.2 CSV Format (Alternative)

CSV (Comma-Separated Values) provides spreadsheet-compatible output for telemetry records.

**Format Characteristics:**

1. First line contains column names (header row).
2. Subsequent lines contain data rows (one record per line).
3. Delimiter is comma (`,`, ASCII 0x2C).
4. Files use the `.csv` extension.
5. Encoding is UTF-8.

**Example:**

```csv
run_id,plugin,window_index,release_ts_ns,deadline_ts_ns,start_ts_ns,end_ts_ns,deadline_missed,W,H,C,Fs,warmup,repeat,device_tin_ns,device_tstart_ns,device_tend_ns,device_tfirst_tx_ns,device_tlast_tx_ns,adapter_name,window_failed,error_code
1762310612183,goertzel,0,21194971498000,21195471498000,21194971498000,21194971740000,0,160,80,64,160,0,1,429226466336,429226466496,429226817216,429226817312,429226817312,native,0,0
1762310612183,goertzel,1,21195476495000,21195976495000,21195476495000,21195476742000,0,160,80,64,160,0,1,429226817500,429226817650,429227168400,429227168500,429227168500,native,0,0
```

**Normative Requirements:**

1. Implementations SHOULD support CSV output (REQUIRED for full conformance).
2. The first line MUST contain column names matching the field names in §6.2.
3. Implementations MUST use comma (`,`) as the delimiter.
4. Implementations MUST use UTF-8 encoding.
5. Implementations MUST use the `.csv` file extension.

**System Metadata:**

System metadata SHOULD be included as comment lines (lines beginning with `#`) before the header row:

```csv
# System Information
# OS: Darwin 23.2.0
# CPU: Apple M1
# Hostname: Westons-MacBook-Air-2.local
# CPU Cores: 8
# Total RAM: 8192 MB
# Thermal: unavailable
#
run_id,plugin,window_index,...
```

**Normative Requirements:**

1. Implementations SHOULD emit system metadata as comment lines (lines prefixed with `#`).
2. Comment lines MUST appear before the header row.
3. Parsing tools SHOULD ignore lines beginning with `#`.

### 6.4.3 Format Selection

The output format is determined by the `output.format` configuration setting.

**Configuration Example (YAML):**

```yaml
output:
  format: "ndjson"  # or "csv"
```

**Normative Requirements:**

1. Implementations MUST support `output.format = "ndjson"` (default).
2. Implementations SHOULD support `output.format = "csv"` (REQUIRED for full conformance).
3. If `output.format` is unspecified, implementations MUST default to NDJSON.

### 6.4.4 Field Ordering

**NDJSON:** Field order within JSON objects is NOT significant. Parsers MUST NOT assume a specific field order.

**CSV:** Column order MUST match the order specified in §6.2. Implementations MAY omit columns for unimplemented fields, but MUST document the omission.

---

## 6.5 Derived Metrics

Implementations MAY compute derived metrics from raw telemetry fields. Derived metrics are NOT part of the telemetry record schema but are commonly reported in analysis summaries.

### 6.5.1 Latency

Latency is the duration from execution start to execution end:

```
latency_ns = end_ts_ns - start_ts_ns
```

**Normative Requirements:**

1. Implementations SHOULD report latency in microseconds (µs) or nanoseconds (ns) in analysis summaries.
2. Latency MUST be computed from `start_ts_ns` and `end_ts_ns` (not device timing fields unless explicitly stated).

### 6.5.2 Jitter

Jitter quantifies latency variability. Common jitter metrics include:

- **P95-P50 jitter:** Difference between 95th percentile and median latency (captures tail latency variability)
- **P99-P50 jitter:** Difference between 99th percentile and median latency (captures extreme tail variability)

```
jitter_p95_minus_p50 = P95(latency_ns) - P50(latency_ns)
jitter_p99_minus_p50 = P99(latency_ns) - P50(latency_ns)
```

**Normative Requirements:**

1. Implementations SHOULD compute jitter as percentile differences (not standard deviation).
2. Jitter MUST be computed per kernel per run (not per window).

### 6.5.3 Throughput

Throughput is the number of windows processed per second:

```
throughput_windows_per_s = window_count / total_time_s
```

Where `total_time_s` is the elapsed time from the first window release to the last window completion.

**Normative Requirements:**

1. Implementations SHOULD report throughput in windows per second (Hz).
2. Throughput MUST exclude warmup windows from the count.

### 6.5.4 Deadline Miss Rate

Deadline miss rate is the fraction of windows that missed their deadlines:

```
deadline_miss_rate = (count of deadline_missed=1) / (total windows)
```

**Normative Requirements:**

1. Implementations SHOULD report deadline miss rate as a percentage (0–100%).
2. Deadline miss rate MUST exclude warmup windows from the count.

---

## 6.6 File Locations

Telemetry files SHOULD be written to the following locations:

```
results/<run-name>/kernel-data/<kernel>/telemetry.ndjson   # Per-kernel NDJSON telemetry
results/<run-name>/kernel-data/<kernel>/telemetry.csv      # Per-kernel CSV telemetry (if enabled)
results/<run-name>/telemetry.ndjson                        # Aggregated NDJSON telemetry (all kernels)
```

**Normative Requirements:**

1. Implementations MUST create the directory structure if it does not exist.
2. Implementations MUST write per-kernel telemetry files for each kernel in the benchmark.
3. Implementations MAY write aggregated telemetry files combining all kernels.

---

## 6.7 Conformance

### 6.7.1 Basic Conformance

A **basic conformant implementation** MUST:

1. Populate all REQUIRED fields from §6.2.1.
2. Use a monotonic clock source (§6.3.1).
3. Use nanosecond precision for timestamps (§6.3.2).
4. Compute deadlines correctly using hop length (§6.3.4).
5. Support NDJSON output format (§6.4.1).

### 6.7.2 Full Conformance

A **fully conformant implementation** MUST additionally:

1. Populate device timing fields when using remote adapters (§6.2.2).
2. Populate error tracking fields (§6.2.3).
3. Support CSV output format (§6.4.2).
4. Emit system metadata (§6.4.1, §6.4.2).

### 6.7.3 Extended Conformance (v1.1+)

An **extended conformant implementation** MUST additionally:

1. Populate energy measurement fields (§6.2.4).
2. Populate runtime memory measurement fields (§6.2.4).

---

## 6.8 Rationale Summary

This section concludes with a summary of key design decisions:

**Why NDJSON as the default format?**

NDJSON provides streaming append-only writes, line-oriented processing (Unix tools), partial read support (crashed runs), and self-describing schema. CSV is provided for spreadsheet compatibility, but NDJSON is superior for programmatic analysis and log aggregation.

**Why nanosecond precision?**

BCI kernels execute in 10µs–1ms. Microsecond precision (1000ns quantization) provides only 10–100 samples per execution, insufficient for percentile analysis. Nanosecond precision matches modern timing API resolution.

**Why CLOCK_MONOTONIC (not wall clock)?**

Wall clocks are subject to NTP adjustments, leap seconds, and manual changes, causing backwards jumps. Monotonic clocks are strictly increasing and immune to external time changes, ensuring valid interval measurements.

**Why deadline = release + H/Fs (not release + W/Fs)?**

In overlapping windowed processing, windows arrive every **hop** samples (H), not window samples (W). The deadline is the next window's arrival time, determined by the hop interval H/Fs.

**Why separate device timing fields?**

Device timing enables decomposition of end-to-end latency into adapter overhead, network latency, and kernel execution time. For remote execution (Jetson via TCP, STM32 via UART), this is critical for identifying transport bottlenecks.

---

**End of Section 6: Telemetry Format**

---

# Document Metadata

**Document Title:** CORTEX System Specification v1.0 - Part II: Core Specifications  
**Version:** 1.0  
**Status:** Draft for Review (Batch 1)  
**Last Updated:** 2026-02-01  

**Contents:**
- Section 3: Plugin ABI Specification (~3,000 words)
- Section 4: Wire Protocol Specification (~3,400 words)
- Section 5: Configuration Schema (~7,800 words)
- Section 6: Telemetry Format (~7,800 words)

**Total Word Count:** ~22,000 words

**Generated By:** Parallel agent-based specification writing (4 agents, Haiku model)

---

**End of Part II: Core Specifications**
