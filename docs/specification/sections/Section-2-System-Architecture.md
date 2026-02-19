# Section 2: System Architecture

## 2. System Architecture

### 2.1 Overview

The CORTEX benchmarking framework implements a modular, composable architecture for measuring kernel performance on diverse execution substrates (native CPU, remote embedded systems, cloud platforms). This section defines the component model and execution flow, establishing the conceptual foundation for detailed specifications in Sections 3-6.

The architecture is organized around **four core component types**: Primitives (versioned artifacts), Harness (orchestrator), Adapter (device abstraction), and Plugin (kernel implementation). These components interact through well-defined interfaces (Plugin ABI, Wire Protocol, Configuration Schema, Telemetry Format) to enable interoperability and composability.

### 2.2 Component Model

The CORTEX component model defines four distinct abstraction layers, each with specific responsibilities and interface contracts.

#### 2.2.1 Primitives

**Definition**

Primitives are **versioned, immutable artifacts** representing reusable building blocks: kernel implementations, benchmark datasets, kernel configurations, and calibration state. Primitives are stored in the `primitives/` directory tree organized by type and version.

**Primitive Types**

**Kernels** (`primitives/kernels/v{version}/`)

A kernel primitive represents a single signal processing algorithm compiled as a shared library (`.so` on Linux/Unix, `.dylib` on macOS). Each kernel MUST:

- Export the Plugin ABI functions: `cortex_init()`, `cortex_process()`, `cortex_teardown()`, and optionally `cortex_calibrate()`
- Include a `spec.yaml` file defining:
  - Algorithm name and description
  - Input/output dimensionality (channels, sample rates, window lengths)
  - Supported data types (`FLOAT32`, `Q15`, `Q7`)
  - Parameter schema (kernel-specific algorithm parameters)
  - Calibration capabilities (if trainable)
- Be tagged with a semantic version (e.g., `v1.0.0`) allowing algorithm improvements over time

**Datasets** (`primitives/datasets/v{version}/{dataset_name}/`)

A dataset primitive represents recording(s) of real or synthetic EEG data with associated metadata. Each dataset MUST:

- Contain raw data in HDF5 or binary format
- Include a `manifest.yaml` specifying:
  - Number of channels
  - Sample rate
  - Recording duration
  - Channel labels (electrode placement, e.g., "C3", "Pz")
  - Optional class labels (for trainable kernel validation)
- Optionally contain pre-calibrated kernel state (`.cortex_state` files) for trainable kernels
- Provide deterministic data access (same dataset → same samples)

**Configurations** (`primitives/configs/v{version}/`)

A configuration primitive is a YAML file defining a complete benchmark run: which kernels to test, dataset parameters, real-time constraints, and output telemetry settings. The configuration format is specified in Section 5 (Configuration Schema).

**Calibration State** (`primitives/datasets/v{version}/{dataset}/calibration_states/`)

Pre-computed kernel parameters (e.g., ICA unmixing matrices, CSP spatial filters) stored in `.cortex_state` binary format (specified in Section 3.3.2). These files enable:

- **Reproducibility**: Same calibration state → same kernel behavior across runs
- **Offline training**: Expensive algorithms run once; state is version-controlled
- **Portability**: Pre-calibrated kernels deploy to embedded targets without re-training

**Normative Requirements**

All primitives MUST:

- Be **immutable** after publishing (version tags are permanent; modifications require new versions)
- Include **versioning** via directory (`v1/`, `v2/`) and/or file tags (e.g., `kernel-car@1.2.0.so`)
- Support **discovery** via filesystem walk (no central registry required)
- Be **self-describing** via metadata files (`spec.yaml`, `manifest.yaml`, binary headers)

Harness software MUST:

- **Not modify** primitives at runtime (primitives are read-only inputs to the benchmark)
- Support **version selection** (allow filtering benchmarks by primitive versions)
- Handle **missing primitives** gracefully with informative error messages

#### 2.2.2 Harness

**Definition**

