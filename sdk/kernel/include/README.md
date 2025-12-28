# CORTEX SDK API Reference

Complete reference for all public SDK headers.

## Headers Overview

| Header | Purpose | Required | Use Case |
|--------|---------|----------|----------|
| [`cortex_plugin.h`](#cortex_pluginh) | Plugin ABI v3 specification | ✅ Yes | All kernels |
| [`cortex_params.h`](#cortex_paramsh) | Runtime parameter parsing | Optional | Kernels with configurable parameters |
| [`cortex_state_io.h`](#cortex_state_ioh) | Calibration state serialization | Optional | Trainable kernels (ICA, CSP, LDA) |
| [`cortex_loader.h`](#cortex_loaderh) | Plugin loader utilities | No | Harness-only (not for kernels) |

## cortex_plugin.h

Core plugin ABI v3 specification. **All kernels must include this header.**

### Data Types

#### `cortex_plugin_config_t`

Runtime configuration passed to `cortex_init()`.

```c
typedef struct {
    uint32_t abi_version;                    // Always check: must be 3
    uint32_t struct_size;                    // Size of this struct
    uint32_t sample_rate_hz;                 // Fs (e.g., 160 Hz)
    uint32_t window_length_samples;          // W (e.g., 160 samples)
    uint32_t channels;                       // C (e.g., 64 channels)
    uint32_t dtype;                          // CORTEX_DTYPE_FLOAT32
    const char *kernel_params;               // Optional runtime parameters (YAML/URL)
    const char *calibration_state;           // Path to .cortex_state file (trainable kernels)
    uint32_t calibration_state_size;         // Size of calibration state
} cortex_plugin_config_t;
```

**Fields:**
- `abi_version`: **Must validate** in `cortex_init()`: `if (config->abi_version != 3) return result;`
- `struct_size`: Forward compatibility check
- `sample_rate_hz`, `window_length_samples`, `channels`: Signal dimensions
- `dtype`: Always `CORTEX_DTYPE_FLOAT32` (v1 kernels)
- `kernel_params`: Optional runtime parameters (parse with `cortex_param_*()`)
- `calibration_state`: Path to `.cortex_state` file (trainable kernels only, NULL for others)

#### `cortex_init_result_t`

Return value from `cortex_init()`.

```c
typedef struct {
    void *handle;                            // Opaque state pointer (returned to process/teardown)
    uint32_t output_window_length_samples;   // Output W (usually == input W)
    uint32_t output_channels;                // Output C (usually == input C)
    uint32_t capabilities;                   // Capability flags (v3+)
} cortex_init_result_t;
```

**Usage:**
```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};  // Zero-initialize!

    my_state_t *state = calloc(1, sizeof(my_state_t));
    // ... initialize state ...

    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;  // Usually same as input
    result.output_channels = config->channels;  // Usually same as input
    result.capabilities = 0;  // Or CORTEX_CAP_OFFLINE_CALIB for trainable kernels

    return result;
}
```

#### `cortex_calibration_result_t`

Return value from `cortex_calibrate()` (ABI v3 trainable kernels only).

```c
typedef struct {
    int success;  // 1 = success, 0 = failure
} cortex_calibration_result_t;
```

### Enums

#### Data Types

```c
typedef enum {
    CORTEX_DTYPE_FLOAT32 = 0,  // 32-bit IEEE 754 float (default for v1 kernels)
    CORTEX_DTYPE_FLOAT64 = 1,  // 64-bit IEEE 754 double (future)
    CORTEX_DTYPE_INT16   = 2,  // 16-bit signed integer (future)
    CORTEX_DTYPE_INT32   = 3,  // 32-bit signed integer (future)
} cortex_dtype_t;
```

**v1 kernels:** Only `CORTEX_DTYPE_FLOAT32` supported.

#### Capability Flags

```c
typedef enum {
    CORTEX_CAP_OFFLINE_CALIB  = 1u << 0,  // Supports cortex_calibrate() (ABI v3)
    CORTEX_CAP_ONLINE_ADAPT   = 1u << 1,  // Reserved for v4
    CORTEX_CAP_FEEDBACK_LEARN = 1u << 2,  // Reserved for v5
} cortex_capabilities_t;
```

**Usage:**
```c
// v2 kernel (stateless/stateful, no calibration)
result.capabilities = 0;

// v3 trainable kernel (ICA, CSP, LDA)
result.capabilities = CORTEX_CAP_OFFLINE_CALIB;
```

### Required Functions

#### cortex_init()

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
```

**Purpose:** Initialize kernel state.

**When called:** Once per benchmark run, before any `cortex_process()` calls.

**Constraints:**
- ✅ Heap allocation allowed
- ✅ Can read files (e.g., calibration state)
- ❌ No blocking I/O
- ❌ No network calls

**Template:**
```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    // 1. Validate ABI version
    if (!config || config->abi_version != 3) {
        return result;  // {NULL, 0, 0, 0}
    }

    // 2. Validate dtype
    if (config->dtype != CORTEX_DTYPE_FLOAT32) {
        return result;
    }

    // 3. Allocate state
    my_state_t *state = calloc(1, sizeof(my_state_t));
    if (!state) return result;

    // 4. Parse runtime parameters (optional)
    const char *params = (const char *)config->kernel_params;
    double f0 = cortex_param_float(params, "f0_hz", 60.0);

    // 5. Load calibration state (trainable kernels only)
    if (config->calibration_state) {
        void *cal_state;
        uint32_t size, version;
        cortex_state_load(config->calibration_state, &cal_state, &size, &version);
        state->weights = cal_state;
    }

    // 6. Store config
    state->channels = config->channels;
    state->window_length = config->window_length_samples;

    // 7. Return result
    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;
    result.capabilities = 0;  // or CORTEX_CAP_OFFLINE_CALIB

    return result;
}
```

#### cortex_process()

```c
void cortex_process(void *handle, const void *input, void *output);
```

**Purpose:** Process one window of data (W samples × C channels).

**When called:** Repeatedly during benchmark (millions of times).

**Constraints (CRITICAL):**
- ❌ **NO heap allocation** (malloc/calloc/realloc)
- ❌ **NO file I/O**
- ❌ **NO network calls**
- ❌ **NO blocking syscalls**
- ✅ Stack allocation allowed (alloca, VLA, local arrays)
- ✅ Read/write to `handle` state allowed

**Data Layout:**
- Input: `float input[W][C]` (row-major: sample0_ch0, sample0_ch1, ..., sample1_ch0, ...)
- Output: `float output[W][C]` (same layout)

**Template:**
```c
void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    my_state_t *s = (my_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    // Process each sample
    for (uint32_t t = 0; t < s->window_length; t++) {
        for (uint32_t c = 0; c < s->channels; c++) {
            uint32_t idx = t * s->channels + c;

            // Handle NaN inputs
            float x = in[idx];
            if (x != x) x = 0.0f;  // isnan() check

            // Apply algorithm
            out[idx] = process_sample(x, s);
        }
    }
}
```

#### cortex_teardown()

```c
void cortex_teardown(void *handle);
```

**Purpose:** Free kernel state.

**When called:** Once per benchmark run, after all `cortex_process()` calls.

**Template:**
```c
void cortex_teardown(void *handle) {
    if (!handle) return;

    my_state_t *s = (my_state_t *)handle;

    // Free nested allocations first
    free(s->weights);
    free(s->buffer);

    // Free state struct last
    free(s);
}
```

### Optional Functions (ABI v3)

#### cortex_calibrate()

```c
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
);
```

**Purpose:** Train kernel on batch data (offline, once before runtime).

**When called:** Via `cortex calibrate` command, NOT during benchmarking.

**Constraints:**
- ✅ Heap allocation allowed
- ✅ Iterative algorithms allowed
- ✅ File I/O allowed (to save state)
- ❌ No network calls

**Data Layout:**
- `calibration_data`: `float data[num_windows][W][C]` (row-major)

**Template:**
```c
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
) {
    cortex_calibration_result_t result = {0};

    const float *data = (const float *)calibration_data;
    uint32_t W = config->window_length_samples;
    uint32_t C = config->channels;

    // 1. Train model
    float *weights = train_model(data, num_windows, W, C);
    if (!weights) return result;

    // 2. Serialize state
    uint32_t state_size = C * C * sizeof(float);
    cortex_state_save("model.cortex_state", weights, state_size, 1);

    // 3. Cleanup
    free(weights);

    result.success = 1;
    return result;
}
```

---

## cortex_params.h

Type-safe runtime parameter parsing. Optional, but recommended for configurable kernels.

### Functions

#### cortex_param_float()

```c
double cortex_param_float(const char *params, const char *key, double default_val);
```

**Purpose:** Extract float parameter from YAML or URL-style string.

**Example:**
```c
// YAML style: "f0_hz: 60.0\nQ: 30.0"
// URL style: "f0_hz=60.0&Q=30.0"
const char *params = config->kernel_params;
double f0 = cortex_param_float(params, "f0_hz", 60.0);  // Returns 60.0 if found, else default
```

#### cortex_param_int()

```c
int64_t cortex_param_int(const char *params, const char *key, int64_t default_val);
```

**Purpose:** Extract integer parameter.

**Example:**
```c
int order = cortex_param_int(params, "order", 129);
int channels = cortex_param_int(params, "ref_channels", 64);
```

#### cortex_param_string()

```c
void cortex_param_string(const char *params, const char *key, char *out, size_t out_size, const char *default_val);
```

**Purpose:** Extract string parameter.

**Example:**
```c
char window[64];
cortex_param_string(params, "window", window, sizeof(window), "hamming");
```

#### cortex_param_bool()

```c
int cortex_param_bool(const char *params, const char *key, int default_val);
```

**Purpose:** Extract boolean parameter.

**Accepted values:** `true`, `false`, `yes`, `no`, `1`, `0` (case-insensitive)

**Example:**
```c
int enabled = cortex_param_bool(params, "enabled", 1);  // Returns 1 (true) or 0 (false)
```

### Supported Formats

**YAML-style:**
```yaml
f0_hz: 60.0
Q: 30.0
order: 129
window: hamming
enabled: true
```

**URL-style:**
```
f0_hz=60.0&Q=30.0&order=129&window=hamming&enabled=true
```

**Both formats can be mixed**, but YAML is recommended for readability in config files.

See [`../lib/params/README.md`](../lib/params/README.md) for complete documentation.

---

## cortex_state_io.h

Binary state file serialization. Required for trainable kernels (ICA, CSP, LDA).

### Functions

#### cortex_state_save()

```c
int cortex_state_save(const char *filepath, const void *payload, uint32_t size, uint32_t version);
```

**Purpose:** Serialize calibration state to `.cortex_state` file.

**Returns:** 0 on success, -1 on failure.

**Example:**
```c
float *weights = train_ica(data, num_windows);  // C×C unmixing matrix
uint32_t size = C * C * sizeof(float);
cortex_state_save("ica_S001.cortex_state", weights, size, 1);
```

#### cortex_state_load()

```c
int cortex_state_load(const char *filepath, void **out_payload, uint32_t *out_size, uint32_t *out_version);
```

**Purpose:** Deserialize calibration state from `.cortex_state` file.

**Returns:** 0 on success, -1 on failure.

**Note:** Caller must free `*out_payload` using `cortex_state_free()` or `free()`.

**Example:**
```c
void *state_payload;
uint32_t state_size, state_version;

if (cortex_state_load("ica_S001.cortex_state", &state_payload, &state_size, &state_version) == 0) {
    float *weights = (float *)state_payload;
    // Use weights...
}
```

#### cortex_state_free()

```c
void cortex_state_free(void *payload);
```

**Purpose:** Free memory allocated by `cortex_state_load()`.

**Example:**
```c
cortex_state_free(state_payload);
```

### File Format

```
┌─────────────────────────┐
│ Magic: "CXST" (4 bytes) │  Identifies CORTEX state file
│ Version: uint32_t       │  Kernel-defined version number
│ Size: uint32_t          │  Payload size in bytes
├─────────────────────────┤
│ Kernel-specific data    │  Binary payload (size bytes)
│ (e.g., ICA weights)     │
└─────────────────────────┘
```

**Version field:** Kernel-defined (e.g., 1 for initial ICA format, 2 for optimized format).

---

## cortex_loader.h

Plugin loader utilities. **Not used by kernels** (harness-only).

### Types

#### cortex_scheduler_plugin_api_t

Function pointers loaded from plugin via `dlsym()`.

```c
typedef struct {
    cortex_init_result_t (*init)(const cortex_plugin_config_t *config);
    void (*process)(void *handle, const void *input, void *output);
    void (*teardown)(void *handle);
    cortex_calibration_result_t (*calibrate)(...);  // NULL for v2 kernels
    uint32_t capabilities;
} cortex_scheduler_plugin_api_t;
```

### Functions

Not documented here (harness-internal use only).

---

## Quick Reference

### Minimal Kernel (v2 - Stateless/Stateful)

```c
#include "cortex_plugin.h"

typedef struct { uint32_t channels, window_length; } state_t;

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};
    if (!config || config->abi_version != 3) return result;

    state_t *s = calloc(1, sizeof(state_t));
    s->channels = config->channels;
    s->window_length = config->window_length_samples;

    result.handle = s;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;
    return result;
}

