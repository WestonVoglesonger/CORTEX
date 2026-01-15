# CORTEX Benchmark Comparison Report

**Analysis Date:** 2025-11-15
**Analyzed By:** Automated Benchmark Analysis System
**Run 1:** /Users/westonvoglesonger/Projects/CORTEX/results/run-2025-11-15-001/ (Idle/No Background Load)
**Run 2:** /Users/westonvoglesonger/Projects/CORTEX/results/run-2025-11-15-002/ (Medium Background Load)

---

## Executive Summary

### Key Findings

**CRITICAL ANOMALY DETECTED:** The results show a **counterintuitive pattern** where Run 2 (with medium background load) significantly **outperformed** Run 1 (idle) across all kernels. This suggests:

1. **Potential Test Setup Issue:** Run 1 may not have been truly "idle" or may have experienced interference
2. **CPU Frequency Scaling:** Background load in Run 2 may have triggered higher CPU frequencies
3. **Thermal Effects:** Run 1 may have experienced thermal throttling
4. **Cache/Memory Effects:** Different cache warming patterns between runs
5. **Data Quality Issue:** notch_iir in Run 1 has only 22 samples vs 1202 in Run 2, indicating Run 1 was incomplete or interrupted

### Overall Performance Impact

- **Average mean latency improvement:** -48.62% (Run 2 performed ~2x better than Run 1)
- **All four kernels showed improvement** under background load
- **Range of improvements:** -45.54% (car) to -52.96% (goertzel)
- **Variability impact:** Mixed - most kernels became more consistent, but goertzel and notch_iir showed increased variance

### Kernel Sensitivity Ranking (by mean latency change)

1. **goertzel** (-52.96%) - Most affected
2. **bandpass_fir** (-48.59%)
3. **notch_iir** (-47.38%) - NOTE: Limited sample size in Run 1 (22 vs 1202)
4. **car** (-45.54%) - Most resilient

---

## 1. High-Level Summary Comparison

### Run 1 Summary Statistics (Idle)

| Kernel | Windows | P50 (µs) | P95 (µs) | P99 (µs) | Jitter P95-P50 (µs) | Deadline Misses | Miss Rate (%) |
|--------|---------|----------|----------|----------|---------------------|-----------------|---------------|
| bandpass_fir | 1203 | 5015.00 | 6363.00 | 8680.74 | 1348.00 | 0 | 0.00 |
| car | 1203 | 28.00 | 48.00 | 72.00 | 20.00 | 0 | 0.00 |
| goertzel | 1203 | 350.00 | 641.90 | 743.78 | 291.90 | 0 | 0.00 |
| notch_iir | **22** | 125.00 | 132.90 | 134.58 | 7.90 | 0 | 0.00 |

### Run 2 Summary Statistics (Medium Load)

| Kernel | Windows | P50 (µs) | P95 (µs) | P99 (µs) | Jitter P95-P50 (µs) | Deadline Misses | Miss Rate (%) |
|--------|---------|----------|----------|----------|---------------------|-----------------|---------------|
| bandpass_fir | 1203 | 2325.00 | 3028.00 | 3753.00 | 703.00 | 0 | 0.00 |
| car | 1204 | 13.00 | 33.00 | 39.00 | 20.00 | 0 | 0.00 |
| goertzel | 1203 | 138.00 | 306.00 | 388.94 | 168.00 | 0 | 0.00 |
| notch_iir | 1202 | 55.00 | 75.00 | 113.98 | 20.00 | 0 | 0.00 |

### System-Level Observations

- **Background Load Configuration (Run 2):** 4 CPU cores @ 50% load using stress-ng
- **Deadline Misses:** Zero deadline misses in both runs across all kernels
- **Data Completeness:** Run 1 appears incomplete for notch_iir (22 samples vs expected ~1200)

---

## 2. Detailed Per-Kernel Analysis

### 2.1 bandpass_fir

**Computational Profile:** FIR filter - computationally intensive, memory-heavy

#### Performance Metrics

