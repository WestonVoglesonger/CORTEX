# Bandpass FIR Filter

## Overview

Linear-phase FIR bandpass filter for isolating EEG frequency bands (8-30 Hz). Uses Hamming window design with persistent tail across windows.

**Use case**: Isolate alpha (8-13 Hz) and beta (13-30 Hz) bands for BCI feature extraction.

## Signal Model

Input [W×C] µV → Output [W×C] µV, linear-phase FIR with known delay and persistent tail across windows.

Length-N FIR with taps `b[k]`, `k=0..N−1` (Hamming window design):

$$y[n] = \sum_{k=0}^{N-1} b[k] x[n−k]$$

Designed via: `firwin(N=129, [8,30], pass_zero=False, fs=160, window='hamming')`.

## Parameters

- `numtaps`: Number of filter coefficients. Fixed at 129
- `passband`: Passband frequencies (Hz). Fixed at [8, 30] Hz
- `window`: Window type. Fixed at 'hamming'
- `fs`: Sampling rate (Hz). Fixed at 160 Hz

## Group Delay

Group delay = `(N−1)/2 = 64` samples = 0.4 s @ 160 Hz.

**Important**: The output is delayed by 64 samples relative to the input. This must be accounted for in real-time systems.

## Edge Cases

- **Zero-init tail**: FIR state (tail) is zero-initialized on first window
- **Tail persistence**: FIR keeps last `numtaps−1` samples per channel across windows
- **NaN handling**: NaNs treated as 0
- **Boundary conditions**: First window has no history; tail builds over subsequent windows

## Acceptance Criteria

- Samplewise `rtol=1e-5`, `atol=1e-6` vs oracle (with identical carried tail)

## Real-time Budget

- **Expected latency**: < 200 ms per window (convolution: O(W × numtaps))
- **Memory footprint**: `(numtaps-1) × C × sizeof(float)` = `128 × 64 × 4` = 32 KB per instance
- **Throughput**: Moderate (FIR convolution, higher than IIR per sample but not recursive)

## Usage

Reference in `cortex.yaml`:

```yaml
plugins:
  - name: "bandpass_fir"
    spec_uri: "kernels/v1/bandpass_fir@f32"
    spec_version: "1.0.0"
    runtime:
      window_length_samples: 160
      hop_samples: 80
      channels: 64
      dtype: "float32"
      allow_in_place: false  # Output delayed by 64 samples
    params: {}  # Parameters are fixed by design
```

**Note**: Due to group delay, the output lags the input by 64 samples. In real-time systems, this creates a latency of 0.4 seconds.

## Reference

See `docs/KERNELS.md` section "Band-pass FIR (8–30 Hz)" for the complete mathematical specification.

## Implementation Details

### Coefficient Precision

The FIR coefficients are **stored as `double` precision** in the C implementation to match Python's `lfilter` internal precision. This ensures exact numerical agreement with the oracle reference implementation, which uses `scipy.signal.lfilter` that operates with double precision coefficients internally.

**Key points:**
- Coefficients are pre-computed using `scipy.signal.firwin(129, [8, 30], pass_zero=False, fs=160, window='hamming')`
- Stored as `double` precision constants in `bandpass_fir.c`
- Output is still `float32` (matching the spec requirement)
- Accumulation performed in `double` precision for accuracy
- Final result cast to `float32` for output

### State Management

The filter maintains a **tail buffer** of the last `numtaps-1` (128) input samples per channel across windows. This enables continuous filtering without discontinuities.

**Implementation:**
- Tail buffer: `(numtaps-1) × channels` float32 values
- Tail is zero-initialized on first window
- After processing each window, the last `numtaps-1` input samples are copied to the tail buffer
- During convolution, samples from before the current window are read from the tail buffer

**Convolution algorithm:**
- For sample `t` at position `n` in the current window:
  - For `k ≤ t`: Use sample from current window at position `(t-k)`
  - For `k > t`: Use sample from tail buffer at index `tail_len - (k - t)`

This ensures proper state persistence across windows and matches the oracle's behavior when prepending the tail to the input.

## Correctness Validation

### Test Methodology

The C implementation is validated against the Python oracle reference implementation using the `test_kernel_accuracy` test suite. The validation process:

1. **Data Loading**: Loads real EEG data from the test dataset (e.g., `S001R03.float32`)
2. **Parallel Processing**: Processes the same windows through both the C kernel and Python oracle
3. **State Management**: Maintains identical tail buffer state across windows for both implementations
4. **Numerical Comparison**: Compares outputs sample-by-sample with strict tolerances

### Tolerances

The implementation must match the oracle within:
- **Relative tolerance**: `rtol = 1e-5` (0.00001)
- **Absolute tolerance**: `atol = 1e-6` (0.000001)

A sample passes if both conditions are met:
- `abs_err > atol AND rel_err > rtol` → mismatch
- Otherwise → match

### Validation Results

**Status**: ✅ **All tests pass** with exact numerical agreement

The implementation achieves exact matches with the oracle when:
- Coefficients are stored as `double` precision (matching Python's `lfilter` internal precision)
- Accumulation is performed in `double` precision
- Final result is cast to `float32` for output

**Test coverage:**
- ✅ Multi-window state persistence (tail buffer management)
- ✅ First window handling (zero-initialized tail)
- ✅ Subsequent windows (carried tail state)
- ✅ Edge cases (NaN handling, boundary conditions)
- ✅ Real EEG data (not just synthetic test cases)

### Running Tests

```bash
# Test FIR bandpass accuracy
./tests/test_kernel_accuracy --kernel bandpass_fir --windows 10 --verbose

# Test registry (validates kernel structure)
./tests/test_kernel_registry
```

### Oracle Reference

The oracle (`oracle.py`) uses `scipy.signal.firwin` to generate coefficients and `scipy.signal.lfilter` for filtering. The C implementation matches this reference exactly, including:
- Same filter design parameters (`numtaps=129`, `passband=[8, 30] Hz`, `window='hamming'`)
- Same state management approach (tail buffer persistence)
- Same numerical precision (double precision coefficients internally)

## Implementation Status

- ✅ Specification defined
- ✅ Oracle implementation (`oracle.py`)
- ✅ C implementation complete
- ✅ Correctness validated (all tests pass)

