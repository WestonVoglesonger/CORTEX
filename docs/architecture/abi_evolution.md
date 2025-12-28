# CORTEX Plugin ABI Evolution

**Document Version**: 1.0
**Last Updated**: 2025-12-27
**Current ABI Version**: 3 (as of CORTEX v0.3.0)

---

## Overview

This document tracks the evolution of the CORTEX kernel plugin Application Binary Interface (ABI) across versions. Understanding this history is critical for:

- **Kernel authors**: Migrating existing kernels to new ABI versions
- **Harness developers**: Maintaining backward compatibility
- **Researchers**: Reproducing results across CORTEX versions

**Design Philosophy**: The ABI must remain simple and deterministic while enabling new capabilities. Breaking changes are minimized, but when necessary, version bumps provide clear migration paths.

---

## Version History Summary

| ABI Version | CORTEX Version | Date | Key Changes | Breaking? |
|-------------|----------------|------|-------------|-----------|
| v1 | 0.1.0 | Oct 2025 | Initial ABI: `get_info()` + `init()` + `process()` + `teardown()` | N/A (initial) |
| v2 | 0.2.0 | Nov 2025 | Eliminated `get_info()`, unified init/shape query | ✅ Yes |
| v3 | 0.3.0 | Dec 2025 | Added calibration support, capability flags, extended config | ✅ Yes |

---

## ABI v1 (October 2025)

### Release Context
- **CORTEX Version**: 0.1.0
- **Initial Release**: First production ABI for CORTEX kernel plugins
- **Kernels Implemented**: goertzel v1, notch_iir, fir_bandpass

### Function Signatures

```c
#define CORTEX_ABI_VERSION 1u

// Metadata query (before instantiation)
cortex_plugin_info_t cortex_get_info(void);

// Instance lifecycle
void* cortex_init(const cortex_plugin_config_t* config);
void cortex_process(void* handle, const void* input, void* output);
void cortex_teardown(void* handle);
```

### Key Structures

```c
typedef struct {
    uint32_t abi_version;           // Must be 1
    uint32_t struct_size;
    uint32_t sample_rate_hz;
    uint32_t window_length_samples;
    uint32_t hop_samples;
    uint32_t channels;
    uint32_t dtype;
    uint8_t  allow_in_place;
    uint8_t  reserved0[3];
    const void *kernel_params;
    uint32_t   kernel_params_size;
} cortex_plugin_config_t;

typedef struct {
    const char* name;
    const char* description;
    const char* version;
    uint32_t supported_dtypes;
    uint32_t input_window_length_samples;
    uint32_t input_channels;
    uint32_t output_window_length_samples;  // Static metadata
    uint32_t output_channels;               // Static metadata
    uint32_t state_bytes;
    uint32_t workspace_bytes;
    void* reserved[4];
} cortex_plugin_info_t;
```

### Design Rationale

**Two-Phase Discovery**:
1. Call `cortex_get_info()` to query capabilities (no instantiation)
2. Call `cortex_init()` to create instance

**Why This Approach?**:
- Harness could validate compatibility before allocating resources
- Kernels advertised memory requirements upfront
- Followed traditional plugin architecture patterns (e.g., VST, AU)

### Limitations Discovered

1. **Redundant Information**: Output shape in `get_info()` often didn't match actual runtime behavior
2. **Static vs. Dynamic**: Some kernels (e.g., Goertzel) have parameter-dependent output shapes
3. **Extra Complexity**: Harness code duplicated validation logic between `get_info()` and `init()`
4. **Test Bug**: Led to zero-byte buffer allocations when info struct was incorrect

---

## ABI v2 (November 2025)

### Release Context
- **CORTEX Version**: 0.2.0
- **Git Commit**: `43695c3` - "Eliminate get_info() and return output shape from init()"
- **Breaking Change**: Removed `cortex_get_info()` entirely

### Migration Summary

**Removed**:
- ❌ `cortex_get_info()` function
- ❌ `cortex_plugin_info_t` struct

**Modified**:
- ✅ `cortex_init()` now returns `cortex_init_result_t` instead of `void*`

**New**:
- ✅ `cortex_init_result_t` struct combines handle + output dimensions

### Function Signatures

```c
#define CORTEX_ABI_VERSION 2u

// Unified init (returns handle + output shape)
cortex_init_result_t cortex_init(const cortex_plugin_config_t* config);
void cortex_process(void* handle, const void* input, void* output);
void cortex_teardown(void* handle);
```

### Key Structures

