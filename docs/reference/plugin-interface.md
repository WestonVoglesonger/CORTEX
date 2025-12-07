# Plugin Interface (C ABI)

This document describes the **CORTEX kernel plugin interface** and how run-time
configuration is passed from the harness to each plugin. It is intended for
developers implementing kernels such as **Common Average Reference (CAR)**,
**Notch IIR filters**, **FIR band-pass filters**, **Goertzel bandpower**, and
future extensions. The goal is to standardize how kernels plug into the harness
so that timing, memory, and energy can be measured fairly across
implementations.

---

## Design Principles

The ABI is designed with these properties:

- **Simple & deterministic**  
  A kernel exposes only three primary functions:  
  `init()`, `process()`, and `teardown()` — plus a metadata accessor.  
  No allocations or blocking calls are allowed inside `process()`.  
  All state must be allocated in `init()` and released in `teardown()`.

- **Forward compatibility**  
  The first two fields of the init struct contain an **ABI version** and
  **struct size**. New fields can be appended without breaking existing plugins.
  Plugins should ignore unknown trailing bytes if `struct_size` is honored.

- **Modality agnostic**
  While current kernel implementations target EEG parameters (Fs=160 Hz, W=160 samples, H=80, C=64), the ABI
  supports arbitrary sample rates, window sizes, and channel counts. Plugins
  never see YAML or file paths — only numeric runtime parameters.

- **Quantization aware**  
  Plugins advertise which numeric formats they support (`float32` today, `Q15`
  and `Q7` in future). The harness requests a specific dtype via the init
  struct. Plugins must reject unsupported types.

- **Discoverable**  
  Plugins expose a metadata accessor so the harness can query capabilities
  (name, version, supported dtypes, shapes, memory requirements) without
  instantiating them.

---

## System Context

CORTEX plugins are dynamically loaded by the harness and process windowed EEG data. Each plugin implements four functions (`cortex_get_info()`, `cortex_init()`, `cortex_process()`, `cortex_teardown()`) and receives runtime configuration through structs—never YAML or file paths. The harness handles all dataset streaming, scheduling, deadline enforcement, and telemetry collection.

For details on how the harness, replayer, scheduler, and analysis pipeline interact, see [Architecture Overview](../architecture/overview.md).

---

## `cortex_plugin_config_t`

The harness fills this struct before `init()`:

| Field                | Type       | Description |
|-----------------------|-----------|-------------|
| `abi_version`        | uint32_t  | Must equal `CORTEX_ABI_VERSION`. Reject if mismatched. |
| `struct_size`        | uint32_t  | Size in bytes. Prevents reading past known fields. |
| `sample_rate_hz`     | uint32_t  | Input sampling rate Fs (Hz). Default = 160 for current EEG kernels. |
| `window_length_samples` | uint32_t | Window length W (samples). Default = 160. |
| `hop_samples`        | uint32_t  | Hop length H (samples). Default = 80. |
| `channels`           | uint32_t  | Input channels C. Default = 64. Must equal dataset.channels. |
| `dtype`              | uint32_t  | Requested dtype: one of `CORTEX_DTYPE_FLOAT32`, `_Q15`, `_Q7`. |
| `allow_in_place`     | uint8_t   | 1 = process may overwrite input buffer. |
| `kernel_params`      | void*     | Pointer to plugin-specific params struct (from YAML `plugins[*].params`). |
| `kernel_params_size` | uint32_t  | Size of that struct. |
| `reserved0`          | 3×uint8_t | Reserved for alignment/future flags. |

### YAML → Struct Mapping

- `dataset.sample_rate_hz` → `sample_rate_hz`  
- `plugins[*].runtime.window_length_samples` → `window_length_samples`  
- `plugins[*].runtime.hop_samples` → `hop_samples`  
- `plugins[*].runtime.channels` → `channels`  
- `plugins[*].runtime.dtype` → `dtype`  
- `plugins[*].runtime.allow_in_place` → `allow_in_place`  
- `plugins[*].params` → serialized string passed to `kernel_params`

  ✅ **Fully Implemented**: Harness passes YAML params as string to `kernel_params`.
  Kernels extract values using the accessor API (see example below).

### Extracting Runtime Parameters

Kernels use the **parameter accessor API** to extract runtime configuration from the `kernel_params` string:

```c
#include "cortex_plugin.h"
#include "accessor.h"  // Parameter accessor functions

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // ... ABI validation ...

    // Extract parameters with typed accessors and defaults
    const char *params = (const char *)config->kernel_params;
    double f0_hz = cortex_param_float(params, "f0_hz", 60.0);    // default: 60.0
    int order = cortex_param_int(params, "order", 4);             // default: 4

    char window[32];
    cortex_param_string(params, "window", window, sizeof(window), "hann");  // default: "hann"

    bool normalize = cortex_param_bool(params, "normalize", true);  // default: true

    // Validate extracted parameters
    if (f0_hz <= 0.0 || f0_hz >= config->sample_rate_hz / 2.0) {
        fprintf(stderr, "[kernel] error: f0_hz must be in (0, Nyquist)\n");
        return (cortex_init_result_t){0};
    }

    // Use parameters to configure kernel behavior...
    // compute_filter_coefficients(f0_hz, order);

    return result;
}
```