The harness is the **benchmark orchestrator**: a C/Python application that loads configuration, instantiates plugin instances, streams data through the execution pipeline, collects timing/energy measurements, and generates reports. The harness is the top-level entry point for all benchmark runs.

**Responsibilities**

1. **Configuration Loading** (from YAML)
   - Parse benchmark specification: dataset, kernels, parameters, real-time settings
   - Validate configuration invariants (channels, sample rates, data types match across components)
   - Auto-discover kernels if not explicitly specified

2. **Adapter Lifecycle Management**
   - Spawn adapter process(es) for remote/local execution
   - Perform handshake (HELLO/CONFIG/ACK frames) to establish communication
   - Detect adapter failures (timeouts, crashes) and retry/abort accordingly

3. **Data Streaming**
   - Load dataset into memory (with optional prefetching for performance)
   - Iterate through data in windows (duration = W samples = hop length H)
   - Stream windows to adapters via wire protocol
   - Receive results and timing information from adapters

4. **Measurement Collection**
   - Record per-window latency (input transmission, kernel execution, output transmission)
   - Aggregate statistics (min, max, mean, stdev, percentiles)
   - Optionally record energy consumption (if device supports telemetry)
   - Detect outliers and anomalies

5. **Reporting**
   - Aggregate results from all kernels, datasets, and runs
   - Generate reports in NDJSON or CSV format
   - Include summary statistics and per-window logs
   - Preserve raw data for post-processing analysis

**Architecture**

The harness comprises several subcomponents:

- **Config Loader** (`src/engine/harness/config/`): YAML parser for benchmark specifications
- **Device Communication** (`src/engine/harness/device/`): Adapter lifecycle and protocol messaging
- **Data Replayer** (`src/engine/replayer/`): Reads datasets and produces windows
- **Scheduler** (`src/engine/scheduler/`): Real-time thread scheduling (FIFO, RR, deadline-based)
- **Telemetry Collector** (`src/engine/telemetry/`): Captures timing and performance metrics
- **Report Generator** (`src/engine/harness/report/`): Formats output (NDJSON, CSV, JSON)

**Normative Requirements**

A conformant CORTEX harness MUST:

- **Load configuration** from YAML files without modification (fail if config is invalid)
- **Validate dimensions** across all pipeline components before measurement begins:
  - Dataset channels/sample_rate MUST match configuration specification
  - Kernel input shape MUST match dataset dimensions
  - Kernel output shape (from ACK) MUST be compatible with next-stage kernel input
- **Stream data deterministically**: Same configuration + dataset → same sequence of windows
- **Capture timing** for every window:
  - Input transmission time (`tin`)
  - Kernel start time (`tstart`)
  - Kernel end time (`tend`)
  - Output transmission time (`tfirst_tx`, `tlast_tx`)
- **Handle failures gracefully**:
  - Adapter death → detect via timeout, log error, abort run
  - Data underrun → pause streaming, retry with backoff
  - Memory exhaustion → scale down dataset or window size, report degradation
- **Generate output** in NDJSON format (one measurement per line, valid JSON per line)

#### 2.2.3 Adapter

**Definition**

An adapter is a **device abstraction layer** that decouples the harness from specific execution targets. Adapters run as separate processes communicating with the harness via a byte-stream transport (Unix domain socket, TCP/IP, serial port, etc.). Each adapter instance represents a single kernel running on a specific device.

**Responsibilities**

1. **Transport Management**
   - Accept bidirectional byte-stream connection from harness
   - Perform version negotiation handshake
   - Encode/decode wire protocol frames
   - Implement flow control (per-frame CRC, timeouts)

2. **Device Communication**
   - Load kernel plugin (via dlopen) from specified path
   - Establish communication with target device (if remote)
   - Serialize calibration state to wire format
   - Translate wire protocol to device-specific APIs

3. **Frame Handling**
   - **HELLO**: Receive adapter identity and device capabilities
   - **CONFIG**: Initialize kernel with configuration and calibration state
   - **WINDOW_CHUNK**: Receive input data in chunked frames (8KB chunks)
   - **RESULT**: Transmit kernel output and device-side timing

