# FIR Bandpass Filter

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
  - name: "fir_bandpass"
    spec_uri: "kernels/v1/fir_bandpass@f32"
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

## Implementation Status

- ✅ Specification defined
- ✅ Oracle implementation (`oracle.py`)
- ⏳ C implementation pending

