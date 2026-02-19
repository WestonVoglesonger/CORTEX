# 6. Telemetry Format

## 6.1 Overview

This section defines the telemetry record schema, timestamp semantics, and output format specifications for CORTEX v1.0. Telemetry records capture per-window execution metrics, enabling latency analysis, deadline tracking, and performance profiling of BCI signal processing kernels.

The telemetry subsystem provides:
- High-resolution timing measurements (nanosecond precision)
- Deadline miss detection
- Device-side timing instrumentation for remote execution
- Structured output in NDJSON and CSV formats
- System metadata for reproducibility

**Conformance Levels:**

A **basic conformant implementation** MUST support:
- Core timing fields (release, deadline, start, end timestamps)
- Deadline miss tracking
- NDJSON output format

A **fully conformant implementation** MUST additionally support:
- Device timing fields for remote execution
- Error tracking (window failure and error codes)
- CSV output format
- System metadata recording

**Implementation Status:**

This specification documents both implemented and planned features. Energy and memory measurement fields are defined in the schema (§6.1.2) but are NOT REQUIRED in v1.0 implementations. Implementations MAY return zero or omit these fields until full instrumentation is available (planned v1.1, Spring 2026).

---

## 6.2 Record Schema

### 6.2.1 Core Telemetry Record

A conformant telemetry record MUST contain the following fields:

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| `run_id` | string | REQUIRED | Unique run identifier (millisecond timestamp) |
| `plugin_name` | string | REQUIRED | Kernel name (e.g., `bandpass_fir`, `car`) |
| `window_index` | uint32 | REQUIRED | Window sequence number (0-indexed) |
| `release_ts_ns` | uint64 | REQUIRED | Window release time (nanoseconds, monotonic clock) |
| `deadline_ts_ns` | uint64 | REQUIRED | Deadline timestamp (release + H/Fs, nanoseconds) |
| `start_ts_ns` | uint64 | REQUIRED | Actual execution start time (nanoseconds, monotonic clock) |
| `end_ts_ns` | uint64 | REQUIRED | Actual execution end time (nanoseconds, monotonic clock) |
| `deadline_missed` | uint8 | REQUIRED | 1 if end > deadline, 0 otherwise |
| `W` | uint32 | REQUIRED | Window length (samples) |
| `H` | uint32 | REQUIRED | Hop length (samples) |
| `C` | uint32 | REQUIRED | Input channel count |
| `Fs` | uint32 | REQUIRED | Sample rate (Hz) |
| `warmup` | uint8 | REQUIRED | 1 if warmup window (excluded from statistics), 0 otherwise |
| `repeat` | uint32 | REQUIRED | Repeat iteration number (1-indexed) |

**Rationale:**

The core schema captures the minimum information needed to compute latency distributions, deadline miss rates, and throughput. The `window_index` provides temporal ordering, while `warmup` enables statistical exclusion of cache-cold executions. The `repeat` field supports multi-trial averaging for statistical robustness.

**Normative Requirements:**

1. Implementations MUST populate all REQUIRED fields for every window.
2. Timestamp fields MUST use nanosecond precision (uint64).
3. The `run_id` MUST be unique across runs on the same system.
4. The `window_index` MUST increment sequentially starting from 0.

### 6.2.2 Device Timing Fields

For implementations supporting remote execution via device adapters, the following fields SHOULD be populated:

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| `device_tin_ns` | uint64 | SHOULD | Time adapter received window data (device clock) |
| `device_tstart_ns` | uint64 | SHOULD | Time kernel execution started (device clock) |
| `device_tend_ns` | uint64 | SHOULD | Time kernel execution finished (device clock) |
| `device_tfirst_tx_ns` | uint64 | SHOULD | Time first output byte transmitted (device clock) |
| `device_tlast_tx_ns` | uint64 | SHOULD | Time last output byte transmitted (device clock) |
| `adapter_name` | string | SHOULD | Adapter identifier (e.g., `native`, `jetson@tcp`) |