| Metric | Run 1 (µs) | Run 2 (µs) | Δ (µs) | Change (%) |
|--------|------------|------------|---------|------------|
| Mean | 4968.76 | 2554.29 | -2414.47 | -48.59% |
| Median | 5015.00 | 2325.00 | -2690.00 | -53.64% |
| Std Dev | 2004.61 | 734.90 | -1269.71 | -63.34% |
| Min | 2293.00 | 2287.00 | -6.00 | -0.26% |
| Max | 43186.00 | 23809.00 | -19377.00 | -44.87% |
| P95 | 6363.00 | 3028.00 | -3335.00 | -52.41% |
| P99 | 8680.74 | 3753.00 | -4927.74 | -56.77% |
| P99.9 | 32136.58 | 8237.83 | -23898.75 | -74.37% |

#### Variability Analysis

- **CV (Coefficient of Variation):** 40.34% → 28.77% (-28.69%) - **Significantly more consistent**
- **IQR:** 1954.50 µs → 648.50 µs - **Tighter distribution**
- **Jitter (P95-P50):** 1348.00 µs → 703.00 µs (-47.85%) - **Much more stable**
- **Frame-to-frame stability:** Mean jump 1369.11 µs → 338.40 µs (-75.28%)

#### Distribution Characteristics

- **Run 1:** Heavily right-skewed (9.549), very heavy-tailed (kurtosis: 155.93)
- **Run 2:** Extremely right-skewed (20.907), extremely heavy-tailed (kurtosis: 583.93)
- **Outliers (>3σ):** 7 (0.58%) → 4 (0.33%)
- **Max outlier severity:** 43.2ms → 23.8ms

#### Temporal Patterns

- **Run 1 Performance Degradation:** +6.42% (worsened over time)
- **Run 2 Performance Degradation:** +2.96% (more stable over time)
- **Quartile Analysis:**
  - Run 1: Q1=4843.71, Q2=4784.38, Q3=5239.00, Q4=5007.53
  - Run 2: Q1=2607.08, Q2=2427.16, Q3=2586.75, Q4=2596.33

#### Key Insights

- Most computationally intensive kernel showed the strongest absolute improvement
- Dramatic reduction in tail latencies (P99 improved by 56.77%)
- Significantly more predictable performance under background load
- Better thermal or frequency characteristics in Run 2

---

### 2.2 car (Correlation/Association Rule)

**Computational Profile:** Lightweight, short-duration processing

#### Performance Metrics

| Metric | Run 1 (µs) | Run 2 (µs) | Δ (µs) | Change (%) |
|--------|------------|------------|---------|------------|
| Mean | 36.00 | 19.61 | -16.39 | -45.54% |
| Median | 28.00 | 13.00 | -15.00 | -53.57% |
| Std Dev | 111.25 | 15.24 | -96.01 | -86.30% |
| Min | 11.00 | 11.00 | 0.00 | 0.00% |
| Max | 3847.00 | 457.00 | -3390.00 | -88.12% |
| P95 | 48.00 | 33.00 | -15.00 | -31.25% |
| P99 | 72.00 | 39.00 | -33.00 | -45.83% |
| P99.9 | 272.96 | 69.14 | -203.82 | -74.67% |

#### Variability Analysis

- **CV:** 309.02% → 77.75% (-74.84%) - **Massive improvement in consistency**
- **IQR:** 23.00 µs → 15.00 µs
- **Jitter (P95-P50):** 20.00 µs → 20.00 µs (0% change) - **Unchanged**
- **Frame-to-frame stability:** Mean jump 17.92 µs → 9.84 µs (-45.09%)

#### Distribution Characteristics

- **Run 1:** Extremely right-skewed (33.438), extremely heavy-tailed (kurtosis: 1141.93)
- **Run 2:** Very right-skewed (19.747), very heavy-tailed (kurtosis: 560.24)
- **Outliers (>3σ):** 1 (0.08%) → 2 (0.17%)
- **Max outlier severity:** 3847 µs (massive) → 457 µs (moderate)

#### Temporal Patterns

- **Run 1 Performance Degradation:** +12.36% (significant degradation)
- **Run 2 Performance Degradation:** +15.15% (similar degradation pattern)
- **Quartile Analysis:**
  - Run 1: Q1=34.03, Q2=33.77, Q3=33.61, Q4=42.57
  - Run 2: Q1=16.69, Q2=19.76, Q3=20.14, Q4=21.84

#### Key Insights

