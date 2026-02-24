# CORTEX Prior Art: Cross-Domain Systems Benchmarking Analysis

**Date**: 2026-01-19
**Research Scope**: Cross-domain methodology analysis (DSP, embedded, databases, networking, compilers)
**Objective**: Identify transferable methodologies from mature benchmarking domains

---

## Executive Summary

This expanded research analyzed **18+ toolsacross 9 domains** beyond BCI-specific tools, focusing on mature systems with decades of benchmarking methodology development. The key finding: **CORTEX's signal-processing kernels share more characteristics with audio/DSP, embedded systems, and I/O benchmarking than with ML inference**.

**Critical Discoveries**:
1. **Coordinated Omission**: CORTEX **does NOT suffer from this** (window-based telemetry is time-independent)
2. **Halide's algorithm/schedule separation**: Directly applicable to CORTEX's kernel/config architecture
3. **fio's latency histograms**: Superior methodology to pandas quantile for P50/P95/P99
4. **EEMBC's cross-platform fairness**: Critical lessons for device adapter comparison
5. **FFTW's initialization/measurement separation**: Validates CORTEX's warmup protocol

---

## Critical Questions Answered

### 1. Does CORTEX Suffer from Coordinated Omission?

**Answer: NO** ✅

**What is Coordinated Omission?** (Gil Tene)
- Measurement systems "back off" during system stalls, systematically missing bad latency data
- Example: Load generator waits for response before sending next request → slow responses aren't measured at intended rate
- Impact: Systems that freeze for 100s show avg latency of 10ms instead of 25 seconds

**Why CORTEX Avoids It**:
- **Time-based windowing**: Kernel processes fixed-duration windows (e.g., 256ms @ 250Hz = 64 samples)
- **Independent measurement**: Telemetry records *every* window, regardless of previous window's latency
- **No backoff**: Harness generates data at constant rate (deterministic from EEG datasets)

**Validation**: The CTRL+Z test (pause system → measure latency spike) would correctly show degradation in CORTEX telemetry.

