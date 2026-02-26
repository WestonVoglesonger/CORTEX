# CSP (Common Spatial Pattern) Kernel — ABI v3 Trainable

**Motor imagery spatial filtering for brain-computer interfaces.**

CSP learns spatial filters that maximize the variance ratio between two classes of EEG data (e.g., left vs. right hand motor imagery). This kernel is a **trainable primitive** that requires offline calibration before deployment.

---

## Quick Reference

| Property | Value |
|----------|-------|
| **ABI Version** | 3 (trainable, offline calibration) |
| **Data Type** | float32 |
| **Input Channels** | 64 (configurable) |
| **Output Channels** | 4 (n_components, configurable) |
| **Requires Calibration** | Yes (labeled two-class data) |
| **Algorithm** | Ramoser et al. 2000 (whitening-based CSP) |

---

## Algorithm Overview

**Common Spatial Pattern (CSP)** finds spatial filters that:
1. Maximize variance for one class (e.g., left hand imagery)
2. Minimize variance for another class (e.g., right hand imagery)

This creates discriminative features for classification tasks.

### Mathematical Formulation

Given two classes of EEG data with covariance matrices `C0` and `C1`:

1. **Whitening**: Compute composite covariance `C = C0 + C1`, then whiten using `P = Λ^(-1/2) U^T`
2. **Eigendecomposition**: Solve `S1 @ V = λ @ V` where `S1 = P @ C1 @ P^T`
3. **Filter Selection**: Select top-m and bottom-m eigenvectors (sorted by eigenvalue)
4. **Inference**: Project data to CSP space: `y = x @ W^T`

### Implementation Details

- **Linear Algebra**: Custom Jacobi eigendecomposition (no BLAS/LAPACK dependencies)
- **Numerical Stability**: Regularization (`ε = 1e-6`) on covariance matrices
- **Memory Layout**: Spatial filters stored in **column-major** order for cache efficiency

---

## Workflow

### 0. Installation

Install oracle dependencies (scipy for CSP validation):

```bash
pip install -e ".[oracle]"  # Installs scipy and scikit-learn
```

### 1. Calibration (Offline)

Generate calibration dataset and train CSP filters:

```bash
# Generate 64-channel synthetic calibration data
cortex generate --signal pink_noise --channels 64 --duration 60 --output-dir calib_64ch

# Train CSP filters (100 windows per class)
cortex calibrate --kernel csp \
    --dataset calib_64ch \
    --windows 200 \
    --labels "100x0,100x1" \
    --output csp_64ch.cortex_state
```

**Labels Pattern Syntax:**
- `"100x0,100x1"` = 100 class-0 windows, 100 class-1 windows
- `"50x0,50x1,50x0,50x1"` = Alternating batches
- Pattern must sum to `--windows` value

**Custom Geometries:**
```bash
# 128-channel configuration
cortex generate --channels 128 --duration 60 --output-dir calib_128ch
cortex calibrate --kernel csp --dataset calib_128ch --windows 200 --labels "100x0,100x1" --output csp_128ch.cortex_state

# Override geometry from dataset spec
cortex calibrate --kernel csp --dataset calib_128ch --channels 64 --output csp_64ch_override.cortex_state
```

**Data Requirements:**
- **Minimum windows**: 200 (100 per class recommended)
- **Format**: Dataset primitive directory with spec.yaml (created by `cortex generate`)
- **Labels**: Pattern syntax (e.g., `"100x0,100x1"`)

### 2. Inference (Real-Time)

Apply learned filters to new data:

```bash
# Using cortex harness (production deployment)
cortex run config.yaml --state csp_model.cortex_state
```

**Config Example** (`config.yaml`):
```yaml
kernels:
  - name: csp
    version: v1
    dtype: float32
    calibration_state: "csp_model.cortex_state"
```

### Runtime Configuration Flexibility

CSP spatial filters have **different flexibility** for different parameters:

| Parameter | Flexibility | Requires Retraining? | Notes |
|-----------|-------------|----------------------|-------|
| **Channels (C)** | ❌ **Fixed** | ✅ **YES** | Baked into filter dimensions [n_components, C] |
| **Window Length (W)** | ✅ **Flexible** | ❌ No | CSP applies same spatial filters per timestep |
| **Sample Rate (Fs)** | ✅ **Flexible** | ❌ No | CSP is purely spatial (no temporal dependencies) |

**Enforcement:**
- C kernel checks `config->channels == state->channels` in `cortex_init()`
- Mismatched channel counts return `NULL` (init failure)
- Python oracle raises `AssertionError` on channel mismatch

**Example: Varying window length at runtime**
```yaml
# Train on 1-second windows
calibration:
  window_length: 160  # 1 sec @ 160 Hz

# Deploy with 0.5-second windows (no retraining needed!)
inference:
  window_length: 80   # 0.5 sec @ 160 Hz
```

**Why this works:** CSP filters are `[n_components, C]` matrices that multiply with input `[W, C]` to produce output `[W, n_components]`. The operation `y[t, k] = sum_c(x[t, c] * W[k, c])` is applied independently to each timestep `t`, so `W` can vary freely.

---

## State File Format

CSP calibration produces a `.cortex_state` file with binary format:

### Header (16 bytes)
```
Bytes 0-3:   Magic number (0x434F5254 = "CORT")
Bytes 4-7:   ABI version (3)
Bytes 8-11:  State version (1)
Bytes 12-15: Payload size (uint32)
```

