# Realistic vs. Ideal Benchmarking: CORTEX's Core Philosophy

**Core Thesis:**
Prior benchmarking work minimizes **all noise sources** to measure **peak performance** in **ideal conditions**.
CORTEX controls **deployment-relevant factors**, accepts **deployment-inherent variance**, and measures **what users will experience in production**.

---

## The Fundamental Difference

### Prior Work: "What CAN this kernel do?"
- **Goal:** Measure theoretical peak performance for algorithm comparison
- **Strategy:** Eliminate all variance sources
- **Environment:** Artificial ideal conditions that don't exist in production
- **Metric:** Single number (mean, median, min)
- **Use case:** "Which algorithm is faster?"

### CORTEX: "What WILL this kernel do in production?"
- **Goal:** Measure deployable performance including worst-case behavior
- **Strategy:** Control production-controllable factors, measure production-inherent variance
- **Environment:** Mimics real-time BCI deployment constraints
- **Metric:** Distributions (P50/P95/P99)
- **Use case:** "Will this meet real-time deadlines when deployed?"

---

## Noise Source Classification

The key insight: Not all "noise" is equal. Some is **artificial** (measurement artifacts), some is **deployment-inherent** (users will experience it).

| Noise Source | Prior Work | CORTEX | Rationale |
|--------------|------------|--------|-----------|
| **Measurement overhead** | Amortize via long runs | Accept 4-5% | Cannot amortize in streaming; within acceptable threshold |
| **DVFS transitions** | Disable to reduce variance | Disable because **production would** | Safety-critical RT systems run at fixed frequency |
| **Cache misses** | Warm-up until eliminated | **Accept and measure** | Production experiences context switches, OS scheduling |
| **Parallel contention** | Eliminate via isolation | Eliminate because **production would** | BCI runs on dedicated cores (safety-critical) |
| **JIT/GC pauses** | Warm-up to steady-state | N/A (C code) | Not applicable |
| **System scheduling** | Minimize/ignore | **Accept and measure** | Even RT Linux has jitter (<15µs); capture in distributions |

---

## Production Deployment Constraints

**What would a real-time BCI system do?**

1. ✅ **Set performance governor** (disable DVFS)
   - *Reason:* Transition latency (100-500µs) violates RT deadlines
   - *CORTEX:* Mandates platform control, quantifies penalty (2-4×)

2. ✅ **Pin to dedicated cores** (no parallel contention)
   - *Reason:* Safety-critical system, need determinism
   - *CORTEX:* Sequential execution enforced

3. ✅ **Run continuously at 160Hz** (streaming)
   - *Reason:* Real-time BCI constraint
   - *CORTEX:* Cannot warm-up indefinitely, must measure every window

4. ❌ **Cannot eliminate cache misses**
   - *Reason:* OS still schedules other processes, context switches happen
   - *CORTEX:* Measures cold and warm, captures in distributions

5. ❌ **Cannot eliminate scheduling jitter**
   - *Reason:* Even RT Linux has <15µs jitter
   - *CORTEX:* Captures in distributions (P95/P99)

---

## Why Prior Approaches Create Artificial Environments

### Example 1: lmbench (1s+ runs)
**Strategy:** Run each benchmark for 1+ seconds to amortize overhead

**Artificial because:**
- Real-time BCI processes 6.25ms windows (160Hz)
- Cannot batch 160 windows together (each is distinct real-time data)
- Cache state after 1s ≠ cache state in streaming workload

**Result:** Measures steady-state throughput, not per-window latency distributions

---

### Example 2: Google Benchmark (10ms batching)
**Strategy:** "For sub-µs operations, run each sample for 10ms+"

**Artificial because:**
- Loops on same data → cache always warm
- Production sees distinct windows → cache may be cold
- Hides bimodality (cold vs. warm)

**Result:** Measures average-case, misses worst-case (which RT systems must plan for)

---

### Example 3: SPEC CPU (median of 3 runs)
**Strategy:** Run 3 times, report median

**Artificial because:**
- Production runs continuously, not 3 times
- Median hides tail latency (P95/P99)
- 3 samples insufficient for worst-case characterization

**Result:** Good for algorithm comparison, poor for deployment planning

---

## CORTEX's Production-Mimicking Environment

### What CORTEX Controls (Because Production Would)

1. **Platform configuration:**
   - Fixed CPU frequency (performance governor)
   - No turbo boost (consistent frequency)
   - Documented, reproducible setup

2. **Execution model:**
   - Sequential (dedicated cores in production)
   - Per-window measurement (streaming constraint)
   - No artificial batching

3. **Correctness:**
   - Oracle validation (production must be correct)
   - Numerical tolerance (1e-5 for f32)

### What CORTEX Accepts (Because Production Must)

1. **Cache variability:**
   - Context switches → cold cache
   - OS scheduling → unpredictable state
   - **Measured in distributions**

