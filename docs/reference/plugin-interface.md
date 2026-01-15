# Plugin Interface (C ABI v3)

**ABI Version**: 3
**Last Updated**: 2025-12-27

This document describes the **CORTEX kernel plugin interface** (ABI v3) and how run-time configuration is passed from the harness to each plugin. It is intended for developers implementing kernels such as **Common Average Reference (CAR)**, **ICA (Independent Component Analysis)**, **Notch IIR filters**, **FIR band-pass filters**, **Goertzel bandpower**, and future extensions.

The goal is to standardize how kernels plug into the harness so that timing, memory, and energy can be measured fairly across implementations.

**New in v3**: Calibration support for trainable kernels (ICA, CSP).

---

## Table of Contents

1. [Design Principles](#design-principles)
2. [System Context](#system-context)
3. [Data Types](#data-types)
4. [Function Contracts](#function-contracts)
5. [Calibration Workflow (v3)](#calibration-workflow-v3)
6. [Guidelines for Plugin Authors](#guidelines-for-plugin-authors)
7. [Platform-Specific Development](#platform-specific-development)
8. [Version History & Migration](#version-history--migration)

---

## Design Principles

The ABI is designed with these properties:

- **Simple & deterministic**
  A kernel exposes 3-4 functions: `init()`, `process()`, `teardown()`, and optionally `calibrate()` (v3+).
  No allocations or blocking calls are allowed inside `process()`.
  All state must be allocated in `init()` and released in `teardown()`.

- **Forward compatibility**
  The first two fields of the config struct contain an **ABI version** and **struct size**.
  New fields can be appended without breaking existing plugins.
  Plugins should ignore unknown trailing bytes if `struct_size` is honored.

- **Modality agnostic**
  While current kernel implementations target EEG parameters (Fs=160 Hz, W=160 samples, H=80, C=64), the ABI supports arbitrary sample rates, window sizes, and channel counts.
  Plugins never see YAML or file paths — only numeric runtime parameters.

- **Quantization aware**
  Plugins advertise which numeric formats they support (`float32` today, `Q15` and `Q7` in future).
  The harness requests a specific dtype via the config struct.
  Plugins must reject unsupported types.

- **Calibration support (v3)**
  Trainable kernels can export `cortex_calibrate()` for offline batch training.
  Calibration state is serialized to `.cortex_state` files and passed to `cortex_init()`.

---

## System Context

CORTEX plugins are dynamically loaded by device adapters and process windowed EEG data. Each plugin implements 3-4 functions and receives runtime configuration through structs—never YAML or file paths. The harness (via device adapters) handles all dataset streaming, scheduling, deadline enforcement, and telemetry collection.

**Plugin Lifecycle**:
```
Optional: cortex_calibrate(batch_data) → calibration_state → save to .cortex_state file
          ↓
          cortex_init(config + calibration_state) → handle
          ↓
          cortex_process(handle, window) → output  [repeated N times]
          ↓
          cortex_teardown(handle)
```

For details on how the harness, replayer, scheduler, and analysis pipeline interact, see [Architecture Overview](../architecture/overview.md).

---

## Data Types

### Numeric Data Types

```c
typedef enum {
    CORTEX_DTYPE_FLOAT32 = 1u << 0,  /* 32-bit IEEE 754 floating point */
    CORTEX_DTYPE_Q15     = 1u << 1,  /* 16-bit fixed-point (signed Q1.15) */
    CORTEX_DTYPE_Q7      = 1u << 2   /* 8-bit fixed-point (signed Q0.7) */
} cortex_dtype_bitmask_t;
```

### Capability Flags (v3+)

```c
typedef enum {
    CORTEX_CAP_OFFLINE_CALIB  = 1u << 0,  /* Supports cortex_calibrate() */
    CORTEX_CAP_ONLINE_ADAPT   = 1u << 1,  /* Reserved for v4 */
    CORTEX_CAP_FEEDBACK_LEARN = 1u << 2,  /* Reserved for v5 */
} cortex_capability_flags_t;
```

Kernels advertise capabilities via `cortex_init_result_t.capabilities`.
Harness uses these flags to determine which optional functions exist.

### Plugin Configuration

```c
typedef struct {
    /* ========== ABI Handshake ========== */
    uint32_t abi_version;            /* Must be CORTEX_ABI_VERSION (3) */
    uint32_t struct_size;            /* sizeof(cortex_plugin_config_t) */

    /* ========== Runtime Configuration ========== */
    uint32_t sample_rate_hz;         /* Fs: samples per second (e.g., 160 Hz) */
    uint32_t window_length_samples;  /* W: samples per window (e.g., 160) */
    uint32_t hop_samples;            /* H: samples to advance (e.g., 80) */
    uint32_t channels;               /* C: input channels (e.g., 64) */
    uint32_t dtype;                  /* One of cortex_dtype_bitmask_t */
    uint8_t  allow_in_place;         /* Non-zero: process() may overwrite input */
    uint8_t  reserved0[3];           /* Reserved for alignment */

    /* ========== Kernel Parameters ========== */
    const void *kernel_params;       /* String: "param1: val1, param2: val2, ..." */
    uint32_t   kernel_params_size;   /* Size of parameters string */

    /* ========== Calibration State (v3+) ========== */
    const void *calibration_state;   /* Pre-trained state (e.g., ICA W matrix) */
    uint32_t calibration_state_size; /* Size in bytes */
} cortex_plugin_config_t;
```

**Size**: 64 bytes (v3), 48 bytes (v2) on 64-bit systems (pointer size affects calibration_state pointer field)

#### YAML → Struct Mapping

- `dataset.sample_rate_hz` → `sample_rate_hz`
- `plugins[*].runtime.window_length_samples` → `window_length_samples`
- `plugins[*].runtime.hop_samples` → `hop_samples`
- `plugins[*].runtime.channels` → `channels`
- `plugins[*].runtime.dtype` → `dtype`
- `plugins[*].runtime.allow_in_place` → `allow_in_place`
- `plugins[*].params` → serialized string passed to `kernel_params`
- `plugins[*].calibration_state` (v3) → loaded file passed to `calibration_state`

#### Extracting Runtime Parameters

Kernels use the **parameter accessor API** to extract runtime configuration:

```c
#include "cortex_plugin.h"
#include "accessor.h"  // Parameter accessor functions

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // Extract parameters with typed accessors and defaults
    const char *params = (const char *)config->kernel_params;

    double f0_hz = cortex_param_float(params, "f0_hz", 60.0);        // default: 60.0
    int order = cortex_param_int(params, "order", 4);                 // default: 4
    bool normalize = cortex_param_bool(params, "normalize", true);   // default: true

    char window[32];
    cortex_param_string(params, "window", window, sizeof(window), "hann");  // default: "hann"

    // Validate extracted parameters
    if (f0_hz <= 0.0 || f0_hz >= config->sample_rate_hz / 2.0) {
        fprintf(stderr, "[kernel] error: f0_hz must be in (0, Nyquist)\n");
        return (cortex_init_result_t){0};  // NULL handle
    }

    // ... use parameters ...
}
```

**Accessor Functions** (defined in `sdk/kernel/include/cortex_params.h`):
- `double cortex_param_float(const char *params, const char *key, double default_val)`
- `int64_t cortex_param_int(const char *params, const char *key, int64_t default_val)`
- `void cortex_param_string(const char *params, const char *key, char *out_buf, size_t buf_size, const char *default_val)`
- `bool cortex_param_bool(const char *params, const char *key, bool default_val)`

**Supported Formats**: YAML-style (`"f0_hz: 60.0, Q: 30.0"`) or URL-style (`"f0_hz=60.0&Q=30.0"`)

See `sdk/kernel/lib/params/README.md` for complete API documentation.

### Init Result

```c
typedef struct {
    void *handle;                         /* Opaque instance handle (NULL on error) */
    uint32_t output_window_length_samples; /* Actual output W */
    uint32_t output_channels;             /* Actual output C */
    uint32_t capabilities;                /* Bitmask of cortex_capability_flags_t (v3+) */
} cortex_init_result_t;
```

**Size**: 24 bytes (v3), 16 bytes (v2) on 64-bit systems (void* handle is 8 bytes + padding)

### Calibration Result (v3+)

```c
typedef struct {
    void *calibration_state;       /* Opaque trained state (NULL on error) */
    uint32_t state_size_bytes;     /* Size for serialization */
    uint32_t state_version;        /* Kernel-specific state version */
} cortex_calibration_result_t;
```

---

## Function Contracts

### `cortex_calibrate()` (Optional, v3+)

```c
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
);
```

**Purpose**: Offline batch training for trainable kernels (ICA, CSP).

**Parameters**:
- `config`: Same as `cortex_init()` (channels, sample_rate, etc.)
- `calibration_data`: Pointer to `(num_windows × W × C)` float32 array
- `num_windows`: Number of windows in calibration data

**Returns**:
- `{state, size, version}` on success
- `{NULL, 0, 0}` on failure

**Constraints**:
- MAY allocate memory (one-time operation)
- MAY perform expensive computation (iterative convergence)
- MUST be deterministic (same input → same output)
- MUST handle NaN inputs gracefully

**Detection**: Harness detects this function via `dlsym()` at runtime. If not exported, kernel is assumed stateless or requires pre-calibrated state.

**Example**:
```c
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
) {
    // Train ICA on batch data
    float *W = train_ica(calibration_data, num_windows, config->channels);

    if (!W) {
        fprintf(stderr, "[ica] ERROR: Calibration failed\n");
        return (cortex_calibration_result_t){0};
    }

    return (cortex_calibration_result_t){
        .calibration_state = W,
        .state_size_bytes = config->channels * config->channels * sizeof(float),
        .state_version = 1  // ICA state format v1
    };
}
```

---

### `cortex_init()`

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
```

**Purpose**: Initialize a plugin instance.

**Parameters**:
- `config`: Configuration structure populated by harness

**Returns**:
- `cortex_init_result_t` containing handle, output dimensions, and capabilities
- `handle` is NULL on error

**Constraints**:
- MUST validate `abi_version` matches `CORTEX_ABI_VERSION`
- MUST validate `struct_size` ≥ `sizeof(cortex_plugin_config_t)`
- MUST allocate all persistent state
- MUST NOT allocate temporary/scratch buffers (use `alloca()` in `process()`)
- MUST handle unsupported dtypes by returning NULL

**v3 Changes**: Now accepts optional `calibration_state` via config.

**Example (v2 kernel)**:
```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // Validate ABI (accept v2 or v3)
    if (config->abi_version < 2 || config->abi_version > 3) {
        return (cortex_init_result_t){0};
    }

    // Validate dtype
    if (config->dtype != CORTEX_DTYPE_FLOAT32) {
        return (cortex_init_result_t){0};
    }

    // Allocate state
    car_state_t *state = calloc(1, sizeof(car_state_t));
    if (!state) return (cortex_init_result_t){0};

    state->channels = config->channels;
    state->window_length = config->window_length_samples;

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = config->window_length_samples,
        .output_channels = config->channels,
        .capabilities = 0  // No special capabilities
    };
}
```

**Example (v3 trainable kernel)**:
```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    if (config->abi_version != 3) {
        return (cortex_init_result_t){0};
    }

    ica_state_t *state = calloc(1, sizeof(ica_state_t));
    if (!state) return (cortex_init_result_t){0};

    // Load calibration state if provided
    if (config->calibration_state != NULL) {
        state->W_matrix = malloc(config->calibration_state_size);
        memcpy(state->W_matrix, config->calibration_state, config->calibration_state_size);
    } else {
        fprintf(stderr, "[ica] ERROR: Calibration state required\n");
        fprintf(stderr, "[ica] Run: cortex calibrate --kernel ica@f32 --dataset <path>\n");
        free(state);
        return (cortex_init_result_t){0};
    }

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = config->window_length_samples,
        .output_channels = config->channels,
        .capabilities = CORTEX_CAP_OFFLINE_CALIB
    };
}
```

---

### `cortex_process()`

```c
void cortex_process(void *handle, const void *input, void *output);
```

**Purpose**: Process one window of data.

**Parameters**:
- `handle`: Opaque instance pointer from `cortex_init()`
- `input`: Pointer to input buffer (`W × C` samples)
- `output`: Pointer to output buffer (size from `cortex_init()`)

**Constraints** (CRITICAL for benchmarking):
- MUST NOT allocate heap memory (use `alloca()` for scratch buffers)
- MUST NOT perform I/O or blocking syscalls
- MUST NOT take excessive locks
- MUST handle NaN inputs gracefully
- MAY overwrite input if `allow_in_place=1`

**Buffer Layout**: Row-major, tightly packed (`channels × samples`)

**Example**:
```c
void cortex_process(void *handle, const void *input, void *output) {
    const car_state_t *state = (const car_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    // Process each timepoint
    for (uint32_t t = 0; t < state->window_length; t++) {
        // Compute mean across channels (excluding NaNs)
        double sum = 0.0;
        int count = 0;

        for (uint32_t c = 0; c < state->channels; c++) {
            float v = in[t * state->channels + c];
            if (v == v) { sum += v; ++count; }  // v == v checks for NaN
        }

        float mean = (count > 0) ? (float)(sum / count) : 0.0f;

        // Subtract mean
        for (uint32_t c = 0; c < state->channels; c++) {
            float v = in[t * state->channels + c];
            out[t * state->channels + c] = (v == v) ? (v - mean) : 0.0f;
        }
    }
}
```

---

### `cortex_teardown()`

```c
void cortex_teardown(void *handle);
```

**Purpose**: Free all resources associated with a plugin instance.

**Parameters**:
- `handle`: Opaque instance pointer from `cortex_init()`

**Constraints**:
- MUST free all memory allocated in `cortex_init()`
- MUST be safe to call with NULL handle
- SHOULD be idempotent

**Example**:
```c
void cortex_teardown(void *handle) {
    if (!handle) return;

    car_state_t *state = (car_state_t *)handle;
    free(state);
}
```

---

## Calibration Workflow (v3)

### Overview

Trainable kernels (ICA, CSP) require a **two-phase workflow**:

1. **Calibration Phase** (offline, expensive): Learn parameters from batch data
2. **Inference Phase** (online, cheap): Apply learned parameters per-window

### Workflow Steps

**1. Calibrate kernel**:
```bash
cortex calibrate \
    --kernel ica@f32 \
    --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
    --output primitives/datasets/v1/physionet-motor-imagery/calibration_states/ica_fastica.cortex_state \
    --params "method: fastica, n_components: 64"
```

**2. Configure run with calibration state**:
```yaml
# primitives/configs/cortex.yaml
plugins:
  - name: "ica"
    spec_uri: "primitives/kernels/v1/ica@f32"
    calibration_state: "primitives/datasets/v1/physionet-motor-imagery/calibration_states/ica_fastica.cortex_state"
```

**3. Run benchmark**:
```bash
cortex run primitives/configs/cortex.yaml
```

### State File Format

Calibration state is saved as `.cortex_state` files with binary format:

```
Offset | Size | Field               | Value
-------|------|---------------------|----------
0x00   | 4    | magic               | 0x434F5254 ("CORT")
0x04   | 4    | abi_version         | 3
0x08   | 4    | state_version       | Kernel-specific (e.g., 1 for ICA v1)
0x0C   | 4    | data_size           | Size of following data (bytes)
0x10   | N    | calibration_data    | Kernel-specific (e.g., W matrix for ICA)
```

**Storage Location**: `primitives/datasets/v{version}/{dataset}/calibration_states/{kernel}_{method}.cortex_state`

### Kernel Types

| Kernel Type | `cortex_calibrate()` | `calibration_state` Required? | Examples |
|-------------|----------------------|-------------------------------|----------|
| Stateless | Not exported | No | CAR, bandpass_fir, noop |
| Stateful (filters) | Not exported | No | notch_iir (filter history), Welch PSD (FFT config) |
| Trainable | Exported | Yes | ICA, CSP |

---

## Guidelines for Plugin Authors

### General

- **Language & linkage**: Implement in C or C++, export with `extern "C"`
- **ABI version**: Check `config->abi_version` in `init()`, reject mismatches
- **Numerical stability**: Follow tolerances in kernel's `spec.yaml`
- **State management**: Allocate all state in `init()`, free in `teardown()`
- **Thread safety**: No concurrent calls to `process()` on same handle
- **Error handling**: Return NULL from `init()` if initialization fails
- **NaN handling**: Treat NaN inputs gracefully (usually as 0.0)

### Memory Management

- **init()**: MAY allocate heap memory
- **process()**: MUST NOT allocate heap memory (use `alloca()` for scratch)
- **teardown()**: MUST free all allocated memory
- **calibrate()**: MAY allocate heap memory (one-time operation)

### Backward Compatibility

**v2 kernels with v3 harness**:
```c
// v2 kernel accepts both v2 and v3
if (config->abi_version < 2 || config->abi_version > 3) {
    return (cortex_init_result_t){0};
}

// v2 kernel ignores v3 fields (safe via struct_size)
// ... normal initialization ...

// MUST set capabilities field (new in v3)
return (cortex_init_result_t){
    .handle = state,
    .output_window_length_samples = W,
    .output_channels = C,
    .capabilities = 0  // No special capabilities
};
```

---

## Platform-Specific Development

### Library Extensions

Plugins must be built with the correct extension for each platform:

- **macOS**: `lib<name>.dylib`
- **Linux**: `lib<name>.so`

Device adapters automatically detect the platform and search for the appropriate extension.

### Build Flags

**macOS**:
```makefile
$(CC) $(CFLAGS) -dynamiclib -o libmyplugin.dylib myplugin.c
```

**Linux**:
```makefile
$(CC) $(CFLAGS) -shared -fPIC -o libmyplugin.so myplugin.c
```

### Cross-Platform Makefile

```makefile
CC = cc
CFLAGS = -Wall -Wextra -O2 -g -fPIC -I../../../../sdk/kernel/include

# Platform detection
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SOFLAG = -dynamiclib
    LIBEXT = .dylib
else
    SOFLAG = -shared
    LIBEXT = .so
endif

# Build plugin
libmyplugin$(LIBEXT): myplugin.c
	$(CC) $(CFLAGS) $(SOFLAG) -o $@ $< -lm
```

### Loading Behavior

Device adapters use `dlopen()` to load plugins:

- Searches for `.dylib` (macOS) or `.so` (Linux) automatically
- Platform-independent ABI (same `cortex_plugin.h` on all platforms)
- No code changes needed in plugin for different platforms

---

## Version History & Migration

### ABI v3 (Current)

**Changes from v2**:
- Added `cortex_calibrate()` function (optional)
- Extended `cortex_plugin_config_t` with `calibration_state` fields (+8 bytes)
- Extended `cortex_init_result_t` with `capabilities` field (+4 bytes)
- Added `cortex_calibration_result_t` type
- Added `cortex_capability_flags_t` enum

**Migration**: See [docs/guides/migrating-to-abi-v3.md](../guides/migrating-to-abi-v3.md)

### ABI v2

**Changes from v1**:
- Removed `cortex_get_info()` function
- Changed `cortex_init()` to return `cortex_init_result_t` instead of `void*`
- Unified shape query with initialization

### ABI v1

- Initial ABI with `cortex_get_info()`, `cortex_init()`, `cortex_process()`, `cortex_teardown()`

**Full history**: See [docs/architecture/abi_evolution.md](../architecture/abi_evolution.md)

---

## Default EEG Parameters

Current kernel implementations use:

- **Sample rate (Fs)**: 160 Hz
- **Window length (W)**: 160 samples (1 s)
- **Hop (H)**: 80 samples (50% overlap)
- **Channels (C)**: 64
- **Deadline**: H/Fs = 0.5 s

---

## References

- **ABI Header**: `sdk/kernel/include/cortex_plugin.h`
- **Parameter API**: `sdk/kernel/lib/params/README.md`
- **Architecture**: `docs/architecture/overview.md`
- **Platform Compatibility**: `docs/architecture/platform-compatibility.md`
- **ABI Evolution**: `docs/architecture/abi_evolution.md`
- **Migration Guide**: `docs/guides/migrating-to-abi-v3.md`

---

**Document Version**: 3.0.0
**Last Updated**: 2025-12-27
**Status**: Current
