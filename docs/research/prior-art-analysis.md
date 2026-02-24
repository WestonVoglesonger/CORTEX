# CORTEX Prior Art Research: Capability Gap Analysis

**Date**: 2026-01-19
**Research Scope**: Comprehensive analysis of existing tools and methodologies for CORTEX capabilities
**Objective**: Determine reuse vs. innovate strategy for each capability

---

## Executive Summary

This research systematically evaluated 18+ capabilities across 5 domains (BCI tools, ML inference, systems benchmarking, real-time profiling, device deployment) to determine where CORTEX should **reuse** existing tools, **adapt** established methodologies, or **innovate** with novel approaches.

**Key Finding**: Most BCI tools focus exclusively on accuracy/efficacy (MOABB, BCI2000), while ML inference frameworks (MLPerf, TensorRT) provide latency measurement methodologies but lack BCI-specific features. **CORTEX's unique value proposition—combining oracle-validated correctness with distributional latency measurement under platform effects—requires innovation in integration architecture, not reinvention of individual components.**

**Strategic Direction**:
- **Reuse** (40%): Leverage established tools for platform measurement (perf/ftrace), load generation (stress-ng), device deployment (ADB, SSH)
- **Adapt** (35%): Adopt methodologies from MLPerf (P90/P99 latency), roofline model (diagnostics), scientific computing (oracle validation)
- **Innovate** (25%): Novel integration of correctness validation with latency measurement, BCI-specific calibration workflows, cross-platform kernel orchestration

---

## Domain 1: BCI-Specific Tools

### Tools Evaluated
- **BCI2000**: Real-time BCI platform (C++, lab workstations)
- **OpenViBE**: Visual programming BCI framework (C++, desktop-focused)
- **MOABB**: Accuracy benchmarking for offline BCI algorithms (Python)
- **MNE-Python**: EEG/MEG analysis library (offline)
- **BCILAB**: MATLAB-based BCI prototyping

### Key Findings

#### 1. Latency Measurement
**BCI2000** provides a latency measurement procedure (PMC3161621) using:
- Software timestamps (QueryPerformanceCounter on Windows)
- Hardware event markers (photodiodes, microphones)
- **Reports only mean ± SD, not percentile distributions (P50/P95/P99)**
- **Does NOT account for platform effects (DVFS, thermal, scheduling)**
- 1ms timer resolution insufficient for sub-millisecond analysis

**Gap**: No BCI tool measures distributional latency or controls for platform state.

#### 2. Accuracy Benchmarking
**MOABB** excels at offline accuracy evaluation:
- 67+ datasets, 1,735+ subjects
- Standardized evaluation schemes (within-session, cross-session, cross-subject)
- Built on MNE-Python and scikit-learn
- **Does NOT measure latency, deployment readiness, or real-time constraints**

**Gap**: Accuracy-focused only; deployment gap documented in literature (Liu 2021, Willett 2019).

#### 3. Oracle Validation
**No BCI tool provides oracle validation**. MOABB compares algorithms against each other on benchmark datasets, but doesn't verify C implementations against Python references.

**Gap**: Complete absence of correctness validation for optimized implementations.

#### 4. Calibration Workflows
**BCILAB** and research literature (Towards Zero Training, PLOS One 2008) document:
- Standard approach: record calibration session → train CSP/ICA filters → apply in feedback session
- State transfer: spatial filters from calibration → new session
- **Serialization is ad-hoc; no standardized format for deployment**

**Gap**: No established ABI for trained-state serialization across platforms.

### Recommendation
- [ ] **Reuse**: MOABB for AR persona efficacy benchmarking (defer to future)
- [x] **Adapt**: Calibration workflow concepts from BCILAB/literature
- [x] **Innovate**: Oracle validation framework (BCI-first), latency measurement integration

---

## Domain 2: ML Inference Benchmarking

### Tools Evaluated
- **MLPerf Inference**: Industry-standard ML benchmark suite
- **nn-Meter**: Latency prediction for edge DNNs (Microsoft Research)
- **TensorRT**: NVIDIA GPU inference optimization
- **ONNX Runtime**: Cross-platform inference engine
- **TFLite**: Mobile/edge inference (Google)

### Key Findings

#### 1. Percentile Latency Measurement (MLPerf)
**Methodology** (MLPerf Inference Rules):
- **Single-stream**: 90th percentile latency
- **Server**: 99th percentile latency (stricter for reliability)
- **LLM server**: P99 TPOT ≤ 40ms, P99 TTFT ≤ 450ms
- **Statistical confidence**: Early stopping with confidence intervals (e.g., 270K samples for 99% CI with 0.05% margin)
- **Load generation**: Poisson distribution for server scenario

**Gap for CORTEX**: MLPerf focuses on DNN inference; lacks signal-processing-specific considerations (window-based processing, stateful kernels).

