# CORTEX

## Common Off-implant Runtime Test Ecosystem for BCI Kernels

### Master Specification

Weston Voglesonger  |  Advisor: Dr. Raghavendra Pothukuchi
University of North Carolina at Chapel Hill  |  Spring 2026

## Executive Summary

CORTEX is a benchmarking framework for BCI signal-processing kernels on real deployment hardware. It provides oracle-validated correctness, distributional latency reporting (P50/P95/P99), and controlled measurement under platform effects (DVFS, thermal throttling, scheduling noise). Unlike MOABB (offline accuracy evaluation) and BCI2000/OpenViBE (runtime platforms for controlled lab environments), CORTEX targets deployment-grade performance engineering on commodity edge devices—phones, wearables, and embedded Linux SoCs—where platform state dictates real-time safety as much as algorithmic complexity.

This specification establishes CORTEX's requirements by tracing from user needs through methodological principles to system capabilities and architecture. It follows a top-down structure: the BCI deployment problem motivates user needs, which reduce to five methodological principles, which are embodied in system capabilities and architecture.

## 1. The BCI Deployment Problem

Brain-computer interfaces translate neural activity into commands for external devices, enabling communication, motor restoration, and therapeutic intervention for patients with neurological conditions. The field has achieved remarkable clinical demonstrations: paralyzed patients controlling cursors, walking via thought-driven exoskeletons, and communicating through implanted speech decoders. Commercial interest is accelerating, with companies spanning invasive implants (Neuralink, Synchron, Blackrock Neurotech, Precision Neuroscience) and non-invasive systems (InteraXon, Cognixion, Kernel).

Yet a critical infrastructure gap separates these demonstrations from scalable deployment. BCI research has robust methodology for evaluating what algorithms compute (classification accuracy, information transfer rate) but almost none for evaluating how fast they compute it on target hardware. This specification addresses that gap.

### 1.1 The Deployment Gap

In current BCI research, deployment-grade software performance engineering on commodity edge devices is underrepresented [4]. Real-time research platforms exist—BCI2000 [5] and OpenViBE [6]—but they typically run on dedicated lab workstations with controlled environments. BCI2000's reference configurations cite "1.4-GHz Athlon" and "2.53-GHz Pentium 4" processors with specialized data acquisition boards [5]; OpenViBE's validation used "Intel Xeon 3.80 GHz" systems in immersive VR rooms [6]. These platforms were not designed for consumer devices subject to DVFS, thermal throttling, OS scheduling noise, and battery constraints [7, 8].

Studies have documented that decoders optimized offline "sometimes fail to achieve optimal performance online" [9], and that "prior work on neural implant algorithms has focused primarily on detection accuracy, with computational performance metrics often unreported" [4]. The BCI field has a disciplinary blind spot: what algorithms compute is well-characterized, but how fast they compute it on deployment hardware is not.

### 1.2 Scale Economics

At research scale (N=10 patients), custom hardware rigs are viable. At industry scale (N=100,000+), economics push toward mass-manufacturable external compute—often commodity-class SoCs—with continuously updatable software. Custom ASICs typically require very large volumes to amortize NRE costs, with industry analyses citing break-even points that can reach into the hundreds of thousands or millions of units depending on process node and design complexity [10]. Off-the-shelf electronics are rewriting the economics of BCI development, with industry estimates suggesting development costs can be reduced by roughly an order of magnitude compared to fully custom approaches [11].

### 1.3 The Thermal Wall

Thermodynamics reinforces this trajectory. Cortical implants face hard thermal limits before risking tissue damage. Bio-heat modeling studies have quantified maximum allowable power dissipation at 5.3–9.3 mW for a 1°C temperature rise in cortical implants [12], with ISO 14708-1 designating a 2°C safety limit for active implantable medical devices [13]. Simple closed-loop applications (e.g., seizure detection) can fit within this envelope. Complex decoding (speech, high-DOF motor control) and general-purpose interfaces cannot.

### 1.4 Compressive Radio Architectures

These thermal constraints make Compressive Radio architectures—where thermal-constrained implants handle acquisition and compression while edge devices handle decoding—thermodynamically necessary as application complexity increases. Demonstrated systems achieve 8× compression ratios on-implant [14], and offloading neural network decoders externally can reduce implant power by 10× [15]. As one study noted: "it took so much power to transmit the data that the devices would generate too much heat to be safe for the patient" [15].

Cloud offload is precluded by closed-loop latency requirements—motor BCIs require real-time feedback that typical cloud round-trip times cannot reliably provide under variable network conditions. Additional barriers include intermittent wireless connectivity in mobile use cases and privacy constraints for neural data classified as protected health information under HIPAA and GDPR. The processing must happen at the edge.

### 1.5 Platform Effects on Edge Devices

When BCI processing moves to commodity edge hardware, practitioners confront platform effects that custom silicon designed away. Mobile inference studies document significant latency variability under CPU resource contention—"a DNN model with better latency performance than another model can become outperformed when resource contention becomes more severe" [7]. Benchmarking methodology must lock CPU frequency to eliminate DVFS-induced measurement variability [9], and account for heterogeneous frequency domains and thermal constraints across big.LITTLE architectures [16].

The Idle Paradox validates this empirically. In CORTEX's cross-load-profile experiments on an Apple M1 platform (n ≈ 1,200 measurements per kernel per load profile, p < 0.001 via Welch's t-test), standard BCI kernels exhibited ~50% latency degradation when benchmarked on idle systems versus medium-load conditions. macOS DVFS policies misinterpreted bursty, low-duty-cycle BCI workloads as idle, downclocking the CPU and incurring wake-up penalties. Prior measurement approaches—batch execution on idle systems—systematically underestimate real-world latency by approximately 2×. Platform state is not noise to be eliminated; it is a first-order experimental variable.

### 1.6 Who Needs This Infrastructure

Three distinct personas require deployment-grade BCI benchmarking, each with different relationships to the problem described above. These are parallel workflows, not a linear pipeline—most algorithms stay in Python, most C implementations never go to custom hardware.

| Persona | Description | CORTEX Enables |
| --- | --- | --- |
| Algorithm Researcher | Implements algorithms in Python/MATLAB for rapid prototyping. Primarily interested in efficacy/accuracy, but needs to validate real-time feasibility before investing in optimized implementations. | Correctness against reference implementations; real-time feasibility assessment |
| Software Engineer | Implements algorithms in C/C++ for execution on edge processors (phones, wearables, embedded Linux). Takes a validated algorithm and produces a production implementation meeting latency constraints on consumer hardware. | Latency distributions (P50/P95/P99), cross-platform comparison, platform effect characterization, bottleneck attribution |
| Hardware Engineer | Implements algorithms in Verilog/SystemVerilog for FPGA/ASIC. Designs custom hardware to meet latency targets unattainable on general-purpose hardware while preserving correctness. | Latency on FPGA vs ARM, implementation comparison, cross-platform validation against same oracle |

**Why Software Engineer First**

CORTEX prioritizes the Software Engineer persona because (1) the deployment gap is documented—decoders optimized offline fail to achieve optimal performance online [9]; (2) scale economics favor commodity hardware where platform effects are unavoidable; (3) thermodynamics requires edge compute via Compressive Radio; and (4) no existing tool serves this persona's latency-on-real-hardware needs. AR and HE personas demonstrate architectural extensibility through shared primitives, not special-purpose workflows.

### 1.7 User Stories

The following user stories capture what each persona requires from CORTEX. Status indicates current implementation state: Exists (fully implemented), Partial (needs enhancement), or Planned (not yet implemented).

**Algorithm Researcher**

| ID | User Story | Required Capabilities | Status |
| --- | --- | --- | --- |
| AR-1 | I need to evaluate my algorithm's accuracy AND know if a C implementation can meet real-time constraints. | Efficacy benchmarking, labeled datasets, latency measurement, oracle validation | Planned |
| AR-2 | I want to contribute my Python algorithm as an oracle so others can implement and benchmark optimized versions. | Oracle contribution workflow, spec generation, validation pipeline | Planned |

Implementation Note: AR efficacy benchmarking is deferred—MOABB [1] serves this need for offline accuracy evaluation. CORTEX complements MOABB by adding latency/correctness validation currently missing from BCI workflows.

**Software Engineer**

| ID | User Story | Required Capabilities | Status |
| --- | --- | --- | --- |
| SE-1 | I have an oracle-validated C kernel. I need to characterize its latency distribution on a target device to determine if it meets a real-time deadline at P99. | Device adapters, latency distribution capture, deadline analysis | Partial |
| SE-2 | I'm choosing between two filter implementations. I need to compare their latency tradeoffs on the target deployment platform. | Comparative benchmarking, diff reports | Partial |
| SE-3 | I'm porting a float32 kernel to fixed16. I need to validate numerical correctness against the float32 oracle before measuring latency. | Multi-dtype oracle validation, degradation metrics | Partial |
| SE-4 | I need to characterize how platform state (idle vs. loaded) affects kernel latency on my target device. | Load profiles, platform effect isolation | Partial |
| SE-5 | My kernel runs slower than expected. I need to determine if it's compute-bound, memory-bound, or platform-effect-bound. | Static analysis, performance counters, platform-state capture, bottleneck attribution | Planned |
| SE-6 | I need to benchmark latency distribution (P50/P95/P99) under sustained load to guarantee consistent real-time performance. | Sustained measurement, warmup protocol, distribution capture | Exists |
| SE-7 | I need to understand why P99 latency is 4× worse than P50 so I can determine if it's algorithmic or platform-caused. | Latency distribution analysis, platform correlation, counter data | Partial |
| SE-8 | I need to measure end-to-end latency of my full pipeline (bandpass → CAR → CSP → classifier) to verify it meets real-time deadlines. | Pipeline composition, stage telemetry | Planned |
| SE-9 | I need to stress test my kernel with 1024 channels to validate it scales for next-generation implants. | Synthetic dataset generation, parameterized data | Exists |
| SE-10 | I need to train my CSP kernel on calibration data, save parameters, then deploy and benchmark the calibrated kernel. | Kernel calibration | Exists |
| SE-11 | I need to analyze benchmark results (latency CDF, deadline miss rate, throughput) and generate reports. | Latency distribution analysis, CDF generation, summary statistics, plot export, HTML reports | Exists |

