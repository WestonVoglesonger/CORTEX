# 2. Methodological Principles

The 15 user stories in Section 1 span three personas with heterogeneous requirements—accuracy evaluation, latency characterization, platform diagnostics, cross-platform comparison, hardware feasibility. These requirements appear chaotic, but they reduce to five methodological principles. This section defines those principles, shows that every user story maps to at least one, and demonstrates through cross-domain comparison that no existing framework satisfies all five.

## 2.1 Principle Definitions

| # | Principle | Definition | Evaluated By |
| --- | --- | --- | --- |
| P1 | Latency Distribution Capture | The framework reports full latency distributions for each kernel invocation rather than only summary statistics. A user can assess the probability of exceeding a given real-time deadline from the framework's output. | Can a user determine the probability of exceeding a given deadline from the framework's output? |
| P2 | Numerical Correctness as Prerequisite | The framework validates computational outputs against a reference oracle before reporting performance metrics. A benchmark run fails if the kernel produces numerically incorrect results. | Does a benchmark run structurally depend on correctness verification, or is correctness checking optional, separate, or absent? |
| P3 | Single-Variable Isolation | The framework structures experiments so that one parameter varies between runs while all others are held constant. Performance differences between runs are attributable to the varied parameter. | Can a user change one experimental variable and obtain structurally comparable results, with the framework providing structural support for holding other variables constant? |
| P4 | Platform State Observability | The framework records platform-level variables (CPU frequency, governor policy, thermal state, load) alongside performance measurements. A user can correlate latency anomalies with platform state from the framework's own telemetry. | Can a user correlate a latency anomaly with a platform state change (e.g., frequency scaling, thermal throttling) using the framework's own output? |
| P5 | Kernel–Device Latency Analysis | The framework analyzes kernel source and device architecture to produce a predicted latency breakdown by resource category (compute, memory, I/O) prior to execution. | Can a user obtain, before running the benchmark, a predicted breakdown of where kernel execution time will be spent on a given device? |

## 2.2 Why BCI Edge Workloads Require All Five Principles

BCI edge workloads uniquely require all five principles because they combine properties that no single prior domain possesses. They have hard real-time deadlines measured in milliseconds (requiring P1), they perform numerical signal processing where floating-point divergence can silently corrupt classification (requiring P2), they run on heterogeneous edge SoCs where the same algorithm on different cores produces different performance profiles (requiring P3), they execute on passively cooled, battery-constrained devices that actively modulate clock frequency based on thermal state (requiring P4), and their deployment engineers must know whether a kernel is compute-bound, memory-bound, or I/O-bound on the target device to make informed optimization decisions (requiring P5). No prior domain combines sub-millisecond deadline sensitivity with numerical fragility with thermal-driven frequency variation with the need for resource-attributed latency prediction.

Existing frameworks were designed for domains where at least one principle was irrelevant. CPU-saturating compute benchmarks (SPEC, CoreMark) never needed per-invocation distributions because sustained workloads produce stable aggregate throughput. Datacenter latency frameworks (TailBench, DeathStarBench) never needed platform-state observability because servers run with fixed governors and active cooling. ML inference benchmarks (MLPerf) treat correctness as a statistical threshold—a kernel producing wrong outputs for <1% of inputs passes—rather than a structural prerequisite. BCI accuracy benchmarks (MOABB) measure what algorithms compute but not how fast, reflecting a disciplinary blind spot in BCI research. All ten frameworks treat kernels or workloads as opaque executables for timing purposes, providing no pre-execution analysis of how kernel resource requirements interact with device architecture to produce latency.

The Idle Paradox validates this argument empirically. In CORTEX's cross-load-profile experiments on an Apple M1 platform (n ≈ 1,200 measurements per kernel per load profile, p < 0.001 via Welch's t-test), standard BCI kernels exhibited ~50% latency degradation when benchmarked on idle systems versus medium-load conditions. macOS DVFS policies misinterpreted bursty, low-duty-cycle BCI workloads as idle, downclocking the CPU and incurring wake-up penalties. This is a systematic error that frameworks lacking platform-state observability (P4) structurally cannot detect, and that frameworks reporting only summary statistics (lacking P1) would average away.

## 2.3 Principle Traceability

Every user story from Section 1 maps to at least one methodological principle. The table below provides the compact reference; per-principle rationale follows.