**Rationale:**

Device timing fields enable decomposition of end-to-end latency into:
- **Adapter overhead:** Time spent marshaling data and managing transport
- **Network latency:** Time spent in serialization and transmission
- **Kernel execution time:** Pure computational latency on the device

For local execution (native adapter), device timestamps approximate harness timestamps within socketpair overhead (~microseconds). For remote execution (TCP, UART), device timing reveals transport bottlenecks.

**Normative Requirements:**

1. Implementations using the `native` adapter SHOULD populate device timing fields.
2. Implementations using remote adapters (TCP, UART) MUST populate device timing fields.
3. Device timestamps MUST use the device's monotonic clock (not synchronized with harness clock).
4. The `adapter_name` field MUST match the adapter identifier in the configuration.

**Clock Synchronization:**

Device clocks and harness clocks are NOT synchronized. Device timing fields are measured relative to an arbitrary device monotonic reference. Interval durations (e.g., `device_tend_ns - device_tstart_ns`) are valid; absolute comparisons between device and harness timestamps are NOT valid.

### 6.2.3 Error Tracking Fields

For implementations supporting error detection and recovery, the following fields SHOULD be populated:

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| `window_failed` | uint8 | SHOULD | 1 if transport/adapter failure occurred, 0 otherwise |
| `error_code` | int32 | SHOULD | Error reason code (implementation-defined) |

**Rationale:**

Error tracking distinguishes transport failures (network timeout, serialization error) from deadline misses (computation too slow). This enables root cause analysis of benchmark anomalies.

**Normative Requirements:**

1. Implementations MUST set `window_failed = 1` if the window could not be processed due to adapter or transport failure.
2. Implementations MUST set `window_failed = 0` for successful windows, even if the deadline was missed.
3. The `error_code` field SHOULD use a documented error taxonomy (e.g., POSIX errno codes or adapter-specific error enumeration).

### 6.2.4 Planned Fields (Not Required in v1.0)

The following fields are defined in the schema but are NOT REQUIRED in v1.0 implementations. Implementations MAY omit these fields or return zero values.

| Field | Type | Planned Version | Description |
|-------|------|-----------------|-------------|
| `energy_j` | float | v1.1 (Spring 2026) | Energy consumption during kernel execution (joules) |
| `power_mw` | float | v1.1 (Spring 2026) | Average power consumption (milliwatts) |
| `rss_bytes` | uint64 | v1.1 (Spring 2026) | Resident set size at window completion (bytes) |
| `state_bytes` | uint64 | v1.1 (Spring 2026) | Kernel state memory allocation (bytes, runtime measurement) |
| `workspace_bytes` | uint64 | v1.1 (Spring 2026) | Kernel workspace memory allocation (bytes, runtime measurement) |

**Implementation Notes:**

- **Energy measurement:** Requires RAPL (Running Average Power Limit) instrumentation on Linux x86_64 platforms. Planned for v1.1.
- **Memory measurement:** Requires runtime RSS tracking and heap instrumentation. Current implementations report static metadata from `cortex_get_info()`, not actual allocations.

**Normative Requirements:**

1. Implementations claiming full telemetry conformance MUST provide energy and memory fields in v1.1+.
2. Implementations MAY omit unimplemented fields from output (NDJSON: omit key, CSV: empty cell).
3. Implementations MUST NOT emit misleading values (e.g., random data) for unimplemented fields. Zero or null MUST indicate unavailability.

---

## 6.3 Timestamp Semantics

### 6.3.1 Clock Source

Timestamp fields MUST use a monotonic clock source:

- **Linux:** `CLOCK_MONOTONIC` (nanosecond resolution, immune to NTP adjustments)
- **macOS:** `clock_gettime(CLOCK_MONOTONIC, ...)` (microsecond quantization on some systems)
- **Other POSIX platforms:** POSIX monotonic clock (`CLOCK_MONOTONIC` or equivalent)

