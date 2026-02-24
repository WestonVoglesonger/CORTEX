# 7. Oracle Validation

## 7.1 Overview

This section defines the oracle validation procedure for CORTEX v1.0, which verifies that C kernel implementations produce numerically correct output before performance measurement. Oracle validation ensures that performance benchmarks measure optimization quality, not algorithmic errors.

The validation subsystem provides:
- Pre-measurement correctness verification
- Python reference implementation comparison
- Multi-dtype tolerance handling (float32, Q15, Q7)
- Detailed mismatch diagnostics for failed kernels
- Optional validation runs via `cortex validate` command

**Conformance Levels:**

A **basic conformant implementation** MUST support:
- Single-window validation with Python oracles
- Float32 tolerance checking
- Failure reporting with element-wise error details

A **fully conformant implementation** MUST additionally support:
- Multi-window state persistence validation (for stateful kernels)
- Per-dtype tolerances (float32, quantized variants)
- Quantized data type validation (Q15, Q7)
- Error categorization (numerical vs. structural failures)

**Validation Timing:**

Validation runs BEFORE performance measurement. The `cortex pipeline` command automatically validates all kernels before telemetry collection. The `cortex validate` command provides standalone validation for development and debugging.

**Implementation Status:**

This specification documents the validated implementation in CORTEX v1.0. All requirements in this section are implemented and tested. Multi-dtype validation is supported for hardware variants; current software kernels operate in float32.

---

## 7.2 Validation Procedure

### 7.2.1 Validation Lifecycle

Validation follows this procedure for each kernel:

1. **Pre-Check**: Verify oracle implementation exists and is importable
2. **Oracle Execution**: Run Python oracle on test data
3. **Kernel Execution**: Run C kernel on identical test data
4. **Comparison**: Compare outputs using specified tolerances
5. **Result**: Pass or fail with diagnostic details

**Normative Requirements:**

1. Implementations MUST execute validation BEFORE measurement if `--validate` flag is set (default: true)
2. Implementations MUST reject kernels with failing validation and MUST NOT include them in performance measurements
3. Implementations MUST log validation results to `{output_directory}/validation_report.json` (NDJSON format)
4. Validation MUST NOT modify kernel state or affect subsequent measurements

### 7.2.2 Oracle Invocation

The oracle is a Python function that implements the reference algorithm. Implementations MUST invoke oracles as follows:

```python
# Import oracle module from kernel directory
import importlib.util
spec = importlib.util.spec_from_file_location("oracle", "/path/to/kernel/oracle.py")
oracle_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle_module)

# Retrieve oracle function
oracle_func = getattr(oracle_module, oracle_config['function'])

# Call oracle with input data
oracle_output = oracle_func(input_array, **oracle_params)
```

**Normative Requirements:**

1. Implementations MUST resolve `oracle.path` relative to the kernel specification directory
2. Implementations MUST import the Python module specified by `oracle.path`
3. Implementations MUST call the function named in `oracle.function` field
4. If the oracle module cannot be imported, implementations MUST report a validation error and skip the kernel
5. If the oracle function raises an exception, implementations MUST report the exception traceback and mark validation as failed

### 7.2.3 Test Data Generation

Validation uses synthetic test data to avoid dataset I/O overhead:

```c
// Pseudocode for validation test data generation
void generate_test_window(float* window, uint32_t W, uint32_t C) {
    // Deterministic sine wave + low-frequency noise
    // Enables reproducible validation across runs
    for (uint32_t sample = 0; sample < W; sample++) {
        for (uint32_t channel = 0; channel < C; channel++) {
            float t = (float)sample / 160.0f;
            float sine = sinf(2.0f * M_PI * 10.0f * t);  // 10 Hz
            float noise = sin_seeded(sample * C + channel) * 0.1f;
            window[sample * C + channel] = sine + noise;
        }
    }
}
```

**Rationale:**

Synthetic data avoids file I/O and ensures validation is fast enough to run on every `cortex pipeline` invocation. Deterministic generation enables reproducible validation failures.

**Normative Requirements:**