| ID | User Story | P1 | P2 | P3 | P4 | P5 |
| --- | --- | --- | --- | --- | --- | --- |
| AR-1 | Evaluate accuracy AND real-time feasibility | ✓ | ✓ | ✓ | | |
| AR-2 | Contribute Python oracle for benchmarking | | ✓ | | | |
| SE-1 | Characterize latency distribution on target device | ✓ | | | ✓ | |
| SE-2 | Compare two implementations on same platform | ✓ | | ✓ | | |
| SE-3 | Validate correctness after dtype conversion | | ✓ | | | |
| SE-4 | Characterize platform state effects on latency | ✓ | | ✓ | ✓ | |
| SE-5 | Determine if kernel is compute/memory/IO-bound | | | | ✓ | ✓ |
| SE-6 | Benchmark latency distribution under sustained load | ✓ | | | | |
| SE-7 | Understand why P99 is 4× worse than P50 | ✓ | | | ✓ | ✓ |
| SE-8 | Benchmark end-to-end pipeline latency | ✓ | ✓ | ✓ | | |
| SE-9 | Stress test with synthetic high-channel data | ✓ | | ✓ | | |
| SE-10 | Calibrate kernel, save params, benchmark | | ✓ | | | |
| SE-11 | Generate latency reports (CDF, deadline miss rate) | ✓ | | | | |
| HE-1 | Compare HLS vs hand-coded Verilog on FPGA | ✓ | ✓ | ✓ | | ✓ |
| HE-2 | Benchmark kernel on ARM vs FPGA fabric | ✓ | ✓ | ✓ | ✓ | ✓ |

Coverage summary: P1 (latency distribution capture) is the most broadly required principle, supporting 12 of 15 user stories across all three personas. P2 (correctness prerequisite) supports 7 stories and is the only principle required by all three personas for distinct reasons. P3 (single-variable isolation) supports 8 stories and is essential wherever comparative benchmarking occurs. P4 (platform state observability) supports 4 stories concentrated in the SE persona where platform effects are first-order concerns. P5 (kernel–device latency analysis) supports 4 stories and provides the diagnostic capability that distinguishes CORTEX from a pure measurement framework.

### Per-Principle Dependencies

**P1: Latency Distribution Capture**

Software Engineer: Must determine whether a kernel meets a real-time deadline at P99, not just on average. A kernel with safe median latency can still violate deadlines at the tail (SE-1, SE-6, SE-7, SE-11). Algorithm Researcher: Needs to know if a C implementation can meet real-time constraints before investing in optimization; distributional data reveals whether feasibility is marginal or comfortable (AR-1). Hardware Engineer: Compares latency distributions across implementation targets (ARM vs. FPGA) to justify the cost of custom hardware (HE-1, HE-2).

**P2: Numerical Correctness as Prerequisite**

Software Engineer: Porting kernels across dtypes (float32 → fixed16) or platforms can introduce silent numerical divergence; oracle validation catches this before latency measurement begins (SE-3). Algorithm Researcher: Contributes Python algorithms as oracles so others can implement and benchmark optimized versions with guaranteed correctness (AR-2). Hardware Engineer: HLS and hand-coded RTL must produce outputs matching the behavioral reference; bit-width truncation and fixed-point rounding require validation (HE-1).

**P3: Single-Variable Isolation**

Software Engineer: Comparing two filter implementations requires isolating the kernel while holding dataset, device, load profile, and configuration constant (SE-2); characterizing platform effects requires varying load while holding the kernel constant (SE-4). Algorithm Researcher: Evaluating whether a C implementation meets constraints requires comparison against the oracle under identical conditions (AR-1). Hardware Engineer: Comparing HLS vs. hand-coded Verilog, or ARM vs. FPGA fabric, requires isolating the implementation variable (HE-1, HE-2).

**P4: Platform State Observability**

Software Engineer: Must distinguish between algorithmic latency and environmental overhead. Variable platform states (thermal throttling, DVFS, OS noise) introduce artifacts into measurements. P4 enables engineers to attribute latency spikes to the platform rather than the code—e.g., distinguishing code inefficiency from Idle Paradox downclocking (SE-1, SE-4, SE-5, SE-7). Hardware Engineer: SoC FPGAs (Zynq) share memory buses between ARM cores and FPGA fabric; platform state on the ARM side affects FPGA-side latency through bus contention (HE-2).

