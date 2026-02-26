## 3. CORTEX System Design

Sections 1 and 2 established the BCI deployment problem and the five methodological principles that any benchmarking framework must satisfy. This section presents the system that embodies those principles: its goal, capabilities, architecture, and interface contracts. Every capability traces back to the principles and user stories it enables.

### 3.1 Goal

Equip software engineers deploying BCI kernels with CLI tools and automated reports to quantitatively analyze and understand latency bottlenecks (compute, memory, and I/O) in individual kernels and complete pipelines on edge devices. The reports will provide full latency distributions, latency decomposition, possible platform state impact on the benchmarking, and ensure numerical correctness as a prerequisite.

| Term | Definition |
|------|-----------|
| **Researchers** | Software engineers deploying BCI kernels (primary focus this semester) |
| **Tools** | CLI and automated quantitative reports |
| **Understand** | Quantitative results interpretable by the researcher without a prescriptive workflow |
| **Bottlenecks** | Latency attributed to compute, memory, and I/O; includes platform state for correlation, flags susceptibility to platform effects, and provides per-kernel breakdowns for pipelines |
| **Performance** | Numerical correctness (prerequisite) and latency (primary metric) |
| **Algorithms / Pipelines** | Kernel as the fundamental unit; composable into sequential or parallel chains |
| **Specific Devices** | Edge compute devices where BCI kernels are practically deployed (laptop, mobile, embedded) |
| **Latency** | Full distribution (P50/P95/P99); crucial for real-time systems where failure occurs at the tail, not the mean |

### 3.2 Design Philosophy

CORTEX's architecture follows Butler Lampson's STEADY principles for system design, adapted to the specific constraints of BCI benchmarking infrastructure.

| Principle | CORTEX Implementation | Rationale |
|-----------|----------------------|-----------|
| **Simplicity** | Minimal 3-function C ABI | `init`, `process`, `teardown` with no external runtime requirements. Any C compiler on any platform can build a kernel. |
| **Timeliness** | Working infrastructure first | Measurement capability delivered before analysis, analysis before diagnostics. Each layer usable independently. |
| **Efficiency** | Zero-allocation hot path | `process()` is hermetic: no malloc, no syscalls, no I/O. Measurement overhead characterized at 1µs. |
| **Adaptability** | Primitive-based architecture | Kernels, configs, datasets, and device adapters are independently versioned, single-responsibility components. |
| **Dependability** | Oracle validation as gate | SciPy-based correctness verification structurally precedes performance measurement. Incorrect kernels cannot produce benchmark results. |
| **Yieldingness** | Intuitive CLI surface | `cortex pipeline`, `cortex run`, `cortex analyze`—complete workflow in three commands. |

### 3.3 Architecture

#### 3.3.1 Primitives Model

CORTEX is built on a primitives-based architecture inspired by Amazon's service-oriented design philosophy: small, independently deployable components with well-defined interfaces that compose into larger workflows. Three primitive types form the foundation:

**Kernel Primitives** are self-contained directories containing a C implementation of the plugin ABI, a Python oracle for validation, a `spec.yaml` with metadata, a README, and a Makefile. They are versioned immutably at `primitives/kernels/v{version}/{name}@{dtype}/`. Each kernel is a single-responsibility signal-processing operation (e.g., bandpass filter, CAR, Goertzel, FFT, Welch PSD).

**Run-Config Primitives** are YAML files specifying dataset path and format, real-time deadlines, load profiles (idle/medium/heavy), CPU governor settings, sample rate, and window parameters. They live in `primitives/configs/` (not yet versioned like kernels). A run-config captures every parameter needed to reproduce an experiment except the kernel and device.

**Device Adapters** abstract the target hardware behind a uniform interface contract: accept a kernel, invoke `process()`, and return timing telemetry. Implementations include native (local execution), remote (SSH/UART/TCP to embedded devices), and simulator (cycle-accurate models calibrated against real hardware). Each adapter declares its timing resolution, controllable parameters, communication latency, and whether it operates in real-time or simulated-time mode.

> **Key Insight:** kernel + run-config + device-adapter = one reproducible experiment. Changing any single primitive while holding the others constant directly enables P3 (single-variable isolation). This composability is what makes CORTEX a framework rather than a collection of scripts.

#### 3.3.2 Execution Engine

The execution engine orchestrates benchmarking through four components arranged in a pipeline. The **Harness** is the top-level orchestrator: it loads the kernel plugin via `dlopen`, parses the YAML run-config, configures the execution environment, supervises the benchmark run, and collects telemetry. The **Replayer** streams EEG data at the configured sample rate, managing synthetic load profiles and enforcing timing cadence—windows arrive at constant rate regardless of kernel execution time, inherently avoiding coordinated omission artifacts. The **Scheduler** manages windowing (window size W, hop size H), deadline tracking, and CPU affinity. The **Kernel Plugin** executes `process()` on each window and returns results for oracle comparison.
```
Execution Engine Architecture

HARNESS (orchestrator)
    ├── load plugin via dlopen
    ├── parse YAML config
    ├── configure execution environment
    ├── supervise execution
    └── collect telemetry
            │
    ┌──────┴──────┐
    ▼              ▼
REPLAYER       SCHEDULER
- stream @ Fs     • windows: W, H
- manage load     • deadlines
- timing cadence  • CPU affinity
                       │
                       ▼
               KERNEL PLUGIN
               • process(W × C window)
```