#### 2. Platform State Control (MLPerf)
**What MLPerf specifies**:
- ECC memory required for datacenter submissions
- Replicability mandatory

**What MLPerf does NOT specify**:
- CPU frequency locking
- Thermal throttling control
- DVFS governor policy
- Power state management

**Gap**: Platform effects acknowledged in mobile inference research (Yang 2020: "latency variability under CPU resource contention"), but not standardized in MLPerf methodology.

#### 3. Latency Prediction (nn-Meter)
**Methodology**:
- Kernel-level latency modeling (divide model into execution units)
- Adaptive sampling to build predictors
- Evaluated on 26K models across mobile CPU/GPU, Intel VPU

**Relevance to CORTEX**: Demonstrates importance of kernel-level decomposition for cross-platform prediction—similar to CORTEX's plugin architecture.

#### 4. Inference Optimization Tools (TensorRT, ONNX, TFLite)
**TensorRT**: 5-8× speedup on NVIDIA GPUs, median latency + throughput metrics
**ONNX Runtime**: Cross-platform portability, execution providers for diverse hardware
**TFLite**: Mobile-optimized, binary size reduction

**Gap**: These are inference *engines*, not benchmarking *frameworks*. They provide runtime optimization but lack standardized measurement methodology.

### Recommendation
- [x] **Adopt**: MLPerf P90/P99 methodology, statistical confidence requirements, early stopping
- [x] **Adapt**: Kernel-level decomposition insight from nn-Meter for CORTEX plugin model
- [ ] **Reuse**: None directly (inference engines serve different purpose)
- [x] **Innovate**: Extend MLPerf methodology with platform-state control (DVFS, thermal)

---

## Domain 3: Systems Benchmarking

### Tools Evaluated
- **stress-ng**: CPU/memory/IO stress testing (Linux)
- **sysbench**: Multi-threaded benchmark for databases, CPU, memory
- **lmbench**: Latency/bandwidth micro-benchmarks
- **perf**: Linux performance counters and profiling
- **ftrace**: Linux kernel function tracing

### Key Findings

#### 1. Load Profiles (stress-ng, sysbench)
**stress-ng capabilities**:
- 75+ CPU stressor methods (FP, integer, vector, matrix, FFT)
- Platform-specific effectiveness (e.g., `--cpu-method fft` best for Pi4 Cortex-A72)
- **Different stressors produce different thermal results** (sysbench 60°C vs stress-ng 80°C+)

**Insight**: Instruction mix matters for thermal behavior—critical for CORTEX platform-effect isolation.

**Gap**: No BCI-specific workload generators; general-purpose stress testing doesn't match signal-processing compute patterns.

#### 2. Platform-State Capture (perf, ftrace)
**Linux tracepoints for power/thermal** (`/include/trace/events/power.h`):
- `cpu_frequency`: DVFS frequency changes (ARM SoCs reliable, Intel CPUs unreliable due to internal DVFS)
- `cpu_idle`: C-state transitions
- `thermal_zone_trip`: Thermal throttling events

**Methodology**:
```bash
# Enable power tracepoints
echo 1 > /sys/kernel/debug/tracing/events/power/cpu_frequency/enable
echo 1 > /sys/kernel/debug/tracing/events/power/cpu_idle/enable
```

**Perfetto** also provides CPU frequency tracing via `cpu_freq` data source.

**Gap**: Tools exist but require per-platform integration. Intel frequency scaling invisible to kernel on modern CPUs.

#### 3. Performance Counter Access (perf)
**Capabilities**:
- CPU performance counters (cache misses, branch mispredictions, etc.)
- Tracepoints (scheduler, syscalls, custom USDT probes)
- Stack sampling for hotspot analysis

**Relevance**: Foundation for CORTEX diagnostic framework (SE-5 bottleneck attribution).

### Recommendation
- [x] **Reuse**: perf/ftrace for platform-state capture (CPU freq, thermal on Linux)
- [x] **Reuse**: stress-ng for controlled load injection (CORTEX load profiles)
- [ ] **Adapt**: Benchmark methodology insights (platform variability)
- [x] **Innovate**: BCI-specific workload characterization (signal processing ≠ matrix multiply)

---

## Domain 4: Real-Time / Embedded Profiling

### Tools Evaluated
- **LTTng**: Low-overhead tracing for real-time Linux
- **Tracealyzer**: Commercial RTOS trace visualization
- **perf-ftrace**: Combined Linux tooling
- **PREEMPT_RT**: Real-time Linux patches

### Key Findings

#### 1. Deadline Miss Detection (LTTng)
**Methodology** (Monitoring real-time latencies, lttng.org 2016):
- **Snapshot mode**: Record in-memory ring buffer, dump on latency threshold
- Minimize critical-path overhead (only latency detection at runtime, analysis offline)
- **ros2_tracing** framework provides deadline miss analysis for ROS 2

