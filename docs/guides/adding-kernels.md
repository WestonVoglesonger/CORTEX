# Adding New Kernels to CORTEX

This guide walks through the complete process of adding a new signal processing kernel to CORTEX, from specification to validation.

## Overview

A kernel in CORTEX is a signal processing algorithm (like filtering, feature extraction, or transformation) that operates on windowed EEG data. Each kernel is implemented as a dynamic plugin that the harness loads at runtime.

**Kernel Types**:
- **Stateless/Stateful Kernels** (ABI v2/v3): Fixed-parameter algorithms like filters, spatial processing, frequency analysis
- **Trainable Kernels** (ABI v3 only): Algorithms requiring calibration phase like ICA, CSP

**Time estimate**:
- 4-8 hours for simple stateless/stateful kernels (CAR, notch filter)
- 12-20 hours for trainable kernels (ICA, CSP)

## Prerequisites

- Understanding of the signal processing algorithm
- C11 compiler and build tools
- Python 3.8+ with SciPy/NumPy
- Familiarity with the plugin ABI (see [plugin-interface.md](../reference/plugin-interface.md))

## Step-by-Step Guide

### Step 1: Create Directory Structure

```bash
# Choose an appropriate name (lowercase, underscores for multi-word)
KERNEL_NAME="your_kernel"  # e.g., "car", "notch_iir", "welch_psd"

# Create directory for v1 float32 implementation
mkdir -p primitives/kernels/v1/${KERNEL_NAME}@f32
cd primitives/kernels/v1/${KERNEL_NAME}@f32
```

**Naming conventions**:
- Lowercase with underscores: `notch_iir`, `bandpass_fir`
- Descriptive but concise: `car` not `common_average_reference`
- Algorithm first: `notch_iir` not `iir_notch`

### Step 2: Write spec.yaml

Create `spec.yaml` with machine-readable kernel specification:

```yaml
kernel:
  name: "your_kernel"
  version: "v1"
  dtype: "float32"
  description: "Brief one-line description"

abi:
  input_shape:
    window_length: 160    # W samples (from config)
    channels: 64          # C channels (from config)
  output_shape:
    window_length: 160    # Usually same as input
    channels: 64          # Can differ (e.g., bandpower → fewer channels)
  stateful: true          # Does algorithm maintain state across windows?

numerical:
  tolerance:
    rtol: 1.0e-5          # Relative tolerance vs oracle
    atol: 1.0e-6          # Absolute tolerance vs oracle

oracle:
  path: "oracle.py"
  function: "your_kernel_oracle"
  dependencies: ["numpy", "scipy"]  # Add "mne" if needed
```

**Key decisions**:
- `output_shape`: Most kernels preserve dimensions. Bandpower/PSD reduce channels.
- `stateful`: `true` for IIR/FIR filters (state persists), `false` for CAR/bandpower
- `tolerance`: Tighter for simple algorithms (CAR: 1e-6), looser for iterative (Welch: 1e-4)

### Step 3: Write README.md

Document your kernel thoroughly:

````markdown
# Your Kernel Name

## Overview

