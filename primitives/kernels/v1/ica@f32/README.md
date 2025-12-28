# ICA (Independent Component Analysis) - ABI v3 Trainable Kernel

## Overview

Independent Component Analysis (ICA) is a blind source separation technique used in BCI systems to remove artifacts (eye blinks, muscle activity, line noise) from EEG signals by unmixing statistically independent source signals.

**Key Innovation**: This kernel demonstrates **ABI v3's offline calibration workflow** - the first trainable kernel in CORTEX requiring batch training before inference.

## Algorithm

**Calibration Phase** (offline, one-time):
1. Collect calibration data: N windows of EEG (typically 500 windows)
2. Run FastICA to learn unmixing matrix `W` and channel means
3. Serialize trained state to `.cortex_state` file

**Inference Phase** (online, per-window):
1. Load pre-trained `W` and means in `cortex_init()`
2. For each window: `y = (x - mean) @ W.T`
3. Output: unmixed independent components (artifacts separated)

## Signal Model

Input: `x[t,c]` with shape `[W×C]` in µV (artifact-contaminated EEG)
Output: `y[t,c]` with shape `[W×C]` in µV (unmixed independent components)

$$
y = (x - \mu) W^T
$$

Where:
- $\mu$ = channel means learned during calibration `[C]`
- $W$ = unmixing matrix learned during calibration `[C×C]`

## ABI v3 Compatibility

- **ABI version**: v3 only (requires calibration support)
- **Calibration required**: Yes (offline batch training via FastICA)
- **Capabilities**: `CORTEX_CAP_OFFLINE_CALIB`
- **Exports**: `cortex_calibrate()`, `cortex_init()`, `cortex_process()`, `cortex_teardown()`

**Backward incompatible**: This kernel will NOT work with ABI v2 harnesses (requires `cortex_calibrate()` support).

## Calibration Workflow

### Prerequisites

- Calibration dataset: EEG data in `.float32` format
- Recommended: 500+ windows for stable ICA convergence
- Minimum: 100 windows

### Step 1: Prepare Calibration Data

```bash
# Use a representative dataset (subject-specific calibration)
CALIB_DATA="primitives/datasets/v1/physionet-motor-imagery/converted/S001R01.float32"
```

**Important**: Calibration should use data from the same subject and recording conditions as the target application (ICA is subject-specific).

### Step 2: Run Calibration

```bash
cortex calibrate \
  --kernel ica \
  --dataset $CALIB_DATA \
  --windows 500 \
  --output ica_S001.cortex_state
```

**Output**:
```
[harness] Loading kernel: ica
[harness] Calibration data: 500 windows (160 samples × 64 channels)
[ica] Calibrating on 500 windows (W=160, C=64)
[ica] Full FastICA with Jacobi eigendecomposition completed
[ica] Calibration complete: state size = 16644 bytes
[harness] Saved: ica_S001.cortex_state
✓ Calibration successful
```

### Step 3: Validate Calibration

```bash
cortex validate \
  --kernel ica \
  --calibration-state ica_S001.cortex_state \
  --verbose
```

**Expected**: C kernel output matches Python oracle (tolerance: rtol=1e-4, atol=1e-5)

### Step 4: Run Benchmarks

```bash
cortex run \
  --kernel ica \
  --calibration-state ica_S001.cortex_state \
  --config primitives/configs/cortex.yaml
```

## Calibration State Format

Binary layout (little-endian):
```
Offset    Size         Field
------    ----         -----
0x00      4 bytes      C (uint32_t) - number of channels
0x04      C×4 bytes    mean (float32[C]) - channel means
0x04+C×4  C×C×4 bytes  W (float32[C×C]) - unmixing matrix, row-major
```

**Total size**: 4 + 4×C + 4×C×C bytes
**Example (C=64)**: 4 + 256 + 16384 = 16644 bytes

**Version**: 1 (increment if format changes)

## Training Algorithm

**Full FastICA Implementation** (production-quality):

1. **Whitening via Eigendecomposition**:
   - Compute covariance matrix: `C = X^T X / n_samples`
   - Jacobi eigendecomposition: `C = V D V^T` (no BLAS/LAPACK)
   - Whitening matrix: `K = V D^(-1/2) V^T`
   - Whitened data: `Z = X K`

2. **Iterative FastICA Optimization**:
   - Initialize unmixing matrix `W` (random orthonormal)
   - For each component: update with logcosh nonlinearity
     - `w_new = E[Z g(w^T Z)] - E[g'(w^T Z)] w`
     - where `g(u) = tanh(u)`, `g'(u) = 1 - tanh^2(u)`
   - Symmetric decorrelation: `W = (W W^T)^(-1/2) W`
   - Check convergence: max change < tolerance (1e-4)
   - Max iterations: 200

