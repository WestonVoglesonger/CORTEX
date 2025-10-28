# CORTEX Project Roadmap

This document tracks progress against the original Fall 2025 proposal and implementation plan, organizing tasks into completed, in-progress, remaining, and future work.

## Completed (Weeks 1-4)

### Infrastructure & Architecture
- ✅ Dataset selection and documentation (PhysioNet EEG Motor Movement/Imagery)
- ✅ Kernel specifications (KERNELS.md with CAR, notch IIR, FIR bandpass, Goertzel)
- ✅ Plugin ABI definition (PLUGIN_INTERFACE.md, cortex_plugin.h)
- ✅ Run configuration schema (RUN_CONFIG.md)
- ✅ Telemetry schema (TELEMETRY.md)
- ✅ Dataset replayer implementation (src/replayer/) with real-time cadence
- ✅ Scheduler with real-time support (src/scheduler/) - FIFO/RR policies, CPU affinity
- ✅ Harness with plugin loader (src/harness/) - sequential plugin execution
- ✅ Kernel registry system (kernels/v1/{name}@{dtype}/) with spec.yaml
- ✅ macOS compatibility (dylib support, cross-platform builds)
- ✅ Oracle reference implementations (Python/SciPy/MNE in kernels/v1/*/oracle.py)
- ✅ Unit tests (replayer, scheduler, kernel registry)

### Design Decisions
- Sequential plugin execution architecture (isolates per-kernel performance)
- Kernel registry with versioned specifications (kernels/v1/{name}@{dtype}/)
- Runtime parameters derived from specs + dataset config
- Separate kernel "what" (spec) from "how to run" (config)

## In Progress (Weeks 5-7, Current)

### Kernel C Implementations ⏳
- CAR (Common Average Reference) - **NOT YET IMPLEMENTED**
- Notch IIR (60Hz line noise removal) - **NOT YET IMPLEMENTED**
- FIR Bandpass (8-30 Hz) - **NOT YET IMPLEMENTED**
- Goertzel Bandpower - **NOT YET IMPLEMENTED**

### Measurement Infrastructure ⏳
- RAPL energy measurement (Linux-only)
- FLOPs/bytes analytical counters
- Background load profiles (stress-ng integration - 5 TODOs in replayer.c)
- JSON telemetry output (currently CSV only)

### Quantization ⏳
- Q15/Q7 quantized data type support (2 TODOs in scheduler)

## Remaining This Semester (Weeks 7-9)

### Midterm Deliverables (Week 7)
- Complete all kernel C implementations
- Run initial experiment matrix (2-3 kernels × load profiles)
- Generate preliminary comparison plots ✅ **COMPLETED** - HTML report generator
- Live demonstration of harness running multiple kernels
- Midterm demo presentation

### Final Deliverables (Weeks 8-9)
- Complete run matrix (all kernels × load profiles × quantization)
- Generate final comparison plots (latency, jitter, energy, deadline misses)
- Optional: Welch PSD kernel implementation
- Optional: Q15/Q7 quantization sweep results
- Final report documenting methodology, results, recommendations
- Reproducibility packaging (one-command builds and runs)
- Final presentation

## Deferred/Future Work

### Unimplemented Configuration Fields
These fields are **documented** in `docs/RUN_CONFIG.md` and **parsed** by the config loader but **not yet used** by the harness:

- `system.name`, `system.description` - Run metadata for identification
- `power.governor`, `power.turbo` - CPU power management settings
- `benchmark.metrics` array - Metric selection (currently collects all)
- `realtime.deadline.*` (runtime_us, period_us, deadline_us) - DEADLINE scheduler parameters
- `plugins[].tolerances` - Per-plugin numerical tolerance specs
- `plugins[].oracle` - Per-plugin oracle reference paths
- `output.include_raw_data` - Raw telemetry data export flag
- `benchmark.load_profile` - Parsed but stress-ng integration pending

**Reference**: `docs/RUN_CONFIG.md` "Implementation Status" section

### Planned Features (From TODOs)

#### Background Load Profiles
- Stress-ng integration for idle/medium/heavy profiles (replayer.c:216, 107, 115)
- Controlled chunk dropout/delay simulation (replayer.c:154)
- Background load startup/teardown functions (currently stubs)

#### Quantization
- Q15 (16-bit fixed-point) and Q7 (8-bit fixed-point) data types (scheduler.c:192, scheduler.h:83)
- Conversion routines from float32
- Accuracy loss analysis vs. float32 references
- Latency/energy comparisons across data types

#### Telemetry & Analysis
- JSON telemetry output format (currently CSV only)
- Summary statistics generation (p50/p95/p99 aggregates, miss rate)
- Multi-session dataset concatenation support
- Per-window energy (E_window) and derived power (P = E_window × Fs/H)

#### Code Cleanup
- Remove unused globals (g_dtype) or implement proper dtype handling (replayer.c:14-19)
- Mark g_replayer_running as volatile/atomic for cross-thread safety (replayer.c:14-19)
- Document callback contract: replayer thread, must not block (replayer.c:14-19)
- Enforce or validate dataset file format assumptions (replayer.c:14-19)

#### Capability Assessment System
**Future Approach: Pre-computed Capability Database**

Instead of dynamically generating synthetic data for each user capability query (which is slow and complex), implement a pre-computed capability assessment system:

- **Synthetic Dataset Generation**: Pre-generate realistic EEG-like datasets for standard configurations (64ch→2048ch, 160Hz→500Hz) using controlled statistical properties
- **System Capability Benchmarking**: Run comprehensive benchmarks once per system to determine maximum supported channel counts and sampling rates for each kernel
- **Capability Database**: Store results in a queryable database with system specifications and performance limits
- **Instant Queries**: Answer user questions like "Can my system handle 512 channels at 500Hz with kernel X?" in milliseconds rather than minutes

**Benefits:**
- Fast capability queries (no data generation overhead)
- Reproducible benchmarks across different systems
- Scalable to high channel counts without runtime complexity
- Enables user-friendly "system compatibility checker" interface

**Implementation Location**: `scripts/` directory with tools for dataset generation, benchmarking, and capability querying.

## Phase 3: Next Semester (HIL Extension)

From CORTEX embedded devices proposal (Spring 2026):

### Hardware-in-the-Loop (HIL) Infrastructure
- Device adapters: STM32H7 (UART), Jetson Orin Nano (TCP + .so)
- Protocol: HELLO/CONFIG/WINDOW/RESULT frames over UART/TCP
- Timing semantics: tin, tstart, tend, tfirst_tx, tlast_tx on device clock
- Host-device synchronization with periodic ping frames

### Energy Measurement on Embedded Targets
- MCU: INA226 shunt-based energy measurement
- Jetson: tegrastats/board sensors (temperature, rail flags)
- GPIO-triggered energy alignment for synchronized power traces

### Calibration Harness
- Minimal on-device calibration program (ISR + DMA stub + double buffer)
- Tunable dummy kernel with cycle counting
- Calibrated overhead models: T_total = a + b × T_kernel + ε
- Parameter extraction: fixed overhead (a), multiplicative factor (b), jitter (ε)
- Validation against external meters

### Multi-Device Benchmarking
- Saturation search to find max channels/hop meeting deadlines per kernel/device
- Comparative analysis across x86 (reference), MCU, and embedded Linux
- Reproducible "apples-to-apples" measurements across compute substrates

## Success Criteria

### This Semester (Fall 2025)
- End-to-end pipeline running 2-4 kernels on fixed dataset
- Reusable codebase with clear documentation
- CSV exports and comparison figures
- Reproducible runs via YAML configs
- Clear recommendations on kernel real-time viability

### Next Semester (Spring 2026)
- Runner overhead < 5%
- Reproducibility ±3%
- Real-time pass at baseline configuration on at least one embedded target
- Validated energy accounting against external meter
- Documentation of HIL vs. full on-device trade-offs

## References

- Original Proposal: "Benchmarking BCI Kernels: A Pipeline for Real-Time Performance Analysis" (Sept 2025)
- Implementation Plan: "Brain–Computer Interface Benchmark Project Plan" (Sept 23, 2025)
- Embedded Extension: "CORTEX: Extending BCI Kernel Benchmarking to Embedded Devices" (Oct 23, 2025)
- Testing Strategy: `docs/TESTING_STRATEGY.md` (HIL vs. Full On-Device vs. Stochastic Calibration)

