# 9. Statistical Reporting

## 9.1 Distributional Metrics

### 9.1.1 Latency Percentiles

Latency is the fundamental performance metric in real-time signal processing. A single mean value hides critical tail behavior that determines real-time system viability. CORTEX implementations MUST report latency as a **full distribution**, characterized by percentile statistics.

**Normative Requirements:**

1. Implementations MUST compute latency for each window as: `latency_ns = end_ts_ns - start_ts_ns`
2. Implementations MUST report the following percentiles from the latency distribution:
   - **P50 (Median)**: The 50th percentile, representing typical latency
   - **P95**: The 95th percentile, representing worst-case latency under normal operation
   - **P99**: The 99th percentile, representing extreme tail latency
3. Implementations SHOULD additionally report P75 and P99.9 for comprehensive analysis
4. Percentiles MUST be computed from non-warmup windows only
5. Percentiles MUST be computed per kernel per run (not aggregated across runs or kernels)
6. Percentiles MUST be reported in microseconds (µs) with at least 2 decimal places of precision

**Rationale:**

Mean latency is insufficient for real-time systems because:

- A system with mean latency 100µs but P99 = 500µs will violate deadline guarantees despite "good average" performance
- Tail latencies (P95, P99) directly determine worst-case schedulability and deadline miss rates
- Jitter and variability, not just central tendency, determine system reliability

Percentile-based reporting aligns with industry standards (SLA reporting, database performance analysis, network QoS) and reflects how real-time systems behave under stress.

**Example Output:**

```
Latency Percentiles (microseconds):
  P50 (Median):  127.43 µs
  P75:           134.82 µs
  P95:           156.21 µs
  P99:           198.47 µs
  P99.9:         287.15 µs
  Min:           115.21 µs
  Max:           412.67 µs
```

### 9.1.2 Jitter Quantification

Jitter quantifies latency **variability** and is a primary concern for deadline-driven systems. Unlike statistical jitter (standard deviation), CORTEX defines jitter as **percentile-based measures** that capture real-world tail behavior relevant to scheduling.

**Normative Requirements:**

1. Implementations MUST compute jitter as percentile differences:
   - **Jitter P95-P50**: `P95(latency_ns) - P50(latency_ns)` (percentile spread)
   - **Jitter P99-P50**: `P99(latency_ns) - P50(latency_ns)` (extreme tail spread)
2. Implementations MUST report jitter in microseconds (µs) with at least 2 decimal places
3. Implementations MUST compute jitter from the same latency dataset used for percentiles
4. Jitter MUST NOT be computed as standard deviation (σ) or coefficient of variation
5. Implementations SHOULD report both P95-P50 and P99-P50 jitter measures
6. Jitter MUST be computed per kernel per run

**Rationale:**

Standard deviation is inappropriate for real-time systems because:

- Standard deviation assumes normal distribution; latency distributions are often bimodal or heavy-tailed (e.g., preemption, DVFS changes)
- Standard deviation weights central values more heavily; real-time systems care about **extreme tails**
- P95-P50 jitter directly answers: "How much worse is worst-case (P95) than typical (P50)?" — the question schedulers ask

**Example Output:**

```
Jitter Quantification:
  Jitter P95-P50:  28.78 µs (14.2% relative to P50)
  Jitter P99-P50:  70.04 µs (34.9% relative to P50)
```

**Interpretation:**

- P95-P50 = 28.78 µs: The worst 5% of windows take 28.78 µs longer than typical
- P99-P50 = 70.04 µs: The worst 1% of windows take 70.04 µs longer than typical

### 9.1.3 Throughput

Throughput quantifies the number of windows successfully processed per unit time.

**Normative Requirements:**

1. Implementations MUST compute throughput as: `throughput_windows_per_s = valid_window_count / total_time_s`
2. `valid_window_count` MUST exclude warmup windows
3. `total_time_s` SHALL be computed as: `(release_ts_ns[last] - release_ts_ns[first]) / 1e9`
4. Throughput MUST be reported in windows per second (Hz)
5. Throughput MUST be reported per kernel per run
6. Implementations SHOULD additionally report throughput in samples per second: `throughput_samples_per_s = throughput_windows_per_s × H × Fs`

