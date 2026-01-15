# CORTEX SDK

Software Development Kit for building and integrating CORTEX BCI signal processing kernels.

## Overview

The CORTEX SDK provides the complete development environment for creating, validating, and deploying real-time BCI signal processing algorithms. It consists of a unified library, development tools, and comprehensive API headers.

**Key Components:**
- **Kernel Library** (`libcortex.a`) - Plugin loader, state I/O, parameter parsing
- **Development Tools** - Calibration and validation utilities
- **Public API Headers** - Plugin ABI, loader, state management, parameters

## Directory Structure

```
sdk/
├── README.md              # This file
├── Makefile               # Top-level SDK builder
└── kernel/                # Kernel SDK subsystem
    ├── README.md          # Kernel SDK documentation
    ├── include/           # Public API headers
    │   ├── README.md      # API reference
    │   ├── cortex_plugin.h       # Plugin ABI v3 (core interface)
    │   ├── cortex_loader.h       # Plugin loader utilities
    │   ├── cortex_state_io.h     # Calibration state serialization
    │   └── cortex_params.h       # Runtime parameter accessors
    ├── lib/               # SDK library implementation
    │   ├── Makefile       # Builds libcortex.a
    │   ├── loader/        # Dynamic plugin loading (dlopen/dlsym)
    │   ├── state_io/      # Binary state file serialization
    │   └── params/        # YAML/URL-style parameter parsing
    └── tools/             # Development tools
        ├── README.md      # Tools documentation
        ├── Makefile       # Builds calibrate & validate
        ├── calibrate.c    # Kernel training tool
        └── validate.c     # Oracle validation tool
```

## Quick Start

### Building the SDK

```bash
# Build SDK library and tools
make -C sdk

# Or from project root
make sdk

# Verify build
ls -lh sdk/kernel/lib/libcortex.a           # SDK library (11KB)
ls -lh sdk/kernel/tools/cortex_calibrate    # Training tool (50KB)
ls -lh sdk/kernel/tools/cortex_validate     # Validation tool (35KB)
```

### Using the SDK in Your Kernel

**1. Include SDK headers:**
```c
#include "cortex_plugin.h"      // Required: Plugin ABI v3
#include "cortex_params.h"      // Optional: Runtime parameters
#include "cortex_state_io.h"    // Optional: Calibration state (trainable kernels)
```

**2. Update your Makefile:**
```makefile
CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I../../../../sdk/kernel/include -fPIC

# Platform-specific linking
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

# Build plugin
KERNEL_NAME = your_kernel
PLUGIN_LIB = lib$(KERNEL_NAME)$(LIBEXT)

all: $(PLUGIN_LIB)

$(PLUGIN_LIB): $(KERNEL_NAME).o
	$(CC) $(SOFLAG) -o $@ $< $(LDFLAGS)
```

**3. Build your kernel:**
```bash
cd primitives/kernels/v1/your_kernel@f32
make
```

## SDK Components

### Library: libcortex.a

Single unified library combining all SDK functionality:

| Component | Purpose | Source |
|-----------|---------|--------|
| **Plugin Loader** | Dynamic loading via dlopen/dlsym, ABI detection | `lib/loader/` |
| **State I/O** | Binary serialization for calibration states | `lib/state_io/` |
| **Parameter Parser** | Runtime config parsing (YAML/URL-style) | `lib/params/` |

**Link against it:**
```makefile
LDFLAGS = -L/path/to/sdk/kernel/lib -lcortex
```

### Tools

| Tool | Purpose | Usage |
|------|---------|-------|
| **cortex_calibrate** | Train trainable kernels (ICA, CSP) | `cortex calibrate --kernel ica --dataset data.float32 --output state.cortex_state` |
| **cortex_validate** | Validate kernels against Python oracles | `cortex validate --kernel notch_iir --verbose` |

See [`tools/README.md`](kernel/tools/README.md) for complete documentation.

### API Headers