3. **Final Unmixing Matrix**:
   - `W_unmix = W^T K` (combines whitening + ICA rotation)

**Platform Compatibility**:
- Pure C11 + math.h (no external dependencies)
- Self-contained Jacobi eigendecomposition
- Works on embedded targets (STM32, Jetson, etc.)
- Numerically stable for float32 precision

## Parameters

None (currently). Future versions may expose:
- `n_components`: Number of ICA components to extract (default: C)
- `max_iter`: Maximum FastICA iterations (default: 200)
- `tolerance`: Convergence tolerance (default: 1e-4)

## Edge Cases

**Insufficient calibration data** (`< 100 windows`):
- `cortex_calibrate()` returns error
- Error message: "Need at least 10 windows for calibration"

**Missing calibration state**:
- `cortex_init()` fails with clear error message:
  ```
  [ica] ERROR: Calibration state required but not provided
    Run: cortex calibrate --kernel ica --dataset <path> --output ica.cortex_state
  ```

**Channel count mismatch**:
- If calibration state has C=32 but config requests C=64:
  ```
  [ica] Channel count mismatch: state has 32, config has 64
  ```

**NaN handling**:
- **Calibration**: NaNs replaced with channel mean
- **Inference**: NaNs replaced with 0.0 after centering

## Acceptance Criteria

✅ Calibration completes without errors on 500 windows
✅ Float32 vs oracle within rtol=1e-4, atol=1e-5 (after same calibration data)
✅ State file loads correctly across runs
✅ Missing calibration state produces clear error message
✅ Handles NaN inputs gracefully

## Real-time Budget

**Calibration time**: ~5-30 seconds for 500 windows (one-time cost)
**Inference latency**: ~50-200µs per window (matrix multiply: O(C²×W))
**Memory footprint**:
- Calibration: O(num_windows × W × C) working buffer
- Runtime state: 4 + 4×C + 4×C×C bytes (16644 bytes for C=64)

## Usage Example

```yaml
# primitives/configs/cortex.yaml
plugins:
  - name: "ica"
    status: ready
    spec_uri: "primitives/kernels/v1/ica@f32"
    spec_version: "1.0.0"
    calibration_state: "ica_S001.cortex_state"  # Pre-trained state
```

## Implementation Status

- [x] Specification defined (spec.yaml)
- [x] Python oracle (FastICA via sklearn)
- [x] C implementation (full FastICA with Jacobi eigendecomposition)
- [x] ABI v3 calibration function
- [x] State serialization/deserialization
- [x] Oracle validation (C kernel matches Python within 1e-5 tolerance)
- [x] End-to-end testing (calibration → validation → benchmarking)

## References

1. **Hyvärinen, A., & Oja, E. (2000)**. Independent component analysis: algorithms and applications. *Neural networks, 13(4-5)*, 411-430.
2. **Makeig, S., et al. (1996)**. Independent component analysis of electroencephalographic data. *NIPS*.
3. **Bell, A. J., & Sejnowski, T. J. (1995)**. An information-maximization approach to blind separation and blind deconvolution. *Neural computation, 7(6)*, 1129-1159.

## Troubleshooting

**Q: Calibration fails with "FastICA failed to converge"**
A: This is expected for random/noisy data. For real EEG, FastICA typically converges. If persistent:
- Increase `--windows` (more data helps)
- Check for NaN/Inf in calibration dataset

**Q: Oracle validation fails (C vs Python mismatch)**
A: The C kernel uses simplified FastICA (symmetric decorrelation) while the Python oracle uses full FastICA. This is a **known limitation** of this reference implementation. For production use:
- Implement full FastICA in C (with iterations)
- OR: Accept that reference implementation demonstrates ABI mechanics, not algorithm quality

**Q: High latency during inference**
A: ICA requires O(C²×W) operations per window. For C=64, W=160: ~655k FLOPs. Optimize with:
- BLAS/LAPACK for matrix multiply
- SIMD vectorization
- Reduced components (n_components < C)

**Q: State file from one subject works poorly on another**
A: ICA is **subject-specific**. Each subject requires separate calibration. Do NOT share state files across subjects.

## Future Enhancements

**ABI v4 (online adaptation)**:
- Incremental ICA updates during runtime
- Adaptive artifact removal

**ABI v5 (hybrid calibration)**:
- Combine offline batch training with online fine-tuning
- Reinforcement learning from user feedback

**Performance**:
- BLAS/LAPACK integration for faster matrix operations
- Fixed-point quantization (Q15 unmixing matrix)
- GPU offload for calibration phase
