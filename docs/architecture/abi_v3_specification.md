# CORTEX ABI v3 Technical Specification

**Version**: 3.0.0
**Date**: 2025-12-27
**Status**: Design Complete, Implementation Pending

---

## Executive Summary

ABI v3 extends CORTEX's plugin interface to support **offline calibration** for trainable kernels (ICA, CSP). The design maintains backward compatibility with v2 kernels while enabling a two-phase workflow: batch calibration → per-window inference.

**Key Additions**:
- Optional `cortex_calibrate()` function for batch training
- Extended configuration struct with calibration state fields
- Capability advertisement mechanism (future-proof for v4/v5)
- State serialization format for cross-platform deployment

---

## 1. ABI Version Constant

```c
#define CORTEX_ABI_VERSION 3u
```

**Breaking Change**: Increment from `2u` to `3u`.

**Rationale**: Extended structs and new function require version bump to prevent v2 harness from loading v3-only kernels.

---

## 2. Core Data Types

### 2.1 Capability Flags (NEW)

```c
/**
 * Kernel capability flags.
 *
 * Kernels advertise capabilities via cortex_init_result_t.capabilities.
 * Harness uses these flags to determine which optional functions exist.
 *
 * Design Note: Flags are future-proof for v4 (online adaptation) and v5 (hybrid).
 */
typedef enum {
    CORTEX_CAP_OFFLINE_CALIB  = 1 << 0,  /**< Supports cortex_calibrate() - batch training */
    CORTEX_CAP_ONLINE_ADAPT   = 1 << 1,  /**< Reserved: v4 - per-window adaptation */
    CORTEX_CAP_FEEDBACK_LEARN = 1 << 2,  /**< Reserved: v5 - reinforcement learning */
} cortex_capability_flags_t;
```

**Usage**:
```c
// Kernel advertises calibration support
result.capabilities = CORTEX_CAP_OFFLINE_CALIB;

// Harness checks capabilities
if (result.capabilities & CORTEX_CAP_OFFLINE_CALIB) {
    void *calib_fn = dlsym(plugin, "cortex_calibrate");
    // ...
}
```

---

### 2.2 Plugin Configuration (EXTENDED)

```c
/**
 * Plugin configuration passed to cortex_init().
 *
 * Extended in v3 with calibration state fields (appended for backward compatibility).
 * v2 kernels safely ignore new fields via struct_size check.
 */
typedef struct {
    /* ========== ABI Handshake (v1+) ========== */
    uint32_t abi_version;           /**< Must be CORTEX_ABI_VERSION (now 3) */
    uint32_t struct_size;           /**< sizeof(cortex_plugin_config_t) supplied by harness */

    /* ========== Runtime Configuration (v1+) ========== */
    uint32_t sample_rate_hz;        /**< Fs: samples per second (e.g., 160 Hz) */
    uint32_t window_length_samples; /**< W: samples per window (e.g., 160) */
    uint32_t hop_samples;           /**< H: samples to advance per window (e.g., 80) */
    uint32_t channels;              /**< C: number of input channels (e.g., 64) */
    uint32_t dtype;                 /**< One of cortex_dtype_bitmask_t values */
    uint8_t  allow_in_place;        /**< Non-zero: process() may read/write same buffer */
    uint8_t  reserved0[3];          /**< Reserved for alignment/future flags */

    /* ========== Kernel Parameters (v1+) ========== */
    const void *kernel_params;      /**< String: "param1: val1, param2: val2, ..." */
    uint32_t   kernel_params_size;  /**< Size of parameters string in bytes */

    /* ========== Calibration State (v3+) ========== */
    const void *calibration_state;   /**< Pre-trained state (e.g., ICA unmixing matrix W) */
    uint32_t calibration_state_size; /**< Size of calibration_state in bytes */

    /* Future fields can be appended here. Use struct_size to safely
     * determine how many bytes are available. Do not remove or change
     * existing fields without bumping CORTEX_ABI_VERSION.
     */
} cortex_plugin_config_t;
```

**Size**:
- v2: 48 bytes
- v3: 56 bytes (+8 bytes for calibration fields)

