# Testing Strategy

This document describes CORTEX's software testing practices, test suites, and quality assurance approach.

## Testing Philosophy

CORTEX uses a **multi-layered testing approach** to ensure correctness at every level:

1. **Unit Tests** - Validate individual components in isolation
2. **Integration Tests** - Verify component interactions and data flow
3. **Validation Tests** - Ensure numerical correctness against reference implementations
4. **Structure Tests** - Verify kernel registry organization and metadata
5. **Smoke Tests** - Basic functionality checks for CLI and configuration

All tests must pass before code is merged. Tests are designed to be fast, deterministic, and runnable on both macOS and Linux without special hardware.

## Test Suites

### Unit Tests

#### test_replayer - Dataset Streaming
**Location:** `tests/test_replayer.c`

Tests the replayer module's data streaming and timing behavior:
- Hop-sized chunks delivered at correct cadence (H/Fs seconds)
- EOF handling and dataset rewind
- Data continuity across chunks
- Multiple configurations (various Fs, C, H values)

**Run:**
```bash
make -C tests test-replayer
```

**Coverage:**
- Chunk size validation
- Timing accuracy (500ms period → 501ms actual)
- EOF detection and looping
- Data ordering verification

#### test_scheduler - Window Formation
**Location:** `tests/test_scheduler.c`

Tests the scheduler module's windowing and plugin dispatch:
- Window formation from hop-sized chunks
- Overlapping window management (W-H sample retention)
- Buffer management for various chunk sizes
- Multiple plugin dispatch
- Warmup period handling
- Flush functionality (remaining samples)
- Sequential plugin execution (isolation)
- Data continuity through scheduler

**Run:**
```bash
make -C tests test-scheduler
```

**Coverage:**
- Configuration validation
- Buffer boundary conditions
- Plugin isolation (no interference)
- State management across windows

#### test_clock_resolution - Timing Infrastructure
**Location:** `tests/test_clock_resolution.c`

Tests the timing measurement infrastructure:
- CLOCK_MONOTONIC resolution (clock_getres)
- Minimum observable time differences
- clock_gettime() overhead
- Simulated latency measurement accuracy
- Platform-specific timing capabilities

**Run:**
```bash
make -C tests test-clock-resolution
```

**Coverage:**
- Nanosecond precision validation
- Measurement overhead quantification
- Platform differences (mach_timebase vs hrtimers)

### Integration Tests

#### test_kernel_accuracy - Numerical Validation
**Location:** `tests/test_kernel_accuracy.c`

Validates C kernel implementations against Python reference implementations (oracles):
- Loads real EEG data from PhysioNet dataset
- Processes windows through C kernels
- Processes same data through Python oracles via subprocess
- Compares outputs with configurable tolerances
- Tracks maximum absolute and relative errors
- Validates state persistence for stateful filters

**Run:**
```bash
# Test specific kernel
./tests/test_kernel_accuracy --kernel notch_iir --windows 10

# Verbose output with per-sample errors
./tests/test_kernel_accuracy --kernel bandpass_fir --windows 5 --verbose

# Custom dataset
./tests/test_kernel_accuracy --kernel goertzel --data datasets/custom.float32
```

**Coverage:**
- Float32 numerical accuracy (rtol=1e-5, atol=1e-6)
- State persistence across windows (IIR/FIR)
- Real EEG data processing
- Oracle-based validation

**Tolerances:**
- **Relative tolerance (rtol):** 1e-5 (0.00001)
- **Absolute tolerance (atol):** 1e-6 (0.000001)

A sample passes if: `abs_error <= atol OR rel_error <= rtol`

#### test_kernel_registry - Structure Validation
**Location:** `tests/test_kernel_registry.c`

Validates kernel registry structure and metadata:
- All expected kernel directories exist
- spec.yaml files present with required sections
- oracle.py files present and executable
- Required spec fields present (input_shape, output_shape, stateful, tolerances)

**Run:**
```bash
make -C tests test-kernel-registry
```

**Coverage:**
- Directory structure compliance
- Metadata completeness
- Oracle availability

### Smoke Tests

#### test_cli.py - CLI Functionality
**Location:** `tests/test_cli.py`

Basic CLI smoke tests:
- Kernel discovery from registry
- YAML config generation
- Kernel name extraction from paths

