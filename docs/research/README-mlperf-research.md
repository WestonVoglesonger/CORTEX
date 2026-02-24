# MLPerf Benchmarking Methodology Research

## Overview

This research comprehensively analyzes the MLPerf benchmarking methodology across three variants (Inference, Mobile, Tiny) to extract measurement approaches, target workloads, validation methods, and critical gaps relevant to BCI (Brain-Computer Interface) real-time signal processing systems.

## Key Finding

**MLPerf measures steady-state throughput and latency percentiles under controlled, reproducible conditions, but explicitly does NOT measure real-time deadline compliance, streaming continuity, platform variability effects, or numerical correctness—gaps critical for BCI applications.**

---

## Documents in This Research

### 1. Main Analysis Document
**File**: `mlperf-methodology-analysis.md` (3,274 words, 24 KB)

Comprehensive technical analysis covering:
- **Part 1**: MLPerf Inference (ISCA 2020)
  - Four scenarios (Single-stream, Server, Offline, Multistream)
  - Percentile reporting (P90, P99)
  - Accuracy validation (99% FP32 targets)
  - Platform assumptions and LoadGen reference implementation

- **Part 2**: MLPerf Mobile (MLSys 2022)
  - Mobile-specific models and constraints
  - Platform effects acknowledged but NOT measured
  - Explicit scope boundaries (thermal, battery)

- **Part 3**: MLPerf Tiny (NeurIPS 2021)
  - Microcontroller benchmarks
  - Energy-per-inference metric
  - Streaming Wakeword extension

- **Part 4**: What MLPerf Does NOT Address
  - Real-time deadline compliance gaps
  - Streaming workload patterns
  - Platform effects characterization
  - Numerical correctness limitations

- **Part 5**: Implications for BCI Benchmarking
  - Direct applications
  - Critical extensions needed
  - BCI-specific metrics beyond MLPerf

### 2. Quick Reference Guide
**File**: `mlperf-gaps-for-bci.md` (1,730 words, 13 KB)

Condensed reference covering:
- What MLPerf DOES measure (latency, accuracy, energy)
- What MLPerf does NOT measure (4 critical gaps)
- Comparison table (MLPerf vs. BCI requirements)
- Direct applications for BCI
- Necessary extensions for BCI benchmarking
- Integration with CORTEX specification

---

## Key Metrics from MLPerf

### Latency Reporting
- **Single-Stream**: 90th percentile (P90)
- **Server/Interactive**: 99th percentile (P99)
- **Example Constraints**:
  - ResNet-50: 15 ms
  - BERT-Large: 130 ms
  - Llama 2 70B: 450 ms TTFT, 40 ms TPOT (P99)

### Accuracy Targets
- **Standard**: 99% of FP32 reference accuracy
- **High-Accuracy**: 99.9% of FP32
- **Mobile**: 93-98% of FP32 (stricter due to quantization)

### Energy Metrics (Tiny)
- Energy per inference = Power (W) × Latency (s) = Joules/inference
- Mobile: "Battery measurement beyond current scope"

---

## Critical Gaps Identified

### 1. Real-Time Deadline Compliance
MLPerf reports P99 latency but NOT:
- % of inferences exceeding hard deadline
- Jitter distribution
- Deadline miss consequences
- Sustained compliance under thermal stress

**Impact**: System with "P99 = 15 ms" might have 5% of queries at 500 ms (thermal throttle). MLPerf marks valid; BCI needs "99.99% within deadline."

### 2. Streaming and Continuous Workload Patterns
MLPerf measures: Query → Response (variable timing, stateless)
BCI requires: Fixed-rate sensor stream (e.g., 250 Hz EEG), stateful with sliding window

**Impact**: Cannot use MLPerf results to predict streaming BCI performance.

### 3. Platform Effects
MLPerf acknowledges but treats as noise:
- Thermal throttling over sustained load
- Cache effects and contention
- System state dependence (GC pauses, preemption)

Explicit quote: "Thermal throttling further complicates fair measurement on battery-powered devices. Given these complexities, establishing a fair and transparent benchmark for measuring power consumption in battery-powered devices is beyond the current scope of work." (MLSys 2022)