1. Implementations MUST use reproducible random generation (e.g., seeded std::mt19937) for synthetic data
2. Test data MUST cover the kernel's input domain (at least one example of typical values)
3. Test data SHOULD NOT be purely zero or constant (would miss numerical errors)

### 7.2.4 Pass/Fail Criteria

Validation passes if all output elements are within specified tolerances:

**Relative Tolerance (rtol):**
```
|kernel_output - oracle_output| ≤ rtol * |oracle_output|
```

**Absolute Tolerance (atol):**
```
|kernel_output - oracle_output| ≤ atol
```

**Combined Criterion (element-wise):**
```
|diff| ≤ atol + rtol * |oracle_output|
```

where `diff = kernel_output - oracle_output`.

Validation PASSES if the combined criterion is satisfied for ALL output elements.
Validation FAILS if ANY element exceeds the tolerance threshold.

**Normative Requirements:**

1. Implementations MUST apply both rtol and atol checks (combined criterion above)
2. Implementations MUST compare element-wise (all elements must pass)
3. Implementations MUST use the tolerances from `kernel.numerical.tolerances` for the tested dtype
4. Implementations MUST consider NaN outputs as failures (NaN != NaN always)
5. Implementations MUST consider Inf outputs as failures unless explicitly allowed by kernel spec

**Example Validation Checks:**

For a kernel with `rtol: 1.0e-5, atol: 1.0e-6`:

| Kernel Output | Oracle Output | |diff| | |diff| ≤ criterion | Status |
|-------|-------|-------|-------|-------|
| 1.00001 | 1.0 | 0.00001 | 0.00001 ≤ 1.0e-5 + 1.0e-5 * 1.0 = 2.0e-5 | PASS |
| 0.99990 | 1.0 | 0.00010 | 0.00010 ≤ 2.0e-5 | FAIL |
| 1e-8 | 0.0 | 1e-8 | 1e-8 ≤ 1.0e-6 (atol dominates) | PASS |
| 1.00001 | 1e-20 | 1.00001 | 1.00001 ≤ 1.0e-5 + 1.0e-5 * 1e-20 ≈ 1.0e-5 | FAIL |

### 7.2.5 Failure Reporting

When validation fails, implementations MUST log diagnostic information:

```json
{
  "kernel": "notch_iir@f32",
  "status": "FAILED",
  "dtype": "float32",
  "reason": "Element-wise tolerance exceeded",
  "error_count": 42,
  "error_rate": 0.0041,
  "first_failure": {
    "window_index": 0,
    "element_index": 128,
    "channel": 2,
    "sample": 0,
    "kernel_value": 1.000123,
    "oracle_value": 0.999990,
    "error": 0.000133,
    "criterion": 1.0e-5,
    "rtol": 1.0e-5,
    "atol": 1.0e-6
  },
  "max_error": {
    "value": 0.000567,
    "criterion": 1.0e-5,
    "ratio": 56.7
  },
  "statistics": {
    "total_elements": 10240,
    "failed_elements": 42,
    "mean_error": 0.000145,
    "max_error": 0.000567,
    "passed_check": false
  }
}
```

**Normative Requirements:**

1. Implementations MUST record the first failing element with full details
2. Implementations MUST record the maximum error and its ratio to the tolerance criterion
3. Implementations MUST report error rate (failed_elements / total_elements)
4. Implementations MUST include all tolerances used in the diagnostic
5. Implementations MUST distinguish numerical failures (tolerance exceeded) from structural failures (shape mismatch, exception)

### 7.2.6 Stateful Kernel Validation

For kernels with `abi.stateful: true`, validation MUST verify state persistence across windows:

```python
# Pseudocode for stateful kernel validation
oracle_state = oracle_init()  # Initialize oracle state
kernel_state = cortex_kernel_init()  # Initialize kernel state

for window_idx in range(3):  # Test 3 windows
    input_data = generate_test_window()
    
    # Run oracle and kernel with state
    oracle_out, oracle_state = oracle_func(input_data, state=oracle_state)
    kernel_out = kernel_func(input_data, state=kernel_state)
    
    # Validate output
    if not validate_output(oracle_out, kernel_out, tolerances):
        return FAILED
    
    # Update kernel state for next window
    kernel_state = cortex_kernel_get_state()

return PASSED
```

