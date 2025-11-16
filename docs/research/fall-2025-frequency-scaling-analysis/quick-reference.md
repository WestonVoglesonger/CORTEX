# Benchmark Comparison Quick Reference

## At a Glance

| Kernel | Mean Latency Change | P95 Change | Max Change | Verdict |
|--------|---------------------|------------|------------|---------|
| **bandpass_fir** | -48.6% ✓ | -52.4% ✓ | -44.9% ✓ | Improved across all metrics |
| **car** | -45.5% ✓ | -31.2% ✓ | -88.1% ✓ | Most consistent improvement |
| **goertzel** | -53.0% ✓ | -52.3% ✓ | +114.5% ⚠ | Better median, worse max |
| **notch_iir** | -47.4% ✓ | -43.6% ✓ | +171.1% ⚠ | **Limited data (22→1202 samples)** |

## Critical Findings

### 🚨 ANOMALY DETECTED
**Run 2 (with background load) outperformed Run 1 (idle) by ~48% on average.**

This is physically counterintuitive. Most likely causes:
1. **CPU Frequency Scaling:** Idle system ran at lower frequencies
2. **Thermal Throttling:** Run 1 may have experienced throttling
3. **Data Quality:** Run 1 incomplete (notch_iir: 22 samples vs 1202)
4. **Test Environment:** Differences in system state between runs

### ⚠️ Data Quality Issues

| Issue | Severity | Impact |
|-------|----------|--------|
| notch_iir Run 1 truncated (22 vs 1202 samples) | **CRITICAL** | Results not comparable |
| No Run 1 harness.log | High | Cannot verify run conditions |
| goertzel max spike to 8077µs in Run 2 | Medium | Needs investigation |
| notch_iir max spike to 366µs in Run 2 | Medium | 2.7x worse than Run 1 max |

## Performance Summary

### Overall Statistics

| Metric | Average Across Kernels |
|--------|------------------------|
| Mean latency change | **-48.6%** |
| P95 latency change | **-44.9%** |
| Deadline misses (both runs) | **0** |
| Kernels improved | **4/4** |
| Kernels with worse max latency | **2/4** (goertzel, notch_iir) |

### Kernel Rankings

#### Most Improved (by mean)
1. goertzel: -53.0%
2. bandpass_fir: -48.6%
3. notch_iir: -47.4%
4. car: -45.5%

#### Most Consistent (by CV improvement)
1. car: -74.8%
2. bandpass_fir: -28.7%
3. notch_iir: -23.6%
4. goertzel: +121.1% ⚠ (worse)

#### Best Jitter Reduction
1. bandpass_fir: -47.9%
2. goertzel: -42.5%
3. car: 0.0%
4. notch_iir: +153.2% ⚠ (worse)

## Detailed Metrics

### bandpass_fir (FIR Filter)
- **Samples:** 1203 → 1203 ✓
- **Mean:** 4968.8µs → 2554.3µs (-48.6%)
- **P50:** 5015.0µs → 2325.0µs (-53.6%)
- **P95:** 6363.0µs → 3028.0µs (-52.4%)
- **P99:** 8680.7µs → 3753.0µs (-56.8%)
- **Max:** 43,186µs → 23,809µs (-44.9%)
- **StdDev:** 2004.6µs → 734.9µs (-63.3%)
- **Outliers:** 7 (0.58%) → 4 (0.33%)
- **Assessment:** ✓ Excellent improvement across all metrics

### car (Correlation/Association)
- **Samples:** 1203 → 1204 ✓
- **Mean:** 36.0µs → 19.6µs (-45.5%)
- **P50:** 28.0µs → 13.0µs (-53.6%)
- **P95:** 48.0µs → 33.0µs (-31.2%)
- **P99:** 72.0µs → 39.0µs (-45.8%)
- **Max:** 3,847µs → 457µs (-88.1%)
- **StdDev:** 111.3µs → 15.2µs (-86.3%)
- **Outliers:** 1 (0.08%) → 2 (0.17%)
- **Assessment:** ✓ Massive outlier reduction, most consistent

### goertzel (Frequency Detection)
- **Samples:** 1203 → 1203 ✓
- **Mean:** 416.9µs → 196.1µs (-53.0%)
- **P50:** 350.0µs → 138.0µs (-60.6%)
- **P95:** 641.9µs → 306.0µs (-52.3%)
- **P99:** 743.8µs → 388.9µs (-47.7%)
- **Max:** 3,765µs → 8,077µs (+114.5%) ⚠
- **StdDev:** 237.2µs → 246.7µs (+4.0%)
- **Outliers:** 7 (0.58%) → 3 (0.25%)
- **Assessment:** ⚠ Mixed - excellent median, concerning max spike