```c
// Config struct: UNCHANGED from v1 (backward compatible appending)
typedef struct {
    uint32_t abi_version;           // Now = 2
    uint32_t struct_size;
    // ... (same fields as v1) ...
} cortex_plugin_config_t;

// NEW: Unified init result
typedef struct {
    void *handle;                        // Opaque instance handle (NULL on error)
    uint32_t output_window_length_samples;  // Actual output W (may differ from input)
    uint32_t output_channels;               // Actual output C (may differ from input)
} cortex_init_result_t;
```

### Design Rationale

**Why Unify Init + Shape Query?**

1. **Eliminate Redundancy**: Output shape often depends on runtime parameters (e.g., Goertzel band count)
2. **Simplify API**: 3 functions instead of 4
3. **Fix Bug**: Prevents mismatch between advertised and actual shapes
4. **Better Error Handling**: NULL handle clearly signals init failure

**Impact on Harness**:
```c
// v1 approach (two-phase)
cortex_plugin_info_t info = cortex_get_info();
if (info.output_channels != expected) { /* error */ }
void *handle = cortex_init(&config);

// v2 approach (unified)
cortex_init_result_t result = cortex_init(&config);
if (!result.handle) { /* error */ }
// Use result.output_channels directly for buffer allocation
```

### Migration Guide (v1 → v2)

**For Kernel Authors**:

```c
// OLD (v1):
void* cortex_init(const cortex_plugin_config_t *config) {
    my_state_t *state = malloc(sizeof(my_state_t));
    // ... initialize state ...
    return state;
}

// NEW (v2):
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    my_state_t *state = malloc(sizeof(my_state_t));
    // ... initialize state ...

    // Return handle + output dimensions
    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = config->window_length_samples,  // or computed value
        .output_channels = config->channels                             // or transformed value
    };
}
```

**Breaking Changes**:
- ❌ Kernels MUST update return type (compilation error if not updated)
- ❌ Harness MUST update loader to expect `cortex_init_result_t`
- ✅ Config struct unchanged (no changes to kernel parameter handling)

### Adoption
- All kernels migrated in same commit (goertzel v1/v2, notch_iir, fir_bandpass)
- Scheduler updated to use new buffer allocation logic
- Test suite updated (`test_kernel_accuracy.c`, `test_scheduler.c`)

---

## ABI v3 (December 2025)

### Release Context
- **CORTEX Version**: 0.3.0
- **Strategic Goal**: Enable calibration-based kernels (ICA, CSP, LDA, SVM)
- **Breaking Change**: Extended config struct, added calibration function

### Migration Summary

**New Functions**:
- ✅ `cortex_calibrate()` - Optional function for trainable kernels

**Extended Structures**:
- ✅ `cortex_plugin_config_t` - Appended calibration state fields (backward compatible via `struct_size`)
- ✅ `cortex_init_result_t` - Added capability flags

**New Types**:
- ✅ `cortex_calibration_result_t` - Calibration output (trained state)
- ✅ `cortex_capability_flags_t` - Kernel capability advertisement

### Function Signatures

```c
#define CORTEX_ABI_VERSION 3u

// Optional calibration (only for trainable kernels)
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
);

// Modified init (now accepts calibration state)
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
void cortex_process(void *handle, const void *input, void *output);
void cortex_teardown(void *handle);
```

### Key Structures

```c
// EXTENDED Config (backward compatible)
typedef struct {
    // v2 fields (UNCHANGED)
    uint32_t abi_version;           // Now = 3
    uint32_t struct_size;           // Larger than v2
    uint32_t sample_rate_hz;
    uint32_t window_length_samples;
    uint32_t hop_samples;
    uint32_t channels;
    uint32_t dtype;
    uint8_t  allow_in_place;
    uint8_t  reserved0[3];
    const void *kernel_params;
    uint32_t   kernel_params_size;

    // NEW v3 fields (appended)
    const void *calibration_state;   // Pre-trained state (e.g., ICA unmixing matrix)
    uint32_t calibration_state_size; // Size in bytes
} cortex_plugin_config_t;

// EXTENDED Init Result (backward compatible)
typedef struct {
    void *handle;
    uint32_t output_window_length_samples;
    uint32_t output_channels;

    // NEW v3 field (appended)
    uint32_t capabilities;  // Bitmask of cortex_capability_flags_t
} cortex_init_result_t;

// NEW: Calibration result
typedef struct {
    void *calibration_state;       // Opaque trained state (e.g., W matrix)
    uint32_t state_size_bytes;     // Size for serialization
    uint32_t state_version;        // Kernel-specific versioning
} cortex_calibration_result_t;

// NEW: Capability flags (future-proof for v4)
typedef enum {
    CORTEX_CAP_OFFLINE_CALIB  = 1 << 0,  // v3: Supports cortex_calibrate()
    CORTEX_CAP_ONLINE_ADAPT   = 1 << 1,  // v4: Per-window adaptation (future)
    CORTEX_CAP_FEEDBACK_LEARN = 1 << 2,  // v5: Reinforcement learning (future)
} cortex_capability_flags_t;
```

