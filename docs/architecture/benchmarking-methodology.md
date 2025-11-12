# Benchmarking Methodology

This document describes CORTEX's benchmarking approach across development phases: x86 host-based profiling (Fall 2025) and hardware-in-the-loop device testing (Spring 2026).

---

## Overview

CORTEX measures BCI kernel performance using a **two-phase approach**:

1. **Fall 2025:** x86 host-based kernel profiling for algorithmic baselines
2. **Spring 2026:** Hardware-in-the-loop (HIL) testing with embedded device adapters

This progression enables early algorithm comparison and optimization on x86, followed by real-world embedded deployment characterization.

---

## Fall 2025: x86 Host-Based Kernel Profiling

### What It Is

A benchmarking harness running entirely on x86 development machines (macOS/Linux). Kernels are compiled as shared libraries (`.dylib`/`.so`) and loaded dynamically via the plugin ABI. The replayer, scheduler, and telemetry all execute in the same host process.

**Architecture:**
```
┌─────────────────────────────────────────────┐
│        x86 Host Machine (macOS/Linux)       │
│                                             │
│  Replayer ──→ Scheduler ──→ Plugin Loader  │
│   (EEG @Fs)    (Windows,       (dlopen)    │
│                Deadlines)          │       │
│                                    ↓       │
│                         Kernel Plugin      │
│                         (CAR, IIR, FIR,    │
│                          Goertzel)         │
│                                    │       │
│                         Telemetry ←┘       │
│                         (CSV/NDJSON)       │
└─────────────────────────────────────────────┘
```

### What We Measure

**Per-Window Metrics:**
- **Latency:** Kernel execution time (p50, p95, p99)
- **Jitter:** Timing variance (p95-p50, p99-p50)
- **Deadline Misses:** `(end_ts - start_ts) > (H / Fs)`
- **Memory Footprint:** Allocated state size
- **Energy:** x86 CPU energy via RAPL counters (Linux only)

**Aggregate Metrics:**
- Latency distributions across all windows
- Deadline miss rate (percentage)
- Throughput (windows/second vs `Fs/H` requirement)

**Output Formats:**
- Per-window telemetry: NDJSON or CSV
- Summary statistics: HTML report with plots

### What We DON'T Measure

This approach provides **algorithmic lower bounds** and does NOT capture:

- ❌ **RTOS overhead** - Task switching, interrupt latency, scheduler delays
- ❌ **DMA setup costs** - Memory transfers, bus arbitration
- ❌ **Context switching** - Multi-tasking interference
- ❌ **Bus contention** - Shared memory bandwidth limits
- ❌ **Thermal effects** - Throttling, temperature-dependent performance
- ❌ **Real device power** - x86 RAPL ≠ MCU/ASIC power consumption

**Expected Overhead on Real Devices:**
- **MCU (Cortex-M + FreeRTOS):** 1.5×-2.0× latency increase
- **FPGA (softcore + DMA):** 1.2×-1.5× latency increase
- **ASIC (dedicated datapath):** 1.1×-1.3× latency increase

These are **planning factors**, not measured values. Spring 2026 work will empirically characterize overhead.

### Use Cases

**When to use x86 host-based profiling:**
- ✅ Compare kernel algorithms (CAR vs notch_iir performance)
- ✅ Test quantization strategies (float32 vs Q15 vs Q7)
- ✅ Validate numerical correctness against oracles
- ✅ Establish reproducible baselines for cross-kernel comparison
- ✅ Early-stage algorithm selection before hardware commitment
- ✅ Academic reproducibility (common x86 platforms)

**When NOT to use:**
- ❌ Predicting exact embedded deployment latency
- ❌ Validating real-time guarantees for production systems
- ❌ Measuring actual device power consumption
- ❌ Characterizing multi-kernel pipeline interference

### Scope and Limitations

**Documented Limitations:**
All reports and publications must clearly state:
- Results are algorithmic lower bounds
- Real embedded systems will have additional overhead
- x86 energy measurements are not representative of MCU/ASIC power
- Conservative safety factors must be applied for deployment planning

**Pass/Fail Criteria:**
- **Pass:** p95 latency < 50% of deadline (500ms window)
- **Caution:** 50-65% of deadline
- **Fail:** >65% of deadline OR any deadline misses

These thresholds account for expected embedded overhead.

---

## Spring 2026: Hardware-in-the-Loop (HIL) Testing

### What It Is

True hardware-in-the-loop testing where the host harness streams data to embedded devices over UART or TCP. The device runs the kernel, measures device-side timestamps, and returns results. This captures real embedded system overhead.