- Shortest-duration kernel showed most consistent benefit
- Eliminated extreme outlier (3.8ms outlier in Run 1 vs max 457µs in Run 2)
- Most dramatic variability improvement (CV reduced by 74.84%)
- Both runs show temporal degradation pattern, suggesting warmup or cache effects

---

### 2.3 goertzel (Frequency Detection)

**Computational Profile:** Medium complexity, iterative processing

#### Performance Metrics

| Metric | Run 1 (µs) | Run 2 (µs) | Δ (µs) | Change (%) |
|--------|------------|------------|---------|------------|
| Mean | 416.90 | 196.11 | -220.78 | -52.96% |
| Median | 350.00 | 138.00 | -212.00 | -60.57% |
| Std Dev | 237.19 | 246.70 | +9.51 | +4.01% |
| Min | 131.00 | 130.00 | -1.00 | -0.76% |
| Max | 3765.00 | 8077.00 | +4312.00 | +114.53% |
| P95 | 641.90 | 306.00 | -335.90 | -52.33% |
| P99 | 743.78 | 388.94 | -354.84 | -47.71% |
| P99.9 | 2826.88 | 1580.34 | -1246.55 | -44.10% |

#### Variability Analysis

- **CV:** 56.90% → 125.80% (+121.10%) - **INCREASED variability** ⚠️
- **IQR:** 361.00 µs → 151.00 µs - Tighter middle distribution
- **Jitter (P95-P50):** 291.90 µs → 168.00 µs (-42.45%) - Improved
- **Frame-to-frame stability:** Mean jump 144.07 µs → 91.70 µs (-36.35%)

#### Distribution Characteristics

- **Run 1:** Right-skewed (4.114), heavy-tailed (kurtosis: 47.76)
- **Run 2:** Extremely right-skewed (27.405), extremely heavy-tailed (kurtosis: 864.17)
- **Outliers (>3σ):** 7 (0.58%) → 3 (0.25%)
- **Outlier concern:** Run 2 has a severe 8077µs outlier (vs max 3765µs in Run 1)

#### Temporal Patterns

- **Run 1 Performance Degradation:** +56.33% (severe degradation over time) ⚠️
- **Run 2 Performance Degradation:** -4.90% (actually improved over time) ✓
- **Quartile Analysis:**
  - Run 1: Q1=380.15, Q2=270.49, Q3=496.82, Q4=520.01 (highly variable)
  - Run 2: Q1=209.55, Q2=192.57, Q3=207.71, Q4=174.67 (consistent)

#### Key Insights

- **Most sensitive kernel** to background load conditions
- Contradictory signals: median improved dramatically but max latency doubled
- Shows best temporal stability improvement (no degradation in Run 2)
- Higher CV despite better median suggests occasional interference spikes
- The single 8ms outlier in Run 2 is concerning for real-time applications

---

### 2.4 notch_iir (IIR Filter)

**Computational Profile:** Lightweight recursive filter

**⚠️ DATA QUALITY WARNING:** Run 1 contains only 22 samples vs 1202 in Run 2. This comparison has limited statistical validity.

#### Performance Metrics

| Metric | Run 1 (µs) | Run 2 (µs) | Δ (µs) | Change (%) |
|--------|------------|------------|---------|------------|
| Mean | 115.45 | 60.75 | -54.70 | -47.38% |
| Median | 125.00 | 55.00 | -70.00 | -56.00% |
| Std Dev | 23.73 | 18.14 | -5.59 | -23.58% |
| Min | 52.00 | 51.00 | -1.00 | -1.92% |
| Max | 135.00 | 366.00 | +231.00 | +171.11% |
| P95 | 132.90 | 75.00 | -57.90 | -43.57% |
| P99 | 134.58 | 113.98 | -20.60 | -15.31% |
| P99.9 | 134.96 | 330.95 | +195.99 | +145.22% |

#### Variability Analysis

- **CV:** 20.56% → 29.86% (+45.23%) - **Increased variability** ⚠️
- **IQR:** 9.75 µs → 13.00 µs
- **Jitter (P95-P50):** 7.90 µs → 20.00 µs (+153.16%) - **Significantly worse** ⚠️
- **Frame-to-frame stability:** Mean jump 24.00 µs → 10.87 µs (-54.71%)

#### Distribution Characteristics