**Impact**: MLPerf's "P99 = 5 ms" in isolation might become "P50 = 10 ms" under real clinical deployment.

### 4. Numerical Correctness and Determinism
MLPerf validates: Functional accuracy on validation dataset (99% of FP32)
MLPerf does NOT validate:
- Output determinism (same input ≠ identical output)
- Adversarial robustness
- Numerical stability under quantization
- Distribution shift robustness

**Impact**: Doesn't guarantee robustness to EEG signal artifacts or pathological patterns outside training distribution.

---

## MLPerf Principles Applicable to CORTEX BCI Benchmark

✓ Accuracy-first validation (define quality target before speed testing)
✓ Percentile-based latency reporting (P90, P99 with statistical backing)
✓ Standardized load generator (deterministic, reproducible)
✓ Fixed reference models and datasets
✓ Hardware diversity support

---

## BCI-Specific Additions Needed

1. **Deadline Compliance Metrics**
   - Deadline miss rate (% exceeding hard deadline)
   - Jitter distribution
   - Miss consequence specification

2. **Streaming State Specification**
   - Fixed sample rate (Hz)
   - State retention (sliding window size)
   - Multi-channel synchronization

3. **Platform Variability Characterization**
   - Thermal profile over sustained load
   - Contention effects (shared cache, system load)
   - Realistic OS conditions (not isolated systems)

4. **Signal-Specific Robustness**
   - Adversarial robustness (electrode noise, artifacts)
   - Quantization sensitivity (FP32 → INT8)
   - Temporal drift (long-duration recording artifacts)
   - Distribution shift (different patient populations)

5. **Clinical Appropriateness**
   - Sensitivity/specificity (ROC curve)
   - Detection latency from event onset
   - Confidence/uncertainty quantification
   - Multi-class confusion matrix

---

## Research Sources

**Primary Papers**:
- Reddi et al. (ISCA 2020): "MLPerf Inference Benchmark"
- Janapa Reddi et al. (MLSys 2022): "MLPerf Mobile Inference Benchmark"
- Banbury et al. (NeurIPS 2021): "MLPerf Tiny Benchmark"

**Documentation**:
- MLCommons Inference Rules: https://github.com/mlcommons/inference_policies
- MLPerf Power (2024): https://arxiv.org/html/2410.12032v1

---

## How to Use This Research

### For CORTEX Specification (Part II - Core Specifications)
- **Section 3 (Plugin ABI)**: Reference MLPerf's deterministic load generation pattern
- **Section 4 (Wire Protocol)**: Adopt percentile-based latency reporting
- **Section 5 (Configuration)**: Model after MLPerf's standardized model/dataset format
- **Section 6 (Telemetry)**: Include deadline miss rate, jitter distribution

### For CORTEX Specification (Part IV - Advanced Capabilities)
- **Section 12 (Diagnostic Framework)**: Thermal profiling, platform characterization
- **Conformance Criteria**: Accuracy-first validation (99% quality target)

### For BCI Implementation Teams
- **Model Validation**: Use MLPerf's accuracy-first paradigm
- **Latency Testing**: Adopt P90 (per-sample) and P99 (batch deadline) reporting
- **Embedded Development**: Use MLPerf Tiny/Mobile for energy-per-inference metrics
- **Real-World Testing**: Note gaps and add deadline compliance + streaming state metrics

---

## Next Steps

1. **Review Batch 1 feedback**: Check if document length/depth appropriate
2. **Integration planning**: How to incorporate MLPerf principles into CORTEX Parts I, III, IV, V
3. **Specification writing**: Batch 2 (Parts I + III) can reference this research
4. **Benchmark design**: Create BCI-specific extensions to MLPerf methodology

---

## Document Status

✓ Research completed: All three MLPerf variants analyzed
✓ Gap analysis completed: Four critical gaps identified with specific examples
✓ Implications assessed: Direct applications + necessary extensions documented
✓ Word count: 5,004 words across two documents (main + summary)
✓ References: Cited specific sections, page numbers, and quotes from primary sources

---

Generated: February 2, 2026
Research Scope: MLPerf Inference (ISCA 2020), Mobile (MLSys 2022), Tiny (NeurIPS 2021)
