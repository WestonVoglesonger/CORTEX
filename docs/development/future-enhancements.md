# Future Enhancements

This document consolidates all planned features, deferred implementations, and future work for CORTEX. Features are organized by timeline and implementation priority.

---

## Timeline Overview

| Phase | Timeframe | Focus |
|-------|-----------|-------|
| **Spring 2026** | Embedded Device Phase | Energy monitoring, quantization, HIL infrastructure |
| **Fall 2025 (Optional)** | Current Semester | Config wiring, SCHED_DEADLINE, load profiles |
| **Future/Unscheduled** | TBD | Testing improvements, analysis tools, code quality |

---

## Spring 2026: Embedded Device Phase

### Energy Monitoring

**Status:** Schema defined, not implemented

**Current State:**
- Telemetry schema includes `energy_j` and `power_mw` fields
- Fall 2025: x86 results are timing-only (latency, jitter, throughput, memory)

**Planned Implementation:**
- **x86:** RAPL via sysfs (`/sys/class/powercap/intel-rapl`)
- **MCU (STM32H7):** INA226 shunt sensor with GPIO triggers
- **Embedded Linux (Jetson):** tegrastats/board sensors
- Plugin architecture will support inline measurement (RAPL, INA3221) and external measurement (GPIO triggers)

**Code Changes Required:**
- `src/engine/harness/energy_rapl.{h,c}` - RAPL energy measurement for Linux x86
- Telemetry integration for energy metrics
- Platform detection for energy measurement capabilities

**Documentation:**
- Schema: `docs/reference/telemetry.md`
- Overview: `CLAUDE.md` lines 372-380
- Proposal document for full embedded timeline

---

### Quantization Support (Q15/Q7) {#quantization-support-q15q7}

**Status:** Infrastructure ready, implementations deferred

**Rationale:** Most valuable when benchmarking on embedded targets (STM32H7, Jetson) in Spring 2026. Fall 2025 establishes float32 baseline on x86.

**Infrastructure Status:**
- ✅ Plugin ABI supports multiple dtypes (`CORTEX_DTYPE_FLOAT32`, `Q15`, `Q7`)
- ✅ Kernel specs include quantized tolerances (rtol=1e-3, atol=1e-3)
- ❌ No Q15/Q7 kernel implementations exist yet (need 8 new plugins)
- ❌ Harness hardcodes `dtype=float32`
- ❌ Replayer only reads float32 datasets

**Implementation Plan:**

1. **Dataset Conversion Scripts**
   - Extend `datasets/tools/convert_edf_to_float32.py` to support Q15/Q7 output formats
   - Q15: 16-bit signed integers with scale S=32768 (value ≈ q / S)
   - Q7: 8-bit signed integers with scale S=128

2. **Replayer Dtype Handling**
   - Replace `float *` buffers with `void *`
   - Read chunks based on `dtype_size = sizeof_dtype(config->dtype)`
   - Make callback signature `const void *chunk_data`
   - Actually use the `dataset.format` config field

3. **Scheduler Buffer Allocation**
   - Support variable element sizes based on dtype
   - Pass dtype-agnostic buffers to plugins

4. **Kernel Implementations**
   - Implement 4 kernels × 2 quantized formats = 8 new plugins:
     - `primitives/kernels/v1/car@q15/`, `primitives/kernels/v1/car@q7/`
     - `primitives/kernels/v1/notch_iir@q15/`, `primitives/kernels/v1/notch_iir@q7/`
     - `primitives/kernels/v1/bandpass_fir@q15/`, `primitives/kernels/v1/bandpass_fir@q7/`
     - `primitives/kernels/v1/goertzel@q15/`, `primitives/kernels/v1/goertzel@q7/`
   - Implement fixed-point arithmetic: manual scaling, overflow protection, saturation

5. **Validation**
   - Test quantized implementations against float32 oracles with looser tolerances
   - Quantized tolerances: `rtol=1e-3`, `atol=1e-3` (vs float32: `rtol=1e-5`, `atol=1e-6`)