**Gap**: Methodology exists but requires application integration; no turnkey solution for arbitrary C kernels.

#### 2. WCET Analysis (Research: From Tracepoints to Timeliness, 2025)
**Novel approach using tracepoints for WCET**:
- Semi-Markov chains model execution times between events
- **Timed Tracepoints (TTPs)**: event ID + high-res timestamp + minimal context
- WCET = maximal time-to-absorption in stochastic process

**Insight**: Empirical WCET estimation from trace data—alternative to static analysis.

**Gap**: Research-stage; no production tools automate this for general embedded systems.

#### 3. Low-Overhead Tracing (LTTng Design)
**Design principles**:
- "Disturb traced system as little as possible"—enables tracing subtle race conditions
- Lock-free ring buffers
- Per-CPU buffering

**Relevance**: CORTEX telemetry must minimize measurement overhead—LTTng design patterns applicable.

### Recommendation
- [x] **Adopt**: LTTng snapshot methodology for deadline anomaly detection
- [x] **Adapt**: Timed tracepoint design for CORTEX telemetry (minimal overhead)
- [ ] **Reuse**: None directly (LTTng requires kernel integration)
- [x] **Innovate**: User-space deadline miss detection for portable deployment

---

## Domain 5: Device Deployment Tools

### Tools Evaluated
- **ADB (Android Debug Bridge)**: Android device communication/automation
- **Ansible**: SSH-based infrastructure automation (Python)
- **Fabric**: SSH command execution library (Python)
- **PlatformIO**: Embedded development platform (supports Zephyr, Arduino, etc.)

### Key Findings

#### 1. Remote Benchmark Automation (ADB)
**Capabilities**:
- Push binaries, run commands, pull results over USB/network
- UL Benchmarks custom benchmark automation via `config.json` + ADB commands
- Shell automation for batch operations

**Gap**: Android-specific; USB reliance limits field deployment scenarios.

#### 2. SSH Deployment (Ansible vs Fabric)
**Ansible**:
- Declarative YAML, idempotent operations
- Designed for large-scale (1000+ hosts)
- Connection multiplexing, pipelining for performance
- IoT/edge device support documented

**Fabric**:
- Procedural Python, imperative commands
- Lightweight, better for ad-hoc tasks
- Not optimized for scale

**Insight**: CORTEX already uses SSH deployer (Paramiko); Ansible's idempotency and pipelining could improve robustness.

#### 3. Embedded Platform Support (PlatformIO + Zephyr)
**PlatformIO**:
- Cross-platform build system (70+ platforms)
- Zephyr RTOS integration
- HAL abstraction for vendor silicon

**Gap**: CORTEX targets *deployment benchmarking* on running OS (Linux, Android), not bare-metal RTOS. PlatformIO relevant for future HE persona (FPGA/RTOS).

### Recommendation
- [x] **Reuse**: ADB for Android deployment (existing CORTEX capability: planned)
- [x] **Adapt**: Ansible deployment patterns (idempotency, pipelining) for SSH deployer improvements
- [ ] **Reuse**: PlatformIO (defer to HE persona, Spring 2026)
- [x] **Innovate**: Unified transport abstraction (SSH, ADB, USB) for CORTEX device adapters

---

## Capability-Specific Analysis

### 1. Oracle Validation

#### Existing Tools
**None directly applicable**. Scientific computing literature (Correctness in Scientific Computing, arXiv 2023) documents:
- **Oracle problem**: Difficult to verify numerical results when no ground truth exists
- **Identity relations**: Test using mathematical identities (e.g., cos(-x) = cos(x))
- **Differential testing**: Check two implementations against each other

#### Methodology in Literature
- **SciPy validation approach**: Test C extensions against pure Python reference
- **Relative tolerance**: `rtol=1e-5`, `atol=1e-6` (NumPy testing conventions)
- **Solution verification**: Assess whether numerical approximation is "sufficiently accurate for its intended use"

#### Gap Analysis
- **What exists**: Conceptual frameworks, testing patterns from scientific Python ecosystem
- **What's missing for CORTEX**:
  - Automated workflow: Python oracle.py ↔ C kernel validation
  - BCI-specific tolerances (signal processing ≠ linear algebra)
  - CLI integration (`cortex validate`)

#### Recommendation
- [x] **Adapt**: SciPy/NumPy testing methodology (rtol/atol), differential testing pattern
- [x] **Innovate**: Automated orchestration (load EEG data → run C + Python → compare)
- **Integration**: Already exists in CORTEX (`cortex validate`, rtol=1e-5, atol=1e-6) ✅

---

### 2. Device Adapters (SSH, USB, ADB, FPGA)

#### Existing Tools
- **SSH**: Ansible, Fabric, Paramiko, OpenSSH
- **ADB**: Android SDK, adb CLI
- **USB**: libusb, pyusb
- **FPGA**: Vivado, Quartus, OpenOCD (JTAG)

