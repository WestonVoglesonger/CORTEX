# CORTEX Development Instructions

CORTEX — Common Off-implant Runtime Test Ecosystem for BCI kernels. A reproducible benchmarking pipeline measuring latency, jitter, throughput, memory, and energy for Brain–Computer Interface kernels under real-time deadlines.

**ALWAYS follow these instructions first and fallback to additional search and context gathering only if the information in these instructions is incomplete or found to be in error.**

## Project Overview

CORTEX is a benchmarking system designed to evaluate Brain-Computer Interface (BCI) kernels under real-time constraints. The system measures critical performance metrics including:
- Latency and jitter 
- Throughput performance
- Memory consumption
- Energy efficiency
- Real-time deadline compliance

## Current State

**IMPORTANT**: This repository is currently in early development with minimal codebase (only README.md). The following instructions anticipate the typical development patterns for BCI benchmarking systems.

## Working Effectively

### Initial Setup
Since the repository is currently minimal, typical BCI benchmarking systems require:

1. **System Dependencies** (validate these when they become available):
   ```bash
   # Real-time kernel patches may be required
   sudo apt-get update
   sudo apt-get install build-essential cmake git
   sudo apt-get install python3 python3-pip python3-venv
   sudo apt-get install libeigen3-dev libfftw3-dev
   ```

2. **Python Environment Setup** (when requirements.txt is added):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt  # When available
   ```

3. **Build System** (when CMakeLists.txt or Makefile is added):
   ```bash
   mkdir build
   cd build
   cmake ..
   make -j$(nproc)  # NEVER CANCEL: Build may take 15-30 minutes depending on complexity
   ```

### Development Workflow (Future)

When the codebase is developed, expect these patterns:

1. **Real-time Testing** - NEVER CANCEL: BCI benchmarking requires extended test runs
   - Latency tests may run 30-60 minutes to gather sufficient statistical data
   - Jitter measurements require continuous sampling over extended periods
   - Energy profiling tests may run 2+ hours for accurate measurements

2. **Performance Validation** - Set timeouts to 120+ minutes for comprehensive benchmarks
   ```bash
   # Expected commands when implemented:
   ./cortex_benchmark --test-suite full  # May take 60+ minutes
   ./cortex_benchmark --latency-profile  # May take 30+ minutes  
   ./cortex_benchmark --energy-profile   # May take 120+ minutes
   ```

### Testing and Validation

**CRITICAL**: BCI systems have strict real-time requirements. When testing:

1. **Always validate real-time deadlines** - missed deadlines are critical failures
2. **Run extended performance tests** - short tests don't capture jitter patterns
3. **Test under load** - BCI kernels must perform under computational stress
4. **Validate across different hardware** - performance varies significantly by platform

### Expected Directory Structure (Future)

Anticipate this organization as the project develops:
```
CORTEX/
├── src/           # Core benchmarking framework
├── kernels/       # BCI kernel implementations to test
├── benchmarks/    # Specific benchmark configurations
├── results/       # Benchmark output data
├── scripts/       # Automation and analysis scripts
├── docs/          # Documentation
├── tests/         # Unit and integration tests
└── configs/       # Configuration files for different scenarios
```

## Common Tasks (When Available)

### Running Benchmarks
- Always check system load before running benchmarks
- Ensure no other intensive processes are running
- Validate that real-time scheduling is available
- Monitor system temperature during extended runs

### Performance Analysis
- Use statistical analysis tools for jitter measurement
- Generate plots for latency distributions
- Compare results against baseline measurements
- Document any environmental factors affecting performance

### Development Guidelines

1. **Real-time Considerations**:
   - Avoid dynamic memory allocation in critical paths
   - Use lock-free data structures where possible
   - Minimize system calls in performance-critical sections
   - Profile for cache efficiency

2. **Measurement Accuracy**:
   - Use high-resolution timers
   - Account for measurement overhead
   - Validate timer resolution and accuracy
   - Consider system clock drift in long measurements

3. **Code Quality**:
   - Follow real-time programming best practices
   - Document timing requirements and guarantees
   - Use static analysis tools for real-time code
   - Validate memory access patterns

## Timeout Guidelines

**NEVER CANCEL** long-running operations. BCI benchmarking requires extended execution:

- **Build operations**: Set timeout to 60+ minutes
- **Full benchmark suite**: Set timeout to 180+ minutes  
- **Latency profiling**: Set timeout to 90+ minutes
- **Energy measurements**: Set timeout to 240+ minutes
- **Statistical analysis**: Set timeout to 120+ minutes

## Validation Scenarios

**CRITICAL**: Always validate functionality after making changes. When the system becomes functional, always test:

1. **Basic latency measurement**: Run a simple latency test to verify timing infrastructure
2. **Jitter analysis**: Execute jitter measurement and validate statistical outputs
3. **Throughput testing**: Measure data processing rates under various loads
4. **Memory profiling**: Monitor memory usage patterns during benchmark execution
5. **Energy measurement**: Validate energy monitoring capabilities if available

## Current Limitations

- Repository contains only README.md
- No build system currently implemented  
- No test infrastructure available yet
- No benchmarking framework present

**When making changes**: Focus on establishing the foundational infrastructure for BCI benchmarking while maintaining compatibility with real-time requirements.

## References

- BCI systems require sub-millisecond latencies
- Real-time deadlines are hard constraints, not soft targets
- Energy efficiency is critical for implantable systems
- Statistical significance requires large sample sizes (10,000+ measurements typical)