6. **Analysis**
   - Compare latency/memory/energy across float32/Q15/Q7 on embedded targets
   - Measure quantization impact on BCI signal quality

**Code Changes Required:**
- `src/engine/replayer/replayer.c` lines 123, 176, 184-185 - Remove float32 hardcoding
- `src/engine/replayer/replayer.h` line 32 - Use dtype field
- `src/engine/harness/app/main.c` line 102 - Remove hardcoded `dtype=1u`
- `src/engine/scheduler/scheduler.c` line 185 - Variable dtype size
- `src/engine/scheduler/scheduler.h` lines 82-83 - Dtype-agnostic buffers

**Current Limitations:**
- Replayer comment (line 19): "Dataset path semantics: assumes float32 file; enforce or validate."
- Replayer TODO (line 15): "Kill unused globals (g_dtype) or implement proper dtype handling."
- `g_dtype` variable stored but never used

**Documentation:**
- Overview: `docs/development/roadmap.md` lines 59-80
- ABI: `sdk/kernel/include/cortex_plugin.h` lines 52-56 (dtype enums), line 75 (config struct)
- Tolerances: `primitives/kernels/v1/{name}@{dtype}/spec.yaml`

**Current Auto-Detection Limitations** (Fall 2025):

The kernel auto-detection system (`cortex_discover_kernels()`) has known limitations that will be addressed during Spring 2026 quantization implementation:

1. **Sorting treats all dtypes equally**: When multiple dtypes exist for the same kernel (e.g., `goertzel@f32`, `goertzel@q15`), the alphabetical sort on kernel name will group them together but their relative order is unpredictable. This may cause inconsistent ordering across runs when multiple dtypes are present.

2. **Display names drop dtype suffix**: User-facing output shows only kernel name (e.g., "goertzel") without the dtype (e.g., "goertzel@f32"), making it ambiguous which variant ran when multiple dtypes are available.

**Impact**: These limitations are **not currently observable** because only `@f32` variants exist (Fall 2025). They will become relevant when `@q15` and `@q7` implementations are added next semester.

**Planned Fixes** (Spring 2026):
- Enhanced sorting: Primary sort by kernel name, secondary sort by dtype priority (f32 > q15 > q7)
- Qualified display names: Show full `{name}@{dtype}` in console output and telemetry
- Dtype filtering: Optional config field to select specific dtypes for auto-detection

See `src/engine/harness/config/config.c` TODOs for implementation locations.

---

### Hardware-in-the-Loop (HIL) Infrastructure

**Status:** Planned for embedded devices extension

**Planned Features:**
- **Device Adapters:**
  - STM32H7: UART-based protocol
  - Jetson Orin Nano: TCP + .so file transfer
- **Protocol:** HELLO/CONFIG/WINDOW/RESULT frames over UART/TCP
- **Timing Semantics:** tin, tstart, tend, tfirst_tx, tlast_tx on device clock
- **Host-Device Synchronization:** Periodic ping frames for clock drift tracking

**Components:**
- Device-side firmware with kernel execution and telemetry reporting
- Host-side adapters for UART/TCP communication
- Protocol implementation for configuration and data exchange
- Timing synchronization and drift compensation

**Documentation:** `docs/development/roadmap.md` lines 133-158

---

### Calibration Harness (Stochastic Modeling)

**Status:** Design documented, not implemented

**Purpose:** Predict real-world deployment latency from HIL measurements using calibrated models.

**Model:** `T_total = a + b × T_kernel + ε`
- **a:** Fixed per-window overhead (ISR entry/exit, DMA setup, wakeups)
- **b:** Multiplicative effects (preemption, cache/bus contention)
- **ε:** Jitter (right-skewed, often lognormal)