**Normative Requirements:**

1. For stateful kernels, validation MUST test at least 3 consecutive windows
2. Implementations MUST initialize oracle and kernel state identically (typically zeros)
3. Implementations MUST verify that oracle and kernel state evolve identically
4. Implementations MUST reset state between validation runs to prevent cross-contamination

---

## 7.3 Oracle Implementation

### 7.3.1 Oracle Requirements

Each kernel MUST provide a Python reference implementation in `oracle.py`. The oracle MUST satisfy the following requirements:

1. **Correctness**: Implements the exact algorithm (numerically equivalent to reference papers)
2. **Signature**: Function signature MUST match `def oracle_function(input_array, **kwargs)`
3. **Input/Output**: Accepts numpy arrays, returns numpy arrays with identical dtype
4. **Dependencies**: MUST declare all imports in `spec.yaml` `oracle.dependencies`
5. **Determinism**: Identical inputs MUST produce identical outputs (no randomness)

**Function Signature:**

```python
def oracle_function(x, **kwargs) -> np.ndarray:
    """
    Reference implementation of kernel algorithm.
    
    Args:
        x: Input array of shape (W, C) where W=window samples, C=channels
        **kwargs: Optional algorithm parameters (frequency bands, filter coefficients, etc.)
    
    Returns:
        y: Output array matching kernel's expected shape
    """
    # Implementation
    return y.astype(np.float32)  # Always cast to output dtype
```

**Normative Requirements:**

1. Oracle functions MUST accept a numpy array as first argument
2. Oracle functions MUST accept arbitrary keyword arguments via `**kwargs`
3. Oracle functions MUST return numpy arrays with the same dtype as kernel output
4. Oracle functions MUST be deterministic (no random state, no time-dependent behavior)
5. Oracle functions MUST handle both single-window and state persistence correctly

### 7.3.2 Example: Stateless Oracle (Goertzel)

```python
#!/usr/bin/env python3
"""
Goertzel Bandpower Oracle

Reference implementation for Goertzel bandpower kernel validation.
Computes power in specified frequency bands using Goertzel algorithm.
"""

import numpy as np


def goertzel_bandpower_ref(x, fs=160.0, bands=None, **kwargs):
    """
    Compute bandpower using Goertzel algorithm (reference implementation).
    
    This is the oracle for the Goertzel bandpower kernel.
    
    Args:
        x: Input array of shape (W, C) in µV (float32)
        fs: Sampling rate (Hz). Default: 160.0
        bands: Dictionary of {name: (low, high)} frequency bands in Hz.
               Default: {'alpha':(8,13), 'beta':(13,30)}
        **kwargs: Additional parameters (ignored)
    
    Returns:
        Array of shape (B, C) in µV² (float32) where B = number of bands
        
    Algorithm:
        For each frequency bin within the band:
        - Compute Goertzel coefficient: coeff = 2 * cos(2π * k / N)
        - Run Goertzel recurrence: s[n] = x[n] + coeff * s[n-1] - s[n-2]
        - Compute power: P_k = s₁² + s₂² - coeff * s₁ * s₂
        - Sum powers over all bins in band
    """
    if bands is None:
        bands = {'alpha': (8, 13), 'beta': (13, 30)}
    
    N = x.shape[0]  # Window length
    C = x.shape[1]  # Channel count
    B = len(bands)  # Number of bands
    
    out = np.zeros((B, C), dtype=np.float32)
    
    for band_idx, (band_name, (lo, hi)) in enumerate(bands.items()):
        # Convert Hz frequency bands to bin indices
        k_start = round(lo * N / fs)
        k_end = round(hi * N / fs)
        ks = np.arange(k_start, k_end + 1, dtype=float)
        
        if len(ks) == 0:
            # Empty band - output zeros
            out[band_idx, :] = 0.0
            continue
        
        # Precompute Goertzel coefficients: coeff[k] = 2*cos(2π*k/N)
        omega = 2 * np.pi * ks / N
        coeff = 2 * np.cos(omega)[:, None]  # Shape: (num_bins, 1)
        
        # Run Goertzel recurrence for all bins and channels simultaneously
        s0 = np.zeros((len(ks), C))
        s1 = np.zeros((len(ks), C))
        s2 = np.zeros((len(ks), C))
        
        for n in range(N):
            s0 = x[n][None, :] + coeff * s1 - s2
            s2, s1 = s1.copy(), s0.copy()
        
        # Compute power: P_k = s1² + s2² - coeff*s1*s2 for each bin
        Pk = s1 * s1 + s2 * s2 - coeff * s1 * s2
        
        # Sum powers across all bins in the band
        out[band_idx, :] = Pk.sum(axis=0).astype(np.float32)
    
    return out.astype(np.float32)


if __name__ == "__main__":
    # Example usage
    np.random.seed(42)
    W, C = 160, 64
    
    # Generate synthetic data with known frequency content
    t = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 10 * t)[:, None] * 50   # 10 Hz in alpha band
        + np.sin(2 * np.pi * 20 * t)[:, None] * 30  # 20 Hz in beta band
        + np.random.randn(W, C).astype(np.float32) * 5  # noise
    )
    
    y = goertzel_bandpower_ref(x)
    
    print(f"Goertzel Bandpower Oracle Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Alpha band power (should be > beta): {y[0].mean():.2f}")
    print(f"Beta band power: {y[1].mean():.2f}")
```