**Accessor Functions** (defined in `src/engine/params/accessor.h`):
- `double cortex_param_float(const char *params, const char *key, double default_val)`
- `long cortex_param_int(const char *params, const char *key, long default_val)`
- `void cortex_param_string(const char *params, const char *key, char *out_buf, size_t buf_size, const char *default_val)`
- `bool cortex_param_bool(const char *params, const char *key, bool default_val)`

**Supported Formats**:
- YAML-style: `"f0_hz: 60.0, Q: 30.0"`
- URL-style: `"f0_hz=60.0&Q=30.0"`

See `src/engine/params/README.md` for complete API documentation and examples  

---

## `cortex_plugin_info_t`

Returned by `cortex_get_info()` before instantiation:

| Field      | Type       | Description |
|------------|-----------|-------------|
| `name`     | const char* | Short identifier (e.g., `"car"`) |
| `description` | const char* | Human-readable description |
| `version`  | const char* | Semantic version string |
| `supported_dtypes` | uint32_t | Bitmask of supported types |
| `input_window_length_samples` | uint32_t | Expected input W |
| `input_channels` | uint32_t | Expected input C |
| `output_window_length_samples` | uint32_t | Output window length |
| `output_channels` | uint32_t | Output channels |
| `state_bytes` | uint32_t | Persistent state memory |
| `workspace_bytes` | uint32_t | Scratch memory per `process()` |
| `reserved` | void*[] | Reserved for extensions |

Harness uses this to validate compatibility before calling `init()`.

---

## Function Contracts

### `cortex_get_info()`
```c
cortex_plugin_info_t cortex_get_info(void);
```

* Returns metadata struct.
* Must not allocate memory.
* Pointers must remain valid for library lifetime.

### `cortex_init()`

```c
void* cortex_init(const cortex_plugin_config_t* config);
```

* Validates `abi_version` and `struct_size`.
* Allocates persistent state (`state_bytes`).
* Copies/references `kernel_params`.
* Returns handle or NULL on error.

### `cortex_process()`

```c
void cortex_process(void* handle, const void* input, void* output);
```

* Processes one window of size W×C.
* Must not allocate memory, perform I/O, or block.
* Supports in-place if `allow_in_place=1`.
* Harness logs latency, jitter, deadline misses.

### `cortex_teardown()`

```c
void cortex_teardown(void* handle);
```

* Frees resources allocated in `init()`.
* Must be idempotent and safe.

---

## Guidelines for Plugin Authors

* **Language & linkage**: Implement in C or C++, export with `extern "C"`.
* **Numerical stability**: Follow tolerances in each kernel's `spec.yaml` file. Use float32 by default; quantised versions must saturate and round correctly.
* **State management**: Store persistent state in memory allocated in `init()`.
* **Thread safety**: No concurrent calls to `process()` on same handle; multiple instances may run in parallel.
* **Error handling**: Return NULL from `init()` if unsupported. Handle NaNs gracefully.
* **Versioning**: Update plugin’s version string when behaviour changes. ABI version changes only when struct or function signatures change.

---

## Default EEG Parameters

From the project proposal and implementation plan (used by current kernel implementations):

* **Sample rate (Fs):** 160 Hz
* **Window length (W):** 160 samples (1 s)
* **Hop (H):** 80 samples (50% overlap)
* **Channels (C):** 64
* **Deadline:** H/Fs = 0.5 s

---

## Platform-Specific Plugin Development

### Library Extensions

Plugins must be built with the correct extension for each platform:

- **macOS**: `lib<name>.dylib`
- **Linux**: `lib<name>.so`

The harness loader automatically detects the platform and searches for the appropriate extension.

### Build Flags

**macOS**:
```makefile
$(CC) $(CFLAGS) -dynamiclib -o libmyplugin.dylib myplugin.c
```

**Linux**:
```makefile
$(CC) $(CFLAGS) -shared -fPIC -o libmyplugin.so myplugin.c
```

### Cross-Platform Makefile Example

```makefile
CC = cc
CFLAGS = -Wall -Wextra -O2 -g -fPIC -I../include

# Detect platform
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
	$(CC) $(CFLAGS) $(SOFLAG) -o $@ $<
```

### Loading Behavior

The harness uses `dlopen()` to load plugins:

- Searches `plugins/` directory relative to harness binary
- Automatically uses correct extension for platform
- No code changes needed in plugin implementation
- ABI is platform-independent (same `cortex_plugin.h` on all platforms)

### Testing Plugins

```bash
# macOS
./cortex run primitives/configs/example.yaml
# Looks for plugins/lib<name>.dylib

# Linux
./cortex run primitives/configs/example.yaml
# Looks for plugins/lib<name>.so
```

See `docs/architecture/platform-compatibility.md` for comprehensive platform documentation.

## References

* Implementation Plan, Weeks 1–2: specification and setup, plugin ABI definition.
* Final Project Proposal: pipeline description and ABI summary.

---