4. **Timing Capture** (device clock)
   - Record timestamp when input complete (`tin`)
   - Record timestamp when `cortex_process()` called (`tstart`)
   - Record timestamp when `cortex_process()` returned (`tend`)
   - Record timestamps for first/last output byte transmission (`tfirst_tx`, `tlast_tx`)

**Adapter Types**

**Native Adapter** (`primitives/adapters/v1/native/`)

- Runs on the same machine as the harness
- Loads kernel shared library locally (dlopen)
- Communicates via Unix domain socketpair
- Measures timing via `clock_gettime(CLOCK_MONOTONIC_RAW)` on Linux or `mach_absolute_time()` on macOS

**Remote Adapter** (future extension)

- Communicates with embedded device via TCP/IP or serial port
- Implements protocol translation (wire → device-specific API)
- Depends on device-side firmware/runtime (not yet standardized)

**Plugin Adapter** (future extension)

- Loads kernel as shared library and runs in-process (no subprocess overhead)
- Used for performance-critical benchmarks or resource-constrained targets
- Shares memory space with harness (no inter-process communication)

**Normative Requirements**

A conformant adapter MUST:

- Implement complete wire protocol (Section 4):
  - Send HELLO frame with adapter identity and device info
  - Receive CONFIG frame and initialize kernel
  - Send ACK with output dimensions
  - Process WINDOW_CHUNK frames and assemble complete windows
  - Call `cortex_process()` and transmit RESULT frame
- **Never modify** input data (unless kernel explicitly opts in via `config->allow_in_place`)
- **Validate** all configuration parameters before kernel initialization
- **Capture accurate timing** using high-resolution device clocks
- **Handle errors gracefully**:
  - Missing kernel → log error, return ACK with error flag
  - Memory allocation failure → abort gracefully, close transport
  - Kernel crash → detect via signal handler, log error, close transport
- **Support graceful shutdown**: When harness closes socket, adapter MUST exit cleanly

#### 2.2.4 Plugin

**Definition**

A plugin is a **kernel shared library** (.so/.dylib) implementing the Plugin ABI (Section 3). Plugins encapsulate signal processing algorithms and are the actual computation targets being benchmarked.

**Responsibilities**

1. **Initialization** (`cortex_init()`)
   - Validate configuration (data types, parameter ranges)
   - Allocate persistent state (filters, delays, pre-computed matrices)
   - Return output dimensions
   - Detect errors and signal failure via NULL handle

2. **Processing** (`cortex_process()`)
   - Process one window of input samples
   - Apply algorithm transformation (e.g., spatial filtering, spectral analysis)
   - Write output to provided buffer
   - Run deterministically (no randomness, no I/O, no allocations)

3. **Cleanup** (`cortex_teardown()`)
   - Free all allocated state
   - Handle NULL gracefully
   - Enable memory leak detection

4. **Optional Calibration** (`cortex_calibrate()`)
   - Offline batch training for trainable kernels (ICA, CSP)
   - Receive batch of windows, return learned state
   - Produce deterministic results (same input → same output)

**Normative Requirements**

A conformant kernel plugin MUST:

- Export ABI functions via dynamic symbol table (accessible via dlsym)
- Implement all mandatory functions: `cortex_init()`, `cortex_process()`, `cortex_teardown()`
- Be **reentrant**: Support multiple concurrent calls to process() on different handles
- Be **deterministic**: Same input data → bit-identical output (for oracle validation)
- Follow strict constraints in hot path (`cortex_process()`):
  - No heap allocations
  - No blocking I/O
  - No lock acquisition that could block
  - No system calls except high-precision timing
- Handle edge cases:
  - NaN values in input (treat as 0.0 or skip)
  - NULL pointers (check and return safely)
  - Invalid parameter ranges (validate and reject)

### 2.3 Execution Model

The CORTEX execution model defines the lifecycle of a benchmark run: from configuration loading through validation, measurement, and telemetry generation.

#### 2.3.1 Two-Phase Execution

CORTEX benchmarking follows a strict **two-phase model**: validation phase and measurement phase.