**Backward Compatibility**:
```c
// v2 kernel ignores v3 fields
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    if (config->struct_size < sizeof_v2) { return error; }
    // v2 kernel never reads past offset 48 → safe
}

// v3 kernel checks for calibration state
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    if (config->struct_size >= offsetof(cortex_plugin_config_t, calibration_state)) {
        // v3 fields available
        if (config->calibration_state != NULL) {
            // Load pre-trained state
        }
    }
}
```

---

### 2.3 Init Result (EXTENDED)

```c
/**
 * Result structure returned by cortex_init().
 *
 * Extended in v3 with capability flags (appended for backward compatibility).
 */
typedef struct {
    void *handle;                        /**< Opaque instance handle (NULL on error) */
    uint32_t output_window_length_samples; /**< Actual output W (may differ from input) */
    uint32_t output_channels;            /**< Actual output C (may differ from input) */

    /* ========== Capability Flags (v3+) ========== */
    uint32_t capabilities;               /**< Bitmask of cortex_capability_flags_t */
} cortex_init_result_t;
```

**Size**:
- v2: 16 bytes
- v3: 20 bytes (+4 bytes for capabilities)

**Migration**:
```c
// v2 kernel: MUST set capabilities = 0
return (cortex_init_result_t){
    .handle = state,
    .output_window_length_samples = W,
    .output_channels = C,
    .capabilities = 0  // NEW: Required in v3
};

// v3 trainable kernel: Set calibration flag
return (cortex_init_result_t){
    .handle = state,
    .output_window_length_samples = W,
    .output_channels = C,
    .capabilities = CORTEX_CAP_OFFLINE_CALIB
};
```

---

### 2.4 Calibration Result (NEW)

```c
/**
 * Result structure returned by cortex_calibrate().
 *
 * Contains trained state (e.g., ICA unmixing matrix, CSP filters).
 * Harness serializes this state to .cortex_state files for later use.
 */
typedef struct {
    void *calibration_state;       /**< Opaque trained state (NULL on error) */
    uint32_t state_size_bytes;     /**< Size of state for serialization */
    uint32_t state_version;        /**< Kernel-specific state version (for evolution) */
} cortex_calibration_result_t;
```

**Example**:
```c
// ICA calibration: return unmixing matrix W
cortex_calibration_result_t cortex_calibrate(...) {
    float *W = train_ica(...);  // Shape: (C, C)

    return (cortex_calibration_result_t){
        .calibration_state = W,
        .state_size_bytes = config->channels * config->channels * sizeof(float),
        .state_version = 1  // ICA state format v1
    };
}
```

**State Lifecycle**:
```
cortex_calibrate() → returns state
    ↓
Harness saves to .cortex_state file
    ↓
User configures calibration_state path in YAML
    ↓
Harness loads .cortex_state file
    ↓
cortex_init(config with calibration_state) → uses pre-trained state
```

---

## 3. Function Signatures

### 3.1 cortex_calibrate() (NEW, OPTIONAL)

```c
/**
 * Calibrate kernel on batch data (optional - trainable kernels only).
 *
 * The harness provides multiple windows of calibration data. The kernel
 * performs batch training (e.g., FastICA, CSP eigendecomposition)
 * and returns learned state.
 *
 * If kernel doesn't export this symbol, harness assumes:
 * - Kernel is stateless (e.g., CAR, bandpass_fir), OR
 * - Kernel requires pre-calibrated state via config->calibration_state
 *
 * Parameters:
 *  @param config        Same as cortex_init (channels, sample_rate, etc.)
 *  @param calibration_data  Pointer to (num_windows × W × C) float32 array
 *  @param num_windows   Number of windows in calibration data
 *
 * Returns:
 *  - {state, size, version} on success
 *  - {NULL, 0, 0} on failure (harness logs error)
 *
 * Constraints:
 *  - MAY allocate memory (this is a one-time operation)
 *  - MAY perform expensive computation (iterative convergence)
 *  - MUST be deterministic (same input → same output, for reproducibility)
 *  - MUST handle NaN inputs gracefully
 *
 * Design Notes:
 *  - This function is called ONCE per calibration session
 *  - Result is serialized to .cortex_state file
 *  - State format is kernel-specific (use state_version for evolution)
 */
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *calibration_data,
    uint32_t num_windows
);
```

