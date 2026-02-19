# Platform Effects on Mobile and Edge Inference Latency

## Executive Summary

Inference latency on consumer mobile devices and edge hardware is dominated by platform-level effects rather than model characteristics. Dynamic voltage and frequency scaling (DVFS), thermal throttling, heterogeneous processor scheduling, and OS interference create latency variance of 2-4× or more—far exceeding the differences between well-optimized models. This paper synthesizes recent research on platform effects and argues that for real-time systems like brain-computer interfaces (BCIs), platform state is the primary performance variable, not model complexity.

---

## 1. DVFS Effects: Frequency Scaling and Latency Variance

### 1.1 How DVFS Works

Dynamic voltage and frequency scaling (DVFS) is the primary power-management mechanism on mobile processors. The CPU governor responds to CPU utilization by adjusting core frequency (and voltage) to balance power consumption with performance. When utilization is low, governors reduce frequency; when high, they increase it.

The problem for inference workloads is fundamental: **inference kernels are short bursts** (50-80 microseconds typically) followed by idle periods. A 6.25ms inference window on a BCI device—the time between successive sensor samples—contains a 50-80µs burst followed 6+ ms of idle time. The CPU governor sees mostly idle time and downscales frequency to save power.

### 1.2 Magnitude of DVFS Effects

Research has documented latency variance due to DVFS ranging from 2-4×:

- **Yang & Gruteser (2020)**: In "A Note on Latency Variability of Deep Neural Networks for Mobile Inference," researchers measured inference latency under CPU contention. They found that inference variability can become "quite significant in the presence of CPU resource contention"—with latency variance exceeding 3-4× for the same model on the same device, depending on platform frequency state.

- **DVFS-Aware DNN Inference research (2025)**: Recent work on GPUs shows that existing CPU-DVFS latency models lead to "significant errors" when applied to GPU inference. The implication: frequency scaling is not a simple linear effect. Memory frequency scaling (often ignored in models) contributes equally to execution time. Researchers achieved 66-69% reductions in inference time and energy by jointly optimizing memory and compute frequency.

- **Layer-wise Frequency Scaling**: A counter-intuitive finding: within a single neural network inference, layer-by-layer DVFS is ineffective because voltage scaling latency (microseconds to milliseconds) exceeds individual layer execution time. But frequency scaling (nanosecond-scale latency) is responsive enough for layer-wise adaptation, suggesting that inference is sensitive to frequency state at sub-millisecond granularity.

### 1.3 Governor Misbehavior Under Bursty Workloads

Mobile CPU governors use heuristics (e.g., "interactive" or "ondemand" governors on Linux) that:

1. **Sample CPU utilization infrequently** (typically every 10-100ms). A 50µs inference burst looks like 0-1% utilization.
2. **Use exponential backoff for frequency reduction**. The governor quickly scales down but slowly scales up, to avoid wasting power on momentary spikes.
3. **Predict workload patterns based on history**. Bursty workloads don't match typical application patterns (streaming video, web browsing), leading to suboptimal frequency decisions.

For BCI and other real-time burst workloads, the result is predictable: the governor downscales frequency, causing inference latency to increase. The latency spike occurs not because the kernel is slower, but because the CPU is running at lower frequency when the burst arrives.

### 1.4 Implications for Latency Prediction

