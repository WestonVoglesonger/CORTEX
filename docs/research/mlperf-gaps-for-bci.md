# MLPerf Gaps for BCI: Quick Reference

## Research Deliverable

**Document**: `/Users/westonvoglesonger/Projects/CORTEX/docs/research/mlperf-methodology-analysis.md` (3,274 words)

**Sources**: MLPerf Inference (ISCA 2020), MLPerf Mobile (MLSys 2022), MLPerf Tiny (NeurIPS 2021), MLCommons documentation

---

## What MLPerf DOES Measure

### Latency Reporting
- **Single-Stream**: 90th percentile latency (P90) - for one inference at a time
- **Server/Interactive**: 99th percentile latency (P99) - for multiple concurrent requests
- **Multistream**: 99th percentile latency across 8-sample batches
- **Offline**: Total throughput (no latency constraint)

Example constraints (datacenter):
- ResNet-50: 15 ms P99 latency
- BERT-Large: 130 ms P99 latency
- Llama 2 70B: 450 ms TTFT (Time To First Token) + 40 ms TPOT (Per-Token) at P99

### Accuracy Validation
- Standard target: **99% of FP32 reference accuracy**
- High-accuracy target: **99.9% of FP32**
- Mobile target: **93-98% of FP32** (stricter due to quantization)
- Validation via labeled datasets (ImageNet, COCO, SQuAD, etc.)
- Accuracy-first: submissions below target quality = INVALID (speed irrelevant)

### Energy (Tiny Benchmark)
- **Energy per inference** = Power (W) × Latency (s) in Joules
- Measured on microcontroller reference implementations
- No battery discharge modeling (mobile explicitly out of scope)

### Platform Coverage
- Datacenter GPUs: NVIDIA H100, A100, AMD MI300
- CPUs: Intel Xeon, AMD EPYC
- Mobile: iOS, Android flagship devices
- Embedded: ARM Cortex-M, RISC-V, DSP microcontrollers

---

## What MLPerf Does NOT Measure (Critical Gaps)

### 1. Real-Time Deadline Compliance

**MLPerf Reports**: P99 latency = 15 ms

**MLPerf Does NOT Report**:
- % of inferences exceeding hard deadline (e.g., "how many miss a 20 ms deadline?")
- Deadline miss consequences (drop vs. queue vs. block)
- Jitter distribution (variance around median)
- Sustained deadline compliance under thermal stress

**Why It Matters for BCI**:
- Motor imagery decoding: hard deadline ~100-200 ms (user expects fast feedback)
- Seizure detection: alert latency from event onset critical (not just query latency)
- Real-time feedback loops: missing deadline = wrong stimulus presentation

**Gap Impact**: A system with "P99 = 15 ms" might have 5% of queries at 500 ms (thermal throttle) or cache miss. MLPerf would mark this valid; BCI safety requires "99.99% within deadline."

---

### 2. Streaming and Continuous Workload Patterns

**What MLPerf Single-Stream Does**:
- Send query → Get response → Send next query (request-response)
- Variable inter-arrival time (depends on inference latency)
- Stateless (no memory between queries)

**What BCI Actually Does**:
- Continuous sensor stream (e.g., 250 Hz EEG = query every 4 ms)
- Fixed inter-arrival time (synchronized to sample clock)
- Stateful (maintains sliding window of prior samples)
- Streaming memory (inference depends on historical context)

**Example Gap**: 
- MLPerf single-stream: "Process one ResNet image, get result, process next image"
- BCI: "Process EEG sample every 4 ms, maintain 2-second history (500 samples), update 3-layer ConvNet state"
- MLPerf latency metric: query → response time
- BCI latency metric: sample arrival → decision available (can be negative if batch ready early)

**MLPerf Streaming Addition** (v1.3 Tiny):
- "Streaming Wakeword" for continuous speech detection
- Still single-stream latency measurement only (not buffer management, state retention)
- No multi-channel synchronization (BCI: 64+ EEG channels × 250 Hz)

**Gap Impact**: Cannot use MLPerf results to predict BCI performance under streaming inference.

---

### 3. Platform Effects (Thermal, Contention, Variability)

**What MLPerf Acknowledges**:

From MLPerf Mobile (MLSys 2022):
> "Battery life prediction requires modeling discharge curves, voltage regulation, thermal behavior, and device usage patterns—complexity beyond current scope. Thermal throttling further complicates fair measurement on battery-powered devices."