**Hardware Engineer**

| ID | User Story | Required Capabilities | Status |
| --- | --- | --- | --- |
| HE-1 | I'm comparing HLS vs hand-coded Verilog. I need to benchmark both on real FPGA with the same methodology. | FPGA adapter, kernel interface, comparative analysis | Planned |
| HE-2 | I'm targeting a Zynq SoC. I need to benchmark kernel latency on ARM vs FPGA fabric. | FPGA adapter, heterogeneous device adapters | Planned |

Implementation Note: HE workflows are planned for device adapter expansion. The same primitives (kernels, datasets, oracles) enable cross-platform comparison—only the device adapter changes.

**Coverage Summary**

| Persona | Total | Exists | Partial | Planned | Coverage (Exists + Partial) |
| --- | --- | --- | --- | --- | --- |
| Algorithm Researcher | 2 | 0 | 0 | 2 | 0% |
| Software Engineer | 11 | 4 | 5 | 2 | 82% |
| Hardware Engineer | 2 | 0 | 0 | 2 | 0% |
| Total | 15 | 4 | 5 | 6 | 60% |

These 15 user stories across three personas represent the chaotic surface of BCI deployment needs. The next section distills the methodological principles that unify them.

## 2. Methodological Principles

The 15 user stories in Section 1 span three personas with heterogeneous requirements—accuracy evaluation, latency characterization, platform diagnostics, cross-platform comparison, hardware feasibility. These requirements appear chaotic, but they reduce to five methodological principles. This section defines those principles, shows that every user story maps to at least one, and demonstrates through cross-domain comparison that no existing framework satisfies all five.

### 2.1 Principle Definitions

| # | Principle | Definition | Evaluated By |
| --- | --- | --- | --- |
| P1 | Latency Distribution Capture | The framework reports full latency distributions for each kernel invocation rather than only summary statistics. A user can assess the probability of exceeding a given real-time deadline from the framework's output. | Can a user determine the probability of exceeding a given deadline from the framework's output? |
| P2 | Numerical Correctness as Prerequisite | The framework validates computational outputs against a reference oracle before reporting performance metrics. A benchmark run fails if the kernel produces numerically incorrect results. | Does a benchmark run structurally depend on correctness verification, or is correctness checking optional, separate, or absent? |
| P3 | Single-Variable Isolation | The framework structures experiments so that one parameter varies between runs while all others are held constant. Performance differences between runs are attributable to the varied parameter. | Can a user change one experimental variable and obtain structurally comparable results, with the framework providing structural support for holding other variables constant? |
| P4 | Platform State Observability | The framework records platform-level variables (CPU frequency, governor policy, thermal state, load) alongside performance measurements. A user can correlate latency anomalies with platform state from the framework's own telemetry. | Can a user correlate a latency anomaly with a platform state change (e.g., frequency scaling, thermal throttling) using the framework's own output? |
| P5 | Kernel–Device Latency Analysis | The framework analyzes kernel source and device architecture to produce a predicted latency breakdown by resource category (compute, memory, I/O) prior to execution. | Can a user obtain, before running the benchmark, a predicted breakdown of where kernel execution time will be spent on a given device? |

### 2.2 Why BCI Edge Workloads Require All Five Principles

BCI edge workloads uniquely require all five principles because they combine properties that no single prior domain possesses. They have hard real-time deadlines measured in milliseconds (requiring P1), they perform numerical signal processing where floating-point divergence can silently corrupt classification (requiring P2), they run on heterogeneous edge SoCs where the same algorithm on different cores produces different performance profiles (requiring P3), they execute on passively cooled, battery-constrained devices that actively modulate clock frequency based on thermal state (requiring P4), and their deployment engineers must know whether a kernel is compute-bound, memory-bound, or I/O-bound on the target device to make informed optimization decisions (requiring P5). No prior domain combines sub-millisecond deadline sensitivity with numerical fragility with thermal-driven frequency variation with the need for resource-attributed latency prediction.

Existing frameworks were designed for domains where at least one principle was irrelevant. CPU-saturating compute benchmarks (SPEC, CoreMark) never needed per-invocation distributions because sustained workloads produce stable aggregate throughput. Datacenter latency frameworks (TailBench, DeathStarBench) never needed platform-state observability because servers run with fixed governors and active cooling. ML inference benchmarks (MLPerf) treat correctness as a statistical threshold—a kernel producing wrong outputs for <1% of inputs passes—rather than a structural prerequisite. BCI accuracy benchmarks (MOABB) measure what algorithms compute but not how fast, reflecting a disciplinary blind spot in BCI research. All ten frameworks treat kernels or workloads as opaque executables for timing purposes, providing no pre-execution analysis of how kernel resource requirements interact with device architecture to produce latency.

The Idle Paradox validates this argument empirically. In CORTEX's cross-load-profile experiments on an Apple M1 platform (n ≈ 1,200 measurements per kernel per load profile, p < 0.001 via Welch's t-test), standard BCI kernels exhibited ~50% latency degradation when benchmarked on idle systems versus medium-load conditions. macOS DVFS policies misinterpreted bursty, low-duty-cycle BCI workloads as idle, downclocking the CPU and incurring wake-up penalties. This is a systematic error that frameworks lacking platform-state observability (P4) structurally cannot detect, and that frameworks reporting only summary statistics (lacking P1) would average away.

### 2.3 Principle Traceability

Every user story from Section 1 maps to at least one methodological principle. The table below provides the compact reference; per-principle rationale follows.

| ID | User Story | P1 | P2 | P3 | P4 | P5 |
| --- | --- | --- | --- | --- | --- | --- |
| AR-1 | Evaluate accuracy AND real-time feasibility | ✓ | ✓ | ✓ | | |
| AR-2 | Contribute Python oracle for benchmarking | | ✓ | | | |
| SE-1 | Characterize latency distribution on target device | ✓ | | | | ✓ |
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

**Per-Principle Dependencies**

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

### 2.4 Cross-Domain Comparison

Ten frameworks from five domains evaluated against CORTEX's five methodological principles. Detailed scoring justifications are provided in Appendix A.

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
| CORTEX | BCI/Edge | Yes | Yes | Yes | Partial | Partial |

Frameworks: BCI2000 (Schalk et al., 2004), MOABB (Jayaram & Barachant, 2018), MLPerf Inference (Reddi et al., 2020), TailBench (Kasture & Sanchez, 2016), SPEC CPU 2017, EEMBC CoreMark, Dhrystone (Weicker, 1984), DeathStarBench (Gan et al., 2019), SeBS (Copik et al., 2021), MiBench (Guthaus et al., 2001).

### 2.5 Gap Analysis

**The Methodological Gap**

Across all ten frameworks, the maximum number of principles any single framework satisfies with a "Yes" is two. MLPerf Inference comes closest (Yes on P1 and P3, Partial on P2, No on P4 and P5), but its correctness checking is a statistical threshold (≥99% aggregate accuracy), not per-invocation oracle validation. SPEC CPU 2017 achieves Yes on P2 and P3 but reports no distributional latency data, captures only static platform metadata, and provides no kernel–device latency analysis. No framework exceeds two "Yes" scores.

The specific gap is the simultaneous conjunction of all five principles. Individual principles are well-served in isolation: latency distribution capture is standard in server-oriented frameworks (MLPerf, TailBench, DeathStarBench, SeBS), correctness gating is routine in compute benchmarks (SPEC, CoreMark), and single-variable isolation has strong precedent in standards-body frameworks (MLPerf Closed division, SPEC base rules). But platform-state observability and kernel–device latency analysis are absent across the board—no framework scores "Yes" on P4 or P5. SPEC CPU 2017 earns a lonely "Partial" on P4: its sysinfo tool captures static MHz and power-management settings, and its optional PTDaemon integration records wall-level power and ambient temperature time-series, but neither tool captures the on-die CPU frequency transitions, governor state changes, or junction thermal events that drive the Idle Paradox.

The gap is defined by three intersecting deficits. First, P4 is universally unmet. Second, P5 is universally unmet. Third, no framework combines either P4 or P5 with the other three. A reviewer might ask: why not simply run external monitoring tools (turbostat, perf) alongside an existing framework? The answer is that integrated telemetry enables per-invocation temporal correlation between platform state transitions and individual kernel latencies at microsecond resolution. Post-hoc joining of independently timestamped tool outputs cannot reliably achieve this alignment, particularly when the events of interest—DVFS transitions—occur on the same timescale as the measurements themselves. Similarly, a reviewer might ask: why not profile kernels with external tools like VTune or cachegrind? The answer is that CORTEX's kernel–device analysis is structural—it derives from the plugin ABI's kernel specification and the device adapter's declared characteristics, producing predictions before execution that are then fitted to measured distributions and platform-state telemetry.

