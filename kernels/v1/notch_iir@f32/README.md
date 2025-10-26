# Notch IIR Filter

## Overview

Second-order IIR notch filter for removing power line interference (50/60 Hz). Implemented as a per-channel biquad with persistent state across windows.

**Use case**: Remove power line noise from EEG signals.

## Signal Model

Input [W×C] µV → Output [W×C] µV, per-channel IIR with **persistent** state across windows.

Second-order notch with target frequency `f0` and quality factor `Q`:

$$H(Z) = \frac{1-2cos(w_0)z^{-1}+z^{-2}}{1-2rcos(w_0)z^{-1}+r^{2}z^{-2}}, \qquad w_0 = \frac{2 \pi f_0}{F_s}$$

Difference equation per channel:

$$y[n]=b_0 x[n]+b_1 x[n−1]+b_2 x[n−2]−a_1 y[n−1]−a_2 y[n−2]$$

Coefficients `(b,a)` are designed via standard notch designer (e.g., SciPy `iirnotch`).

## Parameters

- `f0`: Notch frequency (Hz). Default: 60.0 Hz (or 50.0 Hz for 50 Hz power grids)
- `Q`: Quality factor (dimensionless). Default: 30.0
- `fs`: Sampling rate (Hz). Fixed at 160 Hz

The notch attenuation depends on Q: higher Q = narrower notch, lower Q = wider notch.

## Edge Cases

- **NaN handling**: Treat NaNs as 0 for filtering purposes
- **State persistence**: IIR state **persists** across windows for continuous filtering
- **First window**: IIR states are zero-initialized
- **Invalid config**: Reject configs where `f0 ≈ 0`

## Acceptance Criteria

- Samplewise match within `rtol=1e-5`, `atol=1e-6` vs oracle (with identical state)

## Real-time Budget

- **Expected latency**: < 100 ms per window (matrix multiply per sample)
- **Memory footprint**: 8 bytes per channel (biquad state: x[n-1], x[n-2], y[n-1], y[n-2])
- **Throughput**: Moderate (per-sample recurrence)

## Usage

Reference in `cortex.yaml`:

```yaml
plugins:
  - name: "notch_iir"
    spec_uri: "kernels/v1/notch_iir@f32"
    spec_version: "1.0.0"
    runtime:
      window_length_samples: 160
      hop_samples: 80
      channels: 64
      dtype: "float32"
      allow_in_place: false  # Output may differ significantly from input
    params:
      f0_hz: 60.0
      Q: 30.0
```

## Reference

See `docs/KERNELS.md` section "Notch IIR (biquad) at 50/60 Hz" for the complete mathematical specification.

## Implementation Status

- ✅ Specification defined
- ✅ Oracle implementation (`oracle.py`)
- ⏳ C implementation pending