**P5: Kernel–Device Latency Analysis**

Software Engineer: When a kernel runs slower than expected, the engineer must know whether to optimize compute, memory access patterns, or I/O; total latency alone does not answer this question (SE-5). Hardware Engineer: Comparing resource bottlenecks across ARM vs. FPGA reveals whether custom hardware addresses the actual bottleneck or just shifts it; FPGA synthesis reports provide this natively—CORTEX normalizes the representation across device classes (HE-1, HE-2).

## 2.4 Cross-Domain Comparison

Ten frameworks from five domains evaluated against CORTEX's five methodological principles. Detailed scoring justifications are provided in [Appendix A](appendix-a-scoring-justifications.md).

| Framework | Domain | P1: Distrib. | P2: Correct. | P3: Isolation | P4: Platform | P5: Analysis |
| --- | --- | --- | --- | --- | --- | --- |
| BCI2000 | BCI | Partial | No | Partial | No | No |
| MOABB | BCI | No | No | No | No | No |
| MLPerf Inference | ML | Yes | Partial | Yes | No | No |
| TailBench | Datacenter | Yes | No | Partial | No | No |
| SPEC CPU 2017 | Compute | No | Yes | Yes | Partial | No |
| EEMBC CoreMark | Embedded | No | Yes | Partial | No | No |
| Dhrystone | Embedded | No | No | No | No | No |
| DeathStarBench | Microservices | Yes | No | Partial | No | No |
| SeBS | Serverless | Yes | No | Partial | No | No |
| MiBench | Embedded | No | No | No | No | No |
| **CORTEX** | **BCI/Edge** | **Yes** | **Yes** | **Yes** | **Partial** | **Yes** |

Frameworks: BCI2000 (Schalk et al., 2004), MOABB (Jayaram & Barachant, 2018), MLPerf Inference (Reddi et al., 2020), TailBench (Kasture & Sanchez, 2016), SPEC CPU 2017, EEMBC CoreMark, Dhrystone (Weicker, 1984), DeathStarBench (Gan et al., 2019), SeBS (Copik et al., 2021), MiBench (Guthaus et al., 2001).

## 2.5 Gap Analysis

### The Methodological Gap

Across all ten frameworks, the maximum number of principles any single framework satisfies with a "Yes" is two. MLPerf Inference comes closest (Yes on P1 and P3, Partial on P2, No on P4 and P5), but its correctness checking is a statistical threshold (≥99% aggregate accuracy), not per-invocation oracle validation. SPEC CPU 2017 achieves Yes on P2 and P3 but reports no distributional latency data, captures only static platform metadata, and provides no kernel–device latency analysis. No framework exceeds two "Yes" scores.

The specific gap is the simultaneous conjunction of all five principles. Individual principles are well-served in isolation: latency distribution capture is standard in server-oriented frameworks (MLPerf, TailBench, DeathStarBench, SeBS), correctness gating is routine in compute benchmarks (SPEC, CoreMark), and single-variable isolation has strong precedent in standards-body frameworks (MLPerf Closed division, SPEC base rules). But platform-state observability and kernel–device latency analysis are absent across the board—no framework scores "Yes" on P4 or P5. SPEC CPU 2017 earns a lonely "Partial" on P4: its sysinfo tool captures static MHz and power-management settings, and its optional PTDaemon integration records wall-level power and ambient temperature time-series, but neither tool captures the on-die CPU frequency transitions, governor state changes, or junction thermal events that drive the Idle Paradox.

The gap is defined by three intersecting deficits. First, P4 is universally unmet. Second, P5 is universally unmet. Third, no framework combines either P4 or P5 with the other three. A reviewer might ask: why not simply run external monitoring tools (turbostat, perf) alongside an existing framework? The answer is that integrated telemetry enables per-invocation temporal correlation between platform state transitions and individual kernel latencies at microsecond resolution. Post-hoc joining of independently timestamped tool outputs cannot reliably achieve this alignment, particularly when the events of interest—DVFS transitions—occur on the same timescale as the measurements themselves. Similarly, a reviewer might ask: why not profile kernels with external tools like VTune or cachegrind? The answer is that CORTEX's kernel–device analysis is structural—it derives from the plugin ABI's kernel specification and the device adapter's declared characteristics, producing predictions before execution that are then fitted to measured distributions and platform-state telemetry.