**Why the Gaps Exist: Domain-Specific Design Rationales**

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

CORTEX addresses this gap by being the first framework designed to structurally require all five: per-kernel latency distributions, correctness-gated runs, single-variable experiment structure, concurrent platform-state telemetry, and pre-execution kernel–device latency analysis fitted to measured data. Platform-state capture (P4) and kernel–device analysis (P5) are currently partial implementations—thermal telemetry is captured but per-window frequency and governor state are not yet recorded, and roofline-based latency decomposition is planned but not yet built. The architecture supports both; the implementation is in progress.

### 2.6 Principle Applicability Across Device Classes

CORTEX's five principles are universal in intent but vary in manifestation and implementation difficulty across device classes. The table below characterizes how each principle applies to the four device classes CORTEX targets through its device adapter interface.

| Principle | CPU / SoC | MCU (Bare-Metal) | FPGA | ASIC |
| --- | --- | --- | --- | --- |
| P1: Latency Distribution Capture | Essential. DVFS, OS scheduling, and thermal throttling create wide distributions. The Idle Paradox demonstrates ~50% degradation from frequency scaling alone. | Relevant. No OS jitter, but interrupt latency, DMA contention, and peripheral timing create narrower but non-trivial distributions. | Relevant. Execution is cycle-deterministic for pure logic, but DRAM refresh, bus arbitration on SoC FPGAs (Zynq), and thermal management create measurable variation. | Relevant. Memory controller latency varies with bank conflicts and refresh; multi-block SoCs have bus arbitration. Distributions are tightest but non-zero. |
| P2: Correctness Prerequisite | Essential. FP behavior varies across ISAs and compiler optimization levels. Oracle validation catches silent divergence. | Essential. Fixed-point implementations require validation against FP oracles to quantify accuracy loss. | Essential. HLS-generated and hand-coded RTL must be validated against behavioral references. Bit-width truncation and rounding differences are common. | Essential. Post-synthesis netlists must produce correct outputs. Validation against RTL behavioral model is standard; CORTEX extends this to the algorithmic oracle. |
| P3: Single-Variable Isolation | Essential. Many confounding variables (governor, thermal state, co-running processes, compiler flags) require structural isolation. | Relevant. Fewer confounds (no OS, fixed clock), but ISR configuration, DMA, and memory layout still require controlled comparison. | Essential. Synthesis tool version, placement seed, clock constraint, and resource utilization all affect timing. | Essential. PVT and synthesis constraints create a large design space. Single-variable isolation is standard methodology in design-space exploration. |
| P4: Platform State Observability | Essential and hardest. DVFS, thermal throttling, governor policy, and co-tenant load are first-order latency determinants. | Trivially satisfied. Clock is fixed, no OS scheduler, no DVFS. Platform state is static by design—recording confirms the assumption. | Relevant. SoC FPGAs have thermal management and clock scaling. Less dynamic than CPUs but not static. | Relevant. Modern ASICs include DVFS and thermal management. Recording operating point and junction temperature validates timing assumptions. |
| P5: Kernel–Device Analysis | Essential and hardest. Microarchitectural opacity (OoO execution, speculative prefetch) requires reconstruction from static analysis + counters + fitting. | Useful and simpler. In-order cores with predictable timing make static analysis more accurate. Cycle counts often deterministic. | Useful and natively supported. Post-P&R reports provide resource-attributed timing: LUT delay, DSP latency, BRAM access, routing delay. | Most precise. Static timing analysis provides gate-level delay attribution and exact critical-path decomposition by resource type. |

**Key Observation**

The principles are universal but the difficulty gradient inverts across device classes. P4 (platform state observability) is hardest on CPUs where it matters most and trivially satisfied on MCUs where the platform is static. P5 (kernel–device latency analysis) is hardest on CPUs where microarchitectural opacity obscures resource attribution, and natively supported on FPGAs/ASICs where synthesis tools provide the breakdown. This inversion means CORTEX's novel engineering contribution is concentrated where commodity deployment targets require it—on the CPUs and SoCs where BCI processing will actually run at scale.

The comparison table confirms this prediction: no existing framework satisfies all five principles, and the gaps align precisely with the domain-specific design rationales described above. Section 3 presents the system design that embodies these principles.

## 3. CORTEX System Design

Sections 1 and 2 established the BCI deployment problem and the five methodological principles that any benchmarking framework must satisfy. This section presents the system that embodies those principles: its goal, capabilities, architecture, and interface contracts. Every capability traces back to the principles and user stories it enables.

### 3.1 Goal

Equip software engineers deploying BCI kernels with CLI tools and automated reports to quantitatively analyze and understand latency bottlenecks (compute, memory, and I/O) in individual kernels and complete pipelines on edge devices. The reports will provide full latency distributions, latency decomposition, possible platform state impact on the benchmarking, and ensure numerical correctness as a prerequisite.

| Term | Definition |
| --- | --- |
| Researchers | Software engineers deploying BCI kernels (primary focus this semester) |
| Tools | CLI and automated quantitative reports |
| Understand | Quantitative results interpretable by the researcher without a prescriptive workflow |
| Bottlenecks | Latency attributed to compute, memory, and I/O; includes platform state for correlation, flags susceptibility to platform effects, and provides per-kernel breakdowns for pipelines |
| Performance | Numerical correctness (prerequisite) and latency (primary metric) |
| Algorithms / Pipelines | Kernel as the fundamental unit; composable into sequential or parallel chains |
| Specific Devices | Edge compute devices where BCI kernels are practically deployed (laptop, mobile, embedded) |
| Latency | Full distribution (P50/P95/P99); crucial for real-time systems where failure occurs at the tail, not the mean |

### 3.2 Design Philosophy

CORTEX's architecture follows Butler Lampson's STEADY principles for system design, adapted to the specific constraints of BCI benchmarking infrastructure.

| Principle | CORTEX Implementation | Rationale |
| --- | --- | --- |
| Simplicity | Minimal 3-function C ABI | init, process, cleanup with no external runtime requirements. Any C compiler on any platform can build a kernel. |
| Timeliness | Working infrastructure first | Measurement capability delivered before analysis, analysis before diagnostics. Each layer usable independently. |
| Efficiency | Zero-allocation hot path | process() is hermetic: no malloc, no syscalls, no I/O. Measurement overhead characterized at 1µs. |
| Adaptability | Primitive-based architecture | Kernels, configs, datasets, and device adapters are independently versioned, single-responsibility components. |
| Dependability | Oracle validation as gate | SciPy-based correctness verification structurally precedes performance measurement. Incorrect kernels cannot produce benchmark results. |
| Yieldingness | Intuitive CLI surface | cortex pipeline, cortex run, cortex analyze—complete workflow in three commands. |

### 3.3 Architecture

#### 3.3.1 Primitives Model

CORTEX is built on a primitives-based architecture inspired by Amazon's service-oriented design philosophy: small, independently deployable components with well-defined interfaces that compose into larger workflows. Three primitive types form the foundation:

Kernel Primitives are self-contained directories containing a C implementation of the plugin ABI, a Python oracle for validation, a spec.yaml with metadata, a README, and a Makefile. They are versioned immutably at primitives/kernels/v{version}/{name}@{dtype}/. Each kernel is a single-responsibility signal-processing operation (e.g., bandpass filter, CAR, Goertzel, Welch PSD).

Run-Config Primitives are YAML files specifying dataset path and format, real-time deadlines, load profiles (idle/medium/heavy), CPU governor settings, sample rate, and window parameters. They live in primitives/configs/ (not yet versioned like kernels). A run-config captures every parameter needed to reproduce an experiment except the kernel and device.

Device Adapters abstract the target hardware behind a uniform interface contract: accept a kernel, invoke process(), and return timing telemetry. Implementations include native (local execution), remote (SSH/UART/TCP to embedded devices), and simulator (cycle-accurate models calibrated against real hardware). Each adapter declares its timing resolution, controllable parameters, communication latency, and whether it operates in real-time or simulated-time mode.

**Key Insight**

kernel + run-config + device-adapter = one reproducible experiment. Changing any single primitive while holding the others constant directly enables P3 (single-variable isolation). This composability is what makes CORTEX a framework rather than a collection of scripts.

#### 3.3.2 Execution Engine

The execution engine orchestrates benchmarking through four components arranged in a pipeline. The Harness is the top-level orchestrator: it loads the kernel plugin via dlopen, parses the YAML run-config, configures the execution environment, supervises the benchmark run, and collects telemetry. The Replayer streams EEG data at the configured sample rate, managing synthetic load profiles and enforcing timing cadence—windows arrive at constant rate regardless of kernel execution time, inherently avoiding coordinated omission artifacts. The Scheduler manages windowing (window size W, hop size H), deadline tracking, and CPU affinity. The Kernel Plugin executes process() on each window and returns results for oracle comparison.

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
• stream @ Fs     • windows: W, H
• manage load     • deadlines
• timing cadence  • CPU affinity
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

Every kernel implements three required C functions and one optional function, loaded dynamically via dlopen. This minimal surface is the foundation of cross-platform portability—any system with a C compiler and dynamic linker can host CORTEX kernels.

