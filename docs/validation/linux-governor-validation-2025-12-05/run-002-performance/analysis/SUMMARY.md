# Latency Comparison Summary

Generated: 2025-12-06 12:42:16

## Latency Statistics (μs)

| Kernel | Mean | Median | P95 | P99 | Min | Max | Std Dev |
|--------|------|--------|-----|-----|-----|-----|----------|
| bandpass_fir | 2443.15 | 2968.44 | 2982.11 | 2995.18 | 1394.06 | 3036.94 | 731.86 |
| car | 20.39 | 14.12 | 29.08 | 29.45 | 12.08 | 42.08 | 7.57 |
| goertzel | 426.35 | 496.27 | 501.43 | 503.22 | 166.99 | 515.81 | 133.46 |
| notch_iir | 44.51 | 37.96 | 60.7 | 60.91 | 29.71 | 65.41 | 13.16 |

## Deadline Miss Rates

| Kernel | Miss Rate (%) | Total Samples | Misses |
|--------|---------------|---------------|--------|
| bandpass_fir | 0.0 | 1205.0 | 0.0 |
| car | 0.0 | 1205.0 | 0.0 |
| goertzel | 0.0 | 1205.0 | 0.0 |
| notch_iir | 0.0 | 1205.0 | 0.0 |
