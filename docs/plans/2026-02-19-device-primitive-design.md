# Design: Device Primitive and Tiered Latency Decomposition

**Date:** 2026-02-19
**Status:** Draft
**Author:** Weston Voglesonger + Claude

## Problem Statement

CORTEX device information is fragmented across three disconnected systems: static YAML specs for hardware performance, `device_detect.py` for CPU auto-detection via a hardcoded lookup table, and `decomposition.py` for roofline prediction. None of these systems know about the device's **measurement capabilities** — what the target can observe about its own execution (PMU counters, OS noise tracing, frequency monitoring). Without measurement capability metadata, the analysis engine cannot determine what level of latency decomposition is possible on each target.

## Proposal

Elevate the **device** to a first-class primitive that encapsulates hardware specs, measurement capabilities, and compatible adapters. **Deployment strategy** (how to reach the device — SSH, serial, TCP, local) is specified in the **run config**, not the device primitive, because the same hardware can be reached different ways.

The user composes four primitives — **kernel + dataset + config + device** — and the system resolves everything else.

## Design

### 1. Primitive Taxonomy

```
primitives/
  kernels/v1/       # Signal processing plugins (bandpass_fir, car, ...)
  datasets/v1/      # Input data (physionet EEG recordings)
  configs/           # Benchmark settings (duration, metrics, load profile)
  devices/           # NEW: Complete device descriptions
  adapters/v1/      # Execution runtimes (internal, not user-facing)
```

Users think in four nouns: what kernel, what data, what settings, what device. Adapters are an internal implementation detail — the device knows which adapter to use.

### 2. Device Primitive Schema

The device primitive describes **what the hardware is** — not how to reach it. A Raspberry Pi 4 is a Pi 4 whether you SSH to it, connect via serial, or run locally on it.

```yaml
# primitives/devices/m1.yaml — annotated reference example
device:
  name: "Apple M1"

  # --- Hardware Specs (static) ---
  cpu_peak_gflops: 100.0          # 4 Firestorm cores x 3.2 GHz x 8 FLOP/cycle
  memory_bandwidth_gb_s: 68.25    # LPDDR4X unified memory
  cache:
    l1d_kb: 128                   # Per Firestorm core
    l1i_kb: 64
    l2_kb: 12288                  # 12 MB shared

  # --- Compatible Adapters ---
  adapters: [native]

  # --- Frequency Model ---
  frequency:
    model: fixed                  # fixed | dvfs
    max_hz: 3228000000            # P-core max frequency
    per_sample: false             # No APERF/MPERF on Apple Silicon

  # --- Measurement Capabilities (declared, validated at runtime) ---
  # PMU access requires sudo: macOS (kpc private framework), Linux (perf_event_open)
  pmu:
    instruction_count: true       # kpc fixed counter
    l1d_misses: true              # kpc event 0xa3
    memory_stall_hierarchy: false # No TMA equivalent on Apple Silicon
    backend_stall: false          # No STALL_BACKEND_MEM equivalent

  os_noise:
    tracer: null                  # No osnoise on macOS

  # --- Derived: What decomposition is possible ---
  decomposition_tier: 1
```

**Device summary (all supported targets):**

| Device | Peak GFLOPS | Memory BW | Freq Model | PMU | osnoise | Tier |
|--------|------------|-----------|------------|-----|---------|------|
| Apple M1 | 100.0 | 68.25 GB/s | fixed | insn+L1 | no | 1 |
| Raspberry Pi 4 | 13.5 | 8.5 GB/s | dvfs | insn+L1 | yes (osnoise) | 1 |
| Jetson Nano | 16.0 | 25.6 GB/s | dvfs | insn+L1 | no | 1 |
| Intel Xeon W-2295 | 460.0 | 80.0 GB/s | dvfs | full TMA | yes | 3 |

### 3. Decomposition Tiers

The tier determines what latency decomposition is possible. Higher tiers produce more components with tighter accuracy.

| Tier | Requirements | Decomposition | Accuracy |
|------|-------------|---------------|----------|
| **0** | No PMU access | Prediction from spec.yaml only (roofline model) | Low — theoretical bounds only |
| **1** | Instruction count + L1 misses | Compute (PMU lower bound) + residual (everything else) | Compute: tight. Residual: wide. |
| **2** | + backend stall counters + osnoise | Compute + memory (stall cycles) + I/O (osnoise attribution) | 3-component split with moderate accuracy |
| **3** | + full TMA hierarchy + per-sample freq | Compute + L1/L2/L3/DRAM stalls + I/O + frequency-normalized | Cache-level memory decomposition, tight accuracy |

