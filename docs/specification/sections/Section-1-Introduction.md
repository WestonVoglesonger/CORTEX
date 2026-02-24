# Section 1: Introduction

## 1. Introduction

### 1.1 Purpose and Scope

CORTEX (Common Off-implant Runtime Test Ecosystem for BCI kernels) is a production-grade benchmarking framework designed to measure, validate, and optimize the performance of Brain-Computer Interface (BCI) signal processing kernels under real-time constraints. This specification defines the complete technical architecture, wire protocols, and measurement methodology necessary to implement or extend CORTEX systems across multiple platforms and deployment contexts.

#### What CORTEX Does

CORTEX provides an integrated ecosystem for:

1. **Validating kernel correctness** through automated oracle validation against SciPy/MNE reference implementations prior to performance measurement
2. **Measuring real-time performance** including latency distributions (P50/P95/P99), jitter, throughput, and deadline misses under controlled platform conditions
3. **Managing composable signal processing primitives** — kernels, datasets, and configurations — using an AWS-inspired building-blocks philosophy
4. **Supporting multiple execution platforms** including local development machines, remote servers via TCP, and embedded devices via UART
5. **Providing device-agnostic timing** through standardized adapters that abstract platform-specific measurement mechanics while preserving latency accuracy

The benchmark harness orchestrates a systematic workflow:

```
Dataset (immutable primitive)
    ↓
Replayer (streams H-sized chunks at real-time cadence)
    ↓
Scheduler (buffers into W-sized windows, enforces deadlines)
    ↓
Device Adapter (routes to local/remote/embedded plugin)
    ↓
Plugin (cortex_process(): C kernel implementation)
    ↓
Telemetry (captures per-window timing, deadline compliance, statistics)
    ↓
Analysis (percentiles, plots, regression detection)
```

#### What CORTEX Does NOT Do

CORTEX is not:

- **A statistical inference framework** — Kernels implement signal processing algorithms (filtering, feature extraction, dimensionality reduction), but do not perform machine learning training or inference. Exception: trainable kernels (e.g., ICA, CSP) support offline calibration via `cortex_calibrate()`, decoupled from the measurement pipeline.
- **A hardware design tool** — CORTEX measures kernel performance on existing hardware; it does not optimize silicon design, allocate cache, or generate RTL.
- **A clinical system** — CORTEX is a research and development tool for algorithm validation and optimization. It is not intended for direct clinical use and does not implement the safety/validation requirements of medical devices.
- **A real-time operating system** — While CORTEX enforces deadline semantics (e.g., SCHED_FIFO/RR on Linux), it is designed for controlled benchmark environments, not full-system RT guarantees.
- **A neural network library** — CORTEX does not provide deep learning training, inference, or optimization primitives. It focuses on classical signal processing.

---

#### Core Capabilities

CORTEX supports:

1. **Eight production kernels** (v1, float32):
   - `car` — Common Average Reference (spatial filtering, multi-channel)
   - `notch_iir` — 60 Hz line noise removal (IIR filter, configurable f0/Q)
   - `bandpass_fir` — 8-30 Hz passband (FIR filter, 129 taps)
   - `goertzel` — Spectral bandpower extraction (Goertzel algorithm, configurable bands)
   - `welch_psd` — Power spectral density estimation (Welch's method, configurable FFT/overlap)
   - `ica` — Independent Component Analysis (artifact removal, trainable with offline calibration)
   - `csp` — Common Spatial Patterns (motor imagery classification, trainable with offline calibration)
   - `noop` — Identity function (harness overhead baseline for measurement validation)

2. **Cross-platform execution**:
   - macOS (arm64, x86_64) with `.dylib` plugins
   - Linux (x86_64, arm64) with `.so` plugins
   - Remote execution via TCP adapter
   - Embedded systems via UART adapter (STM32, Jetson Orin, future support)

3. **Real-time scheduling**:
   - Deadline enforcement with window-level timing collection
   - SCHED_FIFO/RR priority support (Linux)
   - Best-effort scheduling (macOS)
   - Quantified deadline miss reporting

4. **Trainable kernel support** (ABI v3):
   - Offline calibration via `cortex_calibrate()` with automatic state serialization
   - Support for algorithms requiring batch training (ICA, CSP)
   - Pre-trained state loading on init without blocking computation

5. **Comprehensive telemetry**:
   - Per-window latency (microsecond granularity)
   - Full latency distributions (percentiles, not means)
   - Deadline miss tracking
   - NDJSON and CSV output formats
   - Automatic regression detection across runs

6. **Oracle validation**:
   - Numerical correctness verification before performance measurement
   - SciPy/MNE reference implementations for all kernels
   - Tolerance-based comparison (1e-5 for float32)
   - Automatic validation in `cortex pipeline` workflow

---

### 1.2 Target Personas

This specification is written for five primary audiences:

#### 1.2.1 BCI Algorithm Researchers

**Goal**: Validate new signal processing algorithms and benchmark their performance.

**Context**: Researchers develop novel kernels (filters, decomposition methods, feature extractors) and need to quantify latency, scalability, and numerical accuracy. They may prototype in Python/MATLAB and require tools to measure C implementations on diverse hardware.

**Specification sections most relevant**:
- Section 3 (Plugin ABI) — For implementing custom kernels
- Section 5 (Configuration Schema) — For setting runtime parameters
- Guides: Adding Kernels, Synthetic Datasets

**Critical constraints for this persona**:
- Kernels **MUST** be hermetic (zero external I/O during `cortex_process()`)
- Kernels **MUST** pass oracle validation before performance numbers are trusted
- Trainable kernels **MUST** separate calibration (offline, unbounded time) from inference (online, real-time deadline)

#### 1.2.2 Embedded Systems Developers

**Goal**: Deploy BCI kernels on resource-constrained hardware (ARM Cortex-M7, Jetson Nano) and measure latency under realistic operating conditions.

**Context**: Developers optimize kernels for low power, small RAM, and predictable latency. They use device adapters to run benchmarks on remote or embedded targets without complex cross-compilation workflows.

**Specification sections most relevant**:
- Device Adapter API (future Section 7) — For interfacing embedded hardware
- Section 6 (Telemetry Format) — For analyzing timing under load
- Guides: Device Adapter Setup, Remote Execution

**Critical constraints for this persona**:
- Sequential kernel execution (never parallel) to maintain measurement reproducibility
- Device adapters **MUST NOT** allocate heap memory during `cortex_process()`
- Telemetry transport **MUST** support low-bandwidth links (serial, rate-limited TCP)

#### 1.2.3 System Integrators

**Goal**: Assemble complete BCI acquisition → processing → output pipelines using CORTEX kernels as components.

**Context**: Integrators select kernel combinations, configure parameters, and compose them into real-time systems. They need clear APIs, predictable performance, and reproducible configurations.

**Specification sections most relevant**:
- Section 5 (Configuration Schema) — For declaring kernel combinations and dataset sources
- Wire Protocol (Section 4) — For understanding adapter communication
- Guides: System Architecture, Configuration Management

**Critical constraints for this persona**:
- Configurations **MUST** be version-controlled alongside kernel implementations
- All primitives (kernels, datasets, configs) **SHOULD** be immutable after release
- Performance characteristics **MUST** be deterministic (no randomness in telemetry)

#### 1.2.4 Performance Engineers

**Goal**: Optimize kernel implementations for specific hardware targets and measure the impact of optimizations.

**Context**: Engineers profile kernels, identify bottlenecks, apply algorithmic or micro-level optimizations, and quantify improvement. They run benchmarks repeatedly across hardware configurations and compare telemetry.

**Specification sections most relevant**:
- Section 6 (Telemetry Format) — For extracting latency percentiles and analyzing distributions
- Validation Studies (in appendix) — For understanding measurement methodology and known pitfalls (Idle Paradox, Schedutil Trap)
- Guides: Profiling, DVFS Management

**Critical constraints for this persona**:
- Performance claims **MUST** include full latency distributions, not just means
- Harness overhead (1 µs baseline) **MUST** be subtracted when comparing kernels
- CPU frequency and governor state **MUST** be fixed to ensure reproducible measurements

#### 1.2.5 Measurement Methodology Researchers

**Goal**: Validate CORTEX's measurement accuracy and extend the framework with new validation studies.

**Context**: Researchers evaluate whether CORTEX's telemetry correctly reflects real-time behavior, identify systematic biases, and propose improvements to the methodology.

**Specification sections most relevant**:
- All sections (this is a comprehensive reference)
- Validation Studies — DVFS Paradox, Schedutil Trap, Harness Overhead experiments
- Architecture docs — Scheduler design, timing collection strategy

**Critical constraints for this persona**:
- All measurements **MUST** be reproducible across independent runs
- Statistical analysis **MUST** account for platform-specific effects (DVFS, CPU scheduling, memory bandwidth)
- No measurement technique is valid until empirically validated on real hardware

---

### 1.3 Design Rationale

CORTEX's architecture embodies several fundamental design principles that emerged from production neurotechnology research requirements:

#### 1.3.1 Two-Phase Measurement: Validation Then Performance

**Principle**: Correctness validation precedes performance measurement.

**Rationale**: A fast algorithm that computes wrong results is useless. CORTEX enforces a rigid workflow: (1) validate kernel output against Python oracle within numerical tolerance (1e-5 for float32), (2) measure latency distribution.

**Implementation**:
```bash
cortex pipeline      # Full workflow: validate → benchmark → analyze
cortex validate      # Validation only (no timing measurements)
cortex run           # Benchmark only (assumes validation passed)
```

The `cortex pipeline` command is the only safe entry point for trusting performance results. Direct calls to `cortex run` skip validation and are intended only for rapid iteration *after* initial verification.

**Trade-offs**: This adds latency to the benchmark workflow (typically 5-10% overhead for oracle calls), but eliminates the risk of incorrect results masquerading as performance numbers. For BCI applications, correctness is non-negotiable.

#### 1.3.2 C Kernel Plugins with ABI Versioning

**Principle**: Kernels are compiled to binary plugins; the plugin interface is versioned and stable.

**Rationale**: BCI kernels must achieve microsecond-scale latency. Python/JavaScript interpreters introduce overhead and jitter. Compiled C kernels with fixed ABIs enable:

1. **Sub-microsecond consistency** — No garbage collection or JIT compilation overhead
2. **Hardware-specific optimization** — Inline SIMD (SSE, AVX, NEON), unrolled loops
3. **Backward compatibility** — ABI versioning allows v2 kernels to run unchanged in a v3 harness
4. **Device portability** — Same ABI on macOS, Linux, embedded STM32 (via adapters)

**ABI Constraints**: The core function signatures are frozen:
```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
void cortex_process(void *handle, const float *input, float *output, uint32_t window_count);
void cortex_teardown(void *handle);
uint32_t cortex_calibrate(void *handle, ...);  // v3+, for trainable kernels only
```

Kernels **MUST NOT** import external libraries (libfftw, liblapack, etc.) during `cortex_process()`. All math must be self-contained or use platform primitives (CBLAS, CMSIS-DSP).

**Trade-offs**: C plugins are harder to develop than Python, require compilation, and introduce platform-specific testing burden. However, the performance and reproducibility gains are essential for real-time neurotechnology.

#### 1.3.3 AWS-Style Primitives for Composability

**Principle**: Kernels, datasets, and configurations are first-class immutable artifacts.

**Rationale**: AWS primitives (EC2 images, security groups, CloudFormation templates) are versioned, immutable, and composable. CORTEX applies this philosophy:

- **Kernel primitives**: `primitives/kernels/v{version}/{name}@{dtype}/`
- **Dataset primitives**: `primitives/datasets/v{version}/{name}/`
- **Configuration templates**: `primitives/configs/{name}.yaml`

Once a primitive is released in version `v1/`, it is **immutable**. Any changes create a new `v2/` directory. This ensures:

1. **Reproducibility** — Benchmarks from 2024 use exactly the same kernels today
2. **Auditability** — Full history of changes visible in git
3. **Composability** — Users mix-and-match versions without conflicts

**Example primitive structure**:
```
primitives/kernels/v1/goertzel@f32/
├── cortex_plugin.c       # Implementation
├── cortex_plugin.h       # Public interface (copied from SDK)
├── Makefile              # Build rules
├── oracle.py             # SciPy reference for validation
└── README.md             # Documentation

primitives/datasets/v1/physionet-motor-imagery/
├── spec.yaml             # Metadata: channels, sample_rate, recordings
├── README.md             # Citation, preprocessing notes
└── converted/
    ├── S001R01.float32   # Binary data (immutable after release)
    └── S001R02.float32
```

**Trade-offs**: Immutability prevents naive bug fixes. If a kernel has a bug, the fix requires releasing `v2/`. However, this preserves scientific reproducibility — researchers can always cite which version was used.

#### 1.3.4 Sequential Execution for Measurement Isolation

**Principle**: Kernels run one-at-a-time; parallel execution is forbidden.

**Rationale**: Parallel kernel execution introduces confounding factors:

1. **CPU core contention** — Latency increases unpredictably as cores compete
2. **Memory bandwidth competition** — Multiple kernels compete for L3 cache and DRAM bandwidth
3. **Cache invalidation** — One kernel's data evicts another's, creating artificial jitter
4. **Non-reproducible results** — Timing varies based on OS scheduling, making comparisons meaningless

Running kernels sequentially eliminates these confounds. Each kernel observes consistent CPU state and full memory bandwidth.

**Constraint**: Benchmarks take longer (8 kernels × 100 repetitions = 30-60 seconds on typical hardware). This is acceptable for development and research workflows.

**Implementation**: The scheduler enforces sequential execution by:
1. Ensuring only one kernel plugin is loaded per benchmark run
2. Completing all windows for kernel A before starting kernel B
3. Collecting independent telemetry for each kernel

---

#### 1.3.5 Adaptive Oracle Validation

**Principle**: Kernel output correctness is validated before latency is measured.

**Rationale**: Performance numbers are meaningless if the algorithm is wrong. CORTEX implements a two-pass validation:

1. **Python oracle pass**: Kernel processes real-world EEG data, output compared against SciPy reference within tolerance (1e-5 for float32)
2. **Synthetic oracle pass**: Kernel processes synthetic signals (known sine waves, pink noise) with expected output verified analytically

If either pass fails, the benchmark aborts before any timing measurements. This prevents incorrect results from reaching users.

**Tolerance selection** (1e-5 for float32): Based on IEEE 754 float32 precision (~7 decimal digits). A 1e-5 relative error is acceptable for signal processing (Butterworth filters, FFTs, linear transforms) but strict enough to catch implementation bugs.

**Trade-offs**: Oracle validation adds 5-10% overhead to pipeline runtime. However, this is the only way to guarantee measurement integrity.

---

#### 1.3.6 Platform-Agnostic Timing via Device Adapters

**Principle**: Device adapters abstract platform-specific measurement mechanics.

**Rationale**: Embedding CORTEX on STM32 microcontrollers, Jetson embedded systems, and x86 servers requires different interfaces (UART vs TCP vs local socketpair), but the timing collection logic should be identical.

Device adapters provide a **single wire protocol** (Section 4) that works across all platforms:

```
Harness (C, on dev machine)
    ↓
Device Adapter (platform-agnostic wire protocol: send config, kernel.so, dataset)
    ↓
Adapter Implementation (platform-specific: tcp_adapter, serial_adapter, local_adapter)
    ↓
Kernel Execution (same C ABI across all platforms)
    ↓
Telemetry (wire protocol: return timing, deadline misses, exit code)
```

This design allows:
1. Develop algorithms on laptop (local adapter)
2. Validate on Jetson (TCP adapter)
3. Deploy on STM32 (UART adapter)

Without adapters, each platform would require custom build systems and test scripts.

---

### 1.4 Document Structure

This specification is organized into six sections covering progressively lower-level details:

#### Section 1: Introduction (this document)
- Purpose, scope, target personas
- Design rationale and principles
- Overview of CORTEX philosophy

#### Section 2: System Architecture (future)
- High-level system design (harness, replayer, scheduler, telemetry)
- Component interactions and data flow
- Real-time scheduling strategy
- Measurement methodology and sources of error

#### Section 3: Plugin ABI Specification
- ABI versioning and negotiation
- Core kernel functions: `cortex_init()`, `cortex_process()`, `cortex_teardown()`, `cortex_calibrate()`
- Data types and structures
- Return value semantics
- Error handling

#### Section 4: Wire Protocol Specification
- Device adapter communication protocol
- Message formats (request/response)
- Kernel loading and execution
- Telemetry transmission
- Transport layer (TCP, UART, socketpair)

#### Section 5: Configuration Schema
- YAML structure for run configurations
- Kernel parameters and type system
- Dataset specification
- Scheduling constraints (window size, deadline)
- Telemetry options

#### Section 6: Telemetry Format
- NDJSON per-window telemetry structure
- CSV aggregated output format
- Statistical metrics (percentiles, jitter)
- Analysis output (plots, regression reports)
- Deadline miss tracking

---

#### Reading Guide by Persona

**For BCI Researchers developing new kernels**:
1. Read Section 1 (this document) for context
2. Study Section 3 (Plugin ABI) — this is your primary reference
3. Browse Section 5 (Configuration) to understand parameter passing
4. Refer to guides: `docs/guides/adding-kernels.md`

**For Embedded Systems Developers**:
1. Read Section 1 for motivation
2. Focus on Section 4 (Wire Protocol) — this defines adapter communication
3. Study Section 6 (Telemetry) to understand output format
4. Refer to guides: `docs/guides/device-adapter-setup.md`

**For Performance Engineers**:
1. Skim Section 1-3 for background
2. Focus on Section 6 (Telemetry Format) — the source of truth for latency numbers
3. Study validation studies for understanding measurement confounds
4. Refer to guides: `docs/guides/profiling.md`, `docs/guides/dvfs-management.md`

**For System Integrators**:
1. Read Section 1 for philosophy
2. Focus on Section 5 (Configuration Schema) — you'll spend most time here
3. Skim Sections 3-4 for API awareness
4. Refer to guides: `docs/guides/system-architecture.md`, `docs/guides/configuration-management.md`

**For Measurement Researchers**:
1. Study all sections — this is comprehensive reference material
2. Deep dive: Validation studies (DVFS Paradox, Schedutil Trap, Harness Overhead)
3. Challenge: Design your own validation study extending this methodology

---

#### Key Normative Terms (RFC 2119 Compliance)

This specification uses RFC 2119 normative keywords with standard definitions:

- **MUST**: Absolute requirement; implementations violating this are non-conformant
- **MUST NOT**: Absolute prohibition
- **SHOULD**: Strong recommendation; deviations require documented justification
- **SHOULD NOT**: Not recommended; deviations should be explicitly considered
- **MAY**: Optional; either option is acceptable

Example usage:
- "Kernels **MUST** pass oracle validation before performance measurement"
- "Adapters **SHOULD** minimize latency overhead (<1 µs)"
- "Implementations **MAY** support fixed-point quantization in future versions"

---

### 1.5 Terminology and Conventions

This section defines domain-specific terminology used throughout the specification:

| Term | Definition |
|------|-----------|
| **Kernel** | A signal processing algorithm compiled to a binary plugin (.so or .dylib) that implements the CORTEX ABI |
| **ABI** | Application Binary Interface; the contract between harness and kernel plugins (function signatures, struct layouts, return semantics) |
| **Harness** | The benchmarking orchestrator (C program) that loads kernels, replays datasets, collects timing, enforces deadlines |
| **Adapter** | Platform-specific execution layer (local, TCP, UART) that implements the wire protocol and routes kernel execution to target hardware |
| **Dataset** | An immutable collection of preprocessed EEG recordings with metadata (channels, sample rate, file format) |
| **Primitive** | A first-class immutable artifact: kernel, dataset, or configuration template, with version directories |
| **Window (W)** | A fixed number of samples processed in one `cortex_process()` call (e.g., 160 samples at 160 Hz = 1 second latency window) |
| **Hop (H)** | The stride between consecutive windows; used by replayer to maintain real-time cadence (e.g., H=80 = 50% overlap) |
| **Channels (C)** | Number of concurrent input signals (e.g., C=64 for 64-channel EEG) |
| **Deadline** | Maximum time allowed to process one window (e.g., 500 ms for real-time streaming) |
| **Idle Paradox** | Empirically observed 2-4× latency penalty on idle systems due to DVFS downclocking to minimum CPU frequency |
| **Schedutil Trap** | Empirically observed 4.5× latency penalty when using dynamic CPU scaling (Linux schedutil governor) versus fixed performance frequency |
| **Oracle validation** | Correctness verification by comparing kernel output to a reference implementation (e.g., SciPy) within numerical tolerance |
| **Telemetry** | Per-window timing data including latency, jitter, deadline miss status, exported as NDJSON or CSV |
| **Trainable kernel** | A kernel requiring offline calibration (e.g., ICA, CSP) that exports `cortex_calibrate()` for batch training and `cortex_init()` for state loading |
| **Calibration state** | Serialized learned parameters (e.g., ICA mixing matrix) stored in `.cortex_state` files |
| **Hermetic kernel** | A kernel with zero external dependencies during `cortex_process()`: no I/O, heap allocation, threading, or blocking syscalls |

---

### 1.6 Assumptions and Constraints

This specification assumes:

1. **Platform assumptions**:
   - Kernels are compiled for specific architectures (arm64, x86_64)
   - At least one CPU core is dedicated to kernel execution
   - Memory bandwidth is sufficient to saturate at >1 Gbps

2. **Measurement assumptions**:
   - Timer resolution is at least microsecond-level (true on modern platforms)
   - System clocks are stable (no CLOCK_MONOTONIC jumps or NTP adjustments during benchmarks)
   - DVFS effects are controlled via governor configuration (no dynamic scaling during measurement)

3. **Kernel assumptions**:
   - Kernels are deterministic (same input produces same output across runs)
   - Kernels are stateless or use only persistent state allocated in `cortex_init()`
   - Kernels do not allocate heap memory during `cortex_process()`

4. **Dataset assumptions**:
   - Datasets are finite and pre-recorded (infinite streaming not supported)
   - Datasets are stored in binary float32 format or MATLAB .mat files
   - Dataset sample rate is known and constant

These assumptions are documented to clarify scope and enable implementations to make consistent design choices.

---

## Summary

CORTEX is a production-grade benchmarking framework for BCI signal processing kernels. It combines:

- **Two-phase validation** (correctness before performance) for measurement integrity
- **C plugin architecture** with versioned ABI for low-latency, reproducible measurement
- **AWS-style primitives** (immutable versioned artifacts) for reproducibility and composability
- **Sequential execution** for measurement isolation
- **Device adapters** for cross-platform portability

This specification defines the complete technical framework necessary to implement CORTEX systems, extend with new kernels, and deploy on diverse hardware platforms from development laptops to embedded neurotechnology devices.

---

