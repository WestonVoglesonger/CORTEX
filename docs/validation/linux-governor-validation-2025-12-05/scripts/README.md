# Scripts Documentation

This directory contains automation and analysis scripts for the Linux Governor Validation experiment.

## Shell Scripts

### run-experiment.sh
**Main automation script for the full experiment.**

```bash
sudo ./run-experiment.sh [OPTIONS]
```

**Options:**
- `--skip-powersave` - Skip the powersave governor run
- `--skip-performance` - Skip the performance governor run
- `--skip-schedutil` - Skip the schedutil governor run
- `--analysis-only` - Only run analysis (skip benchmarks)
- `--dry-run` - Print commands without executing
- `--help` - Show help message

**What it does:**
1. Saves current governor for restoration
2. For each governor (powersave, performance, schedutil):
   - Sets governor on all CPU policies
   - Waits for stabilization
   - Starts frequency logging in background
   - Runs CORTEX benchmark
   - Copies results to experiment directory
3. Restores original governor
4. Runs cross-run analysis scripts

**Requirements:**
- Root access (for governor control)
- CORTEX built (`make all`)
- Dataset available

---

### run-boosted-schedutil.sh
**Additional test: schedutil with stress-ng background load.**

```bash
sudo ./run-boosted-schedutil.sh
```

**Purpose:** Tests whether stress-ng background load can boost schedutil performance (like on macOS).

**Finding:** stress-ng has NO effect on Linux due to per-CPU frequency scaling (unlike macOS cluster-wide scaling).

**What it does:**
1. Sets governor to schedutil
2. Starts frequency logging
3. Runs CORTEX with stress-ng load profile (4 CPUs @ 50%)
4. Saves results to run-004-schedutil-boosted/

---

### set-governor.sh
**Quick utility for manual governor switching.**

```bash
sudo ./set-governor.sh <governor>
sudo ./set-governor.sh             # Show current status
```

**Available governors:** conservative, ondemand, userspace, powersave, performance, schedutil

---

### record-frequency.sh
**Standalone frequency recording utility.**

```bash
./record-frequency.sh <output-file> [duration-seconds]
./record-frequency.sh freq.csv 120    # Record for 2 minutes
./record-frequency.sh freq.csv        # Record until Ctrl+C
```

**Output format (CSV):**
```
timestamp_ns,policy0_freq_khz,policy4_freq_khz,governor
```

## Python Analysis Scripts

### calculate_statistical_significance.py
**Statistical analysis comparing governor conditions.**

```bash
python3 calculate_statistical_significance.py
```

**Method:** Welch's t-test on log-transformed latencies

**Output:**
- t-statistics and p-values for each kernel
- Significance codes (*** p<0.001, ** p<0.01, * p<0.05)
- Aggregate comparison using geometric mean

---

### generate_governor_comparison.py
**Generate primary comparison figure.**

```bash
python3 generate_governor_comparison.py
```

**Output:**
- `../figures/governor_comparison.png` - Bar chart (300 DPI)
- `../figures/governor_comparison.pdf` - Publication-quality vector
- `../figures/per_kernel_comparison.png` - Per-kernel breakdown

---

### compare_to_macos.py
**Cross-platform comparison with macOS results.**

```bash
python3 compare_to_macos.py
```

**Output:**
- `../figures/macos_linux_comparison.png` - Side-by-side comparison
- `../figures/macos_linux_comparison.pdf` - Publication-quality version
- Console output with equivalence analysis

**macOS reference data (hardcoded from dvfs-validation-2025-11-15):**
- Idle: 284.3 us
- Medium: 123.1 us
- Heavy: 183.3 us

## Dependencies

**Shell scripts:**
- bash (with errexit, pipefail)
- Standard Linux utilities (cat, echo, date, sleep)
- sudo access for governor control

**Python scripts:**
- Python 3.8+
- numpy
- scipy (for statistical tests)
- matplotlib

Install Python dependencies:
```bash
pip install numpy scipy matplotlib
```

## Usage Examples

### Full Experiment Run
```bash
sudo ./run-experiment.sh
```

### Skip Schedutil (Two-Way Comparison Only)
```bash
sudo ./run-experiment.sh --skip-schedutil
```

### Re-run Analysis Only (After Data Collection)
```bash
./run-experiment.sh --analysis-only
# or manually:
python3 calculate_statistical_significance.py
python3 generate_governor_comparison.py
python3 compare_to_macos.py
```

### Manual Governor Testing
```bash
# Check current status
sudo ./set-governor.sh

# Set to performance
sudo ./set-governor.sh performance

# Run frequency logger in background
./record-frequency.sh freq.csv 120 &

# Run benchmark manually
cortex run --config ../cortex-config.yaml

# Stop logger
pkill -f record-frequency
```