**Run:**
```bash
python3 tests/test_cli.py
```

**Coverage:**
- CLI entry points functional
- Config generation doesn't crash
- Kernel enumeration works

## Oracle-Based Validation

Each kernel has a Python reference implementation (`oracle.py`) used for validation:

**Location:** `primitives/kernels/v1/{name}@{dtype}/oracle.py`

**Available oracles:**
- `car@f32/oracle.py` - Common Average Reference
- `notch_iir@f32/oracle.py` - Notch IIR filter (SciPy)
- `bandpass_fir@f32/oracle.py` - FIR bandpass (SciPy)
- `goertzel@f32/oracle.py` - Goertzel bandpower

**CLI Interface:**
```bash
# Test mode (used by test_kernel_accuracy)
python3 primitives/kernels/v1/notch_iir@f32/oracle.py --test input.bin --output output.bin --state state.bin
```

**Note:** Oracles only support `--test` mode. Standalone mode (without flags) is not supported.

**Features:**
- State persistence for stateful filters
- Binary I/O (float32 little-endian)
- Exact match to SciPy/NumPy reference implementations

## Running All Tests

### Building Test Binaries

Tests are compiled on-demand:
```bash
make -C tests all              # Build all test binaries
make -C tests test_replayer    # Build specific test
```

Pre-built binaries appear in `tests/` directory and are required before running individual tests.

### Quick Test
```bash
make -C tests test  # Run from project root
# OR
cd tests && make test  # Run from tests/ directory
```
Runs core unit tests (replayer, scheduler, kernel registry).

**Note:** This excludes timing and validation tests which must be run separately:
- `test-clock-resolution`
- `test-kernel-accuracy`

### Individual Test Suites
```bash
make -C tests test-replayer
make -C tests test-scheduler
make -C tests test-kernel-registry
make -C tests test-kernel-accuracy
make -C tests test-clock-resolution
python3 tests/test_cli.py
```

### Kernel Validation
```bash
# Via CLI wrapper (recommended)
./cortex.py validate --kernel notch_iir
./cortex.py validate --kernel bandpass_fir --verbose

# Direct test binary
./tests/test_kernel_accuracy --kernel notch_iir --windows 10 --verbose
```

### Clean Test Artifacts
```bash
make -C tests clean
```

## Writing New Tests

### Test Utilities

**C Test Macros:**
```c
TEST_ASSERT(condition, message)              // Boolean assertion
TEST_ASSERT_EQ(expected, actual, message)   // Equality check
TEST_ASSERT_NEAR(a, b, tolerance, message)  // Floating-point comparison
```

**Example:**
```c
TEST_ASSERT(result != NULL, "Initialization failed");
TEST_ASSERT_EQ(64, config.channels, "Channel count mismatch");
TEST_ASSERT_NEAR(160.0, measured_rate, 0.1, "Sample rate incorrect");
```

### Adding a Unit Test

1. Create `tests/test_newfeature.c`
2. Include required headers (`cortex_plugin.h`, component headers)
3. Write test functions
4. Add main() with test runner
5. Update `tests/Makefile`:
   ```makefile
   test-newfeature: test_newfeature
       ./test_newfeature
   ```

### Adding Kernel Validation

1. Implement `primitives/kernels/v1/{name}@{dtype}/oracle.py`
2. Add kernel to `tests/test_kernel_registry.c` expected list
3. Run `./tests/test_kernel_accuracy --kernel {name}`

## PR Requirements

Before submitting a pull request:

- [ ] All unit tests pass: `make test`
- [ ] Kernel validation passes: `./cortex.py validate --kernel {name}` (if applicable)
- [ ] Build succeeds on macOS and Linux
- [ ] No compiler warnings with `-Wall -Wextra`
- [ ] New functionality includes tests
- [ ] Tests are documented (comments explaining what's being tested)

## Coverage Expectations

### Core Modules
- **Replayer:** Unit tests for timing, chunking, EOF handling
- **Scheduler:** Unit tests for windowing, buffering, dispatch
- **Telemetry:** Structure tests (fields present, types correct)
- **Plugin Loader:** Integration tests via full harness runs

### Kernels
- **Numerical correctness:** Oracle validation within tolerances
- **Edge cases:** NaN handling, first window (zero state), state persistence
- **Spec compliance:** Registry structure tests
- **Documentation:** README.md with mathematical specification

### CLI
- **Smoke tests:** Basic functionality doesn't crash
- **Config generation:** YAML output valid
- **Kernel discovery:** Registry enumeration works

## Test Data

### PhysioNet EEG Dataset

**Source:** EEG Motor Movement/Imagery Database (S001R03)

**Format:** Float32 raw binary (little-endian)
- 64 channels
- 160 Hz sampling rate
- Converted from EDF using `datasets/tools/convert_edf_to_raw.py`

**Location:** `datasets/eegmmidb/converted/S001R03.float32`

**Used by:**
- `test_kernel_accuracy` - Real EEG data for validation
- Full harness runs via `./cortex.py run`

**Conversion:**
```bash
python3 datasets/tools/convert_edf_to_raw.py \
    datasets/eegmmidb/edf/S001R03.edf \
    datasets/eegmmidb/converted/S001R03.float32
```

## Cross-Platform Testing

### macOS
- Uses `.dylib` for plugins
- CLOCK_MONOTONIC via mach_timebase_info
- Tested on Apple Silicon (arm64) and Intel (x86_64)

### Linux
- Uses `.so` for plugins
- CLOCK_MONOTONIC via POSIX hrtimers
- Tested on Ubuntu, Debian, Fedora, Alpine

### Platform-Specific Tests
- `test_clock_resolution` reports platform timing capabilities
- Plugin loading tests both `.dylib` and `.so` extensions
- Makefiles use `$(LIBEXT)` variable for cross-platform builds

## Edge Case Testing

### NaN Handling
All kernels must handle NaN inputs gracefully:
- **CAR:** Exclude NaN channels from mean calculation
- **Filters:** Treat NaN as 0 for filtering purposes
- **Goertzel:** Propagate NaN through computation

Validated by: Oracle comparison on synthetic NaN data (future)

### State Persistence
Stateful filters (IIR, FIR) must maintain state across windows:
- **First window:** Zero-initialized state
- **Subsequent windows:** State carried from previous window
- **Validation:** Multi-window oracle comparison in `test_kernel_accuracy`

### Window Boundaries
- **FIR:** Keeps last (numtaps-1) samples per channel
- **IIR:** Maintains biquad state (x[n-1], x[n-2], y[n-1], y[n-2])
- **Validation:** Continuous vs windowed processing must match

## Not Yet Implemented

The following testing capabilities are planned but not yet implemented:

- [ ] **CI/CD Integration** - Automated test running on push/PR
- [ ] **--all flag for test_kernel_accuracy** - Flag exists but returns "not yet implemented" message
- [ ] **Performance Regression Tests** - Baseline latency tracking
- [ ] **Telemetry Output Validation** - CSV/NDJSON format correctness
- [ ] **Config Parsing Tests** - YAML validation and error handling
- [ ] **Plugin Loading Tests** - ABI version checking, error paths
- [ ] **Deadline Miss Detection Tests** - Explicit deadline enforcement validation
- [ ] **Oracle Unit Tests** - Python oracle correctness
- [ ] **Test Coverage Reports** - lcov/gcov integration
- [ ] **Test Matrix** - Documented platform × test combinations
- [ ] **Synthetic Test Data** - Generated datasets for specific edge cases

## Continuous Integration

**Status:** Not yet configured

**Planned approach:**
- GitHub Actions on push/PR
- Matrix build: macOS (arm64 + x86_64) × Linux (Ubuntu)
- Run `make test` and `./cortex.py validate` for all kernels
- Fail on compiler warnings
- Upload test logs as artifacts

## Related Documentation

- **Benchmarking Methodology:** [benchmarking-methodology.md](benchmarking-methodology.md) - HIL vs on-device measurement philosophy
- **Plugin Interface:** [../reference/plugin-interface.md](../reference/plugin-interface.md) - ABI specification for kernels
- **Adding Kernels:** [../guides/adding-kernels.md](../guides/adding-kernels.md) - Kernel development workflow including testing
- **Contributing:** [../../CONTRIBUTING.md](../../CONTRIBUTING.md) - PR requirements and code review process