#### Methodology in Literature
- **Ansible** (Red Hat IoT docs): SSH multiplexing, pipelining, idempotent operations for edge devices
- **ADB** (UL Benchmarks): JSON config → automated benchmark execution → result pull
- **PlatformIO**: Build system abstraction over vendor toolchains

#### Gap Analysis
- **What exists**: Low-level transport primitives (SSH, ADB, USB libraries)
- **What's missing for CORTEX**:
  - Unified abstraction: transport-agnostic kernel deployment
  - Automated build-deploy-measure workflow
  - Platform detection (use SSH if available, else USB, else ADB)

#### Recommendation
- [x] **Reuse**: Paramiko (SSH), ADB CLI (Android), libusb (future USB adapter)
- [x] **Adapt**: Ansible patterns (idempotency, error handling) for deployer robustness
- [x] **Innovate**: Factory routing (`AdapterFactory.create(uri)` → auto-detect transport)
- **Integration**: SSH adapter exists; USB/ADB/FPGA planned per roadmap

---

### 3. Kernel Calibration

#### Existing Tools
- **scikit-learn**: `model.fit()` + `joblib.dump()` for serialization
- **BCILAB** (MATLAB): CSP filter training, manual state export
- **Research literature**: "Towards Zero Training" (PLOS One 2008)—transfer spatial filters

#### Methodology in Literature
**Standard BCI calibration workflow**:
1. Record calibration session (labeled motor imagery trials)
2. Train CSP/ICA spatial filters using calibration data
3. Serialize trained parameters
4. Load parameters in online/feedback session
5. Apply filters to new data without retraining

**Serialization approaches**:
- Python: `joblib.dump(csp_filters, 'csp.pkl')`
- MATLAB: Manual export to `.mat` files
- **No standardized cross-language format**

#### Gap Analysis
- **What exists**: Training algorithms (CSP in MNE-Python, ICA in scipy), Python serialization
- **What's missing for CORTEX**:
  - **Cross-language ABI**: Python trains → C deploys (need `.cortex_state` format)
  - CLI workflow: `cortex calibrate` → auto-train → serialize → inject into kernel
  - Multi-kernel support (CSP, ICA, adaptive filters)

#### Recommendation
- [x] **Adapt**: scikit-learn fit/dump pattern, BCI calibration workflow from literature
- [x] **Innovate**: `.cortex_state` binary format (cross-platform, C-readable)
- **Integration**: `cortex calibrate` exists; generates `.cortex_state` files ✅

---

### 4. Synthetic Datasets

#### Existing Tools
- **EEGdenoiseNet** (2021): 3400 segments, 10 SNR levels, EOG/EMG artifact injection
- **SEED-G** (2021): Connectivity-pattern-based pseudo-EEG generation
- **Statistical approach** (arXiv 2025): Correlation structure + probabilistic sampling
- **Diffusion models** (arXiv 2023): Generative models for synthetic EEG

#### Methodology in Literature
**Parameterized generation**:
- Control: # channels, duration, sample rate, noise level, connectivity patterns
- Signal types: Pink noise, sine waves, AR processes, real-EEG-derived
- Validation: Spectral properties, connectivity metrics match real data

**Use cases**:
- Algorithm testing without patient data
- Scalability testing (e.g., 1024 channels when only 64-channel data available)
- Ground-truth labels for denoising/artifact removal

#### Gap Analysis
- **What exists**: Research tools for connectivity testing, denoising benchmarks
- **What's missing for CORTEX**:
  - **CLI integration**: `cortex generate --channels 256 --duration 60 --signal pink_noise`
  - **Self-describing datasets**: Embed `spec.yaml` with generation parameters
  - BCI kernel testing focus (not just connectivity/denoising)

#### Recommendation
- [x] **Adapt**: Parameterized generation methodology (channels, duration, SR, signal types)
- [x] **Innovate**: Self-describing dataset format with `spec.yaml`, CLI-driven workflow
- **Integration**: `cortex generate` exists; supports pink_noise, sine_wave ✅

---

### 5. Sustained Measurement & Warmup Protocol

#### Existing Tools
- **MLPerf**: Duration + repeat parameters, no explicit warmup in public rules
- **Benchmark best practices** (SPEC, PARSEC): Warmup to reach steady-state thermal/cache behavior

#### Methodology in Literature
- **SPEC CPU**: Multiple iterations, discard first few for warmup
- **Mobile inference** (Yang 2020): "Benchmark must lock CPU frequency to eliminate DVFS-induced variability"
- **Cache/thermal warmup**: Run workload until performance stabilizes

