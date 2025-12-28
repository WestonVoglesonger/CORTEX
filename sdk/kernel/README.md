# CORTEX Kernel SDK

Core SDK subsystem for BCI signal processing kernel development.

## Overview

The Kernel SDK provides everything needed to develop, test, and deploy CORTEX-compatible signal processing algorithms:

- **Public API Headers** - Plugin ABI, loader, state management, parameters
- **Unified Library** - All SDK functionality in single `libcortex.a`
- **Development Tools** - Calibration and validation utilities

## Architecture

```
sdk/kernel/
├── README.md          # This file
├── include/           # Public API headers (4 headers)
│   ├── README.md                # API reference documentation
│   ├── cortex_plugin.h          # Plugin ABI v3 specification
│   ├── cortex_loader.h          # Plugin loader utilities
│   ├── cortex_state_io.h        # State serialization (trainable kernels)
│   └── cortex_params.h          # Runtime parameter accessors
├── lib/               # SDK library implementation
│   ├── Makefile                 # Builds libcortex.a (11KB)
│   ├── loader/                  # Dynamic plugin loading
│   │   └── loader.c
│   ├── state_io/                # Binary state file I/O
│   │   └── state_io.c
│   └── params/                  # YAML/URL-style parameter parsing
│       ├── README.md            # Parameter API documentation
│       └── accessor.c
└── tools/             # Development tools
    ├── README.md                # Tools documentation
    ├── Makefile                 # Builds calibrate & validate
    ├── calibrate.c              # Kernel training tool (cortex_calibrate)
    └── validate.c               # Oracle validation tool (cortex_validate)
```

## Components

### Public API Headers (`include/`)

All kernel code needs only one include directory:

```makefile
CFLAGS = -I../../../../sdk/kernel/include
```

#### cortex_plugin.h

**Purpose:** Core plugin ABI v3 specification

**Defines:**
- `cortex_plugin_config_t` - Runtime configuration passed to kernel
- `cortex_init_result_t` - Return value from `cortex_init()`
- `cortex_calibration_result_t` - Return value from `cortex_calibrate()` (ABI v3)
- `CORTEX_DTYPE_*` - Data type enums (FLOAT32, FLOAT64, etc.)
- `CORTEX_CAP_*` - Capability flags (OFFLINE_CALIB, etc.)

**Required Functions:**
```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
void cortex_process(void *handle, const void *input, void *output);
void cortex_teardown(void *handle);
```

**Optional Functions (ABI v3 trainable kernels):**
```c
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
);
```

