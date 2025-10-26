# Common Average Reference (CAR)

## Overview

Common Average Reference is a spatial filtering technique that subtracts the mean across channels at each time point, removing common-mode noise and centering the data.

**Use case**: Preprocessing step for EEG signal analysis to reduce shared artifacts and improve signal-to-noise ratio.

## Signal Model

Input `x[t,c]` with shape `[W×C]` in µV → Output `y[t,c]` with shape `[W×C]` in µV.

Let `G` be the set of good channels (default all 64):

$$\bar{x}[t] = \frac{1}{|G|}\sum_{c\in G} x[t,c], \qquad
y[t,c] = x[t,c] - \bar{x}[t]$$

At each time point `t`, compute the mean across all good channels, then subtract that mean from each channel.

## Parameters

- `G`: Set of good channels (default: all C channels)

## Edge Cases

- **NaN handling**: At time `t`, exclude channels where `x[t,c]` is NaN from the mean calculation and divisor. If all channels are NaN at `t`, output zeros.
- **Missing/bad channels**: Excluded from CAR mean calculation; treated independently.

## Acceptance Criteria

- Float32 vs oracle within `rtol=1e-5`, `atol=1e-6`
- Mean across channels ≈ 0 at each `t` (|mean| < 1e-4 µV)

## Real-time Budget

- **Expected latency**: < 50 ms per window (stateless, simple mean subtraction)
- **Memory footprint**: No persistent state
- **Throughput**: High (O(W×C) operations)

## Usage

Reference in `cortex.yaml`:

```yaml
plugins:
  - name: "car"
    spec_uri: "kernels/v1/car@f32"
    spec_version: "1.0.0"
    runtime:
      window_length_samples: 160
      hop_samples: 80
      channels: 64
      dtype: "float32"
      allow_in_place: true
    params: {}  # CAR has no kernel-specific parameters
```

## Reference

See `docs/KERNELS.md` section "Common Average Reference (CAR)" for the complete mathematical specification.

## Implementation Status

- ✅ Specification defined
- ✅ Oracle implementation (`oracle.py`)
- ⏳ C implementation pending