| Function | Contract | Signature Notes |
| --- | --- | --- |
| cortex_init() | Allocate state, precompute constants, load calibration parameters. May allocate memory, perform file I/O, and execute arbitrary setup. Called once per benchmark run. | Returns opaque state pointer. Errors reported via return code. |
| cortex_process() | Process one window of EEG data. Hermetic: zero allocations, zero syscalls, zero I/O. This is the measured function—any violation of hermeticity invalidates timing results. | Accepts state pointer + input buffer + output buffer. Returns status code. |
| cortex_teardown() | Free allocated state, release resources. Called once after all windows are processed. | Accepts state pointer. No return value requirements. |
| cortex_calibrate() (optional) | Train kernel on calibration data and serialize learned parameters to a binary state file. Called offline before benchmarking; the resulting state is loaded by cortex_init() at benchmark time. | Accepts training data + output path. Returns status code. Not all kernels require calibration. |

The two-phase measurement pattern (FFTW-style init/execute separation) ensures that one-time setup costs—allocation, plan creation, calibration loading—are excluded from per-invocation timing. In production, init() is amortized over millions of windows; process() latency is what determines real-time safety. The optional calibrate() function enables trainable kernels (ICA, CSP) to serialize learned parameters offline, which init() loads at benchmark time.

#### 3.4.2 Device Adapter Contract

Device adapters abstract heterogeneous hardware behind a uniform frame-based protocol. Communication between the harness (host) and the adapter (device) follows a session lifecycle with five frame types:

| Frame Type | Contract |
| --- | --- |
| HELLO | Capability exchange. The adapter declares its timing resolution, controllable parameters, supported dtypes, and real-time vs. simulated-time mode. The harness confirms protocol version compatibility. |
| CONFIG | Kernel selection and initialization. The harness specifies which kernel to load, provides calibration state (if any), and declares input/output dimensions. The adapter loads the kernel via dlopen (native) or receives a pre-built binary (remote). |
| ACK | Handshake confirmation. The adapter confirms successful kernel loading and reports output buffer dimensions. Benchmark measurement begins after ACK. |
| WINDOW_CHUNK | Data transfer. The harness sends one window of EEG data (W × C samples). Large windows are chunked at 8KB boundaries with CRC32 integrity checks per chunk. |
| RESULT | Timing telemetry. The adapter returns the kernel's output buffer plus per-window timing metadata (start_ns, end_ns) and available platform state (thermal zone temperature). The harness records these in the telemetry log. |

Current adapter implementations include Native (local dlopen, 1µs overhead), TCP (BSD sockets + TCP_NODELAY, ~180µs localhost / ~1.2ms LAN), and Serial (termios 8N1, ~12ms at 115200 baud). The SSH deployer orchestrates remote setup: passwordless SSH verification, rsync with BCI-aware excludes, remote build, optional on-device oracle validation, and adapter daemon launch.

#### 3.4.3 Transport Protocol

