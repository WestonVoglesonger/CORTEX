# CORTEX Benchmark Results Summary

Generated: 2025-11-15 14:59:23

## Overall Statistics

| Kernel | Windows | P50 (µs) | P95 (µs) | P99 (µs) | Jitter P95-P50 (µs) | Deadline Misses | Miss Rate (%) |
|--------|---------|----------|----------|----------|---------------------|-----------------|---------------|
| bandpass_fir | 1203 | 5015.00 | 6363.00 | 8680.74 | 1348.00 | 0 | 0.00 |
| car | 1203 | 28.00 | 48.00 | 72.00 | 20.00 | 0 | 0.00 |
| goertzel | 1203 | 350.00 | 641.90 | 743.78 | 291.90 | 0 | 0.00 |
| notch_iir | 22 | 125.00 | 132.90 | 134.58 | 7.90 | 0 | 0.00 |

## Interpretation

- **P50/P95/P99**: 50th/95th/99th percentile latencies
- **Jitter**: Difference between P95 and P50 (indicates timing variance)
- **Deadline Misses**: Number of windows that exceeded the 500ms deadline
- **Miss Rate**: Percentage of windows that missed the deadline