**Phase 1: Validation** (non-timing)

Occurs before any performance measurements are recorded:

1. **Load Configuration**
   - Parse YAML benchmark specification
   - Validate required fields (dataset, kernels, output directory)

2. **Discover Primitives**
   - Locate kernel shared libraries
   - Load kernel metadata (spec.yaml)
   - Validate kernel ABI version

3. **Load Dataset**
   - Open dataset file
   - Verify dimensions (channels, sample rate)
   - Read metadata (duration, class labels)

4. **Perform Handshake**
   - Spawn adapter process
   - Send HELLO/CONFIG/ACK frames
   - Verify adapter and kernel are compatible
   - Receive output dimensions from adapter

5. **Warmup** (optional)
   - Stream data through pipeline without recording timing
   - Purpose: Warm caches, establish steady state
   - Duration: Configured parameter (default: 5 seconds)

6. **Validation Check**
   - Verify output dimensions against configuration
   - Verify no errors during warmup
   - Check adapter is responsive

**Rationale**: By performing extensive validation before measurement, we ensure that any failures occur outside the measurement window, preventing corrupted or misleading timing data.

**Phase 2: Measurement** (timing-critical)

Begins after validation passes:

1. **Start Measurement**
   - Initialize telemetry collection
   - Record harness-side timestamp (not used as ground truth, for debugging)
   - Begin data streaming

2. **Process Windows**
   - For each window in dataset:
     - Send WINDOW_CHUNK frames with input data
     - Receive RESULT frame with output and device-side timing
     - Record timing: `tin`, `tstart`, `tend`, `tfirst_tx`, `tlast_tx`
     - Accumulate statistics (min, max, sum of squares for variance)

3. **Duration Check**
   - Stop streaming after:
     - Duration limit reached (e.g., 60 seconds), OR
     - Dataset exhausted, OR
     - Adapter failure detected

4. **Collect Results**
   - Aggregate per-window measurements into summary statistics
   - Compute percentiles (p50, p95, p99)
   - Detect outliers and anomalies
   - Generate telemetry output

**Rationale**: By isolating measurement from validation, we:
- Minimize timing jitter from cold caches and initialization overhead
- Ensure reproducible measurements (multiple runs converge to same statistics)
- Enable fair comparison across different kernels and platforms

#### 2.3.2 Sustained Execution

CORTEX benchmarks are **NOT one-shot measurements**: the kernel processes many windows (typically 1,000-10,000 windows over 60-120 seconds) to capture sustained performance characteristics.

**Reasons for sustained execution**:

1. **Stability assessment**: How does kernel performance evolve over time? (cache effects, thermal throttling, scheduler behavior)
2. **Tail latency**: Percentile metrics (p95, p99) require sufficient samples; one-shot measurements are meaningless
3. **Realistic deployment**: Production BCI systems run for hours; transient spikes (GC, cache misses) matter less than sustained throughput
4. **Statistical significance**: Large sample sizes enable confidence intervals and hypothesis testing

**Execution Constraints**:

A CORTEX benchmark run MUST process a minimum of:
- **100 windows** (required for reliable percentile estimation)
- **5 seconds** of real time (required for thermal stabilization on some platforms)

A CORTEX benchmark run SHOULD process:
- **500+ windows** for high-confidence measurements
- **30-120 seconds** real time (sweet spot for accuracy vs. efficiency)

Benchmarks MAY be truncated early if:
- Adapter dies (fatal error)
- Dataset exhausted (normal termination)
- User requests abort (via signal, e.g., CTRL-C)

### 2.4 Data Flow

The CORTEX data flow defines how windows traverse the system: from dataset through harness, adapter, plugin, and back to telemetry collection.