**Key Characteristics:**

- **Stateless**: No persistent state across calls
- **Deterministic**: Identical inputs always produce identical outputs
- **Vectorized**: Uses numpy operations for efficiency
- **Clear Parameters**: Frequency bands passed as kwargs

### 7.3.3 Example: Stateful Oracle (Notch IIR)

```python
#!/usr/bin/env python3
"""
Notch IIR Filter Oracle

Reference implementation for notch IIR kernel validation.
Maintains filter state across windows for continuous operation.
"""

import numpy as np
from scipy.signal import iirnotch, lfilter


def notch_ref(x, fs=160.0, f0=60.0, Q=30.0, zi=None, **kwargs):
    """
    Apply notch IIR filter with state management (reference implementation).
    
    This is the oracle for the notch IIR kernel (stateful).
    
    Args:
        x: Input array of shape (W, C) in µV (float32)
        fs: Sampling rate (Hz). Default: 160.0
        f0: Notch frequency (Hz). Default: 60.0
        Q: Quality factor (determines notch width). Default: 30.0
        zi: Initial filter state. Shape (2, C) for biquad. 
            If None, initialized to zeros (first window).
        **kwargs: Additional parameters (ignored)
    
    Returns:
        Tuple: (y, zf) where:
        - y: Filtered output of shape (W, C) in µV (float32)
        - zf: Final filter state for next window (float32)
        
    Algorithm:
        1. Compute biquad coefficients using scipy.signal.iirnotch()
        2. Apply cascade of biquad sections via lfilter() with state
        3. Return both output and final state for state persistence
    """
    # Compute notch filter coefficients (normalized frequency response)
    b, a = iirnotch(f0, Q, fs=fs)
    
    # Initialize state if not provided
    if zi is None:
        zi = np.zeros((2, x.shape[1]), dtype=np.float32)
    
    # Apply IIR filter with persistent state
    # lfilter returns (output, final_state)
    y, zf = lfilter(b, a, x, axis=0, zi=zi)
    
    return y.astype(np.float32), zf.astype(np.float32)


if __name__ == "__main__":
    # Example usage
    np.random.seed(42)
    W, C = 160, 64
    
    # Generate synthetic data with 60 Hz contamination
    t = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 60 * t)[:, None] * 10  # 60 Hz (power line)
        + np.sin(2 * np.pi * 10 * t)[:, None] * 20  # 10 Hz signal
        + np.random.randn(W, C).astype(np.float32) * 5  # noise
    )
    
    # Apply notch filter
    y, zf = notch_ref(x, fs=160.0, f0=60.0, Q=30.0)
    
    print(f"Notch IIR Oracle Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Filter state shape: {zf.shape}")
    print(f"60 Hz component attenuated (should see less power at 60 Hz)")
```