- **Run 1:** Left-skewed (-1.800), moderate tail (kurtosis: 1.74)
- **Run 2:** Extremely right-skewed (10.633), very heavy-tailed (kurtosis: 152.14)
- **Outliers (>3σ):** 0 (0%) → 10 (0.83%)
- **Run 2 introduced outliers** reaching 366 µs vs max 135 µs in Run 1

#### Temporal Patterns

- **Run 1 Performance Degradation:** +1.59% (minimal change)
- **Run 2 Performance Degradation:** -3.33% (slight improvement)
- **Quartile Analysis:**
  - Run 1: Q1=125.40, Q2=105.50, Q3=109.80, Q4=121.83 (limited data)
  - Run 2: Q1=61.56, Q2=62.01, Q3=60.02, Q4=59.43 (stable)

#### Key Insights

- **Insufficient data in Run 1 limits conclusions**
- Median performance appears better in Run 2, but worst-case doubled
- Most dramatic jitter increase (+153%)
- Shift from predictable (Run 1) to having occasional spikes (Run 2)
- The 22-sample Run 1 likely truncated before steady-state

---

## 3. Cross-Kernel Comparative Analysis

### 3.1 Sensitivity Rankings

#### By Mean Latency Change
1. **goertzel** (-52.96%) - Highest sensitivity
2. **bandpass_fir** (-48.59%)
3. **notch_iir** (-47.38%) - Limited data
4. **car** (-45.54%) - Most resilient

#### By P95 Latency Change
1. **bandpass_fir** (-52.41%)
2. **goertzel** (-52.33%)
3. **notch_iir** (-43.57%)
4. **car** (-31.25%)

#### By Jitter Change (P95-P50)
1. **notch_iir** (+153.16%) - Significant degradation ⚠️
2. **bandpass_fir** (-47.85%) - Large improvement ✓
3. **goertzel** (-42.45%) - Large improvement ✓
4. **car** (0.00%) - No change

### 3.2 Kernel Type Patterns

#### Computational Intensity vs Sensitivity

| Kernel | Complexity | Mean Change | Variability Change | Pattern |
|--------|------------|-------------|-------------------|---------|
| bandpass_fir | High | -48.59% | -63.34% (better) | Heavy computation benefits |
| goertzel | Medium | -52.96% | +4.01% (worse) | Medium shows mixed results |
| car | Low | -45.54% | -86.30% (better) | Short tasks very consistent |
| notch_iir | Low | -47.38% | -23.58% (better) | Recursive shows stability |

**Observation:** No clear correlation between computational complexity and sensitivity. The counterintuitive improvements suggest systemic differences between runs rather than background load effects.

### 3.3 Consistency Analysis

#### Coefficient of Variation Comparison

| Kernel | Run 1 CV% | Run 2 CV% | Change | Interpretation |
|--------|-----------|-----------|---------|----------------|
| car | 309.02 | 77.75 | -74.84% | Dramatic improvement |
| goertzel | 56.90 | 125.80 | +121.10% | Significant degradation |
| bandpass_fir | 40.34 | 28.77 | -28.69% | Good improvement |
| notch_iir | 20.56 | 29.86 | +45.23% | Moderate degradation |

**Pattern:** Lightweight kernels (car, notch_iir) had extreme initial CVs that improved dramatically, while medium-complexity (goertzel) became less consistent.

### 3.4 Tail Latency Resilience

#### P99 Performance Change

| Kernel | Run 1 P99 (µs) | Run 2 P99 (µs) | Change | Verdict |
|--------|----------------|----------------|---------|---------|
| bandpass_fir | 8680.74 | 3753.00 | -56.77% | Excellent |
| car | 72.00 | 39.00 | -45.83% | Excellent |
| goertzel | 743.78 | 388.94 | -47.71% | Excellent |
| notch_iir | 134.58 | 113.98 | -15.31% | Modest |

#### Maximum Latency Analysis

| Kernel | Run 1 Max (µs) | Run 2 Max (µs) | Change | Concern Level |
|--------|----------------|----------------|---------|---------------|
| car | 3847.00 | 457.00 | -88.12% | Low - huge improvement |
| bandpass_fir | 43186.00 | 23809.00 | -44.87% | Low - improved |
| notch_iir | 135.00 | 366.00 | +171.11% | **High** - 2.7x worse ⚠️ |
| goertzel | 3765.00 | 8077.00 | +114.53% | **High** - 2.1x worse ⚠️ |

