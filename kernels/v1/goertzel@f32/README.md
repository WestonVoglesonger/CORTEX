# Goertzel Bandpower

## Overview

Goertzel algorithm for computing bandpower in specified frequency bands. Operates per window (stateless) and outputs power spectral density estimates.

**Use case**: Extract alpha (8-13 Hz) and beta (13-30 Hz) bandpower features for BCI classification.

## Signal Model

Input [W×C] µV → Output [B×C] µV², where B = number of defined bands.

For window length N = W = 160 and bin k (frequency = `f_k = k*F_s/N = k` Hz at Fs=160):

**Recurrence relation**:
$$s[n] = x[n] + 2 cos (\frac{2 \pi k}{N})s[n-1]-s[n-2]$$

**Power computation**:
$$P_k = s[N-1]^2 + s[N-2]^2 - 2cos(\frac{2 \pi k}{N})s[N-1]s[N-2]$$

**Bandpower**: Sum of `P_k` over bins in the band.

## Parameters

- `bands`: Dictionary of band names and frequency ranges
  - Default: `{'alpha':(8,13), 'beta':(13,30)}`
  - Produces B=2 bands
- `fs`: Sampling rate (Hz). Fixed at 160 Hz

## Output Shape

The algorithm outputs [B×C] where:
- B = number of bands (default: 2 for alpha + beta)
- C = number of channels (64)

Each element `y[b,c]` is the bandpower for band `b` and channel `c`.

## Edge Cases

- **Stateless**: Operates on each window independently (no state persists)
- **Frequency resolution**: With N=160 and Fs=160 Hz, frequency resolution is 1 Hz/bin
- **Band definition**: Bins at boundaries are included (e.g., alpha band includes both 8 Hz and 13 Hz bins)

## Acceptance Criteria

- Match oracle within `rtol=1e-5`, `atol=1e-6`
- Cross-check: FFT method (`np.fft.rfft`) bin-sum within same tolerance on a test window

## Real-time Budget

- **Expected latency**: < 150 ms per window (recurrence for each bin)
- **Memory footprint**: O(C × number_of_bins) scratch space, no persistent state
- **Throughput**: Moderate (vectorized recurrence across bins)

## Usage

Reference in `cortex.yaml`:

```yaml
plugins:
  - name: "goertzel"
    spec_uri: "kernels/v1/goertzel@f32"
    spec_version: "1.0.0"
    runtime:
      window_length_samples: 160
      hop_samples: 80
      channels: 64
      dtype: "float32"
      allow_in_place: false  # Output shape differs from input
    params: {}  # Band definitions are fixed in default implementation
```

## Reference

See `docs/KERNELS.md` section "Goertzel Bandpower" for the complete mathematical specification.

## Implementation Status

- ✅ Specification defined
- ✅ Oracle implementation (`oracle.py`)
- ✅ C implementation complete and tested

