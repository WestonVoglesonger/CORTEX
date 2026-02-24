# 8. Benchmarking Methodology

## 8.1 Overview

This section defines the normative framework for conducting performance measurements on CORTEX-compatible kernels following successful validation. The benchmarking methodology separates measurement from validation to ensure statistical robustness and reproducible performance characterization.

**Key Principles:**

1. **Sustained Measurement**: Benchmarks execute for extended duration (not single-shot measurements) to capture steady-state behavior and amortize harness overhead
2. **Warmup Protocol**: Initial execution windows are discarded to eliminate cache-cold and frequency-scaling transients
3. **Load Profiles**: Background CPU load is configurable to address platform-specific frequency scaling behavior
4. **Two-Phase Separation**: Validation (correctness) and measurement (performance) are distinct phases with different objectives
5. **Platform-State Capture**: System state (CPU governor, frequency, thermal conditions) is recorded for reproducibility

**Conformance Levels:**

A **basic conformant implementation** MUST support:
- Sustained measurement with configurable duration
- Warmup window discarding
- Idle load profile
- Core telemetry collection

A **fully conformant implementation** MUST additionally support:
- Medium and heavy load profiles
- Platform-state metadata capture in telemetry
- CPU governor and frequency logging

---

## 8.2 Sustained Measurement

### 8.2.1 Rationale for Sustained Measurement

Single-shot measurements are unsuitable for real-time system characterization because:

1. **Harness Overhead Amortization**: One-time initialization (memory allocation, thread creation, cache initialization) dominates very short runs. Sustained measurement distributes this overhead over many windows, revealing true kernel performance.

2. **Steady-State Behavior**: The first few windows execute with cold caches and unpredictable CPU frequency. Kernel performance stabilizes after 10–30 windows. Extended benchmarks reach steady-state before measurement begins (via warmup).

3. **Percentile Accuracy**: Latency percentiles (P95, P99, P99.9) require sufficient samples (~500+) for statistical confidence. Single-shot measurements provide no confidence interval on tail behavior.

4. **Variability Characterization**: Real-time applications must tolerate normal jitter within the distribution. Sustained benchmarks reveal the full latency distribution, not just a point estimate.

**Normative Requirements:**

1. Implementations MUST execute benchmarks for at least `duration_seconds` (from the configuration, Section 5).
2. The benchmark clock MUST measure elapsed time using a monotonic clock (CLOCK_MONOTONIC on Linux, equivalent on other platforms).
3. Implementations MUST NOT stop measurement before `duration_seconds` have elapsed, even if a window misses its deadline.

### 8.2.2 Duration Parameters

The `benchmark.parameters` section in the run configuration specifies measurement duration:

```yaml
benchmark:
  parameters:
    duration_seconds: 120    # Total measurement time (after warmup)
    repeats: 5               # Number of independent runs
    warmup_seconds: 10       # Initial discarded period
```

**Field Semantics:**

- **`duration_seconds`**: Total time for measurement after warmup expires. MUST be > 0. Typical values: 60–300 seconds
- **`repeats`**: Number of independent benchmark runs. Each repeat uses fresh process or thread state. MUST be ≥ 1. Typical values: 3–5
- **`warmup_seconds`**: Initial period whose data is discarded. MUST be ≥ 0. Typical values: 5–30 seconds

**Normative Requirements:**

1. Implementations MUST measure elapsed time from when the first window is released (after warmup) until `duration_seconds` have elapsed.
2. Implementations MUST NOT include warmup period in elapsed time calculation.
3. Implementations MUST complete at least one full window execution cycle (window to window, subject to hop timing) within each repeat.
4. The deadline for window N is calculated as: `deadline_ns = release_ts_ns + (H / Fs) × 10^9` (see Section 6.3.4).

### 8.2.3 Multi-Repeat Averaging

When `repeats > 1`, implementations execute the benchmark multiple times and report statistics across repeats:

**Normative Requirements:**

1. Each repeat MUST start with a fresh process/thread state (not a continuation of previous repeat).
2. Between repeats, implementations SHOULD allow a brief settle period (5–10 seconds) for CPU frequency and thermal transients to stabilize.
3. Telemetry records from all repeats MUST be aggregated in the output with a `repeat` field indicating the iteration number (1-indexed).
4. Derived metrics (latency distributions, jitter percentiles) MUST combine data from all repeats.

