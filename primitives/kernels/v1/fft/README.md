# fft

One-sided magnitude-squared FFT spectrum: `|X[k]|^2` for `k = 0..N/2`.

## Overview

Computes a raw (unwindowed) FFT per channel and outputs real-valued magnitude-squared coefficients. This kernel serves two purposes:

1. **Benchmarkable FFT primitive** for cross-dtype latency comparison (f32 vs Q15).
2. **Building block** for `welch_psd@q15` (which requires a Q15 FFT internally).

No windowing is applied. Chain a windowing kernel before this if spectral leakage matters.

## Input / Output

| | Shape | Type |
|---|---|---|
| Input | `(W, C)` | f32 or Q15 |
| Output | `(W/2+1, C)` | f32 or Q15 |

Where `W` = `window_length_samples`, `C` = `channels`.

## Algorithm

For each channel `c`:
1. Extract channel from interleaved input
2. Compute complex FFT via kiss_fft
3. Output `|X[k]|^2 = Re(X[k])^2 + Im(X[k])^2` for `k = 0..N/2`

### Q15 Specifics

The Q15 variant compiles kiss_fft with `-DFIXED_POINT=16`, which makes butterfly arithmetic use `int16_t` with per-stage `C_FIXDIV` scaling. Key consequences:

- **Accumulated scaling is approximately 1/N** but NOT exactly 1/N. The per-stage division depends on the radix factorization path, and each `sround()` introduces rounding error.
- **Magnitude-squared after ~1/N^2 scaling means most bins quantize to zero** for typical EEG signals. The Q15 FFT is useful as a latency primitive and welch_psd building block, not as a standalone analysis tool.
- **The oracle models scaling as "divide by N"** — an approximation. Relaxed tolerance (`rtol=5e-2`) absorbs the gap.
- **N must be a kiss_fft "fast size"** (factors into {2, 3, 5}). Init rejects non-fast sizes.

### Q15 Magnitude-Squared Overflow

`(-32768)^2 + (-32768)^2 = 2^31`, which overflows `int32_t`. Accumulation uses `int64_t`, then shifts Q30 -> Q15 with saturation.

## Parameters

None. The FFT size equals `window_length_samples`.

## Tech Debt

Each dtype vendors its own copy of kiss_fft (same pattern as welch_psd). A future improvement would extract kiss_fft to `vendor/kiss_fft/` at the repo level with each kernel Makefile referencing it. Not blocking; scales poorly at 4+ dtypes.