### Design Rationale

**Why Add Calibration?**

1. **Industry Coverage**: 60% of production BCI algorithms require training (CSP, ICA, LDA)
2. **Research Differentiation**: Enables end-to-end pipeline benchmarking (calibration → inference)
3. **Embedded Deployment**: Separates expensive calibration (host) from cheap inference (embedded)

**Why Two-Phase Model?**

```
Offline calibration:  cortex_calibrate(data) → state
Runtime inference:    cortex_init(state) → handle
                      cortex_process(handle, window) → output
```

**Advantages**:
- Calibration happens once (expensive, multi-window, iterative)
- Inference happens per-window (cheap, deterministic)
- State serialization enables cross-platform deployment (calibrate on host → deploy to STM32)

**Backward Compatibility Strategy**:

```c
// Harness detects v2 vs. v3 kernels
void* calib_fn = dlsym(plugin, "cortex_calibrate");
if (calib_fn != NULL) {
    // v3 kernel - supports calibration
    kernel->capabilities |= CORTEX_CAP_OFFLINE_CALIB;
} else {
    // v2 kernel - stateless or pre-calibrated
    kernel->capabilities = 0;
}

// v2 kernels ignore new config fields (safe via struct_size check)
if (config->struct_size >= offsetof(cortex_plugin_config_t, calibration_state)) {
    // v3 field available
} else {
    // v2 kernel - doesn't read calibration_state
}
```

### State Serialization Format

```c
// Header (16 bytes, fixed)
struct cortex_state_header {
    uint32_t magic;         // 0x434F5254 ("CORT")
    uint32_t abi_version;   // 3
    uint32_t state_version; // Kernel-specific versioning
    uint32_t data_size;     // Bytes of following data
};

// Followed by kernel-specific data (e.g., ICA unmixing matrix)
```

**File Storage**: `primitives/datasets/v{version}/{dataset}/calibration_states/{kernel}_{method}.cortex_state`

### CLI Integration

**New Command**: `cortex calibrate`
```bash
cortex calibrate \
    --kernel ica@f32 \
    --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
    --output primitives/datasets/v1/physionet-motor-imagery/calibration_states/ica_fastica.cortex_state \
    --params "method: fastica, n_components: 64"
```

**Modified YAML Config**:
```yaml
cortex_version: 1
plugins:
  - name: "ica"
    spec_uri: "primitives/kernels/v1/ica@f32"
    calibration_state: "primitives/datasets/v1/physionet-motor-imagery/calibration_states/ica_fastica.cortex_state"
```

### Migration Guide (v2 → v3)

**For v2 Kernel Authors (No Changes Required)**:

```c
// v2 kernels work unchanged with v3 harness
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // Check version (accept v3)
    if (config->abi_version < 2 || config->abi_version > 3) {
        return (cortex_init_result_t){0};  // Reject v1, accept v2 or v3
    }

    // v2 kernel ignores new v3 fields (safe via struct_size)
    // ... (no changes to implementation) ...

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = W,
        .output_channels = C,
        .capabilities = 0  // NEW v3 field: 0 = no special capabilities
    };
}
```

**For New v3 Trainable Kernels**:

```c
// Implement optional calibration function
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
) {
    // Perform batch training (e.g., FastICA on multiple windows)
    float *W_matrix = train_ica(calibration_data, num_windows, config->channels);

    return (cortex_calibration_result_t){
        .calibration_state = W_matrix,
        .state_size_bytes = config->channels * config->channels * sizeof(float),
        .state_version = 1  // Kernel-specific versioning
    };
}

// Modified init: accept calibration state
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    if (config->abi_version != 3) {
        return (cortex_init_result_t){0};
    }

    ica_state_t *state = calloc(1, sizeof(ica_state_t));

    // Load calibration state if provided
    if (config->calibration_state != NULL) {
        state->W_matrix = malloc(config->calibration_state_size);
        memcpy(state->W_matrix, config->calibration_state, config->calibration_state_size);
    } else {
        // Error: ICA requires calibration
        fprintf(stderr, "[ica] ERROR: calibration_state required\n");
        free(state);
        return (cortex_init_result_t){0};
    }

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = config->window_length_samples,
        .output_channels = config->channels,
        .capabilities = CORTEX_CAP_OFFLINE_CALIB  // Advertise calibration support
    };
}
```