From MLPerf Power (2024):
> "Given these complexities, establishing a fair and transparent benchmark for measuring power consumption in battery-powered devices is beyond the current scope of work."

**MLPerf's Approach**: Eliminate platform effects via isolation
- Run in **controlled environment** (air-conditioned, isolated system)
- **Thermal equilibrium** (device warmed up to steady state before measurement)
- **No background processes** (system reserved for benchmark)
- **Power management disabled** (CPU at fixed frequency)

**What Doesn't Get Measured**:
1. **Thermal Throttling Over Time**
   - Phone GPU: first inference at 1000 MHz → after 2 min sustained load at 600 MHz
   - MLPerf: reports average P99 latency (masks dramatic slowdown)
   - BCI reality: continuous inference with thermally-triggered degradation

2. **Cache Effects and Contention**
   - Shared L3 cache on CPU (other cores running interference)
   - Page faults (code paged out, data in swap)
   - MLPerf: runs in isolation (no contention)
   - BCI reality: shared system with other tasks

3. **System State Dependence**
   - Garbage collection pauses (Java, Python)
   - OS scheduler preemption
   - Power state transitions
   - MLPerf: steady-state only

**Gap Impact**: MLPerf's "P99 = 5 ms" in isolated lab might become "P50 = 10 ms" under real clinical deployment (thermal + contention). No guidance on how to extrapolate.

---

### 4. Numerical Correctness and Determinism

**What MLPerf Validates**:
- Functional accuracy on validation dataset (99% of reference accuracy)
- Output is sensible (e.g., image class is valid)

**What MLPerf Does NOT Validate**:
1. **Determinism**: Same input, same hardware, identical run → same output?
   - Floating-point reduction order varies (GPU parallel ops non-associative)
   - MLPerf allows ±0.5% accuracy variance to accommodate this
   - No guarantee of reproducibility

2. **Adversarial Robustness**:
   - Small input perturbation (ε) → bounded output change?
   - MLPerf only tests on clean validation set
   - Doesn't test on adversarial examples

3. **Numerical Stability Under Quantization**:
   - INT8 vs. FP32: do outputs diverge on edge cases?
   - Accumulation error in deep pipelines?
   - MLPerf: checks 99% accuracy on test set (not stability analysis)

4. **Input Distribution Shift**:
   - Validation set != real deployment data
   - MLPerf does not test on out-of-distribution examples

**Why It Matters for BCI**:
- Neural signals are chaotic (small artifacts → large classification changes)
- Clinical decisions based on inference: need high confidence in correctness
- Pathological signals (seizures, artifacts) outside training distribution
- Quantization to INT8 for mobile: might lose critical discriminative features

**Gap Impact**: MLPerf submission shows "99.5% seizure detection accuracy on test set." Doesn't tell you:
- Robustness to electrode impedance variation (distributional shift)
- Sensitivity to quantization (INT8 vs FP32)
- Performance on edge cases (false-positive seizure-like EEG patterns)

---

## Comparison Table: MLPerf vs. BCI Requirements

| Aspect | MLPerf Measures | MLPerf Does NOT Measure | BCI Need |
|--------|-----------------|------------------------|----------|
| **Latency** | P90, P99 percentiles | Deadline miss rate, jitter distribution | Deadline compliance + miss rate |
| **Workload** | Request-response, fixed dataset | Streaming, state-dependent, online | Continuous sensor stream, sliding window state |
| **Platform** | Peak performance, isolated system | Platform effects, thermal degradation, contention | Real-world deployment: shared system, thermal transients |
| **Accuracy** | Functional accuracy on validation set | Adversarial robustness, distribution shift, determinism | Robustness to signal artifacts, pathological patterns |
| **State** | Stateless inference per query | Temporal dependencies, buffer management | Multi-channel synchronization, history window |
| **Power** | Steady-state power (datacenter/mobile) | Battery discharge, thermal behavior | Portable BCI headset: battery life, thermal constraints |

---

## Direct MLPerf Applications for BCI

✓ **Use MLPerf's accuracy-first paradigm**: Validate classifier accuracy (99% target) before speed testing

✓ **Adopt percentile reporting**: Use P90 for sample-level latency, P99 for batch deadline