**Detection Logic**:
```c
// Harness checks for symbol at runtime
void *calib_fn = dlsym(plugin, "cortex_calibrate");
if (calib_fn != NULL) {
    // Kernel supports calibration
    cortex_calibration_result_t result = ((cortex_calibrate_fn)calib_fn)(config, data, num_windows);
} else {
    // Kernel does not support calibration
    fprintf(stderr, "[harness] Kernel '%s' does not export cortex_calibrate\n", name);
}
```

**Determinism Requirement**:
- Same `calibration_data` → same `calibration_state` output
- Use fixed RNG seeds if randomization needed (e.g., FastICA initialization)
- Critical for oracle validation and reproducibility

---

### 3.2 cortex_init() (MODIFIED)

```c
/**
 * Initialize a plugin instance.
 *
 * MODIFIED in v3: Now accepts optional calibration_state via config.
 *
 * The config->abi_version field must match CORTEX_ABI_VERSION and
 * config->struct_size must be at least sizeof(cortex_plugin_config_t).
 * The plugin validates the requested dtype and other parameters, allocates
 * persistent state based on config, and returns both a handle and output
 * dimensions. If initialization fails (unsupported dtype/parameters or
 * allocation failure), the function returns {NULL, 0, 0, 0}.
 *
 * NEW in v3: If config->calibration_state is non-NULL, kernel uses
 * pre-trained state. Otherwise, kernel may:
 * - Use hardcoded defaults (e.g., identity matrix for ICA - usually invalid)
 * - Return error if calibration required
 *
 * Parameters:
 *  @param config  Pointer to configuration structure populated by the harness.
 *
 * Returns:
 *  - cortex_init_result_t containing handle, output dimensions, and capabilities
 *  - handle is NULL on error
 */
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
```

