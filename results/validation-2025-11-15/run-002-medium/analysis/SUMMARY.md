# CORTEX Benchmark Results Summary

Generated: 2025-11-15 15:44:28

## Overall Statistics

| Kernel | Windows | P50 (µs) | P95 (µs) | P99 (µs) | Jitter P95-P50 (µs) | Deadline Misses | Miss Rate (%) |
|--------|---------|----------|----------|----------|---------------------|-----------------|---------------|
| bandpass_fir | 1203 | 2325.00 | 3028.00 | 3753.00 | 703.00 | 0 | 0.00 |
| car | 1204 | 13.00 | 33.00 | 39.00 | 20.00 | 0 | 0.00 |
| goertzel | 1203 | 138.00 | 306.00 | 388.94 | 168.00 | 0 | 0.00 |
| notch_iir | 1202 | 55.00 | 75.00 | 113.98 | 20.00 | 0 | 0.00 |

## Interpretation

- **P50/P95/P99**: 50th/95th/99th percentile latencies
- **Jitter**: Difference between P95 and P50 (indicates timing variance)
- **Deadline Misses**: Number of windows that exceeded the 500ms deadline
- **Miss Rate**: Percentage of windows that missed the deadline