#### 2.4.1 Window Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ HARNESS (Process: cortex)                                       │
│                                                                 │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │ Load Config  │──→   │ Load Dataset │──→   │  Load Kernel │  │
│  └──────────────┘      └──────────────┘      └──────────────┘  │
│         │                     │                      │          │
│         ▼                     ▼                      ▼          │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ Handshake: HELLO/CONFIG/ACK                         │     │
│  │ (Spawn adapter process)                            │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                                 │
│     Validation Phase (cache warmup, dimension checks)         │
│     ↓                                                           │
│     Measurement Phase:                                         │
│     ┌────────────────────────────────────────────────────┐    │
│     │ For each window in dataset:                        │    │
│     │   1. Read W×C samples from dataset                │    │
│     │   2. Send WINDOW_CHUNK frames (8KB chunks)        │    │
│     │   3. ─────→ (to adapter via socket)              │    │
│     │   4. Record harness timestamp (debug only)        │    │
│     │   5. Block waiting for RESULT frame                │    │
│     │   6. Receive RESULT (output + timing)             │    │
│     │   7. ←───── (from adapter via socket)             │    │
│     │   8. Accumulate statistics                         │    │
│     └────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ Generate telemetry report (NDJSON)                  │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ Shutdown: Close socket, reap adapter process         │     │
│  └──────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                             ▲
                             │ socketpair()
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ ADAPTER (Separate Process)                                      │
│                                                                 │
│  ┌──────────────────────────────────┐                          │
│  │ Receive CONFIG frame              │                          │
│  │ (ABI version, channels, params)  │                          │
│  └──────────────────────────────────┘                          │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────┐                          │
│  │ dlopen("kernel@f32.so")           │                          │
│  └──────────────────────────────────┘                          │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────┐                          │
│  │ cortex_init(config)               │                          │
│  │ → (allocate kernel state)         │                          │
│  │ → (return output shape)           │                          │
│  └──────────────────────────────────┘                          │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────┐                          │
│  │ Send ACK (output shape)            │                          │
│  └──────────────────────────────────┘                          │
│                                                                 │
│     Processing Loop (for each window):                         │
│     ┌────────────────────────────────────────────────────┐    │
│     │ 1. Recv WINDOW_CHUNK frames (assemble window)      │    │
│     │ 2. Validate: seq#, offset, CRC per frame          │    │
│     │ 3. Record tin (input complete timestamp)          │    │
│     │ 4. Record tstart = clock_gettime(CLOCK_MONOTONIC) │    │
│     │ 5. Call cortex_process(handle, input, output)     │    │
│     │ 6. Record tend = clock_gettime(CLOCK_MONOTONIC)   │    │
│     │ 7. Send RESULT frame:                              │    │
│     │    - Output samples (chunked)                       │    │
│     │    - Timing: {tin, tstart, tend, tfirst_tx, tlast_tx}  │
│     │ 8. Record tfirst_tx, tlast_tx during transmission   │    │
│     └────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ On EOF (harness closes socket):                      │     │
│  │   cortex_teardown(handle)                            │     │
│  │   dlclose(kernel_handle)                             │     │
│  │   exit(0)                                            │     │
│  └──────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                             ▲
                             │
                             ▼
                      ┌───────────┐
                      │  Kernel   │
                      │  Plugin   │
                      │ (.so/.dylib)
                      └───────────┘
                             ▲
                             │
                       cortex_process()
                             │
                             ▼
                      ┌────────────────┐
                      │ Signal         │
                      │ Processing     │
                      │ Algorithm      │
                      │ (CAR, ICA,     │
                      │  CSP, FIR...)  │
                      └────────────────┘
