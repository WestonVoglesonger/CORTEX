# CORTEX Testing System - 4-Pillar Architecture

This directory contains all tests for the CORTEX project, organized by architectural pillar.

## Directory Structure

```
tests/
├── engine/       - Engine pillar (scheduler, telemetry, replayer, harness)
├── adapter/      - Adapter SDK pillar (protocol, transport, device communication)
├── kernel/       - Kernel SDK pillar (plugin interface examples)
├── cli/          - CLI pillar (Python orchestration and commands)
└── fixtures/     - Shared test utilities and mock implementations
```

Each pillar has its own Makefile with auto-discovery and build/ subdirectory for compiled artifacts.

## Quick Start

```bash
# Build all C test binaries
make all

# Run all test suites (C + Python)
make tests

# Run individual pillar tests
make test-engine    # Engine pillar C tests
make test-adapter   # Adapter SDK C tests
make test-kernel    # Kernel SDK C examples
make test-cli       # CLI Python tests

# Clean all build artifacts
make clean

# Show all available targets
make help
```

## Engine Pillar Tests

C tests for core engine components (scheduler, replayer, telemetry, harness).

**Location:** `tests/engine/`

**Run:** `make test-engine` or `cd engine && make tests`

### Test Coverage

#### Unit Tests
- **test_replayer** - Dataset streaming at real-time cadence
  - ✅ Hop-sized chunks (H samples, not W)
  - ✅ Correct timing cadence (H/Fs seconds per chunk)
  - ✅ EOF handling and rewind
  - ✅ Various configurations (different H, Fs, C)
  - ✅ Data continuity (samples in correct order)

- **test_scheduler** - Window formation and plugin dispatch
  - ✅ Configuration validation
  - ✅ Integer overflow protection
  - ✅ Window formation from hop-sized chunks
  - ✅ Overlapping windows (W-H sample retention)
  - ✅ Buffer management (various chunk sizes)
  - ✅ Multiple devices (sequential execution)
  - ✅ Warmup period handling
  - ✅ Flush functionality
  - ✅ Sequential scheduler execution
  - ✅ Data continuity through scheduler

- **test_telemetry** - Timing and metrics collection
  - ✅ Buffer initialization and growth
  - ✅ Overflow protection
  - ✅ CSV output format
  - ✅ NDJSON output format

- **test_signal_handler** - Graceful shutdown handling
  - ✅ SIGINT/SIGTERM handling
  - ✅ Shutdown flag setting
  - ✅ Handler installation

- **test_clock_resolution** - Timing accuracy validation
  - ✅ Clock resolution measurement
  - ✅ Timing overhead analysis
  - ✅ Simulated latency measurement

- **test_kernel_registry** - Plugin discovery and validation
  - ✅ Kernel structure validation
  - ✅ Required field checks
  - ✅ Oracle executability

- **test_param_accessor** - Kernel parameter parsing
  - ✅ Float parsing (YAML and URL styles)
  - ✅ Integer parsing
  - ✅ String parsing
  - ✅ Boolean parsing
  - ✅ Whitespace handling
  - ✅ Scientific notation
  - ✅ Error handling