**Example:** With `repeats: 5` and `duration_seconds: 120`, the total measurement time is ~5 × 120 = 600 seconds, yielding ~1200 windows per kernel (assuming 160-sample window, 80-sample hop, 160 Hz sample rate).

---

## 8.3 Warmup Protocol

### 8.3.1 Purpose of Warmup

Warmup windows are executed but discarded because:

1. **Cache Cold Start**: The first window executes with all CPU caches containing prior data. Cache misses during the first window dominate execution time, inflating latency. By window 10–20, cache locality stabilizes. Warmup discards this transient.

2. **CPU Frequency Scaling Transients**: On systems with dynamic CPU frequency scaling (e.g., macOS with DVFS), the first few windows may execute at low frequency before the governor ramps up. Warmup allows the frequency governor to reach stable state.

3. **TLB and Branch Prediction**: CPU branch prediction and Translation Lookaside Buffer (TLB) entries accumulate during warmup. Early windows have poor prediction accuracy; later windows benefit from trained predictors.

4. **Harness Initialization**: Logging, telemetry buffering, and other harness subsystems may warm up during the first windows.

**Empirical Evidence (macOS M1, DVFS Study, Nov 2025):**

When comparing idle vs. medium background load on BCI signal processing kernels:

| Kernel | Idle Mean (µs) | Medium Load Mean (µs) | Variance | Warmup Impact |
|--------|------|------|---|---|
| bandpass_fir | 4969 | 2554 | -48.6% | ~10s to stabilize |
| car | 36 | 20 | -45.5% | ~5s to stabilize |
| goertzel | 417 | 196 | -53.0% | ~10s to stabilize |
| notch_iir | 115 | 61 | -47.4% | ~5s to stabilize |

The 45–53% performance delta in medium load is primarily due to sustained CPU frequency (avoiding DVFS downscaling). Warmup ensures consistent frequency for subsequent measurement.

### 8.3.2 Warmup Execution

Warmup windows are executed identically to measurement windows: they release at the scheduled time, execute the kernel, and record telemetry. The only difference is the `warmup` flag in telemetry records.

**Normative Requirements:**

1. Implementations MUST execute `warmup_seconds` worth of windows before beginning measurement data collection.
2. The `warmup_seconds` period is measured from the first window release (start of first window, not arrival of first data block).
3. Implementations MUST record telemetry for warmup windows but mark them with `warmup: 1` in the telemetry record.
4. Implementations MUST NOT include warmup windows in latency statistics, deadline miss counts, or percentile calculations.
5. Implementations MUST NOT count warmup windows toward the reported "total windows" in summaries.

**Example:** With `warmup_seconds: 10`, window size W=160, hop H=80, sample rate Fs=160 Hz:
- Window arrival interval: H / Fs = 80 / 160 = 0.5 seconds
- Windows in 10 seconds: 10 / 0.5 = 20 windows
- After window 20 completes, measurement begins
- Windows 21+ are included in statistics

### 8.3.3 Warmup Marker

The `warmup` field in telemetry (Section 6.2.1) MUST be:
- `1` for windows released before time `warmup_seconds` elapses
- `0` for windows after warmup expires

Implementations MUST set the warmup flag consistently and make it available to downstream analysis tools for filtering.

---

## 8.4 Load Profiles

### 8.4.1 Load Profile Purpose

Load profiles define the background CPU utilization during benchmarks. They address the fundamental problem that modern CPUs scale frequency dynamically based on load, causing benchmarks on "idle" systems to execute at reduced frequency.

**The Problem:** Dynamic Voltage and Frequency Scaling (DVFS)

On most modern systems (macOS, Linux with `ondemand`/`schedutil` governors), CPU frequency automatically scales with load:
- **Idle (0% load)**: Frequency downscales to 0.5–1.0 GHz (low-power state)
- **Moderate load (50%)**: Frequency rises to 2–3 GHz
- **High load (100%)**: Frequency boosts to turbo frequency (3–4+ GHz)

This creates a fundamental benchmark problem: **measuring performance on an idle system does not reflect how the kernel executes under normal operating conditions**. Real-world BCI systems have background processes (I/O, display, data logging) maintaining non-zero CPU load.

**Empirical Evidence (macOS M1, November 2025):**

In the DVFS validation study, idle-mode benchmarks on an M1 MacBook Pro showed **45–53% higher latencies** than medium-load benchmarks:

| Kernel | Idle Latency | Medium-Load Latency | Difference |
|--------|-------------|-------------------|-----------|
| bandpass_fir | 5015 µs | 2325 µs | -53.6% faster |
| car | 28 µs | 13 µs | -53.6% faster |
| goertzel | 350 µs | 138 µs | -60.6% faster |
| notch_iir | 125 µs | 55 µs | -56.0% faster |

The medium-load configuration kept CPU frequency elevated (reducing DVFS variance to <10%), while idle mode exhibited frequency downscaling causing 45–50% mean latency inflation.

### 8.4.2 Load Profile Definitions

Three standard load profiles are defined:

#### **Profile A: Idle**
- **Configuration**: No artificial background load
- **Use Case**: Baseline measurement, minimal interference, legacy compatibility
- **Recommendation**: NOT recommended for macOS; may be used on Linux with manual CPU governor control
- **Caveat**: Subject to DVFS-induced variance on modern platforms

**Idle Profile Implementation:**
```yaml
benchmark:
  load_profile: "idle"
```

Implementations MUST NOT generate artificial load. The system runs measurement processes only.

#### **Profile B: Medium (RECOMMENDED)**
- **Configuration**: Moderate sustained background load on N/2 CPU cores at 50% utilization
- **Use Case**: **Recommended for macOS and systems with DVFS**; simulates typical operating environment
- **CPU Utilization**: For N-core system, activate (N/2) cores at 50% load
- **Tool**: `stress-ng` (requires installation)
- **Expected Frequency**: Sustained at ~2–3 GHz (prevents downscaling)
- **Variance**: <10% across runs

**Medium Profile Implementation:**
```yaml
benchmark:
  load_profile: "medium"
```

The medium profile maintains CPU frequency in a consistent middle range without causing contention or preemption of the benchmark thread.

**Example (8-core system):** Activate 4 CPU cores with 50% load:
```bash
stress-ng --cpu 4 --cpu-load 50 --timeout 120s &
```

#### **Profile C: Heavy**
- **Configuration**: High sustained background load on all N CPU cores at 90% utilization
- **Use Case**: Stress testing, worst-case analysis, heavy contention measurement
- **CPU Utilization**: For N-core system, activate N cores at 90% load
- **Tool**: `stress-ng`
- **Expected Frequency**: Sustained at turbo frequency (~3.5–4 GHz)
- **Variance**: High (CPU contention preempts benchmark thread frequently)

**Heavy Profile Implementation:**
```yaml
benchmark:
  load_profile: "heavy"
```

**Example (8-core system):** Activate 8 CPU cores with 90% load:
```bash
stress-ng --cpu 8 --cpu-load 90 --timeout 120s &
```

### 8.4.3 Platform-Specific Guidance

#### **macOS (DVFS Required)**

**Normative Requirement:** On macOS, implementations MUST use `load_profile: "medium"` in production benchmarks.

**Rationale:** macOS lacks userspace CPU frequency control. Dynamic frequency scaling is always active. The medium load profile is the only practical way to ensure consistent CPU frequency without manual intervention.

**Configuration Example:**
```yaml
benchmark:
  parameters:
    duration_seconds: 120
    repeats: 5
    warmup_seconds: 10
  load_profile: "medium"
```

**Implementation Note:** If `stress-ng` is unavailable on macOS, implementations SHOULD fall back to idle mode with a warning message. This is a degradation in reproducibility but prevents benchmark failure.

#### **Linux (Tunable CPU Governor)**

**Optional Guidance:** On Linux systems with root privileges, the CPU governor can be manually set to `performance`:

```bash
sudo cpupower frequency-set --governor performance
```

This achieves frequency stability similar to medium load without artificial background processes. Then benchmarks can use:
```yaml
benchmark:
  load_profile: "idle"
```

**Normative Requirement:** Implementations MAY document this alternative but MUST NOT require root access for valid benchmarks. Non-root users MUST use load profiles for reproducibility.

### 8.4.4 Load Profile Implementation

Implementations MUST implement load profiles using the `stress-ng` utility. If `stress-ng` is unavailable:

1. Implementations MAY fall back to `idle` mode with a warning
2. Implementations MAY implement alternative load generators (custom CPU loop, etc.)
3. Implementations MUST document the alternative method clearly
4. Implementations MUST NOT silently ignore a requested load profile