**Rationale:**

Throughput measures aggregate processing capacity independent of latency. A system might have low average latency but high jitter; throughput captures sustained processing rate under the actual load profile.

**Example Output:**

```
Throughput:
  Windows per second:  2.04 windows/s (H=80, Fs=160 Hz)
  Samples per second:  32,640 samples/s (theoretical max with 50% overlap)
```

**Normative Note:**

Throughput and latency are complementary metrics. Latency measures individual window performance; throughput measures aggregate sustained performance. Both MUST be reported for complete characterization.

---

## 9.2 Deadline Analysis

### 9.2.1 Deadline Miss Rate

Deadline misses are the primary failure mode for real-time systems. CORTEX MUST report deadline miss statistics to enable real-time feasibility analysis.

**Normative Requirements:**

1. Implementations MUST track the `deadline_missed` field from telemetry (§6 Telemetry Format)
2. Implementations MUST compute deadline miss rate as:
   ```
   deadline_miss_rate = (count of deadline_missed==1) / (total non-warmup windows) × 100%
   ```
3. Implementations MUST report deadline miss rate as a percentage with at least 1 decimal place
4. Deadline miss rate MUST be computed per kernel per run
5. Deadline miss rate MUST exclude warmup windows
6. Implementations MUST report absolute miss count (e.g., "5 misses out of 1200 windows") alongside percentage

**Rationale:**

Deadline miss rate is the fundamental reliability metric for deadline-driven systems:

- 0% miss rate: System is schedulable for the given load
- >0% miss rate: System violates deadlines and may miss real-time guarantees
- Miss rate trends indicate robustness: 1 miss per 10,000 windows indicates occasional preemption; 1% miss rate indicates systematic overload

**Example Output:**

```
Deadline Analysis:
  Deadline Miss Rate: 0.17% (2 misses out of 1200 windows)
  Status: PASS (< 1% threshold)
```

### 9.2.2 Miss Distribution

When deadline misses occur, understanding their distribution reveals root causes and helps distinguish between systematic overload and transient preemption.

**Normative Requirements:**

1. Implementations MUST compute the distribution of deadline miss durations:
   ```
   miss_duration_ns = end_ts_ns - deadline_ts_ns  (for windows where deadline_missed==1)
   ```
2. Implementations MUST report percentiles of miss duration: P50, P95, P99
3. Implementations MUST report miss duration in microseconds
4. Implementations MUST identify temporal clustering of misses:
   - **Clustered misses**: Multiple misses within a short window (e.g., <5 windows apart) indicating transient preemption
   - **Scattered misses**: Misses separated by many successful windows, indicating isolated events
5. Implementations SHOULD report the time since previous miss to identify clustering patterns
6. Implementations MUST flag if miss rate is non-zero and > 1% (systematic overload indicator)

**Rationale:**

Miss distribution answers important diagnostic questions:

- **Miss duration <= 10 µs**: Likely transient preemption or scheduler delay (acceptable for 500ms deadlines)
- **Miss duration >= 100 µs**: Indicates systematic underperformance or workload mismatch
- **Clustered misses**: Suggests preemption burst or DVFS transition; transient phenomenon
- **Scattered misses**: Suggests systematic underperformance or load sensitivity

**Example Output:**

```
Deadline Miss Statistics:
  Miss Count: 2 windows
  Miss Rate: 0.17%
  
  Miss Duration (when missed):
    P50: 12.4 µs (miss extent beyond deadline)
    P95: 23.1 µs
    P99: N/A (fewer than 100 misses)
  
  Temporal Pattern: CLUSTERED
    - Window 512-513: 2 consecutive misses (transient preemption)
    - 687 successful windows between last miss and run end
    - Interpretation: Isolated preemption event, not systematic overload
```