Remote device adapters communicate via a custom binary protocol designed for embedded constraints. The protocol uses a 16-byte header (magic "CRTX", version, type, length, CRC32) with three-phase handshake: HELLO (capability exchange) → CONFIG (kernel selection, calibration state) → ACK (output dimensions). Large windows are chunked at 8KB boundaries. The implementation is ~1,500 lines of C (protocol + CRC + error handling + chunking) with zero external dependencies, embeddable on bare-metal STM32 targets. URI-driven transport selection (local://, tcp://, serial://) enables the same protocol code across all transports.

#### 3.4.4 Oracle Interface

Each kernel's oracle.py implements a Python reference producing the same output as the C kernel for identical input. The validation pipeline loads real EEG data, runs both the C kernel and the Python oracle on identical windows, and compares outputs with configurable tolerance (default: rtol=1e-5, atol=1e-6; relaxed for frequency-domain kernels like Welch PSD). Validation supports ––calibration-state for trainable kernels (ICA, CSP) and runs structurally before any benchmark—correctness precedes performance (P2).

### 3.5 Capabilities

The table below enumerates CORTEX's 33 capabilities across five categories: Infrastructure, Measurement, Analysis, Validation, and Future/Advanced. Each capability traces to the user stories and principles it enables. The Rationale column is a one-sentence summary; full justifications with related work citations are provided in Appendix B.

Status legend: Yes = Implemented, Partial = Needs Enhancement, No = Not Yet Implemented.

**Infrastructure**

| Capability | Enables | Status | Rationale (see Appendix B for detail) | Strategy |
| --- | --- | --- | --- | --- |
| Oracle validation | P2; SE-1,2,3, AR-1, HE-1,2 | Yes | Validates C kernel output against Python/SciPy reference (rtol=1e-5, atol=1e-6) before any benchmark run. | Implemented |
| Coordinated omission resistance | P1; SE-1,6,7 | Partial | Constant-rate window replay prevents measurement backoff during stalls; HdrHistogram correction algorithm not yet integrated. | Adapt |
| Component separation | P3; SE-1, HE-1 | Yes | Independent primitives (kernels, configs, datasets) in versioned directories; parameters via YAML without recompilation. | Implemented |
| SSH deployment | SE-1 | Yes | Automated rsync + remote build + adapter daemon launch over passwordless SSH for embedded targets. | Implemented |
| Transports (TCP, Serial, Local) | SE-1 | Yes | Unified cortex_transport_t interface with URI-driven selection; same protocol across local, TCP, and serial transports. | Implemented |
| Protocol | SE-1 | Yes | Custom binary protocol (~1,500 LOC, zero deps) with CRC32 framing, 3-phase handshake, and 8KB chunking for bare-metal targets. | Implemented |
| Device adapters | P3,P4; SE-1, HE-1,2 | Partial | Native adapter complete; embedded (SSH/UART) and FPGA adapters planned for cross-platform validation. | Adapt/Reuse |
| Kernel calibration | P2; SE-10 | Yes | Standardized cross-language calibration: Python trains via cortex_calibrate() → binary state → C deploys via cortex_init(). | Implemented |
| Synthetic datasets | P3; SE-9 | Yes | Generates 256–2048+ channel synthetic EEG (pink noise, sine waves) with memory-safe chunked generation (<200MB peak RAM). | Implemented |

**Measurement**

| Capability | Enables | Status | Rationale (see Appendix B for detail) | Strategy |
| --- | --- | --- | --- | --- |
| Sustained measurement | P1; SE-6 | Yes | Default 120s × 5 repeats = 600s total (~1,100 windows at 2/sec after warmup) for reliable percentile estimation. | Implemented |
| Warmup protocol | P1; SE-6 | Yes | Discards first N warmup windows (default 10s) to filter cold-start transients (cache, DVFS, thermal ramp). | Implemented |
| Load profiles | P3,P4; SE-4 | Yes | Three-tier declarative profiles (idle/medium/heavy) spawn stress-ng; medium load prevents DVFS downscaling on locked-down platforms. | Implemented |
| Two-phase measurement | P1; SE-6 | Yes | ABI enforces init/process/teardown separation; allocations in process() are contract violations, not just discouraged. | Implemented |
| Platform-state capture | P4; SE-5,7 | Partial | Thermal capture via sysfs implemented; CPU frequency, governor state, and compiler flags still needed. | Adapt |
| Statistical confidence | P1; SE-6,7 | Partial | 1,200 windows per run with full distribution stats; missing explicit CI reporting (mean ± CI at 95%). | Adapt |
| Multi-dtype kernels | P2; SE-3 | Partial | ABI defines FLOAT32, Q15, Q7 as first-class types; all kernels implemented as f32; fixed-point implementations planned. | Adapt |
| Performance counters | P4,P5; SE-5,7 | No | PMU event capture (cache misses, IPC, branch mispredictions) needed for root-cause bottleneck attribution. | Adapt |

**Analysis**

| Capability | Enables | Status | Rationale (see Appendix B for detail) | Strategy |
| --- | --- | --- | --- | --- |
| Latency distribution | P1; SE-1,6,7,11 | Yes | Per-window latency with full distribution stats (median, P95, P99, std) and CDF plots for visual analysis. | Implemented |
| Deadline analysis | P1; SE-1 | Partial | Per-window deadline tracking and miss rate computation; missing formal CLI and root-cause correlation. | Adapt |
| Analysis/reporting | P1; SE-11 | Yes | cortex analyze generates latency/CDF/throughput plots (PNG/PDF/SVG), SUMMARY.md, and full statistics with execution environment. | Implemented |
| Comparative analysis | P3; SE-2, HE-1 | Partial | Visual comparison via CDF overlay and bar charts; missing cortex compare CLI, Welch's t-test, and Cohen's d. | Adapt |
| Latency decomposition | P5; SE-5,7 | No | Roofline-based static analysis + device specs to decompose latency into compute/memory/platform time categories. | Innovate |
| Diagnostic framework | P4,P5; SE-5,7 | No | Predicted vs. actual latency comparison to reveal hidden overhead (scheduler preemption, cache misses, thermal throttle). | Innovate |
| Mandatory reporting | P3,P4; SE-7, HE-1 | No | Capture compiler version/flags, CPU governor, and frequency in telemetry records for reproducible cross-platform comparison. | Adapt |

**Validation**

| Capability | Enables | Status | Rationale (see Appendix B for detail) | Strategy |
| --- | --- | --- | --- | --- |
| Oracle contribution workflow | P2; AR-2 | Partial | Comprehensive written guide exists; missing scaffolding CLI (cortex new-kernel) and pre-submission validation (cortex check-kernel). | Adapt |
| SNR-based validation | P2; SE-3, HE-2 | No | Supplement rtol/atol with signal-to-noise ratio thresholds (60dB float32, 40dB Q15) for frequency-domain kernels. | Innovate |
| Scaled tolerance validation | P2; SE-3, HE-2 | No | Scale tolerance with operation count (rtol = base_rtol × √n) to avoid spurious failures on complex kernels. | Innovate |

**Future / Advanced**

| Capability | Enables | Status | Rationale (see Appendix B for detail) | Strategy |
| --- | --- | --- | --- | --- |
| Pipeline composition | P1,P3; SE-8 | No | cortex pipeline runs all kernels sequentially on the same dataset (exists). Chained pipeline execution—where kernel A's output feeds kernel B's input with per-stage telemetry—is not yet implemented. | Innovate |
| Scenario-based testing | P1; SE-1,6 | Partial | Sequential single-stream implemented; streaming scenario with queueing model and deadline-aware scheduling planned. | Adapt |
| Power/energy measurement | P4; HE-1,2 | No | Optional power telemetry via PTDaemon/RAPL/USB meters for energy-per-window efficiency analysis. | Adapt |
| Hardware feasibility | P5; HE-1,2 | No | Foresee integration points to translate validated kernels into FPGA/ASIC feasibility estimates. | Integration |
| Labeled dataset primitives | AR-1 | No | Deferred to MOABB integration; MOABB provides 67+ datasets and standardized evaluation protocols. | Defer |
| Efficacy benchmarking | AR-1 | No | Deferred to MOABB for accuracy; CORTEX focuses on latency. Future integration enables accuracy + latency co-evaluation. | Defer |

| | Yes (Implemented) | Partial | No (Planned) | Total |
| --- | --- | --- | --- | --- |
| | 14 | 10 | 9 | 33 |

## 4. Evaluation & Roadmap

### 4.1 Priority Tiers

Capabilities are organized into priority tiers reflecting implementation urgency and research value. Complexity: Low = days, Medium = weeks, High = multi-week.

| Tier | Capability | Complexity | Strategy | Key Prior Art |
| --- | --- | --- | --- | --- |
| Tier 1 | Pipeline composition | High | Innovate | Darkroom streaming, ILP buffer scheduling |
| Tier 1 | Device adapters | High | Adapt | |
| Tier 1 | Latency decomposition | High | Innovate | Roofline, nn-Meter |
| Tier 2 | Deadline analysis CLI | Low | Adapt | LTTng, Cyclictest, WCET |
| Tier 2 | Comparative analysis CLI | Low | Adapt | MLPerf stats, Welch t-test, Cohen's d |
| Tier 2 | Platform-state (full) | Medium | Reuse | perf/ftrace, sysfs, eBPF |
| Tier 2 | Multi-dtype (Q15) | Medium | Adapt | CMSIS-DSP Q15 |
| Tier 2 | Mandatory reporting | Low | Adapt | EEMBC CoreMark, MLPerf |
| Tier 2 | Statistical confidence (CI) | Low | Adapt | MLPerf, Kalibera & Jones |
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
| --- | --- | --- |
| Implemented | 14 | Oracle validation, component separation, SSH deployment, transports, protocol, native adapter, kernel calibration, synthetic datasets, sustained measurement, warmup, load profiles, two-phase measurement, latency distribution, analysis/reporting |
| Reuse | 3 | stress-ng (load profiles), perf/ftrace (platform-state), OpenSSH+rsync (deployment) |
| Adapt | 11 | Platform-state, statistical confidence, multi-dtype, deadline analysis, comparative analysis, mandatory reporting, oracle workflow, scenario-based, power measurement, diagnostic framework, performance counters |
| Innovate | 4 | Pipeline composition, latency decomposition, SNR validation, scaled tolerance |
| Defer | 3 | Labeled datasets (MOABB), efficacy benchmarking (MOABB), hardware feasibility (Foresee) |

### 4.3 Key Research Insights

What CORTEX does that no prior work does:

1. **Oracle-first validation before performance measurement.** Unlike SPEC, MLPerf, and EEMBC, which either gate on aggregate quality or separate correctness from timing, CORTEX structurally requires per-invocation correctness verification as a prerequisite to benchmark execution.

2. **Platform state as experimental variable, not noise to eliminate.** The Idle Paradox demonstrates that platform state is a first-order determinant of BCI kernel latency. CORTEX records and correlates platform state with per-window timing, enabling causal attribution of latency anomalies.

3. **Window-based latency distributions at streaming cadence.** CORTEX measures per-window latency at 160 Hz streaming cadence with full distributional reporting (P50/P95/P99), capturing the tail behavior that determines real-time safety.

4. **Sub-100µs kernel measurement where DVFS transitions dominate.** BCI kernels execute in 20–100µs, a timescale where DVFS transitions are the primary source of latency variation—a regime no existing framework was designed to characterize.

5. **BCI-specific correctness + latency co-evaluation.** MOABB provides accuracy-only evaluation; fio and TailBench provide latency-only measurement. CORTEX is the first framework to combine numerically validated correctness with distributional latency analysis for BCI workloads.

## References

[1] V. Jayaram and A. Barachant, "MOABB: Trustworthy Algorithm Benchmarking for BCIs," J. Neural Eng., vol. 15, no. 6, p. 066011, 2018. doi:10.1088/1741-2552/aadea0

[2] J. Dean and L. A. Barroso, "The Tail at Scale," Commun. ACM, vol. 56, no. 2, pp. 74–80, 2013. doi:10.1145/2408776.2408794

[3] V. J. Reddi et al., "MLPerf Inference Benchmark," in Proc. ISCA, 2020. doi:10.1109/ISCA45697.2020.00045

[4] X. Liu and A. G. Richardson, "Edge Deep Learning for Neural Implants: A Case Study of Seizure Detection and Prediction," J. Neural Eng., vol. 18, p. 046034, 2021. doi:10.1088/1741-2552/abf473

[5] G. Schalk, D. J. McFarland, T. Hinterberger, N. Birbaumer, and J. R. Wolpaw, "BCI2000: A General-Purpose Brain-Computer Interface (BCI) System," IEEE Trans. Biomed. Eng., vol. 51, no. 6, pp. 1034–1043, 2004. doi:10.1109/TBME.2004.827072

[6] Y. Renard et al., "OpenViBE: An Open-Source Software Platform to Design, Test, and Use Brain–Computer Interfaces in Real and Virtual Environments," Presence, vol. 19, no. 1, pp. 35–53, 2010. doi:10.1162/pres.19.1.35

[7] L. Yang and M. Gruteser, "A Note on Latency Variability of Deep Neural Networks for Mobile Inference," arXiv:2003.00138, 2020.

[8] L. L. Zhang et al., "nn-Meter: Towards Accurate Latency Prediction of Deep-Learning Model Inference on Diverse Edge Devices," in Proc. MobiSys, 2021. doi:10.1145/3458864.3467882

[9] F. R. Willett et al., "Principled BCI Decoder Design and Parameter Selection Using a Feedback Control Model," Sci. Rep., vol. 9, p. 8881, 2019. doi:10.1038/s41598-019-44166-7

[10] I. Lankshear, "The Economics of ASICs: At What Point Does a Custom SoC Become Viable?," Electronic Design, EnSilica white paper, Jul. 2019.

[11] TTP Neurotechnology Team, "What Does It Cost to Build a Brain-Computer Interface (BCI) Today?," TTP Insights, Oct. 2025.

[12] K. M. Silay, C. Dehollain, and M. Declercq, "Numerical Analysis of Temperature Elevation in the Head Due to Power Dissipation in a Cortical Implant," in Proc. 30th IEEE EMBS, pp. 951–956, 2008. doi:10.1109/IEMBS.2008.4649312

[13] A. J. Whalen and S. I. Fried, "Thermal Safety Considerations for Implantable Micro-Coil Design," J. Neural Eng., vol. 20, no. 4, 2023. doi:10.1088/1741-2552/ace79a

[14] X. Liu et al., "A Fully Integrated Wireless Compressed Sensing Neural Signal Acquisition System for Chronic Recording and Brain Machine Interface," IEEE Trans. Biomed. Circuits Syst., vol. 10, no. 4, pp. 874–883, 2016. doi:10.1109/TBCAS.2016.2574362

[15] N. Even-Chen et al., "Power-Saving Design Opportunities for Wireless Intracortical Brain-Computer Interfaces," Nat. Biomed. Eng., vol. 4, pp. 984–996, 2020. doi:10.1038/s41551-020-0595-9

[16] V. J. Reddi et al., "MLPerf Mobile Inference Benchmark," Proc. Mach. Learn. Syst., vol. 4, pp. 352–369, 2022.

[17] J. Li, N. K. Sharma, D. R. K. Ports, and S. D. Gribble, "Tales of the Tail: Hardware, OS, and Application-level Sources of Tail Latency," in Proc. SoCC, 2014. doi:10.1145/2670979.2670988

[18] G. Tene, "How NOT to Measure Latency," Strange Loop Conference, 2015.

[19] T. Kalibera and R. Jones, "Rigorous Benchmarking in Reasonable Time," in Proc. ISMM, 2013. doi:10.1145/2464157.2464160

[20] A. Delorme et al., "EEGLAB, SIFT, NFT, BCILAB, and ERICA: New Tools for Advanced EEG Processing," Comput. Intell. Neurosci., 2011. doi:10.1155/2011/130714

[21] SPEC, "SPEC CPU 2017 Benchmark Suite," Standard Performance Evaluation Corporation. https://www.spec.org/cpu2017/

[22] SPEC, "SPECpower_ssj2008 Benchmark," Standard Performance Evaluation Corporation. https://www.spec.org/power_ssj2008/

[23] EEMBC, "CoreMark Benchmark," Embedded Microprocessor Benchmark Consortium. https://www.eembc.org/coremark/

[24] EEMBC, "AudioMark Benchmark," Embedded Microprocessor Benchmark Consortium. https://www.eembc.org/audiomark/

[25] M. Frigo and S. G. Johnson, "The Design and Implementation of FFTW3," Proc. IEEE, vol. 93, no. 2, pp. 216–231, 2005. doi:10.1109/JPROC.2004.840301

[26] ARM Ltd., "CMSIS-DSP Software Library," https://arm-software.github.io/CMSIS-DSP/

[27] J. Ragan-Kelley et al., "Halide: A Language and Compiler for Optimizing Parallelism, Locality, and Recomputation," in Proc. PLDI, 2013. doi:10.1145/2491956.2462176

[28] J. Hegarty et al., "Darkroom: Compiling High-Level Image Processing Code into Hardware Pipelines," in Proc. SIGGRAPH, 2014. doi:10.1145/2601097.2601174

[29] T. Chen et al., "TVM: An Automated End-to-End Optimizing Compiler for Deep Learning," in Proc. OSDI, 2018.

[30] S. Williams et al., "Roofline: An Insightful Visual Performance Model for Multicore Architectures," Commun. ACM, vol. 52, no. 4, pp. 65–76, 2009. doi:10.1145/1498765.1498785

[31] N. J. Higham, Accuracy and Stability of Numerical Algorithms, 2nd ed. SIAM, 2002.

[32] E. Anderson et al., LAPACK Users' Guide, 3rd ed. SIAM, 1999.

[33] A. L. Goldberger et al., "PhysioBank, PhysioToolkit, and PhysioNet: Components of a New Research Resource," Circulation, vol. 101, no. 23, pp. e215–e220, 2000. doi:10.1161/01.CIR.101.23.e215

[34] F. Krausz et al., "Towards Zero Training for Brain-Computer Interfacing," PLoS ONE, vol. 3, no. 8, e2967, 2008. doi:10.1371/journal.pone.0002967

[35] G. Tene, "wrk2: A Constant Throughput, Correct Latency Recording Variant of wrk," https://github.com/giltene/wrk2

[36] G. Tene, "HdrHistogram: A High Dynamic Range Histogram," https://github.com/HdrHistogram/HdrHistogram

[37] J. Axboe, "fio: Flexible I/O Tester," https://github.com/axboe/fio

[38] V. M. Weaver et al., "Linux perf_event Features and Overhead," in Proc. FastPath Workshop, 2013.

[39] LTTng Project, "Linux Trace Toolkit: next generation," https://lttng.org/

[40] T. Gleixner, "Cyclictest: RT Testing Tool," https://wiki.linuxfoundation.org/realtime/

[41] J. V. King, "stress-ng: A Tool to Load and Stress a Computer System," https://github.com/ColinIanKing/stress-ng

[42] dSPACE GmbH, "Hardware-in-the-Loop Simulation," https://www.dspace.com/en/pub/home/products/hw/hil_simulation.cfm

[43] C. Banbury et al., "MLPerf Tiny Benchmark," in Proc. NeurIPS Datasets and Benchmarks, 2021.

[44] S. Yadav et al., "Foresee: A Modular and Open Framework to Explore Processing on Brain-Computer Interfaces," in Proc. IEEE EMBC, 2025.

[45] H. Kasture and D. Sanchez, "TailBench: A Benchmark Suite and Evaluation Methodology for Latency-Critical Applications," in Proc. IISWC, 2016.

[46] Y. Gan et al., "An Open-Source Benchmark Suite for Microservices and Their Hardware-Software Implications for Cloud and Edge Systems," in Proc. ASPLOS, 2019. doi:10.1145/3297858.3304013

[47] M. Copik et al., "SeBS: A Serverless Benchmark Suite for Function-as-a-Service Computing," in Proc. Middleware, 2021. doi:10.1145/3464298.3476133

[48] M. R. Guthaus et al., "MiBench: A Free, Commercially Representative Embedded Benchmark Suite," in Proc. WWC, 2001. doi:10.1109/WWC.2001.990739

[49] B. W. Lampson, "Hints for Computer System Design," ACM SIGOPS Oper. Syst. Rev., vol. 17, no. 5, pp. 33–48, 1983. doi:10.1145/773379.806614

## Appendix A: Detailed Scoring Justifications

Each cell in the cross-domain comparison table (§2.4) is justified below with evidence from the framework's paper, documentation, or run rules.

### P1: Latency Distribution Capture

| Framework | Score | Justification |
| --- | --- | --- |
| BCI2000 | Partial | BCI2000Certification records per-block timestamps and visualizes latency distributions, but these capture system-level roundtrip timing (ADC→processing→stimulus), not per-kernel invocation latencies. |
| MOABB | No | Reports only a single aggregate time field (training duration) per evaluation fold; no per-invocation latency data exists. Operates entirely offline on pre-recorded datasets. |
| MLPerf Inference | Yes | Server scenario records per-query latency; LoadGen reports P50–P99.9 percentiles. Raw per-query timing logs enable full distribution reconstruction and deadline-exceedance assessment. |
| TailBench | Yes | Records ⟨service_time, e2e_time⟩ tuples for every request in lats.bin, parsed via parselats.py to produce full CDFs. Explicitly designed for tail-latency characterization. |
| SPEC CPU 2017 | No | Reports median of three runs (elapsed seconds) per benchmark and computes geometric-mean ratios. Batch-compute workloads have no per-invocation latency concept. |
| CoreMark | No | Produces a single aggregate Iterations/Sec score from total time divided by total iterations. No per-iteration timing, histogram, or percentile output. |
| Dhrystone | No | Reports a single Dhrystones/Second figure from Begin_Time and End_Time around the entire loop. No per-iteration or distributional measurement. |
| DeathStarBench | Yes | Uses wrk2 with HdrHistogram and coordinated-omission correction for full percentile spectra (P50–P99.999), plus Jaeger distributed tracing at RPC granularity. |
| SeBS | Yes | Measures latency at three levels (benchmark, provider, client) across 200+ invocations with 95th/99th percentile confidence intervals. Separately captures cold-start vs. warm distributions. |
| MiBench | No | A workload characterization suite originally analyzed via SimpleScalar simulation. Contains no timing harness, no per-invocation measurement, and no latency reporting. |

### P2: Numerical Correctness as Prerequisite

| Framework | Score | Justification |
| --- | --- | --- |
| BCI2000 | No | Certification validates timing thresholds (e.g., audio latency < 65 ms) as pass/fail, but never checks whether signal-processing kernels produce numerically correct outputs. |
| MOABB | No | Computes classification scores (ROC-AUC, accuracy) as output metrics but does not validate intermediate computational correctness against a reference oracle. |
| MLPerf Inference | Partial | Closed-division submissions must achieve ≥99% of reference FP16 accuracy, gating performance on aggregate quality. However, this is a statistical threshold—a kernel producing incorrect outputs for <1% of inputs passes. Per-invocation numerical correctness is not validated. |
| TailBench | No | Purely a timing framework—records service time and e2e latency per request but performs no output validation. Correctness of underlying applications is assumed. |
| SPEC CPU 2017 | Yes | Output validation is structurally mandatory per Run Rule 1.2.1: SPEC tools validate outputs against expected results; validation failure marks the run INVALID and unpublishable. |
| CoreMark | Yes | CRC-16 self-verification computes checksums on every algorithm's output (list, matrix, state machine). Score printed only on successful validation. |
| Dhrystone | No | Prints computed values alongside "should be:" comments for manual visual inspection only. No programmatic pass/fail; reports score regardless of correctness. |
| DeathStarBench | No | No output correctness verification. Measures latency/throughput of microservice requests but does not validate HTTP response content. |
| SeBS | No | Employs "self-validation" that retries failed invocations and filters them from the dataset rather than failing the benchmark run. A system that fails 20% of invocations reports the same statistics as one that fails none. |
| MiBench | No | Programs produce functional output but the original suite includes no validation framework. Correctness scripts added later by cBench (Fursin, ~2008), not part of original design. |

### P3: Single-Variable Isolation

| Framework | Score | Justification |
| --- | --- | --- |
| BCI2000 | Partial | Certification sweeps system parameters (sampling rate, channels, block size) across ~100 configurations, but these are hardware/system variables, not algorithm-benchmarking variables. |
| MOABB | No | Excellent structural isolation for accuracy comparisons (fixed dataset/paradigm, vary pipeline only), but zero structural support for isolating variables affecting computational latency. |
| MLPerf Inference | Yes | Closed-division rules constrain model, dataset, and preprocessing to reference implementation, isolating only the HW/SW stack. LoadGen ensures identical traffic generation across submissions. |
| TailBench | Partial | Provides standardized load generation (Poisson arrivals, configurable QPS) and three deployment modes, but no formal run-rule divisions enforce which parameters must be held constant. |
| SPEC CPU 2017 | Yes | Base rules (2.3.5) require identical compiler flags across all benchmarks by language, forbid FDO, and mandate same thread count. Base-vs-peak structurally isolates compiler optimization. |
| CoreMark | Partial | Reporting rules require documenting compiler version/flags; run rules prohibit source modification (MD5 check). But no experiment harness or A/B comparison infrastructure exists. |
| Dhrystone | No | Specifies unenforced ground rules that Weicker documented as insufficient. Results circulate as bare DMIPS numbers without compiler or platform context. |
| DeathStarBench | Partial | The paper demonstrates careful single-variable methodology (varying CPU frequency, cluster size), but the framework provides only workloads and a load generator—experiment design is the user's responsibility. |
| SeBS | Partial | Structures experiments to systematically vary memory allocation (128–3008 MB) while fixing workloads, and considers time-of-day as a confound, but does not enforce single-variable designs. |
| MiBench | No | Provides domain-categorized workloads with small/large inputs but includes no experiment harness, reporting rules, or standardized result format. A source-code collection, not a framework. |

### P4: Platform State Observability

| Framework | Score | Justification |
| --- | --- | --- |
| BCI2000 | No | Documents static hardware configuration (CPU model, clock speed) for certification but records no dynamic platform telemetry (frequency scaling, thermal throttling, load) alongside timing. |
| MOABB | No | Results contain only dataset/subject/session/score/pipeline metadata. No platform-level variables; the additional_columns extension exists but no built-in platform telemetry is provided. |
| MLPerf Inference | No | System description JSON captures static configuration. Optional "Power" submission mode integrates SPEC PTDaemon for wall-level AC power and ambient temperature, but does not record CPU frequency, governor state, or on-die thermal data. |
| TailBench | No | Output contains only per-request ⟨service_time, e2e_time⟩ tuples. README recommends disabling C-states but these are configuration guidelines, not recorded measurements. |
| SPEC CPU 2017 | Partial | Requires disclosure of nominal/max MHz and power-management enabled/disabled; sysinfo captures OS/hardware details as static snapshots. Optional PTDaemon records wall-level AC power and ambient temperature, but not on-die CPU frequency, governor transitions, or junction thermal state. |
| CoreMark | No | Logs only buffer size, total ticks, iterations/sec, and compiler info. CoreMark/MHz requires the user to externally determine clock frequency—the benchmark itself does not measure it. |
| Dhrystone | No | A manual submission form asks for CPU model, clock, and OS, but these are user-reported text fields external to the benchmark. No runtime measurement of any platform variable. |
| DeathStarBench | No | The paper's authors use external tools (vTune, RAPL, perf) for platform analysis, but the framework's own tracing records only per-service latency—no platform-state correlation. |
| SeBS | No | Commercial FaaS platforms are black boxes where CPU frequency, thermal state, and co-location are unobservable. Local mode supports PAPI counters, but cloud (primary use case) provides zero visibility. |
| MiBench | No | Originally analyzed via SimpleScalar simulation. When run on real hardware, no instrumentation records CPU frequency, thermal state, or system load. |

### P5: Kernel–Device Latency Analysis

| Framework | Score | Justification |
| --- | --- | --- |
| BCI2000 | No | Signal-processing filters are compiled into monolithic executables. No structural access to kernel resource profiles or device architecture characteristics for pre-execution latency prediction. |
| MOABB | No | Pipelines are scikit-learn estimators evaluated for accuracy only. No analysis of computational resource requirements or device-specific execution characteristics. |
| MLPerf Inference | No | Model operation graphs are available, but the framework performs no analysis mapping operations to device resource utilization. No predicted latency breakdown by resource category. |
| TailBench | No | Applications are pre-compiled server binaries (Xapian, MySQL, etc.) treated as opaque workloads. No kernel-level resource analysis or device-specific latency prediction. |
| SPEC CPU 2017 | No | Benchmark sources are available but the framework provides no analysis tooling. Workloads are opaque executables for timing purposes; no resource-category latency breakdown. |
| CoreMark | No | Algorithms (list sort, matrix multiply, state machine) are specified but no tooling maps their instruction mix or memory access patterns to device-specific latency predictions. |
| Dhrystone | No | A synthetic loop with no analysis of resource utilization. The benchmark's entire purpose is a single throughput number, not resource-attributed latency. |
| DeathStarBench | No | Microservices are containerized applications. The framework provides distributed tracing of request flow but no per-service compute/memory/IO latency decomposition. |
| SeBS | No | Functions are packaged for cloud deployment. No analysis of function resource requirements against provider hardware; latency is measured end-to-end without resource attribution. |
| MiBench | No | Originally characterized via SimpleScalar cycle-accurate simulation, which does provide resource breakdown—but this is external tooling, not part of the benchmark suite itself. |

## Appendix B: Full Capability Rationale

This appendix provides the full rationale and related work citations for each capability in the §3.5 capability table. Each entry describes the gap CORTEX addresses, the solution approach, and the prior art it builds on.

### Infrastructure

| Capability | Related Work | Full Rationale |
| --- | --- | --- |
| Oracle validation | SciPy/NumPy rtol/atol | Gap: Optimized C kernels (SIMD, fixed-point, cache-blocking) may introduce numerical errors undetected until classification accuracy degrades. BCI tools compare algorithms but don't verify C implementations against references. Solution: Every kernel has oracle.py (Python reference). cortex validate loads real EEG, runs C kernel + oracle, compares with tolerance (rtol=1e-5, atol=1e-6; relaxed for welch psd). Supports –calibration-state for trainable kernels (ICA, CSP). Runs before benchmarks: correctness precedes performance. |
| Coordinated omission resistance | Gil Tene "How NOT to Measure Latency" [18]; wrk2 [35] | Gap: Naive benchmarks back off during stalls, missing tail latency. Tene showed this causes 10ms reported vs 25s actual. BCI difference: Streaming data arrives continuously regardless of processing state—failure mode is staleness/loss, not request queuing. Implemented: Replayer generates windows at constant rate, release_ts_ns captures intended time, all windows recorded, distributional percentiles reveal tails. Missing: HdrHistogram [36] correction algorithm, true parallel constant-rate generation. |
| Component separation | AWS primitives philosophy; Halide [27]/Darkroom [28]/TVM [29] | Gap: Benchmarking frameworks couple implementations with configurations, requiring code changes to adjust parameters or swap datasets. Solution: Independent primitives (kernels, configs, datasets) in versioned directories. Kernels expose algorithm parameters via config YAML—change parameters without recompiling. Does not provide algorithm/schedule separation a la Halide (loop order, vectorization, tiling changeable at schedule time). |
| SSH deployment | OpenSSH + rsync | Gap: Deploying to embedded devices (Jetson, Pi, SBCs) typically requires manual copying or complex cross-compilation toolchains. Solution: SSHDeployer orchestrates complete workflow: passwordless SSH verification, rsync with BCI-aware excludes, remote make build-only, optional on-device oracle validation, adapter daemon launch. Returns transport URI to harness. |
| Transports | BSD sockets; POSIX serial | Gap: BCI benchmarking spans local dev machines, network edge devices, and serial-connected embedded. Each needs different communication but same protocol. Solution: Unified cortex_transport_t interface with three implementations: Local (socketpair, 45µs P50), TCP (BSD sockets + TCP_NODELAY, 180µs localhost / 1.2ms LAN), Serial (termios 8N1, 12ms @ 115200 baud). URI-driven selection. |
| Protocol | CRC32 (IEEE 802.3); binary framing | Gap: Remote kernel execution needs message framing over byte streams. gRPC/Thrift too heavyweight for embedded. Solution: Custom binary protocol with 16-byte header (MAGIC "CRTX", version, type, length, CRC32). Three-phase handshake. 8KB chunking. Session/boot ID tracking. Little-endian wire format. ~1,500 lines of C (protocol + CRC + error handling + chunking), zero dependencies, embeddable on bare-metal STM32. |
| Device adapters | dSPACE [42] HIL patterns; MLPerf LoadGen [3] | dSPACE HIL validation architecture (real component + simulated environment + automated tests) maps to CORTEX (kernel + EEG replay + oracle). MLPerf: contrast—targets DNN inference, not streaming signal processing. Native adapter complete; embedded and FPGA adapters planned. |
| Kernel calibration | BCILAB [20]; Towards Zero Training [34] | BCI kernels (ICA, CSP) require subject-specific training. BCILAB established calibration workflow pattern; "Towards Zero Training" demonstrated filter transfer feasibility. Gap: ad-hoc state serialization, no deployment ABI. CORTEX: standardized cross-language calibration (Python trains → binary .cortex_state → C deploys via cortex_init()). |
| Synthetic datasets | PhysioNet [33]; MOABB [1] | Gap: Public datasets lag modern hardware by 7–10× (Neuralink N1: 1024ch, Paradromics: 1600ch). Solution: CORTEX synthetic generator enables scalability testing at 256–2048+ channels with memory-safe chunked generation (<200MB peak RAM). Signal types: pink noise (1/f spectrum), sine waves (filter validation). |

### Measurement

| Capability | Related Work | Full Rationale |
| --- | --- | --- |
| Sustained measurement | MLPerf Inference [3] (early stopping); EEMBC [23] (≥10s runtime) | Gap: Short runs (1–5s) produce unreliable percentiles—insufficient samples, platform not at steady state (DVFS settling, cache warming, thermal ramp). Solution: CORTEX default 120s × 5 repeats = 600s total (~1,100 windows at 2/sec after 10s warmup). Captures steady-state behavior and sufficient samples for accurate P50/P95/P99. |
| Warmup protocol | FFTW [25] two-phase measurement; SPEC [21] warmup; Google Benchmark | Gap: Sub-100µs kernels dominated by cold-start effects—cache misses (20× penalty), DVFS upscaling, thermal ramp. Solution: CORTEX runs N warmup windows (default 10s) to stabilize caches/DVFS/thermals, then discards warmup telemetry. Unlike Google Benchmark's same-data batching, CORTEX processes distinct windows during warmup—realistic cache behavior. |
| Load profiles | stress-ng [41] (75+ CPU stressors); sysbench | Gap: BCI kernels (50–80µs every 6.25ms = <2% utilization) trigger DVFS downscaling—governors misinterpret bursty workloads as idle. Causes 2.3× latency penalty (macOS) and 3.2× penalty (Linux powersave). Solution: Three-tier declarative profiles (idle/medium/heavy) spawn stress-ng with platform-aware parameters. Medium load forces DVFS to maintain frequency—user-space proxy for performance governor on locked-down platforms. |
| Two-phase measurement | FFTW [25] init/execute separation | Gap: Generic benchmarks conflate one-time setup with per-invocation cost. Production amortizes setup over millions of windows—per-window latency is what matters. Solution: ABI enforces separation: cortex_init() (allocate state), cortex_process() (hermetic, measured), cortex_teardown(). Allocations in process() are contract violations. |
| Platform-state capture | perf [38]/ftrace; sysfs; eBPF/bpftrace; Perfetto | Gap: Sub-100µs kernels exhibit 2–4× latency variance from DVFS/thermal effects [17]. Without per-window platform telemetry, can't distinguish kernel regression from platform downclocking. Implemented: Thermal capture via sysfs. Missing: CPU frequency, governor state, compiler flags. |
| Statistical confidence | MLPerf [3] early stopping with CI; Kalibera & Jones [19] | Gap: 71/122 benchmarking papers report only point estimates without confidence intervals (Kalibera & Jones). Can't determine if 50µs vs 55µs is significant or noise. Implemented: 1,200 windows per run, full distribution stats. Missing: std not converted to CI—no "mean ± CI (95%)" reporting. |
| Multi-dtype kernels | CMSIS-DSP [26] Q15/Q31; MLPerf [3] INT8 quantization | Gap: Edge deployment (ARM Cortex-M, mobile) requires fixed-point—32-bit float consumes 2–4× memory and 10–50× power vs Q15/Q7. ABI defines FLOAT32, Q15, Q7 as first-class types. All kernels implemented as f32. Missing: Q15/Q7 implementations, degradation comparison tools. |
| Performance counters | Linux perf [38]; Intel VTune; ARM Streamline; PAPI | Gap: Diagnostic framework uses model-based attribution but lacks actual micro-architectural event capture. Without counters: "kernel is slow" (guess). With counters: "30M cache misses, 0.5 IPC → memory-bound" (actionable). Planned: Extend platform-state capture to include hardware PMU events on supported platforms. |

### Analysis

| Capability | Related Work | Full Rationale |
| --- | --- | --- |
| Latency distribution | MLPerf [3] P90/P99; fio [37] histogram-based; HdrHistogram [36] | Gap: Mean/median hide tail latency critical for real-time [2]. A kernel with 50µs mean but 500µs P99 violates deadlines despite acceptable average. Solution: CORTEX records per-window latency, computes full distribution (median, P95, P99, std). CDF plots for visual analysis. Uses pandas quantile; HdrHistogram deferred to v1.0+ for 1M+ runs. |
| Deadline analysis | LTTng [39] snapshot mode; Cyclictest [40]; RTOS WCET | Gap: Real-time BCI requires 160Hz (6.25ms budget). Missing deadlines corrupts temporal sequences. Implemented: Per-window deadline tracking, miss rate computation, deadline miss plots. Missing: Formal CLI (cortex check-deadline), root cause correlation. |
| Analysis/reporting | MLPerf [3] submission format; SPEC [21] disclosure requirements | Gap: Results without execution context are misleading—"50µs" means nothing without CPU, compiler flags, governor, thermal state. Solution: cortex analyze generates latency/CDF/throughput plots (PNG/PDF/SVG), SUMMARY.md with execution environment, full statistics. Missing vs MLPerf/SPEC: compiler flags not in telemetry yet. |
| Comparative analysis | MLPerf [3] statistical confidence; Welch t-test; Cohen's d | Gap: "Did my optimization improve performance?" requires statistical testing, not eyeballing means. With large samples (1200 windows), tiny differences become statistically significant even if practically irrelevant. Implemented: Visual comparison via CDF overlay and bar charts. Missing: cortex compare CLI, automated regression detection. |
| Latency decomposition | Roofline [30]; nn-Meter [8] | Gap: Measured latency alone can't attribute bottlenecks—is 85µs CAR compute-bound or memory-bound? Without decomposition, optimization is trial-and-error. Planned: Static analyzer parses kernel C → FLOPs/memory ops; combine with device specs; Roofline-based attribution decomposes into compute/memory/platform time. |
| Diagnostic framework | Roofline [30]; async-profiler; eBPF | Gap: Profilers report aggregate latency but don't attribute bottlenecks. Planned: Combine static analysis + device specs + measured latency. Compare predicted vs actual—residual reveals hidden overhead. Output: percentage breakdown with actionable recommendations. |
| Mandatory reporting | EEMBC CoreMark [23]; MLPerf [3]; SPEC [21] | Gap: Cross-platform comparison meaningless without context. gcc -O2 vs -O3 = 2× difference. Governor powersave vs performance = 2–4× (Idle Paradox). Existing: Telemetry has OS, CPU model, thermal. Missing: Compiler version/flags, CPU governor, frequency in telemetry records. |

### Validation

| Capability | Related Work | Full Rationale |
| --- | --- | --- |
| Oracle contribution workflow | MOABB [1] contribution guidelines; MLPerf reference requirements | Gap: Adding kernels requires manual 10-step process (1,171 lines of docs). First-time contributors spend 4–20 hours. PRs fail CI for missing files or broken oracles. Implemented: Comprehensive written guide, example kernels as templates. Missing: Scaffolding CLI (cortex new-kernel), pre-submission validation (cortex check-kernel). |
| SNR-based validation | CMSIS-DSP [26] SNR thresholds; EEMBC AudioMark [24] 50dB tolerance | Gap: rtol/atol works for time-domain kernels but misses perceptual quality for frequency-domain. Fixed-point Q15 might fail rtol but have acceptable 40dB SNR. Planned: Add snr_db_min to spec.yaml (60dB float32, 40dB Q15). Compute SNR = 10·log10(signal²/noise²) in cortex validate. |
| Scaled tolerance | LAPACK [32] test ratio; Higham [31] numerical stability | Gap: Fixed rtol=1e-5 treats CAR (64 ops) identically to Welch PSD (200K ops). Roundoff accumulates O(√n) statistically. Workaround: Welch PSD manually relaxes to rtol=2e-3. Planned: rtol = base_rtol × √n, atol = base_atol × n × ulp. LAPACK-style two-tier severity. |

### Future / Advanced

| Capability | Related Work | Full Rationale |
| --- | --- | --- |
| Pipeline composition | Darkroom [28] streaming model; ILP buffer scheduling | Gap: cortex pipeline runs all kernels sequentially on the same dataset (implemented), but real BCI chains bandpass→CAR→CSP where one kernel's output feeds the next. End-to-end latency ≠ sum of individuals—inter-kernel overhead adds 10–30%. Planned: Chained sequential streaming with per-stage telemetry. Intermediate buffers (~40KB) fit L2—no DRAM round-trips. |
| Scenario-based testing | MLPerf [3] Singlestream/Server/Offline scenarios | Gap: Single-stream benchmarking measures kernel latency in isolation. Real BCI faces variable load—when 7ms kernel meets 6.25ms window, queue builds, cascading deadline misses. Implemented: Sequential processing, per-window deadline detection. Missing: Queueing model, Poisson arrivals, deadline-aware scheduling. |
| Power/energy | SPEC Power [22] PTDaemon; MLPerf Tiny [43]; Foresee [44] | Gap: CORTEX measures latency but ignores power—critical for battery-powered BCI. M1: 2.1ms at 15W (31.5mJ/window). Snapdragon: 4.8ms at 3W (14.4mJ/window). Snapdragon is 2.3× slower but 2.2× more energy-efficient. Planned: Optional power.enabled with hardware abstraction layer. |
| Hardware feasibility | Foresee [44]; Yosys/OpenSTA; iverilog | Gap: FPGA/ASIC architects need early feasibility estimates before RTL development. No path from BCI kernel specs to hardware projections. Planned: Define Foresee integration points. Extends CORTEX from software benchmarking to hardware-software co-design. |
| Labeled datasets | MOABB [1] 67+ datasets; PhysioNet [33]; BCI Competition | Gap: AR persona needs ground-truth labels for efficacy metrics. Decision: Defer to MOABB integration. MOABB already provides 67+ datasets, 1,735+ subjects, standardized evaluation protocols. Future: "Does CSP maintain 94% accuracy while meeting 10ms deadline on Jetson?" |
| Efficacy benchmarking | MOABB [1]; BCI2000 [5]/OpenViBE [6]; Paradromics SONIC ITR | Gap: Tools measure accuracy or latency, never both. MOABB excels at offline accuracy but ignores deployment. Paradromics SONIC introduced rigorous ITR with 56ms total latency—first to combine both. Decision: Defer accuracy to MOABB, CORTEX focuses on latency. |