**Rationale:**

Wall clock timestamps (`CLOCK_REALTIME`) are unsuitable for interval measurement because they are subject to:
- NTP adjustments (forward/backward jumps)
- Leap second corrections
- Manual time changes

Monotonic clocks provide strictly increasing timestamps, ensuring valid interval calculations.

**Normative Requirements:**

1. Implementations MUST use a monotonic clock for all timestamp fields.
2. Implementations MUST NOT use wall clock time for latency measurement.
3. Implementations SHOULD document the clock source and resolution in system metadata.

### 6.3.2 Timestamp Precision

All timestamp fields MUST use **nanosecond precision** (uint64, nanoseconds since an arbitrary monotonic reference).

**Rationale:**

BCI kernels execute in the 10µs–1ms range. Microsecond precision (1000ns quantization) provides only 10–100 samples per kernel execution, insufficient for percentile analysis. Nanosecond precision matches the resolution of modern timing APIs (`CLOCK_MONOTONIC`, `clock_gettime`).

**Normative Requirements:**

1. Timestamp fields MUST store values in nanoseconds (not milliseconds or microseconds).
2. Implementations MAY experience quantization depending on platform clock resolution (e.g., macOS quantizes to 1µs increments).
3. Implementations MUST NOT artificially inflate precision (e.g., multiplying microsecond timestamps by 1000 does not create nanosecond precision).

### 6.3.3 Timestamp Zero Point

The monotonic clock zero point is **arbitrary and platform-dependent**. Timestamps represent nanoseconds since an unspecified reference (e.g., system boot, arbitrary epoch).

**Normative Requirements:**

1. Implementations MUST NOT assume timestamps represent wall clock time.
2. Implementations MUST NOT compare absolute timestamps across runs or systems.
3. Interval durations (e.g., `end_ts_ns - start_ts_ns`) are valid; absolute timestamp values have no universal interpretation.

### 6.3.4 Deadline Calculation

The deadline timestamp SHALL be computed as:

```
deadline_ts_ns = release_ts_ns + (hop_samples / sample_rate_hz) × 1,000,000,000
```

Where:
- `hop_samples` (H): Hop length in samples
- `sample_rate_hz` (Fs): Sample rate in Hz
- Result: Deadline in nanoseconds (same clock domain as `release_ts_ns`)

**Example:**

Given:
- Hop (H) = 80 samples
- Sample rate (Fs) = 160 Hz
- Release time = 1,000,000,000 ns

Computation:
```
deadline_delta_s = 80 / 160 = 0.5 seconds
deadline_delta_ns = 0.5 × 1,000,000,000 = 500,000,000 ns
deadline_ts_ns = 1,000,000,000 + 500,000,000 = 1,500,000,000 ns
```

The deadline is 500ms after release (the next window arrives every H/Fs seconds).

**Rationale:**

In overlapping windowed processing, windows arrive every **hop** samples (H), not window samples (W). For a sample rate Fs, a new window arrives every H/Fs seconds. Processing must complete before the next window arrival, establishing the deadline.

**Why deadline uses hop, not window:**

For 50% overlapping windows (W=160, H=80, Fs=160 Hz):
- Window 0 arrives at t=0.0s (samples 0–159)
- Window 1 arrives at t=0.5s (samples 80–239, overlaps 80 samples with window 0)
- Window 2 arrives at t=1.0s (samples 160–319, overlaps 80 samples with window 1)

If window 0 processing finishes at t=0.6s, it has **missed the deadline** (window 1 already arrived at t=0.5s). The hop determines the inter-arrival interval, not the window length.

**Normative Requirements:**

1. Implementations MUST compute deadlines using the hop length (H), not window length (W).
2. Implementations MUST use floating-point division to avoid integer truncation: `(H / Fs)` computed as `(double)H / (double)Fs`.
3. Implementations MUST convert the deadline delta to nanoseconds (multiply by 10^9) before adding to the release timestamp.