**Normative Requirements:**

1. Implementations MUST spawn the load generator process before the first benchmark window releases.
2. Load must remain active throughout all repeats and measurement windows.
3. Implementations MUST terminate the load generator after the final repeat completes.
4. Implementations MUST record the `load_profile` in telemetry metadata for analysis.
5. Implementations SHOULD log the actual stress-ng command and its process ID for reproducibility.

**Example Shell Command:**
```bash
# Medium profile on 8-core system (N/2 cores @ 50%)
stress-ng --cpu 4 --cpu-load 50 --timeout 600s --quiet &
LOAD_PID=$!

# Run benchmarks...

# Terminate load after benchmarks
kill $LOAD_PID
wait $LOAD_PID
```

---

## 8.5 Two-Phase Separation: Validation vs. Measurement

### 8.5.1 Distinct Objectives

**Validation Phase (Pre-Benchmark):**
- **Goal**: Verify kernel correctness (does it produce correct output?)
- **Method**: Compare kernel output against oracle output using defined tolerances
- **Success Criteria**: Numerical error within tolerance limits
- **Result**: Pass/fail binary decision; kernel is functionally correct or not
- **Location**: Section 7 (Validation Protocol)

**Measurement Phase (This Section):**
- **Goal**: Characterize performance (how fast and consistent is execution?)
- **Method**: Execute kernel repeatedly under controlled conditions; collect latency telemetry
- **Success Criteria**: Statistical distributions, deadline meeting, jitter quantiles
- **Result**: Performance metrics (mean, P95, jitter, deadline miss rate)
- **Prerequisite**: Validation MUST pass first

### 8.5.2 Why Separation Matters

Combining validation and measurement creates ambiguity:

**Without Separation (Anti-Pattern):**
```
For each test case:
  Run kernel with test input
  Compare output to oracle
  If mismatch: report failure
  Measure latency during run
```

**Problem**: If validation fails mid-benchmark, was performance bad or was the kernel incorrect? Confounded variables make root-cause analysis impossible.

**With Separation (Correct Pattern):**
```
Phase 1 - Validation:
  For each test case:
    Run kernel with test input
    Compare output to oracle
    If ANY mismatch: fail immediately, do not proceed to measurement

Phase 2 - Measurement:
  (Assumption: kernel is functionally correct from Phase 1)
  For each repeat:
    For duration_seconds:
      Run kernel with dataset
      Collect latency telemetry
      Ignore correctness (already validated)
```

**Benefits:**
1. **Clean Root Cause Analysis**: Performance anomalies are not confounded with correctness failures
2. **Faster Iteration**: Validation is quick; measurement is lengthy. Separate phases allow quick rejection of broken kernels before expensive measurement
3. **Statistical Robustness**: Measurement phase assumes 100% correctness; no need to handle error cases that should have failed in validation
4. **Reproducibility**: Performance metrics are only reported for functionally correct kernels

### 8.5.3 Normative Requirements

1. Implementations MUST execute the Validation Protocol (Section 7) completely before beginning measurement.
2. Implementations MUST NOT begin measurement if validation fails.
3. Implementations MUST NOT re-validate during measurement phase (assume correctness from Phase 1).
4. Implementations MUST report validation status (pass/fail) separately from measurement results.
5. If any window's output differs from expected behavior during measurement (should not happen if validation passed), implementations SHOULD log the anomaly but continue measurement (measurement phase assumes correctness).

---

## 8.6 Platform-State Capture

### 8.6.1 Purpose of Platform-State Capture

Benchmarks are influenced by system-level factors beyond the kernel code:

1. **CPU Frequency**: Determines peak throughput and latency
2. **CPU Governor**: Controls frequency scaling policy
3. **Thermal State**: Thermal throttling degrades performance
4. **CPU Load**: Background processes affect frequency and cache behavior
5. **Power Management**: Sleep states, clock gating affect startup latency

To enable reproducibility and root-cause analysis, implementations MUST capture this state in telemetry metadata.

### 8.6.2 Platform-State Fields

Implementations SHOULD capture the following system state at benchmark start and record in telemetry metadata (Section 6.4.1):

