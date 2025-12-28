# Migrating to ABI v3: Offline Calibration Support

**Status:** Stable (December 2025)
**Backward Compatibility:** ✅ v2 kernels work unmodified with v3 harness

---

## Overview

ABI v3 adds support for **trainable kernels** that require offline batch training (calibration) before real-time inference. This enables adaptive signal processing algorithms like ICA, CSP, and LDA while maintaining zero-latency overhead during `cortex_process()`.

### Key Changes

| Feature | ABI v2 | ABI v3 |
|---------|--------|--------|
| **Core functions** | `init`, `process`, `teardown` | Same + optional `calibrate` |
| **Backward compat** | N/A | ✅ v2 kernels work unmodified |
| **Calibration** | Not supported | `cortex_calibrate()` for batch training |
| **State loading** | N/A | `.cortex_state` files via `config->calibration_state` |
| **Capability flags** | None | `CORTEX_CAP_OFFLINE_CALIB` (bitmask) |
| **Harness detection** | N/A | Auto-detect via `dlsym("cortex_calibrate")` |

---

## Breaking Changes

**None.** ABI v3 is fully backward compatible with v2 kernels.

- v2 kernels (stateless/stateful) continue to work without modification
- Loader detects missing `cortex_calibrate` symbol and treats kernel as v2
- No changes required to existing kernel code

---

## Migration Paths

### Path 1: Existing Kernels (No Action Required)

**All existing v2 kernels work as-is:**
- CAR, notch_iir, bandpass_fir, goertzel, welch_psd, noop
- No code changes needed
- Harness logs: `[loader] Plugin is ABI v2 compatible (no calibration support)`

**What happens:**
1. Loader calls `dlsym(handle, "cortex_calibrate")`
2. Returns NULL → kernel is v2
3. `api.calibrate = NULL`, `api.capabilities = 0`
4. Kernel works normally via `init/process/teardown`

### Path 2: New Trainable Kernels

**For algorithms requiring batch training** (ICA, CSP, LDA):

1. **Implement `cortex_calibrate()`** (offline batch training)
2. **Load state in `cortex_init()`** (deserialize model parameters)
3. **Apply model in `cortex_process()`** (zero-latency inference)

