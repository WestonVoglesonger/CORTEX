# CORTEX CLI Usage Guide

The CORTEX CLI provides a unified interface for building, running, and analyzing BCI kernel benchmarks.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run full automated pipeline
./cortex pipeline

# View results
cat results/analysis/SUMMARY.md
open results/analysis/latency_comparison.png
```

## Installation

```bash
# Ensure cortex is executable
chmod +x cortex

# Install Python dependencies
pip install -r requirements.txt
```

## Commands

### `cortex list`
List all available kernels with build status.

```bash
./cortex list              # Table view
./cortex list --verbose    # Detailed view
```

**Example output:**
```
Kernel               Version    DType      Status
----------------------------------------------------------------
car                  v1         f32        ⚠ No impl
fir_bandpass         v1         f32        ✓ Built
goertzel             v1         f32        ✓ Built
notch_iir            v1         f32        ✓ Built
goertzel             v2         f32        ✓ Built

Summary: 4/5 implemented, 4/5 built
```

---

### `cortex build`
Build harness, kernel plugins, and tests.

```bash
./cortex build                    # Build everything
./cortex build --clean            # Clean before building
./cortex build --kernels-only     # Build only kernel plugins
./cortex build --verbose          # Show build output
./cortex build --jobs 4           # Parallel build (4 jobs)
```

**What it builds:**
- Harness binary (`src/harness/cortex`)
- All kernel plugins (v1 and v2)
- Unit tests

---

### `cortex validate`
Run kernel accuracy tests against Python oracles.

```bash
./cortex validate                    # Test all kernels
./cortex validate --kernel goertzel  # Test specific kernel
./cortex validate --verbose          # Show verbose output
```

**What it does:**
- Runs `tests/test_kernel_accuracy`
- Compares C implementations against SciPy/MNE references
- Validates output within tolerance bounds

---

### `cortex run`
Execute benchmark experiments.

#### Run single kernel:
```bash
./cortex run --kernel goertzel
./cortex run --kernel notch_iir --duration 60 --repeats 5
```

#### Run all kernels (batch mode):
```bash
./cortex run --all
./cortex run --all --duration 125 --repeats 3 --warmup 5
```

#### Use custom config:
```bash
./cortex run --config my_custom_config.yaml
```

**Options:**
- `--kernel <name>`: Run specific kernel
- `--all`: Run all available kernels
- `--config <path>`: Use custom YAML config
- `--duration <secs>`: Override benchmark duration
- `--repeats <n>`: Override number of repeats
- `--warmup <secs>`: Override warmup duration
- `--verbose`: Show harness output

**Output:**
- Telemetry CSVs: `results/<run_id>/`
- HTML reports: `results/<run_id>/report.html`
- Batch runs: `results/batch_<timestamp>/`

---

### `cortex analyze`
Generate comparison plots and summary from benchmark results.

```bash
# Analyze batch results
./cortex analyze results/batch_1234567890

# Specify output directory and format
./cortex analyze results/batch_123 --output my_analysis --format pdf

# Generate specific plots only
./cortex analyze results/batch_123 --plots latency deadline
```

**Options:**
- `results_dir`: Path to results directory (required)
- `--output <dir>`: Output directory (default: `results/analysis`)
- `--format <png|pdf|svg>`: Plot format (default: `png`)
- `--plots <list>`: Plots to generate: `latency`, `deadline`, `throughput`, `cdf`, `all` (default: `all`)

**Generated files:**
- `latency_comparison.png`: P50/P95/P99 latency bar chart
- `deadline_miss_rate.png`: Deadline miss rate comparison
- `throughput_comparison.png`: Throughput comparison
- `latency_cdf_overlay.png`: CDF curves for all kernels
- `SUMMARY.md`: Markdown summary table

**View summary:**
```bash
cat results/analysis/SUMMARY.md
```

---

### `cortex pipeline`
Run full end-to-end pipeline: build → validate → run → analyze.

```bash
# Full pipeline
./cortex pipeline

# Skip steps
./cortex pipeline --skip-build           # Assume already built
./cortex pipeline --skip-validate        # Skip validation

# Override parameters
./cortex pipeline --duration 60 --repeats 5
```

**Pipeline steps:**
1. **Build** - Compile harness and all kernels
2. **Validate** - Run accuracy tests
3. **Run** - Execute all kernel benchmarks
4. **Analyze** - Generate comparison plots

**Total time:** ~15-30 minutes (depending on duration/repeats)

**Output:**
```
Results:
  Telemetry data: results/batch_<timestamp>/
  Analysis plots: results/analysis/
  Summary table: results/analysis/SUMMARY.md
