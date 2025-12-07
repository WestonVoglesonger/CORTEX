# noop-overhead Experiment Automation Scripts

This directory contains automation scripts for the **noop-overhead-2025-12-05** experiment, which measures CORTEX harness dispatch overhead using an identity (no-op) kernel.

---

## Quick Start

To reproduce the entire experiment from scratch:

```bash
cd experiments/noop-overhead-2025-12-05
./scripts/run-experiment.sh
```

**Runtime**: ~21 minutes (10 min idle + 10 min medium + analysis)

**Outputs**:
- `run-001-idle/` - Idle profile results
- `run-002-medium/` - Medium load profile results
- `figures/` - Publication-quality visualizations

---

## Scripts Overview

### **run-experiment.sh**
Main orchestration script that runs the complete experiment pipeline.

**What it does:**
1. Backs up old data (`noop-idle/` → `noop-idle.old/`)
2. Runs idle profile (`cortex pipeline --config config-idle.yaml`)
3. Copies results to `run-001-idle/`
4. Runs medium profile (`cortex pipeline --config config-medium.yaml`)
5. Copies results to `run-002-medium/`
6. Generates all figures

**Usage:**
```bash
./scripts/run-experiment.sh
```

**Duration**: ~21 minutes
**Requirements**: CORTEX installed, noop kernel built

---

### **generate_noop_comparison.py**
Creates publication-quality bar chart comparing idle vs medium profiles.

**What it does:**
- Loads telemetry from both run directories
- Computes min, median, P95 for each profile
- Generates side-by-side bar chart with annotations
- Outputs PNG and PDF versions

**Usage:**
```bash
python3 scripts/generate_noop_comparison.py
```

**Outputs:**
- `figures/noop_idle_medium_comparison.png`
- `figures/noop_idle_medium_comparison.pdf`

**Requirements**: matplotlib, numpy, pandas (standard CORTEX analysis dependencies)

---

### **calculate_overhead_stats.py**
Performs statistical analysis and SNR calculations.

**What it does:**
- Computes percentiles for both profiles
- Welch's t-test for idle vs medium significance
- Calculates SNR for all CORTEX kernels using 1µs overhead
- Outputs formatted tables to console

**Usage:**
```bash
python3 scripts/calculate_overhead_stats.py
```

**Output**: Console tables with:
- Percentile statistics (min, P50, P95, P99, max)
- Statistical significance (p-value, effect size)
- SNR calculations for car, notch_iir, goertzel, bandpass_fir

---

### **create_all_figures.sh**
Wrapper script to generate all figures.

**What it does:**
- Creates `figures/` directory if needed
- Runs `generate_noop_comparison.py`
- Runs any other figure generation scripts

**Usage:**
```bash
./scripts/create_all_figures.sh
```

---

## Workflow Details

### **Data Flow**

```
cortex pipeline (config-idle.yaml)
   └─> results/run-<timestamp>/
       ├── kernel-data/noop/telemetry.ndjson
       └── analysis/
           ├── SUMMARY.md
           └── *.png
   └─> Copied to run-001-idle/

cortex pipeline (config-medium.yaml)
   └─> results/run-<timestamp>/
       └─> Copied to run-002-medium/

Python analysis scripts
   └─> Read run-001-idle/ and run-002-medium/
   └─> Generate figures/
```

### **Directory Structure Created**

```
experiments/noop-overhead-2025-12-05/
├── run-001-idle/
│   ├── kernel-data/noop/telemetry.ndjson    # Raw telemetry
│   ├── analysis/SUMMARY.md                   # CORTEX analysis
│   ├── analysis/*.png                        # CORTEX plots
│   └── cortex-results-path.txt               # Link to original
├── run-002-medium/
│   └── (same structure)
└── figures/
    ├── noop_idle_medium_comparison.png       # Main figure
    └── noop_idle_medium_comparison.pdf       # Paper version
```

---

## Manual Workflow

If you need to run steps individually:

### **1. Run idle profile**
```bash
cd /Users/westonvoglesonger/Projects/CORTEX
cortex pipeline --config experiments/noop-overhead-2025-12-05/config-idle.yaml
```

### **2. Find and copy results**
```bash
# Find latest results directory
RESULTS_DIR=$(ls -td results/run-* | head -1)
echo $RESULTS_DIR

# Copy to experiment directory
cp -r "$RESULTS_DIR" experiments/noop-overhead-2025-12-05/run-001-idle/
echo "$RESULTS_DIR" > experiments/noop-overhead-2025-12-05/run-001-idle/cortex-results-path.txt
```

### **3. Repeat for medium profile**
```bash
cortex pipeline --config experiments/noop-overhead-2025-12-05/config-medium.yaml
RESULTS_DIR=$(ls -td results/run-* | head -1)
cp -r "$RESULTS_DIR" experiments/noop-overhead-2025-12-05/run-002-medium/
echo "$RESULTS_DIR" > experiments/noop-overhead-2025-12-05/run-002-medium/cortex-results-path.txt
```

### **4. Generate figures**
```bash
cd experiments/noop-overhead-2025-12-05
./scripts/create_all_figures.sh
```

---

## Expected Results

**Idle Profile (run-001-idle):**
- Minimum: ~1 µs (true harness overhead)
- Median: ~3 µs (DVFS penalty visible)
- P95: ~5 µs
- Sample count: ~1200

**Medium Profile (run-002-medium):**
- Minimum: ~1 µs (same as idle - confirms harness floor)
- Median: ~2 µs (CPU at high frequency)
- P95: ~8 µs (stress-ng jitter)
- Sample count: ~1200

**Key Finding:** Minimum is identical across profiles (1 µs), proving it represents true harness overhead independent of environmental factors.

---

## Troubleshooting

**"cortex: command not found"**
- Ensure CORTEX is installed: `pip install -e .`
- Ensure you're in CORTEX root when running cortex commands

**"noop kernel not found"**
- Build noop kernel: `cd primitives/kernels/v1/noop@f32 && make`

**"figures/ directory empty"**
- Check Python dependencies: `pip install matplotlib numpy pandas`
- Run figure generation manually: `python3 scripts/generate_noop_comparison.py`

**"Results differ from original"**
- Normal - system state varies between runs
- Original results preserved in `noop-idle.old/` and `noop-medium.old/`
- Expect ±20% variation in median/P95, minimum should be stable

---

## Dependencies

**Required:**
- CORTEX CLI installed (`pip install -e .`)
- noop@f32 kernel built (`make` in primitives/kernels/v1/noop@f32/)
- Python 3.8+
- stress-ng (for medium load profile): `brew install stress-ng` (macOS)

**Python packages:**
- matplotlib (figure generation)
- numpy (statistics)
- pandas (data loading)
- scipy (statistical tests)

Install Python deps:
```bash
pip install matplotlib numpy pandas scipy
```

---

## Files in This Directory

```
scripts/
├── README.md                       # This file
├── run-experiment.sh               # Main orchestration (executable)
├── generate_noop_comparison.py     # Figure generation
├── calculate_overhead_stats.py     # Statistical analysis
└── create_all_figures.sh           # Figure generation wrapper (executable)
```

---

## Authors

- Weston Voglesonger (@WestonVoglesonger)
- With assistance from Claude Code (Anthropic)

**Last Updated**: December 6, 2025 - Created automation infrastructure
