# CORTEX CLI Usage Guide

The CORTEX CLI provides a unified interface for building, running, and analyzing BCI kernel benchmarks.

## Quick Start

```bash
# Install dependencies
pip install -e .

# Run full automated pipeline
cortex pipeline

# View results (stored in named run directories)
cat results/run-*/analysis/SUMMARY.md
open results/run-*/analysis/latency_comparison.png
```

## Installation

```bash
# Install Python dependencies
pip install -e .
```

## Commands

### `cortex list`
List all available kernels with build status.

```bash
cortex list              # Table view
cortex list --verbose    # Detailed view
```

**Example output:**
```
Kernel               Version    DType      Status
----------------------------------------------------------------
bandpass_fir         v1         f32        ✓ Built
car                  v1         f32        [ ] No impl
goertzel             v1         f32        ✓ Built
notch_iir            v1         f32        ✓ Built

Summary: 3/4 implemented, 3/4 built
```

---

### `cortex build`
Build harness, kernel plugins, and tests.

```bash
cortex build                    # Build everything
cortex build --clean            # Clean before building
cortex build --kernels-only     # Build only kernel plugins
cortex build --verbose          # Show build output
cortex build --jobs 4           # Parallel build (4 jobs)
```

**What it builds:**
- Harness binary (`src/engine/harness/cortex`)
- All kernel plugins
- Unit tests

---

### `cortex validate`
Run kernel accuracy tests against Python oracles.

```bash
cortex validate --kernel notch_iir   # Test specific kernel
cortex validate --kernel goertzel --verbose  # With verbose output
```

**What it does:**
- Runs `tests/test_kernel_accuracy` for specified kernel
- Compares C implementation against SciPy/MNE reference
- Validates output within tolerance bounds (rtol=1e-5, atol=1e-6)

**Note**: Testing all kernels at once is not yet implemented. Validate kernels individually.

---

### `cortex run`
Execute benchmark experiments.

#### Run single kernel:
```bash
cortex run --kernel goertzel
cortex run --kernel notch_iir --duration 60 --repeats 5
```

#### Run all kernels (batch mode):
```bash
cortex run --all
cortex run --all --duration 125 --repeats 3 --warmup 5
```

#### Use custom config:
```bash
cortex run --config my_custom_config.yaml
```

**Options:**
- `--kernel <name>`: Run specific kernel
- `--all`: Run all available kernels
- `--config <path>`: Use custom YAML config
- `--run-name <name>`: Custom name for this run (default: auto-generated)
- `--duration <secs>`: Override benchmark duration
- `--repeats <n>`: Override number of repeats
- `--warmup <secs>`: Override warmup duration
- `--verbose`: Show harness output

**Output:**
- Run directory: `results/run-YYYY-MM-DD-NNN/` or `results/<custom-name>/`
- Kernel data: `results/<run-name>/kernel-data/<kernel>/`
  - Telemetry: `telemetry.{csv,ndjson}` (NDJSON format by default)
  - HTML report: `report.html`
- Analysis: `results/<run-name>/analysis/`

---

## Benchmark Duration Guidelines {#benchmark-duration-guidelines}

Selecting appropriate benchmark durations is critical for reliable latency statistics. Based on research in real-time system benchmarking and statistical requirements for percentile confidence:

### Statistical Requirements

Different percentiles require different minimum sample sizes:
- **P50 (Median)**: Reliable with ~100+ samples
- **P95**: Needs ~1,000+ samples for confidence
- **P99**: Needs ~10,000+ samples for confidence

With CORTEX's default configuration (2 windows/second):
- 100 samples = 50 seconds
- 1,000 samples = 500 seconds (~8 minutes)
- 10,000 samples = 5,000 seconds (~83 minutes)

### Duration Recommendations

| Duration | Windows/Repeat | Total Windows (3 repeats) | P50 | P95 | P99 | Use Case |
|----------|----------------|---------------------------|-----|-----|-----|----------|
| 10s      | ~20            | ~60                       | Good | Acceptable | Low | Quick tests, CI |
| 30s      | ~60            | ~180                      | Excellent | Good | Acceptable | Development |
| **60s**  | **~120**       | **~360**                  | **Excellent** | **Good** | **Acceptable** | **Recommended** |
| 120s     | ~240           | ~720                      | Excellent | Excellent | Good | Production |
| 300s+    | ~600+          | ~1,800+                   | Excellent | Excellent | Excellent | Research/Publication |

**Note**: Based on 2 Hz window rate (160 Hz sample rate, 80 sample hop, 64 channels).

### Examples

**Quick development test:**
```bash
cortex run --all --duration 10 --repeats 1 --warmup 5
# ~20 windows: Good for P50, limited P95/P99 confidence
```

**Standard benchmark (recommended):**
```bash
cortex run --all --duration 60 --repeats 3 --warmup 5
# ~360 windows: Reliable P50/P95, acceptable P99
```

**Publication-quality:**
```bash
cortex run --all --duration 300 --repeats 3 --warmup 5
# ~1,800 windows: Excellent for all percentiles, captures tail latencies
```

### Research References

