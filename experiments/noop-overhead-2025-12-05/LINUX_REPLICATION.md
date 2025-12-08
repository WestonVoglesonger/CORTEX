# Running noop-overhead Experiment on Linux

This document provides instructions for replicating the noop-overhead experiment on Linux to validate cross-platform consistency of harness overhead measurements.

---

## Purpose

The macOS noop-overhead study measured harness overhead at **1 µs minimum**. Running the same experiment on Linux will:

1. **Validate platform independence**: Confirm harness overhead is similar on Linux (expected: 1-2 µs)
2. **Cross-platform comparison**: Document any platform-specific differences
3. **Complete the experimental suite**: Provide Linux baseline for all three experiments

---

## Prerequisites

### System Requirements

- **Platform**: Linux (x86_64 or arm64)
- **Kernel**: Recent kernel with cpufreq support
- **Governors**: powersave and performance available
- **Tools**: stress-ng (for medium profile)

### CORTEX Setup

```bash
# Clone and build CORTEX
git clone https://github.com/WestonVoglesonger/CORTEX.git
cd CORTEX
make all

# Verify noop kernel built
ls primitives/kernels/v1/noop@f32/libnoop.so

# Verify dataset exists
ls primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32

# Install stress-ng
sudo apt install stress-ng   # Debian/Ubuntu
sudo dnf install stress-ng   # Fedora
sudo pacman -S stress-ng     # Arch
```

---

## Running the Experiment

### Option 1: Automated (Recommended)

The automation scripts should work on Linux with minimal modifications:

```bash
cd experiments/noop-overhead-2025-12-05

# Run complete experiment
./scripts/run-experiment.sh

# Expected runtime: ~21 minutes
# Expected output: run-001-idle/, run-002-medium/, figures/
```

**Platform-specific adjustments** (if needed):

The script should automatically detect Linux and use `.so` instead of `.dylib`. If you encounter issues:

1. Check plugin extension in `run-experiment.sh` (should detect `$LIBEXT`)
2. Verify `cortex` CLI works: `cortex --version`

### Option 2: Manual Execution

#### Step 1: Set Governor to Performance

```bash
# Check available governors
cat /sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors

# Set performance governor (requires sudo)
echo performance | sudo tee /sys/devices/system/cpu/cpufreq/policy*/scaling_governor

# Verify
cat /sys/devices/system/cpu/cpufreq/policy*/scaling_governor
# Should show: performance (all cores)
```

#### Step 2: Run Idle Profile

```bash
cd /path/to/CORTEX

# Run idle profile (10 minutes)
cortex run --config experiments/noop-overhead-2025-12-05/config-idle.yaml

# Find latest results
RESULTS_DIR=$(ls -td results/run-* | head -1)
echo "Results: $RESULTS_DIR"

# Copy to experiment directory
cp -r "$RESULTS_DIR" experiments/noop-overhead-2025-12-05/run-001-idle-linux/
echo "$RESULTS_DIR" > experiments/noop-overhead-2025-12-05/run-001-idle-linux/cortex-results-path.txt
```

#### Step 3: Run Medium Profile

```bash
# Start stress-ng in background
stress-ng --cpu 4 --cpu-load 50 &
STRESS_PID=$!

# Run medium profile (10 minutes)
cortex run --config experiments/noop-overhead-2025-12-05/config-medium.yaml

# Stop stress-ng
kill $STRESS_PID

# Copy results
RESULTS_DIR=$(ls -td results/run-* | head -1)
cp -r "$RESULTS_DIR" experiments/noop-overhead-2025-12-05/run-002-medium-linux/
echo "$RESULTS_DIR" > experiments/noop-overhead-2025-12-05/run-002-medium-linux/cortex-results-path.txt
```

#### Step 4: Generate Figures and Analysis

```bash
cd experiments/noop-overhead-2025-12-05

# Generate comparison figure
python3 scripts/generate_noop_comparison.py

# Run statistical analysis
python3 scripts/calculate_overhead_stats.py
```

---

## Expected Results

### Prediction: Similar to macOS

Based on the harness implementation (platform-independent C code), we expect:

| Metric | macOS | Linux (Expected) | Notes |
|--------|-------|------------------|-------|
| **Minimum** | 1 µs | **1-2 µs** | Slight variation due to syscall overhead |
| **Idle median** | 5 µs | **2-10 µs** | Depends on powersave frequency |
| **Medium median** | 4 µs | **2-5 µs** | Depends on stress-ng effectiveness |

**Key validation**: If Linux shows similar minimum (1-2 µs), this confirms harness overhead is platform-independent.

### Platform Differences to Document

