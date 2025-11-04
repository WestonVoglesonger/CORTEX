# Goertzel Bandpower

## Overview

Goertzel algorithm for computing bandpower in specified frequency bands. Operates per window (stateless) and outputs power spectral density estimates.

**Use case**: Extract alpha (8-13 Hz) and beta (13-30 Hz) bandpower features for BCI classification.

## Signal Model

Input [W×C] µV → Output [B×C] µV², where B = number of defined bands.

For window length N = W and bin k, frequency = `f_k = k*F_s/N`.

**Frequency-to-bin conversion**: Frequency bands (Hz) are converted to bin indices using `k = round(f * N / Fs)`. This allows the kernel to work correctly with any sample rate and window length.

**Recurrence relation**:
$$s[n] = x[n] + 2 cos (\frac{2 \pi k}{N})s[n-1]-s[n-2]$$

**Power computation**:
$$P_k = s[N-1]^2 + s[N-2]^2 - 2cos(\frac{2 \pi k}{N})s[N-1]s[N-2]$$

**Bandpower**: Sum of `P_k` over bins in the band.

## Parameters

- `bands`: Dictionary of band names and frequency ranges (in Hz)
  - Default: `{'alpha':(8,13), 'beta':(13,30)}`
  - Produces B=2 bands
  - Bands are converted to bin indices based on configured `Fs` and `N`
- `fs`: Sampling rate (Hz). Supports any sample rate (not limited to 160 Hz)
- Window length `N`: Supports any window length (not limited to 160 samples)

## Output Shape

The algorithm outputs [B×C] where:
- B = number of bands (default: 2 for alpha + beta)
- C = number of channels (from runtime config)

Each element `y[b,c]` is the bandpower for band `b` and channel `c`.

## Dynamic Configuration

The kernel supports dynamic channel counts and window lengths via runtime config:

- **Channels**: `output_channels` matches `input_channels` and both use the runtime `config->channels` value (not hardcoded)
- **Window length**: Uses runtime `config->window_length_samples` value (not hardcoded)
- **Sample rate**: Uses runtime `config->sample_rate_hz` value (from dataset config)
- **Frequency bands**: Currently fixed to alpha (8-13 Hz) and beta (13-30 Hz) until `kernel_params` support is added

The kernel uses the harness fallback mechanism: `get_info()` returns `0` for `input_channels`, `output_channels`, and `input_window_length_samples`, causing the harness to use `scheduler->config` values which match the runtime config.

## Edge Cases

- **Stateless**: Operates on each window independently (no state persists)
- **Frequency resolution**: Frequency resolution is `Fs/N` Hz/bin (e.g., Fs=160 Hz, N=160 → 1 Hz/bin)
- **Band definition**: Bins are computed by rounding `f * N / Fs`, so bands track the configured sample rate correctly
- **Nyquist limit**: Bins exceeding Nyquist frequency (Fs/2) are rejected at initialization

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
- ✅ C implementation complete and tested (v2 with cache aliasing fix)

## Version 2: Cache Aliasing Fix

**Problem in v1**: The v1 implementation used 4 separate `alloca()` calls for scratch buffers (`s0`, `s1`, `s2`, `Pk`), each 11.5KB in size. The buffer separation (11,776 bytes) was exactly 23 × 512 cache sets, causing all buffers to alias to the **same cache set** (11,776 % 512 = 0). This created a bimodal performance distribution:
- **Fast mode**: ~22% of windows complete in < 300 µs (cache-friendly alignment)
- **Slow mode**: ~65% of windows take 500-700 µs (cache thrashing)
- **Performance gap**: ~360 µs between modes

**Solution in v2**: Single `alloca()` allocation with struct-of-arrays layout and padding between buffers to break cache set alignment. This eliminates cache set conflicts and produces stable, unimodal performance:
- **Stable distribution**: Mean ~400 µs, std dev <50 µs
- **No bimodality**: Consistent performance across all windows
- **Same algorithm**: Identical results, optimized memory layout

**Performance Improvement**:
- Eliminates 360 µs performance gap
- Reduces cache miss rate from bimodal to stable
- Maintains ABI compliance (still uses `alloca()` in `process()`)
- Same numerical accuracy (bit-for-bit identical with v1)

**Technical Details**:
- Single allocation with 512-byte padding between buffers
- Ensures buffers map to different cache sets
- Prevents deterministic cache conflicts
- Maintains stack-based allocation (no heap in `process()`)