See [Adding Kernels Guide](adding-kernels.md#trainable-kernels-abi-v3) for full implementation details.

---

## New ABI v3 Features

### 1. Calibration Function

**Purpose:** Offline batch training to learn model parameters.

```c
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,     // [num_windows, W, C] float32
    uint32_t num_windows
);
```

**When to use:**
- Kernel requires training on batch data (ICA unmixing matrix, CSP filters, LDA weights)
- Model parameters are fixed after training
- Real-time `process()` applies pre-trained model with zero overhead

**Example: ICA**
```c
cortex_calibration_result_t cortex_calibrate(...) {
    // 1. Run FastICA on batch data
    float *W_unmix = train_ica(calibration_data, num_windows, C);

    // 2. Serialize state
    uint32_t state_size = C * C * sizeof(float);
    uint8_t *state = malloc(state_size);
    memcpy(state, W_unmix, state_size);

    // 3. Return state
    return (cortex_calibration_result_t){
        .calibration_state = state,
        .state_size_bytes = state_size,
        .state_version = 1
    };
}
```

### 2. State Loading

**Purpose:** Load pre-trained model parameters in `cortex_init()`.

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // Check if calibration state provided
    if (config->calibration_state == NULL) {
        fprintf(stderr, "[kernel] ERROR: Calibration state required\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    // Deserialize state
    const uint8_t *bytes = config->calibration_state;
    uint32_t C;
    memcpy(&C, bytes, sizeof(uint32_t));

    float *W_unmix = malloc(C * C * sizeof(float));
    memcpy(W_unmix, bytes + sizeof(uint32_t), C * C * sizeof(float));

    // Store in kernel state
    state->W_unmix = W_unmix;
    state->C = C;

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = W,
        .output_channels = C,
        .capabilities = CORTEX_CAP_OFFLINE_CALIB
    };
}
```

### 3. Capability Flags

**Purpose:** Advertise kernel features to harness.

```c
// In cortex_plugin.h
#define CORTEX_CAP_OFFLINE_CALIB  (1 << 0)  // Supports offline calibration
// Reserved for future:
// #define CORTEX_CAP_ONLINE_ADAPT   (1 << 1)  // ABI v4: Online adaptation
// #define CORTEX_CAP_HYBRID         (1 << 2)  // ABI v5: Hybrid learning
```

**Usage:**
```c
return (cortex_init_result_t){
    .handle = state,
    .output_window_length_samples = W,
    .output_channels = C,
    .capabilities = CORTEX_CAP_OFFLINE_CALIB  // Declare support
};
```

### 4. State File Format

**Binary structure** (`.cortex_state` files):

```
┌─────────────────────────┐
│ Header (16 bytes)       │
├─────────────────────────┤
│ magic       (4B) 0x434F5254 ("CORT") │
│ abi_version (4B) 3               │
│ state_version (4B) kernel-specific │
│ state_size  (4B) payload bytes   │
├─────────────────────────┤
│ Payload (variable)      │
│ Kernel-specific data    │
│ (state_size bytes)      │
└─────────────────────────┘
```

**Utilities:**
```c
#include "src/engine/harness/util/state_io.h"

// Save state
cortex_state_save("ica_model.cortex_state", state_payload, state_size, state_version);

// Load state
void *payload;
uint32_t size, version;
cortex_state_load("ica_model.cortex_state", &payload, &size, &version);
```

---

## Calibration Workflow

### Command: `cortex calibrate`

**Purpose:** Train kernel on batch data, save model to `.cortex_state` file.

**Example:**
```bash
# 1. Calibrate ICA on 500 windows of EEG data
cortex calibrate \
    --kernel ica \
    --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
    --windows 500 \
    --output ica_S001.cortex_state

# Output: ica_S001.cortex_state (16,660 bytes)
#   Header: 16 bytes
#   Payload: 16,644 bytes (64×64 unmixing matrix + 64 channel means)

# 2. Validate calibrated kernel
cortex validate \
    --kernel ica \
    --calibration-state ica_S001.cortex_state

# 3. Benchmark with calibrated model
cortex run \
    --kernel ica \
    --calibration-state ica_S001.cortex_state \
    --config primitives/configs/cortex.yaml
```

### Validation Workflow

```bash
# For trainable kernels (v3)
cortex validate --kernel ica --calibration-state model.cortex_state

# For stateless/stateful kernels (v2) - no state needed
cortex validate --kernel car
cortex validate --kernel notch_iir
```

---

## Implementation Checklist

### For New Trainable Kernels

- [ ] Implement `cortex_calibrate()` for batch training
- [ ] Define state serialization format (document in kernel README)
- [ ] Load state in `cortex_init()` via `config->calibration_state`
- [ ] Require state: return error if `calibration_state == NULL`
- [ ] Set `capabilities = CORTEX_CAP_OFFLINE_CALIB` in init result
- [ ] Apply model in `cortex_process()` (zero allocation, hermetic)
- [ ] Create Python oracle with CLI support (`--test`, `--calibrate`, `--state`)
- [ ] Document calibration requirements in `spec.yaml` (min_windows, etc.)
- [ ] Validate: C kernel output matches Python oracle

### For Existing v2 Kernels

- [ ] No action required ✅
- [ ] Kernels work unmodified with v3 harness

---

## Example: ICA Reference Implementation

**Full working example:** `primitives/kernels/v1/ica@f32/`

**Key files:**
- `ica.c` - C implementation (403 LOC)
- `oracle.py` - Python reference (375 LOC)
- `spec.yaml` - Calibration metadata
- `README.md` - Usage guide

**End-to-end test:**
```bash
# Build
make all

# Calibrate
cortex calibrate \
    --kernel ica \
    --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
    --windows 100 \
    --output ica_test.cortex_state

# Validate (C kernel vs Python oracle)
tests/test_kernel_accuracy \
    --kernel ica \
    --data primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
    --state ica_test.cortex_state \
    --windows 5 \
    --verbose

# Expected output:
#   Window 0 PASSED: max_abs=3.05e-05, max_rel=4.12e-06
#   Window 1 PASSED: max_abs=3.05e-05, max_rel=3.68e-05
#   ...
#   ✅ ica: ALL TESTS PASSED (5 windows)
```

---

## Troubleshooting

### Error: "Calibration state required"

**Symptom:**
```
[kernel] ERROR: Calibration state required
Failed to initialize plugin
```

**Cause:** Trainable kernel called without `--calibration-state` argument.

**Fix:**
```bash
# First calibrate
cortex calibrate --kernel ica --dataset data.float32 --windows 100 --output model.cortex_state

# Then use state
cortex validate --kernel ica --calibration-state model.cortex_state
```

### Error: "Invalid magic number"

**Symptom:**
```
[state_io] ERROR: Invalid magic number: 0xXXXXXXXX
```

**Cause:** File is not a valid `.cortex_state` file or corrupted.

**Fix:** Re-run `cortex calibrate` to regenerate state file.

### Error: "ABI version mismatch"

**Symptom:**
```
[kernel] ERROR: ABI version mismatch (expected 3, got 2)
```

**Cause:** Kernel was compiled against ABI v2 headers but harness is v3.

**Fix:** Rebuild kernel with updated headers:
```bash
make clean
make all
```

### Warning: "Plugin is ABI v2 compatible"

**Not an error!** Harness detected kernel doesn't have `cortex_calibrate()` and is treating it as v2. This is expected for non-trainable kernels.

---

## Performance Considerations

### Zero Runtime Overhead

**Key design principle:** Calibration cost is paid once offline. Real-time `cortex_process()` has zero overhead.

**Allowed in `cortex_calibrate()`:**
- Heap allocation (malloc/free)
- Iterative algorithms
- Float64 precision
- External libraries (BLAS, LAPACK)

**Forbidden in `cortex_process()`:**
- Heap allocation (state from `init()` only)
- Blocking I/O
- External dependencies
- Non-deterministic behavior

**Measurement:**
```bash
# Benchmark calibrated ICA kernel
cortex run --kernel ica --calibration-state model.cortex_state

# Expected P99 latency: <100µs (same as stateless kernels)
```

---

## Future ABI Versions

### ABI v4 (Planned: Q2 2026)

- **Online adaptation:** Update model parameters during `process()`
- **Incremental learning:** Low-cost updates (RLS, LMS, gradient descent)
- **Capability flag:** `CORTEX_CAP_ONLINE_ADAPT`

### ABI v5 (Planned: Q3 2026)

- **Hybrid learning:** Combine offline calibration + online adaptation
- **Multi-stage training:** Coarse offline → fine online
- **Capability flag:** `CORTEX_CAP_HYBRID`

---

## References

- **ABI v3 Specification:** `docs/architecture/abi_v3_specification.md`
- **Adding Trainable Kernels:** `docs/guides/adding-kernels.md#trainable-kernels-abi-v3`
- **Plugin Interface Reference:** `docs/reference/plugin-interface.md`
- **ICA Example:** `primitives/kernels/v1/ica@f32/README.md`
- **State I/O Utilities:** `src/engine/harness/util/state_io.h`

---

## Summary

**TL;DR:**
1. ✅ v2 kernels work unmodified (zero migration effort)
2. ✅ New trainable kernels: implement `cortex_calibrate()` + load state in `init()`
3. ✅ Workflow: `cortex calibrate` → `.cortex_state` → `cortex validate/run`
4. ✅ Zero runtime overhead (calibration is offline only)
5. ✅ ICA reference implementation demonstrates complete workflow