#### Gap Analysis
- **What exists**: General principles (warmup before measurement, sustained runs for stability)
- **What's missing for CORTEX**:
  - **Configurable warmup**: Per-kernel warmup duration (some kernels reach steady-state faster)
  - **Stability detection**: Auto-detect when warmup completes (variance threshold)
  - Multi-level override: YAML config → CLI flag → env var

#### Recommendation
- [x] **Adopt**: Warmup-then-measure pattern from SPEC/benchmarking best practices
- [x] **Innovate**: Three-tier configuration (YAML, CLI, env), per-plugin warmup application
- **Integration**: `benchmark.parameters.warmup_seconds`, `CORTEX_WARMUP_OVERRIDE` exist ✅

---

### 6. Load Profiles

#### Existing Tools
- **stress-ng**: 75+ CPU stressor methods, configurable load intensity
- **sysbench**: Thread-count-based load generation
- **cpulimit**: Limit CPU usage of processes

#### Methodology in Literature
- **Platform effects** (Yang 2020): "Latency variability under CPU resource contention"
- **Thermal management**: Different instruction mixes → different heat output (stress-ng matrix vs FFT)

#### Gap Analysis
- **What exists**: Tools to generate CPU load (stress-ng best-in-class)
- **What's missing for CORTEX**:
  - **Declarative load profiles**: `idle`, `medium`, `heavy` → auto-select stress-ng parameters
  - **Co-scheduled execution**: Run kernel benchmark + background load simultaneously
  - Platform-specific tuning (Cortex-A72 vs x86 vs Snapdragon)

#### Recommendation
- [x] **Reuse**: stress-ng as load generator subprocess
- [x] **Adapt**: Instruction-mix insight (matrix stressor for thermal stress)
- [x] **Innovate**: Declarative `benchmark.load_profile` config with platform-aware mapping
- **Integration**: Config has `load_profile` field (idle/medium/heavy); **enforcement pending** 🟡

---

### 7. Platform-State Capture

#### Existing Tools
- **perf/ftrace**: Linux power tracepoints (`cpu_frequency`, `cpu_idle`, `thermal_zone_trip`)
- **Perfetto**: CPU frequency and idle state tracing
- **tegrastats** (NVIDIA Jetson): Temperature, power, CPU/GPU freq monitoring
- **powertop**: Power consumption analysis

#### Methodology in Literature
**Kernel tracepoints** (`/include/trace/events/power.h`):
- `cpu_frequency`: Log DVFS changes (ARM reliable, Intel unreliable)
- `thermal_zone_trip`: Thermal throttling events
- **sysfs polling**: Read `/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq` periodically

**Limitations**:
- Intel turbo boost invisible to kernel on modern CPUs
- Polling overhead vs event-driven tracing tradeoff

#### Gap Analysis
- **What exists**: Platform-specific tools (tegrastats, perf), kernel APIs
- **What's missing for CORTEX**:
  - **Cross-platform abstraction**: Unified API for freq/thermal capture (Linux/macOS/Windows)
  - **Telemetry integration**: Embed platform state in per-window NDJSON telemetry
  - **Governor enforcement**: Set + verify CPU governor before benchmark

#### Recommendation
- [x] **Reuse**: ftrace power events (Linux ARM), tegrastats (Jetson), sysfs polling (fallback)
- [x] **Adapt**: Tracepoint-based methodology where available, polling where not
- [x] **Innovate**: Cross-platform abstraction layer (`get_cpu_freq()`, `get_thermal_state()`)
- **Integration**: Thermal capture exists (telemetry.c:517-527); **DVFS/governor pending** 🟡

---

### 8. Latency Distribution (P50/P95/P99)

#### Existing Tools
- **MLPerf**: P90 (single-stream), P99 (server)
- **TensorRT**: Median latency + throughput
- **Benchmark literature** (Dean & Barroso 2013): "The Tail at Scale"—P99.9 can be 150× median

#### Methodology in Literature
**MLPerf statistical confidence**:
- Minimum sample counts for confidence intervals (e.g., 270K for 99% CI, 0.05% margin)
- Early stopping: Allow smaller runs with adjusted percentile estimate

**Reporting standard** (industry):
- Single-value throughput benchmarks considered insufficient
- Tail latencies (P95, P99, P99.9) critical for SLA guarantees

#### Gap Analysis
- **What exists**: Established percentile methodology (P90/P95/P99), statistical confidence formulas
- **What's missing for CORTEX**:
  - **Per-window telemetry → distribution aggregation**: Kernel logs per-window latency, analyzer computes P50/P95/P99
  - CDF plots, latency histograms

#### Recommendation
- [x] **Adopt**: MLPerf percentile methodology, statistical confidence principles
- [x] **Adapt**: "Tail at Scale" reporting conventions (P50/P95/P99 standard)
- [x] **Innovate**: Window-based signal processing context (not request-based like MLPerf)
- **Integration**: `calculate_statistics()` computes P50/P95/P99, `plot_cdf_overlay()` exists ✅

