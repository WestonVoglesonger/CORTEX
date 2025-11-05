# CORTEX Architecture Overview

CORTEX is a reproducible benchmarking pipeline for Brain-Computer Interface (BCI) signal processing kernels. This document provides a high-level overview of the system architecture, component responsibilities, and data flow.

## System Architecture

```
┌─────────────┐
│   Dataset   │ (PhysioNet EEG, 64ch @ 160Hz)
└──────┬──────┘
       │
       v
┌─────────────────────────────────────────────────────────┐
│                    Replayer                             │
│  - Streams samples at configured Fs (e.g., 160 Hz)     │
│  - Delivers hop-sized chunks (H samples) on schedule    │
│  - Maintains real-time cadence                          │
└────────────────────┬────────────────────────────────────┘
                     │ (Hop-sized chunks: H×C samples)
                     v
┌─────────────────────────────────────────────────────────┐
│                   Scheduler                             │
│  - Buffers incoming chunks into windows (W samples)     │
│  - Manages 50% overlap (W=160, H=80)                   │
│  - Assigns release_time and deadline (deadline = H/Fs)  │
│  - Enforces CPU affinity and RT priority (SCHED_FIFO)   │
└────────────────────┬────────────────────────────────────┘
                     │ (Windows: W×C samples)
                     v
            ┌────────┴────────┐
            │  Plugin Loader   │
            └────────┬────────┘
                     │
       ┌─────────────┼─────────────┐
       │             │             │
       v             v             v
  ┌─────────┐  ┌─────────┐  ┌─────────┐
  │ notch   │  │   fir   │  │goertzel │  (Sequential execution)
  │  _iir   │  │_bandpass│  │         │
  └────┬────┘  └────┬────┘  └────┬────┘
       │            │            │
       └────────────┼────────────┘
                    │ (Per-window metrics)
                    v
         ┌──────────────────────┐
         │     Telemetry         │
         │  - Latency tracking   │
         │  - Deadline checking  │
         │  - NDJSON/CSV output  │
         └──────────────────────┘
                    │
                    v
         ┌──────────────────────┐
         │   results/ directory  │
         │  - Per-kernel runs    │
         │  - Batch summaries    │
         │  - HTML reports       │
         └──────────────────────┘
                    │
                    v
         ┌──────────────────────┐
         │  Analysis Pipeline    │
         │  - Load NDJSON data   │
         │  - Statistical summary│
         │  - Visualization plots│
         └──────────────────────┘
```

## Core Components

### 1. Harness (`src/harness/`)

**Purpose**: Orchestration and coordination layer

**Responsibilities**:
- Parse YAML configuration (`configs/cortex.yaml`)
- Initialize replayer with dataset parameters
- Load kernel plugins dynamically (`.dylib` on macOS, `.so` on Linux)
- Create separate scheduler instance per plugin
- Execute plugins sequentially (not in parallel)
- Collect and write telemetry to disk
- Generate HTML reports with visualizations

**Key files**:
- `src/harness/app/main.c` - Entry point and orchestration
- `src/harness/loader/loader.c` - Dynamic plugin loading
- `src/harness/telemetry/telemetry.c` - Metrics collection
- `src/harness/config/config.c` - YAML parsing

**Binary output**: `src/harness/cortex`

### 2. Replayer (`src/replayer/`)

**Purpose**: Dataset streaming with real-time cadence

**Responsibilities**:
- Read EEG dataset from disk (currently float32 raw format)
- Stream samples at configured sample rate (Fs, typically 160 Hz)
- Deliver hop-sized chunks (H samples) on schedule
- Maintain timing cadence: period = H/Fs (e.g., 80/160 = 500 ms)
- Loop dataset if needed for longer benchmarks
- Callback to scheduler when chunk ready

**Timing model**:
```
Chunk rate = Fs / H
Period = H / Fs

Example: 160 Hz, H=80 → 2 chunks/sec, 500ms period
```

**Formats supported**:
- Float32 raw (current)
- EDF+ (via conversion scripts in `scripts/`)