✓ **Apply fixed-dataset validation**: Labeled EEG datasets (seizure, motor imagery) with ground truth

✓ **Leverage reference models**: Compare BCI models against standard baselines (OpenBMI, Physionet)

✓ **Mobile/Tiny metrics**: Energy-per-inference directly applicable to wearable BCI

---

## Necessary Extensions for BCI-Specific Benchmarking

**1. Deadline Semantics**
- Define hard vs. soft deadline
- Measure deadline miss rate (not just P99 latency)
- Track jitter distribution
- Specify consequence of miss (drop sample, queue, substitute)

**2. Streaming Workload Specification**
- Fixed sample rate (Hz) as primary parameter
- State retention model (sliding window size, state reset semantics)
- Synchronization to external clock (sample arrival event)
- Buffer occupancy and pipeline state metrics
- Multi-channel synchronization (EEG: 64+ channels × 250 Hz)

**3. Platform Characterization**
- Thermal profile: latency vs. time under sustained load
- Contention model: shared cache, system load effects
- Worst-case analysis under realistic OS conditions
- Not just average-case performance

**4. Signal-Specific Robustness**
- Adversarial robustness: small EEG perturbations (electrode noise) → bounded output
- Quantization sensitivity: FP32 → INT8 accuracy drop on edge cases
- Temporal drift: long-duration recording artifacts (impedance change, motion artifacts)
- Distribution shift: different patient populations, electrode configurations

**5. Clinical Appropriateness**
- False-positive rate at target sensitivity (ROC curve focus)
- Detection latency from event onset (not just inference latency)
- Confidence/uncertainty quantification (not binary decisions)
- Multi-class confusion matrix (not just top-1 accuracy)

---

## Integration with CORTEX Specification

**MLPerf Principles for CORTEX BCI Benchmark**:

1. **Accuracy-First Validation**: Define quality target (e.g., "99% classification accuracy on reference dataset") before measuring real-time performance

2. **Percentile-Based Latency Reporting**: Use P90 and P99 latency with statistical backing (not just average)

3. **Standardized Load Generator**: Create deterministic stimulus generator for BCI (equivalent to MLPerf LoadGen) to ensure reproducibility

4. **Fixed Reference Models and Datasets**: Specify canonical seizure detection or motor imagery models + labeled data

5. **Hardware Diversity**: Support multiple BCI platforms (EEG headsets, implanted arrays, portable vs. tethered)

**BCI-Specific Additions**:

6. **Real-Time Deadline Compliance**: Add deadline miss rate, jitter distribution, miss consequence specification

7. **Streaming State Specification**: Define buffer management, history window, multi-channel synchronization

8. **Platform Variability Characterization**: Measure thermal profile, contention effects, realistic OS conditions

9. **Signal-Specific Robustness**: Adversarial examples, quantization sensitivity, distribution shift validation

10. **Clinical Validation Metrics**: Sensitivity/specificity, detection latency from event onset, confidence quantification

---

## References and Key Quotes

**MLPerf Inference (ISCA 2020)**
- "MLPerf prescribes a set of rules and best practices to ensure comparability across systems with wildly differing architectures"
- Single-stream = P90 latency; Server = P99 latency with throughput constraint
- Accuracy-first: 99% of FP32 reference accuracy required for valid submission

**MLPerf Mobile (MLSys 2022)**
- "Battery life prediction... complexity beyond current scope"
- "Thermal throttling further complicates fair measurement on battery-powered devices"
- Acknowledges platform effects but treats as noise to eliminate, not measure

**MLPerf Tiny (NeurIPS 2021)**
- "All MLPerf Tiny benchmarks are single stream, meaning they measure the latency of a single inference"
- Energy-per-inference focus (Joules/inference)
- Four benchmarks for microcontroller-scale inference

**MLPerf Power (2024)**
- "Precise power measurement is always possible" is a misconception
- Mobile power measurement: "beyond the current scope of work"
- Measurement challenges with shared cooling, networking, cloud environments

---

## File Generated

- **Main Document**: `/Users/westonvoglesonger/Projects/CORTEX/docs/research/mlperf-methodology-analysis.md` (3,274 words, 24 KB)
- **This Summary**: `/Users/westonvoglesonger/Projects/CORTEX/docs/research/mlperf-gaps-for-bci.md`