### 9.2.3 Worst-Case Latency

Worst-case latency (maximum observed latency) provides practical upper bounds for real-time scheduling but must be interpreted cautiously.

**Normative Requirements:**

1. Implementations MUST report maximum observed latency across all non-warmup windows
2. Implementations MUST report the window index where maximum latency occurred
3. Implementations MUST report maximum latency in microseconds
4. Implementations SHOULD report whether the maximum latency window resulted in a deadline miss
5. Implementations SHOULD report context information: system load (if available), preemption indicators, DVFS state (if available)
6. Implementations MUST document that maximum latency is an **observed data point**, not a strict upper bound (future runs may exceed it)

**Rationale:**

Maximum latency is useful for:
- Identifying extreme outliers (e.g., >10× median) that might indicate OS interference
- Validating measurement validity (outliers >5× P99 often indicate preemption or measurement artifacts)
- Setting conservative scheduling margins

However, maximum latency is NOT a reliable upper bound because:
- Future runs may exceed the observed maximum due to OS scheduling variability
- Single-run statistics are insufficient for hard real-time guarantees (require multiple runs with statistical confidence intervals)

**Example Output:**

```
Worst-Case Latency:
  Maximum Observed: 287.15 µs (window 847)
  Deadline Missed: NO (deadline = 500 µs)
  Percentile Rank: P99.9 (99.9th percentile)
  Relative to P95: 1.84× P95 latency
  Likely Cause: OS preemption (system load spike at t=423.5s)
```

---

## 9.3 Mandatory Disclosure

### 9.3.1 Platform and System Information

Benchmark results are only meaningful in context. CORTEX implementations MUST disclose comprehensive platform information to enable reproducibility and cross-platform comparison.

**Normative Requirements:**

1. Implementations MUST report all of the following system information:

   **Hardware Platform:**
   - CPU model (e.g., "Apple M1", "Intel Core i9-12900K")
   - CPU architecture (e.g., "arm64", "x86_64")
   - Physical core count and logical core count (if different)
   - CPU nominal frequency (GHz) and frequency scaling range (if applicable)
   - Total system RAM (GB)
   - Cache hierarchy (L1d, L1i, L2, L3 sizes if available)

   **Operating System:**
   - OS name and version (e.g., "Linux 5.15.148-tegra", "Darwin 23.2.0", "Windows 11 22H2")
   - Kernel build date (if available)
   - Real-time kernel patches (if applicable, e.g., PREEMPT_RT for Linux)

   **System State:**
   - CPU governor or power state (if applicable, e.g., "performance", "powersave", "schedutil")
   - CPU frequency at time of measurement (if pinned or overclocked)
   - Thermal state (CPU temperature, if available)
   - Thermal throttling status (enabled/disabled, if known)
   - System uptime at benchmark start

2. Implementations MUST include this information in all output formats:
   - **NDJSON**: As a system metadata record with `"_type": "system_info"` (see §6.4.1)
   - **CSV**: As comment lines prefixed with `#` before the header row (see §6.4.2)
   - **Report**: As a "Platform Information" section or table

3. Implementations SHOULD report hostname and device identifier for reproducibility

**Rationale:**

Platform information is essential because:

- **Frequency scaling**: CPU frequency can vary 2–4× between idle and performance modes; results are only valid for the measured frequency
- **OS kernel version**: Performance varies significantly between kernel releases (scheduler changes, cache behavior, syscall overhead)
- **Real-time patches**: PREEMPT_RT or other RT patches dramatically reduce latency jitter
- **Architecture**: ARM and x86 have different cache hierarchies, instruction costs, and branch predictor behavior

Without platform context, reported latencies are meaningless.

**Example Output:**

