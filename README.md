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
# Clone and build (works on both macOS and Linux)
cd src/harness
make clean && make

# Verify build
./cortex run <config.yaml>
```

### Platform-Specific Notes

- **macOS**: Uses `.dylib` extension for plugins
- **Linux**: Uses `.so` extension for plugins
- Plugin developers: Use `$(LIBEXT)` variable in Makefiles
- See `docs/MACOS_COMPATIBILITY.md` for detailed platform information
