# 1. The BCI Deployment Problem

Brain-computer interfaces translate neural activity into commands for external devices, enabling communication, motor restoration, and therapeutic intervention for patients with neurological conditions. The field has achieved remarkable clinical demonstrations: paralyzed patients controlling cursors, walking via thought-driven exoskeletons, and communicating through implanted speech decoders. Commercial interest is accelerating, with companies spanning invasive implants (Neuralink, Synchron, Blackrock Neurotech, Precision Neuroscience) and non-invasive systems (InteraXon, Cognixion, Kernel).

Yet a critical infrastructure gap separates these demonstrations from scalable deployment. BCI research has robust methodology for evaluating what algorithms compute (classification accuracy, information transfer rate) but almost none for evaluating how fast they compute it on target hardware. This specification addresses that gap.

## 1.1 The Deployment Gap

In current BCI research, deployment-grade software performance engineering on commodity edge devices is underrepresented [4]. Real-time research platforms exist—BCI2000 [5] and OpenViBE [6]—but they typically run on dedicated lab workstations with controlled environments. BCI2000's reference configurations cite "1.4-GHz Athlon" and "2.53-GHz Pentium 4" processors with specialized data acquisition boards [5]; OpenViBE's validation used "Intel Xeon 3.80 GHz" systems in immersive VR rooms [6]. These platforms were not designed for consumer devices subject to DVFS, thermal throttling, OS scheduling noise, and battery constraints [7, 8].

Studies have documented that decoders optimized offline "sometimes fail to achieve optimal performance online" [9], and that "prior work on neural implant algorithms has focused primarily on detection accuracy, with computational performance metrics often unreported" [4]. The BCI field has a disciplinary blind spot: what algorithms compute is well-characterized, but how fast they compute it on deployment hardware is not.

## 1.2 Scale Economics

At research scale (N=10 patients), custom hardware rigs are viable. At industry scale (N=100,000+), economics push toward mass-manufacturable external compute—often commodity-class SoCs—with continuously updatable software. Custom ASICs typically require very large volumes to amortize NRE costs, with industry analyses citing break-even points that can reach into the hundreds of thousands or millions of units depending on process node and design complexity [10]. Off-the-shelf electronics are rewriting the economics of BCI development, with industry estimates suggesting development costs can be reduced by roughly an order of magnitude compared to fully custom approaches [11].

## 1.3 The Thermal Wall

Thermodynamics reinforces this trajectory. Cortical implants face hard thermal limits before risking tissue damage. Bio-heat modeling studies have quantified maximum allowable power dissipation at 5.3–9.3 mW for a 1°C temperature rise in cortical implants [12], with ISO 14708-1 designating a 2°C safety limit for active implantable medical devices [13]. Simple closed-loop applications (e.g., seizure detection) can fit within this envelope. Complex decoding (speech, high-DOF motor control) and general-purpose interfaces cannot.

## 1.4 Compressive Radio Architectures

These thermal constraints make Compressive Radio architectures—where thermal-constrained implants handle acquisition and compression while edge devices handle decoding—thermodynamically necessary as application complexity increases. Demonstrated systems achieve 8× compression ratios on-implant [14], and offloading neural network decoders externally can reduce implant power by 10× [15]. As one study noted: "it took so much power to transmit the data that the devices would generate too much heat to be safe for the patient" [15].

Cloud offload is precluded by closed-loop latency requirements—motor BCIs require real-time feedback that typical cloud round-trip times cannot reliably provide under variable network conditions. Additional barriers include intermittent wireless connectivity in mobile use cases and privacy constraints for neural data classified as protected health information under HIPAA and GDPR. The processing must happen at the edge.

## 1.5 Platform Effects on Edge Devices

When BCI processing moves to commodity edge hardware, practitioners confront platform effects that custom silicon designed away. Mobile inference studies document significant latency variability under CPU resource contention—"a DNN model with better latency performance than another model can become outperformed when resource contention becomes more severe" [7]. Benchmarking methodology must lock CPU frequency to eliminate DVFS-induced measurement variability [9], and account for heterogeneous frequency domains and thermal constraints across big.LITTLE architectures [16].

The Idle Paradox validates this empirically. In CORTEX's cross-load-profile experiments on an Apple M1 platform (n ≈ 1,200 measurements per kernel per load profile, p < 0.001 via Welch's t-test), standard BCI kernels exhibited ~50% latency degradation when benchmarked on idle systems versus medium-load conditions. macOS DVFS policies misinterpreted bursty, low-duty-cycle BCI workloads as idle, downclocking the CPU and incurring wake-up penalties. Prior measurement approaches—batch execution on idle systems—systematically underestimate real-world latency by approximately 2×. Platform state is not noise to be eliminated; it is a first-order experimental variable.

## 1.6 Who Needs This Infrastructure

Three distinct personas require deployment-grade BCI benchmarking, each with different relationships to the problem described above. These are parallel workflows, not a linear pipeline—most algorithms stay in Python, most C implementations never go to custom hardware.