```
# System Information
# Platform: Darwin 23.2.0 (macOS Sonoma)
# CPU: Apple M1 (arm64, 8 cores, 3.2 GHz nominal)
# RAM: 8192 MB
# Cache: L1d 64KB, L1i 128KB, L2 4MB (per core), GPU shared
# CPU Governor: N/A (Apple PowerMetrics, cluster-wide frequency scaling)
# Current Frequency: 3.2 GHz (estimated from task rates)
# System Uptime: 12345 seconds (3.4 hours)
# Thermal: 46°C (nominal, not throttling)
# Hostname: Westons-MacBook-Air-2.local
```

### 9.3.2 Benchmark Configuration

Configuration parameters determine which kernel and load profile was tested. CORTEX MUST mandate full disclosure of configuration.

**Normative Requirements:**

1. Implementations MUST report the following configuration parameters:

   **Kernel Configuration:**
   - Kernel name (plugin identifier, e.g., `bandpass_fir`)
   - Kernel version or commit hash (if applicable)
   - Kernel implementation language (C, CUDA, etc.)

   **Window Configuration:**
   - Window length (W) in samples
   - Hop length (H) in samples
   - Input channel count (C)
   - Sample rate (Fs) in Hz
   - Computed deadline = `(H / Fs) × 1e9` nanoseconds
   - Overlap percentage = `((W - H) / W) × 100%`

   **Dataset Configuration:**
   - Input dataset name or identifier
   - Dataset size (number of windows tested)
   - Data type (float32, float64, int16, etc.)

   **Load Profile Configuration:**
   - Background load (idle, light, medium, heavy, custom stress parameters)
   - CPU affinity (which cores reserved for kernel, which for background load)
   - Real-time priority (if applicable)
   - Thread count and thread model

2. Implementations MUST include configuration in output:
   - NDJSON: As fields in each telemetry record (W, H, C, Fs, plugin_name already required in §6)
   - CSV: In metadata comment section
   - Report: As a "Configuration" section

3. Implementations MUST ensure configuration is human-readable and unambiguous

**Rationale:**

Configuration disclosure enables:

- **Reproducibility**: Other researchers can run the exact same test
- **Generalization**: Understanding which parameters affect latency (e.g., C=64 vs C=1)
- **Fairness**: Comparing kernels under identical load conditions
- **Root cause analysis**: Identifying why performance differs between runs

**Example Output:**

```
# Benchmark Configuration
# Kernel: bandpass_fir
# Window Length (W): 160 samples
# Hop Length (H): 80 samples (50% overlap)
# Channels (C): 64
# Sample Rate (Fs): 160 Hz
# Deadline: 500 ms (500,000,000 ns)
# Dataset: EEG Motor Movement/Imagery (S001R03, 10 minutes)
# Load Profile: medium (4 cores @ 50% via stress-ng)
# CPU Affinity: Kernel on E-core, load on P-core
# Real-time Priority: SCHED_FIFO, priority 90
```

### 9.3.3 Sample Size and Statistical Confidence

Statistical significance depends critically on sample size. CORTEX MUST mandate reporting of sample sizes and confidence intervals.

**Normative Requirements:**

1. Implementations MUST report:
   - **Total windows tested** (N, excluding warmup)
   - **Warmup duration** (in seconds and window count)
   - **Repeat count** (number of independent benchmark runs)
   - **Total measurement time** (in seconds, from first window release to last window completion)

2. For multi-trial runs (repeat > 1), implementations MUST compute **per-trial statistics** and then **aggregate statistics across trials**:
   - Per-trial P50, P95, P99 latencies
   - Mean of per-trial medians (with 95% confidence interval)
   - Mean of per-trial P95 latencies (with 95% confidence interval)
   - Statistical test results (e.g., t-test for load profile differences)

3. Implementations MUST report confidence intervals using standard Student's t-distribution:
   ```
   mean ± t(α/2, n-1) × (σ / √n)
   ```
   where α=0.05 (95% confidence), n=repeat count

4. Implementations SHOULD report degrees of freedom (n-1) alongside confidence intervals

5. Implementations SHOULD report whether results are statistically significant using standard hypothesis testing (p-value < 0.05 indicates significance)

**Rationale:**