**Contrast with Load Generators**:
- wrk/hey: Send request, wait for response, send next → **suffers from CO**
- wrk2 (Gil Tene's fork): Sends at fixed rate regardless of response time → **avoids CO** (like CORTEX)

---

### 2. Should CORTEX Adopt HdrHistogram?

**Answer: YES, for percentile calculation** (consider for future)

**What HdrHistogram Provides**:
- High dynamic range percentile tracking (nanoseconds to hours) with fixed memory
- Corrected percentile calculation accounting for coordinated omission
- Used by: Cassandra, HBase, wrk2, many JVM applications

**Current CORTEX Approach**:
```python
# analyzer/statistics.py
df['latency_us'].quantile([0.50, 0.95, 0.99])
```
- Uses pandas quantile → simple, accurate for moderate datasets
- Works well for CORTEX's typical run size (10K-100K windows)

**When HdrHistogram Becomes Valuable**:
- **Very long runs**: 1M+ windows (memory-efficient histogramming)
- **Real-time percentiles**: Streaming calculation during benchmark run
- **CO correction**: If CORTEX adds closed-loop feedback (kernel output → next input)

**Recommendation**: **Defer to v1.0+**. Current pandas approach is correct and sufficient. HdrHistogram would be optimization, not fix.

---

### 3. What Can Halide Teach CORTEX About Algorithm/Schedule Separation?

**Answer: CORTEX already implements this core principle** ✅

**Halide's Innovation**:
```halide
// Algorithm: WHAT to compute
Func blur(Func input) {
    return (input(x-1,y) + input(x,y) + input(x+1,y)) / 3;
}

// Schedule: HOW to compute (separate!)
blur.vectorize(x, 8).parallel(y);
```

**Key Insight**: "Optimizing execution strategy requires modifying the schedule, not the algorithm."

**CORTEX's Parallel Structure**:
```c
// Algorithm: kernel/bandpass_fir@f32/kernel.c
void bandpass_fir_process(float *in, float *out, cortex_state_t *state) {
    // Pure algorithm logic (no execution details)
}

// Schedule: primitives/configs/cortex.yaml
benchmark:
  parameters:
    load_profile: heavy      # Execution environment
    warmup_seconds: 2        # Measurement protocol
```

**Transferable Scheduling Primitives from Halide**:

| Halide Primitive | CORTEX Equivalent | Status |
|------------------|-------------------|--------|
| `vectorize(x, 8)` | Compiler flags (`-march=native -ftree-vectorize`) | Implemented (Makefile) |
| `parallel(y)` | Thread count config (future multi-threaded kernels) | Planned |
| `tile(x, y, 32, 32)` | Window size / block size config | Exists (`window_length`) |
| `compute_root()` | Kernel fusion (pipeline composition) | Planned (SE-9) |

**Halide's Auto-Scheduler** (2019):
- Learns optimal schedules from search space exploration
- **Relevance to CORTEX**: Future auto-tuning of config parameters (warmup, load profile) per device

**Action Item**: Document CORTEX's algorithm/schedule separation as design principle (similar to Halide).

---

### 4. How Do EEMBC Benchmarks Achieve Cross-Platform Fairness?

**Answer: Through rigorous run rules and mandatory reporting** (adopt for CORTEX)

**EEMBC CoreMark Fairness Mechanisms**:

#### 1. Prevent Compiler Pre-Computation
- **Problem**: Compiler could pre-compute results at compile-time (Dhrystone weakness)
- **Solution**: "Every operation derives a value not available at compile time"
- **CORTEX Equivalent**: Oracle validation ensures kernel uses *real* EEG data, not constants

#### 2. Eliminate Library Call Variance
- **Problem**: Dhrystone called library functions within timed section → unfair (different libs)
- **Solution**: "All code used within timed portion is part of the benchmark itself (no library calls)"
- **CORTEX Equivalent**: Kernels are self-contained; only cortex_plugin.h API allowed

#### 3. Mandatory Reporting
- **Requirements**:
  - Exact compiler version and flags
  - Memory configuration (freq:core ratio)
  - Cache settings (if configurable)
  - Validation results (CRC checksums must match)
- **CORTEX Gap**: Telemetry doesn't capture compiler info, CPU governor, memory bandwidth

**CORTEX Should Add to Telemetry**:
```c
typedef struct {
    // Existing
    uint64_t start_ts;
    uint64_t end_ts;
    uint32_t latency_us;

    // Add from EEMBC methodology
    char compiler_version[64];   // "gcc 13.2.0 -O3 -march=native"
    char cpu_governor[32];       // "performance", "powersave"
    uint32_t cpu_freq_mhz;       // Actual frequency during window
    uint32_t mem_bandwidth_mbps; // If measurable
} cortex_telemetry_t;
```

#### 4. Runtime Requirements
- **Minimum run duration**: 10 seconds (ensure steady-state)
- **Validation seeds**: Must succeed for multiple fixed seeds
- **Self-checking**: CRC verification ensures correct execution

**CORTEX Alignment**:
- ✅ Runtime: `duration_seconds` config (equivalent)
- ✅ Validation: Oracle validation with fixed tolerances
- 🟡 Self-checking: Could add CRC of output data to telemetry

**Certification Process**:
- EEMBC has "Certification Lab" that verifies submitted scores
- **CORTEX Equivalent**: Future registry of validated results (community-submitted benchmarks)

---

### 5. What HIL Patterns from Automotive/Aerospace Apply to BCI?

**Answer: Real-time validation, 24/7 automation, fault injection**

**dSPACE HIL Testing Patterns**:

#### 1. Hardware-in-the-Loop Architecture
```
[Real ECU] ↔ [Simulated Environment (SCALEXIO)] ↔ [Automated Test Suite]
```

**BCI Equivalent**:
```
[Real Kernel (C)] ↔ [Simulated EEG Data (datasets)] ↔ [Oracle Validation (Python)]
```

**Transferable**: CORTEX already implements this pattern ✅

#### 2. Restbus Simulation
- **Automotive**: Simulate all ECUs except the one under test
- **BCI**: Simulate full pipeline except kernel under test
- **CORTEX Gap**: Pipeline composition (SE-9) would enable this

#### 3. Fault Injection
- **Automotive**: Inject CAN bus errors, sensor faults, power glitches
- **BCI**: Inject data corruption, missing samples, thermal throttle
- **CORTEX Application**:
  - Synthetic datasets with missing data (NaN injection)
  - Forced CPU frequency scaling during benchmark
  - Validation under degraded conditions

#### 4. 24/7 Automated Testing
- **Automotive**: Run test suites overnight, comprehensive coverage
- **CORTEX**: CI/CD integration for continuous benchmarking
- **Already Enabled**: `cortex run` is scriptable, CI-ready

#### 5. ModelDesk/ControlDesk for Real-Time Monitoring
- **Automotive**: Live visualization of ECU state during tests
- **CORTEX**: Real-time telemetry visualization (future)
- **Current**: Post-hoc analysis only (`cortex analyze`)

**Recommendation**: Add `cortex monitor` CLI for live telemetry streaming (WebSocket → dashboard).

---

## Domain-by-Domain Transferable Methodology

### Domain A: DSP/Audio Benchmarking

#### FFTW (Fastest Fourier Transform in the West)

**What It Does**: Benchmark suite for FFT implementations across platforms

**Transferable Methodology**:

1. **Two-Phase Measurement** (Setup vs. Repeated Execution)
   - Phase 1: Call initialization/setup routines (one-time cost)
   - Phase 2: Measure "repeated FFTs of the same zero-initialized array"
   - **CORTEX Adoption**: ✅ Already implemented via `warmup_seconds` config

2. **Normalized Performance Metric**
   ```
   mflops = 5 * N * log2(N) / (time_us)  // Complex FFT
   ```
   - Scales for algorithmic complexity (O(N log N))
   - **CORTEX Equivalent**: Could report "samples/sec" or "windows/sec" normalized by window_length

3. **Timer Calibration**
   - Use lmbench calibration to determine minimum measurable time
   - **CORTEX**: Could add calibration step to `cortex run` (detect timer resolution)

4. **Compiler Flag Consistency**
   - "Hand-pick 'good' compiler options" uniformly
   - **CORTEX**: Document recommended flags per platform in `primitives/kernels/*/Makefile`

**How CORTEX Could Adopt**:
- Add `cortex calibrate-timer` to detect measurement resolution
- Report normalized throughput metric (windows/sec/channel)

**Limitations**: FFTW benchmarks isolated functions; CORTEX benchmarks end-to-end kernels (closer to real use).

---

#### JACK Audio Connection Kit

**What It Does**: Professional real-time audio server with strict latency requirements (3-5ms)

**Transferable Methodology**:

1. **Dual Latency Model** (Capture + Playback)
   ```
   capture_latency:  data arrival → port read
   playback_latency: port write → data output
   ```
   - **CORTEX Equivalent**: Input latency (EEG acquire → kernel start) + Processing latency (kernel duration)

2. **Port-Level Latency Reporting** (`jack_lsp -l`)
   - Every port reports min/max latency
   - **CORTEX**: Per-kernel latency tracking in pipeline composition

3. **jack_delay Utility**
   - Round-trip latency measurement: emit tone → capture → measure phase shift
   - "Great accuracy" via correlation
   - **CORTEX Equivalent**: Oracle could measure round-trip error (input → kernel → oracle → compare)

4. **Real-time Scheduling Priority**
   - Uses elevated RT priority by default
   - **CORTEX**: Could set thread priority for harness (SCHED_FIFO on Linux)

**How CORTEX Could Adopt**:
- **Pipeline latency attribution**: Measure per-stage contribution (bandpass: 5ms, CAR: 2ms, CSP: 8ms)
- **Deadline miss correlation**: JACK detects xruns (buffer underruns); CORTEX detects deadline misses

**Limitations**: JACK assumes closed-loop (audio feedback); CORTEX is open-loop (offline EEG).

---

#### CMSIS-DSP (ARM Signal Processing Library)

**What It Does**: Optimized DSP kernels for ARM Cortex-M/A processors with validation

**Transferable Methodology**:

1. **SNR-Based Validation**
   - Signal-to-noise ratio thresholds for numerical correctness
   - **CORTEX Equivalent**: Could supplement rtol/atol with SNR metrics for filter outputs

2. **Multi-Architecture Testing**
   - Tests on M0, M4, M7, M33, M55, A32 cores
   - **CORTEX**: Device adapters enable similar coverage (x86, ARM, Jetson)

3. **Test Framework Organization**
   - `Testing/Source/Tests` demonstrates function usage
   - **CORTEX Equivalent**: `tests/` directory per kernel (exists for some kernels)

4. **Compiler Coverage**
   - Validates with Arm Compiler v6 (LLVM) and GCC
   - **CORTEX**: Should test with gcc, clang, ICC (Intel)

**How CORTEX Could Adopt**:
- Add SNR validation for frequency-domain kernels (bandpass, goertzel, welch_psd)
- Document test matrix: {kernel} × {platform} × {compiler}

**Limitations**: CMSIS-DSP is library-level; CORTEX benchmarks application-level workloads.

---

### Domain B: Image Processing / Compiler Optimization

#### Halide (Covered in Critical Questions Above)

**Action Item**: Formalize CORTEX's algorithm/schedule separation in architecture docs.

---

#### TVM (Tensor Virtual Machine)

**What It Does**: ML compiler with auto-tuning for cross-platform deployment

**Transferable Methodology**:

1. **Learning-Based Cost Modeling**
   ```
   Loop: Pick candidates → Profile on real hardware → Fit model → Predict next candidates
   ```
   - **CORTEX Equivalent**: Auto-tune config parameters (warmup, load_profile) per device
   - Could learn "on Snapdragon 888, `warmup_seconds=1` is optimal for bandpass_fir"

2. **Search Space Exploration**
   - Dynamic gradient descent through optimization space
   - **CORTEX**: Could explore {compiler_flags} × {warmup} × {cpu_governor} space

3. **Performance Portability**
   - "Competitive with hand-tuned libraries across hardware back-ends"
   - **CORTEX Goal**: Portable kernel API, optimized per platform via config

4. **Benchmark Results Across Platforms**
   - Reports x86 vs ARM vs GPU vs TPU
   - **CORTEX**: Should publish benchmark matrix (kernel × device × latency)

**How CORTEX Could Adopt**:
- `cortex auto-tune --kernel bandpass_fir --device snapdragon888 --metric p95_latency`
- Explore warmup/load_profile/compiler_flags to minimize P95 latency

**Limitations**: TVM optimizes DNN graphs; CORTEX kernels are hand-written C (not graph-based).

---

### Domain C: Database/Storage Benchmarking

#### fio (Flexible I/O Tester)

**What It Does**: Gold standard for I/O latency histograms and percentile reporting

**Transferable Methodology**:

1. **Histogram-Based Percentile Calculation**
   - 1,216 frequency bins with logarithmic distribution
   - Enables "excellent accuracy compared to calculating from logs of every single IOP"
   - **CORTEX**: Currently stores every window latency → could histogram for large runs

2. **Custom Percentile Lists**
   ```
   --percentile_list=99.5:99.9:99.99
   ```
   - User-defined percentiles (max 20)
   - **CORTEX**: Hardcoded to P50/P95/P99; could make configurable

3. **Dual Latency Types**
   - `clat_percentiles`: Completion latency (kernel execution)
   - `lat_percentiles`: Total latency (submission + completion)
   - **CORTEX Equivalent**:
     - Processing latency: Kernel-only time (current)
     - Total latency: Data load + kernel + oracle validation

4. **JSON+ Output with Full Histogram Dump**
   - Enables offline percentile calculation, visualization
   - **CORTEX**: NDJSON telemetry supports this ✅

**How CORTEX Could Adopt**:
- Add `--percentiles` CLI flag: `cortex run --percentiles 90,95,99,99.9`
- Optional histogram mode for million-window runs (memory efficiency)
- Report dual latencies: kernel-only vs end-to-end

**Limitations**: fio measures I/O (microseconds); CORTEX measures signal processing (milliseconds). Different scale, similar methodology.

---

### Domain D: Network/Web Latency Measurement

#### Coordinated Omission (Covered Above)

**Conclusion**: CORTEX avoids this due to time-based windowing ✅

---

#### wrk2 (Gil Tene's Fork)

**What It Does**: HTTP load tester that avoids coordinated omission

**Key Innovation**:
```
wrk:  Send request → Wait for response → Send next  [BAD]
wrk2: Send requests at constant rate (Poisson)       [GOOD]
```

**CORTEX Alignment**:
- Kernel processes EEG windows at constant rate (250Hz, 500Hz, etc.)
- Telemetry independent of previous window's latency
- ✅ Inherently avoids CO

**Action**: Document this as design principle in measurement methodology.

---

### Domain E: Embedded/RTOS Benchmarking

#### EEMBC CoreMark (Covered in Critical Questions)

**Key Takeaway**: Cross-platform fairness requires mandatory reporting of execution environment.

---

### Domain F: Hardware-in-the-Loop Testing

#### dSPACE (Covered in Critical Questions)

**Key Takeaway**: 24/7 automation, fault injection, real-time monitoring.

---

### Domain G: Continuous Profiling

#### async-profiler + eBPF

**What It Does**: Low-overhead JVM profiling (< 5% overhead at 1kHz sampling)

**Transferable Methodology**:

1. **Sampling Frequency vs. Overhead Tradeoff**
   - 100Hz: minimal overhead
   - 1kHz: < 5% overhead (production-safe)
   - 4kHz: ~10% overhead
   - **CORTEX**: Per-window telemetry is zero-overhead (post-execution write)

2. **eBPF Kernel-Level Sampling**
   - Collect stack traces without JVM safepoint bias
   - **CORTEX**: Could use eBPF to capture CPU freq, cache misses during kernel execution

3. **Continuous Production Profiling**
   - "Low enough overhead to be enabled continuously"
   - **CORTEX Future**: Embedded device agents for continuous kernel monitoring

**How CORTEX Could Adopt**:
- Integrate eBPF probes for platform-state capture (CPU freq, thermal) on Linux
- Lightweight sampling mode: Record telemetry every Nth window (reduce overhead)

**Limitations**: async-profiler is for profiling; CORTEX is for benchmarking (different goals).

---

### Domain H: Scientific Computing Validation

#### BLAS/LAPACK Testing

**What It Does**: Numerical library correctness validation with tolerance methodology

**Transferable Methodology**:

1. **Test Ratio with Machine Precision Scaling**
   ```c
   test_ratio = (abs(computed - expected) / expected) / (n * ulp)
   ulp = unit in last place (machine epsilon)
   ```
   - Accounts for roundoff error growth (O(n))
   - **CORTEX**: Uses fixed rtol=1e-5, atol=1e-6 (doesn't scale with n)

2. **Two-Tier Failure Classification**
   - **Minor**: test_ratio slightly exceeds threshold (investigate)
   - **Major**: test_ratio ~ E+06 (critical bug)
   - **CORTEX**: Binary pass/fail; could add severity levels

3. **Machine-Dependent Parameters**
   - r1mach.f, d1mach.f for machine epsilon, max/min float
   - **CORTEX**: Hardcoded tolerances; could query numpy.finfo(np.float32)

4. **Comprehensive Test Suite in Distribution**
   - LAPACK includes Fortran source + test programs
   - **CORTEX**: Kernels have oracles; could add unit tests (cmocka, Check)

**How CORTEX Could Adopt**:
- **Scaled tolerances**: rtol = f(operation_count, data_size)
- **Severity reporting**: oracle validation returns (PASS, MINOR_FAIL, MAJOR_FAIL, error_magnitude)
- **Test matrix**: {kernel} × {dtype} × {channel_count} × {sample_rate}

**Limitations**: BLAS/LAPACK are pure numerical; BCI kernels have state management.

---

### Domain I: Build/Deploy Systems

#### Bazel Remote Execution

**What It Does**: Distributed build/test with cross-platform support

**Transferable Methodology**:

1. **Platform Constraints** (`exec_properties`)
   - Specify target architecture (arm64, amd64)
   - Route actions to appropriate worker pools
   - **CORTEX Equivalent**: Device adapter factory routes to SSH/ADB/USB based on target

2. **Hermetic Builds**
   - All dependencies explicit; no reliance on host environment
   - **CORTEX**: Kernel Makefiles should be hermetic (no implicit /usr/lib paths)

3. **Remote Caching Across Platforms**
   - Cache keyed by: source hash + compiler + flags + platform
   - **CORTEX**: Could cache compiled kernels (same source + flags → reuse binary)

4. **Tool Shipping**
   - "Ship source code for tools to be built for remote platform"
   - **CORTEX**: Device adapters deploy source → compile on target (SSH adapter does this)

**How CORTEX Could Adopt**:
- Binary cache for kernels: `~/.cortex/cache/{source_hash}/{platform}/{compiler}/kernel.so`
- Hermetic Makefiles: All paths relative, no system library assumptions
- Remote compilation: `cortex build --device snapdragon888` → compile on device via SSH

**Limitations**: Bazel is for large-scale infrastructure; CORTEX is research tool (different scale).

---

## Synthesis: Reuse/Adapt/Innovate (Updated)

### Reuse (Direct Integration)

| Tool/Library | Purpose | Integration Point | Priority |
|--------------|---------|-------------------|----------|
| **HdrHistogram** | High-precision percentile calculation | Analyzer (replace pandas quantile) | Low (v1.0+) |
| **eBPF/bpftrace** | Platform-state capture (CPU freq, cache) | Telemetry module (Linux only) | High (v0.6.0) |
| **lmbench timer calibration** | Detect measurement resolution | `cortex calibrate-timer` CLI | Medium (v0.7.0) |
| **wrk2 constant-rate pattern** | Avoid coordinated omission | Already inherent in design ✅ | N/A |

### Adopt Methodologies

| Methodology | Source | CORTEX Application | Implementation |
|-------------|--------|-------------------|----------------|
| **Algorithm/schedule separation** | Halide | Document as design principle | Existing (kernel.c + config.yaml) |
| **Histogram-based percentiles** | fio | Configurable percentile list | Add `--percentiles` CLI flag |
| **Two-phase measurement** | FFTW | Warmup vs measurement | Implemented ✅ |
| **Mandatory reporting** | EEMBC | Compiler, governor, freq in telemetry | Extend telemetry struct |
| **Test ratio scaling** | BLAS/LAPACK | Machine-precision-aware tolerances | Scale rtol by operation count |
| **SNR validation** | CMSIS-DSP | Frequency-domain correctness | Add for bandpass, goertzel, welch |
| **Dual latency types** | fio | Kernel-only vs end-to-end latency | Add total_latency_us field |
| **Fault injection** | dSPACE HIL | Dataset corruption, forced throttling | Synthetic dataset options |

### Innovate (CORTEX-Specific)

| Innovation | Rationale | Status |
|-----------|-----------|--------|
| **Window-based telemetry** | Signal processing ≠ request/response | Implemented ✅ |
| **Oracle-validated correctness** | BCI kernels need numerical validation | Implemented ✅ |
| **Platform-effect correlation** | Commodity edge devices have DVFS/thermal | Partial (thermal only) |
| **Pipeline composition** | BCI workflows are multi-stage | Not implemented |
| **Cross-language calibration ABI** | Python trains → C deploys | Implemented (`.cortex_state`) |

---

## Critical Recommendations

### Immediate (v0.6.0)

1. **Add Platform Context to Telemetry** (EEMBC-inspired)
   ```c
   struct cortex_platform_context {
       char compiler[64];     // "gcc 13.2.0 -O3 -march=native"
       char cpu_governor[32]; // "performance" | "powersave"
       uint32_t cpu_freq_mhz; // Actual frequency during window
       uint32_t thermal_c;    // Temperature (if available)
   };
   ```
   **Effort**: 1 week
   **Impact**: Cross-platform comparability (EEMBC fairness)

2. **Document Coordinated Omission Avoidance**
   Add to `docs/methodology.md`: "CORTEX avoids CO via time-based windowing"
   **Effort**: 1 day
   **Impact**: Establishes measurement rigor

3. **eBPF Integration for Platform State** (Linux)
   Use bpftrace to capture CPU freq, cache misses per window
   **Effort**: 2 weeks
   **Impact**: SE-8 (P99 latency root cause analysis)

### Near-Term (v0.7.0)

4. **Configurable Percentile Reporting**
   `cortex analyze --percentiles 90,95,99,99.9`
   **Effort**: 3 days
   **Impact**: User flexibility (fio-inspired)

5. **Dual Latency Metrics** (Processing vs Total)
   - `processing_latency_us`: Kernel execution only
   - `total_latency_us`: Data load + kernel + telemetry write
   **Effort**: 1 week
   **Impact**: Isolate kernel performance from I/O

6. **Timer Calibration** (FFTW-inspired)
   `cortex calibrate-timer` → detect measurement resolution
   **Effort**: 1 week
   **Impact**: Validates telemetry accuracy per platform

### Long-Term (v1.0+)

7. **Auto-Tuning Framework** (TVM-inspired)
   `cortex auto-tune --kernel bandpass_fir --device pi4 --optimize p95_latency`
   Explores {warmup, load_profile, compiler_flags} to minimize P95
   **Effort**: 4 weeks
   **Impact**: Optimal config per device (researcher productivity)

8. **HdrHistogram Integration**
   Replace pandas quantile with HdrHistogram for P50/P95/P99
   **Effort**: 1 week
   **Impact**: Memory efficiency for long runs (1M+ windows)

9. **Pipeline Latency Attribution** (JACK-inspired)
   Report per-stage latency: bandpass → CAR → CSP → classifier
   **Effort**: Requires SE-9 pipeline composition (3 weeks)
   **Impact**: End-to-end optimization

---

## Validation of CORTEX's Unique Position (Updated)

**Cross-domain analysis confirms**: No single tool combines:
- ✅ **Numerical correctness** (BLAS/LAPACK-style validation)
- ✅ **Distributional latency** (fio/HdrHistogram methodology)
- ✅ **Platform-effect awareness** (EEMBC reporting + eBPF capture)
- ✅ **Signal-processing focus** (FFTW/CMSIS-DSP domain)
- ✅ **Cross-platform deployment** (Bazel remote execution patterns)
- ✅ **Algorithm/schedule separation** (Halide design principle)

**CORTEX fills the gap between**:
- **Numerical libraries** (BLAS/LAPACK): Correctness but no latency/platform measurement
- **I/O benchmarks** (fio): Latency but no numerical validation
- **ML compilers** (TVM): Cross-platform but no signal-processing focus
- **DSP libraries** (CMSIS-DSP): Optimized kernels but no deployment benchmarking

---

## Final Architecture Implications

### 1. Telemetry Must Expand (EEMBC + fio)
```c
typedef struct cortex_telemetry {
    // Existing
    uint64_t start_ts;
    uint64_t end_ts;
    uint32_t latency_us;
    uint8_t deadline_missed;

    // Add from cross-domain research
    uint32_t processing_latency_us; // Kernel only (fio: clat)
    uint32_t total_latency_us;      // End-to-end (fio: lat)
    uint32_t cpu_freq_mhz;          // EEMBC mandatory reporting
    char cpu_governor[16];          // EEMBC mandatory reporting
    int32_t thermal_c;              // dSPACE: thermal monitoring
    uint64_t cache_misses;          // eBPF: performance counters
} cortex_telemetry_t;
```

### 2. Configuration Must Document Intent (Halide)
```yaml
# primitives/configs/cortex.yaml
benchmark:
  algorithm:  # WHAT to compute (kernel logic)
    kernels:
      - name: bandpass_fir
        precision: float32

  schedule:   # HOW to compute (execution strategy)
    warmup_seconds: 2
    load_profile: heavy
    compiler_flags: "-O3 -march=native"  # NEW
```

### 3. Validation Must Scale with Complexity (BLAS/LAPACK)
```python
# oracle/bandpass_fir/oracle.py
def validate(c_output, py_output, metadata):
    n = metadata['operation_count']  # Filter taps × samples
    ulp = np.finfo(np.float32).eps

    # Scale tolerance with complexity (BLAS-inspired)
    rtol = 1e-5 * np.sqrt(n)
    atol = 1e-6 * n * ulp

    np.testing.assert_allclose(c_output, py_output, rtol=rtol, atol=atol)
```

### 4. Reporting Must Enable Fairness (EEMBC)
```json
{
  "kernel": "bandpass_fir@f32",
  "device": "raspberrypi4",
  "p95_latency_us": 4523,
  "execution_environment": {
    "compiler": "gcc 12.2.0",
    "flags": "-O3 -march=armv8-a+simd -mfpu=neon-fp-armv8",
    "cpu": "Cortex-A72 @ 1.8GHz",
    "governor": "performance",
    "thermal_max_c": 62,
    "cortex_version": "0.6.0",
    "validation": "PASS (rtol=1e-5)"
  }
}
```

---

## Conclusion

**Cross-domain research reveals CORTEX is more similar to**:
1. **I/O benchmarks** (fio) — latency distributions, percentile rigor
2. **DSP libraries** (FFTW, CMSIS-DSP) — signal processing, numerical validation
3. **Embedded benchmarks** (EEMBC) — cross-platform fairness, mandatory reporting
4. **Compiler frameworks** (Halide, TVM) — algorithm/schedule separation, auto-tuning

**Than to**:
- ML inference tools (MLPerf, TensorRT) — focused on DNNs, not signal processing
- BCI tools (MOABB, BCI2000) — accuracy or latency, never both

**Strategic Direction**:
- **Short-term**: Adopt fio's dual-latency model, EEMBC's mandatory reporting
- **Medium-term**: Integrate eBPF for platform-state capture, configurable percentiles
- **Long-term**: TVM-style auto-tuning, HdrHistogram for extreme-scale runs

**CORTEX remains unique**: The only tool combining BLAS/LAPACK-style correctness validation with fio-style latency measurement for signal-processing kernels on commodity edge devices.

---

## References (Cross-Domain)

### DSP/Audio
- FFTW Benchmark Methodology: https://www.fftw.org/speed/method.html
- JACK Latency Functions: https://jackaudio.org/api/group__LatencyFunctions.html
- CMSIS-DSP Testing: https://github.com/ARM-software/CMSIS-DSP/tree/main/Testing

### Image Processing / Compilers
- Halide: "Decoupling Algorithms from Schedules" (ACM CACM 2018)
- TVM: "An Automated End-to-End Optimizing Compiler for Deep Learning" (OSDI 2018)

### Databases / Storage
- fio Manual: https://fio.readthedocs.io/
- fio Latency Measurements: https://www.cronburg.com/fio/cloud-latency-problem-measurement/

### Networking
- Gil Tene: "How NOT to Measure Latency" (talk)
- Coordinated Omission: https://groups.google.com/g/mechanical-sympathy/c/icNZJejUHfE
- HdrHistogram: https://hdrhistogram.github.io/HdrHistogram/

### Embedded
- EEMBC CoreMark: https://www.eembc.org/coremark/
- CoreMark White Paper: https://www.eembc.org/techlit/articles/coremark-whitepaper.pdf

### HIL Testing
- dSPACE HIL Simulation: https://www.dspace.com/en/inc/home/applicationfields/foo/hil-testing.cfm

### Continuous Profiling
- async-profiler: https://github.com/async-profiler/async-profiler
- "Profiling and Tracing Support for Java Applications" (ICPE 2019)

### Scientific Computing
- LAPACK Testing: https://www.netlib.org/lapack/lug/node72.html
- "Testing Linear Algebra Software" (Higham 1997)

### Build/Deploy
- Bazel Remote Execution: https://bazel.build/remote/rbe
- "Leveraging Bazel Remote Caching for Cross-Platform Builds" (Medium 2021)