#### CPU State
- **`cpu_governor`** (string): Current CPU frequency governor (e.g., `"performance"`, `"ondemand"`, `"powersave"`)
- **`cpu_frequency_mhz`** (integer): Current CPU frequency in MHz at benchmark start
- **`cpu_count`** (integer): Total number of CPU cores on the system
- **`cpu_model`** (string): CPU model name (e.g., `"Apple M1"`, `"Intel Core i7-10700K"`)

#### Thermal State
- **`thermal_celsius`** (float or null): CPU temperature in Celsius at benchmark start (if available)
- **`thermal_throttling_active`** (boolean): Whether thermal throttling is currently active (if detectable)

#### Memory State
- **`total_ram_mb`** (integer): Total system RAM in megabytes
- **`available_ram_mb`** (integer): Available RAM at benchmark start
- **`page_cache_mb`** (integer): Kernel page cache size at benchmark start (Linux-specific)

#### Load State
- **`load_profile`** (string): Benchmark load profile (`"idle"`, `"medium"`, `"heavy"`)
- **`system_load_1min`** (float): System load average (1-minute) at benchmark start
- **`system_load_5min`** (float): System load average (5-minute) at benchmark start
- **`system_load_15min`** (float): System load average (15-minute) at benchmark start

#### OS/Platform State
- **`os_name`** (string): Operating system (e.g., `"Darwin"`, `"Linux"`)
- **`os_version`** (string): OS version (e.g., `"23.2.0"`)
- **`kernel_version`** (string): Kernel version (Linux) or similar
- **`hostname`** (string): System hostname for multi-system studies

### 8.6.3 Platform-State Recording

**Normative Requirements:**

1. Implementations MUST attempt to read CPU governor, frequency, and thermal state at the start of each benchmark run.
2. Implementations MUST record these values in the telemetry metadata (NDJSON `_type: "system_info"` record or CSV comment header).
3. If a metric is unavailable (e.g., thermal state not exposed by OS), implementations SHOULD omit it or set to null rather than guessing.
4. Implementations SHOULD document which metrics are available on each platform.

**Example (NDJSON Metadata Record):**
```json
{
  "_type": "system_info",
  "os": "Darwin 23.2.0",
  "cpu": "Apple M1",
  "hostname": "Westons-MacBook-Air-2.local",
  "cpu_count": 8,
  "total_ram_mb": 8192,
  "cpu_governor": "ondemand",
  "cpu_frequency_mhz": 1200,
  "thermal_celsius": 58.5,
  "load_profile": "medium",
  "system_load_1min": 2.45,
  "system_load_5min": 1.89,
  "system_load_15min": 1.12
}
```

**Example (CSV Comment Header):**
```csv
# System Information
# OS: Darwin 23.2.0
# CPU: Apple M1 (8 cores)
# Hostname: Westons-MacBook-Air-2.local
# Total RAM: 8192 MB
# CPU Governor: ondemand
# CPU Frequency at Start: 1200 MHz
# Thermal: 58.5°C
# Load Profile: medium
# System Load (1/5/15 min): 2.45 / 1.89 / 1.12
#
run_id,plugin_name,window_index,...
```

### 8.6.4 Reproducibility Through State Capture

By recording platform state, researchers can:

1. **Identify Configuration Differences**: If Run A uses `performance` governor and Run B uses `ondemand`, latency differences are attributable to governor policy, not kernel changes
2. **Detect Thermal Effects**: Correlate thermal state with performance; detect thermal throttling anomalies
3. **Normalize Across Platforms**: Record CPU frequency to account for different hardware (M1 vs Intel vs Snapdragon)
4. **Reproduce Exact Conditions**: Archive metadata for future reproduction attempts
5. **Audit for Confounds**: Statistical analysis can condition on platform state variables

---

## 8.7 Telemetry Collection During Measurement

### 8.7.1 Per-Window Telemetry

During the measurement phase, implementations MUST collect telemetry for every window according to the schema in Section 6.2. Key requirements:

1. **Core Timing**: Every window MUST record `release_ts_ns`, `start_ts_ns`, `end_ts_ns`, `deadline_ts_ns`
2. **Deadline Tracking**: Every window MUST record `deadline_missed` (1 if late, 0 if on-time)
3. **Window Metadata**: Every window MUST record `W`, `H`, `C`, `Fs`, `warmup`, `repeat`
4. **Monotonic Clock**: All timestamps MUST use monotonic clock (CLOCK_MONOTONIC)
5. **Nanosecond Precision**: Timestamps MUST be in nanoseconds (not milliseconds)