**Architecture:**
```
┌──────────────────────┐                    ┌─────────────────────┐
│   x86 Host Machine   │                    │   Target Device     │
│                      │   UART/TCP         │                     │
│  Replayer            │──────────────────→ │  Device Adapter     │
│  Scheduler           │                    │  • Parse frames     │
│  Harness             │                    │  • Manage state     │
│                      │                    │  • Call kernel      │
│                      │ ←──────────────────│  • Measure timing   │
│  Telemetry           │   Results          │  • Sample energy    │
│  • Device timestamps │                    │                     │
│  • Energy            │                    │  Kernel (C/CMSIS)   │
│  • Kernel outputs    │                    │  • CAR, IIR, FIR    │
└──────────────────────┘                    └─────────────────────┘
```

### Target Devices

**Three device classes:**

1. **x86 (Reference)**
   - Development machine baseline
   - Shared library plugins
   - RAPL energy measurement
   - Already implemented (Fall 2025)

2. **MCU-Class (STM32H7)**
   - Bare-metal or FreeRTOS
   - UART communication (1-3 Mbaud, USB-CDC optional)
   - Statically linked kernels
   - Energy via INA226 shunt sensor
   - **Planned:** Spring 2026

3. **Embedded Linux (Jetson Orin Nano / Raspberry Pi)**
   - Linux userspace process
   - TCP communication (USB-RNDIS/Ethernet)
   - Shared library kernels (dlopen)
   - Energy via tegrastats/board sensors
   - **Planned:** Spring 2026

### Communication Protocol

**Frame-Based Protocol (UART/TCP):**
- `HELLO` - Device capability negotiation
- `CONFIG` - Echo runtime parameters (Fs, W, H, C, dtype)
- `WINDOW` - W×C f32 samples (little-endian, interleaved)
- `RESULT` - Device timestamps + kernel outputs
- `ERROR` - Protocol or kernel errors

**Device Timing Semantics:**
Each adapter records five timestamps per window (device clock):
- `tin` - Last input sample arrives at adapter
- `tstart` - Kernel `process()` invoked
- `tend` - Kernel `process()` returns
- `tfirst_tx` - First output byte transmitted
- `tlast_tx` - Last output byte transmitted

**Derived Metrics:**
- **Ingress latency:** `tstart - tin`
- **Kernel latency:** `tend - tstart` (primary metric)
- **Egress gap:** `tfirst_tx - tend`
- **Serialization latency:** `tlast_tx - tfirst_tx`
- **Device E2E (first):** `tfirst_tx - tin`
- **Device E2E (complete):** `tlast_tx - tin`

**Deadline Enforcement:**
Deadline misses scored using kernel latency only: `(tend - tstart) > H/Fs`

### Energy Measurement

**Platform-Specific Approaches:**

| Platform | Method | Precision | Notes |
|----------|--------|-----------|-------|
| x86 | RAPL (sysfs) | Package-level | Planned for Spring 2026 |
| STM32H7 | INA226 shunt | Per-rail | Requires GPIO triggers for alignment |
| Jetson | tegrastats | Board sensors | Records temp/rail flags |

**Energy Synchronization:**
- Kernels, adapters, and OS share power domains
- **Challenge:** Isolate kernel energy from adapter/OS overhead
- **Approach:** GPIO triggers to align external energy traces with execution intervals
- **Validation:** One platform validated against external meter

### Overhead Characterization

**Goal:** Empirically measure embedded system overhead vs x86 baseline.

**Method:**
1. Run same kernel configurations on x86 and embedded devices
2. Compare device latency to x86 latency
3. Compute overhead factors per device class
4. Publish overhead factors for deployment planning

**Output:**
- Overhead factors (measured vs x86 baseline)
- Platform-specific latency distributions
- Energy per window per device
- Thermal/throttling characterization

### Saturation Search

**Objective:** Find maximum channel count and hop size meeting real-time deadlines per kernel/device combination.

**Method:**
1. Start with baseline configuration (64 channels, 80-sample hop)
2. Incrementally increase workload (more channels or smaller hop)
3. Record when deadline miss rate exceeds threshold (>5%)
4. Document saturation point per kernel/device

**Output:**
Capability matrix showing maximum sustainable configuration per kernel/device.

---

## Comparison: x86 vs HIL

| Aspect | x86 Host-Based (Fall 2025) | HIL with Devices (Spring 2026) |
|--------|---------------------------|--------------------------------|
| **What's Measured** | Kernel algorithm performance | Real embedded system performance |
| **Overhead** | None (algorithmic baseline) | RTOS, DMA, interrupts, bus contention |
| **Energy** | x86 CPU (RAPL) | Device-specific (INA226, tegrastats) |
| **Complexity** | Low (shared library loading) | High (device protocol, cross-compilation) |
| **Reproducibility** | Excellent (common x86 platforms) | Good (standardized devices, documented setup) |
| **Use Case** | Algorithm selection, quantization testing | Deployment validation, platform comparison |
| **Results** | Lower bounds | Deployment-realistic |

