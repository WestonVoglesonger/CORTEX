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