Duration recommendations are based on:
- **MDPI Study (2021)**: Real-time performance measurements of Linux kernels conducted 3-hour tests with ~1 million samples for comprehensive latency analysis ([link](https://www.mdpi.com/2073-431X/10/5/64))
- **EVL Project Benchmarks**: Recommends extended measurement periods to capture rare latency events and worst-case behavior ([link](https://evlproject.org/core/benchmarks/))

---

### `cortex analyze`
Generate comparison plots and summary from benchmark results.

```bash
# Analyze most recent run (default)
cortex analyze

# Analyze specific run
cortex analyze --run-name run-2025-11-10-001

# Specify custom output directory and format
cortex analyze --run-name my-experiment --output custom_analysis --format pdf

# Generate specific plots only
cortex analyze --plots latency deadline
```

**Options:**
- `--run-name <name>`: Name of run to analyze (default: most recent run)
- `--output <dir>`: Output directory (default: `<run-dir>/analysis`)
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
# View most recent run
cat results/run-*/analysis/SUMMARY.md

# View specific run
cat results/run-2025-11-10-001/analysis/SUMMARY.md
```

---

### `cortex pipeline`
Run full end-to-end pipeline: build → validate → run → analyze.

```bash
# Full pipeline (auto-named)
cortex pipeline

# Custom run name
cortex pipeline --run-name production-benchmark

# Skip steps
cortex pipeline --skip-build           # Assume already built
cortex pipeline --skip-validate        # Skip validation

# Override parameters
cortex pipeline --duration 60 --repeats 5
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
  Run directory: results/run-YYYY-MM-DD-NNN/
  Kernel data: results/<run-name>/kernel-data/
  Analysis plots: results/<run-name>/analysis/
  Summary table: results/<run-name>/analysis/SUMMARY.md
```

---

### `cortex clean`
Clean build artifacts and results.

```bash
cortex clean               # Clean everything
cortex clean --build       # Clean only build artifacts
cortex clean --results     # Clean only results directory
```

**What gets cleaned:**
- Build artifacts (`.o`, `.dylib`, `.so` files)
- Results directory (`results/`)
- Analysis outputs (`results/analysis/`)

---

## Typical Workflows

### First-Time Setup
```bash
# 1. Install dependencies
pip install -e .

# 2. Build everything
cortex build

# 3. Validate kernels work
cortex validate --kernel notch_iir
cortex validate --kernel bandpass_fir
cortex validate --kernel goertzel

# 4. Run quick test with one kernel
cortex run --kernel goertzel --duration 10 --repeats 1
```

### Full Experiment Run
```bash
# One-command full pipeline (creates auto-named run)
cortex pipeline

# Or with custom name:
cortex pipeline --run-name baseline-measurements

# Or step-by-step:
cortex build
cortex validate --kernel notch_iir
cortex validate --kernel bandpass_fir
cortex validate --kernel goertzel
cortex run --all --duration 125 --repeats 3
cortex analyze  # Analyzes most recent run
```

### Iterative Development
```bash
# After modifying a kernel
cortex build --kernels-only
cortex validate --kernel my_kernel
cortex run --kernel my_kernel --duration 30
```

### Custom Analysis
```bash
# Run experiments with custom name and settings
cortex run --all --run-name high-load-test --duration 60 --repeats 10

# Generate only specific plots for that run
cortex analyze --run-name high-load-test --plots latency cdf --format pdf
```

---

## Understanding Results

### Directory Structure
Each run creates an isolated directory:
```
results/run-2025-11-10-001/
├── kernel-data/
│   ├── bandpass_fir/
│   │   ├── telemetry.ndjson
│   │   ├── telemetry.csv
│   │   └── report.html
│   └── goertzel/
│       └── ...
└── analysis/
    ├── SUMMARY.md
    └── *.png
```

### Telemetry Files
Each kernel produces (in `kernel-data/<kernel>/`):
- **NDJSON format**: `telemetry.ndjson` (default)
- **CSV format**: `telemetry.csv` (alternative format)
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
cortex list

# Ensure kernel is built
cortex build --kernels-only
```

### "Harness binary not found"
```bash
# Build harness
cortex build
```

### "No telemetry files found"
- Ensure you're analyzing the correct run directory
- Check that the run completed successfully
- Look for telemetry files: `results/<run-name>/kernel-data/*/telemetry.*`
- Use `cortex analyze` without arguments to analyze the most recent run

### Python import errors
```bash
# Install all dependencies
pip install -e .
```

### Build failures
```bash
# Clean and rebuild
cortex clean
cortex build --verbose  # See detailed error messages
```

---

## Advanced Usage

### N=2 Laptop Scenario
To run experiments on two identical laptops:

**Laptop 1:**
```bash
cortex run --all --run-name laptop1-baseline --duration 125 --repeats 3
# Copy results/laptop1-baseline/ to shared location
```

**Laptop 2:**
```bash
cortex run --all --run-name laptop2-baseline --duration 125 --repeats 3
# Copy results/laptop2-baseline/ to shared location
```

**Analysis machine:**
```bash
# Copy both run directories to local results/
cp -r shared/laptop1-baseline results/
cp -r shared/laptop2-baseline results/

# Analyze each separately
cortex analyze --run-name laptop1-baseline
cortex analyze --run-name laptop2-baseline

# Or combine kernel data for joint analysis (advanced)
mkdir results/combined-analysis
cp -r results/laptop1-baseline/kernel-data/* results/combined-analysis/
cp -r results/laptop2-baseline/kernel-data/* results/combined-analysis/
```

### Custom Configurations
Edit `primitives/configs/cortex.yaml` template or create new configs:

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
    spec_uri: "primitives/kernels/v1/my_kernel@f32"
    adapter_path: "primitives/adapters/v1/native/cortex_adapter_native"
```

Run with:
```bash
cortex run --config my_custom_config.yaml
```

---

## Getting Help

```bash
# General help
cortex --help

# Command-specific help
cortex build --help
cortex run --help
cortex analyze --help
```

**Documentation:**
- Main README: `README.md`
- Plugin interface: `docs/reference/plugin-interface.md`
- Configuration: `docs/reference/configuration.md`
- Telemetry: `docs/reference/telemetry.md`
- Roadmap: `docs/development/roadmap.md`
- Individual kernel specs: `primitives/kernels/v1/{name}@{dtype}/README.md`

**Issues:**
https://github.com/WestonVoglesonger/CORTEX/issues