**Normative Requirements:**

1. Implementations MUST NOT skip windows or sub-sample during measurement
2. Implementations MUST record every window's telemetry, including those that miss deadlines
3. Implementations MUST include warmup windows with `warmup: 1` marker (for filtering during analysis)
4. Implementations MUST NOT artificially delay or skip windows to meet deadline targets

### 8.7.2 Aggregation Across Repeats

When `repeats > 1`, implementations SHOULD aggregate telemetry files:

1. **Per-Kernel File**: Write all windows from all repeats to a single telemetry file (e.g., `results/bandpass_fir/telemetry.ndjson`)
2. **Repeat Field**: Each record includes `repeat` (1-indexed iteration number)
3. **Analysis Tools**: Downstream tools can filter by `warmup`, `repeat` fields to compute statistics

**Example (NDJSON file content):**
```json
{"_type":"system_info","os":"Darwin 23.2.0","cpu_count":8,...}
{"run_id":"1762310612183","plugin":"bandpass_fir","window_index":0,"release_ts_ns":21194971498000,...,"warmup":1,"repeat":1}
{"run_id":"1762310612183","plugin":"bandpass_fir","window_index":1,"release_ts_ns":21195476495000,...,"warmup":1,"repeat":1}
...
{"run_id":"1762310612183","plugin":"bandpass_fir","window_index":20,"release_ts_ns":21203000000000,...,"warmup":0,"repeat":1}
{"run_id":"1762310612183","plugin":"bandpass_fir","window_index":21,"release_ts_ns":21203500000000,...,"warmup":0,"repeat":1}
...
{"run_id":"1762310612183","plugin":"bandpass_fir","window_index":240,"release_ts_ns":21303500000000,...,"warmup":0,"repeat":5}
```

---

## 8.8 Benchmark Completion Criteria

### 8.8.1 Success Conditions

A benchmark run is considered **complete** if:

1. **Validation Phase Passed**: Kernel produced correct output (Section 7)
2. **Measurement Duration Met**: All repeats executed for at least `duration_seconds` each
3. **Warmup Completed**: At least `warmup_seconds` of windows were executed and marked
4. **Telemetry Collected**: All windows have complete telemetry records
5. **No Uncaught Errors**: No exceptions or crashes during measurement (expected errors like deadline misses are normal)

### 8.8.2 Early Termination

Implementations MAY stop measurement early if:

1. **User Interruption**: User sends SIGINT (Ctrl+C) - implementations SHOULD gracefully flush telemetry and exit
2. **Resource Exhaustion**: Out of memory, disk full - implementations SHOULD log error and exit cleanly
3. **Kernel Crash**: Kernel executable crashes or hangs - implementations SHOULD report error and skip to next kernel

**Normative Requirement:** Implementations MUST NOT silently discard partial results. Incomplete benchmark runs MUST be clearly marked or quarantined for manual review.

---

## 8.9 Measurement Output

### 8.9.1 File Locations

Telemetry files MUST be written to the directory structure defined in Section 6.6:

```
results/
├── run-2025-11-15-003/
│   ├── telemetry.ndjson                    # Aggregated (all kernels)
│   ├── bandpass_fir/
│   │   ├── telemetry.ndjson                # Per-kernel telemetry
│   │   └── telemetry.csv                   # Per-kernel CSV (if enabled)
│   ├── car/
│   │   ├── telemetry.ndjson
│   │   └── telemetry.csv
│   ├── goertzel/
│   │   ├── telemetry.ndjson
│   │   └── telemetry.csv
│   └── notch_iir/
│       ├── telemetry.ndjson
│       └── telemetry.csv
```

**Normative Requirements:**

1. Implementations MUST create output directories if they do not exist
2. Implementations MUST write per-kernel telemetry files for each kernel in the run
3. Implementations SHOULD write aggregated telemetry combining all kernels
4. Implementations MUST use `.ndjson` extension for NDJSON files (Section 6.4.1)
5. Implementations MUST use `.csv` extension for CSV files (Section 6.4.2)

### 8.9.2 Summary Report (Optional)

Implementations MAY generate a human-readable summary report alongside telemetry:

**Example `results/run-2025-11-15-003/SUMMARY.md`:**

