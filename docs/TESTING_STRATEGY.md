## Testing Strategy: HIL vs Full On‑Device vs Stochastic Calibration

### Purpose
Capture the trade‑offs, when‑to‑use, and our current semester plan for three evaluation modes:
1) Hardware‑in‑the‑Loop (HIL, kernel‑mode), 2) Reference Full On‑Device (system‑mode), and 3) Stochastic Calibration (model‑based prediction).

### North Star (Scope)
We benchmark individual BCI signal‑processing kernels. The primary mission is comparable algorithmic efficiency (latency, jitter, energy, memory) on x86 this semester. Platform realism is handled via clearly documented limits and, later, per‑platform calibration.

---

## Modes

### 1) HIL (Kernel‑Mode)
- **What it is**: Isolated kernel measurement behind a stable ABI; everything else runs on the host harness. Used to quantify core compute cost with fixed inputs/outputs and deadlines.
- **Measures**: Kernel latency, jitter, energy (e.g., RAPL on x86), memory; apples‑to‑apples across kernels and builds.
- **Pros**: Simple, fast, reproducible; perfect for ranking kernels and studying quantization; minimal engineering per platform.
- **Limits**: Misses system overhead (interrupts, DMA setup, scheduler/context switches, memory/bus contention). Can under‑estimate real deployment by ~1.5×–2.0× for MCUs; smaller but non‑zero for FPGA/ASIC.
- **Use when**: Early design, cross‑kernel comparisons, exploratory quantization, academic reproducibility.

### 2) Reference Full On‑Device (System‑Mode)
- **What it is**: A representative, end‑to‑end pipeline on target class (e.g., MCU with RTOS + DMA, FPGA softcore + FIFOs). Measures kernel plus realistic overhead.
- **Measures**: End‑to‑end latency/energy; deadline miss rates under real ISR/scheduler/DMA/bus behavior.
- **Pros**: Deployment‑faithful; validates HIL predictions; quantifies overhead for that class.
- **Limits**: Platform‑specific (not universal); significantly more engineering per platform; harder to keep reproducible.
- **Use when**: Tight deadlines, multi‑kernel contention, or when publishing deployment guidance.

### 3) Stochastic Calibration (Model‑Based)
- **What it is**: Predict end‑to‑end time from HIL kernel time using a calibrated model:
  \( T_{total} = a + b \cdot T_{kernel} + \varepsilon \), where:
  - **a**: fixed per‑window overhead (ISR entry/exit, DMA setup, wakeups)
  - **b**: multiplicative effects (preemption, cache/bus contention)
  - **\(\varepsilon\)**: jitter (right‑skewed; often modeled lognormal)
- **Pros**: Much cheaper than full pipelines; yields p50/p95/p99 predictions and miss probabilities; still kernel‑centric.
- **Limits**: Requires a tiny on‑target calibration harness per platform to be credible; priors alone are only estimates.
- **Use when**: You want realistic predictions without building a full pipeline; you can run a minimal calibration.

---

## Recommended Plan (Fall 2025)
- **This semester (PC‑only)**
  - Run HIL on x86 with the harness (replayer → scheduler → plugin ABI), CSV telemetry, and energy via RAPL.
  - Clearly document scope: results are algorithmic lower bounds; apply conservative safety bands in reporting.
- **Next semester (platform realism)**
  - Add a tiny on‑device calibration harness per first target MCU (and optionally FPGA): timer/ISR + DMA stub + double buffer + tunable dummy work + cycle counter. Fit \(a,b,\varepsilon\) to produce platform‑specific factors.
  - Optionally implement one reference full pipeline per platform class (e.g., STM32F7 + FreeRTOS) to validate the model and publish overhead factors for that class.

---

## Safety Bands and Reporting
- **Default planning factors (when uncalibrated)**
  - MCU (Cortex‑M + RTOS): 1.5×–2.0× over HIL kernel latency
  - FPGA (softcore + DMA/FIFOs): 1.2×–1.5×
  - ASIC (well‑provisioned datapaths): 1.1×–1.3×
- **Pass/caution/fail suggestion** (by deadline at p95):
  - Pass: p95 utilization < 50%
  - Caution: 50–65%
  - Fail: > 65%

---

## Why HIL Alone Isn’t Enough (Evidence Snapshot)
- RTOS/context‑switch/ISR timing on Cortex‑M is microsecond‑scale per event and accumulates at kHz rates with multi‑stage pipelines. Published benchmarks and suites report meaningful overhead vs bare‑metal:
  - Zephyr timing benchmarks (ISR latency, thread switches): kernel timing microbenches per board.
  - SEGGER embOS benchmarks: task switch/interrupt measurements on Cortex‑M.
  - FreeRTOS guidance on interrupt latency/run‑time stats; emphasizes on‑target measurement.
  - EEMBC ULPMark‑RTOS: standardizes RTOS + workload overhead (energy/perf impact).
  - Vendor app notes (ST) on DMA setup/arbitration and ISR latency.
- Typical real‑time DSP/biomed pipelines report ~15–40% overhead; worst‑case scenarios higher depending on RTOS config, FPU save/restore, and memory/bus contention.

References (illustrative):
- Zephyr timing info and latency benchmarks: https://docs.zephyrproject.org/latest/samples/benchmarks/
- SEGGER embOS benchmarks: https://www.segger.com/products/rtos/embos/technology/benchmarks/
- FreeRTOS run‑time stats and latency notes: https://www.freertos.org/rtos-run-time-stats.html
- EEMBC ULPMark‑RTOS: https://www.eembc.org/ulpmark/rtos/
- ST DMA app note (F2/F4 example): https://www.st.com/resource/en/application_note/dm00046011-an4031-using-the-stm32f2-and-stm32f4-dma-controller-stmicroelectronics.pdf

---

## Minimal Calibration Harness (Next Semester)
- **Components**: periodic ISR (Fs), double buffer/DMA stub, scheduler wake path (RTOS or bare‑metal), tunable dummy kernel (cycle‑counted), precise timing (DWT_CYCCNT or GPIO + LA), CSV logging.
- **Procedure**:
  1) Measure “empty” pipeline to estimate **a** per window.
  2) Sweep dummy kernel durations; regress total vs kernel to estimate **b**.
  3) Collect 5k–10k windows to model jitter **\(\varepsilon\)** (lognormal).
- **Artifact**: `configs/calibration/<platform>.yaml` storing a, b, jitter params, board/RTOS/toolchain metadata.
- **Use**: Monte Carlo from HIL \(T_{kernel}\) → predict p50/p95/p99 \(T_{total}\), miss probability by deadline.

---

## Representativeness of Our Current Design
- **Replayer** streams hop‑sized chunks at cadence H/Fs; **Scheduler** forms overlapping windows and enforces deadlines. This mirrors typical BCI acquisition + buffering + windowing separation (hardware/data source vs processing pipeline).
- On real implants/ASICs, buffer/windowing may be in silicon; our split is still valid for benchmarking kernels as long as scope is documented and overhead is accounted for via calibration or reference runs.

---

## Practical Guidance
- For this semester’s x86 HIL goals: implement harness glue, CSV telemetry, CAR + notch, RAPL energy, and dataset preconversion. Publish clear scope and apply conservative safety bands.
- For platform realism next semester: add the calibration harness and, optionally, one reference full pipeline per platform class to validate and publish overhead factors.