**Key Characteristics:**

- **Stateful**: Returns both output and final filter state
- **State Persistence**: Final state `zf` becomes initial state `zi` for next window
- **Scipy Integration**: Uses scipy.signal for numerical stability
- **Coupled Output**: Returns (output, state) tuple

### 7.3.4 Oracle Configuration in spec.yaml

Oracles are configured in the kernel's `spec.yaml`:

```yaml
oracle:
  path: "oracle.py"                    # REQUIRED: Path to oracle script
  function: "goertzel_bandpower_ref"   # REQUIRED: Function name
  dependencies:                        # OPTIONAL: Required packages
    - numpy
    - scipy

numerical:
  tolerances:
    float32:
      rtol: 1.0e-5
      atol: 1.0e-6
    quantized:                         # For Q15/Q7 variants
      rtol: 1.0e-3
      atol: 1.0e-3
```

**Normative Requirements:**

1. `oracle.path` MUST point to an existing Python file in the kernel directory
2. `oracle.function` MUST name an existing function in the oracle module
3. `oracle.dependencies` MUST list all packages imported by the oracle (for pip install)
4. If `oracle.dependencies` is omitted, numpy MUST be assumed as implicit dependency
5. Implementations MUST verify oracle function exists before attempting validation

### 7.3.5 Oracle CLI Interface (Optional)

Oracles MAY provide a CLI interface for standalone testing:

```bash
python3 oracle.py --test <input_file> --output <output_file> [--state <state_file>]
```

**Normative Requirements:**

1. CLI interface is OPTIONAL and not required for validation
2. If CLI is provided, it MUST support `--test <input_file>` and `--output <output_file>` arguments
3. For stateful kernels, CLI SHOULD support `--state <state_file>` for state persistence
4. CLI MUST read input as raw float32 binary and write output in identical format

---

## 7.4 Multi-Dtype Validation

### 7.4.1 Dtype Variants

CORTEX v1.0 supports multiple data type representations:

| Dtype | Bit Width | Range | Use Case | Tolerance |
|-------|-----------|-------|----------|-----------|
| `float32` | 32 | ±3.4e38 | Reference, high precision | 1.0e-5 rtol |
| `q15` | 16 | ±1.0 | Fixed-point DSP, low power | 1.0e-3 rtol |
| `q7` | 8 | ±1.0 | Extreme low-power, edge devices | 1.0e-3 rtol |

Each dtype has its own kernel variant and oracle implementation.

**Normative Requirements:**

1. Implementations MUST validate each dtype variant independently
2. Implementations MUST NOT mix dtype comparisons (float32 oracle with Q15 kernel)
3. Each kernel variant MUST have corresponding oracle implementation in the same directory

### 7.4.2 Quantized Dtype Validation

For fixed-point kernels (Q15, Q7), validation uses relaxed tolerances to account for quantization error:

**Q15 Fixed-Point Format:**
- 16 bits total: 1 sign + 15 fractional
- Represents values in [-1.0, 1.0) with LSB = 2^-15 ≈ 3.05e-5
- Quantization error: ±LSB/2 ≈ ±1.5e-5

**Q7 Fixed-Point Format:**
- 8 bits total: 1 sign + 7 fractional
- Represents values in [-1.0, 1.0) with LSB = 2^-7 ≈ 0.0078
- Quantization error: ±LSB/2 ≈ ±0.0039

**Example Tolerances in spec.yaml:**

```yaml
numerical:
  tolerances:
    float32:
      rtol: 1.0e-5    # ~1 ULP for float32
      atol: 1.0e-6
    quantized:        # For both Q15 and Q7
      rtol: 1.0e-3    # Allow 0.1% relative error
      atol: 1.0e-3    # ~1-2 LSBs of quantization
```

**Normative Requirements:**

1. Quantized variants MUST use oracle function that converts float32 reference to fixed-point
2. Quantized validation MUST account for quantization LSB and rounding
3. Quantized tolerances (rtol=1e-3) MAY be 100× larger than float32 (rtol=1e-5)
4. Implementations MUST clearly distinguish dtype variant in validation reports