**Components:**
1. **Minimal On-Device Calibration Program:**
   - Periodic ISR at sampling rate
   - Double buffer/DMA stub
   - Scheduler wake path (RTOS or bare-metal)
   - Tunable dummy kernel with cycle counting
   - Precise timing (DWT_CYCCNT or GPIO + logic analyzer)
   - CSV logging

2. **Calibration Procedure:**
   - Measure "empty" pipeline to estimate **a** per window
   - Sweep dummy kernel durations and regress total vs kernel time to estimate **b**
   - Collect 5k-10k windows to model jitter **ε** (lognormal distribution)

3. **Output Artifact:**
   - `primitives/configs/calibration/<platform>.yaml` storing:
     - Overhead parameters (a, b, ε distribution parameters)
     - Board/RTOS/toolchain metadata
     - Calibration conditions and date

4. **Usage:**
   - Monte Carlo simulation from HIL `T_kernel` → predict p50/p95/p99 `T_total`
   - Deadline miss probability prediction
   - Safety bands for deployment planning

**Default Planning Factors (when uncalibrated):**
- MCU (Cortex-M + RTOS): 1.5×-2.0× over HIL kernel latency
- FPGA (softcore + DMA/FIFOs): 1.2×-1.5×
- ASIC (well-provisioned datapaths): 1.1×-1.3×

**Documentation:** `docs/architecture/benchmarking-methodology.md` lines 28-37, 80-88

---

### Multi-Device Comparative Benchmarking

**Status:** Planned

**Features:**
- Saturation search to find max channels/hop meeting deadlines per kernel/device
- Comparative analysis across x86 (reference), MCU, and embedded Linux
- Reproducible "apples-to-apples" measurements across compute substrates
- Performance/power/cost trade-off analysis

**Documentation:** `docs/development/roadmap.md` lines 155-158

---

## Fall 2025 (Optional): Current Semester

### Configurable Kernel Parameters

**Status:** Parsed but NOT wired up in harness

**Current Limitation:**
- `kernel_params` set to NULL in `src/engine/harness/app/main.c` lines 82-83
- All v1 kernels use hardcoded parameters:
  - `notch_iir`: f0=60 Hz, Q=30
  - `bandpass_fir`: numtaps=129, passband=[8,30] Hz
  - `goertzel`: alpha (8-13 Hz), beta (13-30 Hz)
  - `car`: No parameters

**Implementation Needed:**
1. Update harness to serialize YAML `params` → `kernel_params` struct
2. Update ALL kernels to parse `kernel_params` if provided, else use defaults
3. Update kernel specs to document parameterization
4. Test parameter validation and error handling

**Benefits:**
- Run same kernel with different parameters without recompiling
- Experiment with filter designs (different notch frequencies, bandpass ranges)
- Support multiple frequency bands for Goertzel

**Code Changes Required:**
- `src/engine/harness/app/main.c` lines 82-83 - Implement kernel_params serialization
- All `primitives/kernels/v1/*/` C implementations - Add parameter parsing
- All `primitives/kernels/v1/*/spec.yaml` - Document parameter schemas

**Documentation:**
- Interface: `docs/reference/plugin-interface.md` lines 95-104
- Overview: `CLAUDE.md` lines 258-267
- FAQ: `docs/FAQ.md` lines 38-44
- Guide: `docs/guides/adding-kernels.md` lines 100, 164

---

### Linux SCHED_DEADLINE Policy

**Status:** Parsed but NOT implemented

**Current Support:** SCHED_FIFO, SCHED_RR, SCHED_OTHER

**What's Missing:**
- Bandwidth-reservation real-time scheduler
- `runtime_us`, `period_us`, `deadline_us` parameters
- `sched_setattr()` system call for SCHED_DEADLINE

**Note:** Per-window deadline checking (whether processing finished before deadline) IS fully implemented. This feature is specifically about the Linux SCHED_DEADLINE scheduling policy.

**Implementation Needed:**
1. Parse SCHED_DEADLINE config from YAML
2. Implement `sched_setattr()` call with SCHED_DEADLINE parameters
3. Handle platform-specific errors (SCHED_DEADLINE only on Linux >= 3.14)
4. Document usage and limitations