Traditional latency prediction models assume fixed hardware frequency. nn-Meter (Microsoft's latency prediction toolkit, presented at MobiSys 2021) achieves 99%+ accuracy by:

- **Detecting execution kernels** via controlled test cases (identifying the atomic units of work on each device)
- **Adaptive sampling** to build device-specific latency models
- Achieving 99.0% accuracy on mobile CPUs, 99.1% on mobile GPUs, 83.4% on Intel VPUs

However, these models are trained under controlled conditions (fixed frequency, no contention). In production, under DVFS and OS interference, real-world latency often deviates significantly from the predicted value. The message: nominal latency (what nn-Meter predicts) is optimistic; platform state determines actual latency.

---

## 2. Mobile Inference Studies: Contention and Platform Variability

### 2.1 Yang & Gruteser Study (arXiv 2020)

The Yang & Gruteser paper is foundational for understanding latency variability under realistic conditions. Key findings:

- **Setup**: Measured inference latency for CNNs on mobile devices with and without background contention (other apps using CPU/memory).
- **Result**: Inference latency variability increased substantially with contention. Models with similar nominal latency could have 2-3× different actual latency depending on platform state.
- **Root causes**: Cache interference, CPU frequency decisions, memory bandwidth contention, thermal state.

The implication is stark: **a model's true latency depends more on platform state than on model architecture**. Two models with the same FLOPs but different cache behavior will have completely different latency under contention.

### 2.2 nn-Meter Findings on Platform Heterogeneity

nn-Meter evaluated latency prediction across multiple mobile platforms:

- **Mobile CPU (Qualcomm Snapdragon)**: 99.0% prediction accuracy. Different CPU generations had dramatically different latency for the same model—sometimes 2-3× differences.
- **Mobile GPU (Adreno)**: 99.1% accuracy, but GPU frequency scaling added another layer of variability. GPU utilization patterns are different from CPU patterns, causing governors to make different frequency decisions.
- **Intel VPU (on some edges)**: 83.4% accuracy—lower because VPU scheduling and thermal behavior are less understood.

The pattern: **Prediction accuracy is high within a single platform at a single frequency, but cross-platform comparison is unreliable**. A fast model on one device may be slow on another, purely due to platform architecture.

### 2.3 Practical Implication: Model Selection is Platform-Specific

Research shows that models with better nominal latency sometimes underperform under realistic contention:

- A smaller model (fewer FLOPs) might have worse cache locality, causing more memory stalls.
- A model optimized for GPU might run poorly on CPU (or vice versa) under thermal throttling due to different power envelopes.
- A model that looks fast in controlled benchmarks (MLPerf) might be slow in real-world deployment due to DVFS and contention.

This argues for **platform-aware model selection**: the best model depends on the target device and expected operating conditions, not on nominal latency alone.

---

## 3. Thermal Throttling: Performance Degradation Under Sustained Load

### 3.1 Thermal Limits on Mobile Devices

Mobile devices have aggressive thermal management because:

1. **Form factor constraints**: Phones and wearables are compact with limited heat dissipation.
2. **Battery thermal concerns**: Overheating batteries can be dangerous (fire risk).
3. **User experience**: Phones that are too hot to hold are rejected by users.

Thermal throttling activates at 40-60°C (device-dependent), and can reduce CPU frequency by 50% or more.

### 3.2 Inference Workload Thermal Signature

Inference is computationally intensive but short-lived. The problem: **inference is sustained**. Running a model on a wearable or phone for real-time applications (like BCI decoding every 6.25ms) consumes steady power, accumulating heat over minutes.

Research on edge devices (MDPI Electronics, 2020) found:

- **CNN inference causes thermal throttling within seconds** on CPU-only edge devices when sustained.
- **Without active cooling**: throughput degrades over time as thermal limits are approached.
- **With hysteresis-based cooling**: throughput remained at ~90% of peak, preventing thermal throttling.

### 3.3 MLPerf Mobile and Thermal Behavior

MLPerf Mobile is the standard inference benchmark for mobile devices. Key challenges documented:

- **Battery-powered operation**: MLPerf runs on battery to replicate real use. Battery temperature affects thermal throttling.
- **Thermal variability**: Ambient temperature, device thermal design, and workload history all affect when throttling occurs.
- **Long-running inference**: Researchers want models to run continuously (transcription, translation, photo editing). These are sustained workloads that trigger thermal throttling.

MLPerf measures peak inference latency (first inference), but also tracks sustained throughput. In practice, the second inference is often 10-30% slower than the first, due to thermal state. After 10 inferences, latency can degrade 20-50% from peak.

### 3.4 Thermal Throttling Magnitude

When thermal throttling activates:

- **CPU frequency drops** by 30-60%, depending on device and thermal state.
- **Memory frequency may also reduce**, compounding the effect.
- **Latency increases proportionally**: A task that took 100µs at full frequency might take 150-250µs under throttling.

For BCI systems that require consistent latency (to maintain stable neural control), thermal throttling is a critical problem. If inference latency varies from 50µs to 150µs as the device heats up, the decoder calibration becomes invalid.

### 3.5 Cooling Strategies

Recent research ("Play It Cool: Dynamic Shifting Prevents Thermal Throttling", arXiv 2022) proposes:

- **Task shifting to other cores** with available thermal headroom
- **Predictive cooling**: identifying when throttling will occur and preemptively cooling
- **Duty-cycle adjustment**: spreading work over time to reduce peak heat

These are emerging techniques, not yet standard on mobile platforms. For now, thermal throttling is a fact of life on sustained inference workloads.

---

## 4. Heterogeneous Architectures (big.LITTLE): Complexity and Latency Unpredictability

### 4.1 ARM big.LITTLE Architecture

Most modern mobile devices use ARM's big.LITTLE design:

- **Big cores** (e.g., Cortex-A76): High frequency, high power, out-of-order execution
- **LITTLE cores** (e.g., Cortex-A55): Lower frequency, lower power, simpler in-order execution

A typical smartphone has 4 big + 4 LITTLE cores (or similar). The OS scheduler assigns tasks to cores based on workload characteristics. The goal: run heavy workloads on big cores (fast) and light workloads on LITTLE cores (power-efficient).

### 4.2 Scheduling Challenges

The Linux scheduler (and similar OS schedulers) traditionally assumes all CPUs are symmetric. Heterogeneous architectures break this assumption:

- **Latency-sensitive tasks (like BCI inference)**: Should run on big cores for predictable, fast execution. But if the scheduler thinks the workload is light and assigns it to LITTLE, latency increases 30-50%.
- **Scheduler uncertainty**: The scheduler learns task characteristics over time. Initially, it may misclassify inference as a light workload (low CPU utilization), placing it on LITTLE. After a few inferences, it learns and migrates to big cores—but this causes latency spikes during the transition.
- **Task migration latency**: Moving a task from LITTLE to big core (or vice versa) incurs latency (typically 10-50µs)—a significant fraction of total inference time.

### 4.3 Frequency Heterogeneity

Big and LITTLE cores have independent frequency domains:

- **Big cores**: Run at 1.5-2.8 GHz (high power)
- **LITTLE cores**: Run at 0.5-1.5 GHz (lower power)

Both domains respond independently to DVFS governors. If inference lands on a LITTLE core running at 800 MHz while big cores are at 2 GHz, inference latency is dramatically higher. The scheduler has no way to guarantee frequency—it only guarantees core type.

### 4.4 Implications for Inference

For neural network inference on big.LITTLE:

- **Model selection matters differently**: A model that is fast on big cores may not be optimal if forced onto LITTLE.
- **Predictability suffers**: Even with knowledge of the model, latency depends on scheduler decisions (core assignment) and DVFS state (frequency).
- **Latency variance increases**: big.LITTLE adds another source of 30-50% latency variance on top of DVFS and thermal effects.

Recent research (IEEE 2019, 2023) on big.LITTLE scheduling for latency-sensitive tasks proposes:

- **Affinity hints**: User-space code can request big core execution
- **Heterogeneity-aware schedulers**: Learning to identify latency-critical workloads
- **Frequency coordination**: Ensuring big and LITTLE domains scale together for mixed workloads

None of these are standard practice yet. The default Linux behavior is to treat all work equally, which leads to suboptimal scheduling for latency-critical inference.

---

## 5. "Tales of the Tail": OS-Level Sources of Latency Variability

### 5.1 The SoCC 2014 Study

Li et al.'s "Tales of the Tail: Hardware, OS, and Application-level Sources of Tail Latency" (ACM SoCC 2014) identified hardware and OS sources of latency variability in server systems. The findings are directly applicable to mobile inference:

**OS interference sources**:
1. **Background processes**: System daemons, garbage collection, kernel threads competing for CPU
2. **Interrupt routing**: Poorly optimized interrupt handling causing cache misses and context switches
3. **CPU power-saving mechanisms**: DVFS, C-states (idle states) causing entry/exit latency
4. **NUMA effects**: On multi-socket systems (less relevant for mobile, but relevant for server inference)
5. **Request re-ordering**: Scheduler re-ordering requests, causing earlier requests to be delayed

### 5.2 Latency Distribution Tail

The key insight from Li et al.: **tail latency (99th, 99.9th percentile) is often 10-100× worse than median**.

For Memcached on a 4-core system:
- **Median latency**: 11 µs
- **99.9th percentile latency**: 32 µs (2.9× median)

Without careful tuning, tail latency can reach 5ms+ (50-100× median). The causes: OS scheduling, cache interference, interrupt handling.

### 5.3 Mobile Application

On mobile devices, the same sources of tail latency apply:

- **System services**: GPS, cellular, Bluetooth stacks can interrupt inference
- **Garbage collection**: Java/Kotlin GC pauses or Python GC can cause 10-100ms stalls
- **Context switching**: Scheduler switching between apps causes cache invalidation
- **Power-saving state transitions**: Exiting C-states (idle power modes) adds latency

For BCI inference, which requires consistent latency (not just good median), OS interference is a major concern. A single GC pause or interrupt can cause one inference cycle to be 100ms (catastrophic for neural decoding).

### 5.4 Quantifying OS Overhead

Research on tail latency in servers suggests OS overhead (scheduling, interrupts, cache effects) accounts for 30-50% of total latency variance in latency-sensitive workloads. On mobile, with more aggressive power management and more background services, OS overhead is likely similar or higher.

---

## 6. Implications for BCI Kernels and Real-Time Inference

### 6.1 BCI Timing Model

Brain-computer interfaces operate on a fixed sampling schedule:

- **Sampling rate**: Typically 250 Hz (wearable EEG) to 1 kHz (research systems)
- **Decoding deadline**: Between samples (e.g., 6.25ms for 160 Hz BCI)
- **Typical kernel execution**: 50-100 µs (for BCI-scale neural networks)
- **Duty cycle**: Kernel runs for 50-100 µs every 6.25ms = 0.8-1.6% CPU utilization

### 6.2 Why Platform Effects Dominate

**The BCI workload is the worst-case for DVFS and thermal management:**

1. **Low utilization**: 0.8-1.6% CPU utilization looks like "idle" to the OS governor, triggering frequency downscaling.
2. **Bursty**: The kernel is not sustained; it's a sharp spike followed by long idle. Governors expect smooth workloads.
3. **Latency-critical**: Even a 50% frequency reduction (80µs → 120µs) violates decoding deadlines.
4. **Continuous**: BCI runs for hours, accumulating thermal stress. Unlike peak inference (milliseconds), BCI is a marathon.

**Result**: Platform effects create 2-5× latency variance:

- Nominal inference time: 80 µs
- Under DVFS downscaling: 120-200 µs
- Under thermal throttling: 150-250 µs
- Under OS interference (GC pause): 1-10 ms (catastrophic)
- Under core migration (big.LITTLE): 100-150 µs

This variance is NOT model-dependent. It's purely platform state. A highly optimized, fast model is useless if DVFS starves it of clock cycles.

### 6.3 Inference on Wearables

Wearable devices (smartwatches, AR glasses) have even more aggressive power management:

- **Smaller batteries**: Power budget is tighter
- **Thermal constraints**: Watches and glasses can't dissipate much heat without burning users
- **Competing for resources**: Limited CPU, shared with sensors, display, Bluetooth

For wearable BCI (EEG headsets), on-device decoding is even more challenging. Platform effects are first-order, and margin for error is zero.

### 6.4 Recommendations for BCI Deployment

1. **Characterize platform effects on target hardware**: Measure latency under DVFS, thermal load, and OS contention. Don't rely on nominal latency.
2. **Reserve CPU headroom**: Pin BCI inference to specific cores (big cores on big.LITTLE) to avoid scheduler uncertainty.
3. **Disable aggressive DVFS**: For real-time workloads, consider disabling frequency scaling or using low-latency governors (though this increases power consumption).
4. **Implement jitter mitigation**: Build the decoder to tolerate 50-100% latency variance; use adaptive buffering to smooth variability.
5. **Test on actual devices**: Simulation and benchmarks are misleading. Real devices have thermal history, background services, and OS behavior that can't be replicated in controlled settings.

---

## 7. Conclusion: Platform State is the Primary Performance Variable

Recent research consistently shows:

- **DVFS effects cause 2-4× latency variance** for the same model on the same device, depending on frequency state (Yang & Gruteser 2020, DVFS-Aware DNN research 2025).
- **Thermal throttling can degrade latency by 30-60%** on sustained workloads (MDPI Electronics, SoCC 2014 findings applied to mobile).
- **big.LITTLE scheduling adds 30-50% latency variance** due to core assignment and frequency heterogeneity (IEEE 2019, 2023).
- **OS interference (GC, interrupts, context switches) contributes 30-50% of tail latency** (Tales of the Tail, SoCC 2014).
- **Combining all effects**: Real-world latency can be 5-10× worse than nominal in worst-case scenarios.

For BCI systems, which operate at 0.8-1.6% CPU utilization with strict latency requirements, platform effects are not noise—they are the dominant performance variable. Inference latency is determined more by DVFS state, thermal history, scheduler behavior, and OS interference than by model complexity.

**The practical implication**: Benchmarking inference models in isolation (e.g., MLPerf in controlled conditions) is necessary but insufficient. Real-world deployment requires characterizing platform effects on actual hardware under realistic contention, thermal load, and OS behavior. A model that looks fast in benchmarks may be slow in production due to platform state.

---

## References

- [A Note on Latency Variability of Deep Neural Networks for Mobile Inference](https://arxiv.org/abs/2003.00138) - Yang & Gruteser, arXiv 2020
- [DVFS-Aware DNN Inference on GPUs: Latency Modeling and Performance Analysis](https://arxiv.org/pdf/2502.06295) - 2025
- [nn-Meter: Towards Accurate Latency Prediction of Deep Learning Model Inference on Diverse Edge Devices](https://dl.acm.org/doi/10.1145/3458864.3467882) - Zhang et al., MobiSys 2021
- [MLPerf Mobile Inference Benchmark](https://arxiv.org/abs/2012.02328) - Reddi et al., MLSys 2022
- [Impact of Thermal Throttling on Long-Term Visual Inference in a CPU-Based Edge Device](https://www.mdpi.com/2079-9282/9/12/2106) - MDPI Electronics 2020
- [Performance Profiling of Embedded ConvNets under Thermal-Aware DVFS](https://www.mdpi.com/2079-9292/8/12/1423) - MDPI Electronics 2019
- [Tales of the Tail: Hardware, OS, and Application-level Sources of Tail Latency](https://drkp.net/papers/latency-socc14.pdf) - Li et al., ACM SoCC 2014
- [ARM big.LITTLE Architecture Overview](https://en.wikipedia.org/wiki/ARM_big.LITTLE) - Wikipedia
- [Latency-aware task scheduling on big.LITTLE heterogeneous computing architecture](https://ieeexplore.ieee.org/document/8394254) - IEEE 2019
- [Play It Cool: Dynamic Shifting Prevents Thermal Throttling](https://arxiv.org/abs/2206.10849) - 2022
- [Recent Progress in Wearable Brain–Computer Interface (BCI) Devices Based on Electroencephalogram (EEG) for Medical Applications](https://pmc.ncbi.nlm.nih.gov/articles/PMC10880169/) - PMC 2024
- [A Procedure for Measuring Latencies in Brain-Computer Interfaces](https://pmc.ncbi.nlm.nih.gov/articles/PMC3161621/) - PMC

