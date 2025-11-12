# Quick Start Guide

Get CORTEX up and running in 5 minutes.

## Prerequisites

- **macOS**: Xcode Command Line Tools (`xcode-select --install`)
- **Linux**: GCC/Clang, make, pthread, libdl
- **Python**: 3.8+ with pip

## 1. Clone and Install Dependencies

```bash
# Clone repository
git clone https://github.com/WestonVoglesonger/CORTEX.git
cd CORTEX

# Install Python dependencies
pip install -r requirements.txt
```

## 2. Build Everything

```bash
# Clean build of harness, plugins, and tests
make clean && make
```

**Expected output:**
```
Building harness...
Building kernel plugins from registry...
  Building v1/notch_iir@f32...
  Building v1/bandpass_fir@f32...
  Building v1/goertzel@f32...
Building and running tests...
```

**Troubleshooting:**
- **macOS "dylib not found"**: Ensure Xcode CLT installed
- **Linux "libdl not found"**: `sudo apt-get install libdl-dev`
- See [docs/guides/troubleshooting.md](../guides/troubleshooting.md) for more issues

## 3. Run Your First Benchmark

```bash
# Run automated pipeline (build + validate + benchmark + analyze)
./cortex.py pipeline
```

**What happens:**
1. Validates all kernels against Python oracles
2. Runs benchmarks on each kernel (default: 5 seconds per kernel, configurable via `--duration`)
3. Generates analysis plots and summary

**Expected runtime:** ~2-3 minutes for default 5-second runs (depends on system and number of kernels)

**Note**: To run longer benchmarks, use `./cortex.py pipeline --duration 125` for 125-second runs per kernel.

## 4. View Results

```bash
# View summary table (most recent run)
cat results/run-*/analysis/SUMMARY.md

# Or view a specific run
cat results/run-2025-11-10-001/analysis/SUMMARY.md

# Open visualizations (macOS)
open results/run-*/analysis/latency_comparison.png
open results/run-*/analysis/latency_cdf_overlay.png
open results/run-*/analysis/deadline_miss_rate.png

# Open visualizations (Linux)
xdg-open results/run-*/analysis/latency_comparison.png
```

**Example output:**
```
Kernel          | Median Latency | p95 Latency | p99 Latency | Deadline Miss Rate
----------------|----------------|-------------|-------------|--------------------
notch_iir       |   18.2 µs     |   24.5 µs   |   32.1 µs   | 0.00%
bandpass_fir    |   42.3 µs     |   58.7 µs   |   78.4 µs   | 0.00%
goertzel        |   35.6 µs     |   48.2 µs   |   64.9 µs   | 0.00%
```

## 5. Run Individual Commands

```bash
# List available kernels
./cortex.py list

# Validate a specific kernel
./cortex.py validate --kernel goertzel

# Run a single benchmark with custom name
./cortex.py run --kernel notch_iir --duration 30 --run-name quick-test

# Analyze most recent run
./cortex.py analyze

# Analyze specific run
./cortex.py analyze --run-name quick-test
```

## Next Steps

### Run Custom Benchmarks

```bash
# Longer duration for more statistical confidence
./cortex.py run --all --duration 300 --repeats 5

# Single kernel with custom settings
./cortex.py run --kernel bandpass_fir --duration 60 --warmup 5
```

### Modify Configuration

```bash
# Edit default config
vim configs/cortex.yaml

# Run with custom config
./src/harness/cortex run configs/my-custom-config.yaml
```

### Add Your Own Kernel

See [docs/guides/adding-kernels.md](../guides/adding-kernels.md) for step-by-step guide.

## Verification Checklist

- [x] Build completes without errors
- [x] Tests pass (`make tests`)
- [x] Kernels validate successfully (`./cortex.py validate --kernel <name>` for each kernel)
- [x] Benchmarks run and produce results
- [x] Analysis generates plots
- [x] SUMMARY.md shows realistic latencies (< 1 ms for EEG kernels)

## Common Issues

| Issue | Solution |
|-------|----------|
| `cortex: command not found` | Use `./cortex.py` or add to PATH |
| `Permission denied` | `chmod +x cortex.py` |
| `Plugin not found` | Run `make plugins` to rebuild |
| `Dataset file not found` | Check `configs/cortex.yaml` dataset path |
| High deadline miss rate | System overloaded, close other applications |

## Learning Resources

- **Complete CLI Reference**: [cli-usage.md](cli-usage.md)
- **Architecture Overview**: [docs/architecture/overview.md](../architecture/overview.md)
- **Configuration Guide**: [docs/reference/configuration.md](../reference/configuration.md)
- **Plugin Interface**: [docs/reference/plugin-interface.md](../reference/plugin-interface.md)
- **Troubleshooting**: [docs/guides/troubleshooting.md](../guides/troubleshooting.md)

## Need Help?

- Check [Troubleshooting Guide](../guides/troubleshooting.md)
- Review [CLI Usage](cli-usage.md)
- Open a GitHub Issue
- See [CONTRIBUTING.md](../../CONTRIBUTING.md) for development questions