---

### 9. Deadline Analysis

#### Existing Tools
- **LTTng snapshot mode**: Anomaly-triggered trace capture
- **ros2_tracing**: Deadline miss detection for ROS 2 systems
- **WCET analysis**: Tracealyzer, Gliwa T1, research tools (semi-Markov chains)

#### Methodology in Literature
**Real-time systems approach**:
- Define deadline (e.g., 50ms for BCI feedback loop)
- Log `end_timestamp - start_timestamp > deadline` as miss
- Compute miss rate: `misses / total_windows`

**WCET estimation** (From Tracepoints to Timeliness, arXiv 2025):
- Timed tracepoints → semi-Markov chain → probabilistic WCET
- Alternative to static analysis (overly conservative)

#### Gap Analysis
- **What exists**: Telemetry field `deadline_missed` (scheduler.c:476-479), miss rate calculation
- **What's missing for CORTEX**:
  - **Formal validation**: `cortex check-deadline --spec requirements.yaml` (compare measured vs spec)
  - **Root cause hints**: Correlate deadline misses with platform state (thermal throttle? DVFS drop?)
  - WCET estimation (probabilistic, trace-based)

#### Recommendation
- [x] **Adopt**: LTTng anomaly-detection pattern, real-time miss rate calculation
- [ ] **Adapt**: WCET estimation methodology (defer—research-stage)
- [x] **Innovate**: Spec-based validation (`cortex check-deadline`), platform correlation
- **Integration**: `deadline_missed` telemetry exists; **formal validation missing** 🟡

---

### 10. Comparative Analysis (Diff Reports)

#### Existing Tools
- **MLCommons**: Compare submissions across vendors/platforms
- **CI performance regression tools**: Benchmark GitHub Action, Bencher.dev, pytest-benchmark
- **Statistical significance**: T-tests, Mann-Whitney U for latency distributions

#### Methodology in Literature
**Regression detection**:
- Baseline run (e.g., main branch) vs candidate run (PR)
- Statistical test: Is latency difference significant? (p < 0.05)
- Alert on degradation > threshold (e.g., P95 latency +10%)

**Comparative visualizations**:
- Side-by-side CDF plots
- Difference heatmaps (kernel A vs B across percentiles)

#### Gap Analysis
- **What exists**: `plot_latency_comparison()`, `plot_cdf_overlay()` show multiple kernels
- **What's missing for CORTEX**:
  - **Formalized diff reports**: `cortex compare baseline.csv candidate.csv`
  - Baseline storage (e.g., `results/baselines/main/kernel_name.csv`)
  - Regression detection (automated or CLI-driven)

#### Recommendation
- [x] **Adapt**: CI regression detection patterns, statistical significance testing
- [x] **Innovate**: `cortex compare` CLI command, baseline management
- **Integration**: Plotting exists; **formal diff command missing** 🟡

---

### 11. Diagnostic Framework (Compute vs Memory vs Platform)

#### Existing Tools
- **Roofline model**: Intel Advisor, NVIDIA Nsight Compute, LIKWID, ERT
- **Performance counters**: perf (Linux), Instruments (macOS), VTune (Intel)

#### Methodology in Literature
**Roofline model**:
- **Arithmetic intensity** (AI): FLOPs / bytes transferred
- **Machine balance**: Peak FLOPS / peak bandwidth
- If AI < balance → memory-bound; if AI > balance → compute-bound

**Automated tools**:
- **Intel Advisor**: Auto-roofline, suggests SIMD vs memory optimization
- **Nsight Compute**: Kernel roofline analysis, bottleneck attribution

**Model-based attribution** (CORTEX approach):
1. Static analysis → theoretical FLOPs, memory accesses
2. Device spec → peak FLOPS, bandwidth, cache size
3. Measured latency (ground truth)
4. Roofline comparison → attribute time to compute/memory/platform

#### Gap Analysis
- **What exists**: Roofline tools for GPU/CPU, performance counter APIs
- **What's missing for CORTEX**:
  - **Automated static analysis**: Parse kernel C code → extract operation count, memory access pattern
  - **Device spec database**: Per-platform peak FLOPS, bandwidth (e.g., Snapdragon 888: X GFLOPS, Y GB/s)
  - **Model integration**: Combine static + dynamic + spec → attribution report

#### Recommendation
- [x] **Adopt**: Roofline model methodology, compute/memory/platform trichotomy
- [x] **Adapt**: Automated tools insight (Intel Advisor, Nsight Compute)
- [x] **Innovate**: Lightweight static analysis for C kernels, model-based attribution CLI
- **Integration**: SE-5 capability **not implemented** (Tier 3) ❌

---

### 12. Pipeline Composition