### Why the Gaps Exist: Domain-Specific Design Rationales

**CPU-saturating compute benchmarks (SPEC, CoreMark, Dhrystone, MiBench)**

These target workloads that fully utilize the processor for seconds to minutes. When a benchmark runs for 400 seconds of sustained computation, per-invocation latency distributions are meaningless—what matters is aggregate throughput. Platform-state observability was historically unnecessary because sustained compute drives the processor to thermal steady state: the governor settles, the clock stabilizes. Short, bursty kernels that never reach thermal steady state break this assumption entirely.

**Datacenter latency frameworks (TailBench, DeathStarBench)**

These excel at P1 because tail latency under load is their raison d'être. They omit P2 because their applications are mature production software where computational correctness is solved. They omit P4 because datacenter servers typically run with fixed CPU governors (performance mode), disabled turbo boost, and active cooling. Their focus is software-level sources of tail latency (queuing, lock contention, GC), not hardware-level sources. Edge devices, by contrast, actively throttle under thermal constraints as a design feature, not a failure mode.

**ML inference benchmarks (MLPerf Inference)**

MLPerf satisfies P1 and P3 fully and comes closest to P2, but its quality threshold is statistical rather than structural: a submission achieving ≥99% aggregate accuracy passes even if individual inferences produce incorrect outputs. This design reflects ML's tolerance for approximate computation—acceptable for neural network inference where minor output variations are expected, but insufficient for BCI signal processing where a single corrupted FFT bin can propagate through the classification pipeline. MLPerf omits P4 because its primary targets—GPUs, TPUs, and datacenter accelerators—operate with fixed clock profiles and active cooling.

**BCI accuracy benchmarks (MOABB)**

MOABB omits all five principles for latency benchmarking because it was designed for an entirely different question: which classification pipeline achieves the best accuracy? Computational latency was never in scope because MOABB operates offline. This reflects a disciplinary blind spot: the BCI field has robust methodology for evaluating what algorithms compute but almost none for evaluating how fast they compute it on target hardware.

**Why no framework provides kernel–device latency analysis (P5)**

Every framework in the comparison table treats its workloads as opaque executables. SPEC runs compiled binaries and measures elapsed time. MLPerf packages models as inference engines. TailBench wraps server applications. Even frameworks with access to source code (CoreMark, Dhrystone) provide no tooling to analyze how a kernel's instruction mix and memory access patterns interact with a specific device's microarchitecture to produce latency. This is a rational design choice for domains where the user's question is "how fast is this workload?" rather than "why is this workload slow?" BCI deployment engineers need the latter—they must decide whether to restructure memory access patterns, reduce arithmetic complexity, or move I/O off the critical path, and total latency alone does not answer that question.

CORTEX addresses this gap by being the first framework designed to structurally require all five: per-kernel latency distributions, correctness-gated runs, single-variable experiment structure, concurrent platform-state telemetry, and pre-execution kernel–device latency analysis fitted to measured data. Kernel–device analysis (P5) is implemented via a 3-step workflow: `cortex predict` produces pre-benchmark Roofline predictions (compute/memory attribution from spec.yaml annotations and optional PMU instruction counting), `cortex run` captures per-window PMU telemetry (instruction count, cycle count, backend stall cycles), and `cortex decompose` performs post-hoc characterization with IPC, effective frequency, frequency tax, and compute-vs-memory-stall decomposition. The Roofline model provides regime classification (compute-bound vs memory-bound) and relative kernel ranking, not accurate absolute latency estimates—on out-of-order cores with deep memory hierarchies, theoretical floors underestimate measured latency by 10–100× due to microarchitectural effects (pipeline bubbles, cache coherence, speculative execution overhead) that static analysis cannot capture. The 3-step workflow addresses this by design: `predict` classifies the bottleneck regime, then `decompose` fits measured PMU data to quantify the actual overhead breakdown, closing the gap between theoretical classification and observed performance. `cortex decompose` also provides tail-latency attribution (SE-7): three-tier analysis that answers *why* P99 exceeds P50—Tier 1 computes P99/P50 ratios and noop-normalized verdicts (platform-dominated vs algorithmic), Tier 2 uses Mann-Whitney U tests to identify platform covariates statistically elevated in tail windows, and Tier 3 applies Shapley R² variance decomposition to attribute latency variance across platform factors and algorithmic residual. Platform-state capture (P4) remains a partial implementation—per-window CPU frequency (sysfs on Linux, PMU-derived on both platforms), per-window osnoise (Linux tracefs), PMU counters (instruction count, cycle count, backend stall cycles), and run-level governor/thermal are captured. SE-7 tail attribution statistically correlates these covariates with tail latency. Missing: per-window thermal telemetry (only run-level snapshot) and macOS has no userspace frequency interface (Apple Silicon returns 0 for sysfs freq, but PMU-derived effective frequency compensates).