```markdown
# Benchmark Run Summary

**Date**: 2025-11-15 14:30:00 UTC
**Duration**: 600 seconds (5 repeats × 120 seconds)
**Load Profile**: medium
**Warmup**: 10 seconds per repeat

## Per-Kernel Results

### bandpass_fir
- Windows: 1203
- Mean Latency: 2554 µs
- Median Latency: 2325 µs
- P95 Jitter: 703 µs
- Deadline Misses: 0 (0.00%)

### car
- Windows: 1204
- Mean Latency: 19.61 µs
- Median Latency: 13 µs
- P95 Jitter: 20 µs
- Deadline Misses: 0 (0.00%)

[... etc ...]

## System State
- OS: Darwin 23.2.0
- CPU: Apple M1 (8 cores)
- Frequency: 1200–2300 MHz
- Thermal: 58.5°C
- Load Profile: medium (4 cores @ 50%)
```

---

## 8.10 Conformance

An implementation conforms to this Benchmarking Methodology section if:

1. It executes benchmarks for at least `duration_seconds` (sustained measurement, not single-shot)
2. It executes and marks `warmup_seconds` of initial windows before measurement
3. It supports at least idle load profile; SHOULD support medium and heavy profiles
4. It separates validation (Phase 1, Section 7) from measurement (Phase 2, this section)
5. It records platform state (CPU governor, frequency, thermal) in telemetry metadata
6. It implements per-window telemetry collection with nanosecond timestamps
7. It uses monotonic clock source for all timing measurements
8. It supports multi-repeat benchmarks with the `repeat` field in telemetry

**Platform-Specific Conformance:**

- **On macOS**: Implementations MUST support medium load profile for reproducible results
- **On Linux**: Implementations MUST support idle profile; medium/heavy are RECOMMENDED
- **On other platforms**: Implementations SHOULD support all three profiles or document which are available

---

## 8.11 Rationale

### 8.11.1 Why Sustained Measurement?

Single-shot benchmarks are misleading because initial windows execute with cold caches and transient CPU frequency scaling. Harness overhead dominates short runs. Sustained measurement allows steady-state behavior to emerge and amortizes fixed overhead over many windows, revealing true kernel performance.

### 8.11.2 Why Warmup Protocol?

The first 5–30 windows execute differently (cold cache, frequency ramping, TLB misses) compared to steady state. Discarding warmup windows ensures statistical measurements reflect normal operation, not exceptional startup behavior.

### 8.11.3 Why Load Profiles?

Modern CPUs scale frequency with load. Idle systems run at reduced frequency, inflating latencies. The DVFS validation study (Nov 2025) documented 45–53% latency inflation in idle mode due to frequency downscaling. Load profiles ensure consistent CPU frequency for reproducible measurements.

### 8.11.4 Why Two-Phase Separation?

Validation (correctness) and measurement (performance) have different objectives. Combining them creates confounded variables: is slow performance due to incorrect implementation or systemic factors? Separating phases enables clean root-cause analysis and faster iteration (quick rejection of broken kernels before expensive measurement).

### 8.11.5 Why Platform-State Capture?

Benchmarks are not isolated from the system. CPU frequency, thermal state, and competing load dramatically affect performance. Recording this state enables:
- Reproducibility (future runs can match conditions)
- Root-cause analysis (identify confounding factors)
- Cross-platform comparison (normalize for frequency differences)
- Audit trail (detect when conditions changed between runs)

---

## 8.12 Implementation Checklist

Implementations can use this checklist to verify conformance:

- [ ] Sustain benchmark execution for full `duration_seconds` (not early termination)
- [ ] Implement warmup discarding with `warmup_seconds` parameter
- [ ] Support idle load profile as baseline
- [ ] Support medium load profile (RECOMMENDED for macOS)
- [ ] Support heavy load profile (OPTIONAL, for stress testing)
- [ ] Use stress-ng for load generation (or document alternative)
- [ ] Record `warmup` flag for every window
- [ ] Record `repeat` iteration number across multi-repeat benchmarks
- [ ] Use CLOCK_MONOTONIC for timestamp source
- [ ] Collect nanosecond-precision timestamps
- [ ] Capture CPU governor, frequency, thermal state in metadata
- [ ] Generate per-kernel telemetry files in correct directory structure
- [ ] Support both NDJSON and CSV output formats
- [ ] Include system metadata in first telemetry record
- [ ] Document platform-specific limitations (e.g., thermal state unavailable)

---

**End of Section 8: Benchmarking Methodology**