| Persona | Description | CORTEX Enables |
| --- | --- | --- |
| Algorithm Researcher | Implements algorithms in Python/MATLAB for rapid prototyping. Primarily interested in efficacy/accuracy, but needs to validate real-time feasibility before investing in optimized implementations. | Correctness against reference implementations; real-time feasibility assessment |
| Software Engineer | Implements algorithms in C/C++ for execution on edge processors (phones, wearables, embedded Linux). Takes a validated algorithm and produces a production implementation meeting latency constraints on consumer hardware. | Latency distributions (P50/P95/P99), cross-platform comparison, platform effect characterization, bottleneck attribution |
| Hardware Engineer | Implements algorithms in Verilog/SystemVerilog for FPGA/ASIC. Designs custom hardware to meet latency targets unattainable on general-purpose hardware while preserving correctness. | Latency on FPGA vs ARM, implementation comparison, cross-platform validation against same oracle |

**Why Software Engineer First**

CORTEX prioritizes the Software Engineer persona because (1) the deployment gap is documented—decoders optimized offline fail to achieve optimal performance online [9]; (2) scale economics favor commodity hardware where platform effects are unavoidable; (3) thermodynamics requires edge compute via Compressive Radio; and (4) no existing tool serves this persona's latency-on-real-hardware needs. AR and HE personas demonstrate architectural extensibility through shared primitives, not special-purpose workflows.

## 1.7 User Stories

The following user stories capture what each persona requires from CORTEX. Status indicates current implementation state: Exists (fully implemented), Partial (needs enhancement), or Planned (not yet implemented).

### Algorithm Researcher

| ID | User Story | Required Capabilities | Status |
| --- | --- | --- | --- |
| AR-1 | I need to evaluate my algorithm's accuracy AND know if a C implementation can meet real-time constraints. | Efficacy benchmarking, labeled datasets, latency measurement, oracle validation | Planned |
| AR-2 | I want to contribute my Python algorithm as an oracle so others can implement and benchmark optimized versions. | Oracle contribution workflow, spec generation, validation pipeline | Planned |

Implementation Note: AR efficacy benchmarking is deferred—MOABB [1] serves this need for offline accuracy evaluation. CORTEX complements MOABB by adding latency/correctness validation currently missing from BCI workflows.

### Software Engineer

| ID | User Story | Required Capabilities | Status |
| --- | --- | --- | --- |
| SE-1 | I have an oracle-validated C kernel. I need to characterize its latency distribution on a target device to determine if it meets a real-time deadline at P99. | Device adapters, latency distribution capture, deadline analysis | Partial |
| SE-2 | I'm choosing between two filter implementations. I need to compare their latency tradeoffs on the target deployment platform. | Comparative benchmarking, diff reports | Partial |
| SE-3 | I'm porting a float32 kernel to fixed16. I need to validate numerical correctness against the float32 oracle before measuring latency. | Multi-dtype oracle validation, degradation metrics | Partial |
| SE-4 | I need to characterize how platform state (idle vs. loaded) affects kernel latency on my target device. | Load profiles, platform effect isolation | Partial |
| SE-5 | My kernel runs slower than expected. I need to determine if it's compute-bound, memory-bound, or platform-effect-bound. | Static analysis, performance counters, platform-state capture, bottleneck attribution | Partial |
| SE-6 | I need to benchmark latency distribution (P50/P95/P99) under sustained load to guarantee consistent real-time performance. | Sustained measurement, warmup protocol, distribution capture | Exists |
| SE-7 | I need to understand why P99 latency is 4× worse than P50 so I can determine if it's algorithmic or platform-caused. | Latency distribution analysis, platform correlation, counter data | Partial |
| SE-8 | I need to measure end-to-end latency of my full pipeline (bandpass → CAR → CSP → classifier) to verify it meets real-time deadlines. | Pipeline composition, stage telemetry | Exists |
| SE-9 | I need to stress test my kernel with 1024 channels to validate it scales for next-generation implants. | Synthetic dataset generation, parameterized data | Exists |
| SE-10 | I need to train my CSP kernel on calibration data, save parameters, then deploy and benchmark the calibrated kernel. | Kernel calibration | Exists |
| SE-11 | I need to analyze benchmark results (latency CDF, deadline miss rate, throughput) and generate reports. | Latency distribution analysis, CDF generation, summary statistics, plot export, HTML reports | Exists |

### Hardware Engineer

| ID | User Story | Required Capabilities | Status |
| --- | --- | --- | --- |
| HE-1 | I'm comparing HLS vs hand-coded Verilog. I need to benchmark both on real FPGA with the same methodology. | FPGA adapter, kernel interface, comparative analysis | Planned |
| HE-2 | I'm targeting a Zynq SoC. I need to benchmark kernel latency on ARM vs FPGA fabric. | FPGA adapter, heterogeneous device adapters | Planned |

Implementation Note: HE workflows are planned for device adapter expansion. The same primitives (kernels, datasets, oracles) enable cross-platform comparison—only the device adapter changes.

### Coverage Summary

| Persona | Total | Exists | Partial | Planned | Coverage (Exists + Partial) |
| --- | --- | --- | --- | --- | --- |
| Algorithm Researcher | 2 | 0 | 0 | 2 | 0% |
| Software Engineer | 11 | 5 | 6 | 0 | 100% |
| Hardware Engineer | 2 | 0 | 0 | 2 | 0% |
| Total | 15 | 5 | 6 | 4 | 73% |

These 15 user stories across three personas represent the chaotic surface of BCI deployment needs. The next section distills the methodological principles that unify them.