| Header | Purpose | Documentation |
|--------|---------|---------------|
| **cortex_plugin.h** | Plugin ABI v3 (init/process/teardown/calibrate) | [`include/README.md`](kernel/include/README.md#cortex_pluginh) |
| **cortex_loader.h** | Plugin loading, API type definitions | [`include/README.md`](kernel/include/README.md#cortex_loaderh) |
| **cortex_state_io.h** | State save/load for trainable kernels | [`include/README.md`](kernel/include/README.md#cortex_state_ioh) |
| **cortex_params.h** | Type-safe runtime parameter accessors | [`include/README.md`](kernel/include/README.md#cortex_paramsh) |

## Usage Examples

### Stateless/Stateful Kernels (ABI v2/v3)

```c
#include "cortex_plugin.h"
#include "cortex_params.h"

typedef struct {
    uint32_t channels;
    double param1;
    // ...
} kernel_state_t;

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    // Parse runtime parameters
    const char *params = (const char *)config->kernel_params;
    double param1 = cortex_param_float(params, "param1", 1.0);  // default: 1.0

    // Allocate state
    kernel_state_t *state = calloc(1, sizeof(kernel_state_t));
    state->channels = config->channels;
    state->param1 = param1;

    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;
    return result;
}

void cortex_process(void *handle, const void *input, void *output) {
    kernel_state_t *s = (kernel_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    // Process window...
}

void cortex_teardown(void *handle) {
    free(handle);
}
```

### Trainable Kernels (ABI v3)

```c
#include "cortex_plugin.h"
#include "cortex_state_io.h"

// Implement offline calibration
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
) {
    cortex_calibration_result_t result = {0};

    // Train model on batch data...
    float *trained_weights = train_model(calibration_data, num_windows);

    // Serialize state
    cortex_state_save("model.cortex_state", trained_weights, size, version);

    result.success = 1;
    return result;
}

// Load state at runtime
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    // Load pre-trained model
    void *state_payload;
    uint32_t state_size, state_version;
    cortex_state_load(config->calibration_state, &state_payload, &state_size, &state_version);

    // Initialize with loaded state...
    result.handle = state_payload;
    result.capabilities = CORTEX_CAP_OFFLINE_CALIB;
    return result;
}

// Zero-latency inference
void cortex_process(void *handle, const void *input, void *output) {
    // Apply pre-trained model (no heap allocation!)
}
```

## Platform Support

| Platform | Architecture | Compiler | Plugin Extension | Status |
|----------|--------------|----------|------------------|--------|
| macOS | arm64, x86_64 | Clang 12+ | `.dylib` | ✅ Fully supported |
| Linux | x86_64, arm64 | GCC 7+, Clang 10+ | `.so` | ✅ Fully supported |
| Embedded | ARM Cortex-M | GCC ARM | Static link | 🚧 Planned (Q2 2026) |

## Build Requirements

- C11 compiler (GCC 7+, Clang 10+, Apple Clang 12+)
- POSIX threads (`pthread`)
- Dynamic linking support (`libdl` on Linux)
- Make build system

**macOS:**
```bash
xcode-select --install
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install build-essential libdl-dev
```

## Integration Workflows

### Development Workflow

```bash
# 1. Build SDK
make sdk

# 2. Write kernel (primitives/kernels/v1/my_kernel@f32/)
#    - Implement cortex_init(), cortex_process(), cortex_teardown()
#    - Include SDK headers (#include "cortex_plugin.h")
#    - Link against libcortex.a

# 3. Build kernel
cd primitives/kernels/v1/my_kernel@f32
make

# 4. Validate kernel
sdk/kernel/tools/cortex_validate --kernel my_kernel --verbose

# 5. Integrate into harness
#    - Add kernel to primitives/configs/cortex.yaml
#    - Run: cortex pipeline
```

### Trainable Kernel Workflow (ICA, CSP)

```bash
# 1. Build SDK
make sdk

# 2. Implement cortex_calibrate() in kernel
#    - Train model on batch data
#    - Serialize state using cortex_state_save()

# 3. Calibrate kernel
sdk/kernel/tools/cortex_calibrate \
    --kernel ica \
    --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
    --windows 500 \
    --output ica_S001.cortex_state

# 4. Validate trained kernel
sdk/kernel/tools/cortex_validate \
    --kernel ica \
    --state ica_S001.cortex_state \
    --windows 10

# 5. Benchmark with harness
cortex run --kernel ica --calibration-state ica_S001.cortex_state
```

## Documentation

| Document | Description |
|----------|-------------|
| [`sdk/README.md`](README.md) | This file - SDK overview |
| [`sdk/kernel/README.md`](kernel/README.md) | Kernel SDK architecture |
| [`sdk/kernel/include/README.md`](kernel/include/README.md) | Complete API reference |
| [`sdk/kernel/tools/README.md`](kernel/tools/README.md) | Development tools guide |
| [`docs/guides/adding-kernels.md`](../docs/guides/adding-kernels.md) | Kernel development tutorial |
| [`docs/reference/plugin-interface.md`](../docs/reference/plugin-interface.md) | Plugin ABI v3 specification |

## FAQ

### Why a separate SDK directory?

Clear separation between:
- **SDK**: Development tools (headers, libraries, calibration/validation)
- **Harness**: Runtime measurement infrastructure (scheduler, telemetry, benchmarking)

This enables:
1. Embedded target support (link against SDK library only, no harness)
2. Simplified kernel development (single include path, single library)
3. Cleaner dependency management (SDK → Harness, not bidirectional)

### How do I update from old paths?

**Old (pre-SDK restructure):**
```c
#include "../../../../sdk/kernel/include/cortex_plugin.h"
#include "../../../../src/engine/params/accessor.h"
```
```makefile
CFLAGS = -I../../../../sdk/kernel/include -I../../../../src/engine/params
LDFLAGS = -L../../../../src/engine/params -lcortex_params
```

**New (SDK):**
```c
#include "cortex_plugin.h"
#include "cortex_params.h"
```
```makefile
CFLAGS = -I../../../../sdk/kernel/include
LDFLAGS = -L../../../../sdk/kernel/lib -lcortex
```

### What's in libcortex.a?

Single unified library combining:
- **loader**: Dynamic plugin loading (`cortex_plugin_load()`, `cortex_plugin_unload()`)
- **state_io**: Binary state serialization (`cortex_state_save()`, `cortex_state_load()`)
- **params**: Runtime parameter parsing (`cortex_param_float()`, `cortex_param_int()`, etc.)

Previously these were separate (`libloader.a`, `libstate_io.a`, `libcortex_params.a`). Now consolidated for simplicity.

### Are old kernels compatible?

Yes! ABI v2 kernels (without `cortex_calibrate()`) work unmodified. Just update:
1. Include paths: `../../../../sdk/kernel/include`
2. Link flags: `-L../../../../sdk/kernel/lib -lcortex`

The loader auto-detects v2 vs v3 via `dlsym("cortex_calibrate")`.

## Support

- **Issues**: https://github.com/anthropics/claude-code/issues
- **Documentation**: [`docs/`](../docs/)
- **Examples**: [`primitives/kernels/v1/`](../primitives/kernels/v1/)

## License

See project root LICENSE file.