### 7.4.3 Cross-Dtype Consistency Checking

Optional: Implementations MAY verify that quantized variants preserve relative ordering:

```python
# Pseudocode for cross-dtype consistency
float32_out = kernel_float32(input_data)
q15_out = kernel_q15(input_data)

# Check that quantized output maintains monotonicity
# (if oracle_out[i] > oracle_out[j], then q15_out[i] ≥ q15_out[j])
for i in range(len(float32_out)):
    for j in range(i + 1, len(float32_out)):
        if float32_out[i] > float32_out[j]:
            assert q15_out[i] >= q15_out[j], \
                f"Monotonicity violated: float32[{i}] > float32[{j}] " \
                f"but q15[{i}]={q15_out[i]} < q15[{j}]={q15_out[j]}"
```

**Normative Requirements:**

1. Cross-dtype consistency checking is OPTIONAL (not required for v1.0)
2. If implemented, MUST be reported separately from individual dtype validation
3. Monotonicity violations SHOULD be reported as warnings, not failures

---

## 7.5 Validation Report Format

Implementations MUST output validation results in NDJSON format to `{output_directory}/validation_report.json`. Each line is a complete JSON object describing one kernel's validation.

### 7.5.1 Validation Report Schema

```json
{
  "timestamp": "2026-02-01T14:30:00Z",
  "kernel": "notch_iir@f32",
  "status": "PASSED",
  "dtype": "float32",
  "run_id": "validation_1704145200",
  "oracle_config": {
    "path": "oracle.py",
    "function": "notch_ref",
    "dependencies": ["scipy"]
  },
  "validation_config": {
    "windows_tested": 3,
    "samples_per_window": 160,
    "channels": 64,
    "total_elements": 30720
  },
  "tolerances": {
    "rtol": 1.0e-5,
    "atol": 1.0e-6
  },
  "results": {
    "passed": true,
    "total_elements": 30720,
    "failed_elements": 0,
    "error_rate": 0.0,
    "statistics": {
      "mean_error": 0.0,
      "max_error": 2.1e-6,
      "min_error": 0.0,
      "std_error": 4.5e-7
    }
  }
}
```

### 7.5.2 Failure Report Schema

```json
{
  "timestamp": "2026-02-01T14:30:00Z",
  "kernel": "broken_kernel@f32",
  "status": "FAILED",
  "dtype": "float32",
  "run_id": "validation_1704145200",
  "oracle_config": {
    "path": "oracle.py",
    "function": "broken_ref",
    "dependencies": ["numpy"]
  },
  "validation_config": {
    "windows_tested": 3,
    "samples_per_window": 160,
    "channels": 64,
    "total_elements": 30720
  },
  "tolerances": {
    "rtol": 1.0e-5,
    "atol": 1.0e-6
  },
  "error_type": "TOLERANCE_EXCEEDED",
  "error_message": "Element-wise tolerance exceeded in 42 elements",
  "results": {
    "passed": false,
    "total_elements": 30720,
    "failed_elements": 42,
    "error_rate": 0.001366,
    "statistics": {
      "mean_error": 0.000145,
      "max_error": 0.000567,
      "min_error": 0.0,
      "std_error": 0.000089
    }
  },
  "first_failure": {
    "window_index": 1,
    "element_index": 512,
    "channel": 8,
    "sample": 0,
    "kernel_value": 1.000123,
    "oracle_value": 0.999990,
    "absolute_error": 0.000133,
    "relative_error": 0.000133,
    "criterion": 2.0e-5,
    "tolerance_exceeded_by": 1.15
  },
  "recommendations": [
    "Check kernel implementation for off-by-one errors in indexing",
    "Verify filter coefficients match oracle specification",
    "Test with constant input to isolate algorithmic errors"
  ]
}
```

**Normative Requirements:**

1. Implementations MUST write one JSON object per line (NDJSON format)
2. Implementations MUST include `timestamp` (ISO 8601 UTC) for each record
3. For PASSED status, `results.passed` MUST be true and `failed_elements` MUST be 0
4. For FAILED status, implementations MUST include `error_type` and `first_failure` details
5. Implementations MUST include diagnostic `recommendations` for failed kernels