## 2.6 Principle Applicability Across Device Classes

CORTEX's five principles are universal in intent but vary in manifestation and implementation difficulty across device classes. The table below characterizes how each principle applies to the four device classes CORTEX targets through its device adapter interface.

| Principle | CPU / SoC | MCU (Bare-Metal) | FPGA | ASIC |
| --- | --- | --- | --- | --- |
| P1: Latency Distribution Capture | Essential. DVFS, OS scheduling, and thermal throttling create wide distributions. The Idle Paradox demonstrates ~50% degradation from frequency scaling alone. | Relevant. No OS jitter, but interrupt latency, DMA contention, and peripheral timing create narrower but non-trivial distributions. | Relevant. Execution is cycle-deterministic for pure logic, but DRAM refresh, bus arbitration on SoC FPGAs (Zynq), and thermal management create measurable variation. | Relevant. Memory controller latency varies with bank conflicts and refresh; multi-block SoCs have bus arbitration. Distributions are tightest but non-zero. |
| P2: Correctness Prerequisite | Essential. FP behavior varies across ISAs and compiler optimization levels. Oracle validation catches silent divergence. | Essential. Fixed-point implementations require validation against FP oracles to quantify accuracy loss. | Essential. HLS-generated and hand-coded RTL must be validated against behavioral references. Bit-width truncation and rounding differences are common. | Essential. Post-synthesis netlists must produce correct outputs. Validation against RTL behavioral model is standard; CORTEX extends this to the algorithmic oracle. |
| P3: Single-Variable Isolation | Essential. Many confounding variables (governor, thermal state, co-running processes, compiler flags) require structural isolation. | Relevant. Fewer confounds (no OS, fixed clock), but ISR configuration, DMA, and memory layout still require controlled comparison. | Essential. Synthesis tool version, placement seed, clock constraint, and resource utilization all affect timing. | Essential. PVT and synthesis constraints create a large design space. Single-variable isolation is standard methodology in design-space exploration. |
| P4: Platform State Observability | Essential and hardest. DVFS, thermal throttling, governor policy, and co-tenant load are first-order latency determinants. | Trivially satisfied. Clock is fixed, no OS scheduler, no DVFS. Platform state is static by design—recording confirms the assumption. | Relevant. SoC FPGAs have thermal management and clock scaling. Less dynamic than CPUs but not static. | Relevant. Modern ASICs include DVFS and thermal management. Recording operating point and junction temperature validates timing assumptions. |
| P5: Kernel–Device Analysis | Essential and hardest. Microarchitectural opacity (OoO execution, speculative prefetch) requires reconstruction from static analysis + counters + fitting. | Useful and simpler. In-order cores with predictable timing make static analysis more accurate. Cycle counts often deterministic. | Useful and natively supported. Post-P&R reports provide resource-attributed timing: LUT delay, DSP latency, BRAM access, routing delay. | Most precise. Static timing analysis provides gate-level delay attribution and exact critical-path decomposition by resource type. |

### Key Observation

The principles are universal but the difficulty gradient inverts across device classes. P4 (platform state observability) is hardest on CPUs where it matters most and trivially satisfied on MCUs where the platform is static. P5 (kernel–device latency analysis) is hardest on CPUs where microarchitectural opacity obscures resource attribution, and natively supported on FPGAs/ASICs where synthesis tools provide the breakdown. This inversion means CORTEX's novel engineering contribution is concentrated where commodity deployment targets require it—on the CPUs and SoCs where BCI processing will actually run at scale.

The comparison table confirms this prediction: no existing framework satisfies all five principles, and the gaps align precisely with the domain-specific design rationales described above. Section 3 presents the system design that embodies these principles.