**Breaking Changes**:
- ✅ v2 kernels MUST set `capabilities = 0` in `cortex_init_result_t` (compilation error if omitted)
- ✅ v3 harness MUST check for `cortex_calibrate` symbol via `dlsym()`
- ✅ Config struct size increased (v2 kernels ignore new fields safely)

### Adoption
- All 6 existing v2 kernels (car, notch_iir, bandpass_fir, goertzel, welch_psd, noop) migrated with minimal changes
- New ICA kernel serves as reference v3 implementation
- Backward compatibility tests added (`test_abi_compatibility.c`)

---

## Future Roadmap

### ABI v4 (Planned: Q1 2026)

**Goal**: Online adaptive learning

**Proposed Additions**:
```c
#define CORTEX_ABI_VERSION 4u

// NEW: Per-window adaptation
void cortex_adapt(
    void *handle,
    const void *window,
    const void *feedback  // Optional: labels, rewards, etc.
);
```

**Use Cases**:
- Adaptive ICA (online Infomax)
- Online LDA (incremental discriminant updates)
- Reinforcement learning BCIs (reward-based adaptation)

**Design Challenge**: How to validate non-deterministic algorithms?
- Tolerance-based oracle comparison
- Convergence criteria
- Reproducibility via RNG seeding

### ABI v5+ (Planned: Q2+ 2026)

**Goal**: Hybrid calibration (offline warm-start + online fine-tuning)

**Proposed Additions**:
```c
// Combine offline calibration + online adaptation
cortex_calibration_result_t cortex_calibrate(...);  // v3: Batch training
void cortex_adapt(...);                             // v4: Per-window updates
```

**Use Cases**:
- Subject-specific adaptation (calibrate on population → adapt per-subject)
- Non-stationarity tracking (pre-train → adapt to drift)
- Transfer learning (warm-start from pretrained models)

---

## Design Principles Across Versions

These principles have guided all ABI versions:

1. **Simplicity**: Minimal function count (3-4 functions)
2. **Determinism**: Reproducible results (critical for benchmarking)
3. **Forward Compatibility**: New fields appended via `struct_size` mechanism
4. **Platform Agnostic**: Same ABI on macOS, Linux, embedded
5. **Zero Allocations in Process**: Real-time safety (all allocation in `init()`)
6. **Explicit Versioning**: Kernels reject unsupported ABI versions explicitly

---

## Version Compatibility Matrix

| Kernel ABI | Harness v0.1 (ABI v1) | Harness v0.2 (ABI v2) | Harness v0.3 (ABI v3) |
|------------|----------------------|----------------------|----------------------|
| v1 kernels | ✅ Compatible        | ❌ Incompatible      | ❌ Incompatible      |
| v2 kernels | ❌ Incompatible      | ✅ Compatible        | ✅ Compatible        |
| v3 kernels | ❌ Incompatible      | ❌ Incompatible      | ✅ Compatible        |

**Note**: v2 kernels work with v3 harness via backward compatibility mechanism (missing `cortex_calibrate` symbol detected via `dlsym()`).

---

## References

- **ABI v2 Implementation**: Git commit `43695c3` - "Eliminate get_info() and return output shape from init()"
- **Plugin Interface Spec**: `docs/reference/plugin-interface.md`
- **Migration Guides**:
  - v1 → v2: N/A (all kernels migrated in single commit)
  - v2 → v3: `docs/guides/migrating-to-abi-v3.md`
- **Sacred Constraints**: `CLAUDE.md` (constraint #6: "ABI version enforcement")

---

## Appendix: Breaking Change Checklist

When proposing a new ABI version, ensure:

- [ ] Bump `CORTEX_ABI_VERSION` in `cortex_plugin.h`
- [ ] Document rationale in this file (`abi_evolution.md`)
- [ ] Create migration guide (`docs/guides/migrating-to-abi-v{N}.md`)
- [ ] Update all existing kernels or provide backward compatibility mechanism
- [ ] Add compatibility tests (`tests/test_abi_compatibility.c`)
- [ ] Update CHANGELOG with breaking change notice
- [ ] Update CLAUDE.md Sacred Constraints
- [ ] Update `docs/reference/plugin-interface.md`
- [ ] Verify cross-platform builds (macOS + Linux)
- [ ] Run full test suite (unit + integration + oracle validation)

---

**Document Status**: ✅ Complete - covers ABI v1, v2, and v3.

**Next Update**: After ABI v4 implementation (online adaptation support).