**Critical Finding:** While median/P95/P99 improved, maximum latencies increased for notch_iir and goertzel, indicating occasional severe interference spikes.

---

## 4. Statistical Summary Tables

### 4.1 Absolute Performance Deltas

| Kernel | Mean Δ (µs) | P50 Δ (µs) | P95 Δ (µs) | P99 Δ (µs) | Jitter Δ (µs) |
|--------|-------------|------------|------------|------------|---------------|
| bandpass_fir | -2414.47 | -2690.00 | -3335.00 | -4927.74 | -645.00 |
| goertzel | -220.78 | -212.00 | -335.90 | -354.84 | -123.90 |
| notch_iir | -54.70 | -70.00 | -57.90 | -20.60 | +12.10 |
| car | -16.39 | -15.00 | -15.00 | -33.00 | 0.00 |

### 4.2 Relative Performance Changes

| Kernel | Mean % | Median % | P95 % | P99 % | StdDev % |
|--------|--------|----------|-------|-------|----------|
| goertzel | -52.96% | -60.57% | -52.33% | -47.71% | +4.01% |
| bandpass_fir | -48.59% | -53.64% | -52.41% | -56.77% | -63.34% |
| notch_iir | -47.38% | -56.00% | -43.57% | -15.31% | -23.58% |
| car | -45.54% | -53.57% | -31.25% | -45.83% | -86.30% |

### 4.3 Outlier Statistics

| Kernel | Run 1 Outliers | Run 1 % | Run 2 Outliers | Run 2 % | Run 2 Max Outlier |
|--------|----------------|---------|----------------|---------|-------------------|
| bandpass_fir | 7 | 0.58% | 4 | 0.33% | 23,809 µs |
| goertzel | 7 | 0.58% | 3 | 0.25% | **8,077 µs** ⚠️ |
| car | 1 | 0.08% | 2 | 0.17% | 457 µs |
| notch_iir | 0 | 0.00% | 10 | 0.83% | 366 µs |

### 4.4 Frame-to-Frame Stability

| Kernel | Run 1 Mean Jump (µs) | Run 2 Mean Jump (µs) | Change % | Run 2 Max Jump (µs) |
|--------|----------------------|----------------------|----------|---------------------|
| bandpass_fir | 1369.11 | 338.40 | -75.28% | 21,511 |
| goertzel | 144.07 | 91.70 | -36.35% | 7,945 |
| notch_iir | 24.00 | 10.87 | -54.71% | 290 |
| car | 17.92 | 9.84 | -45.09% | 446 |

### 4.5 Temporal Stability (First Half vs Second Half)

| Kernel | Run 1 Degradation | Run 2 Degradation | Interpretation |
|--------|-------------------|-------------------|----------------|
| goertzel | +56.33% | -4.90% | Run 1 had severe degradation, Run 2 stable |
| car | +12.36% | +15.15% | Both runs show slight degradation |
| bandpass_fir | +6.42% | +2.96% | Both stable, Run 2 slightly better |
| notch_iir | +1.59% | -3.33% | Both very stable |

---

## 5. Root Cause Analysis

### 5.1 Anomaly Investigation

The counterintuitive results (background load improving performance) strongly suggest:

#### Theory 1: CPU Frequency Scaling (Most Likely)
- **Evidence:** Consistent 45-53% improvement across all kernels
- **Mechanism:** Idle system may have entered low-power states; background load kept CPUs at higher frequencies
- **Supporting data:** All kernels improved, not just specific types
- **Validation needed:** Check CPU frequency logs, power management settings

#### Theory 2: Thermal Throttling in Run 1
- **Evidence:** Run 1 shows temporal degradation in multiple kernels (goertzel +56%)
- **Mechanism:** Run 1 may have started cool but throttled; Run 2 maintained steady thermal state
- **Supporting data:** Bandpass_fir Q4 > Q1 in Run 1, stable in Run 2
- **Validation needed:** Thermal sensor data, CPU temperature logs

#### Theory 3: Cache/Memory State Differences
- **Evidence:** Large absolute improvements (bandpass_fir: -2.4ms mean)
- **Mechanism:** Different cache warming, memory alignment, or NUMA effects
- **Supporting data:** Minimum latencies essentially unchanged (~-0.26% to -1.92%)
- **Validation needed:** Memory bandwidth measurements, cache miss rates