Sequential execution is enforced: kernels run one at a time to ensure measurement isolation. Parallel execution would introduce cache contention and scheduler interference that degrades reproducibility.

Telemetry is captured as per-window timestamps (release, start, end, deadline) exported to NDJSON/CSV, enabling post-hoc analysis with standard data tools. Each record includes thermal state and (when available) CPU frequency, providing the temporal correlation required by P4.

#### 3.3.3 Ground-Truth-First Philosophy

CORTEX follows a ground-truth-first measurement philosophy: results are collected from real hardware executing real kernels on real data. The device adapter abstraction supports simulators and emulators alongside physical devices—this is not an anti-simulation stance, but a calibration hierarchy. Simulators are validated against real hardware measurements, not the reverse. The Idle Paradox itself demonstrates why this ordering matters: the ~50% latency degradation from DVFS policies is precisely the kind of platform effect that simulators do not model because it arises from undocumented, proprietary power management heuristics.

### 3.4 Interface Contracts

CORTEX defines four interface contracts. These are the stable surfaces that all extensions (new kernels, new devices, new transports) must conform to.

#### 3.4.1 Kernel Plugin ABI

Every kernel implements three required C functions and one optional function, loaded dynamically via `dlopen`. This minimal surface is the foundation of cross-platform portability—any system with a C compiler and dynamic linker can host CORTEX kernels.

| Function | Contract | Signature Notes |
|----------|----------|-----------------|
| `cortex_init()` | Allocate state, precompute constants, load calibration parameters. May allocate memory, perform file I/O, and execute arbitrary setup. Called once per benchmark run. | Returns opaque state pointer. Errors reported via return code. |
| `cortex_process()` | Process one window of EEG data. **Hermetic:** zero allocations, zero syscalls, zero I/O. This is the measured function—any violation of hermeticity invalidates timing results. | Accepts state pointer + input buffer + output buffer. Returns status code. |
| `cortex_teardown()` | Free allocated state, release resources. Called once after all windows are processed. | Accepts state pointer. No return value requirements. |
| `cortex_calibrate()` *(optional)* | Train kernel on calibration data and serialize learned parameters to a binary state file. Called offline before benchmarking; the resulting state is loaded by `cortex_init()` at benchmark time. | Accepts training data + output path. Returns status code. Not all kernels require calibration. |

The two-phase measurement pattern (FFTW-style init/execute separation) ensures that one-time setup costs—allocation, plan creation, calibration loading—are excluded from per-invocation timing. In production, `init()` is amortized over millions of windows; `process()` latency is what determines real-time safety. The optional `calibrate()` function enables trainable kernels (ICA, CSP) to serialize learned parameters offline, which `init()` loads at benchmark time.

#### 3.4.2 Device Adapter Contract

Device adapters abstract heterogeneous hardware behind a uniform frame-based protocol. Communication between the harness (host) and the adapter (device) follows a session lifecycle with five frame types:

| Frame Type | Contract |
|-----------|----------|
| **HELLO** | Capability exchange. The adapter declares its timing resolution, controllable parameters, supported dtypes, and real-time vs. simulated-time mode. The harness confirms protocol version compatibility. |
| **CONFIG** | Kernel selection and initialization. The harness specifies which kernel to load, provides calibration state (if any), and declares input/output dimensions. The adapter loads the kernel via `dlopen` (native) or receives a pre-built binary (remote). |
| **ACK** | Handshake confirmation. The adapter confirms successful kernel loading and reports output buffer dimensions. Benchmark measurement begins after ACK. |
| **WINDOW_CHUNK** | Data transfer. The harness sends one window of EEG data (W × C samples). Large windows are chunked at 8KB boundaries with CRC32 integrity checks per chunk. |
| **RESULT** | Timing telemetry. The adapter returns the kernel's output buffer plus per-window timing metadata (`start_ns`, `end_ns`) and available platform state (thermal zone temperature). The harness records these in the telemetry log. |

Current adapter implementations include **Native** (local `dlopen`, 1µs overhead), **TCP** (BSD sockets + `TCP_NODELAY`, ~180µs localhost / ~1.2ms LAN), and **Serial** (termios 8N1, ~12ms at 115200 baud). The SSH deployer orchestrates remote setup: passwordless SSH verification, rsync with BCI-aware excludes, remote build, optional on-device oracle validation, and adapter daemon launch.

#### 3.4.3 Transport Protocol

Remote device adapters communicate via a custom binary protocol designed for embedded constraints. The protocol uses a 16-byte header (magic `"CRTX"`, version, type, length, CRC32) with three-phase handshake: HELLO (capability exchange) → CONFIG (kernel selection, calibration state) → ACK (output dimensions). Large windows are chunked at 8KB boundaries. The implementation is ~1,500 lines of C (protocol + CRC + error handling + chunking) with zero external dependencies, embeddable on bare-metal STM32 targets. URI-driven transport selection (`local://`, `tcp://`, `serial://`) enables the same protocol code across all transports.

#### 3.4.4 Oracle Interface

Each kernel's `oracle.py` implements a Python reference producing the same output as the C kernel for identical input. The validation pipeline loads real EEG data, runs both the C kernel and the Python oracle on identical windows, and compares outputs with configurable tolerance (default: `rtol=1e-5`, `atol=1e-6`; relaxed for frequency-domain kernels like Welch PSD and FFT). Validation supports `--calibration-state` for trainable kernels (ICA, CSP) and runs structurally before any benchmark—correctness precedes performance (P2).