```

#### 2.4.2 Window Framing and Transmission

**Input Window Format**

Windows are streams of floating-point samples in row-major (time-major, interleaved channels) format:

```
Input buffer: [samples per channel × channels]
Address      Sample
-------      ------
[0]          t=0, c=0
[1]          t=0, c=1
...
[C-1]        t=0, c=C-1
[C]          t=1, c=0
[C+1]        t=1, c=1
...
[W×C-1]      t=W-1, c=C-1
```

**Chunking Strategy** (Wire Protocol, Section 4)

Large windows (160 samples × 64 channels × 4 bytes = 40,960 bytes) are transmitted in multiple frames to maintain bounded latency and memory usage:

1. Window divided into 8KB WINDOW_CHUNK frames
2. Each chunk contains:
   - Frame header (16 bytes: MAGIC, version, type, length, CRC)
   - Payload (≤8192 bytes of float32 samples)
3. Last chunk marked with CORTEX_CHUNK_FLAG_LAST
4. Adapter reassembles chunks into complete window

**Output Window Format**

Kernel output has same layout as input (row-major, interleaved channels) but may have different dimensions:
- Output channels (C') from `cortex_init()` result
- Output window length (W') from `cortex_init()` result

Adapter transmits output using same chunking strategy.

**Timing Measurement Points**

Device clock captures five timestamps:

```
Time →
│
├─ tin         : Input complete (last chunk received, before processing)
├─ tstart      : cortex_process() call enters kernel
│
│              [KERNEL EXECUTION - time tend - tstart]
│
├─ tend        : cortex_process() returns
├─ tfirst_tx   : First output byte transmitted
│
│              [OUTPUT TRANSMISSION - time tlast_tx - tfirst_tx]
│
└─ tlast_tx    : Last output byte transmitted
```

Harness computes metrics:
- **Latency** (core algorithm): `tend - tstart`
- **Input latency**: `tstart - tin` (transfer time before processing)
- **Output latency**: `tlast_tx - tend` (transfer time after processing)
- **End-to-end**: `tlast_tx - tin` (complete window turnaround)

#### 2.4.3 Error Handling in Data Flow

**Adapter Death Detection**

If adapter process dies during measurement:
- Harness blocks on socket recv() → timeout (configurable, default 10 seconds)
- Harness detects timeout → logs error with sequence number
- Harness aborts current run
- Harness attempts cleanup: waitpid() to reap zombie

**Sequence Number Validation**

Each RESULT frame includes sequence number (matching WINDOW_CHUNK sequence):
- Harness increments sequence for each window
- Adapter validates RESULT sequence matches expected
- Mismatch indicates adapter restart or data loss → abort

**CRC Validation**

Each frame includes CRC32 checksum:
- Harness/adapter compute CRC over payload
- Frame header includes CRC
- Receiver validates CRC before processing
- CRC mismatch → discard frame, request retransmission (not yet implemented, future extension)

**Data Underrun**

If dataset exhausted before duration target:
- Harness detects EOF on dataset file
- Harness sends final window, collects final RESULT
- Harness terminates measurement phase
- Harness generates report with actual duration (< configured duration)

### 2.5 Configuration and Telemetry

#### 2.5.1 Configuration Schema

The configuration schema (Section 5) defines the YAML structure for benchmark specifications:

```yaml
cortex:
  version: 1
  dataset:
    path: primitives/datasets/v1/physionet-motor-imagery
  realtime:
    scheduler: fifo
    priority: 50
  benchmark:
    duration_seconds: 60
    warmup_seconds: 5
    repeats: 3
  output:
    directory: results/
    format: ndjson
  plugins:
    - name: car@f32
      spec_uri: primitives/kernels/v1/car/spec.yaml
      params: {}
    - name: ica@f32
      spec_uri: primitives/kernels/v1/ica/spec.yaml
      params: {}
      calibration_state: primitives/datasets/v1/physionet-motor-imagery/calibration_states/ica_fastica.cortex_state