### 6.3.5 Deadline Miss Detection

A deadline miss occurs when the execution end time exceeds the deadline:

```
deadline_missed = (end_ts_ns > deadline_ts_ns) ? 1 : 0
```

**Normative Requirements:**

1. Implementations MUST set `deadline_missed = 1` if `end_ts_ns > deadline_ts_ns`.
2. Implementations MUST set `deadline_missed = 0` otherwise.
3. Implementations MUST compare nanosecond timestamps directly (not converted to other units).

---

## 6.4 Output Formats

### 6.4.1 NDJSON Format (Default)

NDJSON (Newline-Delimited JSON) is the **default output format** for telemetry records.

**Specification:** https://github.com/ndjson/ndjson-spec

**Format Characteristics:**

1. Each line contains ONE complete JSON object (no outer array brackets).
2. Lines are separated by newline characters (`\n`, ASCII 0x0A).
3. Each object is a complete, self-describing telemetry record.
4. Files use the `.ndjson` extension.
5. Encoding is UTF-8.

**Example:**

```json
{"run_id":"1762310612183","plugin":"goertzel","window_index":0,"release_ts_ns":21194971498000,"deadline_ts_ns":21195471498000,"start_ts_ns":21194971498000,"end_ts_ns":21194971740000,"deadline_missed":0,"W":160,"H":80,"C":64,"Fs":160,"warmup":0,"repeat":1,"device_tin_ns":429226466336,"device_tstart_ns":429226466496,"device_tend_ns":429226817216,"device_tfirst_tx_ns":429226817312,"device_tlast_tx_ns":429226817312,"adapter_name":"native","window_failed":0,"error_code":0}
{"run_id":"1762310612183","plugin":"goertzel","window_index":1,"release_ts_ns":21195476495000,"deadline_ts_ns":21195976495000,"start_ts_ns":21195476495000,"end_ts_ns":21195476742000,"deadline_missed":0,"W":160,"H":80,"C":64,"Fs":160,"warmup":0,"repeat":1,"device_tin_ns":429226817500,"device_tstart_ns":429226817650,"device_tend_ns":429227168400,"device_tfirst_tx_ns":429227168500,"device_tlast_tx_ns":429227168500,"adapter_name":"native","window_failed":0,"error_code":0}
```

**Rationale:**

NDJSON provides significant advantages over JSON arrays or CSV for telemetry:

1. **Streaming:** Append-only writes without re-parsing the entire file. New records are appended as they arrive.
2. **Line-oriented processing:** Compatible with Unix tools (`grep`, `tail -f`, `awk`, `jq`). Each record is a complete line.
3. **Partial reads:** Incomplete runs (e.g., benchmark crashed mid-execution) are still parseable. No closing bracket required.
4. **Self-describing:** Schema is embedded in every record (field names present). No separate header required.
5. **Standard format:** Widely supported in log aggregation systems (Elasticsearch, Splunk, etc.).

**Normative Requirements:**

1. Implementations MUST support NDJSON output.
2. Each JSON object MUST occupy exactly one line (no embedded newlines in values).
3. Each line MUST contain a complete, valid JSON object.
4. Implementations MUST use UTF-8 encoding.
5. Implementations MUST use the `.ndjson` file extension.

**System Metadata:**

The first line of an NDJSON file SHOULD contain a system metadata record with `"_type": "system_info"`:

```json
{"_type":"system_info","os":"Darwin 23.2.0","cpu":"Apple M1","hostname":"Westons-MacBook-Air-2.local","cpu_count":8,"total_ram_mb":8192,"thermal_celsius":null,"device_hostname":"weston-desktop","device_cpu":"ARMv8 Processor rev 1 (v8l)","device_os":"Linux 5.15.148-tegra"}
```

**Normative Requirements:**

1. Implementations SHOULD emit a system metadata record as the first line.
2. The system metadata record MUST include the field `"_type": "system_info"` to distinguish it from telemetry records.
3. Parsing tools SHOULD skip records with `"_type"` ≠ null.