- **test_device_comm** - Adapter lifecycle and communication
  - ✅ Adapter spawn (local transport, cleanup, spawn failure)
  - ✅ Handshake sequence (HELLO→CONFIG→ACK, output dimensions)
  - ✅ Transport URI parsing (local://, NULL default, empty string)
  - ⏸️ SKIP: Window execution tests (4 tests require integration debugging)

#### Integration Tests
- **test_config_overrides** - Runtime configuration overrides
  - ✅ Kernel filter (single, multiple, whitespace)
  - ✅ Not found handling
  - ✅ Zero result handling

## Adapter SDK Pillar Tests

C tests for adapter SDK (protocol, transport, device communication).

**Location:** `tests/adapter/`

**Run:** `make test-adapter` or `cd adapter && make tests`

### Test Coverage

#### Unit Tests
- **test_protocol** - Protocol layer robustness
  - ✅ Frame fragmentation handling
  - ✅ Timeout behavior
  - ✅ Window chunking
  - ✅ Sequence validation
  - ✅ CRC corruption detection
  - ✅ Large window support

- **test_protocol_loopback** - End-to-end protocol validation
  - ✅ HELLO frame send/receive via socketpair
  - ✅ Frame type validation
  - ✅ Payload parsing

#### Integration Tests
- **test_adapter_smoke** - Basic adapter initialization
  - ⏸️ SKIP: Requires native adapter binary

- **test_adapter_all_kernels** - All 6 kernels through adapter
  - ⏸️ SKIP: Requires native adapter binary

- **test_socketpair_hello** - Minimal HELLO exchange
  - ⏸️ SKIP: Requires native adapter binary

## Kernel SDK Pillar Tests

C tests and examples for the Kernel SDK (plugin interface and calibration state I/O).

**Location:** `tests/kernel/`

**Run:** `make test-kernel` or `cd kernel && make tests`

### Unit Tests

- **test_state_io** - Calibration state I/O (ABI v3)
  - ✅ Basic save/load (100B, 16KB, 1MB)
  - ✅ Corrupt file handling (bad magic, wrong ABI, truncated header/payload, empty, not found)
  - ✅ Security (path traversal, max size enforcement)
  - ✅ Endianness (little-endian write/read verification)
  - ✅ State version evolution (v1/v2 compatibility)

### Examples

- **hello_kernel** - Minimal ABI v3 implementation
  - ✅ Demonstrates cortex_init() with ABI validation
  - ✅ Demonstrates cortex_process() hermetic processing
  - ✅ Demonstrates cortex_teardown() cleanup
  - ✅ Identity function (output = input)
  - ✅ Built as standalone executable with embedded test harness

## CLI Pillar Tests

Python tests for CLI commands and orchestration logic.

**Location:** `tests/cli/`

**Run:** `make test-cli` or `pytest tests/cli/`

**Prerequisites:** `pip install -e .` (install cortex package in development mode)

### Test Coverage

#### Unit Tests
- **test_analyzer.py** - Results analysis and report generation
- **test_runner.py** - Benchmark orchestration
- **commands/test_check_system.py** - System validation command

#### Integration Tests
- **test_run_command.py** - `cortex run` end-to-end
- **test_pipeline_command.py** - `cortex pipeline` end-to-end
- **test_analyze_command.py** - `cortex analyze` end-to-end
- **test_check_system_command.py** - `cortex check-system` end-to-end
- **test_cli_commands.py** - General CLI behavior

## Fixtures

Shared test utilities and mock implementations.

**Location:** `tests/fixtures/`

- **common/** - Shared C headers (test_common.h)
- **mock_adapter/** - Controllable test adapter for protocol testing

## Development Workflow

### Running All Tests
```bash
make tests
```

This runs:
1. Engine C tests
2. Adapter C tests
3. Kernel C examples
4. CLI Python tests

### Running Specific Pillars
```bash
make test-engine    # Just engine tests
make test-adapter   # Just adapter tests
make test-kernel    # Just kernel examples
make test-cli       # Just CLI tests (requires pip install -e .)
```

### Building Without Running
```bash
make all            # Build all C tests
cd engine && make   # Build just engine tests
cd adapter && make  # Build just adapter tests
cd kernel && make   # Build just kernel examples
```

### Cleaning Build Artifacts
```bash
make clean          # Clean all pillars
cd engine && make clean   # Clean just engine
```

## Test Status Legend

- ✅ **PASS** - Test passes successfully
- ⏸️ **SKIP** - Test skipped (dependency missing or by design)
- ❌ **FAIL** - Test fails (should not happen in main branch)

## Adding New Tests

### C Tests (Engine, Adapter, Kernel)

1. Add test file to appropriate directory:
   - Engine: `tests/engine/unit/test_*.c` or `tests/engine/integration/test_*.c`
   - Adapter: `tests/adapter/unit/test_*.c` or `tests/adapter/integration/test_*.c`
   - Kernel: `tests/kernel/examples/*.c`

2. Add build rule to pillar Makefile if needed (auto-discovery handles most cases)

3. Run `make clean && make all && make tests` to verify

### Python Tests (CLI)

1. Add test file to appropriate directory:
   - Unit: `tests/cli/unit/test_*.py`
   - Integration: `tests/cli/integration/test_*.py`

2. Ensure cortex package is installed: `pip install -e .`

3. Run `pytest tests/cli/` to verify

## Architecture Alignment

This test structure mirrors the 4 pillars of CORTEX architecture:

1. **Engine** - Core runtime (scheduler, replayer, telemetry, harness)
2. **CLI** - User-facing commands and orchestration
3. **Adapter SDK** - Device abstraction layer (protocol, transport)
4. **Kernel SDK** - Plugin interface (signal processing implementations)

Each pillar is independently testable, maintainable, and can evolve without affecting others.
