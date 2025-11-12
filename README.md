# CORTEX

![Version](https://img.shields.io/badge/version-0.2.0-blue)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

CORTEX — Common Off-implant Runtime Test Ecosystem for BCI kernels. A reproducible benchmarking pipeline measuring latency, jitter, throughput, memory, and energy for Brain–Computer Interface kernels under real-time deadlines.

## Quick Start

```bash
# Clone and install dependencies
git clone https://github.com/WestonVoglesonger/CORTEX.git
cd CORTEX
pip install -r requirements.txt

# Build and run full pipeline
make clean && make
./cortex.py pipeline

# View results (analysis is in the run directory)
cat results/run-*/analysis/SUMMARY.md
```

**See [Quick Start Guide](docs/getting-started/quickstart.md) for detailed setup instructions.**

## Features

- ✅ **Automated CLI Pipeline** - Build, validate, benchmark, and analyze with one command
- ✅ **Plugin Architecture** - Dynamically loadable signal processing kernels (ABI v2)
- ✅ **Real-Time Scheduling** - Deadline enforcement with SCHED_FIFO/RR support (Linux)
- ✅ **Comprehensive Telemetry** - Latency, jitter, throughput, memory, deadline tracking
- ✅ **Multiple Output Formats** - NDJSON (streaming-friendly) and CSV
- ✅ **Visualization & Analysis** - Automated plot generation and statistical summaries
- ✅ **Cross-Platform** - macOS (arm64/x86_64) and Linux (x86_64/arm64)
- ✅ **Oracle Validation** - Numerical correctness verified against SciPy/MNE references

**Current Kernels** (v1 float32):
- CAR (Common Average Reference)
- Notch IIR filter (60 Hz line noise removal)
- FIR bandpass filter (8-30 Hz)
- Goertzel bandpower (alpha/beta bands)

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
# Clone and build entire pipeline (works on both macOS and Linux)
make clean && make

# Or build individual components:
make harness    # Build benchmarking harness
make plugins    # Build plugins (when available)
make tests      # Build and run unit tests

# Verify build
./src/harness/cortex run configs/cortex.yaml
```

### Platform-Specific Notes

- **macOS**: Uses `.dylib` extension for plugins
- **Linux**: Uses `.so` extension for plugins
- Plugin developers: Use `$(LIBEXT)` variable in Makefiles
- See [docs/architecture/platform-compatibility.md](docs/architecture/platform-compatibility.md) for detailed platform information

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