### 6.4.2 CSV Format (Alternative)

CSV (Comma-Separated Values) provides spreadsheet-compatible output for telemetry records.

**Format Characteristics:**

1. First line contains column names (header row).
2. Subsequent lines contain data rows (one record per line).
3. Delimiter is comma (`,`, ASCII 0x2C).
4. Files use the `.csv` extension.
5. Encoding is UTF-8.

**Example:**

```csv
run_id,plugin,window_index,release_ts_ns,deadline_ts_ns,start_ts_ns,end_ts_ns,deadline_missed,W,H,C,Fs,warmup,repeat,device_tin_ns,device_tstart_ns,device_tend_ns,device_tfirst_tx_ns,device_tlast_tx_ns,adapter_name,window_failed,error_code
1762310612183,goertzel,0,21194971498000,21195471498000,21194971498000,21194971740000,0,160,80,64,160,0,1,429226466336,429226466496,429226817216,429226817312,429226817312,native,0,0
1762310612183,goertzel,1,21195476495000,21195976495000,21195476495000,21195476742000,0,160,80,64,160,0,1,429226817500,429226817650,429227168400,429227168500,429227168500,native,0,0
```

**Normative Requirements:**

1. Implementations SHOULD support CSV output (REQUIRED for full conformance).
2. The first line MUST contain column names matching the field names in §6.2.
3. Implementations MUST use comma (`,`) as the delimiter.
4. Implementations MUST use UTF-8 encoding.
5. Implementations MUST use the `.csv` file extension.

**System Metadata:**

System metadata SHOULD be included as comment lines (lines beginning with `#`) before the header row:

```csv
# System Information
# OS: Darwin 23.2.0
# CPU: Apple M1
# Hostname: Westons-MacBook-Air-2.local
# CPU Cores: 8
# Total RAM: 8192 MB
# Thermal: unavailable
#
run_id,plugin,window_index,...
```

**Normative Requirements:**

1. Implementations SHOULD emit system metadata as comment lines (lines prefixed with `#`).
2. Comment lines MUST appear before the header row.
3. Parsing tools SHOULD ignore lines beginning with `#`.

### 6.4.3 Format Selection

The output format is determined by the `output.format` configuration setting.

**Configuration Example (YAML):**

```yaml
output:
  format: "ndjson"  # or "csv"
```

**Normative Requirements:**

1. Implementations MUST support `output.format = "ndjson"` (default).
2. Implementations SHOULD support `output.format = "csv"` (REQUIRED for full conformance).
3. If `output.format` is unspecified, implementations MUST default to NDJSON.

### 6.4.4 Field Ordering

**NDJSON:** Field order within JSON objects is NOT significant. Parsers MUST NOT assume a specific field order.

**CSV:** Column order MUST match the order specified in §6.2. Implementations MAY omit columns for unimplemented fields, but MUST document the omission.

---

## 6.5 Derived Metrics

Implementations MAY compute derived metrics from raw telemetry fields. Derived metrics are NOT part of the telemetry record schema but are commonly reported in analysis summaries.

### 6.5.1 Latency

Latency is the duration from execution start to execution end:

```
latency_ns = end_ts_ns - start_ts_ns
```

**Normative Requirements:**

1. Implementations SHOULD report latency in microseconds (µs) or nanoseconds (ns) in analysis summaries.
2. Latency MUST be computed from `start_ts_ns` and `end_ts_ns` (not device timing fields unless explicitly stated).

### 6.5.2 Jitter

Jitter quantifies latency variability. Common jitter metrics include:

- **P95-P50 jitter:** Difference between 95th percentile and median latency (captures tail latency variability)
- **P99-P50 jitter:** Difference between 99th percentile and median latency (captures extreme tail variability)

```
jitter_p95_minus_p50 = P95(latency_ns) - P50(latency_ns)
jitter_p99_minus_p50 = P99(latency_ns) - P50(latency_ns)
```