---

## 7.6 Conformance and Testing

### 7.6.1 Validation Conformance

An implementation conforms to this specification if:

1. It validates all kernels before measurement (unless `--no-validate` flag used)
2. It correctly implements the tolerance criterion (combined rtol + atol)
3. It handles both stateless and stateful kernels correctly
4. It produces validation reports in NDJSON format
5. It gracefully handles missing or broken oracle implementations
6. It supports multi-dtype tolerances for float32, Q15, Q7 variants

### 7.6.2 Test Validation

Implementations SHOULD run the following self-tests to verify oracle validation:

**Test 1: Float32 Tolerance Check**
```
Input: Known oracle/kernel pair with 1e-6 relative error
Expected: PASSED (within rtol=1e-5)
```

**Test 2: Tolerance Overage**
```
Input: Known oracle/kernel pair with 1e-4 relative error
Expected: FAILED (exceeds rtol=1e-5)
```

**Test 3: Stateful Kernel**
```
Input: Notch IIR filter over 3 windows with state persistence
Expected: PASSED if all windows validate and state evolves correctly
```

**Test 4: Oracle Import Failure**
```
Input: Nonexistent oracle.py file
Expected: FAILED with clear error message
```

---

## 7.7 Rationale

### 7.7.1 Why Oracle Validation Before Measurement?

Performance benchmarks only make sense if kernels are correct. Measuring a broken implementation wastes time and produces misleading results. Pre-measurement validation ensures:

1. **Correctness Guarantee**: Benchmarks measure optimization quality, not algorithmic errors
2. **Fail-Fast**: Developers discover mistakes immediately, not after a 2-hour benchmark run
3. **Reproducibility**: Validation with synthetic data is fast and deterministic
4. **Documentation**: Oracle serves as executable specification of expected behavior

### 7.7.2 Why Combined Tolerance Criterion?

The combined `rtol + atol` criterion handles both large and small values correctly:

- **Large values**: Relative tolerance dominates (e.g., rtol error of 1e-5 * 1e6 = 10 is acceptable)
- **Small values**: Absolute tolerance dominates (e.g., atol = 1e-6 when values near zero)
- **Balanced**: Avoids false positives (rejecting correct small values) and false negatives (accepting large errors)

This is the standard criterion used in numpy's `allclose()` and accepted across numerical computing.

### 7.7.3 Why Separate Quantized Tolerances?

Fixed-point arithmetic introduces unavoidable quantization error:

- **Q15**: LSB = 2^-15 ≈ 3e-5, so 1e-3 rtol is reasonable
- **Q7**: LSB = 2^-7 ≈ 7.8e-3, so 1e-3 rtol is reasonable

Using float32 tolerances (1e-5) for quantized implementations would reject correct conversions. Separate tolerances acknowledge the fundamental precision differences.

### 7.7.4 Why Python for Oracles?

Python provides:

1. **Accessibility**: Researchers can implement oracles without C expertise
2. **Libraries**: scipy, numpy provide battle-tested reference implementations
3. **Performance**: Adequate for validation (one-time per kernel, not in measurement loop)
4. **Debugging**: Easy to inspect oracle behavior and trace through algorithm

---

## 7.8 Implementation Checklist

Implementations SHOULD verify the following before claiming oracle validation conformance:

- [ ] Oracle functions imported correctly from kernel's `oracle.py`
- [ ] Test data generation is deterministic (reproducible across runs)
- [ ] Combined tolerance criterion implemented (rtol + atol)
- [ ] Element-wise comparison (all elements must pass)
- [ ] Stateful kernels tested over 3+ consecutive windows
- [ ] State persistence works correctly (final state becomes initial state)
- [ ] Failure reports include first failure details and diagnostics
- [ ] NDJSON output written to `{output_directory}/validation_report.json`
- [ ] Per-dtype tolerances applied correctly (float32 vs. quantized)
- [ ] NaN/Inf outputs treated as failures
- [ ] Validation skipped if `--no-validate` flag set
- [ ] Kernels with failed validation excluded from measurement

---

**End of Section 7**