#### Theory 4: Run 1 Incomplete/Corrupted
- **Evidence:** notch_iir has only 22 samples vs 1202
- **Mechanism:** Run 1 may have been interrupted, stopped early, or had logging issues
- **Supporting data:** Missing harness.log for Run 1
- **Validation needed:** Check run logs, timestamps, process termination

### 5.2 Data Quality Assessment

| Run | Overall Quality | Issues | Reliability |
|-----|----------------|--------|-------------|
| Run 1 | **Questionable** | notch_iir truncated (22 samples), no harness.log, high variance | Low for notch_iir, Moderate for others |
| Run 2 | **Good** | Complete data, full logging | High |

**Recommendation:** **Re-run both benchmarks** under controlled conditions before drawing firm conclusions.

---

## 6. Detailed Distribution Analysis

### 6.1 bandpass_fir Distribution

#### Percentile Distribution
- **10th %ile:** 3039.40 µs → 2297.00 µs (-24.43%)
- **90th %ile:** 6336.00 µs → 2993.00 µs (-52.76%)
- **99.9th %ile:** 32,136.58 µs → 8,237.83 µs (-74.37%)

**Observation:** Improvements increase with higher percentiles - tail latencies benefited most

#### Bucket Analysis (Run 1)
- **Main cluster:** 1,152/1,203 (95.8%) in 2.3-6.4ms range
- **Outlier distribution:** 51 samples (4.2%) spread across 6.4-43ms

#### Bucket Analysis (Run 2)
- **Main cluster:** 1,201/1,203 (99.8%) in 2.3-6.4ms range
- **Outlier distribution:** Only 2 samples (0.2%) above 6.4ms

### 6.2 car Distribution

#### Percentile Distribution
- **10-40th %ile:** Dramatic compression (22µs → 12µs range)
- **50-70th %ile:** -46% to -54% improvements
- **99.9th %ile:** 272.96 µs → 69.14 µs (-74.67%)

**Observation:** Eliminated the long tail entirely

#### Bucket Analysis
- **Run 1:** 1 catastrophic outlier at 3,847 µs (350x median)
- **Run 2:** Tight distribution, max only 457 µs (35x median vs 137x in Run 1)

### 6.3 goertzel Distribution

#### Percentile Distribution
- **10-50th %ile:** -12% to -61% improvements
- **95-99th %ile:** -47% to -52% improvements
- **Max latency:** 3,765 µs → **8,077 µs** (+114.53%) ⚠️

**Observation:** Excellent median/P95 but introduced a severe outlier

#### Bucket Analysis
- **Run 1:** 99.4% of samples in 130-925µs range
- **Run 2:** 99.8% in same range, but one extreme 8ms spike

### 6.4 notch_iir Distribution

**WARNING: Run 1 has insufficient data (n=22) for robust distribution analysis**

#### Percentile Distribution
- **10-50th %ile:** -22% to -57% improvements
- **99.9th %ile:** 134.96 µs → 330.95 µs (+145.22%) ⚠️

#### Bucket Analysis
- **Run 1:** Clustered 82-145µs (limited data)
- **Run 2:** Tight main cluster 51-82µs (97.4%), with 10 outliers reaching 366µs

---

## 7. Recommendations and Conclusions

### 7.1 Test Validity Assessment

**PRIMARY RECOMMENDATION: Re-run both benchmarks**

The current results are not valid for assessing background load impact because:

1. ✗ Run 1 (baseline) appears compromised (incomplete notch_iir data)
2. ✗ Counterintuitive results suggest confounding variables
3. ✗ No CPU frequency, temperature, or power metrics captured
4. ✗ Missing Run 1 harness.log prevents validation

### 7.2 Future Test Protocol Recommendations

#### Before Next Run
1. **Document system state:** CPU governor, frequency scaling settings, thermal state
2. **Capture metrics:** CPU frequency, temperature, cache statistics
3. **Ensure completeness:** Verify all kernels complete expected sample count
4. **Environmental control:**
   - Let system reach thermal steady-state
   - Disable dynamic frequency scaling for consistent baseline
   - Run multiple iterations of each configuration