```

Configuration loading validates:
- Dataset exists and is readable
- All referenced kernels exist
- Kernel ABI version is compatible
- Calibration state files exist (if specified)
- Output directory is writable

#### 2.5.2 Telemetry Format

The telemetry format (Section 6) defines output metrics collected from each window:

```json
{"timestamp": "2024-01-15T14:32:10.123Z", "kernel": "car@f32", "dataset": "physionet-motor-imagery", "sequence": 1, "window_idx": 0, "latency_us": 2314, "input_latency_us": 127, "output_latency_us": 89, "end_to_end_latency_us": 2530}
{"timestamp": "2024-01-15T14:32:10.223Z", "kernel": "car@f32", "dataset": "physionet-motor-imagery", "sequence": 2, "window_idx": 1, "latency_us": 2298, "input_latency_us": 122, "output_latency_us": 91, "end_to_end_latency_us": 2511}
...
```

Each line is valid JSON with:
- `timestamp`: Harness-side measurement time (UTC)
- `kernel`: Kernel name from config
- `dataset`: Dataset name from config
- `sequence`: Window sequence number
- `window_idx`: Index within dataset (for traceability)
- `latency_us`: Core algorithm latency (tend - tstart) in microseconds
- `input_latency_us`: Input transmission time (tstart - tin)
- `output_latency_us`: Output transmission time (tlast_tx - tend)
- `end_to_end_latency_us`: Complete turnaround (tlast_tx - tin)

Summary statistics (aggregated per kernel/dataset):

```json
{"type": "summary", "kernel": "car@f32", "dataset": "physionet-motor-imagery", "samples": 512, "duration_seconds": 60.123, "latency_min_us": 2145, "latency_max_us": 3821, "latency_mean_us": 2298, "latency_p50_us": 2287, "latency_p95_us": 2456, "latency_p99_us": 2798}
```

### 2.6 Composability and Extensibility

#### 2.6.1 Kernel Chaining (Future Extension)

The architecture supports **kernel chaining**: connecting output of one kernel to input of another, enabling multi-stage signal processing pipelines:

```
Dataset → [Kernel 1: CAR] → [Kernel 2: Bandpass FIR] → [Kernel 3: ICA] → Telemetry
```

Shape propagation:
- Kernel 1: Input W×C → Output W'×C' (from spec.yaml or `cortex_init()` result)
- Kernel 2: Input W'×C' (validated during handshake) → Output W''×C''
- Kernel 3: Input W''×C'' → Output W'''×C'''

Timing measurement:
- Harness measures latency for each stage independently
- Propagates output of stage N to input of stage N+1
- Generates separate telemetry for each kernel

#### 2.6.2 Remote Deployment (Future Extension)

Current architecture supports local execution (adapter spawned on same machine). Future extensions enable remote deployment:

- **TCP/IP adapter**: Communicates with embedded device via TCP socket
- **Serial adapter**: Communicates with embedded microcontroller via UART
- **Cloud adapter**: Submits jobs to cloud platform (AWS Lambda, Kubernetes pod)

All remote adapters follow same protocol (Section 4) and ABI (Section 3), requiring only:
- Different adapter binary (e.g., `cortex_adapter_tcp`)
- Device-side firmware to implement wire protocol
- Network configuration (IP, port, credentials)

#### 2.6.3 Plugin Extensibility

New kernels are added by:

1. **Implementing Plugin ABI**: Write `cortex_init()`, `cortex_process()`, `cortex_teardown()`
2. **Creating spec.yaml**: Describe input/output, parameters, capabilities
3. **Building shared library**: Compile to `.so` or `.dylib`
4. **Adding to primitives tree**: Place in `primitives/kernels/v1/{kernel_name}/`
5. **Running benchmark**: Harness auto-discovers and tests new kernel

No changes to harness, adapter, or configuration required (full backward compatibility).

---

## Summary

CORTEX architecture decomposes benchmarking into four orthogonal concerns:

- **Primitives**: Versioned, immutable reusable building blocks (kernels, datasets, configs, state)
- **Harness**: Configuration loading, adapter lifecycle, data streaming, measurement collection
- **Adapter**: Device abstraction, protocol translation, timing capture
- **Plugin**: Signal processing algorithm with well-defined input/output contract

The execution model enforces a strict **validation → measurement** separation, enabling high-confidence performance metrics. Sustained execution over hundreds/thousands of windows captures realistic performance characteristics and enables statistical analysis.

Data flows through the system as windows (W×C float32 samples) via chunked transmission over byte-stream transports. Device-side timing captures five measurement points enabling decomposition of latency into algorithmic, input transmission, and output transmission components.

The architecture prioritizes **modularity and extensibility**: new kernels, datasets, and adapters can be added without modifying core components, enabling rapid research iteration and real-world deployment scenarios.
