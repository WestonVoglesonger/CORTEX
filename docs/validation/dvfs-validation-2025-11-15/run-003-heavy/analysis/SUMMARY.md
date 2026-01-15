# CORTEX Benchmark Results Summary

Generated: 2025-11-15 19:05:05

## Overall Statistics

| Kernel | Windows | P50 (µs) | P95 (µs) | P99 (µs) | Jitter P95-P50 (µs) | Deadline Misses | Miss Rate (%) |
|--------|---------|----------|----------|----------|---------------------|-----------------|---------------|
| bandpass_fir | 1202 | 2982.00 | 4234.95 | 6042.56 | 1252.95 | 0 | 0.00 |
| car | 1200 | 22.00 | 23.00 | 73.06 | 1.00 | 0 | 0.00 |
| goertzel | 1200 | 282.00 | 318.00 | 1207.55 | 36.00 | 0 | 0.00 |
| notch_iir | 1202 | 61.00 | 75.00 | 152.56 | 14.00 | 0 | 0.00 |

## Interpretation

- **P50/P95/P99**: 50th/95th/99th percentile latencies
- **Jitter**: Difference between P95 and P50 (indicates timing variance)
- **Deadline Misses**: Number of windows that exceeded the 500ms deadline
- **Miss Rate**: Percentage of windows that missed the deadline
