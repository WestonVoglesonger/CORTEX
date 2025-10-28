# CORTEX
CORTEX — Common Off-implant Runtime Test Ecosystem for BCI kernels. A reproducible benchmarking pipeline measuring latency, jitter, throughput, memory, and energy for Brain–Computer Interface kernels under real-time deadlines.

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
- See `docs/MACOS_COMPATIBILITY.md` for detailed platform information

## Future: Capability Assessment System

**Current Limitation**: Users asking "Can my system handle X channels at Y Hz?" requires generating synthetic data on-demand, which is slow and complex.

**Future Solution**: Pre-computed capability database approach:
- Generate synthetic EEG datasets once for standard configurations (64→2048 channels, 160→500 Hz)
- Benchmark each system once to determine maximum capabilities per kernel
- Store results in queryable database with instant answers
- Benefits: Fast queries, reproducible benchmarks, scalable to high channel counts

**Implementation**: Planned for `scripts/` directory with dataset generation, benchmarking, and capability query tools.