**Benefits:**
- Better real-time guarantees with bandwidth reservation
- More predictable scheduling under system load
- Research-grade real-time performance characterization

**Code Changes Required:**
- `src/engine/scheduler/scheduler.c` lines 310-322 - Add SCHED_DEADLINE case

**Documentation:**
- Overview: `CLAUDE.md` lines 389-404
- FAQ: `docs/FAQ.md` lines 73-85

---

### Unimplemented Configuration Fields

**Status:** Documented and PARSED by config loader, but NOT used by harness

**Fields:**
- `system.name`, `system.description` - Run metadata for identification
- `power.governor`, `power.turbo` - CPU power management settings
- `benchmark.metrics` - Metric selection (currently collects all)
- `realtime.deadline.*` - SCHED_DEADLINE parameters
- `plugins[].tolerances` - Per-plugin tolerance overrides
- `plugins[].oracle` - Per-plugin oracle reference paths
- `output.include_raw_data` - Raw telemetry data export flag
- `benchmark.load_profile` - Background load profile
- `benchmark.fail_fast` - Abort on first failure

**Implementation Priority:**
- **High:** `benchmark.fail_fast` - Useful for development
- **Medium:** `power.governor` - Important for reproducibility
- **Medium:** `benchmark.metrics` - Reduce output size for specific analyses
- **Low:** `system.name/description` - Nice metadata for reports

**Documentation:**
- Schema: `docs/reference/configuration.md` lines 9-17
- Overview: `docs/development/roadmap.md` lines 82-94

---

### Background Load Profiles

**Status:** ✅ COMPLETED (November 2024)

**Implemented Features:**
- ✅ stress-ng integration for idle/medium/heavy system load profiles
- ✅ Background load startup/teardown orchestration
- ✅ CPU/memory/IO stress scenarios via stress-ng
- ✅ Load profile definitions (idle=0%, medium=50%, heavy=90% CPU)

**Implementation Details:**
- Config field `benchmark.load_profile` fully implemented in replayer
- Background load functions implemented in `src/engine/replayer/replayer.c`
- Functions: `cortex_replayer_start_background_load()`, `cortex_replayer_stop_background_load()`
- Process management: proper SIGTERM/SIGKILL handling with 2-second timeout
- Platform support: Linux (stress-ng), macOS (graceful degradation)

**Code Location:**
- Implementation: `src/engine/replayer/replayer.c` (functions `prepare_background_load`, `cortex_replayer_start_background_load`, `cortex_replayer_stop_background_load`)
- Integration: `src/engine/harness/app/main.c` lines 108-112, 116, 130
- Header: `src/engine/replayer/replayer.h`

**Documentation:** `docs/development/roadmap.md`

---

## Future/Unscheduled

### Testing & Quality Assurance

#### CI/CD Integration
**Status:** Not configured

**Planned Approach:**
- GitHub Actions on push/PR
- Matrix build: macOS (arm64 + x86_64) × Linux (Ubuntu)
- Run `make -C tests test` and `cortex validate` for all kernels
- Fail on compiler warnings
- Upload test logs as artifacts

**Additional CI/CD Features:**
- Code coverage reporting (lcov/gcov)
- Performance regression tests
- Integration tests (replayer → scheduler → plugin)
- Release workflow for tagged versions
- Multi-architecture testing (ARM, x86_64)

#### Test Gaps

From `docs/architecture/testing-strategy.md`:

- [ ] `--all` flag for `test_kernel_accuracy` - Flag exists but returns "not yet implemented"
- [ ] Performance regression tests - Baseline latency tracking
- [ ] Telemetry output validation - CSV/NDJSON format correctness
- [ ] Config parsing tests - YAML validation and error handling
- [ ] Plugin loading tests - ABI version checking, error paths
- [ ] Deadline miss detection tests - Explicit deadline enforcement validation
- [ ] Oracle unit tests - Python oracle correctness
- [ ] Test coverage reports - lcov/gcov integration
- [ ] Test matrix documentation - Platform × test combinations
- [ ] Synthetic test data - Generated datasets for specific edge cases
- [ ] NaN edge case validation - Oracle comparison on synthetic NaN data