#### Benchmark Configuration
1. **Add CPU frequency monitoring** to telemetry
2. **Log thermal state** throughout benchmark
3. **Record system load metrics** (CPU %, memory, I/O)
4. **Capture timestamps** for run start/end/interruptions
5. **Validate sample counts** before analysis

#### Analysis Enhancements
1. **Correlation analysis** between CPU frequency and latency
2. **Time-series analysis** to detect warmup, steady-state, degradation
3. **Statistical significance testing** (t-tests, effect size)
4. **Reproducibility:** Run each configuration 3-5 times

### 7.3 What We Can Conclude (Despite Limitations)

#### Definitive Findings

1. **No deadline misses** in either configuration - system meets real-time requirements ✓
2. **notch_iir Run 1 incomplete** - data integrity issue confirmed
3. **Temporal patterns differ** - Run 1 shows more degradation over time
4. **Maximum latencies** - Run 2 has concerning spikes for goertzel (8ms) and notch_iir (366µs)

#### Tentative Observations (Pending Re-test)

1. **IF Run 2 results are valid**, medium background load may:
   - Maintain higher CPU frequencies, improving throughput
   - Prevent aggressive power-saving states
   - Provide more consistent thermal environment

2. **Kernel-specific patterns**:
   - Heavy computation (bandpass_fir) shows consistent behavior
   - Medium complexity (goertzel) most susceptible to variability
   - Lightweight (car, notch_iir) highly sensitive to system state

3. **Jitter vs throughput tradeoff**:
   - Median latencies improved but max latencies increased for some kernels
   - May indicate background load causes occasional preemption

### 7.4 Risk Assessment for Production Deployment

**Based on Run 2 (better-quality data):**

| Kernel | Real-Time Suitability | Primary Risk | Mitigation |
|--------|----------------------|--------------|------------|
| car | **Excellent** | Minimal (max 457µs) | None needed |
| bandpass_fir | **Good** | Rare 23ms spikes | CPU pinning, RT priority |
| notch_iir | **Moderate** | Occasional 366µs spikes | Monitor in production |
| goertzel | **Moderate** | Rare but severe 8ms spike | **Critical**: Needs investigation ⚠️ |

**Overall Assessment:** All kernels meet deadline requirements, but goertzel's 8ms outlier needs root cause analysis before production deployment.

### 7.5 Final Verdict

**Cannot draw valid conclusions about background load impact from this data.**

The results suggest **Run 1 had systemic issues** (incomplete data, potential thermal/frequency problems, high variability) rather than demonstrating that background load improves performance. The physical reality is that background load should degrade or, at best, not affect well-isolated real-time tasks.

**Required Actions:**
1. Re-run Run 1 with same config as Run 2, ensuring completion
2. Capture CPU frequency and thermal data
3. Run both configurations multiple times for statistical validity
4. Investigate goertzel's 8ms outlier in Run 2
5. Determine why notch_iir in Run 1 stopped after 22 samples

Only after controlled re-runs with proper instrumentation can we make evidence-based recommendations about operating under background load.

---

## Appendix: Methodology

### Data Sources
- **Run 1:** `/Users/westonvoglesonger/Projects/CORTEX/results/run-2025-11-15-001/`
- **Run 2:** `/Users/westonvoglesonger/Projects/CORTEX/results/run-2025-11-15-002/`

### Analysis Tools
- Pandas for data processing
- NumPy for statistical calculations
- SciPy for distribution analysis
- Custom Python scripts for multi-dimensional analysis

### Metrics Calculated
- Central tendency: mean, median
- Dispersion: standard deviation, IQR, CV
- Percentiles: P10, P20, ..., P95, P99, P99.9
- Outlier detection: 3-sigma method
- Distribution shape: skewness, kurtosis
- Temporal: quartile analysis, degradation percentage
- Stability: frame-to-frame jumps, jitter

### Statistical Validity Notes
- **bandpass_fir:** n=1203 both runs - statistically robust ✓
- **car:** n=1203/1204 - statistically robust ✓
- **goertzel:** n=1203 both runs - statistically robust ✓
- **notch_iir:** n=22 (Run 1), n=1202 (Run 2) - **NOT comparable** ✗

---

**Report Generated:** 2025-11-15
**Analysis Duration:** Comprehensive multi-dimensional analysis
**Next Steps:** Re-run benchmarks with enhanced instrumentation