1. **Governor control**: Linux has explicit performance governor (better control than macOS stress-ng)
2. **Per-CPU scaling**: stress-ng may have NO effect on Linux (see `linux-governor-validation` findings)
3. **syscall overhead**: `clock_gettime()` via VDSO may differ slightly
4. **Scheduling**: Linux scheduler behavior under load differs from macOS

---

## Analysis Script Modifications

If running on Linux, you may need to update paths in analysis scripts:

### `generate_noop_comparison.py`

```python
# Update paths to use Linux directories
idle_file = experiment_dir / 'run-001-idle-linux' / 'kernel-data' / 'noop' / 'telemetry.ndjson'
medium_file = experiment_dir / 'run-002-medium-linux' / 'kernel-data' / 'noop' / 'telemetry.ndjson'
```

### `calculate_overhead_stats.py`

```python
# Update paths
idle_file = experiment_dir / 'run-001-idle-linux' / 'kernel-data' / 'noop' / 'telemetry.ndjson'
medium_file = experiment_dir / 'run-002-medium-linux' / 'kernel-data' / 'noop' / 'telemetry.ndjson'
```

Or create symlinks:
```bash
ln -s run-001-idle-linux run-001-idle
ln -s run-002-medium-linux run-002-medium
```

---

## Documentation Updates After Linux Run

After completing the Linux replication, update:

### 1. `experiments/noop-overhead-2025-12-05/README.md`

Add cross-platform comparison table:

```markdown
### Cross-Platform Comparison

| Platform | Idle Median | Medium Median | Minimum | Notes |
|----------|-------------|---------------|---------|-------|
| macOS | 5 µs | 4 µs | 1 µs | Cluster-wide DVFS |
| Linux | X µs | Y µs | Z µs | Per-CPU DVFS |

**Key finding**: Minimum harness overhead is consistent at ~1 µs across platforms,
validating platform independence of measurement apparatus.
```

### 2. `technical-report/HARNESS_OVERHEAD_ANALYSIS.md`

Add Linux results to Section 9 (Future Work) or create new section:

```markdown
## 10. Linux Cross-Platform Validation

**Platform**: Linux x86_64/arm64
**Sample size**: n=XXXX

**Results**:
- Minimum: Z µs (vs 1 µs macOS)
- Idle median: X µs (vs 5 µs macOS)
- Medium median: Y µs (vs 4 µs macOS)

**Conclusion**: Harness overhead is consistent at ~1 µs across platforms ✅
```

### 3. `linux-governor-validation-2025-12-05/README.md`

Update the reference to mention Linux noop results:

```markdown
- Harness Overhead Measurement: `experiments/noop-overhead-2025-12-05/`
  - macOS: 1 µs harness overhead (n=2399)
  - Linux: Z µs harness overhead (n=XXXX)
  - Confirms platform independence of measurement apparatus
```

---

## Troubleshooting

### `cortex: command not found`

```bash
# Install CORTEX CLI
cd /path/to/CORTEX
pip install -e .
```

### `noop kernel not found`

```bash
cd primitives/kernels/v1/noop@f32
make clean && make
```

### `stress-ng not available`

```bash
# Install via package manager
sudo apt install stress-ng   # Debian/Ubuntu
sudo dnf install stress-ng   # Fedora
```

### Governor control requires sudo

```bash
# Either run cortex with sudo
sudo cortex run --config ...

# Or set governor once before running
echo performance | sudo tee /sys/devices/system/cpu/cpufreq/policy*/scaling_governor
cortex run --config ...
```

### Different results than macOS

This is expected! Document differences:
- **CPU architecture**: x86_64 vs arm64
- **DVFS implementation**: Per-CPU vs cluster-wide
- **Governor behavior**: performance vs stress-ng workaround
- **Kernel scheduler**: Linux CFS vs macOS XNU

---

## Contributing Results

If you run this experiment on Linux, please consider contributing results:

1. **Create PR** with Linux results in `run-001-idle-linux/` and `run-002-medium-linux/`
2. **Update README.md** with cross-platform comparison table
3. **Document platform**: CPU model, Linux distribution, kernel version
4. **Include analysis**: Run `calculate_overhead_stats.py` and include output

This will help validate CORTEX's measurement methodology across platforms!

---

## Questions?

If you run into issues or have questions about Linux replication:
- Open an issue: https://github.com/WestonVoglesonger/CORTEX/issues
- Reference this document: `experiments/noop-overhead-2025-12-05/LINUX_REPLICATION.md`

---

## Authors

- Weston Voglesonger (@WestonVoglesonger)
- With assistance from Claude Code (Anthropic)

**Last Updated**: December 6, 2025
