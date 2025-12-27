# CORTEX Project Roadmap

This document tracks progress against the original Fall 2025 proposal and implementation plan, organizing tasks into completed, in-progress, remaining, and future work.

## Completed (Weeks 1-4)

### Infrastructure & Architecture
- [x] Dataset selection and documentation (PhysioNet EEG Motor Movement/Imagery)
- [x] Kernel specifications (individual README.md files for CAR, notch IIR, bandpass FIR, Goertzel)
- [x] Plugin ABI definition ([plugin-interface.md](../reference/plugin-interface.md), cortex_plugin.h)
- [x] Run configuration schema ([configuration.md](../reference/configuration.md))
- [x] Telemetry schema ([telemetry.md](../reference/telemetry.md))
- [x] Dataset replayer implementation (src/engine/replayer/) with real-time cadence
- [x] Scheduler with real-time support (src/engine/scheduler/) - FIFO/RR policies, CPU affinity
- [x] Harness with plugin loader (src/engine/harness/) - sequential plugin execution
- [x] Kernel registry system (primitives/kernels/v1/{name}@{dtype}/) with spec.yaml
- [x] macOS compatibility (dylib support, cross-platform builds)
- [x] Oracle reference implementations (Python/SciPy/MNE in primitives/kernels/v1/*/oracle.py)
- [x] Unit tests (replayer, scheduler, kernel registry)

### Design Decisions
- Sequential plugin execution architecture (isolates per-kernel performance)
- Kernel registry with versioned specifications (primitives/kernels/v1/{name}@{dtype}/)
- Runtime parameters derived from specs + dataset config
- Separate kernel "what" (spec) from "how to run" (config)

## In Progress (Weeks 5-7, Current)

### Kernel C Implementations (In Progress)
- CAR (Common Average Reference) - **COMPLETED**
- Notch IIR (60Hz line noise removal) - **COMPLETED**
- FIR Bandpass (8-30 Hz) - **COMPLETED**
- Goertzel Bandpower - **COMPLETED**

### Measurement Infrastructure
- Background load profiles (stress-ng integration) - **COMPLETED**
- Kernel auto-detection system - **COMPLETED**

## Remaining This Semester (Weeks 7-9)

### Midterm Deliverables (Week 7)
- Complete all kernel C implementations
- Run initial experiment matrix (2-3 kernels × load profiles)
- Generate preliminary comparison plots **COMPLETED** - HTML report generator
- Live demonstration of harness running multiple kernels
- Midterm demo presentation

### Final Deliverables (Weeks 8-9)
- Complete run matrix (all kernels × float32 baseline)
- Generate final comparison plots (latency, jitter, throughput, deadline misses, memory)
- Optional: Welch PSD kernel implementation
- Final report documenting methodology, results, recommendations
- Reproducibility packaging (one-command builds and runs)
- Final presentation

**Note**: Quantization (Q15/Q7) and energy measurement (RAPL) are deferred to Spring 2026 to align with embedded device testing phase (see Phase 3 below).

## Deferred/Future Work

### Quantization (Q15/Q7) - Deferred to Spring 2026

**Rationale**: Quantization is most valuable when benchmarking on embedded targets (STM32H7, Jetson) planned for Spring 2026. Fall 2025 establishes the float32 baseline on x86.

**Infrastructure Status**:
- [x] Plugin ABI supports multiple dtypes (CORTEX_DTYPE_FLOAT32, Q15, Q7)
- [x] Kernel specs include quantized tolerances (rtol=1e-3, atol=1e-3)
- [ ] TODOs in scheduler (scheduler.c:185, scheduler.h:82-83) mark implementation points
- [ ] No Q15/Q7 kernel implementations exist yet
- [ ] Harness hardcodes dtype=float32 (main.c:102)
- [ ] Replayer only reads float32 datasets

**Spring 2026 Implementation Plan**:
1. Dataset conversion: float32 → Q15/Q7 binary formats
2. Replayer dtype handling: read Q15/Q7 from disk
3. Scheduler buffer allocation: variable element size
4. Kernel implementations: 4 kernels × 2 quantized formats = 8 new plugins
5. Fixed-point arithmetic: manual scaling, overflow protection, saturation
6. Validation: test against float32 oracles with looser tolerances
7. Analysis: compare latency/memory/energy across float32/Q15/Q7 on embedded targets

See `primitives/kernels/v1/cortex_plugin.h` for dtype definitions and `primitives/kernels/v1/{name}@{dtype}/spec.yaml` for tolerance specifications.

**Kernel Auto-Detection Multi-Dtype Limitations**: The Fall 2025 auto-detection system (`cortex_discover_kernels()`) has known limitations with multi-dtype support that will be addressed during quantization implementation. See `docs/development/future-enhancements.md` "Current Auto-Detection Limitations" section and `src/engine/harness/config/config.c` TODOs for details.

### Host Power Configuration - DEFERRED to Spring 2026

**Original Implementation** (Commit 02197d8, November 2025):
- Python wrapper for CPU governor/turbo control
- Context manager for automatic cleanup
- Platform-specific implementations (Linux `cpupower`, macOS `pmset`)
- Full ADR documentation (ADR-001)
- Comprehensive error handling and fallback

**Why Deferred** (Commit 1a3a868, November 2025):
- Feature only works on Linux (requires `sysfs`, `cpupower` utilities)
- macOS `pmset` only provides warnings, no actual power control
- Fall 2025 benchmarks run exclusively on macOS
- Alternative solution achieves same goal: `load_profile: "medium"` maintains consistent CPU frequency through sustained background load (empirically validated)

**Current Alternative**:
Use `load_profile: "medium"` for platform-agnostic CPU frequency control. This approach:
- Prevents macOS frequency scaling (49% performance variance discovered in validation runs)
- Works on both macOS and Linux
- Empirically validated via three-way comparison (n=1200+ samples)
- Goal-equivalent to Linux performance governor

**Spring 2026 Reinstatement Plan**:
When embedded device HIL testing begins on Linux hosts:
1. Restore power config feature from commit 02197d8
2. Integrate with device adapter framework
3. Linux host will use performance governor control
4. macOS host will continue using medium load baseline approach
5. Update ADR-002 with platform-specific strategy

**Documentation**:
- Decision rationale: [ADR-002](../architecture/adr/adr-002-benchmark-reproducibility-macos.md)
- Technical report: [`experiments/dvfs-validation-2025-11-15/technical-report/`](../../experiments/dvfs-validation-2025-11-15/technical-report/)
- Validation data: [`experiments/dvfs-validation-2025-11-15/`](../../experiments/dvfs-validation-2025-11-15/)
- Configuration guide: [Platform-Specific Recommendations](../reference/configuration.md#platform-specific-recommendations)

### Unimplemented Configuration Fields
These fields are **documented** in `docs/reference/configuration.md` and **parsed** by the config loader but **not yet used** by the harness:

- `system.name`, `system.description` - Run metadata for identification
- `power.governor`, `power.turbo` - CPU power management settings
- `benchmark.metrics` array - Metric selection (currently collects all)
- `realtime.deadline.*` (runtime_us, period_us, deadline_us) - DEADLINE scheduler parameters
- `plugins[].tolerances` - Per-plugin numerical tolerance specs
- `plugins[].oracle` - Per-plugin oracle reference paths
- `output.include_raw_data` - Raw telemetry data export flag

**Reference**: `docs/reference/configuration.md` "Implementation Status" section

### Planned Features (From TODOs)

#### Background Load Profiles
- [x] Stress-ng integration for idle/medium/heavy profiles (✅ COMPLETED)
- [x] Background load startup/teardown functions (✅ COMPLETED)
- [ ] Controlled chunk dropout/delay simulation (deferred - not currently needed)

#### Telemetry & Analysis
- [x] NDJSON telemetry output format (completed - alternative to CSV)
- Summary statistics generation (p50/p95/p99 aggregates, miss rate) - partially available in HTML reports
- Multi-session dataset concatenation support (future enhancement)
- Per-window energy (E_window) and derived power (P = E_window × Fs/H) - deferred to Spring 2026

## Removed from Scope

### Analytical FLOPs/Bytes Counters - **REMOVED** (November 2025)

**Original Proposal Requirement** (Week 5-6):
> "We additionally log rough FLOPs and bytes-per-window (analytical counters) to estimate arithmetic intensity for accelerator targeting."

**Decision Rationale**:
Analytical (theoretical) FLOPs/bytes metrics were **removed from scope** rather than deferred because they provide **limited practical value** for the BCI real-time analysis use case:

1. **Latency is sufficient**: The core question "Does this kernel meet real-time deadlines?" is conclusively answered by measured latency (µs) compared to deadline (ms). Theoretical operation counts don't add actionable information.

2. **Misleading for accelerator decisions**: Analytical metrics (e.g., "high FLOPs/byte → GPU candidate") ignore reality:
   - Current performance: Goertzel @ 134µs with 500ms deadline = **3,731× safety margin**
   - GPU overhead: PCIe transfer + kernel launch ≈ 100-500µs would make it **slower**
   - The analytical metric would incorrectly suggest GPU acceleration

3. **Ignores real-world constraints**: Theoretical FLOPs don't account for:
   - Cache behavior (cache miss = 100× slowdown)
   - Vectorization (SIMD = 8× speedup)
   - Memory bandwidth limitations
   - Branch prediction effects
   - Compiler optimizations

4. **Alternative metrics are more valuable**: For the same implementation effort (~45 min), these provide better insight:
   - **Deadline slack** = `(deadline - p99_latency) / deadline × 100%` → Shows optimization headroom
   - **Memory footprint** = actual heap usage → Critical for embedded targets (STM32H7: 1MB RAM)
   - **Throughput saturation** = max sustainable rate → Shows real capacity limits

5. **Embedded porting decisions rely on empirical data**: Cross-platform performance estimation requires:
   - Measured latency on reference platform (x86)
   - Empirical scaling factors from target hardware benchmarks
   - Not theoretical operation counts

**What We Have Instead**:
- ✅ **Measured latency** (P50/P95/P99) - actual execution time
- ✅ **Jitter analysis** - consistency/predictability
- ✅ **Deadline miss tracking** - hard real-time compliance
- ✅ **Throughput** (windows/second) - derived from measured latency

These **measured metrics** directly answer the research questions and support evidence-based recommendations for BCI kernel deployment.

**Academic Note**: Analytical FLOPs remain useful for:
- HPC benchmarking comparisons (achieving X% of theoretical peak)
- Algorithm comparison before implementation
- Cross-platform rough estimation (with large error bars)

For **BCI real-time viability analysis**, measured latency is the definitive metric.

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

**Implementation Location**: `datasets/tools/` directory with tools for dataset generation, benchmarking, and capability querying.

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
- Benchmarking Methodology: `docs/architecture/benchmarking-methodology.md` (HIL vs. Full On-Device vs. Stochastic Calibration)