### 3. Scheduler (`src/scheduler/`)

**Purpose**: Windowing, buffering, and deadline enforcement

**Responsibilities**:
- Buffer hop-sized chunks into windows (W samples)
- Manage overlapping windows (retain W-H samples between windows)
- Assign timestamps:
  - `release_ts` - when window became available
  - `deadline_ts` - release_ts + (H/Fs)
  - `start_ts` - when plugin processing began
  - `end_ts` - when plugin processing completed
- Check deadline: `deadline_missed = (end_ts > deadline_ts)`
- Configure real-time priority (SCHED_FIFO or SCHED_RR on Linux)
- Set CPU affinity (pin to specific cores)
- Pass windows to plugin `cortex_process()` function

**Window parameters** (EEG v1):
- **W (window length)**: 160 samples (1 second @ 160 Hz)
- **H (hop)**: 80 samples (50% overlap)
- **C (channels)**: 64
- **Deadline**: H/Fs = 500 ms per window

### 4. Plugin System

**Purpose**: Loadable kernel implementations

**ABI Version**: 2 (current)

**Interface** (`include/cortex_plugin.h`):

```c
// Initialize plugin, return output dimensions
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);

// Process one window (no allocations allowed!)
void cortex_process(void *handle, const void *input, void *output);

// Free resources
void cortex_teardown(void *handle);
```

**Plugin lifecycle**:
1. Harness calls `dlopen()` to load `.dylib`/`.so`
2. Harness calls `cortex_init()` → plugin allocates state, returns output shape
3. For each window: Harness calls `cortex_process()` → plugin runs algorithm
4. At end: Harness calls `cortex_teardown()` → plugin frees resources

**Key constraints**:
- ❌ **No allocations in `cortex_process()`** - pre-allocate everything in `init()`
- ✅ **Stateful** - IIR/FIR state persists across windows
- ✅ **Thread-safe** - no concurrent calls on same handle
- ✅ **Platform-agnostic** - same C code for macOS and Linux

**See**: [plugin-interface.md](../reference/plugin-interface.md) for complete spec

### 5. Telemetry (`src/harness/telemetry/`)

**Purpose**: Metrics collection and output

**Metrics collected**:
- **Latency**: `end_ts - start_ts` (time to process one window)
- **Jitter**: Variance in latency across windows
- **Throughput**: Windows processed per second
- **Memory**: RSS (resident set size)
- **Deadline misses**: Count of windows where `end_ts > deadline_ts`

**Output formats**:
- **NDJSON** (default): One JSON object per line, streaming-friendly
- **CSV**: Legacy format for Excel/spreadsheets

**Output location**: `results/{run_id}/{kernel}_telemetry.ndjson`

**See**: [telemetry.md](../reference/telemetry.md) for schema details

## Data Flow

### 1. Configuration Phase

```
configs/cortex.yaml  →  config parser  →  cortex_run_config_t
```

Configuration specifies:
- Dataset path and parameters (Fs, channels)
- Benchmark duration, repeats, warmup
- Real-time scheduler settings
- Plugin list with spec URIs

### 2. Initialization Phase

```
1. Load dataset → replayer_init()
2. For each plugin:
   a. dlopen("kernels/v1/{name}@f32/lib{name}.dylib")
   b. cortex_init() → allocate state, return output shape
   c. scheduler_init() → create dedicated scheduler instance
```

### 3. Execution Phase (Per Plugin)

```
Loop for duration:
  1. Replayer delivers chunk (H×C samples) every H/Fs seconds
  2. Scheduler buffers chunk into window (W×C samples)
  3. When window ready:
     a. Record release_ts, calculate deadline_ts
     b. Call cortex_process(window) → kernel processes
     c. Record start_ts, end_ts
     d. Check: deadline_missed = (end_ts > deadline_ts)
     e. Write telemetry record
  4. Slide window: keep last W-H samples, wait for next chunk
```

### 4. Teardown Phase