### notch_iir (IIR Filter)
- **Samples:** 22 → 1202 ⚠ **INVALID COMPARISON**
- **Mean:** 115.5µs → 60.8µs (-47.4%)
- **P50:** 125.0µs → 55.0µs (-56.0%)
- **P95:** 132.9µs → 75.0µs (-43.6%)
- **P99:** 134.6µs → 114.0µs (-15.3%)
- **Max:** 135µs → 366µs (+171.1%) ⚠
- **StdDev:** 23.7µs → 18.1µs (-23.6%)
- **Outliers:** 0 (0%) → 10 (0.83%)
- **Assessment:** ⚠ Run 1 data insufficient, max latency 2.7x worse

## Distribution Analysis

### Skewness (0 = symmetric, + = right tail, - = left tail)
| Kernel | Run 1 | Run 2 | Change |
|--------|-------|-------|--------|
| bandpass_fir | 9.5 | 20.9 | More right-skewed |
| car | 33.4 | 19.7 | Less right-skewed ✓ |
| goertzel | 4.1 | 27.4 | Much more right-skewed |
| notch_iir | -1.8 | 10.6 | Flipped to right-skewed |

### Kurtosis (0 = normal, + = heavy tails, - = light tails)
| Kernel | Run 1 | Run 2 | Change |
|--------|-------|-------|--------|
| bandpass_fir | 155.9 | 583.9 | Heavier tails |
| car | 1141.9 | 560.2 | Lighter tails ✓ |
| goertzel | 47.8 | 864.2 | Much heavier tails |
| notch_iir | 1.7 | 152.1 | Much heavier tails |

## Temporal Stability

### Performance Degradation (First Half vs Second Half)
| Kernel | Run 1 Degradation | Run 2 Degradation | Improvement |
|--------|-------------------|-------------------|-------------|
| bandpass_fir | +6.4% | +2.96% | ✓ More stable |
| car | +12.4% | +15.2% | Similar pattern |
| goertzel | +56.3% | -4.9% | ✓ Much better |
| notch_iir | +1.6% | -3.3% | ✓ Stable |

### Frame-to-Frame Stability (Mean Jump)
| Kernel | Run 1 (µs) | Run 2 (µs) | Change |
|--------|------------|------------|--------|
| bandpass_fir | 1369.1 | 338.4 | -75.3% ✓ |
| car | 17.9 | 9.8 | -45.1% ✓ |
| goertzel | 144.1 | 91.7 | -36.4% ✓ |
| notch_iir | 24.0 | 10.9 | -54.7% ✓ |

## Recommendations

### Immediate Actions
1. ⚠️ **RE-RUN BOTH BENCHMARKS** - Current results are not valid
2. ⚠️ Investigate notch_iir Run 1 truncation (22 samples)
3. ⚠️ Investigate goertzel 8ms outlier in Run 2
4. ⚠️ Investigate notch_iir 366µs spikes in Run 2

### Future Test Protocol
1. **Monitor CPU frequency** during all runs
2. **Log thermal state** (temperature sensors)
3. **Disable dynamic frequency scaling** for baseline
4. **Let system reach thermal steady-state** before runs
5. **Run each configuration 3-5 times** for statistical validity
6. **Validate sample counts** before declaring run complete
7. **Capture system load metrics** throughout

### Analysis Files Generated
- **BENCHMARK_COMPARISON_REPORT.md** (25KB) - Full comprehensive analysis
- **analyze_runs.py** - Statistical analysis script
- **detailed_analysis.py** - Distribution analysis script
- **generate_comparison_summary.py** - Executive summary generator

## Bottom Line

**❌ Cannot draw valid conclusions about background load impact from this data.**

The counterintuitive results (background load improving performance) indicate **Run 1 had systemic issues** rather than demonstrating actual background load benefits. Physical reality dictates that background CPU load should either degrade or (at best) not affect properly isolated real-time tasks.

**Required:** Controlled re-runs with proper instrumentation (CPU freq, thermals, complete logging) before making any production decisions.

**However:** Both runs achieved **zero deadline misses**, indicating the system meets basic real-time requirements under both conditions.

---

**Report Date:** 2025-11-15
**Analysis Tools:** Python 3.10, Pandas, NumPy, SciPy
**Data Sources:** /Users/westonvoglesonger/Projects/CORTEX/results/run-2025-11-15-{001,002}/
