# Linux Governor Validation Study (December 2025)

## Purpose

This study validates the DVFS/Idle Paradox discovered on macOS by using Linux's direct CPU governor control. It provides empirical evidence that:

1. The "Idle Paradox" is a real DVFS phenomenon, not macOS-specific
2. Linux `performance` governor achieves frequency locking (3.21× improvement over powersave)
3. **The Schedutil Trap**: Dynamic scaling is *worse* than fixed minimum frequency for real-time workloads
4. **Platform Difference**: stress-ng workaround fails on Linux (per-CPU scaling) but works on macOS (cluster-wide scaling)

## Key Results

| Governor | Latency (µs) | vs Performance | Notes |
|----------|--------------|----------------|-------|
| Performance | 167.6 | 1.00× (baseline) | Optimal - max frequency locked |
| Powersave | 537.7 | 3.21× slower | DVFS penalty confirmed |
| Schedutil | 762.8 | 4.55× slower | **Worse than powersave!** |
| Schedutil+stress | 763.8 | 4.56× slower | stress-ng has no effect |

### Cross-Platform Comparison

| Platform | Low-Frequency | High-Frequency | Ratio |
|----------|---------------|----------------|-------|
| macOS | 284.3 µs (idle) | 123.1 µs (medium) | 2.31× |
| Linux | 537.7 µs (powersave) | 167.6 µs (performance) | 3.21× |

**Note**: These latency differences (167-538 µs range) are **167-538× larger** than the harness overhead (1 µs, measured empirically via noop kernel in `experiments/noop-overhead-2025-12-05/`), confirming that DVFS effects dominate measurement methodology.

## Major Discoveries

### 1. The Schedutil Trap
Dynamic frequency scaling (schedutil) produces **worse** latency than even fixed minimum frequency (powersave):
- Schedutil average frequency: ~1300 MHz (2× higher than powersave's 600 MHz)
- Yet schedutil latency is 1.42× *worse* than powersave
- **Root cause**: Frequency transition overhead during short compute bursts exceeds benefits

### 2. Per-CPU vs Cluster-Wide Scaling
stress-ng background load has **no effect** on Linux (1.00×) despite working on macOS (2.31×):

| Platform | Scaling Domain | stress-ng Effect |
|----------|----------------|------------------|
| Linux | Per-CPU | Fails (only boosts loaded CPUs) |
| macOS | Cluster-wide | Works (boosts entire cluster) |

**Why**: Benchmark pinned to CPU 0, stress-ng runs on CPUs 1-7. Linux schedutil only considers CPU 0's load.

## Quick Start

### Prerequisites

```bash
# Build CORTEX
cd /path/to/CORTEX
make all

# Verify dataset exists
ls primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32

# Check available governors
cat /sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors
```

### Running the Experiment

```bash
# Run full automated experiment (requires sudo for governor control)
cd experiments/linux-governor-validation-2025-12-05
sudo ./scripts/run-experiment.sh

# Run additional schedutil+stress-ng test
sudo ./scripts/run-boosted-schedutil.sh

# Or run with options
sudo ./scripts/run-experiment.sh --skip-schedutil    # Skip schedutil run
sudo ./scripts/run-experiment.sh --analysis-only     # Only run analysis
sudo ./scripts/run-experiment.sh --dry-run           # Preview commands
```

## File Structure

```
experiments/linux-governor-validation-2025-12-05/
├── README.md                         # This file
├── cortex-config.yaml                # CORTEX config (idle, no stress-ng)
├── cortex-config-boosted.yaml        # CORTEX config (with stress-ng)
├── scripts/
│   ├── run-experiment.sh             # Main automation script
│   ├── run-boosted-schedutil.sh      # Additional stress-ng test
│   ├── set-governor.sh               # Governor manipulation utility
│   ├── record-frequency.sh           # Frequency logging utility
│   ├── generate_governor_comparison.py
│   └── compare_to_macos.py
├── run-001-powersave/                # Powersave governor (600 MHz)
│   ├── kernel-data/{kernel}/telemetry.ndjson
│   ├── frequency-log.csv
│   └── analysis/
├── run-002-performance/              # Performance governor (2064/3204 MHz)
├── run-003-schedutil/                # Schedutil (dynamic, ~1300 MHz avg)
├── run-004-schedutil-boosted/        # Schedutil + stress-ng (no effect)
├── figures/
│   ├── governor_comparison.png       # 4-condition bar chart
│   ├── per_kernel_comparison.png     # Per-kernel breakdown
│   └── macos_linux_comparison.png    # Cross-platform comparison
└── technical-report/
    └── COMPREHENSIVE_VALIDATION_REPORT.md
```

## Benchmark Parameters

Identical to macOS validation experiment for direct comparison:

| Parameter | Value |
|-----------|-------|
| Duration | 120 seconds per kernel |
| Repeats | 5 per kernel |
| Warmup | 10 seconds |
| Dataset | S001R03.float32 (64ch @ 160Hz) |
| Kernels | car, notch_iir, goertzel, bandpass_fir |
| Scheduler | FIFO (real-time) |
| Priority | 90 |
| CPU Affinity | Core 0 |
| Deadline | 500 ms |

## System Configuration

**Hardware**: Apple M1 MacBook Air (8GB RAM)
**Platform**: Fedora Asahi Linux 42
**Kernel**: 6.14.2-401.asahi.fc42.aarch64+16k
**Available Governors**: conservative, ondemand, userspace, powersave, performance, schedutil

**CPU Policies**:
- policy0 (CPUs 0-3): Efficiency cores, 600-2064 MHz
- policy4 (CPUs 4-7): Performance cores, 600-3204 MHz

## Practical Recommendations

### For Linux Real-Time Systems
```bash
# Set performance governor before running real-time workloads
echo performance | sudo tee /sys/devices/system/cpu/cpufreq/policy*/scaling_governor

# Verify
cat /sys/devices/system/cpu/cpufreq/policy*/scaling_governor
```

### For macOS Real-Time Systems
```bash
# Use stress-ng background load (cluster-wide scaling makes it effective)
stress-ng --cpu 4 --cpu-load 50 &
```

## Per-Kernel Improvement

| Kernel | Worst (schedutil) | Best (performance) | Improvement |
|--------|-------------------|--------------------| ------------|
| car | 96.95 µs | 14.12 µs | 6.9× |
| notch_iir | 199.12 µs | 37.96 µs | 5.2× |
| goertzel | 1709.25 µs | 496.27 µs | 3.4× |
| bandpass_fir | 10262.70 µs | 2968.44 µs | 3.5× |

## References

- macOS DVFS Validation: `experiments/dvfs-validation-2025-11-15/`
- Harness Overhead Measurement: `experiments/noop-overhead-2025-12-05/`
  - Empirically validates that harness overhead (1 µs) is negligible compared to DVFS effects (3.21× on Linux)
  - Provides measurement methodology validation for all 8 CORTEX kernels
- Technical Report: `technical-report/COMPREHENSIVE_VALIDATION_REPORT.md`
- Architecture Decision Record: `docs/architecture/adr/adr-002-benchmark-reproducibility-macos.md`

## Authors

- Weston Voglesonger
- With assistance from Claude Code (Anthropic)

## Last Updated

2025-12-06: Experiment complete with all 4 conditions analyzed