```

---

### `cortex clean`
Clean build artifacts and results.

```bash
./cortex clean               # Clean everything
./cortex clean --build       # Clean only build artifacts
./cortex clean --results     # Clean only results directory
```

**What gets cleaned:**
- Build artifacts (`.o`, `.dylib`, `.so` files)
- Generated configs (`configs/generated/`)
- Results directory (`results/`)
- Analysis outputs (`results/analysis/`)

---

## Typical Workflows

### First-Time Setup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Build everything
./cortex build

# 3. Validate kernels work
./cortex validate

# 4. Run quick test with one kernel
./cortex run --kernel goertzel --duration 10 --repeats 1
```

### Full Experiment Run
```bash
# One-command full pipeline
./cortex pipeline

# Or step-by-step:
./cortex build
./cortex validate
./cortex run --all --duration 125 --repeats 3
./cortex analyze results/batch_<timestamp>
```

### Iterative Development
```bash
# After modifying a kernel
./cortex build --kernels-only
./cortex validate --kernel my_kernel
./cortex run --kernel my_kernel --duration 30
```

### Custom Analysis
```bash
# Run experiments with custom settings
./cortex run --all --duration 60 --repeats 10

# Generate only specific plots
./cortex analyze results/batch_123 --plots latency cdf --format pdf
```

---

## Understanding Results

### Telemetry Files
Each kernel run produces:
- **CSV format**: `<kernel>_telemetry.csv`
- **NDJSON format**: `<kernel>_telemetry.ndjson` (if configured)
- **HTML report**: `report.html` (auto-generated)

**CSV columns:**
```
run_id, plugin, window_index, release_ts_ns, deadline_ts_ns,
start_ts_ns, end_ts_ns, deadline_missed, W, H, C, Fs, warmup, repeat
```

### Analysis Outputs

**SUMMARY.md table:**
| Kernel | Windows | P50 (µs) | P95 (µs) | P99 (µs) | Jitter | Deadline Misses | Miss Rate (%) |
|--------|---------|----------|----------|----------|--------|-----------------|---------------|
| goertzel | 1500 | 240.5 | 285.2 | 310.8 | 44.7 | 0 | 0.00 |
| ... | ... | ... | ... | ... | ... | ... | ... |

**Metrics explained:**
- **P50/P95/P99**: 50th/95th/99th percentile latencies
- **Jitter**: P95 - P50 (timing variance)
- **Deadline Misses**: Count of windows exceeding 500ms deadline
- **Miss Rate**: Percentage of windows that missed deadline

---

## Troubleshooting

### "Kernel not found"
```bash
# Check available kernels
./cortex list

# Ensure kernel is built
./cortex build --kernels-only
```

### "Harness binary not found"
```bash
# Build harness
./cortex build
```

### "No telemetry files found"
- Ensure you're analyzing the correct directory
- Check that the run completed successfully
- Look for CSV files in subdirectories: `results/batch_*/` \_run`/`

### Python import errors
```bash
# Install all dependencies
pip install -r requirements.txt
```

### Build failures
```bash
# Clean and rebuild
./cortex clean
./cortex build --verbose  # See detailed error messages
```

---

## Advanced Usage

### N=2 Laptop Scenario
To run experiments on two identical laptops:

**Laptop 1:**
```bash
./cortex run --all --duration 125 --repeats 3
# Copy results to shared location
```

**Laptop 2:**
```bash
./cortex run --all --duration 125 --repeats 3
# Copy results to shared location
```

**Analysis machine:**
```bash
# Combine results
mkdir combined_results
cp -r laptop1_results/* combined_results/
cp -r laptop2_results/* combined_results/
./cortex analyze combined_results
```

### Custom Configurations
Edit `configs/cortex.yaml` template or create new configs:

```yaml
dataset:
  path: "datasets/my_dataset.float32"
  sample_rate_hz: 250  # Custom sample rate

benchmark:
  parameters:
    duration_seconds: 300
    repeats: 10

plugins:
  - name: my_custom_kernel
    spec_uri: "kernels/v1/my_kernel@f32"
```

Run with:
```bash
./cortex run --config my_custom_config.yaml
```

---

## Getting Help

```bash
# General help
./cortex --help

# Command-specific help
./cortex build --help
./cortex run --help
./cortex analyze --help
```

**Documentation:**
- Main README: `README.md`
- Kernel specs: `docs/KERNELS.md`
- Plugin interface: `docs/PLUGIN_INTERFACE.md`
- Configuration: `docs/RUN_CONFIG.md`
- Roadmap: `docs/ROADMAP.md`

**Issues:**
https://github.com/WestonVoglesonger/CORTEX/issues
