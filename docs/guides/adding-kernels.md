# Adding New Kernels to CORTEX

This guide walks through the complete process of adding a new signal processing kernel to CORTEX, from specification to validation.

## Overview

A kernel in CORTEX is a signal processing algorithm (like filtering, feature extraction, or transformation) that operates on windowed EEG data. Each kernel is implemented as a dynamic plugin that the harness loads at runtime.

**Time estimate**: 4-8 hours for a simple kernel (like CAR or notch filter)

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

**Note**: Parameters currently hardcoded in C implementation (kernel_params not yet wired).

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
    spec_version: "1.0.0"
    runtime:
      window_length_samples: 160
      hop_samples: 80
      channels: 64
      dtype: "float32"
    params: {}  # Currently not supported
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
    
    // 4. Store configuration
    state->W = config->window_length_samples;
    state->C = config->channels;
    
    // 5. Pre-allocate any working buffers
    // state->buffer = malloc(state->W * sizeof(float));
    // if (!state->buffer) {
    //     free(state);
    //     return (cortex_init_result_t){NULL, 0, 0};
    // }
    
    // 6. Initialize algorithm-specific state (coefficients, delays, etc.)
    // ...
    
    // 7. Return handle and output dimensions
    return (cortex_init_result_t){
        .handle = state,
        .output_window_length = state->W,  // Adjust if output differs
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
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../../../../src/engine/include -fPIC
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

$(TARGET): $(OBJ)
	$(CC) $(SOFLAG) -o $@ $^ $(LDFLAGS)

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
    spec_version: "1.0.0"
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

- **Simple (stateless)**: `primitives/kernels/v1/car@f32/` - Common Average Reference
- **IIR (stateful)**: `primitives/kernels/v1/notch_iir@f32/` - Biquad filter
- **FIR (stateful)**: `primitives/kernels/v1/bandpass_fir@f32/` - Bandpass filter
- **Frequency domain**: `primitives/kernels/v1/goertzel@f32/` - Bandpower extraction

## Getting Help

- **Common issues**: [troubleshooting.md](troubleshooting.md)
- **Build problems**: [platform-compatibility.md](../architecture/platform-compatibility.md)
- **API questions**: [plugin-interface.md](../reference/plugin-interface.md)
- **GitHub Discussions**: For kernel design questions
- **CONTRIBUTING.md**: For PR process
