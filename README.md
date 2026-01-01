# CORTEX

![Version](https://img.shields.io/badge/version-0.3.0-blue)
![CI](https://github.com/WestonVoglesonger/CORTEX/actions/workflows/ci.yml/badge.svg)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**CORTEX** — Common Off-implant Runtime Test Ecosystem for BCI kernels. A production-grade benchmarking framework for Brain-Computer Interface signal processing, built on **AWS-inspired primitives architecture** for maximum composability and reproducibility.

CORTEX measures latency, jitter, throughput, memory usage, and energy consumption for BCI kernels under real-time deadlines, providing comprehensive telemetry for performance-critical neurotechnology research.

## Architecture Highlights

CORTEX follows a **clean, modular architecture** inspired by AWS primitives philosophy:

- **Composable primitives**: Kernels, configs, and datasets as reusable building blocks
- **Unified source layout**: Modern Python packaging (PEP 517/518) with `src/` directory best practices
- **Separation of concerns**: Clean boundaries between engine (C), CLI (Python), and data
- **Validated measurement methodology**: Empirically proven <1µs harness overhead, <13% of all kernel signals

```
CORTEX/
├── src/               # Unified source code
│   ├── cortex/        # Python CLI & analysis tools
│   └── engine/        # C engine (harness, replayer, scheduler, telemetry)
├── sdk/               # Kernel development kit
│   └── kernel/        # Headers, libraries, tools (ABI v3)
├── primitives/        # Composable building blocks (AWS philosophy)
│   ├── kernels/       # Signal processing kernel implementations
│   ├── datasets/      # EEG dataset primitives (versioned)
│   └── configs/       # Configuration templates
├── results/           # Benchmark outputs (generated, gitignored)
├── tests/             # Comprehensive test suite
└── docs/              # Complete documentation
```

## Quick Start

```bash
# Clone repository
git clone https://github.com/WestonVoglesonger/CORTEX.git
cd CORTEX

# Install Python CLI and dependencies
pip install -e .

# Build C engine, device adapters, and kernel plugins
make all

# Run full benchmarking pipeline
cortex pipeline

# View results and analysis
cat results/run-*/analysis/SUMMARY.md
```

**See [Quick Start Guide](docs/getting-started/quickstart.md) for detailed setup and configuration instructions.**

## Features

### Core Capabilities
- ✅ **Automated CLI Pipeline** - Build, validate, benchmark, and analyze with one command
- ✅ **Device Adapter Architecture** - Unified execution via adapters (local/remote HIL testing)
- ✅ **Plugin Architecture** - Dynamically loadable signal processing kernels (ABI v3)
- ✅ **Trainable Kernels** - Offline calibration support for ML-based algorithms (ICA, CSP, LDA)
- ✅ **Runtime Parameters** - Type-safe configuration API for kernel customization
- ✅ **Real-Time Scheduling** - Deadline enforcement with SCHED_FIFO/RR support (Linux)
- ✅ **Comprehensive Telemetry** - Latency, jitter, throughput, memory, deadline tracking
- ✅ **Multiple Output Formats** - NDJSON (streaming-friendly) and CSV
- ✅ **Visualization & Analysis** - Automated plot generation and statistical summaries
- ✅ **Cross-Platform** - macOS (arm64/x86_64) and Linux (x86_64/arm64)
- ✅ **Oracle Validation** - Numerical correctness verified against SciPy/MNE references
- ✅ **Validated Methodology** - Empirically validated measurement accuracy (n=2399 samples)

### Architecture & Engineering
- ✅ **AWS Primitives Philosophy** - Composable building blocks for kernel, config, and dataset primitives
- ✅ **Modern Python Packaging** - PEP 517/518 compliant with `pyproject.toml` and `src/` layout
- ✅ **Production-Grade Structure** - Clean separation of concerns across engine, CLI, and data
- ✅ **Validated Methodology** - Three cross-platform validation studies (macOS + Linux)

**Current Kernels** (v1 float32):
- CAR (Common Average Reference) - Spatial filtering
- Notch IIR (60 Hz line noise removal) - Configurable f0/Q
- Bandpass FIR (8-30 Hz) - 129-tap filter
- Goertzel (Alpha/Beta bandpower) - Configurable frequency bands
- Welch PSD (Power spectral density) - Configurable FFT/overlap
- ICA (Independent Component Analysis) - Artifact removal (trainable, ABI v3)
- No-op (Identity function) - Harness overhead baseline

## Installation

### Prerequisites
- **Python**: 3.8 or higher
- **C Compiler**: GCC or Clang with C11 support
- **Build Tools**: Make, pthread library

### Quick Install

```bash
# Clone repository
git clone https://github.com/WestonVoglesonger/CORTEX.git
cd CORTEX

# Install Python CLI and dependencies
pip install -e .

# Build C engine and kernel plugins
make all
```

### Development Install

```bash
# Install with development dependencies (pytest, black, ruff)
pip install -e .[dev]

# Install with dataset conversion tools (pyedflib for EDF processing)
pip install -e .[datasets]

# Install with all optional dependencies
pip install -e .[dev,datasets]
```

### Build Options

```bash
# Build everything (recommended)
make all

# Or build individual components:
make harness    # Build C benchmarking engine
make plugins    # Build signal processing kernel plugins
make tests      # Build and run C unit tests

# Clean build artifacts
make clean
```

### Verify Installation

```bash
# Check Python CLI
cortex --help

# Check C engine (routes through native adapter)
cortex run primitives/configs/cortex.yaml

# Run test suite
make test
```

## Validation & Measurement Methodology

CORTEX's measurement methodology has been empirically validated across platforms:

### Key Findings

**Harness Overhead** ([`experiments/noop-overhead-2025-12-05/`](experiments/noop-overhead-2025-12-05/)):
- **1 µs minimum** measured overhead (n=2399 samples, macOS M1)
- Components: timing (100ns) + dispatch (50-100ns) + memcpy (800ns) + bookkeeping (100ns)
- **0.02-12.5% of signal** across all kernels (<3% for kernels >30µs)
- **SNR: 8:1 to 5000:1** (all exceed 10:1 industry standard using typical latency)

**Idle Paradox** ([`experiments/dvfs-validation-2025-11-15/`](experiments/dvfs-validation-2025-11-15/)):
- **macOS**: Idle systems run 2.31× slower than medium load (geometric mean across 4 kernels)
- **Cause**: DVFS downclocking to minimum frequency when idle
- **Solution**: Background load (4 CPUs @ 50%) locks CPU frequency

**Cross-Platform Replication** ([`experiments/linux-governor-validation-2025-12-05/`](experiments/linux-governor-validation-2025-12-05/)):
- **Linux**: Powersave governor 3.21× slower than performance (confirms Idle Paradox is cross-platform)
- **Schedutil Trap**: Dynamic scaling is 4.55× slower than performance (worse than fixed minimum!)
- **Platform Difference**: stress-ng works on macOS (cluster-wide scaling) but fails on Linux (per-CPU scaling)
- **Recommendation**: Use `performance` governor on Linux, NOT stress-ng

**Validation**: These findings prove that DVFS effects (2-4×) dominate measurement methodology, while harness overhead (1µs) is negligible.

---

## Repository Structure

CORTEX follows a **production-grade architecture** with clean separation of concerns:

```
CORTEX/
├── src/                           # Unified source code (PEP 517/518)
│   ├── cortex/                    # Python CLI & analysis toolkit
│   │   ├── commands/              # CLI subcommands (pipeline, build, validate, run, analyze, calibrate)
│   │   ├── utils/                 # Analysis, plotting, file I/O utilities
│   │   └── ui/                    # Terminal output formatting
│   └── engine/                    # C benchmarking engine
│       ├── harness/               # Main execution harness
│       ├── replayer/              # Dataset streaming engine
│       ├── scheduler/             # Real-time scheduling & deadline enforcement
│       └── telemetry/             # Performance data collection
│
├── sdk/                           # Kernel development kit (ABI v3)
│   └── kernel/                    # SDK for kernel developers
│       ├── include/               # Plugin ABI v3 headers (cortex_plugin.h)
│       ├── lib/                   # Reusable libraries (state I/O, loader, params)
│       └── tools/                 # Development tools (cortex_validate, cortex_calibrate)
│
├── primitives/                    # Composable building blocks (AWS philosophy)
│   ├── kernels/v1/                # Signal processing kernel implementations (7 kernels)
│   │   ├── bandpass_fir@f32/      # FIR bandpass filter (8-30 Hz)
│   │   ├── car@f32/               # Common Average Reference
│   │   ├── goertzel@f32/          # Goertzel bandpower (alpha/beta)
│   │   ├── ica@f32/               # Independent Component Analysis (trainable, ABI v3)
│   │   ├── notch_iir@f32/         # IIR notch filter (60 Hz, configurable f0/Q)
│   │   ├── welch_psd@f32/         # Welch PSD (configurable FFT/overlap)
│   │   └── noop@f32/              # No-op kernel (harness overhead baseline)
│   ├── datasets/v1/               # Dataset primitives (EEG recordings)
│   │   ├── physionet-motor-imagery/ # PhysioNet Motor Imagery dataset
│   │   │   ├── spec.yaml          # Metadata (channels, sample_rate, recordings)
│   │   │   └── converted/*.float32 # Preprocessed binary data
│   │   └── fake/                  # Synthetic test dataset
│   └── configs/                   # Configuration templates (YAML)
│       └── cortex.yaml            # Default benchmark configuration
│
├── experiments/                   # Validation studies & measurement methodology
│   ├── dvfs-validation-2025-11-15/          # Idle Paradox discovery (macOS)
│   ├── linux-governor-validation-2025-12-05/ # Cross-platform + Schedutil Trap
│   └── noop-overhead-2025-12-05/            # Harness overhead measurement (1µs)
│
├── results/                       # Benchmark outputs (gitignored)
│   └── run-<timestamp>/           # Per-run results
│       ├── telemetry.ndjson       # Raw benchmark data
│       └── analysis/              # Plots and statistical summaries
│
├── tests/                         # Comprehensive test suite
│   ├── unit/                      # C unit tests
│   └── integration/               # End-to-end integration tests
│
├── docs/                          # Complete documentation
│   ├── getting-started/           # Quick start, CLI usage
│   ├── reference/                 # API docs, configuration reference
│   ├── architecture/              # System design, testing strategy
│   ├── guides/                    # How-to guides, troubleshooting
│   └── development/               # Roadmap, contributing guidelines
│
└── pyproject.toml                 # Modern Python packaging (PEP 517/518)
```

### Design Principles

1. **AWS Primitives Philosophy**: Kernels, configs, and datasets are composable building blocks
2. **Separation of Concerns**: Engine (C) for performance, CLI (Python) for usability
3. **Modern Best Practices**: `src/` layout, `pyproject.toml`, editable installs
4. **Reproducibility**: Configuration-driven benchmarks with version-controlled primitives
5. **Validated Methodology**: Empirically proven measurement accuracy across platforms

## Documentation

📚 **[Complete Documentation](docs/README.md)**

- **Getting Started**: [Quick Start](docs/getting-started/quickstart.md) | [CLI Usage](docs/getting-started/cli-usage.md)
- **Reference**: [Plugin API](docs/reference/plugin-interface.md) | [Configuration](docs/reference/configuration.md)
- **Architecture**: [System Overview](docs/architecture/overview.md) | [Benchmarking Methodology](docs/architecture/benchmarking-methodology.md)
- **Guides**: [Adding Kernels](docs/guides/adding-kernels.md) | [Adding Datasets](docs/guides/adding-datasets.md) | [Troubleshooting](docs/guides/troubleshooting.md)
- **Validation**: [DVFS Validation](experiments/dvfs-validation-2025-11-15/) | [Harness Overhead](experiments/noop-overhead-2025-12-05/) | [Linux Governor Study](experiments/linux-governor-validation-2025-12-05/)
- **Development**: [Roadmap](docs/development/roadmap.md) | [Contributing](CONTRIBUTING.md)

## Supported Platforms

CORTEX is designed for cross-platform development and testing:

### macOS
- **Architectures**: Apple Silicon (arm64), Intel (x86_64)
- **Versions**: macOS 10.15+ (Catalina and later)
- **Build Requirements**:
  - Xcode Command Line Tools (`xcode-select --install`)
  - Standard C11 compiler (clang)
  - pthread support (built-in)

### Linux
- **Distributions**: Ubuntu, Debian, Fedora, CentOS, RHEL, Alpine
- **Architectures**: x86_64, arm64
- **Build Requirements**:
  - GCC or Clang with C11 support
  - pthread library (`libpthread`)
  - Dynamic linker library (`libdl`)

### Building

```bash
# Build entire pipeline (works on both macOS and Linux)
make all

# Or build individual components:
make harness    # Build C benchmarking engine
make plugins    # Build signal processing kernel plugins
make tests      # Build and run C unit tests

# Verify build (routes through adapter automatically)
cortex run primitives/configs/cortex.yaml
```

### Platform-Specific Notes

- **macOS**: Uses `.dylib` extension for plugins
- **Linux**: Uses `.so` extension for plugins
- Plugin developers: Use `$(LIBEXT)` variable in Makefiles
- See [docs/architecture/platform-compatibility.md](docs/architecture/platform-compatibility.md) for detailed platform information

## Usage Examples

### Full Benchmarking Pipeline

```bash
# Run complete pipeline: build, validate, benchmark, analyze
cortex pipeline

# Results will be in results/run-<timestamp>/
# - telemetry.ndjson: Raw benchmark data
# - analysis/: Plots and statistical summaries
```

### Individual Commands

```bash
# Build C engine and plugins
cortex build

# Validate kernel correctness against oracles
cortex validate

# Calibrate trainable kernels (ABI v3)
cortex calibrate --kernel ica --data primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
  --output ica_S001.cortex_state

# Run benchmarks with custom config
cortex run primitives/configs/cortex.yaml

# Run trainable kernel with calibration state
cortex run --kernel ica --state ica_S001.cortex_state --duration 10

# Analyze existing results
cortex analyze results/run-20250112-143022/
```

### Advanced Usage

```bash
# Filter to specific kernel(s) via environment variable
CORTEX_KERNEL_FILTER=noop cortex run primitives/configs/cortex.yaml

# Override benchmark duration/repeats
CORTEX_DURATION_OVERRIDE=10 CORTEX_REPEATS_OVERRIDE=5 cortex run primitives/configs/cortex.yaml

# Specify custom output directory
CORTEX_OUTPUT_DIR=/tmp/my_results cortex run primitives/configs/cortex.yaml
```

**Note:** All kernel execution routes through device adapters (no direct harness execution). See [adapter documentation](primitives/adapters/v1/README.md) for details.

### Working with Primitives

```bash
# Browse available kernel implementations
ls primitives/kernels/

# View dataset primitives
ls primitives/datasets/v1/

# View configuration templates
cat primitives/configs/cortex.yaml
```

### Analysis and Visualization

```bash
# Generate plots and summaries for latest run
cortex analyze results/run-latest/

# View comprehensive analysis report
cat results/run-latest/analysis/SUMMARY.md

# Access raw telemetry for custom analysis
python -c "import pandas as pd; df = pd.read_json('results/run-latest/telemetry.ndjson', lines=True); print(df.describe())"
```

## Citation

If you use CORTEX in your research, please cite:

```bibtex
@software{cortex2025,
  title = {CORTEX: Common Off-implant Runtime Test Ecosystem for BCI Kernels},
  author = {Voglesonger, Weston and Kumar, Avi},
  year = {2025},
  url = {https://github.com/WestonVoglesonger/CORTEX},
  version = {0.3.0}
}
```

See [CITATION.cff](CITATION.cff) for machine-readable citation metadata.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**Dataset License**: This project uses the PhysioNet EEG Motor Movement/Imagery Dataset, licensed under ODC-By 1.0. See [LICENSE](LICENSE) for dataset attribution requirements.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:
- Code style and standards
- Adding new kernels
- Testing requirements
- Pull request process

## Project Status

**Current Version**: 0.3.0 (Winter 2025)

**Latest Release**: ABI v3 with trainable kernel support
- Offline calibration workflow for ML-based algorithms
- ICA kernel reference implementation
- SDK restructure for kernel development
- Complete backward compatibility with v2 kernels

**Roadmap**: See [docs/development/roadmap.md](docs/development/roadmap.md) for implementation timeline and future plans.

**Future Work** (Spring 2026):
- Additional trainable kernels (CSP, LDA)
- Quantization support (Q15/Q7 fixed-point kernels)
- Energy measurement (RAPL on x86, INA226 on embedded)
- Hardware-in-the-Loop testing on embedded targets (STM32H7, Jetson)