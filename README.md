# CORTEX

![Version](https://img.shields.io/badge/version-0.2.0-blue)
![CI](https://github.com/WestonVoglesonger/CORTEX/actions/workflows/ci.yml/badge.svg)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**CORTEX** — Common Off-implant Runtime Test Ecosystem for BCI kernels. A production-grade benchmarking framework for Brain-Computer Interface signal processing, built on **AWS-inspired primitives architecture** for maximum composability and reproducibility.

CORTEX measures latency, jitter, throughput, memory usage, and energy consumption for BCI kernels under real-time deadlines, providing comprehensive telemetry for performance-critical neurotechnology research.

## Architecture Highlights

CORTEX has been redesigned with a **clean, modular architecture** inspired by AWS primitives philosophy:

- **From 14 → 7 directories**: Streamlined repository structure for production-grade organization
- **Composable primitives**: Kernels, configs, and adapters as reusable building blocks
- **Unified source layout**: Modern Python packaging (PEP 517/518) with `src/` directory best practices
- **Separation of concerns**: Clean boundaries between engine (C), CLI (Python), and data

```
CORTEX/
├── src/               # Unified source code
│   ├── cortex/        # Python CLI & analysis tools
│   └── engine/        # C engine (harness, replayer, scheduler, plugin ABI)
├── primitives/        # Composable building blocks (AWS philosophy)
│   ├── kernels/       # Signal processing kernel implementations
│   └── configs/       # Configuration templates
├── datasets/          # EEG datasets for benchmarking
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

# Build C engine and kernel plugins
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
- ✅ **Plugin Architecture** - Dynamically loadable signal processing kernels (ABI v2)
- ✅ **Real-Time Scheduling** - Deadline enforcement with SCHED_FIFO/RR support (Linux)
- ✅ **Comprehensive Telemetry** - Latency, jitter, throughput, memory, deadline tracking
- ✅ **Multiple Output Formats** - NDJSON (streaming-friendly) and CSV
- ✅ **Visualization & Analysis** - Automated plot generation and statistical summaries
- ✅ **Cross-Platform** - macOS (arm64/x86_64) and Linux (x86_64/arm64)
- ✅ **Oracle Validation** - Numerical correctness verified against SciPy/MNE references

### Architecture & Engineering
- ✅ **AWS Primitives Philosophy** - Composable building blocks for kernel, config, and dataset primitives
- ✅ **Modern Python Packaging** - PEP 517/518 compliant with `pyproject.toml` and `src/` layout
- ✅ **Clean Repository Structure** - Streamlined from 14 directories to 7 production-grade directories
- ✅ **Separation of Concerns** - Clear boundaries between engine (C), CLI (Python), and data layers

**Current Kernels** (v1 float32):
- CAR (Common Average Reference)
- Notch IIR filter (60 Hz line noise removal)
- FIR bandpass filter (8-30 Hz)
- Goertzel bandpower (alpha/beta bands)

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

# Check C engine
./src/engine/harness/cortex run primitives/configs/cortex.yaml

# Run test suite
make test
```

## Repository Structure

CORTEX follows a **production-grade architecture** with clean separation of concerns:

```
CORTEX/
├── src/                           # Unified source code (PEP 517/518)
│   ├── cortex/                    # Python CLI & analysis toolkit
│   │   ├── commands/              # CLI subcommands (pipeline, build, validate, run, analyze)
│   │   ├── utils/                 # Analysis, plotting, file I/O utilities
│   │   └── ui/                    # Terminal output formatting
│   └── engine/                    # C benchmarking engine
│       ├── harness/               # Main execution harness
│       ├── replayer/              # Dataset streaming engine
│       ├── scheduler/             # Real-time scheduling & deadline enforcement
│       └── include/               # Plugin ABI v2 headers
│
├── primitives/                    # Composable building blocks (AWS philosophy)
│   ├── kernels/                   # Signal processing kernel implementations
│   │   ├── bandpass_fir/          # FIR bandpass filter (8-30 Hz)
│   │   ├── car/                   # Common Average Reference
│   │   ├── goertzel_bandpower/    # Goertzel bandpower (alpha/beta)
│   │   └── notch_iir/             # IIR notch filter (60 Hz)
│   └── configs/                   # Configuration templates (YAML)
│       └── cortex.yaml            # Default benchmark configuration
│
├── datasets/                      # EEG datasets for benchmarking
│   ├── tools/                     # Dataset conversion utilities
│   │   └── edf_to_float32.py      # EDF → float32 converter
│   └── *.float32                  # Preprocessed binary datasets (gitignored)
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

## Documentation

📚 **[Complete Documentation](docs/README.md)**

- **Getting Started**: [Quick Start](docs/getting-started/quickstart.md) | [CLI Usage](docs/getting-started/cli-usage.md)
- **Reference**: [Plugin API](docs/reference/plugin-interface.md) | [Configuration](docs/reference/configuration.md)
- **Architecture**: [System Overview](docs/architecture/overview.md) | [Testing Strategy](docs/architecture/testing-strategy.md)
- **Guides**: [Adding Kernels](docs/guides/adding-kernels.md) | [Troubleshooting](docs/guides/troubleshooting.md)
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

# Verify build
./src/engine/harness/cortex run primitives/configs/cortex.yaml
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

# Run benchmarks with custom config
cortex run primitives/configs/cortex.yaml

# Analyze existing results
cortex analyze results/run-20250112-143022/
```

### Using the C Engine Directly

```bash
# Run with default configuration
./src/engine/harness/cortex run primitives/configs/cortex.yaml

# Override configuration parameters
./src/engine/harness/cortex run primitives/configs/cortex.yaml \
  --kernel primitives/kernels/bandpass_fir/bandpass_fir.dylib \
  --dataset datasets/S001R01.float32 \
  --deadline-us 10000
```

### Working with Primitives

```bash
# Browse available kernel implementations
ls primitives/kernels/

# View configuration templates
cat primitives/configs/cortex.yaml

# Convert EEG datasets to float32 format
python datasets/tools/edf_to_float32.py \
  input.edf output.float32 --channels 64 --duration 60
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
  version = {0.2.0}
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

**Current Version**: 0.2.0 (Fall 2025)

**Roadmap**: See [docs/development/roadmap.md](docs/development/roadmap.md) for implementation timeline and future plans.

**Future Work** (Spring 2026):
- Quantization support (Q15/Q7 fixed-point kernels)
- Energy measurement (RAPL on x86, INA226 on embedded)
- Hardware-in-the-Loop testing on embedded targets (STM32H7, Jetson)