---

### Telemetry & Analysis

#### Enhanced Telemetry
- Multi-session dataset concatenation support
- Per-window energy (E_window) and derived power (P = E_window × Fs/H)
- Summary statistics generation beyond HTML reports (automated p50/p95/p99 aggregates)
- Telemetry validation tests

#### Capability Assessment System

**Status:** Future approach documented

**Vision:** Pre-computed capability database for instant queries

**Components:**
1. **Synthetic Dataset Generation:** Pre-generate realistic EEG-like datasets for standard configurations (64ch→2048ch, 160Hz→500Hz)
2. **System Capability Benchmarking:** Run comprehensive benchmarks once per system
3. **Capability Database:** Store results with system specs and performance limits
4. **Instant Queries:** Answer "Can my system handle 512 channels at 500Hz with kernel X?" in milliseconds

**Benefits:**
- Fast capability queries without data generation overhead
- Reproducible benchmarks across different systems
- Scalable to high channel counts
- User-friendly "system compatibility checker" interface

**Implementation Location:** `datasets/tools/capability_database/`

**Documentation:** `docs/development/roadmap.md` lines 115-131

---

### Code Quality & Cleanup

#### Replayer Improvements
- Remove unused `g_dtype` global or implement proper dtype handling
- Mark `g_replayer_running` as volatile/atomic for thread safety
- Document callback contract (replayer thread, must not block)
- Enforce or validate dataset file format assumptions
- Randomly skip or delay chunks based on configuration

#### Oracle Enhancements
- Configurable `hop_samples` in oracles (currently hardcoded)
- Oracle unit tests to validate reference implementations
- Standalone mode support (currently only `--test` mode works)

#### General Code Quality
- Comprehensive error handling throughout codebase
- Memory leak detection and fixes
- Static analysis integration (clang-tidy, cppcheck)
- Documentation completeness review

**Code References:**
- Replayer TODOs: `src/engine/replayer/replayer.c` lines 14-19, 107, 115, 154, 159, 216, 221
- Oracle TODO: `primitives/kernels/v1/bandpass_fir@f32/oracle.py` line 117

---

### Platform-Specific Future Work

**Out of Scope (per `docs/architecture/platform-compatibility.md`):**
- Additional embedded targets beyond STM32H7 and Jetson
- Windows support
- RISC-V platforms
- FPGA-specific optimizations beyond softcore implementations

---

## Implementation Guidelines

When implementing future enhancements:

1. **Check Dependencies:** Many features depend on others (e.g., quantization requires dtype flexibility in replayer)
2. **Update Documentation:** Modify this document and relevant reference docs
3. **Add Tests:** Include test coverage for new features
4. **Maintain Backwards Compatibility:** Preserve existing APIs and configs
5. **Consider Cross-Platform:** Ensure features work on macOS and Linux (or document platform-specific behavior)
6. **Update CLAUDE.md:** Keep project instructions synchronized

---

## Related Documentation

- **Roadmap:** [roadmap.md](roadmap.md) - Project timeline and milestones
- **Testing Strategy:** [../architecture/testing-strategy.md](../architecture/testing-strategy.md) - Software testing practices
- **Benchmarking Methodology:** [../architecture/benchmarking-methodology.md](../architecture/benchmarking-methodology.md) - HIL vs on-device measurement philosophy
- **Configuration Schema:** [../reference/configuration.md](../reference/configuration.md) - YAML configuration reference
- **Plugin Interface:** [../reference/plugin-interface.md](../reference/plugin-interface.md) - ABI specification
- **Telemetry Format:** [../reference/telemetry.md](../reference/telemetry.md) - Output schema and metrics