---

## Why Start with x86?

**Advantages:**
1. **Fast iteration** - Compile and test kernels in seconds
2. **Easy debugging** - Full toolchain, debuggers, profilers
3. **Numerical validation** - Oracle comparison without device complexity
4. **Reproducible** - Common development machines, no hardware dependencies
5. **Algorithm focus** - Isolate kernel efficiency from platform effects

**Foundation for HIL:**
- Validates kernel correctness before device deployment
- Establishes baseline for overhead comparison
- Identifies best-performing algorithms for embedded implementation
- Enables quantization testing without device constraints

---

## Reporting Guidelines

### x86 Host-Based Results

**Must Include:**
- Statement: "Results are algorithmic lower bounds measured on x86"
- Platform specs (CPU model, frequency, RAM, OS)
- Safety factor note: "Real embedded systems will have 1.5-2.0× overhead"
- RAPL energy caveat: "x86 CPU power, not representative of MCU/ASIC"

**Report Format:**
- Latency distributions (p50/p95/p99) per kernel
- Deadline miss rates
- Memory footprints
- Comparative rankings across kernels

### HIL Device Results

**Must Include:**
- Device specifications (MCU/SoC model, RTOS version, compiler)
- Communication overhead (ingress + egress + serialization)
- Energy measurement method and validation
- Thermal conditions (temperature ranges, throttling events)
- Overhead factor vs x86 baseline

**Report Format:**
- Device-specific latency distributions
- Cross-device comparisons
- Energy per window per device
- Saturation points (max channels/hop)

---

## Implementation Timeline

### Fall 2025 (Completed)
- ✅ x86 harness (replayer, scheduler, plugin ABI)
- ✅ Kernel implementations (CAR, notch_iir, bandpass_fir, goertzel)
- ✅ Numerical validation against oracles
- ✅ Telemetry output (CSV/NDJSON + HTML reports)

### Spring 2026 (Planned)
- Device adapters:
  - STM32H7 (UART, statically linked)
  - Jetson Orin Nano (TCP, shared libraries)
- Communication protocol implementation
- Energy integration:
  - RAPL for Linux x86
  - INA226 for STM32H7
  - tegrastats for Jetson
  - GPIO-triggered alignment
  - External meter validation (one platform)
- Overhead characterization
- Saturation search automation

### Success Criteria (Spring 2026)
- Adapter overhead < 5% of total latency
- Measurement reproducibility ±3% across runs
- Real-time pass (deadline miss rate <5%) at baseline configuration on at least one embedded target
- Energy measurement validated against external meter

---

## Risks and Mitigations

### Clock Drift and Synchronization
**Risk:** Host and device clocks drift over long runs
**Mitigation:** Periodic ping frames estimate host-device offset; echo mode detects buffering

### Energy Measurement Accuracy
**Risk:** Kernel, adapter, and OS share power domains; hard to isolate kernel energy
**Mitigation:** GPIO-triggered alignment, baseline subtraction, external meter validation

### Thermal Throttling
**Risk:** Embedded devices may downclock under sustained load
**Mitigation:** Record temperature/rail flags, tag affected runs as unstable, document thermal conditions

### Transport Bandwidth
**Risk:** UART bandwidth (~95 kB/s @ 1 Mbaud) may constrain large transfers
**Mitigation:** Higher baud rates, batched windows, prefer TCP for Linux-class devices

### Scope Creep
**Risk:** Feature requests delay core deliverables
**Mitigation:** Strict spec versioning, milestone isolation, minimal adapters first

---

## Related Documentation

- **Testing Strategy:** [testing-strategy.md](testing-strategy.md) - Software testing practices
- **Future Enhancements:** [../development/future-enhancements.md](../development/future-enhancements.md) - Planned features beyond Spring 2026
- **System Overview:** [overview.md](overview.md) - Architecture and component design
- **Telemetry Format:** [../reference/telemetry.md](../reference/telemetry.md) - Output schema and metrics
- **Plugin Interface:** [../reference/plugin-interface.md](../reference/plugin-interface.md) - Kernel ABI specification

---

## References

- Original Proposal: "Benchmarking BCI Kernels: A Pipeline for Real-Time Performance Analysis" (Sept 2025)
- Implementation Plan: "Brain-Computer Interface Benchmark Project Plan" (Sept 23, 2025)
- Embedded Extension: "CORTEX: Extending BCI Kernel Benchmarking to Embedded Devices" (Oct 23, 2025)