```
1. cortex_teardown() for each plugin
2. scheduler_teardown() for each instance
3. replayer_teardown()
4. Write HTML report
```

### 5. Analysis Phase (Post-Run)

```
1. Load NDJSON files from results/batch_{timestamp}/
2. Compute statistics (p50, p95, p99, deadline miss rate)
3. Generate plots (latency CDF, comparison bar charts)
4. Write SUMMARY.md
```

## Design Principles

### Sequential Plugin Execution

**Decision**: Run each plugin in a separate, sequential scheduler instance

**Rationale**:
- Isolates per-kernel performance (no interference)
- Simplifies deadline tracking (one plugin at a time)
- Enables fair comparison (same dataset slice, same conditions)
- Matches real-world BCI usage (single kernel active)

**Trade-off**: Longer total benchmark time vs. accurate per-kernel metrics

**See**: [sequential-execution.md](sequential-execution.md) for full rationale

### Hardware-in-the-Loop (HIL) Testing

**Current mode**: All kernels run on host system (x86 Mac/Linux)

**Rationale**:
- Establish algorithmic lower bounds for latency
- Validate correctness against oracles
- Measure float32 baseline before quantization
- Reproducible environment (consistent hardware)

**Future**: Spring 2026 adds embedded HIL (STM32H7, Jetson)

**See**: [testing-strategy.md](testing-strategy.md) for methodology

### Plugin Versioning

**Structure**: `kernels/v{version}/{name}@{dtype}/`

**Versions**:
- `v1/` - Initial float32 implementations
- `v2/` - Reserved for optimized/quantized variants

**Data types**:
- `@f32` - 32-bit float (current)
- `@q15` - 16-bit fixed-point (future)
- `@q7` - 8-bit fixed-point (future)

**Immutability**: Once a version is released, it's frozen. Optimizations go in new version.

## Platform Compatibility

### macOS
- Plugin extension: `.dylib`
- Build flag: `-dynamiclib`
- Real-time: Not supported (logs warning)
- Tested: Apple Silicon (arm64), Intel (x86_64)

### Linux
- Plugin extension: `.so`
- Build flag: `-shared -fPIC`
- Real-time: SCHED_FIFO, SCHED_RR, CPU affinity
- Tested: Ubuntu, Fedora, Alpine

**See**: [platform-compatibility.md](platform-compatibility.md) for details

## Configuration Flow

```
YAML → config parser → numerical parameters → cortex_plugin_config_t
```

**Important**: Plugins receive **only numeric runtime parameters**, not raw YAML:
- Window length, hop, channels, sample rate
- Optional: `kernel_params` pointer (not yet wired up in harness)

**Note**: Current limitation - all kernel parameters are hardcoded:
- `notch_iir`: f0=60 Hz, Q=30
- `fir_bandpass`: numtaps=129, passband=[8,30] Hz
- `goertzel`: alpha (8-13 Hz), beta (13-30 Hz)

## File Organization

```
CORTEX/
├── src/
│   ├── harness/       # Main orchestration
│   ├── replayer/      # Dataset streaming
│   └── scheduler/     # Windowing & deadlines
├── include/
│   └── cortex_plugin.h  # Public ABI
├── kernels/
│   └── v1/            # Kernel implementations
│       ├── car@f32/
│       ├── notch_iir@f32/
│       ├── fir_bandpass@f32/
│       └── goertzel@f32/
├── configs/           # YAML configurations
├── datasets/          # EEG data
├── results/           # Benchmark output
├── tests/             # Unit/integration tests
├── scripts/           # Dataset conversion
└── cortex_cli/        # Python analysis tools
```

## Next Steps

- **Add a kernel**: [guides/adding-kernels.md](../guides/adding-kernels.md)
- **Configure runs**: [reference/configuration.md](../reference/configuration.md)
- **Understand kernels**: [reference/kernels.md](../reference/kernels.md)
- **Interpret results**: [reference/telemetry.md](../reference/telemetry.md)
- **Platform-specific**: [platform-compatibility.md](platform-compatibility.md)
