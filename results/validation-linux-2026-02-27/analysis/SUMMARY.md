# Latency Comparison Summary

Generated: 2026-02-27 20:54:48

## Execution Environment

- **Execution Mode**: Remote
- **Device**: weston-macbookair
- **Device CPU**: aarch64
- **Device OS**: Linux 6.14.2-401.asahi.fc42.aar

## Latency Statistics (μs)

| Kernel | Mean ± 95% CI | Median | P95 | P99 | Min | Max | Std Dev | N |
|--------|----------------|--------|-----|-----|-----|-----|---------|---|
| bandpass_fir | 1231.35 ± 2.36 (0.2%) | 1216.26 | 1286.09 | 1293.55 | 1169.32 | 1346.31 | 32.7 | 744 |
| car | 368.74 ± 1.48 (0.4%) | 368.61 | 384.07 | 443.69 | 337.07 | 670.18 | 20.6 | 744 |
| fft | 398.89 ± 1.95 (0.5%) | 392.65 | 442.76 | 452.38 | 346.07 | 691.55 | 27.2 | 744 |
| goertzel | 422.58 ± 1.44 (0.3%) | 420.1 | 448.14 | 454.92 | 391.23 | 744.17 | 20.06 | 744 |
| noop | 348.84 ± 0.90 (0.3%) | 350.86 | 367.9 | 376.38 | 309.82 | 397.9 | 12.4 | 744 |
| notch_iir | 380.06 ± 0.94 (0.2%) | 384.44 | 398.34 | 407.22 | 344.69 | 420.1 | 13.16 | 744 |

## Deadline Miss Rates

| Kernel | Miss Rate (%) | Total Samples | Misses |
|--------|---------------|---------------|--------|
| bandpass_fir | 0.0 | 744.0 | 0.0 |
| car | 0.0 | 744.0 | 0.0 |
| fft | 0.0 | 744.0 | 0.0 |
| goertzel | 0.0 | 744.0 | 0.0 |
| noop | 0.0 | 744.0 | 0.0 |
| notch_iir | 0.0 | 744.0 | 0.0 |