### Payload
```
Bytes 0-3:   n_channels (uint32, e.g., 64)
Bytes 4-7:   n_components (uint32, e.g., 4)
Bytes 8-end: Spatial filters [n_components × C] (float32, column-major)
```

**Total Size**: `16 + 8 + 4*n_components*C` bytes (1048 bytes for 64ch, 4 components)

---

## Motor Imagery Use Case

**Brain-Computer Interface Paradigm**: Motor imagery (imagining limb movements without physical execution)

### Typical Setup
- **Task**: User imagines left vs. right hand movement
- **EEG Channels**: 64 (motor cortex coverage: C3, Cz, C4)
- **Frequency Band**: Alpha/beta (8-30 Hz, bandpass filtered upstream)
- **Trial Duration**: 3-5 seconds per imagery trial
- **Training Data**: 100-200 trials per class (10-20 minutes of calibration)

### Pipeline Example
```yaml
# Preprocessing + CSP feature extraction
kernels:
  - name: bandpass_fir  # Isolate alpha/beta rhythm
    passband: [8, 30]
  
  - name: csp  # Extract discriminative spatial features
    calibration_state: "motor_imagery_csp.cortex_state"
  
  - name: lda  # Classify (future kernel, not yet implemented)
    calibration_state: "motor_imagery_lda.cortex_state"
```

---

## Performance Characteristics

### Latency (160Hz, W=160, C=64, n_components=4)
- **Expected**: <50µs per window (matrix-vector multiply: 64×4 = 256 ops)
- **Deadline**: 500ms (H/Fs = 80/160)
- **Headroom**: >10000× (latency << deadline)

### Memory Footprint
- **Runtime State**: `8 + 4*C*n_components` bytes (1032 bytes for 64ch×4comp)
- **Stack Usage**: <1KB (no heap allocation in `cortex_process()`)

---

## Validation Status

| Component | Status | Notes |
|-----------|--------|-------|
| **Python Oracle** | ✅ **Passing** | Calibration + inference tested end-to-end |
| **C Calibration** | ✅ **Passing** | Generalized eigenvalue solver validated |
| **C Runtime** | ✅ **Passing** | Init/process/teardown all working correctly |
| **Accuracy Validation** | ✅ **Passing** | Max error: 5.96e-08 (< 1e-5 tolerance) |
| **Cross-Platform** | ⏳ Pending | Needs Jetson ARM64 validation |

### Validation Results
- **Numerical Accuracy**: C kernel matches Python oracle within float32 tolerance
  - Max absolute error: `5.96e-08` (across 10 test windows)
  - Mean absolute error: `4.69e-08`
  - Tolerance threshold: `1e-5` ✅
- **Test Coverage**: Calibration (200 windows, 2 classes) + inference (10 windows)
- **Test Script**: `test_csp_validation.py` (automated validation)

---

## References

### Academic Literature
- **Ramoser, H., Muller-Gerking, J., & Pfurtscheller, G. (2000)**  
  "Optimal spatial filtering of single trial EEG during imagined hand movement"  
  *IEEE Transactions on Rehabilitation Engineering*  
  [DOI: 10.1109/86.895946](https://doi.org/10.1109/86.895946)

- **Blankertz, B., et al. (2008)**  
  "Optimizing spatial filters for robust EEG single-trial analysis"  
  *IEEE Signal Processing Magazine*  
  [DOI: 10.1109/MSP.2008.4408441](https://doi.org/10.1109/MSP.2008.4408441)

### Implementation References
- **MNE-Python**: `mne.decoding.CSP` (Python reference)
- **EEGLAB**: `pop_csp()` (MATLAB reference)
- **BCI Competition**: Public motor imagery datasets

---

## Development Notes

### Column-Major Storage
Spatial filters are stored in column-major (Fortran) order for compatibility with BLAS/LAPACK conventions and potential future GPU acceleration:

```c
// Access filter matrix W[C, n_components] in column-major layout
float w_ck = W_filters[c + k * C];  // Element (c, k)
```

Python serialization uses:
```python
filters.flatten(order='F').tobytes()  # Column-major
```

### Testing Strategy
1. **Unit Tests**: Eigendecomposition correctness (Jacobi solver)
2. **Oracle Validation**: Python (SciPy/MNE) vs C implementation (<1e-5 tolerance)
3. **Synthetic Data**: Known class structure (amplitude differences in specific channels)
4. **Real Data**: PhysioNet Motor Imagery dataset (S001-S109)

---

## Future Enhancements

- **Multi-class CSP**: Extend to >2 classes (One-vs-Rest or One-vs-One)
- **Regularized CSP**: Tikhonov regularization for small sample sizes
- **Filter Bank CSP**: Multi-band frequency decomposition
- **Online Adaptation**: Incremental updates (ABI v4 feature)
- **Fixed-Point**: Q15 quantization for embedded deployment

---

## Build & Test

```bash
# Build kernel
make -C primitives/kernels/v1/csp@f32

# Verify ABI exports
nm primitives/kernels/v1/csp@f32/libcsp.dylib | grep cortex

# Test oracle (standalone)
python3 primitives/kernels/v1/csp@f32/oracle.py

# Full validation (requires oracle-C comparison framework)
cortex validate --kernel csp
```

---

**Maintainer**: CORTEX Development Team  
**Created**: 2026-01-12  
**Last Updated**: 2026-01-12  
**Sprint**: Week 1 (CSP Implementation)