void cortex_process(void *handle, const void *input, void *output) {
    state_t *s = (state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    for (uint32_t i = 0; i < s->window_length * s->channels; i++) {
        out[i] = process(in[i]);  // Your algorithm here
    }
}

void cortex_teardown(void *handle) {
    free(handle);
}
```

### Kernel with Parameters

```c
#include "cortex_plugin.h"
#include "cortex_params.h"

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // ...
    const char *params = config->kernel_params;
    double f0 = cortex_param_float(params, "f0_hz", 60.0);
    int order = cortex_param_int(params, "order", 129);
    // Use f0, order...
}
```

### Trainable Kernel (v3)

```c
#include "cortex_plugin.h"
#include "cortex_state_io.h"

cortex_calibration_result_t cortex_calibrate(...) {
    float *weights = train(...);
    cortex_state_save("model.cortex_state", weights, size, 1);
    cortex_calibration_result_t result = {.success = 1};
    return result;
}

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    void *payload; uint32_t size, version;
    cortex_state_load(config->calibration_state, &payload, &size, &version);
    // Use payload as state...
    cortex_init_result_t result = {
        .handle = payload,
        .capabilities = CORTEX_CAP_OFFLINE_CALIB
    };
    return result;
}
```

## Further Reading

- **SDK Overview**: [`../../README.md`](../../README.md)
- **Kernel SDK**: [`../README.md`](../README.md)
- **Tools**: [`../tools/README.md`](../tools/README.md)
- **Parameter API**: [`../lib/params/README.md`](../lib/params/README.md)
- **Plugin Interface Spec**: [`../../../docs/reference/plugin-interface.md`](../../../docs/reference/plugin-interface.md)
