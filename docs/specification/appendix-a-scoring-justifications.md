## Appendix A: Detailed Scoring Justifications

Each cell in the cross-domain comparison table (§2.4) is justified below with evidence from the framework's paper, documentation, or run rules.

### P1: Latency Distribution Capture

| Framework | Score | Justification |
|-----------|-------|---------------|
| BCI2000 | Partial | BCI2000Certification records per-block timestamps and visualizes latency distributions, but these capture system-level roundtrip timing (ADC→processing→stimulus), not per-kernel invocation latencies. |
| MOABB | No | Reports only a single aggregate time field (training duration) per evaluation fold; no per-invocation latency data exists. Operates entirely offline on pre-recorded datasets. (Verified Feb 2026: v1.4.3 added execution time and environmental impact considerations but still no per-invocation latency API.) |
| MLPerf Inference | Yes | Server scenario records per-query latency; LoadGen reports P50–P99.9 percentiles. Raw per-query timing logs enable full distribution reconstruction and deadline-exceedance assessment. (Verified Feb 2026: v5.1 current.) |
| TailBench | Yes | Records ⟨service_time, e2e_time⟩ tuples for every request in `lats.bin`, parsed via `parselats.py` to produce full CDFs. Explicitly designed for tail-latency characterization. |
| SPEC CPU 2017 | No | Reports median of three runs (elapsed seconds) per benchmark and computes geometric-mean ratios. Batch-compute workloads have no per-invocation latency concept. |
| CoreMark | No | Produces a single aggregate Iterations/Sec score from total time divided by total iterations. No per-iteration timing, histogram, or percentile output. |
| Dhrystone | No | Reports a single Dhrystones/Second figure from `Begin_Time` and `End_Time` around the entire loop. No per-iteration or distributional measurement. |
| DeathStarBench | Yes | Uses wrk2 with HdrHistogram and coordinated-omission correction for full percentile spectra (P50–P99.999), plus Jaeger distributed tracing at RPC granularity. |
| SeBS | Yes | Measures latency at three levels (benchmark, provider, client) across 200+ invocations with 95th/99th percentile confidence intervals. Separately captures cold-start vs. warm distributions. |
| MiBench | No | A workload characterization suite originally analyzed via SimpleScalar simulation. Contains no timing harness, no per-invocation measurement, and no latency reporting. |

### P2: Numerical Correctness as Prerequisite

| Framework | Score | Justification |
|-----------|-------|---------------|
| BCI2000 | No | Certification validates timing thresholds (e.g., audio latency < 65 ms) as pass/fail, but never checks whether signal-processing kernels produce numerically correct outputs. (Verified Feb 2026: still no kernel correctness validation.) |
| MOABB | No | Computes classification scores (ROC-AUC, accuracy) as output metrics but does not validate intermediate computational correctness against a reference oracle. (Verified Feb 2026: v1.4.3 still accuracy-only; no per-invocation correctness validation.) |
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
|-----------|-------|---------------|
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
|-----------|-------|---------------|
| BCI2000 | No | Documents static hardware configuration (CPU model, clock speed) for certification but records no dynamic platform telemetry (frequency scaling, thermal throttling, load) alongside timing. (Verified Feb 2026: actively maintained with UI and usability improvements, but no platform-state telemetry added.) |
| MOABB | No | Results contain only dataset/subject/session/score/pipeline metadata. No platform-level variables; the `additional_columns` extension exists but no built-in platform telemetry is provided. |
| MLPerf Inference | No | System description JSON captures static configuration. Optional "Power" submission mode integrates SPEC PTDaemon for wall-level AC power and ambient temperature, but does not record CPU frequency, governor state, or on-die thermal data. (Verified Feb 2026: v5.1 Power measurement still uses wall-level AC via SPEC PTDaemon; no CPU frequency or governor telemetry in LoadGen.) |
| TailBench | No | Output contains only per-request ⟨service_time, e2e_time⟩ tuples. README recommends disabling C-states but these are configuration guidelines, not recorded measurements. |
| SPEC CPU 2017 | Partial | Requires disclosure of nominal/max MHz and power-management enabled/disabled; sysinfo captures OS/hardware details as static snapshots. Optional PTDaemon records wall-level AC power and ambient temperature, but not on-die CPU frequency, governor transitions, or junction thermal state. |
| CoreMark | No | Logs only buffer size, total ticks, iterations/sec, and compiler info. CoreMark/MHz requires the user to externally determine clock frequency—the benchmark itself does not measure it. |
| Dhrystone | No | A manual submission form asks for CPU model, clock, and OS, but these are user-reported text fields external to the benchmark. No runtime measurement of any platform variable. |
| DeathStarBench | No | The paper's authors use external tools (vTune, RAPL, perf) for platform analysis, but the framework's own tracing records only per-service latency—no platform-state correlation. |
| SeBS | No | Commercial FaaS platforms are black boxes where CPU frequency, thermal state, and co-location are unobservable. Local mode supports PAPI counters, but cloud (primary use case) provides zero visibility. (Verified Feb 2026: SeBS 2.0 added CPU allocation analysis and cold-start characterization, but no on-device platform state capture—cloud opacity remains fundamental.) |
| MiBench | No | Originally analyzed via SimpleScalar simulation. When run on real hardware, no instrumentation records CPU frequency, thermal state, or system load. |

### P5: Kernel–Device Latency Analysis

| Framework | Score | Justification |
|-----------|-------|---------------|
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