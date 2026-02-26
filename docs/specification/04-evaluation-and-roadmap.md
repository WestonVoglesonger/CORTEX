## 4. Evaluation & Roadmap

### 4.1 Priority Tiers

Capabilities are organized into priority tiers reflecting implementation urgency and research value. **Complexity:** Low = days, Medium = weeks, High = multi-week.

| Tier | Capability | Complexity | Strategy | Key Prior Art |
|------|-----------|------------|----------|---------------|
| Tier 1 | Pipeline composition | High | Implemented | Darkroom streaming, ILP buffer scheduling |
| Tier 1 | Device adapters | High | Adapt | |
| Tier 1 | Latency decomposition (incl. SE-7 tail attribution) | High | Implemented | Roofline, nn-Meter |
| Tier 2 | Deadline analysis CLI | Low | Adapt | LTTng, Cyclictest, WCET |
| Tier 2 | Comparative analysis CLI | Low | Implemented | MLPerf stats, Welch t-test, Cohen's d |
| Tier 2 | Platform-state (full) | Medium | Reuse | perf/ftrace, sysfs, eBPF |
| Tier 2 | Multi-dtype (Q15) | Medium | Implemented | CMSIS-DSP Q15 |
| Tier 2 | Mandatory reporting | Low | Adapt | EEMBC CoreMark, MLPerf |
| Tier 2 | Statistical confidence (CI) | Low | Implemented | MLPerf, Kalibera & Jones |
| Tier 2 | Scenario-based (Streaming) | Medium | Adapt | MLPerf scenarios |
| Tier 2 | Oracle workflow CLI | Low | Adapt | MOABB, MLPerf reference |
| Tier 3 | Diagnostic framework | High | Adapt | Roofline, async-profiler, eBPF |
| Tier 3 | Device adapters (FPGA) | High | Reuse | OpenOCD, CMSIS-DAP, dSPACE |
| Tier 3 | Power/energy | Medium | Adapt | SPEC PTDaemon, MLPerf Tiny, Foresee |
| Tier 3 | SNR validation | Low | Innovate | CMSIS-DSP, EEMBC AudioMark |
| Tier 3 | Scaled tolerance | Medium | Innovate | LAPACK, Higham |
| Tier 3 | Hardware feasibility | High | Integration | Foresee, Yosys/OpenSTA |
| Tier 3 | Performance counters | Medium | Adapt | Linux perf, VTune, ARM Streamline, PAPI |
| Defer | Efficacy benchmarking | — | Defer | MOABB |
| Defer | Labeled datasets | — | Defer | MOABB, PhysioNet |

### 4.2 Build Strategy Summary

| Strategy | Count | Capabilities |
|----------|-------|-------------|
| **Implemented** | 19 | Oracle validation, component separation, SSH deployment, transports, protocol, native adapter, kernel calibration, synthetic datasets, sustained measurement, warmup, load profiles, two-phase measurement, statistical confidence (CI), latency distribution, analysis/reporting, comparative analysis, pipeline composition, latency decomposition, multi-dtype (Q15) |
| **Reuse** | 3 | stress-ng (load profiles), perf/ftrace (platform-state), OpenSSH+rsync (deployment) |
| **Adapt** | 8 | Platform-state, deadline analysis, mandatory reporting, oracle workflow, scenario-based, power measurement, diagnostic framework, performance counters |
| **Innovate** | 2 | SNR validation, scaled tolerance |
| **Defer** | 3 | Labeled datasets (MOABB), efficacy benchmarking (MOABB), hardware feasibility (Foresee) |

### 4.3 Key Research Insights

What CORTEX does that no prior work does:

1. **Oracle-first validation before performance measurement.** Unlike SPEC, MLPerf, and EEMBC, which either gate on aggregate quality or separate correctness from timing, CORTEX structurally requires per-invocation correctness verification as a prerequisite to benchmark execution.

2. **Platform state as experimental variable, not noise to eliminate.** The Idle Paradox demonstrates that platform state is a first-order determinant of BCI kernel latency. CORTEX records and correlates platform state with per-window timing, enabling causal attribution of latency anomalies.

3. **Window-based latency distributions at streaming cadence.** CORTEX measures per-window latency at 160 Hz streaming cadence with full distributional reporting (P50/P95/P99), capturing the tail behavior that determines real-time safety.

4. **Sub-100µs kernel measurement where DVFS transitions dominate.** BCI kernels execute in 20–100µs, a timescale where DVFS transitions are the primary source of latency variation—a regime no existing framework was designed to characterize.

5. **BCI-specific correctness + latency co-evaluation.** MOABB provides accuracy-only evaluation; fio and TailBench provide latency-only measurement. CORTEX is the first framework to combine numerically validated correctness with distributional latency analysis for BCI workloads.