#### Existing Tools
- **PlantD**: Data pipeline latency/throughput measurement (open-source)
- **LLM serving**: Multi-stage inference (prefill → decode) with TTFT, ITL, end-to-end latency
- **CPU pipelining**: Latency vs throughput tradeoffs in multi-stage execution

#### Methodology in Literature
**PlantD approach**:
- Instrument each pipeline stage
- Measure: throughput, latency, latency-at-throughput
- Per-stage telemetry → end-to-end attribution

**LLM serving** (E2E modeling paper):
- Lack of "systematic methodology for navigating end-to-end co-design space"
- Multi-stage interactions: isolated decisions → propagate through pipeline
- Metrics: TTFT (time to first token), end-to-end latency, intertoken latency

#### Gap Analysis
- **What exists**: Per-kernel measurement in CORTEX (run bandpass, then CAR, then CSP separately)
- **What's missing for CORTEX**:
  - **Run-config schema**: Define pipeline (bandpass → CAR → CSP → classifier)
  - **Stage telemetry**: Per-stage latency, inter-stage buffering overhead
  - **End-to-end validation**: Oracle for full pipeline (not just individual kernels)

#### Recommendation
- [ ] **Adapt**: PlantD per-stage instrumentation, LLM serving metrics (TTFT analog: "time to first feature vector")
- [x] **Innovate**: Run-config YAML schema, pipeline orchestration engine, stage-aware telemetry
- **Integration**: SE-9 capability **not implemented** (Tier 1 priority) ❌

---

## Final Synthesis

### Reuse List (Direct Integration)

| Tool/Library | Purpose | Integration Point |
|--------------|---------|-------------------|
| **perf/ftrace** | Platform-state capture (CPU freq, thermal) | Telemetry module (Linux only) |
| **stress-ng** | Load profile generation | Harness spawns subprocess for `medium`/`heavy` profiles |
| **Paramiko** | SSH transport | Device adapter (already integrated) |
| **ADB CLI** | Android device deployment | Planned device adapter (USB transport) |
| **pandas/matplotlib** | Latency analysis, plotting | Analyzer CLI (already integrated) |

### Methodology Adoption List

| Methodology | Source | CORTEX Application |
|-------------|--------|-------------------|
| **P90/P95/P99 percentile latency** | MLPerf Inference | `calculate_statistics()`, telemetry aggregation |
| **Statistical confidence (early stopping)** | MLPerf Inference Rules | Minimum sample counts for valid runs |
| **Warmup-then-measure** | SPEC CPU, benchmark best practices | `warmup_seconds` config, per-plugin warmup |
| **Oracle validation (rtol/atol)** | SciPy/NumPy testing conventions | `cortex validate`, rtol=1e-5 |
| **Roofline model** | Berkeley/Intel | Diagnostic framework (SE-5, Tier 3) |
| **Calibration workflow** | BCILAB, BCI literature | `cortex calibrate`, `.cortex_state` serialization |
| **Synthetic EEG generation** | EEGdenoiseNet, SEED-G | `cortex generate`, parameterized datasets |
| **Deadline miss detection** | LTTng, real-time systems | Telemetry `deadline_missed` field |
| **Timed tracepoints** | LTTng low-overhead design | Telemetry minimal-context philosophy |

### Innovation List (Novel Development)

| Capability | Innovation | Rationale |
|-----------|-----------|-----------|
| **Oracle validation framework** | Automated C-kernel ↔ Python-oracle comparison | No existing BCI tool provides this |
| **Platform-state control** | Cross-platform abstraction for DVFS/thermal capture | MLPerf doesn't standardize; Linux-only tools insufficient |
| **Calibration ABI** | `.cortex_state` binary format for cross-language state | scikit-learn joblib is Python-only |
| **Unified transport abstraction** | Factory pattern (SSH, ADB, USB, FPGA) | No existing framework spans all transports |
| **Pipeline composition** | Run-config schema + stage telemetry | BCI tools run kernels in isolation, not pipelines |
| **Window-based latency measurement** | Per-window telemetry for signal processing | MLPerf measures per-request (DNN inference context) |
| **Declarative load profiles** | `idle/medium/heavy` → platform-specific stress-ng mapping | stress-ng requires manual parameter selection |
| **Self-describing datasets** | `spec.yaml` embedded in dataset directories | Synthetic EEG tools lack metadata standards |

### Architecture Implications

#### 1. **Layer Separation Validated**
Research confirms CORTEX's architecture is sound:
- **Primitives** (kernels, datasets, configs): Reusable across use cases ✅
- **SDK** (plugin API, transport protocol): Platform-agnostic interfaces ✅
- **Orchestration** (harness, telemetry): Novel integration logic ✅
- **Analysis** (Python tools): Leverage existing libraries (pandas, matplotlib) ✅

