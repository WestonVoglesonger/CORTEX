# Latency Comparison Summary

Generated: 2025-11-26 15:20:59

## Latency Statistics (μs)

| Kernel | Mean | Median | P95 | P99 | Min | Max | Std Dev |
|--------|------|--------|-----|-----|-----|-----|----------|
| bandpass_fir | 4968.76 | 5015.0 | 6363.0 | 8680.74 | 2293.0 | 43186.0 | 2005.44 |
| car | 36.0 | 28.0 | 48.0 | 72.0 | 11.0 | 3847.0 | 111.29 |
| goertzel | 416.9 | 350.0 | 641.9 | 743.78 | 131.0 | 3765.0 | 237.29 |
| notch_iir | 135.92 | 133.0 | 188.0 | 219.73 | 52.0 | 2126.0 | 73.83 |

## Deadline Miss Rates

| Kernel | Miss Rate (%) | Total Samples | Misses |
|--------|---------------|---------------|--------|
| bandpass_fir | 0.0 | 1203.0 | 0.0 |
| car | 0.0 | 1203.0 | 0.0 |
| goertzel | 0.0 | 1203.0 | 0.0 |
| notch_iir | 0.0 | 1204.0 | 0.0 |