See [`include/README.md#cortex_plugin.h`](include/README.md#cortex_pluginh) for full specification.

#### cortex_params.h

**Purpose:** Type-safe runtime parameter parsing

**Functions:**
```c
double cortex_param_float(const char *params, const char *key, double default_val);
int64_t cortex_param_int(const char *params, const char *key, int64_t default_val);
void cortex_param_string(const char *params, const char *key, char *out, size_t out_size, const char *default_val);
int cortex_param_bool(const char *params, const char *key, int default_val);
```

**Example:**
```c
#include "cortex_params.h"

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    const char *params = (const char *)config->kernel_params;

    // Parse YAML-style: "f0_hz: 60.0\nQ: 30.0"
    // or URL-style: "f0_hz=60.0&Q=30.0"
    double f0 = cortex_param_float(params, "f0_hz", 60.0);
    double Q = cortex_param_float(params, "Q", 30.0);
    int order = cortex_param_int(params, "order", 129);

    // Use parameters...
}
```

See [`lib/params/README.md`](lib/params/README.md) for complete documentation.

#### cortex_state_io.h

**Purpose:** Calibration state serialization (trainable kernels only)

**Functions:**
```c
int cortex_state_save(const char *filepath, const void *payload, uint32_t size, uint32_t version);
int cortex_state_load(const char *filepath, void **out_payload, uint32_t *out_size, uint32_t *out_version);
void cortex_state_free(void *payload);
```

**File Format:**
```
┌─────────────────────────┐
│ Magic: "CXST" (4 bytes) │
│ Version: uint32_t       │
│ Size: uint32_t          │
├─────────────────────────┤
│ Kernel-specific data    │
│ (size bytes)            │
└─────────────────────────┘
```

**Example:**
```c
#include "cortex_state_io.h"

cortex_calibration_result_t cortex_calibrate(...) {
    // Train model...
    float *weights = train_ica(calibration_data, num_windows);

    // Save state
    cortex_state_save("model.cortex_state", weights, size, 1);

    cortex_calibration_result_t result = {0};
    result.success = 1;
    return result;
}

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // Load state
    void *state_payload;
    uint32_t state_size, state_version;
    cortex_state_load(config->calibration_state, &state_payload, &state_size, &state_version);

    cortex_init_result_t result = {0};
    result.handle = state_payload;
    result.capabilities = CORTEX_CAP_OFFLINE_CALIB;
    return result;
}
```

#### cortex_loader.h

**Purpose:** Plugin loader utilities (used by harness, generally not needed by kernels)

**Defines:**
- `cortex_scheduler_plugin_api_t` - Function pointers loaded via dlsym
- `cortex_loaded_plugin_t` - Loaded plugin handle

**Functions:**
```c
int cortex_plugin_build_path(const char *spec_uri, char *out_path, size_t out_sz);
int cortex_plugin_load(const char *path, cortex_loaded_plugin_t *out);
void cortex_plugin_unload(cortex_loaded_plugin_t *p);
```

**Kernel developers don't typically use this header** (harness-only functionality).

### Unified Library (`lib/libcortex.a`)

Single static library combining all SDK components.

**Build:**
```bash
make -C sdk/kernel/lib
```

**Link:**
```makefile
LDFLAGS = -L../../../../sdk/kernel/lib -lcortex
```

**Components:**

| Component | Source | Purpose |
|-----------|--------|---------|
| **loader** | `lib/loader/loader.c` | `dlopen`/`dlsym` wrappers, ABI detection |
| **state_io** | `lib/state_io/state_io.c` | Binary state file serialization |
| **params** | `lib/params/accessor.c` | YAML/URL parameter parsing |

**Size:** ~11KB (optimized with `-O2`)

### Development Tools (`tools/`)

#### cortex_calibrate

**Purpose:** Train trainable kernels on batch data

**Usage:**
```bash
sdk/kernel/tools/cortex_calibrate \
    --kernel ica \
    --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
    --windows 500 \
    --output ica_S001.cortex_state
```

**Workflow:**
1. Loads kernel plugin
2. Reads calibration dataset (N windows × W samples × C channels)
3. Calls `cortex_calibrate()` function
4. Saves resulting state to `.cortex_state` file

**Output:**
```
================================================================================
CORTEX Kernel Calibration (ABI v3)
================================================================================

Kernel:       ica
Spec URI:     primitives/kernels/v1/ica@f32
Dataset:      primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32
Windows:      500
Output:       ica_S001.cortex_state

Running calibration...

✓ Calibration successful
  State file: ica_S001.cortex_state (16,512 bytes)

Usage:
  cortex run --kernel ica --calibration-state ica_S001.cortex_state
  cortex validate --kernel ica --calibration-state ica_S001.cortex_state
================================================================================
```

See [`tools/README.md#cortex_calibrate`](tools/README.md#cortex_calibrate) for full documentation.

#### cortex_validate

**Purpose:** Validate C kernel output against Python oracle (SciPy/NumPy reference)

**Usage:**
```bash
sdk/kernel/tools/cortex_validate --kernel notch_iir --windows 10 --verbose
```

**Workflow:**
1. Loads C kernel plugin
2. Loads corresponding Python oracle (`oracle.py`)
3. Processes same windows through both
4. Compares outputs (element-wise max absolute/relative error)
5. Reports PASS/FAIL per tolerance thresholds

**Output:**
```
Window 0 PASSED: max_abs=3.05e-05, max_rel=4.12e-06
Window 1 PASSED: max_abs=2.98e-05, max_rel=3.68e-05
Window 2 PASSED: max_abs=3.12e-05, max_rel=4.05e-06
...
✅ notch_iir: ALL TESTS PASSED (10 windows)
```

See [`tools/README.md#cortex_validate`](tools/README.md#cortex_validate) for full documentation.

## Build System Integration

### Kernel Makefile Template

```makefile
CC = cc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../../../../sdk/kernel/include -fPIC

# Platform detection
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SOFLAG = -dynamiclib
    LIBEXT = .dylib
    LDFLAGS = -L../../../../sdk/kernel/lib -lcortex -lm
else
    SOFLAG = -shared
    LIBEXT = .so
    LDFLAGS = -L../../../../sdk/kernel/lib -lcortex -lm
endif

# Kernel name from directory (e.g., "notch_iir" from "notch_iir@f32/")
KERNEL_NAME = $(shell basename $(CURDIR) | sed 's/@.*//')
PLUGIN_SRC = $(KERNEL_NAME).c
PLUGIN_OBJ = $(KERNEL_NAME).o
PLUGIN_LIB = lib$(KERNEL_NAME)$(LIBEXT)

all: $(PLUGIN_LIB)

$(PLUGIN_OBJ): $(PLUGIN_SRC)
	$(CC) $(CFLAGS) -c -o $@ $<

$(PLUGIN_LIB): $(PLUGIN_OBJ)
	$(CC) $(SOFLAG) -o $@ $(PLUGIN_OBJ) $(LDFLAGS)

clean:
	rm -f $(PLUGIN_OBJ) $(PLUGIN_LIB)

.PHONY: all clean
```

### Harness Integration

**Harness Makefile** (`src/engine/harness/Makefile`):
```makefile
CFLAGS = -I../../../sdk/kernel/include ...
LDFLAGS = -L../../../sdk/kernel/lib -lcortex ...
```

**Test Makefile** (`tests/Makefile`):
```makefile
CFLAGS = -I../sdk/kernel/include ...
LDFLAGS = -L../sdk/kernel/lib -lcortex ...
```

## Development Workflow

### 1. Create New Kernel

```bash
# Create directory
mkdir -p primitives/kernels/v1/my_kernel@f32
cd primitives/kernels/v1/my_kernel@f32

# Create files
touch my_kernel.c spec.yaml Makefile README.md oracle.py
```

### 2. Implement Kernel

**my_kernel.c:**
```c
#include "cortex_plugin.h"
#include "cortex_params.h"

typedef struct {
    uint32_t channels;
    uint32_t window_length;
    // kernel-specific state...
} my_kernel_state_t;

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    // Parse runtime parameters
    const char *params = (const char *)config->kernel_params;
    double param1 = cortex_param_float(params, "param1", 1.0);

    // Allocate state
    my_kernel_state_t *state = calloc(1, sizeof(my_kernel_state_t));
    state->channels = config->channels;
    state->window_length = config->window_length_samples;

    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;
    result.capabilities = 0;  // v2 kernel (no calibration)

    return result;
}

void cortex_process(void *handle, const void *input, void *output) {
    my_kernel_state_t *s = (my_kernel_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    // Process window: apply algorithm to transform in → out
    for (uint32_t t = 0; t < s->window_length; t++) {
        for (uint32_t c = 0; c < s->channels; c++) {
            uint32_t idx = t * s->channels + c;
            out[idx] = process_sample(in[idx], s);
        }
    }
}

void cortex_teardown(void *handle) {
    my_kernel_state_t *s = (my_kernel_state_t *)handle;
    free(s);
}
```

### 3. Create Python Oracle

**oracle.py:**
```python
#!/usr/bin/env python3
import numpy as np
from scipy import signal

def my_kernel_oracle(x, **params):
    """Reference implementation using SciPy/NumPy"""
    # x: (W, C) array
    # returns: (W, C) array
    return signal.sosfilt(sos, x, axis=0)  # example
```

### 4. Build and Validate

```bash
# Build kernel
make

# Validate against oracle
sdk/kernel/tools/cortex_validate --kernel my_kernel --windows 10 --verbose

# Should see:
# ✅ my_kernel: ALL TESTS PASSED (10 windows)
```

### 5. Integrate into Harness

Add to `primitives/configs/cortex.yaml`:
```yaml
plugins:
  - spec_uri: "primitives/kernels/v1/my_kernel@f32"
    params:
      param1: 2.5
```

Run full pipeline:
```bash
cortex pipeline
```

## Trainable Kernel Workflow (ICA Example)

See [`primitives/kernels/v1/ica@f32/`](../../primitives/kernels/v1/ica@f32/) for complete reference implementation.

**Key steps:**
1. Implement `cortex_calibrate()` - Train model on batch data
2. Save state using `cortex_state_save()`
3. Load state in `cortex_init()` using `cortex_state_load()`
4. Set `result.capabilities = CORTEX_CAP_OFFLINE_CALIB`
5. Calibrate: `sdk/kernel/tools/cortex_calibrate ...`
6. Validate: `sdk/kernel/tools/cortex_validate --state model.cortex_state`
7. Benchmark: `cortex run --calibration-state model.cortex_state`

## API Versioning

| ABI Version | Release | Features | Backward Compatible |
|-------------|---------|----------|---------------------|
| v1 | 2024-10 | Initial release (stateless kernels) | N/A |
| v2 | 2024-11 | Stateful kernels, output dimension control | ✅ v1 → v2 |
| v3 | 2024-12 | Trainable kernels (`cortex_calibrate()`), capability flags | ✅ v2 → v3 |

**Loader auto-detection:**
```c
void *calib_fn = dlsym(plugin, "cortex_calibrate");
if (calib_fn != NULL) {
    // v3 trainable kernel
} else {
    // v2 stateful/stateless kernel
}
```

## Best Practices

1. **Hermetic `cortex_process()`**: No heap allocation, no I/O, no syscalls
2. **Validate before benchmarking**: Always pass oracle validation first
3. **Use SDK parameters**: Leverage `cortex_param_*()` for runtime config
4. **Document state format**: For trainable kernels, document `.cortex_state` structure
5. **Test on real data**: Use PhysioNet datasets, not synthetic sine waves
6. **Check for NaN**: Handle NaN inputs gracefully (replace with 0.0 or skip)
7. **Zero-initialize results**: `cortex_init_result_t result = {0};`

## Troubleshooting

### "dlsym: symbol not found: cortex_init"

**Cause:** Plugin doesn't export required ABI functions

**Fix:** Ensure functions are NOT static:
```c
// ❌ Wrong:
static cortex_init_result_t cortex_init(...) { }

// ✅ Correct:
cortex_init_result_t cortex_init(...) { }
```

### "Calibration state required but not provided"

**Cause:** Trainable kernel requires calibration state but none passed

**Fix:**
```bash
# Calibrate first
sdk/kernel/tools/cortex_calibrate --kernel ica ... --output state.cortex_state

# Then validate
sdk/kernel/tools/cortex_validate --kernel ica --state state.cortex_state
```

### "Oracle validation failed: max_abs=1.23e-2"

**Cause:** C implementation doesn't match Python oracle

**Fix:**
1. Check algorithm correctness
2. Verify numeric precision (use `double` for intermediate calculations)
3. Compare with SciPy documentation for filter design
4. Ensure state continuity across windows (IIR filters)

## Further Documentation

- **SDK Overview**: [`../README.md`](../README.md)
- **API Reference**: [`include/README.md`](include/README.md)
- **Tools Guide**: [`tools/README.md`](tools/README.md)
- **Adding Kernels**: [`../../docs/guides/adding-kernels.md`](../../docs/guides/adding-kernels.md)
- **Plugin Interface**: [`../../docs/reference/plugin-interface.md`](../../docs/reference/plugin-interface.md)
- **ABI v3 Migration**: [`../../docs/guides/migrating-to-abi-v3.md`](../../docs/guides/migrating-to-abi-v3.md)