**No signature change from v2**, but semantics extended:
- v2: Ignored `calibration_state` (field didn't exist)
- v3: Reads `calibration_state` if available

---

### 3.3 cortex_process() (UNCHANGED)

```c
/**
 * Process one window of data.
 *
 * UNCHANGED from v2 - same signature and constraints.
 */
void cortex_process(void *handle, const void *input, void *output);
```

---

### 3.4 cortex_teardown() (UNCHANGED)

```c
/**
 * Free all resources associated with a plugin instance.
 *
 * UNCHANGED from v2 - same signature and constraints.
 */
void cortex_teardown(void *handle);
```

---

## 4. State Serialization Format

### 4.1 File Format (`.cortex_state`)

```c
/* ========== Header (16 bytes, fixed) ========== */
struct cortex_state_header {
    uint32_t magic;         /**< 0x434F5254 ("CORT" in ASCII, little-endian) */
    uint32_t abi_version;   /**< ABI version that produced this state (3) */
    uint32_t state_version; /**< Kernel-specific state format version */
    uint32_t data_size;     /**< Size of following data in bytes */
};

/* ========== Data (variable length) ========== */
/* Kernel-specific data follows immediately after header.
 *
 * Examples:
 * - ICA: float32 unmixing matrix W (C × C elements)
 * - CSP: float32 spatial filters (K × C elements)
 */
```

**Example (ICA with 64 channels)**:
```
Offset | Size | Field               | Value
-------|------|---------------------|----------
0x00   | 4    | magic               | 0x434F5254
0x04   | 4    | abi_version         | 3
0x08   | 4    | state_version       | 1 (ICA state format v1)
0x0C   | 4    | data_size           | 16384 (64×64×4 bytes)
0x10   | 16384| W matrix            | float32[64][64]
```

**File Size**: 16 + data_size bytes

---

### 4.2 Storage Location

**Path Convention**:
```
primitives/datasets/v{version}/{dataset}/calibration_states/{kernel}_{method}.cortex_state
```

**Examples**:
```
primitives/datasets/v1/physionet-motor-imagery/calibration_states/ica_fastica.cortex_state
primitives/datasets/v1/physionet-motor-imagery/calibration_states/ica_infomax.cortex_state
primitives/datasets/v1/physionet-motor-imagery/calibration_states/csp_default.cortex_state
```

**Rationale**:
- Calibration state is tied to specific dataset (subject-specific)
- Stored alongside dataset for reproducibility
- Versioned like other primitives

---

### 4.3 Loading API

```c
/**
 * Load calibration state from file.
 *
 * Validates header magic and ABI version, allocates buffer, and loads data.
 * Caller must free returned pointer.
 *
 * @param path         Path to .cortex_state file
 * @param[out] size    Size of loaded data (bytes)
 * @param[out] version Kernel state version
 * @return Pointer to calibration state (NULL on error)
 */
void* cortex_load_calibration_state(
    const char *path,
    uint32_t *size,
    uint32_t *version
);
```

**Implementation** (harness utility):
```c
void* cortex_load_calibration_state(const char *path, uint32_t *size, uint32_t *version) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;

    // Read header
    struct cortex_state_header header;
    if (fread(&header, sizeof(header), 1, f) != 1) {
        fclose(f);
        return NULL;
    }

    // Validate magic
    if (header.magic != 0x434F5254) {
        fprintf(stderr, "[harness] Invalid magic number in %s\n", path);
        fclose(f);
        return NULL;
    }

    // Validate ABI version
    if (header.abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[harness] State ABI mismatch: file=%u, expected=%u\n",
                header.abi_version, CORTEX_ABI_VERSION);
        fclose(f);
        return NULL;
    }

    // Allocate and load data
    void *data = malloc(header.data_size);
    if (!data) {
        fclose(f);
        return NULL;
    }

    if (fread(data, header.data_size, 1, f) != 1) {
        free(data);
        fclose(f);
        return NULL;
    }

    fclose(f);
    *size = header.data_size;
    *version = header.state_version;
    return data;
}
```

---

### 4.4 Saving API

```c
/**
 * Save calibration state to file.
 *
 * Writes header + data in binary format.
 *
 * @param path    Path to .cortex_state file (will be created/overwritten)
 * @param state   Pointer to calibration state data
 * @param size    Size of state data (bytes)
 * @param version Kernel state version
 * @return 0 on success, -1 on error
 */
int cortex_save_calibration_state(
    const char *path,
    const void *state,
    uint32_t size,
    uint32_t version
);
```

**Implementation**:
```c
int cortex_save_calibration_state(const char *path, const void *state, uint32_t size, uint32_t version) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;

    // Write header
    struct cortex_state_header header = {
        .magic = 0x434F5254,
        .abi_version = CORTEX_ABI_VERSION,
        .state_version = version,
        .data_size = size
    };

    if (fwrite(&header, sizeof(header), 1, f) != 1) {
        fclose(f);
        return -1;
    }

    // Write data
    if (fwrite(state, size, 1, f) != 1) {
        fclose(f);
        return -1;
    }

    fclose(f);
    return 0;
}
```

---

## 5. Backward Compatibility Mechanism

### 5.1 Version Detection

**Harness Logic**:
```c
// Load plugin
void *plugin = dlopen(plugin_path, RTLD_NOW);

// Check for cortex_calibrate symbol
void *calib_fn = dlsym(plugin, "cortex_calibrate");
if (calib_fn != NULL) {
    // v3 kernel with calibration support
    fprintf(stderr, "[harness] Loaded v3 kernel (calibration-capable)\n");
} else {
    // v2 kernel (or v3 stateless kernel)
    fprintf(stderr, "[harness] Loaded v2 kernel (no calibration)\n");
}

// Call cortex_init (all versions)
cortex_init_fn init_fn = (cortex_init_fn)dlsym(plugin, "cortex_init");
cortex_init_result_t result = init_fn(&config);

// Check capabilities (v3+ kernels set this, v2 kernels return 0)
if (result.capabilities & CORTEX_CAP_OFFLINE_CALIB) {
    fprintf(stderr, "[harness] Kernel advertises calibration capability\n");
}
```

### 5.2 Config Struct Compatibility

**v2 Kernel Reading v3 Config**:
```c
// v2 kernel checks struct_size before reading fields
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // Validate ABI version (accept v2 or v3)
    if (config->abi_version < 2 || config->abi_version > 3) {
        return (cortex_init_result_t){0};
    }

    // Validate struct size (must be at least v2 size)
    if (config->struct_size < 48) {  // v2 size
        return (cortex_init_result_t){0};
    }

    // v2 kernel never reads past offset 48 (safe - calibration fields at offset 48+)
    // ... normal v2 initialization ...

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = W,
        .output_channels = C,
        .capabilities = 0  // NEW: v3 requires this field
    };
}
```

**v3 Harness Calling v2 Kernel**:
```c
// Harness always passes v3 config
cortex_plugin_config_t config = {
    .abi_version = 3,
    .struct_size = sizeof(cortex_plugin_config_t),  // v3 size (56 bytes)
    // ... fill v2 fields ...
    .calibration_state = NULL,      // v2 kernel ignores this
    .calibration_state_size = 0
};

// v2 kernel safely ignores new fields (reads only first 48 bytes)
cortex_init_result_t result = cortex_init(&config);
```

### 5.3 Capability Flag Compatibility

**v2 Kernels**:
- MUST set `capabilities = 0` in `cortex_init_result_t`
- Compilation will fail if field omitted (forces migration)

**v3 Harness**:
- Checks `capabilities` field to determine kernel features
- Zero capabilities → v2-style stateless kernel

---

## 6. Error Handling

### 6.1 Calibration Errors

**Scenario**: `cortex_calibrate()` fails (e.g., insufficient data, convergence failure)

**Kernel Behavior**:
```c
cortex_calibration_result_t cortex_calibrate(...) {
    if (num_windows < MIN_WINDOWS) {
        fprintf(stderr, "[ica] ERROR: Calibration requires >= %d windows, got %d\n",
                MIN_WINDOWS, num_windows);
        return (cortex_calibration_result_t){0};  // NULL state
    }

    if (!convergence_achieved) {
        fprintf(stderr, "[ica] WARNING: Calibration did not converge after %d iterations\n",
                MAX_ITERS);
        return (cortex_calibration_result_t){0};  // NULL state
    }

    return (cortex_calibration_result_t){state, size, version};
}
```

**Harness Behavior**:
```c
cortex_calibration_result_t result = cortex_calibrate(&config, data, num_windows);
if (result.calibration_state == NULL) {
    fprintf(stderr, "[harness] ERROR: Calibration failed for kernel '%s'\n", name);
    exit(1);  // Fatal error - cannot proceed without calibration
}
```

### 6.2 Missing Calibration State

**Scenario**: v3 trainable kernel called without calibration state

**Kernel Behavior**:
```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // Check for required calibration state
    if (config->calibration_state == NULL) {
        fprintf(stderr, "[ica] ERROR: This kernel requires pre-calibrated state.\n");
        fprintf(stderr, "[ica] Run: cortex calibrate --kernel ica@f32 --dataset <path> --output <state_file>\n");
        return (cortex_init_result_t){0};  // NULL handle
    }

    // Load state
    // ...
}
```

### 6.3 State Version Mismatch

**Scenario**: Kernel state format evolved (state_version=2 but kernel expects v1)

**Kernel Behavior**:
```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    // Load state header (first 4 bytes = version)
    uint32_t *state_version = (uint32_t *)config->calibration_state;

    if (*state_version != EXPECTED_STATE_VERSION) {
        fprintf(stderr, "[ica] ERROR: State version mismatch: file=%u, expected=%u\n",
                *state_version, EXPECTED_STATE_VERSION);
        fprintf(stderr, "[ica] Recalibrate with current kernel version.\n");
        return (cortex_init_result_t){0};
    }

    // ...
}
```

---

## 7. CLI Integration

### 7.1 New Command: `cortex calibrate`

**Syntax**:
```bash
cortex calibrate --kernel <name> --dataset <path> --output <state_file> [--params <params>]
```

**Example**:
```bash
cortex calibrate \
    --kernel ica@f32 \
    --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
    --output primitives/datasets/v1/physionet-motor-imagery/calibration_states/ica_fastica.cortex_state \
    --params "method: fastica, n_components: 64, max_iter: 1000"
```

**Behavior**:
1. Load dataset (all windows)
2. Load kernel plugin
3. Call `cortex_calibrate(config, data, num_windows)`
4. Save result to `.cortex_state` file
5. Print summary (convergence info, state size, etc.)

### 7.2 Modified Config: `calibration_state` Field

**YAML Schema Addition**:
```yaml
plugins:
  - name: "ica"
    spec_uri: "primitives/kernels/v1/ica@f32"
    calibration_state: "primitives/datasets/v1/physionet-motor-imagery/calibration_states/ica_fastica.cortex_state"  # NEW
    params:
      # ... (kernel-specific runtime params) ...
```

**Harness Behavior**:
```c
// Parse YAML
if (yaml_has_key("calibration_state")) {
    const char *state_path = yaml_get_string("calibration_state");

    // Load state
    uint32_t size, version;
    void *state = cortex_load_calibration_state(state_path, &size, &version);

    // Pass to cortex_init
    config.calibration_state = state;
    config.calibration_state_size = size;
}
```

---

## 8. Testing Requirements

### 8.1 Unit Tests

**File**: `tests/test_abi_compatibility.c`

**Test Cases**:
1. v2 kernel with v3 harness (backward compatibility)
2. v3 kernel with v2 harness (rejection)
3. v3 kernel with missing `cortex_calibrate` symbol (stateless v3 kernel)
4. Capability flag detection

### 8.2 Integration Tests

**File**: `tests/test_calibration.c`

**Test Cases**:
1. `cortex_calibrate()` → save state → load state → `cortex_init()`
2. Calibration determinism (same input → same output)
3. State serialization round-trip (save → load → verify)
4. Invalid state file rejection (corrupted header, wrong ABI version)

### 8.3 Oracle Validation

**ICA Calibration Oracle** (`primitives/kernels/v1/ica@f32/oracle.py`):
```python
def ica_calibrate_ref(data, n_components=64, random_state=42):
    """Calibration oracle using sklearn FastICA."""
    from sklearn.decomposition import FastICA
    ica = FastICA(n_components=n_components, random_state=random_state, max_iter=1000)
    ica.fit(data)
    return ica.components_.astype('float32')  # W matrix (C × C)

def ica_process_ref(x, W):
    """Process oracle (apply unmixing)."""
    return (x @ W.T).astype('float32')
```

**Validation**:
```bash
# C calibration
cortex calibrate --kernel ica@f32 --dataset test_data.float32 --output c_state.cortex_state

# Python calibration
python oracle.py calibrate test_data.float32 py_state.npy

# Compare states
python -c "
import numpy as np
c_w = np.fromfile('c_state.cortex_state', dtype=np.float32, offset=16).reshape(64, 64)
py_w = np.load('py_state.npy')
assert np.allclose(c_w, py_w, rtol=1e-5, atol=1e-6)
print('PASS: Calibration oracle validation')
"
```

---

## 9. Migration Checklist

**For v2 Kernel Authors** (minimal changes):
- [ ] Add `capabilities = 0` to `cortex_init_result_t` return value
- [ ] Optionally: Update ABI version check to accept v3 (`if (config->abi_version >= 2 && config->abi_version <= 3)`)
- [ ] Recompile and test with v3 harness

**For New v3 Trainable Kernels**:
- [ ] Implement `cortex_calibrate()` function
- [ ] Load `config->calibration_state` in `cortex_init()`
- [ ] Set `capabilities = CORTEX_CAP_OFFLINE_CALIB` in init result
- [ ] Implement Python calibration oracle
- [ ] Create `.cortex_state` file format documentation
- [ ] Write calibration workflow guide in README

---

## 10. Open Questions & Future Work

### 10.1 Online Adaptation (v4)

**Question**: How to validate non-deterministic algorithms?

**Proposed Approach**:
- Require RNG seeding for reproducibility
- Tolerance-based oracle comparison (looser than offline calibration)
- Convergence criteria (e.g., "P95 latency below threshold after N windows")

### 10.2 State Evolution

**Question**: How to handle state format changes?

**Current Approach**:
- `state_version` field allows kernel-specific versioning
- Kernels check version and reject incompatible states

**Future Enhancement**:
- State migration functions (v1 → v2 converter)
- Backward compatibility guarantees (v2 kernel reads v1 state)

### 10.3 Multi-Platform Serialization

**Question**: Does state format need endianness handling?

**Current Approach**:
- Assume little-endian (x86-64, ARM64 both little-endian)
- Document endianness requirement

**Future Enhancement**:
- Add endianness flag to header
- Byte-swap on load if mismatch detected

---

## 11. References

- **ABI v2 Specification**: `sdk/kernel/include/cortex_plugin.h` (v2)
- **Plugin Interface**: `docs/reference/plugin-interface.md`
- **ABI Evolution**: `docs/architecture/abi_evolution.md`
- **State Serialization**: Section 4 of this document

---

**Document Status**: ✅ Complete - ready for implementation.

**Next Steps**:
1. Implement header changes (`cortex_plugin.h`)
2. Implement harness loader detection logic
3. Implement state I/O utilities
4. Implement ICA kernel as reference
5. Write tests

**Approval**: Requires technical review before Phase 3 (implementation).