Each tier builds on the previous. The decomposition engine queries `decomposition_tier` and adapts its analysis.

**Note:** PMU access requires sudo on macOS (kpc private framework) and Linux (`perf_event_open` with `CAP_SYS_ADMIN` or `perf_event_paranoid <= 1`). Runtime validation catches this and degrades the tier automatically.

### 4. Run Config: Separating Device from Deployment

Currently, the config conflates device identity with transport. After this change, device and deployment are separate, explicit fields:

```yaml
# cortex.yaml — local development (simplest case)
# device: omitted → auto-detect local machine
# deploy: omitted → local (no deployment needed)
dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  format: float32
  channels: 64
  sample_rate_hz: 160
benchmark:
  duration_seconds: 60
  warmup_seconds: 5
```

```yaml
# cortex.yaml — remote Pi via SSH (deployer handles everything)
device: rpi4                              # What hardware (primitives/devices/rpi4.yaml)
deploy: ssh://pi@192.168.1.100            # DeployerFactory routes to SSHDeployer
```

CLI overrides work naturally:

```bash
cortex run                                         # auto-detect local
cortex run --device rpi4 --deploy ssh://pi@rpi     # SSH deploy + benchmark
cortex run --device rpi4 --deploy tcp://pi:9100    # pre-deployed, direct connect
cortex run --device m1                             # explicit local device
```

The `deploy:` field routes through the existing `DeployerFactory.from_device_string()`:
- `ssh://user@host` → SSHDeployer (rsync → build → start adapter → return transport URI)
- `tcp://host:port` → direct transport URI (no deployment, adapter already running)
- `serial:///dev/...` → direct transport URI
- `stm32:` → JTAGDeployer (future)

### 5. Deployer: How Code Gets Onto the Device

The deployer is a **distinct concept** from the device, adapter, and transport. It's the orchestration pipeline that takes source code and a target device and produces a running adapter with a transport URI.

The existing deployer subsystem (`src/cortex/deploy/`) already implements this:

| Component | File | Role |
|-----------|------|------|
| Protocol | `deploy/base.py` | `Deployer` protocol: `deploy()` → `DeploymentResult(transport_uri)` |
| SSH | `deploy/ssh_deployer.py` | rsync code → remote build → validate → start adapter daemon |
| Factory | `deploy/factory.py` | Routes device strings to deployers or direct transport URIs |

**Four concepts, clean separation:**

```
Device Primitive     Deployer              Adapter           Transport
(what it IS)    →   (get code onto it)  → (execute kernels) ← (talk to it)
rpi4.yaml           SSHDeployer            native adapter     tcp://pi:9100
                    JTAGDeployer           native adapter     serial:///dev/...
                    (none — local)         native adapter     local://
```

The deployer is NOT specified in the device primitive. The same Pi 4 can be deployed to via SSH, JTAG, or run locally. Deployment strategy is a per-run choice.

### 6. Runner Resolution Flow

The Python runner (`src/cortex/utils/runner.py`) orchestrates all four concepts:

```
User: cortex run --device rpi4 --deploy ssh://pi@192.168.1.100

Runner:
  1. Load primitives/devices/rpi4.yaml (device = what it is)
  2. Resolve adapter: device.adapters[0] = "native"
  3. Route deployment via DeployerFactory:
     - "ssh://pi@192.168.1.100" → SSHDeployer
     - SSHDeployer.deploy(): rsync → build → validate → start adapter
     - Returns DeploymentResult(transport_uri="tcp://192.168.1.100:9100")
  4. Pass transport_uri to harness config
  5. Write adapter_path into generated harness config
  6. Launch harness (C engine) with generated config
  7. Store device.decomposition_tier for post-run analysis

Harness (unchanged C code):
  1. Reads config → gets adapter_path, reads CORTEX_TRANSPORT_URI
  2. device_comm_init() → parses URI → spawns/connects adapter
  3. HELLO/CONFIG/ACK handshake
  4. Scheduler loop → collect raw timing telemetry
  5. Write telemetry to output directory

Runner (post-run):
  1. Load telemetry
  2. Query device.decomposition_tier
  3. Run tier-appropriate decomposition analysis
  4. Report component distributions with accuracy estimates

Runner (cleanup):
  1. SSHDeployer.cleanup(): kill remote adapter, delete remote files
```

For the **local case** (no `--deploy` flag), no deployer runs. The runner sets `transport_uri="local://"` and the harness spawns the adapter directly via `fork/exec`. The C engine does not change.

