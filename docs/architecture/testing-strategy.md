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

## Pragmatic Testing Philosophy (Python CLI/Utils)

**Added:** 2025-11-18 (CRIT-004 completion)

CORTEX uses a **pragmatic, context-appropriate approach** to dependency injection and testing for Python code. The guiding principle is: **Test behavior, not coverage metrics.**

### When to Use Full DI vs Integration Tests

#### Full Dependency Injection + Unit Tests
Use when **high ROI** from testability:
- **Complex cross-platform logic** (e.g., `check_system.py` - Linux/macOS/Windows behavior differences)
- **Complex business logic** (e.g., scheduler orchestration, multi-kernel benchmarking)
- **State machines** or stateful components with many edge cases
- **Algorithm implementations** that benefit from fast, isolated testing

**Example:** `check_system.py` (CRIT-004 PR #28)
```python
class SystemChecker:
    def __init__(
        self,
        filesystem: FileSystemService,
        process_executor: ProcessExecutor,
        env_provider: EnvironmentProvider,
        tool_locator: ToolLocator,
        logger: Logger
    ):
        # Full DI - enables cross-platform testing without actual OS differences
```

**Benefits:**
- 30 unit tests cover all platforms (Linux/macOS/Windows) on single dev machine
- Mock different OS behaviors without VMs
- Test edge cases (missing files, command failures) deterministically
- Fast execution (<0.2s for 30 tests)

#### Minimal DI + Integration Tests
Use when **deterministic libraries** or **simple I/O** wrappers:
- **Thin wrappers around subprocess/filesystem** (e.g., `build.py`, `clean.py`, `validate.py`)
- **Data processing with deterministic libraries** (e.g., pandas, numpy, matplotlib)
- **Simple CRUD operations** without complex logic
- **CLI argument parsing** (argparse is already well-tested)

**Example:** `analyzer.py` (CRIT-004 PR #27)
```python
class TelemetryAnalyzer:
    def __init__(
        self,
        filesystem: FileSystemService,
        logger: Logger
    ):
        # Minimal DI - only I/O abstracted
        # pandas/matplotlib NOT abstracted (deterministic, no value in mocking pixels)
```

**Rationale:**
- Testing matplotlib pixel-by-pixel provides **zero value**
- Integration tests verify actual plot generation works
- pandas operations are deterministic (no need to mock)
- Focus testing effort on I/O and data transformation logic, not library internals

**Example:** `build.py`, `clean.py`, `validate.py`, `list_kernels.py` (CRIT-004 PR #28)
- No DI refactoring (thin wrappers around `make`, `subprocess`)
- 18 integration tests verify argument handling and error cases
- Testing mocks instead of actual behavior provides **negative value**

### Testing Patterns by Module Type

#### Pattern 1: Full DI for Complex Logic
**Use when:** Multi-platform behavior, complex state, many edge cases

**Structure:**
```
src/cortex/commands/check_system.py  - SystemChecker class with full DI
tests/unit/commands/test_check_system.py  - 30 unit tests (mocked dependencies)
tests/integration/test_check_system_command.py  - 5 integration tests (real dependencies)
```

**Test Distribution:** 85% unit tests, 15% integration tests

#### Pattern 2: Minimal DI for Deterministic Processing
**Use when:** Data transformation, deterministic libraries, simple I/O

**Structure:**
```
src/cortex/utils/analyzer.py  - TelemetryAnalyzer with minimal DI
tests/unit/utils/test_analyzer.py  - 22 unit tests (filesystem/logger mocked, pandas real)
tests/integration/test_analyze_command.py  - 10 integration tests (all real)
```

**Test Distribution:** 60% unit tests, 40% integration tests

#### Pattern 3: Integration-Only for Thin Wrappers
**Use when:** Simple subprocess/filesystem wrappers, CLI argument parsers

**Structure:**
```
src/cortex/commands/build.py  - No refactoring (thin wrapper)
tests/integration/test_cli_commands.py  - 18 integration tests (mocked subprocess only)
```

**Test Distribution:** 0% unit tests, 100% integration tests

### Dependency Injection Infrastructure

**Core Protocols** (`src/cortex/core/protocols.py`):
```python
class Logger(Protocol): ...           # stdout/stderr abstraction
class FileSystemService(Protocol): ... # Path/glob/read/write operations
class ProcessExecutor(Protocol): ...  # subprocess.run/Popen abstraction
class TimeProvider(Protocol): ...     # time.time/sleep abstraction
class EnvironmentProvider(Protocol): ... # os.environ/platform.system
class ToolLocator(Protocol): ...      # shutil.which abstraction
class ConfigLoader(Protocol): ...     # YAML loading abstraction
```

**Production Implementations** (`src/cortex/core/implementations.py`):
- `ConsoleLogger`, `RealFileSystemService`, `SubprocessExecutor`
- `SystemTimeProvider`, `SystemEnvironmentProvider`
- `SystemToolLocator`, `YamlConfigLoader`

**Protocol Benefits:**
- Structural typing (duck typing with type hints)
- No inheritance required (Pythonic)
- Easy to mock (just implement the methods)
- Type-safe with mypy/pyright

### Mock Factories for Unit Tests

**Example:** `test_check_system.py`
```python
def create_mock_filesystem(files=None, dirs=None):
    """Create mock filesystem with pre-configured files."""
    files = files or {}
    dirs = dirs or set()

    class MockFileSystem:
        def exists(self, path):
            return str(path) in files or str(path) in dirs

        def read_file(self, path):
            return files.get(str(path), "")

    return MockFileSystem()

def create_mock_process(commands=None):
    """Create mock process executor with command response lookup."""
    commands = commands or {}

    class MockProcess:
        def run(self, cmd, **kwargs):
            cmd_key = tuple(cmd)
            response = commands.get(cmd_key, {'returncode': 0, 'stdout': '', 'stderr': ''})

            class Result:
                returncode = response['returncode']
                stdout = response['stdout']
                stderr = response['stderr']

            return Result()

    return MockProcess()
```

**Usage:**
```python
def test_linux_performance_governor():
    fs = create_mock_filesystem({
        '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor': 'performance\n'
    })
    env = create_mock_env('Linux')

    checker = SystemChecker(
        filesystem=fs,
        process_executor=create_mock_process(),
        env_provider=env,
        tool_locator=create_mock_tools(),
        logger=create_mock_logger()
    )

    result = checker.check_cpu_governor()
    assert result.status == 'pass'
```

### Anti-Patterns to Avoid

#### ❌ Mocking Deterministic Libraries
```python
# BAD: Mocking pandas provides zero value
def test_calculate_statistics_with_mocked_pandas():
    with patch('pandas.DataFrame') as mock_df:
        mock_df.groupby.return_value.agg.return_value = ...
        # This tests pandas mock, not your logic!
```

```python
# GOOD: Use real pandas, mock only I/O
def test_calculate_statistics():
    df = pd.DataFrame({...})  # Real pandas
    stats = analyzer.calculate_statistics(df)
    assert stats.loc['kernel1', 'latency_us_mean'] == 154.5
```

#### ❌ Over-Abstracting Thin Wrappers
```python
# BAD: DI for simple subprocess wrapper
class BuildCommand:
    def __init__(self, process_executor: ProcessExecutor):
        self.process = process_executor

    def execute(self, args):
        # Just calls make!
        return self.process.run(['make', 'all'])
```

```python
# GOOD: Integration test with real subprocess
def test_build_command():
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = build.execute(args)
        assert result == 0
```

#### ❌ Testing Coverage Instead of Behavior
```python
# BAD: Testing mock interactions (fragile, no value)
def test_runner_calls_filesystem():
    mock_fs = MagicMock()
    runner = HarnessRunner(filesystem=mock_fs, ...)
    runner.run(...)
    mock_fs.exists.assert_called_once_with(...)  # Tests mock, not behavior!
```

```python
# GOOD: Testing actual behavior
def test_runner_fails_if_binary_missing():
    fs = create_mock_filesystem({})  # No harness binary
    runner = HarnessRunner(filesystem=fs, ...)
    result = runner.run(...)
    assert result is None  # Tests actual failure behavior
```

### ROI-Based Testing Decisions

**High ROI (Full DI + Many Unit Tests):**
- Cross-platform system configuration checker ✅
- Multi-kernel orchestration logic ✅
- Complex state machines ✅
- Algorithm implementations ✅

**Medium ROI (Minimal DI + Balanced Tests):**
- Data processing pipelines ⚖️
- Configuration management ⚖️
- Telemetry analysis ⚖️

**Low ROI (Integration Tests Only):**
- Thin subprocess wrappers ❌
- CLI argument parsers ❌
- Simple CRUD operations ❌

**Negative ROI (Never Do This):**
- Mocking deterministic libraries (pandas, numpy, matplotlib) 🚫
- Mocking standard library (json, yaml) 🚫
- Pixel-by-pixel plot validation 🚫

### Test Metrics (CRIT-004 Completion)

**After completing CRIT-004 (2025-11-18):**
- **Unit tests:** 80 (runner: 28, analyzer: 22, check_system: 30)
- **Integration tests:** 40 (runner: 10, analyzer: 10, check_system: 5, CLI: 25)
- **Total:** 120 Python tests
- **Coverage:** >90% for refactored modules
- **Pass rate:** 100%

**Philosophy wins:**
- Avoided ~50 low-value unit tests for thin wrappers
- Focused effort on high-complexity modules
- Faster test suite (integration tests run in 5-10s vs 90s+ for full pipeline)
- Better coverage of actual behavior vs mock interactions

### Industry Alignment

This pragmatic approach aligns with industry best practices:
- **Django:** Thin view wrappers use integration tests, complex business logic uses unit tests
- **Rails:** Controller tests are integration tests, model logic is unit tested
- **Kubernetes CLI:** kubectl commands tested via integration, complex controllers use unit tests

**Key insight:** Test the thing, not the mock. Integration tests that verify actual behavior are better than unit tests that verify mock interactions.

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

#### test_signal_handler - Graceful Shutdown
**Location:** `tests/test_signal_handler.c`

Tests the signal handler module's graceful shutdown behavior:
- Initial state verification (shutdown flag starts at 0)
- SIGINT handling (Ctrl+C sets shutdown flag)
- SIGTERM handling (shutdown flag set on termination signal)
- Multiple signal deliveries (idempotent flag setting)
- Handler installation success
- Ignored signals (SIGUSR1 doesn't affect shutdown flag)

**Run:**
```bash
make -C tests test-signal-handler
```

**Coverage:**
- POSIX signal handling correctness
- Async-signal-safe flag operations
- Process isolation via fork() for test independence
- Signal handler installation without crashes

**Design notes:**
- Tests use fork() to isolate global shutdown flag between test cases
- Once set, the shutdown flag cannot be reset (by design)
- Validates graceful shutdown that prevents orphaned processes and data loss

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
- Kernel name extraction from paths

**Run:**
```bash
python3 tests/test_cli.py
```

**Coverage:**
- CLI entry points functional
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

**Note:** This includes signal handler tests. The following must be run separately:
- `test-clock-resolution` - Timing infrastructure validation
- `test-kernel-accuracy` - Numerical validation against oracles

### Individual Test Suites
```bash
make -C tests test-replayer
make -C tests test-scheduler
make -C tests test-kernel-registry
make -C tests test-signal-handler
make -C tests test-kernel-accuracy
make -C tests test-clock-resolution
python3 tests/test_cli.py
```

### Kernel Validation
```bash
# Via CLI wrapper (recommended)
cortex validate --kernel notch_iir
cortex validate --kernel bandpass_fir --verbose

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
- [ ] Kernel validation passes: `cortex validate --kernel {name}` (if applicable)
- [ ] Build succeeds on macOS and Linux
- [ ] No compiler warnings with `-Wall -Wextra`
- [ ] New functionality includes tests
- [ ] Tests are documented (comments explaining what's being tested)

## Coverage Expectations

### Core Modules
- **Replayer:** Unit tests for timing, chunking, EOF handling
- **Scheduler:** Unit tests for windowing, buffering, dispatch
- **Signal Handler:** Unit tests for graceful shutdown on SIGINT/SIGTERM
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
- Converted from EDF using `dataset conversion utilities (see docs/guides/adding-datasets.md)`

**Location:** `primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32`

**Used by:**
- `test_kernel_accuracy` - Real EEG data for validation
- Full harness runs via `cortex run`

**Conversion:**
```bash
python3 dataset conversion utilities (see docs/guides/adding-datasets.md) \
    primitives/datasets/v1/physionet-motor-imagery/edf/S001R03.edf \
    primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32
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
- Run `make test` and `cortex validate` for all kernels
- Fail on compiler warnings
- Upload test logs as artifacts

## Related Documentation

- **Benchmarking Methodology:** [benchmarking-methodology.md](benchmarking-methodology.md) - HIL vs on-device measurement philosophy
- **Plugin Interface:** [../reference/plugin-interface.md](../reference/plugin-interface.md) - ABI specification for kernels
- **Adding Kernels:** [../guides/adding-kernels.md](../guides/adding-kernels.md) - Kernel development workflow including testing
- **Contributing:** [../../CONTRIBUTING.md](../../CONTRIBUTING.md) - PR requirements and code review process