#### 2. **Platform Abstraction Required**
- **Linux**: perf/ftrace, stress-ng, sysfs polling
- **macOS**: Instruments, IOKit for sensors (different APIs)
- **Android**: ADB, `/sys/class/thermal/`, governor via shell
- **Windows**: QueryPerformanceCounter, WMI for freq/thermal

**Recommendation**: Create `platform_info.h` abstraction layer with per-OS implementations.

#### 3. **Telemetry Must Expand**
Current telemetry captures:
- ✅ Per-window latency_us, deadline_missed
- ✅ Thermal (Linux: thermal_zone0/temp)
- 🟡 CPU frequency (not captured)
- ❌ Governor state (not captured)
- ❌ Pipeline stage attribution (not supported)

**Action**: Add `cpu_freq_mhz`, `governor` fields to telemetry struct.

#### 4. **CLI Expansion Needed**
**Existing**: `cortex run`, `calibrate`, `validate`, `generate`, `analyze`
**Needed (Tier 1-2)**:
- `cortex compare <baseline> <candidate>` — diff reports
- `cortex check-deadline --spec requirements.yaml` — formal deadline validation
- `cortex diagnose <run-dir>` — roofline-based bottleneck attribution (Tier 3)
- `cortex pipeline <run-config.yaml>` — multi-stage orchestration (Tier 1)

#### 5. **Device Adapter Expansion**
**Existing**: SSH (Paramiko)
**Roadmap**:
- **USB**: libusb for direct device communication (HE persona)
- **ADB**: subprocess wrapper for Android (SE persona, SE-7)
- **FPGA**: JTAG/UART via OpenOCD (HE persona, Spring 2026)

**Unified interface**: `AdapterFactory.create(uri)` → auto-detect transport type.

#### 6. **Integration Opportunities**

##### **Short-Term (v0.6.0)**
1. **Platform-state capture completion**: Add CPU freq, governor to telemetry (integrate perf/ftrace, sysfs)
2. **Comparative analysis CLI**: `cortex compare` command with baseline storage
3. **Formal deadline validation**: `cortex check-deadline` against spec files

##### **Medium-Term (v0.7.0)**
4. **Pipeline composition**: Run-config schema + multi-kernel orchestration
5. **ADB/USB adapters**: Android/embedded device support
6. **Load profile enforcement**: Auto-spawn stress-ng for `medium/heavy` configs

##### **Long-Term (v1.0+)**
7. **Diagnostic framework**: Static analysis + roofline model attribution
8. **WCET estimation**: Trace-based probabilistic WCET
9. **FPGA adapters**: Zynq, Artix-7 support for HE persona

---

## Conclusion

**Key Insight**: CORTEX's value lies not in building new low-level tools (perf, stress-ng, ADB already exist), but in **intelligent integration** of correctness validation (oracles), latency measurement (MLPerf methodology), and platform-effect awareness (Linux tracing)—a combination absent in both BCI tools (accuracy-only) and ML benchmarking tools (no oracles, weak platform control).

**Strategic Recommendation**:
- **Reuse aggressively** for well-established components (platform measurement, deployment transports)
- **Adapt proven methodologies** from adjacent domains (MLPerf percentiles, roofline model)
- **Innovate at integration points** (oracle orchestration, pipeline composition, cross-platform abstraction)

This positions CORTEX as the **first deployment-grade BCI benchmarking framework**, bridging the documented gap between offline algorithm development (MOABB) and production-ready edge inference.

---

## References

### BCI Tools
- BCI2000 latency measurement: PMC3161621
- MOABB: "trustworthy algorithm benchmarking for BCIs" (Jayaram 2018)
- Calibration workflows: "Towards Zero Training for BCIs" (PLOS One 2008)

### ML Inference
- MLPerf Inference Rules: github.com/mlcommons/inference_policies
- nn-Meter: "Towards Accurate Latency Prediction of DNN Inference" (MobiSys 2021)
- Yang et al.: "Latency Variability of DNNs for Mobile Inference" (arXiv 2020)

### Systems
- stress-ng: kernel.org/doc/html/latest (Ubuntu wiki)
- perf/ftrace: kernel.org/doc/html/latest/trace/
- Perfetto: perfetto.dev/docs/data-sources/cpu-freq

### Real-Time
- LTTng real-time latencies: lttng.org/blog/2016/01/06/
- WCET via tracepoints: "From Tracepoints to Timeliness" (arXiv 2025)

### Deployment
- Ansible IoT: redhat.com/blog/iot-edge-ansible-automation
- ADB automation: UL Benchmarks documentation

### Diagnostics
- Roofline model: "Roofline: An Insightful Visual Performance Model" (Berkeley)
- Intel Advisor: intel.com/docs/advisor/roofline-analysis

### Pipeline
- PlantD: "Performance, Latency ANalysis for Data Pipelines" (arXiv 2025)
- LLM multi-stage: "End-to-End Modeling for LLM Serving" (arXiv 2025)