Sample size context answers critical questions:

- **N=100 vs N=10,000**: Both might report identical P95, but N=100 has much wider confidence intervals
- **Repeat=1 vs Repeat=5**: Single-trial results are unreliable; multi-trial results enable statistical significance testing
- **Confidence intervals**: Readers can assess measurement precision and decide if differences between conditions are meaningful

Single-trial results can be misleading: Two runs of the same kernel might show 20% performance variation due to OS scheduling, DVFS, or thermal conditions.

**Example Output:**

```
Sample Size and Statistical Confidence:
  Total Windows: 1200 (non-warmup)
  Warmup: 10 seconds (20 windows discarded)
  Total Run Time: 600 seconds
  Repeat Count: 5 independent trials
  
  Per-Trial Median Latencies: 127.1, 128.3, 126.8, 129.2, 127.5 µs
  Median across trials: 127.8 µs
  95% Confidence Interval: 127.2 ± 1.4 µs
  Degrees of Freedom: 4
  
  Per-Trial P95 Latencies: 156.2, 157.8, 155.4, 159.1, 156.7 µs
  P95 across trials: 157.0 µs
  95% Confidence Interval: 157.0 ± 1.8 µs
  
  Statistical Significance Test (Idle vs Medium):
    t-statistic: 4.23
    p-value: 0.002 (SIGNIFICANT)
    Effect size (Cohen's d): 0.84 (large effect)
```

### 9.3.4 Warmup Procedure

Warmup is essential for eliminating cold-cache artifacts. CORTEX MUST mandate explicit warmup disclosure.

**Normative Requirements:**

1. Implementations MUST perform a warmup phase before collecting statistics:
   - Duration: At least 5 seconds (RECOMMENDED minimum)
   - For high-frequency kernels (>100 Hz window rate): At least 100 windows
   - For low-frequency kernels (<10 Hz window rate): At least 10 seconds

2. Implementations MUST track warmup windows separately in telemetry:
   - Set `warmup=1` for warmup windows
   - Set `warmup=0` for measured windows

3. Implementations MUST discard warmup windows from all statistical computations:
   - Percentiles, mean, jitter: Exclude `warmup=1` windows
   - Deadline miss rate: Exclude `warmup=1` windows
   - Throughput: Exclude `warmup=1` windows

4. Implementations MUST report warmup duration and window count in output

5. Implementations SHOULD document warmup rationale (e.g., "10 seconds to stabilize CPU frequency and populate caches")

**Rationale:**

Warmup is necessary because:

- **Cold caches**: First 10–100 windows have higher latency due to cache misses
- **Frequency scaling**: CPU frequency may ramp from idle frequency during startup, affecting first windows disproportionately
- **DVFS transitions**: Kernel initialization may trigger frequency scaling decisions that persist for several windows

Without warmup exclusion, reported medians and P95 are inflated 10–50% depending on dataset size.

**Example Output:**

```
Warmup Procedure:
  Duration: 10 seconds
  Window Count: 20 windows (at H=80, Fs=160 Hz)
  Rationale: Stabilize CPU frequency (DVFS) and populate L1/L2 caches
  
  Latency Impact of Warmup:
    Warmup windows (avg): 214.3 µs
    Post-warmup windows (avg): 127.8 µs
    Inflation Factor: 1.68× (67.6% higher with cold cache)
  
  Statistical Impact on P95:
    If warmup included: P95 = 184.2 µs
    After warmup exclusion: P95 = 156.1 µs
    Adjustment: 17.9% reduction in tail latency
```

---

## 9.4 Mandatory Report Format

All of the above statistics MUST be aggregated into a structured report. CORTEX implementations MUST support both machine-readable and human-readable output.

### 9.4.1 Report Schema

Implementations MUST generate a report with the following sections:

**1. Metadata Block:**
- Run ID, timestamp, duration
- Kernel name, version
- Platform information (§9.3.1)
- Benchmark configuration (§9.3.2)

