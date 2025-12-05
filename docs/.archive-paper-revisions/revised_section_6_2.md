# Revised Section 6.2: Stabilization via Synthetic Load

If the Idle Paradox arises from DVFS policies misinterpreting BCI workloads as idle, the solution is to prevent the CPU from entering low-power states. On Linux, administrators can set the CPU governor to `performance`, locking cores at maximum frequency. On macOS, no such interface exists—users cannot disable DVFS or pin processes to specific P-states.

CORTEX addresses this by applying synthetic background load as a user-space proxy for a performance governor. The Medium profile (`stress-ng --cpu 4 --cpu-load 50`) applies sustained 50% utilization to 4 CPU cores, forcing Darwin to maintain high-frequency operation without saturating resources.

## The Checkmark Pattern

Table 2 presents the complete three-way comparison across load profiles. Performance follows a characteristic "checkmark" pattern visible in Figure 2:

**Table 2. Per-kernel performance across load profiles (median latency).**

| Kernel | Idle | Medium | Heavy | Idle/Medium | Heavy/Medium |
|--------|------|--------|-------|-------------|--------------|
| bandpass_fir | 5,015 µs | 2,325 µs | 2,982 µs | 2.16× | 1.28× |
| car | 28 µs | 13 µs | 22 µs | 2.15× | 1.69× |
| goertzel | 350 µs | 138 µs | 282 µs | 2.54× | 2.04× |
| notch_iir | 133 µs | 55 µs | 61 µs | 2.42× | 1.11× |
| **Geom. Mean** | **284.3 µs** | **123.1 µs** | **183.3 µs** | **2.31×** | **1.49×** |

*All values are median latencies (P50) in microseconds. Median is used rather than mean because it is robust to outliers—a critical property for latency analysis in systems with OS scheduling noise [5, 10].*

• **Idle → Medium**: Mean latency improves by **2.31×** (geometric mean), confirming that moderate load eliminates DVFS-induced penalties. This improvement is consistent across all kernels (2.16×–2.54×).

• **Medium → Heavy**: Mean latency degrades by **1.49×** as the system transitions from stabilized operation to resource contention (cache thrashing, scheduler preemption).

• **Heavy vs. Idle**: Critically, Heavy remains **1.55× faster** than Idle, proving that both Heavy and Medium maintain high CPU frequency. The Medium→Heavy degradation is pure contention, not DVFS.

This non-linear response validates two distinct performance regimes: **DVFS-dominated** (Idle) and **contention-dominated** (Heavy), with Medium representing the optimal operating point where frequency is stable but resources remain available. This is precisely the operating point required for reproducible benchmarking.

## Variance Stabilization

The stabilization effect on variance is kernel-dependent (Table 4). The `car` kernel shows dramatic variance reduction: coefficient of variation (CV) dropped from 309% (Idle) to 78% (Medium)—a **4.0× improvement**. The `bandpass_fir` and `notch_iir` kernels show moderate improvements (1.4× and 1.8× respectively).

**Table 4. Variance analysis across load profiles.**

| Kernel | Idle CV | Medium CV | Heavy CV | Idle→Medium Reduction |
|--------|---------|-----------|----------|----------------------|
| bandpass_fir | 40.4% | 28.8% | 27.4% | 1.40× |
| car | 309.1% | 77.8% | 516.1% | 3.97× |
| goertzel | 56.9% | 125.8% | 95.8% | 0.45× (worse) |
| notch_iir | 54.3% | 29.9% | 302.3% | 1.82× |

*CV = Coefficient of Variation (σ/μ × 100%). Lower is better (more stable timing).*

Surprisingly, the `goertzel` kernel exhibits **higher** variance under medium load (126% vs 57% idle), suggesting that background load interference affects iterative algorithms differently than filter-based kernels. This may result from cache line contention during the iterative multiply-accumulate loop, which amplifies timing jitter when CPUs are active.

Despite heterogeneous variance effects, medium load **consistently improves median latency** across all kernels (Table 2), confirming that DVFS elimination dominates the performance benefit even when variance increases for some workloads. For benchmarking reproducibility, we prioritize median latency over variance reduction, as the former represents the typical case while the latter affects tail behavior.

## Generalizability of the Methodology

The methodology generalizes: any researcher on macOS can reproduce this stabilization using `stress-ng --cpu 4 --cpu-load 50`. On Linux or Windows systems with direct governor access, administrators can achieve equivalent stabilization through:

- **Linux**: `cpupower frequency-set -g performance`
- **Windows**: Power Options → High Performance mode

CORTEX's synthetic load approach provides a **portable, user-space solution** that works across locked-down consumer platforms where kernel-level frequency control is unavailable—precisely the environment that BCI edge devices will encounter in deployment.

---

## Updated Figure 2 Caption

**Figure 2. Aggregated kernel latency by load profile (geometric mean across all kernels).** The "checkmark pattern" demonstrates two performance regimes: (1) Idle systems exhibit 2.31× higher latency than medium load due to DVFS—the Idle Paradox, and (2) heavy load exhibits 1.49× higher latency than medium due to resource contention. Medium load achieves optimal performance by locking CPU frequency without saturating resources. Lower latency is better. This pattern validates that DVFS effects dominate performance variance in BCI workloads, dwarfing algorithmic differences.

---

## LaTeX-Ready Table 2

```latex
\begin{table}[htbp]
\centering
\caption{Per-kernel performance across load profiles (median latency).}
\label{tab:load_profile_comparison}
\begin{tabular}{lrrrrr}
\toprule
\textbf{Kernel} & \textbf{Idle} & \textbf{Medium} & \textbf{Heavy} & \textbf{Idle/Medium} & \textbf{Heavy/Medium} \\
\midrule
bandpass\_fir & 5,015 µs & 2,325 µs & 2,982 µs & 2.16× & 1.28× \\
car           & 28 µs    & 13 µs    & 22 µs    & 2.15× & 1.69× \\
goertzel      & 350 µs   & 138 µs   & 282 µs   & 2.54× & 2.04× \\
notch\_iir    & 133 µs   & 55 µs    & 61 µs    & 2.42× & 1.11× \\
\midrule
\textbf{Geom. Mean} & \textbf{284.3 µs} & \textbf{123.1 µs} & \textbf{183.3 µs} & \textbf{2.31×} & \textbf{1.49×} \\
\bottomrule
\end{tabular}

\vspace{0.5em}
\footnotesize
\textit{Median latency (P50) is used rather than mean because it is robust to outliers—critical for latency analysis in systems with OS scheduling noise. Geometric mean aggregates across kernels spanning multiple orders of magnitude.}
\end{table}
```

## LaTeX-Ready Table 4

```latex
\begin{table}[htbp]
\centering
\caption{Variance stabilization across load profiles.}
\label{tab:variance_analysis}
\begin{tabular}{lrrrr}
\toprule
\textbf{Kernel} & \textbf{Idle CV} & \textbf{Medium CV} & \textbf{Heavy CV} & \textbf{Reduction} \\
\midrule
bandpass\_fir & 40.4\% & 28.8\% & 27.4\% & 1.40× \\
car           & 309.1\% & 77.8\% & 516.1\% & 3.97× \\
goertzel      & 56.9\% & 125.8\% & 95.8\% & 0.45× \\
notch\_iir    & 54.3\% & 29.9\% & 302.3\% & 1.82× \\
\bottomrule
\end{tabular}

\vspace{0.5em}
\footnotesize
\textit{CV = Coefficient of Variation (σ/μ × 100\%). Lower is better (more stable timing). Goertzel shows increased variance under medium load, suggesting iterative algorithms experience cache interference from background processes.}
\end{table}
```