[One paragraph: what it does, why it's useful, what use case]

## Signal Model

Input `x[t,c]` with shape `[W×C]` in µV → Output `y[t,c]` with shape `[W×C]` in µV.

[Mathematical equations using LaTeX]

$$
y[t] = H(x[t])
$$

[Explain variables, parameters, frequency response, etc.]

## Parameters

- `param1`: Description (default: value)
- `param2`: Description (default: value)

Parameters are extracted at runtime using the accessor API (see Step 5 for implementation).

## Edge Cases

- **NaN handling**: [How does your algorithm handle NaN inputs?]
- **State initialization**: [How is state initialized for first window?]
- **Boundary conditions**: [How do you handle window edges?]

## Acceptance Criteria

- Float32 vs oracle within `rtol=1e-5`, `atol=1e-6`
- [Any algorithm-specific correctness checks]

## Real-time Budget

- **Expected latency**: [< X ms per window]
- **Memory footprint**: [State size, allocations]
- **Throughput**: [Expected windows/sec]

## Usage

Reference in `cortex.yaml`:

```yaml
plugins:
  - name: "your_kernel"
    spec_uri: "primitives/kernels/v1/your_kernel@f32"
    adapter_path: "primitives/adapters/v1/native/cortex_adapter_native"
    spec_version: "1.0.0"
    runtime:
      window_length_samples: 160
      hop_samples: 80
      channels: 64
      dtype: "float32"
    params: {}  # Optional: kernel-specific runtime parameters
```

## Implementation Status

- [x] Specification defined
- [x] Oracle implementation
- [x] C implementation
- [x] Validation passed
````

### Step 4: Write oracle.py

Create Python reference implementation:

```python
#!/usr/bin/env python3
"""
Oracle reference implementation for your_kernel.
Validates C implementation against gold-standard libraries (SciPy/MNE/NumPy).
"""

import numpy as np
from scipy import signal  # or other libraries

def your_kernel_oracle(x, **params):
    """
    Reference implementation using SciPy/NumPy.
    
    Args:
        x: Input array, shape (W, C) - W samples x C channels
        params: Algorithm parameters (currently unused, future feature)
    
    Returns:
        y: Output array, shape (W, C) or other as specified
    """
    W, C = x.shape
    y = np.zeros_like(x)  # Adjust shape if output differs
    
    # Your algorithm here using SciPy/NumPy
    # ...
    
    return y

def main():
    """Test oracle with synthetic data"""
    # Generate test input
    W, C = 160, 64
    x = np.random.randn(W, C).astype(np.float32)
    
    # Run oracle
    y = your_kernel_oracle(x)
    
    # Validate output
    assert y.shape == (W, C), f"Expected shape ({W}, {C}), got {y.shape}"
    assert not np.any(np.isnan(y)), "Output contains NaNs"
    
    print(f"✓ Oracle test passed: {W}×{C} → {y.shape}")
    print(f"  Input range: [{x.min():.2f}, {x.max():.2f}]")
    print(f"  Output range: [{y.min():.2f}, {y.max():.2f}]")

if __name__ == "__main__":
    main()
```

**Test your oracle**:
```bash
python oracle.py
# Should output: ✓ Oracle test passed
```

### Step 5: Write {name}.c

Implement the C kernel following plugin ABI:

```c
#include "cortex_plugin.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

// Plugin state (persistent across windows)
typedef struct {
    int W;           // Window length
    int C;           // Number of channels
    // Add your state variables here (IIR coefficients, buffers, etc.)
    // float *state;
} your_kernel_state_t;

// cortex_init: Allocate resources, validate config
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // 1. Validate ABI version
    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[your_kernel] ABI version mismatch: got %d, expected %d\n",
                config->abi_version, CORTEX_ABI_VERSION);
        return (cortex_init_result_t){NULL, 0, 0};
    }
    
    // 2. Validate struct size
    if (config->struct_size != sizeof(cortex_plugin_config_t)) {
        fprintf(stderr, "[your_kernel] Config struct size mismatch\n");
        return (cortex_init_result_t){NULL, 0, 0};
    }
    
    // 3. Allocate persistent state
    your_kernel_state_t *state = calloc(1, sizeof(your_kernel_state_t));
    if (!state) {
        fprintf(stderr, "[your_kernel] Failed to allocate state\n");
        return (cortex_init_result_t){NULL, 0, 0};
    }
    
    // 4. Extract runtime parameters (if needed)
    // #include "accessor.h" at top of file
    // const char *params = (const char *)config->kernel_params;
    // double my_param = cortex_param_float(params, "my_param", 1.0);  // default: 1.0
    // int order = cortex_param_int(params, "order", 4);  // default: 4
    // See sdk/kernel/lib/params/README.md for full accessor API

    // 5. Store configuration
    state->W = config->window_length_samples;
    state->C = config->channels;

    // 6. Pre-allocate any working buffers
    // state->buffer = malloc(state->W * sizeof(float));
    // if (!state->buffer) {
    //     free(state);
    //     return (cortex_init_result_t){NULL, 0, 0};
    // }
    
    // 7. Initialize algorithm-specific state (coefficients, delays, etc.)
    // Use extracted parameters here to configure your algorithm

    // 8. Return handle and output dimensions
    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = state->W,  // Adjust if output differs
        .output_channels = state->C
    };
}

// cortex_process: Process one window (NO ALLOCATIONS!)
void cortex_process(void *handle, const void *input, void *output) {
    your_kernel_state_t *state = (your_kernel_state_t *)handle;
    const float *x = (const float *)input;  // Shape: [W×C] row-major
    float *y = (float *)output;
    
    const int W = state->W;
    const int C = state->C;
    
    // Your algorithm here
    // IMPORTANT: No malloc/calloc/realloc allowed!
    // All memory must be pre-allocated in cortex_init()
    
    for (int t = 0; t < W; t++) {
        for (int c = 0; c < C; c++) {
            int idx = t * C + c;  // Row-major index
            
            // Handle NaN gracefully
            if (isnan(x[idx])) {
                y[idx] = 0.0f;  // Or skip, or substitute
                continue;
            }
            
            // Your processing here
            y[idx] = x[idx];  // Placeholder
        }
    }
}

// cortex_teardown: Free resources
void cortex_teardown(void *handle) {
    if (!handle) return;
    
    your_kernel_state_t *state = (your_kernel_state_t *)handle;
    
    // Free any buffers allocated in init()
    // if (state->buffer) free(state->buffer);
    
    // Free state struct
    free(state);
}
```

**Critical rules**:
- **NO allocations in `cortex_process()`** - pre-allocate everything in `init()`
- Handle NaNs gracefully (substitute 0, skip, or exclude from calculation)
- Return `{NULL, 0, 0}` from `init()` on any error
- Always check `abi_version` and `struct_size` in `init()`

### Step 6: Create Makefile

Copy and adapt from existing kernel:

```makefile
# Makefile for your_kernel@f32 plugin

CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../../../../sdk/kernel/include -fPIC
PARAMS_LIB = ../../../../sdk/kernel/lib/libcortex.a
LDFLAGS = -lm

# Detect platform for plugin extension
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SOFLAG = -dynamiclib
    LIBEXT = .dylib
else
    SOFLAG = -shared
    LIBEXT = .so
endif

TARGET = libyour_kernel$(LIBEXT)
SRC = your_kernel.c
OBJ = $(SRC:.c=.o)

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJ) $(PARAMS_LIB)
	$(CC) $(SOFLAG) -o $@ $(OBJ) $(PARAMS_LIB) $(LDFLAGS)

# Build params library if it doesn't exist
$(PARAMS_LIB):
	$(MAKE) -C ../../../../src/engine/params

%.o: %.c
	$(CC) $(CFLAGS) -c $<

clean:
	rm -f $(TARGET) $(OBJ)
```

### Step 7: Build and Test

```bash
# Build plugin
make

# Test oracle
python oracle.py

# Verify plugin loads (should see output dimensions)
cd ../../../..
./src/engine/harness/cortex --help  # Rebuild harness if needed
```

### Step 8: Validate Against Oracle

Add kernel to test config and run validation:

```bash
# Run kernel accuracy test
cd tests
./test_kernel_accuracy --kernel your_kernel --windows 10 --verbose

# Expected output:
# Window 1/10: max_diff=1.23e-06 (within tolerance)
# ...
# ✓ All windows within tolerance (rtol=1e-5, atol=1e-6)
```

Or use CLI:
```bash
cortex validate --kernel your_kernel --verbose
```

### Step 9: Integration Test

Run full benchmark to ensure integration works:

```bash
# Short test run
cortex run --kernel your_kernel --duration 30

# Check results
ls results/batch_*/your_kernel_run/
cat results/batch_*/your_kernel_run/your_kernel_telemetry.ndjson | head -5

# Analyze
cortex analyze results/batch_*
```

### Step 10: Add to Registry

Update configuration to include your kernel:

```bash
# Edit primitives/configs/cortex.yaml
vim primitives/configs/cortex.yaml
```

Add entry:
```yaml
plugins:
  - name: "your_kernel"
    status: ready
    spec_uri: "primitives/kernels/v1/your_kernel@f32"
    adapter_path: "primitives/adapters/v1/native/cortex_adapter_native"
    spec_version: "1.0.0"
```

## Part 2: Trainable Kernels (ABI v3)

Trainable kernels require a **calibration phase** where the algorithm learns from batch data before processing live windows. Examples include ICA (artifact removal), CSP (motor imagery), and LDA (classification).

**When to use trainable kernels**:
- Algorithm requires batch training (FastICA, eigendecomposition, supervised learning)
- Parameters cannot be set a priori (ICA unmixing matrix, CSP spatial filters, classifier weights)
- Performance depends on subject-specific calibration

**Time estimate**: 12-20 hours (includes calibration script, oracle, C implementation)

### Overview of Two-Phase Workflow

```
PHASE 1: Calibration (offline, one-time)
├─ Load calibration dataset (N windows)
├─ cortex_calibrate() trains model
├─ Returns calibration_state (serialized model)
└─ Save to .cortex_state file

PHASE 2: Inference (online, per-window)
├─ cortex_init() loads pre-trained state
├─ cortex_process() applies trained model
└─ No re-training during inference
```

### Additional Prerequisites

- Calibration dataset with sufficient windows (typically 100-1000 depending on algorithm)
- Understanding of batch training algorithm (FastICA, CSP, etc.)
- NumPy/SciPy libraries for oracle calibration reference

### Step 1: Design State Format

Define your kernel's calibration state structure:

```c
// Example: ICA kernel state (unmixing matrix W)
typedef struct {
    uint32_t C;              // Number of channels
    float *W;                // Unmixing matrix [C×C]
} ica_calibration_state_t;

// Serialization format:
// Bytes 0-3:   C (uint32_t, little-endian)
// Bytes 4-end: W (C*C floats, row-major, little-endian)
```

**Design principles**:
- Use simple binary layout (raw floats/ints, little-endian)
- Include version field if state format may evolve
- Document byte layout in README.md
- Keep state minimal (only trained parameters, not runtime buffers)

### Step 2: Implement cortex_calibrate()

Add calibration function to your kernel:

```c
#include "cortex_plugin.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

// Calibration function (exports via symbol table)
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
) {
    // 1. Validate ABI version
    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[your_kernel] ABI v3 required for calibration\n");
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    // 2. Extract configuration
    const int W = config->window_length_samples;
    const int C = config->channels;
    const float *data = (const float *)calibration_data;  // Shape: [num_windows, W, C]

    // 3. Allocate working memory for batch training
    //    (This is allowed in calibrate(), but NOT in process())
    float *X = malloc(num_windows * W * C * sizeof(float));
    if (!X) {
        fprintf(stderr, "[your_kernel] Calibration memory allocation failed\n");
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    // 4. Preprocess data (concatenate windows, remove mean, etc.)
    memcpy(X, data, num_windows * W * C * sizeof(float));
    // ... preprocessing ...

    // 5. Run batch training algorithm
    //    Example: FastICA, CSP eigendecomposition, LDA fit
    float *W_unmix = malloc(C * C * sizeof(float));
    if (!W_unmix) {
        free(X);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    // YOUR TRAINING ALGORITHM HERE
    // (e.g., FastICA iterations, eigendecomposition, gradient descent)
    // Populate W_unmix with trained parameters

    // 6. Serialize state to binary format
    uint32_t state_size = sizeof(uint32_t) + C * C * sizeof(float);
    uint8_t *state_bytes = malloc(state_size);
    if (!state_bytes) {
        free(X);
        free(W_unmix);
        return (cortex_calibration_result_t){NULL, 0, 0};
    }

    // Write header (C as uint32_t)
    memcpy(state_bytes, &C, sizeof(uint32_t));

    // Write unmixing matrix (C*C floats)
    memcpy(state_bytes + sizeof(uint32_t), W_unmix, C * C * sizeof(float));

    // 7. Clean up temporary allocations
    free(X);
    free(W_unmix);

    // 8. Return calibration result
    return (cortex_calibration_result_t){
        .calibration_state = state_bytes,
        .state_size_bytes = state_size,
        .state_version = 1  // Increment if state format changes
    };
}
```

**Critical constraints**:
- **MAY** allocate memory (one-time operation)
- **MAY** perform expensive computation (iterative convergence)
- **MUST** be deterministic (same input → same output)
- **MUST** handle NaN inputs gracefully
- **MUST** free temporary allocations before returning
- State memory will be freed by harness (do NOT free it yourself)

### Step 3: Modify cortex_init() for Calibration State

Update initialization to accept pre-trained state:

```c
// Runtime state (includes loaded calibration state + processing buffers)
typedef struct {
    int W, C;
    float *W_unmix;      // Loaded from calibration_state
    float *work_buffer;  // Allocated for per-window processing
} your_kernel_runtime_t;

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // 1. Validate ABI version (accept v2 for testing, v3 for production)
    if (config->abi_version < 2 || config->abi_version > CORTEX_ABI_VERSION) {
        fprintf(stderr, "[your_kernel] Unsupported ABI version %u\n", config->abi_version);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    const int W = config->window_length_samples;
    const int C = config->channels;

    // 2. Allocate runtime state
    your_kernel_runtime_t *state = calloc(1, sizeof(your_kernel_runtime_t));
    if (!state) {
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    state->W = W;
    state->C = C;

    // 3. Load calibration state (REQUIRED for trainable kernels)
    if (config->calibration_state == NULL || config->calibration_state_size == 0) {
        fprintf(stderr, "[your_kernel] ERROR: Calibration state required but not provided\n");
        fprintf(stderr, "  Run: cortex calibrate --kernel your_kernel --dataset path/to/data.float32\n");
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    // 4. Deserialize calibration state
    const uint8_t *state_bytes = (const uint8_t *)config->calibration_state;

    // Read header
    uint32_t C_stored;
    memcpy(&C_stored, state_bytes, sizeof(uint32_t));

    if (C_stored != C) {
        fprintf(stderr, "[your_kernel] Channel count mismatch: state has %u, config has %d\n",
                C_stored, C);
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    // Allocate and load unmixing matrix
    state->W_unmix = malloc(C * C * sizeof(float));
    if (!state->W_unmix) {
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }
    memcpy(state->W_unmix, state_bytes + sizeof(uint32_t), C * C * sizeof(float));

    // 5. Allocate per-window work buffers
    state->work_buffer = malloc(W * C * sizeof(float));
    if (!state->work_buffer) {
        free(state->W_unmix);
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    // 6. Return handle with capabilities flag
    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = W,
        .output_channels = C,
        .capabilities = CORTEX_CAP_OFFLINE_CALIB  // Advertise calibration support
    };
}
```

**Key differences from stateless/stateful kernels**:
- **MUST** check for `calibration_state != NULL`
- **MUST** deserialize state and validate compatibility
- **MUST** set `capabilities = CORTEX_CAP_OFFLINE_CALIB`
- Return error if calibration state missing (trainable kernels cannot run without it)

### Step 4: Implement cortex_process() Using Trained State

Standard processing function, using loaded calibration state:

```c
void cortex_process(void *handle, const void *input, void *output) {
    your_kernel_runtime_t *state = (your_kernel_runtime_t *)handle;
    const float *x = (const float *)input;  // [W×C]
    float *y = (float *)output;

    const int W = state->W;
    const int C = state->C;

    // Apply trained model (e.g., ICA unmixing: y = W * x)
    for (int t = 0; t < W; t++) {
        for (int out_c = 0; out_c < C; out_c++) {
            float sum = 0.0f;
            for (int in_c = 0; in_c < C; in_c++) {
                float x_val = x[t * C + in_c];
                if (isnan(x_val)) x_val = 0.0f;  // Handle NaN

                sum += state->W_unmix[out_c * C + in_c] * x_val;
            }
            y[t * C + out_c] = sum;
        }
    }
}
```

**Same constraints as non-trainable kernels**:
- **NO** allocations (use pre-allocated `work_buffer` if needed)
- **NO** blocking I/O or syscalls
- Handle NaNs gracefully

### Step 5: Implement Calibration Oracle

Create Python calibration reference:

```python
#!/usr/bin/env python3
"""
Calibration oracle for your_kernel.
Trains model on batch data using gold-standard library (sklearn/MNE/scipy).
"""

import numpy as np
from sklearn.decomposition import FastICA  # Example

def calibrate_your_kernel(calibration_data, **params):
    """
    Train model on calibration data.

    Args:
        calibration_data: Shape (num_windows, W, C) float32 array
        params: Algorithm hyperparameters

    Returns:
        state_dict: Dictionary with trained parameters
            - 'W': Unmixing matrix [C, C]
            - 'version': State version (for evolution tracking)
    """
    num_windows, W, C = calibration_data.shape

    # 1. Concatenate windows into [num_windows*W, C]
    X = calibration_data.reshape(-1, C)

    # 2. Run batch training (example: FastICA)
    ica = FastICA(n_components=C, random_state=0, max_iter=200)
    ica.fit(X)

    # 3. Extract trained parameters
    W_unmix = ica.components_  # Shape: [C, C]

    # 4. Return state dictionary
    return {
        'W': W_unmix.astype(np.float32),
        'version': 1
    }

def apply_your_kernel(x, state):
    """
    Apply trained model to single window.

    Args:
        x: Input window, shape (W, C)
        state: State dict from calibrate_your_kernel()

    Returns:
        y: Output window, shape (W, C)
    """
    W_unmix = state['W']  # [C, C]

    # Apply unmixing: y = x @ W_unmix.T
    y = x @ W_unmix.T

    return y

def main():
    """Test calibration oracle"""
    # Generate synthetic calibration data
    num_windows, W, C = 100, 160, 64
    calibration_data = np.random.randn(num_windows, W, C).astype(np.float32)

    # Train model
    state = calibrate_your_kernel(calibration_data)

    print(f"✓ Calibration successful")
    print(f"  Windows: {num_windows}, Shape: ({W}, {C})")
    print(f"  Unmixing matrix: {state['W'].shape}")
    print(f"  State version: {state['version']}")

    # Test on single window
    x_test = np.random.randn(W, C).astype(np.float32)
    y_test = apply_your_kernel(x_test, state)

    assert y_test.shape == (W, C)
    print(f"✓ Inference test passed: ({W}, {C}) → {y_test.shape}")

if __name__ == "__main__":
    main()
```

### Step 6: Update spec.yaml

Add calibration requirements:

```yaml
kernel:
  name: "your_kernel"
  version: "v1"
  dtype: "float32"
  description: "Brief description"
  trainable: true  # NEW: Indicates calibration required

abi:
  version: 3  # Requires ABI v3
  capabilities:
    - offline_calibration  # Uses cortex_calibrate()
  input_shape:
    window_length: 160
    channels: 64
  output_shape:
    window_length: 160
    channels: 64
  stateful: false  # Trainable kernels can be stateless at runtime

calibration:  # NEW section
  min_windows: 100        # Minimum calibration data
  recommended_windows: 500
  max_duration_sec: 300   # 5 minutes typical

numerical:
  tolerance:
    rtol: 1.0e-4  # Looser for iterative algorithms
    atol: 1.0e-5

oracle:
  calibrate_function: "calibrate_your_kernel"
  apply_function: "apply_your_kernel"
  path: "oracle.py"
  dependencies: ["numpy", "scipy", "sklearn"]
```

### Step 7: CLI Calibration Workflow

Users interact with trainable kernels via CLI:

```bash
# 1. Calibrate kernel on dataset
cortex calibrate \
  --kernel your_kernel \
  --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R01.float32 \
  --windows 500 \
  --output your_kernel_S001.cortex_state

# Output:
# [harness] Loading kernel: your_kernel
# [harness] Calibration data: 500 windows (160 samples × 64 channels)
# [your_kernel] Running FastICA (max_iter=200)...
# [your_kernel] Converged in 127 iterations
# [harness] Calibration state: 16388 bytes
# [harness] Saved: your_kernel_S001.cortex_state
# ✓ Calibration complete

# 2. Run benchmarks with calibrated state
cortex run \
  --kernel your_kernel \
  --calibration-state your_kernel_S001.cortex_state \
  --config primitives/configs/cortex.yaml

# 3. Validate against oracle
cortex validate \
  --kernel your_kernel \
  --calibration-state your_kernel_S001.cortex_state \
  --verbose
```

**State file format** (`.cortex_state`):
```
Offset  Size  Field
------  ----  -----
0x00    4     Magic number (0x434F5254 = "CORT")
0x04    4     ABI version (3)
0x08    4     State version (kernel-specific)
0x0C    4     State size (bytes, excluding header)
0x10    N     Calibration state (kernel-specific binary)
```

Harness automatically handles header; kernel only sees state payload.

### Step 8: Update README.md

Document calibration workflow:

````markdown
# Your Kernel (Trainable)

## Overview

[Description emphasizing batch training requirement]

**Calibration**: This kernel requires offline batch training before inference. See Calibration Workflow below.

## Signal Model

[Standard signal model documentation]

## Calibration Workflow

### Step 1: Prepare Calibration Data

```bash
# Use sufficient data (recommended: 500+ windows)
CALIB_DATA="primitives/datasets/v1/physionet-motor-imagery/converted/S001R01.float32"
```

### Step 2: Run Calibration

```bash
cortex calibrate \
  --kernel your_kernel \
  --dataset $CALIB_DATA \
  --windows 500 \
  --output your_kernel_trained.cortex_state
```

### Step 3: Benchmark or Validate

```bash
# Benchmark
cortex run --kernel your_kernel --calibration-state your_kernel_trained.cortex_state

# Validate against oracle
cortex validate --kernel your_kernel --calibration-state your_kernel_trained.cortex_state
```

## Calibration State Format

Binary layout (little-endian):
- Bytes 0-3: C (uint32_t) - number of channels
- Bytes 4+: W (C×C float32) - unmixing matrix, row-major

Version: 1 (increment if format changes)

## Training Algorithm

[Describe batch training method: FastICA, CSP eigendecomposition, LDA fit, etc.]

Convergence criteria: [...]
Typical iterations: [...]

## Edge Cases

- **Insufficient calibration data**: Returns error if < 100 windows
- **Singular matrix**: [How does algorithm handle non-invertible cases?]
- **Missing calibration state**: cortex_init() fails with clear error message

## Acceptance Criteria

- Calibration completes without errors on 500 windows
- Float32 vs oracle within rtol=1e-4, atol=1e-5 (after same calibration data)
- State file loads correctly across runs

## Real-time Budget

- **Calibration time**: [Expected training duration]
- **Inference latency**: [Per-window processing time]
- **Memory footprint**: [State size + runtime buffers]

## ABI v3 Compatibility

- Exports: `cortex_calibrate()`, `cortex_init()`, `cortex_process()`, `cortex_teardown()`
- Capabilities: `CORTEX_CAP_OFFLINE_CALIB`
- Requires: ABI v3 harness (backward incompatible with v2)
````

### Step 9: Testing Trainable Kernels

Additional test coverage needed:

```bash
# 1. Test calibration oracle
python oracle.py
# Should output: ✓ Calibration successful

# 2. Calibrate C kernel
cortex calibrate --kernel your_kernel --dataset test_data.float32 --windows 100

# 3. Validate C vs oracle (using SAME calibration data)
cortex validate --kernel your_kernel --calibration-state your_kernel.cortex_state

# 4. Test missing calibration state (should fail gracefully)
cortex run --kernel your_kernel  # No --calibration-state
# Expected: ERROR: Calibration state required but not provided

# 5. Test state file portability (save on one machine, load on another)
scp your_kernel.cortex_state remote:~/
ssh remote "cortex run --kernel your_kernel --calibration-state your_kernel.cortex_state"
```

### Step 10: Backward Compatibility Notes

**v2 kernels with v3 harness**: ✅ Fully supported
- Harness detects missing `cortex_calibrate()` symbol via `dlsym()`
- `capabilities = 0` indicates no calibration needed

**v3 trainable kernels with v2 harness**: ❌ Not supported
- v2 harness doesn't know how to call `cortex_calibrate()`
- v2 harness cannot pass `calibration_state` to `cortex_init()`
- Error: "ABI version mismatch"

**Recommendation**: Document minimum harness version in kernel README.

### Trainable Kernel Checklist

Before submitting:

- [ ] `cortex_calibrate()` implemented and deterministic
- [ ] `cortex_init()` checks for calibration_state != NULL
- [ ] `capabilities = CORTEX_CAP_OFFLINE_CALIB` set in init result
- [ ] State serialization format documented in README.md
- [ ] Python calibration oracle implemented and tested
- [ ] spec.yaml includes `trainable: true` and calibration section
- [ ] CLI calibration workflow tested end-to-end
- [ ] Validation passes with same calibration data for C and oracle
- [ ] Handles missing calibration state gracefully (clear error message)
- [ ] State file loads correctly across multiple runs

### Common Pitfalls (Trainable Kernels)

**1. Non-deterministic calibration**
```c
// WRONG: Random seed not fixed
srand(time(NULL));  // Different results each run

// CORRECT: Fixed seed for reproducibility
srand(12345);  // Or use deterministic algorithm (eigendecomposition)
```

**2. Forgetting to free calibration state**
```c
// WRONG: Kernel frees state returned by cortex_calibrate()
free(result.calibration_state);  // Harness owns this memory!

// CORRECT: Return state, harness will free it
return result;  // Harness handles cleanup
```

**3. Calibration data shape mismatch**
```c
// Data is [num_windows, W, C] NOT [num_windows, C, W]
const float *data = (const float *)calibration_data;
for (int w = 0; w < num_windows; w++) {
    for (int t = 0; t < W; t++) {
        for (int c = 0; c < C; c++) {
            int idx = w * (W * C) + t * C + c;  // Correct indexing
            // ...
        }
    }
}
```

**4. Missing capability flag**
```c
// WRONG: Forgot to set capabilities
return (cortex_init_result_t){state, W, C, 0};

// CORRECT: Advertise calibration support
return (cortex_init_result_t){state, W, C, CORTEX_CAP_OFFLINE_CALIB};
```

## File Checklist

After completing all steps, your kernel directory should contain:

```
primitives/kernels/v1/your_kernel@f32/
├── spec.yaml                 # Machine-readable specification
├── README.md                 # Full documentation
├── oracle.py                 # Python reference (executable)
├── your_kernel.c             # C implementation
├── Makefile                  # Build script
├── your_kernel.o             # Compiled object (generated)
└── libyour_kernel.dylib/.so  # Plugin library (generated)
```

## Common Pitfalls

### 1. Memory Allocations in process()
**Don't do this**:
```c
void cortex_process(void *handle, const void *input, void *output) {
    float *temp = malloc(1000 * sizeof(float));  // WRONG!
    // ...
}
```

**Do this instead**:
```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    state->temp = malloc(1000 * sizeof(float));  // Allocate once
    // ...
}

void cortex_process(void *handle, const void *input, void *output) {
    // Use pre-allocated state->temp
}
```

### 2. Forgetting NaN Handling
**Crashes or incorrect results**:
```c
y[idx] = x[idx] * 2.0f;  // NaN propagates
```

**Graceful handling**:
```c
if (isnan(x[idx])) {
    y[idx] = 0.0f;
    continue;
}
y[idx] = x[idx] * 2.0f;
```

### 3. ABI Version Mismatch
Always check version in `cortex_init()`:
```c
if (config->abi_version != CORTEX_ABI_VERSION) {
    return (cortex_init_result_t){NULL, 0, 0};
}
```

### 4. Incorrect Output Dimensions
Return actual output shape, not input shape if they differ:
```c
// Bandpower: 64 channels → 2 frequency bands
return (cortex_init_result_t){
    .handle = state,
    .output_window_length = state->W,
    .output_channels = 2  // Not state->C!
};
```

## Testing Checklist

Before submitting your kernel:

- [ ] `make` builds without warnings
- [ ] `python oracle.py` runs successfully
- [ ] `cortex validate --kernel {name}` passes
- [ ] `cortex run --kernel {name} --duration 30` completes
- [ ] Median latency < 500 ms (EEG real-time deadline)
- [ ] No deadline misses under normal load
- [ ] Handles NaN inputs gracefully
- [ ] Output shape matches spec.yaml
- [ ] README.md documents all edge cases
- [ ] spec.yaml tolerances validated

## Next Steps

- Read complete ABI spec: [plugin-interface.md](../reference/plugin-interface.md)
- Study existing kernels: `primitives/kernels/v1/notch_iir@f32/`, `primitives/kernels/v1/bandpass_fir@f32/`
- Platform-specific builds: [platform-compatibility.md](../architecture/platform-compatibility.md)

## Example Kernels

Good reference implementations:

**Stateless/Stateful (ABI v2/v3 compatible)**:
- **Simple (stateless)**: `primitives/kernels/v1/car@f32/` - Common Average Reference
- **IIR (stateful)**: `primitives/kernels/v1/notch_iir@f32/` - Biquad filter
- **FIR (stateful)**: `primitives/kernels/v1/bandpass_fir@f32/` - Bandpass filter
- **Frequency domain**: `primitives/kernels/v1/goertzel@f32/` - Bandpower extraction

**Trainable (ABI v3 only)**:
- **ICA (artifact removal)**: `primitives/kernels/v1/ica@f32/` - FastICA with calibration workflow

## Getting Help

- **Common issues**: [troubleshooting.md](troubleshooting.md)
- **Build problems**: [platform-compatibility.md](../architecture/platform-compatibility.md)
- **API questions**: [plugin-interface.md](../reference/plugin-interface.md)
- **GitHub Discussions**: For kernel design questions
- **CONTRIBUTING.md**: For PR process