2. **Measurement overhead:**
   - 4-5% for 50µs kernels
   - Cannot amortize (streaming)
   - Within acceptable threshold (3-5%)

3. **System nondeterminism:**
   - ASLR, branch prediction, prefetcher state
   - Modern hardware/software randomization
   - **Captured in thousands of samples**

### What CORTEX Measures (Because Users Experience It)

1. **Full distributions:**
   - P50 (typical case)
   - P95/P99 (worst-case for RT planning)
   - Histograms (reveals bimodality)

2. **Per-window telemetry:**
   - Thousands of measurements
   - Statistical power for tail characterization
   - Temporal patterns (jitter over time)

3. **Deadline misses:**
   - Real-time constraint validation
   - Not just "how fast?" but "fast enough?"

---

## Concrete Example: Cache Effects

### Prior Work Approach
```
Warm-up phase:
  for i in 1..1000:
    kernel(data)  // Same data, cache becomes warm

Measurement phase:
  time_start = now()
  for i in 1..10000:
    kernel(data)  // Cache stays warm
  time_end = now()
  report mean(time_end - time_start) / 10000
```

**Result:** Measures warm-cache performance (ideal)

**Problem:** Production doesn't have 1000-iteration warm-up. First window may be cold.

---

### CORTEX Approach
```
for each window in streaming_data:
  time_start = now()
  kernel(window)  // Distinct data, cache state varies
  time_end = now()
  record(time_end - time_start)

report P50, P95, P99 of all measurements
```

**Result:** Measures distribution including cold-cache starts (realistic)

**Rationale:** Users experience this distribution, not just warm-cache mean

---

## When Ideal Benchmarking IS Appropriate

CORTEX's approach is **not** universally better. Ideal benchmarking is appropriate when:

1. **Comparing algorithms abstractly** (which is asymptotically faster?)
2. **Hardware evaluation** (what's the CPU's peak throughput?)
3. **Compiler optimization** (did this change improve code generation?)

CORTEX's approach is appropriate when:

1. **Deployment planning** (will this meet real-time deadlines?)
2. **Safety-critical systems** (what's the worst-case latency?)
3. **Real-time constraints** (can we handle 160Hz streaming?)

---

## The Tension: Comparability vs. Realism

**Prior work optimizes for comparability:**
- Eliminate all variance → clean comparison
- Same platform setup across studies
- Repeatable, portable

**CORTEX optimizes for deployment validity:**
- Measure realistic variance → characterize what users see
- Platform setup mimics production (performance governor, dedicated cores)
- Repeatable, but distribution-aware

**Trade-off:**
- Harder to compare CORTEX results across different platforms (distributions differ)
- But more accurate prediction of deployment behavior

---

## Positioning Statement for Paper

**Research Question:**
*"How do you benchmark real-time streaming kernels when the goal is deployment validation (will it meet deadlines?) rather than algorithm comparison (which is faster in ideal conditions)?"*

**CORTEX's Answer:**
*"Distinguish between artificial noise (measurement artifacts to eliminate) and deployment-inherent variance (user-experienced behavior to measure). Control what production would control (DVFS, parallel contention), accept what production must accept (cache misses, scheduling jitter), and measure what users will experience (latency distributions including worst-case)."*

---

## Key Contributions

1. **Conceptual:** Framework for distinguishing artificial noise vs. deployment-inherent variance
2. **Methodological:** Production-mimicking benchmarking for real-time systems
3. **Empirical:** Quantified deployment-relevant factors (DVFS transitions, cache effects) at timescales where they're first-order
4. **Statistical:** Distribution-based metrics (P95/P99) for worst-case planning, not just average-case optimization

---

## Table: Ideal vs. Realistic Benchmarking

| Aspect | Ideal Benchmarking | Realistic Benchmarking (CORTEX) |
|--------|-------------------|--------------------------------|
| **Goal** | Peak performance | Deployable performance |
| **Environment** | Eliminate all variance | Mimic production constraints |
| **Metrics** | Mean, median, min | P50/P95/P99 distributions |
| **DVFS** | Disable to reduce noise | Disable because production would |
| **Cache** | Warm-up to eliminate misses | Accept misses (production sees them) |
| **Samples** | Few (3-10) | Thousands (statistical power) |
| **Use case** | Algorithm comparison | Deployment validation |
| **Question answered** | "Which is faster?" | "Will it meet deadlines?" |

---

## Future Work: Empirical Validation

To strengthen this positioning, we should quantify:

1. **Cache effect magnitude:** Cold vs. warm latency distributions for CORTEX kernels
2. **Parallel contention:** Measure 2-4× prediction for CORTEX workloads specifically
3. **Cross-platform distributions:** Show that realistic benchmarking produces different distributions on different platforms (expected), but same kernel meets/fails deadlines consistently

---

**END DOCUMENT**
