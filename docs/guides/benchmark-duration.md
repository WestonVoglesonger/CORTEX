# Benchmark Duration Guidelines

## Purpose
This document provides guidance on selecting appropriate benchmark durations for reliable latency statistics in CORTEX, based on research and industry best practices.

## Research Findings

Based on studies in real-time system benchmarking:

1. **Extended Measurement Periods**: Research studies demonstrate that comprehensive latency analysis requires extended measurement periods. A study on real-time performance of Linux kernels on single-board computers conducted tests over approximately 3 hours, accumulating around 1 million samples with an average cycle duration of 120 microseconds. This extensive period allowed for comprehensive analysis of mean, minimum, and maximum response latencies, as well as variance and standard deviation. ([MDPI Study, 2021](https://www.mdpi.com/2073-431X/10/5/64))

2. **Statistical Requirements for Percentiles**:
   - **P50 (Median)**: Reliable with ~100+ samples
   - **P95**: Needs ~1,000+ samples for confidence (20× inverse of 5% tail)
   - **P99**: Needs ~10,000+ samples for confidence (100× inverse of 1% tail)
   - **Rare events**: Longer runs needed to observe tail latencies

3. **Real-Time System Considerations**:
   - Need to capture transient latency spikes and system variability
   - Must observe worst-case behavior for real-time guarantees
   - Extended periods help in obtaining accurate representation of kernel latency characteristics ([EVL Project Benchmarks](https://evlproject.org/core/benchmarks/))

## References

1. **MDPI Study (2021)**: Real-time performance measurements of Linux kernels on single-board computers. *Computers*, 10(5), 64. https://www.mdpi.com/2073-431X/10/5/64
   - Conducted 3-hour tests with ~1 million samples
   - Emphasized importance of large sample sizes for accurate statistical analysis

2. **EVL Project Benchmarks**: Real-time Linux kernel latency measurement tools and practices. https://evlproject.org/core/benchmarks/
   - Recommends extended measurement periods to capture rare latency events
   - Tools like `latmus` accumulate data over time for comprehensive analysis

## Duration Recommendations for CORTEX

### Current Setup
- **Chunk rate**: 2 Hz (2 windows/second)
- **Configuration**: 64 channels, 160 Hz sample rate
- **Hop length**: 80 samples

### Recommended Durations

#### Quick Feedback (Development/CI)
- **Duration**: 10-30 seconds
- **Samples**: ~20-60 windows per repeat
- **Use case**: Fast iteration, smoke tests
- **Statistics**: P50 reliable; P95/P99 may have limited confidence

```yaml
benchmark:
  parameters:
    duration_seconds: 10
    repeats: 3
    warmup_seconds: 5
```

**Expected windows**: 10 sec × 2 windows/sec = 20 windows per repeat  
**Total across 3 repeats**: ~60 windows  
**Statistics**: Good for P50; P95 acceptable; P99 limited

---

#### Standard Benchmark (Recommended)
- **Duration**: 60-120 seconds
- **Samples**: ~120-240 windows per repeat
- **Use case**: Standard benchmarking, publication-quality results
- **Statistics**: Reliable P50, P95; acceptable P99

```yaml
benchmark:
  parameters:
    duration_seconds: 60
    repeats: 3
    warmup_seconds: 5
```

**Expected windows**: 60 sec × 2 windows/sec = 120 windows per repeat  
**Total across 3 repeats**: ~360 windows  
**Statistics**: Excellent for P50/P95; good for P99

---

#### Comprehensive Analysis
- **Duration**: 300-600 seconds (5-10 minutes)
- **Samples**: ~600-1,200 windows per repeat
- **Use case**: Deep analysis, worst-case characterization
- **Statistics**: Highly reliable all percentiles, captures rare events

```yaml
benchmark:
  parameters:
    duration_seconds: 300
    repeats: 3
    warmup_seconds: 5
```

**Expected windows**: 300 sec × 2 windows/sec = 600 windows per repeat  
**Total across 3 repeats**: ~1,800 windows  
**Statistics**: Excellent for all percentiles, captures tail latencies

---

#### Research-Grade (Extended)
- **Duration**: 1800+ seconds (30+ minutes)
- **Samples**: 3,600+ windows per repeat
- **Use case**: Research studies, comprehensive characterization
- **Statistics**: Captures rare events, full variability analysis

## Sample Size Calculations

### For Reliable P99 (99th percentile):
- **Minimum**: 100 samples (very basic)
- **Recommended**: 1,000+ samples
- **Research-grade**: 10,000+ samples

For your 2 windows/second rate:
- **100 samples**: 50 seconds
- **1,000 samples**: 500 seconds (8.3 minutes)
- **10,000 samples**: 5,000 seconds (83 minutes)

### For Reliable P95 (95th percentile):
- **Minimum**: 20 samples
- **Recommended**: 200+ samples

For your 2 windows/second rate:
- **20 samples**: 10 seconds
- **200 samples**: 100 seconds (1.7 minutes)

## Current Config Analysis

### Dataset Availability

The current dataset (`S001R03.float32`) contains:
- **Duration**: 125 seconds (2.08 minutes)
- **Samples**: 20,000 per channel × 64 channels
- **Auto-looping**: The replayer automatically rewinds and loops the dataset, so you can run benchmarks of **any duration**

**Dataset Usage by Duration**:
| Duration | Dataset Coverage | Number of Loops |
|----------|------------------|-----------------|
| 10s      | ~8% of dataset   | 0.08×          |
| 60s      | ~48% of dataset  | 0.48×          |
| 125s     | Full dataset     | 1.0×           |
| 300s     | 2.4× loops       | 2.4×           |
| 600s     | 4.8× loops       | 4.8×           |

### Current Config Analysis

Your current `cortex.yaml`:
```yaml
duration_seconds: 10
repeats: 3
```

**Expected windows**: 10 × 2 = 20 per repeat × 3 = 60 total

**Assessment**:
- ✅ Good for P50 (median)
- ⚠️ Acceptable for P95 (95th percentile)
- ❌ Limited confidence for P99 (99th percentile)

## Recommendations

### For Development
- **10-30 seconds**: Fast iteration
- **Warmup**: 5 seconds adequate

### For Production Benchmarks
- **60-120 seconds**: Best balance of time vs. statistical confidence
- **3+ repeats**: Reduces variance in estimates

### For Research/Publication
- **300+ seconds**: Comprehensive analysis
- **Consider**: Higher sample rates (if configurable) to collect more data faster

## Duration Recommendations Summary Table

Based on research findings and statistical requirements:

| Duration | Windows/Repeat | Total Windows (3 repeats) | P50 Confidence | P95 Confidence | P99 Confidence | Time Cost | Use Case |
|----------|----------------|---------------------------|----------------|----------------|----------------|-----------|----------|
| 10s      | ~20            | ~60                       | ✅ Good        | ⚠️ Acceptable  | ❌ Low         | Low       | Development, quick tests |
| 30s      | ~60            | ~180                      | ✅ Excellent   | ✅ Good        | ⚠️ Acceptable  | Medium    | Standard development |
| **60s**  | **~120**       | **~360**                  | **✅ Excellent** | **✅ Good**  | **✅ Acceptable** | **Medium** | **Recommended default** |
| 120s     | ~240           | ~720                      | ✅ Excellent   | ✅ Excellent   | ✅ Good        | High      | Production benchmarking |
| 300s     | ~600           | ~1,800                    | ✅ Excellent   | ✅ Excellent   | ✅ Excellent   | Very High | Research, comprehensive analysis |

**Note**: These recommendations assume a chunk rate of 2 Hz (2 windows/second) with your current configuration (160 Hz sample rate, 80 sample hop length, 64 channels).

## Future Improvements

1. **Adaptive Duration**: Start with short run; extend if variance is high
2. **Target Sample Count**: Specify desired samples, calculate duration automatically
3. **Statistical Confidence**: Report confidence intervals for percentiles
4. **Rare Event Detection**: Track outlier windows separately