**2. Sample Size Block:**
- Window count, warmup parameters
- Repeat count, per-trial statistics
- Confidence intervals (§9.3.3)

**3. Latency Distribution Block (§9.1):**
- Percentiles: P50, P75, P95, P99, P99.9
- Min, Max
- Jitter: P95-P50, P99-P50

**4. Throughput Block (§9.1.3):**
- Windows per second
- Samples per second

**5. Deadline Analysis Block (§9.2):**
- Deadline miss rate and count
- Miss duration distribution (if misses > 0)
- Temporal clustering analysis (if misses > 0)
- Worst-case latency

### 9.4.2 Report Formats

Implementations MUST support at least one report format:

**Option A: JSON Report (RECOMMENDED for programmatic analysis)**
```json
{
  "metadata": {
    "run_id": "1762310612183",
    "timestamp": "2026-01-15T11:37:00Z",
    "kernel": "bandpass_fir",
    "platform": {...}
  },
  "statistics": {
    "latency_percentiles_us": {
      "p50": 127.43,
      "p75": 134.82,
      "p95": 156.21,
      "p99": 198.47,
      "min": 115.21,
      "max": 287.15
    },
    "jitter_us": {
      "p95_minus_p50": 28.78,
      "p99_minus_p50": 70.04
    },
    "deadline": {
      "miss_rate_percent": 0.17,
      "miss_count": 2,
      "total_windows": 1200
    }
  }
}
```

**Option B: Markdown Report (RECOMMENDED for human reading)**
```markdown
# Benchmark Report: bandpass_fir
Run ID: 1762310612183
Timestamp: 2026-01-15T11:37:00Z

## Platform Information
- CPU: Apple M1 (arm64)
- OS: Darwin 23.2.0
- ...

## Latency Statistics (Percentiles)
- P50: 127.43 µs
- P95: 156.21 µs
- P99: 198.47 µs
...
```

**Option C: HTML Report (RECOMMENDED for visualization)**
- Includes plots: latency distribution histogram, percentile curves, deadline miss timeline
- Interactive tables with sortable columns
- System metadata embedded in page

### 9.4.3 Conformance Checklist

Implementations claiming CORTEX v1.0 conformance MUST include the following in all reports:

- [ ] Platform information: CPU model, OS version, frequency state
- [ ] Configuration: W, H, C, Fs, kernel name, dataset
- [ ] Sample size: Total windows, warmup duration, repeat count
- [ ] Latency distribution: P50, P95, P99 (minimum)
- [ ] Jitter: P95-P50 and/or P99-P50
- [ ] Deadline miss rate (if applicable)
- [ ] Warmup disclosure: Duration, windows discarded

---

## 9.5 Rationale Summary

This section concludes with key design rationales:

**Why percentiles instead of mean?**

Mean latency is sufficient for batch processing (high-throughput databases, mapreduce) but fails for deadline-driven systems. Real-time viability depends on tail latencies (P95, P99), not central tendency.

**Why jitter as percentile differences instead of standard deviation?**

Standard deviation assumes normal distribution; real-time latencies are often bimodal (fast/slow execution paths) or heavy-tailed (OS preemption). Percentile-based jitter directly measures "worst case relative to typical," which is what schedulers care about.

**Why mandatory platform disclosure?**

Results are meaningless without context. CPU frequency, OS kernel version, and real-time patches affect latency by 2–10×. Comparing results without this context is unscientific.

**Why multi-trial statistics with confidence intervals?**

Single-trial results are unreliable due to OS scheduling variability (±20% common). Multi-trial means with confidence intervals enable valid cross-platform comparison and hypothesis testing.

**Why separate latency distribution, throughput, and deadline miss rate?**

These metrics answer different questions:
- Latency distribution: Is performance acceptable? (individual window quality)
- Throughput: Can the system keep up? (aggregate processing rate)
- Deadline miss rate: Does the system meet hard deadlines? (reliability)

All three are required for complete characterization.

---

**End of Section 9: Statistical Reporting**