### 7. Runtime Capability Validation

The device YAML declares **expected** capabilities. The runtime **validates** them:

```python
def validate_capabilities(device_spec) -> dict:
    """Probe actual capabilities, degrade tier if reality doesn't match declaration."""
    # Probe PMU access
    if device.pmu.instruction_count:
        if not probe_pmu_available():
            degrade to tier 0
            warn("PMU unavailable (need sudo?). Degrading to tier 0.")

    # Probe osnoise (Linux only)
    if device.os_noise.tracer == "osnoise":
        if not Path("/sys/kernel/tracing/osnoise").exists():
            degrade to tier 1
            warn("osnoise tracer not available. Degrading to tier 1.")

    # Probe per-sample frequency
    if device.frequency.per_sample:
        if not probe_aperf_mperf():
            degrade to tier 2
            warn("APERF/MPERF unavailable. Degrading to tier 2.")
```

This separates "what should work" (YAML) from "what actually works" (runtime). Users see clear messages when capabilities degrade, and the system adapts automatically.

### 8. Tiered Decomposition Analysis

#### Tier 0: Spec-Based Prediction Only

No runtime decomposition. Prediction uses roofline model from device specs:

```
compute_us = instruction_estimate / (cpu_freq_hz * IPC)
memory_us = data_bytes / memory_bandwidth
predicted = max(compute_us, memory_us)
```

#### Tier 1: PMU Compute Bound + Residual

Available everywhere PMU works (all platforms with sudo).

For each sample `L_i` in the measured distribution:

```
C_lower_i = instruction_count / (cpu_freq_hz * IPC_max)
C_upper_i = instruction_count / (cpu_freq_hz * IPC_min)
residual_i = L_i - C_i
```

Output: Two component distributions — `P(Compute)` and `P(Residual)`.

The noop baseline distribution characterizes the minimum residual (overhead floor). Deconvolution (Delaigle/Hall method) can remove this overhead distribution from the measured total.

#### Tier 2: Compute + Memory + I/O

Available on Linux ARM (Neoverse) and Linux x86 with osnoise.

```
C_i = instruction_count / (cpu_freq_hz * IPC)
M_i = stall_backend_mem_cycles / cpu_freq_hz
IO_i = osnoise_total_ns / 1e3
unexplained_i = L_i - C_i - M_i - IO_i
```

Output: Three component distributions + residual.

#### Tier 3: Full Cache Hierarchy + Frequency Normalization

Available on Intel x86 with TMA and APERF/MPERF. Full TMA Level 3 decomposition per sample with frequency normalization.

### 9. What the Device Primitive Does NOT Cover

**Deployment strategy.** How to get code onto the device is a per-run choice handled by the deployer subsystem. The device YAML doesn't know or care how you reach the hardware.

**Hardware health.** A device primitive does not track DRAM degradation, SSD wear, or thermal paste aging.

**Kernel-specific tuning.** The device describes hardware and measurement capabilities. Kernel parameters remain in kernel spec.yaml files.

**Real-time scheduling policy.** FIFO priority, CPU affinity, and deadline parameters remain in the benchmark config.

### 10. Migration Path

**Phase 1 (current):** Add measurement capability fields to device YAMLs. Replace `device_detect.py` lookup table with YAML-based resolve + validate. Surface `decomposition_tier` in predict/attribute output. No changes to run config schema, C engine, or deployer system.

**Phase 2:** Add device primitive support to the runner. If `device:` is specified in config, resolve adapter and transport from it.

**Phase 3:** Implement tier 1 distributional decomposition (PMU compute bound + deconvolution).

**Phase 4:** Implement tier 2/3 as Linux-specific extensions.

## Key References

| Topic | Source |
|-------|--------|
| Intel TMA | Yasin, ISPASS 2014; pmu-tools (Andi Kleen) |
| ARM Top-Down | ARM Neoverse Telemetry Specification |
| Apple Silicon PMU | jiegec/apple-pmu; Bugsik blog; clf3 blog |
| BayesPerf | Banerjee et al., ASPLOS 2021 |
| ECM Model | Hofmann et al., arXiv 1509.03118 |
| Deconvolution | Delaigle & Hall, Annals of Statistics 2008 |
| Workload Frequency Scaling Law | Eyerman & Eeckhout, ACM Queue |
| osnoise | Linux kernel docs; Red Hat Research |
| BCI Latency Decomposition | Wilson et al., IEEE TBME 2010 |
| Variance Decomposition | Kalibera & Jones, ISMM 2013 |
| GUM Uncertainty Framework | JCGM 100:2008 |
