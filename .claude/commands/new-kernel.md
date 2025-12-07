Create a new CORTEX kernel plugin with proper ABI v2 scaffolding.

## Instructions

Ask the user for:
1. **Kernel name** (lowercase, underscores for multi-word, e.g., "kalman_filter")
2. **Data type** (default: f32)
3. **Brief description** (one sentence describing what the kernel does)

Then create the following structure:

### Directory Structure

```
primitives/kernels/v1/{name}@{dtype}/
├── {name}.c          # Kernel implementation
├── Makefile         # Cross-platform build
├── spec.yaml        # Kernel metadata
├── oracle.py        # Python reference implementation
├── README.md        # Kernel documentation
└── test_{name}.c    # Unit tests (optional)
```

### File Templates

#### {name}.c (Kernel Implementation)

```c
/*
 * {Description}
 * ABI Version: 2
 * Data Type: {dtype}
 */

#include "cortex_plugin.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>

#define CORTEX_ABI_VERSION 2u

/* Kernel state structure */
typedef struct {
    uint32_t channels;
    uint32_t window_length;
    uint32_t hop_samples;
    /* TODO: Add kernel-specific state fields */
} {name}_state_t;

/* Initialize kernel */
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    /* Validate ABI */
    if (!config) return result;
    if (config->abi_version != CORTEX_ABI_VERSION) return result;
    if (config->struct_size < sizeof(cortex_plugin_config_t)) return result;

    /* Validate dtype */
    if (config->dtype != CORTEX_DTYPE_FLOAT32) return result;

    /* Allocate state */
    {name}_state_t *st = ({name}_state_t *)calloc(1, sizeof({name}_state_t));
    if (!st) return result;

    /* Store configuration */
    st->channels      = config->channels;
    st->window_length = config->window_length_samples;
    st->hop_samples   = config->hop_samples;

    /* TODO: Parse kernel parameters if provided */
    /* const cortex_params_t *params = (const cortex_params_t *)config->kernel_params; */
    /* double my_param = cortex_param_float(params, "my_param", 1.0); */

    /* TODO: Initialize kernel-specific state */

    /* Set output shape */
    result.handle                           = st;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels              = config->channels;

    return result;
}

/* Process one window */
void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    {name}_state_t *st = ({name}_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    const uint32_t W = st->window_length;
    const uint32_t C = st->channels;

    /* TODO: Implement kernel algorithm */
    /* Example: copy input to output (identity function) */
    memcpy(out, in, W * C * sizeof(float));
}

/* Clean up resources */
void cortex_teardown(void *handle) {
    if (handle) {
        free(handle);
    }
}
```

#### Makefile

```makefile
# Makefile for {name}@{dtype} kernel plugin

CC = cc
CFLAGS = -Wall -Wextra -O2 -g -fPIC -I../../../../src/engine/include -I../../../../src/engine/params
PARAMS_LIB = ../../../../src/engine/params/libcortex_params.a

# Platform detection
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SOFLAG = -dynamiclib
    LIBEXT = dylib
else
    SOFLAG = -shared
    LIBEXT = so
endif

PLUGIN_LIB = lib{name}.$(LIBEXT)
PLUGIN_SRC = {name}.c
PLUGIN_OBJ = {name}.o

all: $(PLUGIN_LIB)

$(PLUGIN_LIB): $(PLUGIN_OBJ) $(PARAMS_LIB)
	$(CC) $(SOFLAG) -o $@ $(PLUGIN_OBJ) $(PARAMS_LIB) -lm

$(PLUGIN_OBJ): $(PLUGIN_SRC)
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -f $(PLUGIN_OBJ) $(PLUGIN_LIB)

.PHONY: all clean
```

#### spec.yaml

```yaml
name: "{name}"
version: "1.0.0"
abi_version: 2
dtype: float32
description: "{Description}"

input_shape:
  - W  # window length (e.g., 160 samples)
  - C  # channels (e.g., 64)

output_shape:
  - W  # TODO: Update if output shape differs
  - C  # TODO: Update if output shape differs

parameters:
  # TODO: Document kernel parameters
  # Example:
  # - name: cutoff_hz
  #   type: float
  #   default: 30.0
  #   description: "Cutoff frequency in Hz"

tags:
  - signal-processing
  # TODO: Add relevant tags (e.g., filtering, feature-extraction, etc.)

references:
  # TODO: Add citations for algorithms used
  # Example:
  # - "Smith, J. O. (2007). Introduction to Digital Filters"
```

#### oracle.py

```python
#!/usr/bin/env python3
"""
Python oracle implementation for {name}@{dtype}

This reference implementation must match the C kernel output within
numerical tolerance (1e-5 for float32).
"""

import numpy as np
import argparse

def {name}_oracle(input_data, sample_rate_hz=160, **params):
    """
    {Description}

    Args:
        input_data: Input array of shape (W, C) - float32
        sample_rate_hz: Sample rate in Hz
        **params: Kernel parameters (if any)

    Returns:
        Output array of shape (W, C) - float32
    """
    W, C = input_data.shape

    # TODO: Implement reference algorithm using NumPy/SciPy
    # Example: identity function
    output_data = input_data.copy()

    return output_data.astype(np.float32)

def main():
    parser = argparse.ArgumentParser(description='{name} oracle')
    parser.add_argument('--input', required=True, help='Input .float32 file (W*C elements)')
    parser.add_argument('--output', required=True, help='Output .float32 file')
    parser.add_argument('--channels', type=int, default=64, help='Number of channels')
    parser.add_argument('--sample-rate', type=float, default=160.0, help='Sample rate (Hz)')
    # TODO: Add kernel-specific parameters

    args = parser.parse_args()

    # Load input
    input_flat = np.fromfile(args.input, dtype=np.float32)
    W = len(input_flat) // args.channels
    input_data = input_flat.reshape(W, args.channels)

    # Process
    output_data = {name}_oracle(input_data, sample_rate_hz=args.sample_rate)

    # Save output
    output_data.flatten().tofile(args.output)
    print(f"Processed {W} samples × {args.channels} channels")

if __name__ == '__main__':
    main()
```

#### README.md

```markdown
# {name}@{dtype}

{Description}

## Overview

TODO: Provide detailed description of the algorithm and its use in BCI signal processing.

## Parameters

TODO: Document all configurable parameters (if any).

## Algorithm

TODO: Describe the mathematical formulation and implementation details.

## References

TODO: Add citations for papers/books describing the algorithm.

## Performance

TODO: After benchmarking, document typical latency (P50, P95, P99) for standard configurations.
```

### After Creation

1. Build the kernel:
   ```bash
   cd primitives/kernels/v1/{name}@{dtype}
   make
   ```

2. Add to cortex.yaml:
   ```yaml
   plugins:
     - name: "{name}"
       status: ready
       spec_uri: "primitives/kernels/v1/{name}@{dtype}"
       spec_version: "1.0.0"
   ```

3. Implement oracle validation:
   - Complete oracle.py with reference implementation
   - Run `cortex validate --kernel {name}`

4. Complete TODOs in all files

## Sacred Constraints Checklist

Before finalizing:
- ✅ Exactly 3 ABI functions: `cortex_init`, `cortex_process`, `cortex_teardown`
- ✅ ABI version check in `cortex_init`
- ✅ No heap allocation in `cortex_process`
- ✅ No external dependencies during process
- ✅ State allocation only in `cortex_init`
- ✅ Oracle validation passes before benchmarking