**Normative Requirements:**

1. Implementations SHOULD compute jitter as percentile differences (not standard deviation).
2. Jitter MUST be computed per kernel per run (not per window).

### 6.5.3 Throughput

Throughput is the number of windows processed per second:

```
throughput_windows_per_s = window_count / total_time_s
```

Where `total_time_s` is the elapsed time from the first window release to the last window completion.

**Normative Requirements:**

1. Implementations SHOULD report throughput in windows per second (Hz).
2. Throughput MUST exclude warmup windows from the count.

### 6.5.4 Deadline Miss Rate

Deadline miss rate is the fraction of windows that missed their deadlines:

```
deadline_miss_rate = (count of deadline_missed=1) / (total windows)
```

**Normative Requirements:**

1. Implementations SHOULD report deadline miss rate as a percentage (0–100%).
2. Deadline miss rate MUST exclude warmup windows from the count.

---

## 6.6 File Locations

Telemetry files SHOULD be written to the following locations:

```
results/<run-name>/kernel-data/<kernel>/telemetry.ndjson   # Per-kernel NDJSON telemetry
results/<run-name>/kernel-data/<kernel>/telemetry.csv      # Per-kernel CSV telemetry (if enabled)
results/<run-name>/telemetry.ndjson                        # Aggregated NDJSON telemetry (all kernels)
```

**Normative Requirements:**

1. Implementations MUST create the directory structure if it does not exist.
2. Implementations MUST write per-kernel telemetry files for each kernel in the benchmark.
3. Implementations MAY write aggregated telemetry files combining all kernels.

---

## 6.7 Conformance

### 6.7.1 Basic Conformance

A **basic conformant implementation** MUST:

1. Populate all REQUIRED fields from §6.2.1.
2. Use a monotonic clock source (§6.3.1).
3. Use nanosecond precision for timestamps (§6.3.2).
4. Compute deadlines correctly using hop length (§6.3.4).
5. Support NDJSON output format (§6.4.1).

### 6.7.2 Full Conformance

A **fully conformant implementation** MUST additionally:

1. Populate device timing fields when using remote adapters (§6.2.2).
2. Populate error tracking fields (§6.2.3).
3. Support CSV output format (§6.4.2).
4. Emit system metadata (§6.4.1, §6.4.2).

### 6.7.3 Extended Conformance (v1.1+)

An **extended conformant implementation** MUST additionally:

1. Populate energy measurement fields (§6.2.4).
2. Populate runtime memory measurement fields (§6.2.4).

---

## 6.8 Rationale Summary

This section concludes with a summary of key design decisions:

**Why NDJSON as the default format?**

NDJSON provides streaming append-only writes, line-oriented processing (Unix tools), partial read support (crashed runs), and self-describing schema. CSV is provided for spreadsheet compatibility, but NDJSON is superior for programmatic analysis and log aggregation.

**Why nanosecond precision?**

BCI kernels execute in 10µs–1ms. Microsecond precision (1000ns quantization) provides only 10–100 samples per execution, insufficient for percentile analysis. Nanosecond precision matches modern timing API resolution.

**Why CLOCK_MONOTONIC (not wall clock)?**

Wall clocks are subject to NTP adjustments, leap seconds, and manual changes, causing backwards jumps. Monotonic clocks are strictly increasing and immune to external time changes, ensuring valid interval measurements.

**Why deadline = release + H/Fs (not release + W/Fs)?**

In overlapping windowed processing, windows arrive every **hop** samples (H), not window samples (W). The deadline is the next window's arrival time, determined by the hop interval H/Fs.

**Why separate device timing fields?**

Device timing enables decomposition of end-to-end latency into adapter overhead, network latency, and kernel execution time. For remote execution (Jetson via TCP, STM32 via UART), this is critical for identifying transport bottlenecks.

---

**End of Section 6: Telemetry Format**
