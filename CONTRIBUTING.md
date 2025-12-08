# Contributing to CORTEX

Thank you for your interest in contributing to CORTEX! This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful, collaborative, and professional. Focus on technical merit and constructive feedback.

## Repository Structure

CORTEX follows a clean AWS-inspired structure:

```
CORTEX/
├── primitives/        # Computational kernels and configurations
│   ├── kernels/       # Kernel implementations organized by version
│   │   └── v1/        # Version 1 kernels (bandpass_fir@f32/, car@f32/, etc.)
│   ├── datasets/      # Dataset primitives (versioned EEG recordings)
│   │   └── v1/        # Version 1 datasets
│   │       ├── physionet-motor-imagery/ # PhysioNet Motor Imagery dataset
│   │       └── fake/  # Synthetic test datasets
│   └── configs/       # Kernel configuration files (YAML)
├── src/               # All source code
│   ├── cortex/        # Python CLI application
│   │   ├── commands/  # CLI command implementations
│   │   ├── core/      # Core business logic
│   │   ├── ui/        # User interface components
│   │   └── utils/     # Utility functions
│   └── engine/        # C execution engine
│       ├── harness/   # Benchmark harness implementation
│       ├── include/   # C header files
│       ├── replayer/  # Dataset replay engine
│       └── scheduler/ # Window scheduler
├── tests/             # Test suites (unit and integration)
│   ├── unit/          # Python unit tests
│   └── integration/   # Python integration tests
├── docs/              # Documentation
│   ├── getting-started/  # Quick start guides
│   ├── guides/        # How-to guides
│   ├── reference/     # API and reference docs
│   ├── architecture/  # Design decisions (ADRs)
│   └── development/   # Development roadmap and planning
├── results/           # Benchmark results and visualizations
└── build/             # Build artifacts (generated)
```

Understanding this structure is essential for contributing effectively.

### Directory Details

**primitives/**
- Houses all computational kernels and their configurations
- `primitives/kernels/v1/` contains versioned kernel implementations:
  - `bandpass_fir@f32/` - FIR bandpass filter
  - `car@f32/` - Common Average Reference
  - `goertzel@f32/` - Goertzel algorithm for frequency detection
  - `notch_iir@f32/` - IIR notch filter
  - `welch_psd@f32/` - Welch power spectral density
- `primitives/configs/cortex.yaml` configures which kernels to load
- Each kernel directory contains: `spec.yaml`, `README.md`, `oracle.py`, `{name}.c`, `Makefile`

**primitives/datasets/**
- `v1/physionet-motor-imagery/converted/` stores the PhysioNet Motor Imagery dataset in float32 binary format
- `v1/fake/` contains synthetic test datasets for development
- Each dataset includes `spec.yaml` metadata file and `converted/*.float32` binary files
- Dataset binary files are tracked in git (small synthetic datasets) or gitignored (large real datasets)

**src/**
- All source code organized by component
- `cortex/` is the Python CLI application with submodules:
  - `commands/` - Command implementations (run, analyze, pipeline, etc.)
  - `core/` - Core logic (runner, analyzer)
  - `ui/` - User interface components (spinners, progress bars)
  - `utils/` - Utility functions
- `engine/` contains the C execution engine:
  - `harness/` - Main benchmark harness
  - `include/` - C header files (plugin ABI, types)
  - `replayer/` - Dataset replay engine
  - `scheduler/` - Window scheduling logic

**tests/**
- Test suites at repository root (not in src/)
- `unit/` contains Python unit tests
- `integration/` contains Python integration tests
- C test files are at top level: `test_replayer.c`, `test_scheduler.c`, etc.
- Tests run in CI on every push/PR

**docs/**
- Comprehensive documentation organized by purpose:
  - `getting-started/` - Installation and quick start
  - `guides/` - How-to guides for common tasks
  - `reference/` - API documentation and specifications
  - `architecture/` - ADRs (Architecture Decision Records)
  - `development/` - Roadmap, planning, future enhancements
- Always update relevant docs when making changes

**results/**
- Benchmark results, visualizations, and analysis outputs
- Generated during `cortex run` and `cortex analyze` commands
- Contains timestamped run directories with telemetry and plots

## Development Setup

Before contributing, set up your development environment:

```bash
# Clone the repository
git clone https://github.com/WestonVoglesonger/CORTEX.git
cd CORTEX

# Install Python package in editable mode with dev dependencies
pip install -e .[dev]

# Build C components
make clean && make

# Verify installation
cortex --version
cortex validate
```

**Key directories**:
- `src/cortex/` - Python CLI application code
- `src/engine/harness/` - C benchmark harness
- `primitives/kernels/v1/` - Kernel implementations
- `primitives/datasets/v1/` - Dataset primitives
- `primitives/configs/` - Configuration files
- `tests/` - Test suites (Python and C)

## How to Contribute

### Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Provide clear reproduction steps for bugs
- Include system information (OS, compiler version, etc.)

### Proposing Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes following our coding standards
4. Write or update tests as appropriate
5. Update documentation
6. Submit a pull request

## Coding Standards

### C Code Style

- **Language**: C11 standard
- **Naming**:
  - Functions: `snake_case` with `cortex_` prefix for public APIs
  - Variables: `snake_case`
  - Constants: `UPPER_SNAKE_CASE`
  - Structs: `snake_case` with `_t` suffix (e.g., `cortex_plugin_config_t`)
- **Formatting**:
  - 4-space indentation (no tabs)
  - K&R brace style
  - 80-character line limit (soft guideline)
- **Memory Management**:
  - Explicit allocation/deallocation, no hidden allocations
  - Check all allocation returns for NULL
  - Free resources in reverse order of allocation
- **Error Handling**:
  - Return codes or NULL pointers (no exceptions)
  - Document error conditions in function comments

### Python Code Style

- Follow PEP 8
- Use type hints for function signatures
- Document functions with docstrings

### Documentation

- Update relevant documentation with code changes
- Use GitHub-flavored Markdown
- Include code examples where appropriate
- Keep docs/ organized by category (see docs/README.md)

## Developing Kernels

To add a new kernel implementation:

1. **Create directory structure**:
   ```bash
   mkdir -p primitives/kernels/v1/{name}@f32
   cd primitives/kernels/v1/{name}@f32
   ```

2. **Required files**:
   - `spec.yaml` - Machine-readable specification
   - `README.md` - Full documentation with equations
   - `oracle.py` - Python reference implementation
   - `{name}.c` - C implementation
   - `Makefile` - Build script

3. **Makefile template**:
   ```makefile
   CC = cc
   CFLAGS = -Wall -Wextra -O2 -g -fPIC -I../../../../src/engine/include

   UNAME_S := $(shell uname -s)
   ifeq ($(UNAME_S),Darwin)
       SOFLAG = -dynamiclib
       LIBEXT = .dylib
   else
       SOFLAG = -shared
       LIBEXT = .so
   endif

   KERNEL_NAME = $(shell basename $(CURDIR) | sed 's/@.*//')
   PLUGIN_SRC = $(KERNEL_NAME).c
   PLUGIN_LIB = lib$(KERNEL_NAME)$(LIBEXT)

   all: $(PLUGIN_LIB)

   $(PLUGIN_LIB): $(PLUGIN_SRC)
   	$(CC) $(CFLAGS) $(SOFLAG) -o $@ $< -lm

   clean:
   	rm -f $(PLUGIN_LIB) *.o
   ```

   **Note**: The include path `-I../../../../src/engine/include` points to the C headers from the kernel directory.

4. **Implementation requirements**:
   - Implement `cortex_init()`, `cortex_process()`, `cortex_teardown()`
   - Check `config->abi_version == CORTEX_ABI_VERSION`
   - Allocate persistent state in `init()`, free in `teardown()`
   - **No allocations in `process()`** - all memory must be pre-allocated
   - Handle NaNs gracefully (see docs/guides/adding-kernels.md)

5. **Register in configuration**:
   Add your kernel to `primitives/configs/cortex.yaml`:
   ```yaml
   plugins:
     - name: "{name}"
       status: ready
       spec_uri: "primitives/kernels/v1/{name}@f32"
       spec_version: "1.0.0"
   ```

6. **Validation**:
   ```bash
   # Build your kernel
   make

   # Test oracle implementation
   python oracle.py

   # Validate C implementation against oracle
   cortex validate --kernel {name} --verbose
   ```

7. **Testing**:
   ```bash
   # Run kernel in harness
   cortex run --kernel {name} --duration 30 --run-name test-{name}

   # Analyze results
   cortex analyze --run-name test-{name}
   ```

See [docs/guides/adding-kernels.md](docs/guides/adding-kernels.md) for comprehensive guide.

## Plugin ABI Compliance

- Always check ABI version in `cortex_init()`
- Return `{NULL, 0, 0}` on initialization errors
- Maintain thread safety (no concurrent calls on same handle)
- Document state persistence behavior
- See [docs/reference/plugin-interface.md](docs/reference/plugin-interface.md)

## Testing Requirements

### Before Submitting PRs

- [ ] All C unit tests pass: `cd tests && make test`
- [ ] All Python tests pass: `pytest tests/`
- [ ] Kernel accuracy tests pass: `cortex validate`
- [ ] Build succeeds on both macOS and Linux
- [ ] No compiler warnings with `-Wall -Wextra`
- [ ] Documentation updated for changes
- [ ] CI checks pass (tests run automatically on push/PR)

### Test Coverage

- C unit tests for engine components (replayer, scheduler, kernel registry)
- Python unit tests for CLI and core logic (see `tests/unit/`)
- Python integration tests for end-to-end workflows (see `tests/integration/`)
- Numerical validation against oracles (scipy, MNE references)
- Cross-platform builds (macOS .dylib + Linux .so)

### Running Tests

```bash
# Run all C unit tests
cd tests && make test

# Run all Python tests
pytest tests/

# Run specific Python test suites
pytest tests/unit/
pytest tests/integration/

# Run specific test files
pytest tests/unit/test_analyzer.py
pytest tests/integration/test_run_command.py

# Validate all kernels against oracles
cortex validate

# Validate specific kernel
cortex validate --kernel {name} --verbose
```

## Pull Request Process

1. **Update documentation**: README and docs/ as needed
2. **Self-review**: Check your own diff for issues
3. **Descriptive PR title**: Use conventional commit format
   - `feat:` for new features
   - `fix:` for bug fixes
   - `docs:` for documentation
   - `refactor:` for code refactoring
   - `test:` for test additions
4. **PR description**: Explain what, why, and how
5. **Link issues**: Reference related GitHub issues
6. **Pass CI**: Ensure all checks pass
7. **Responsive**: Address review feedback promptly

## Commit Message Guidelines

```
<type>: <subject>

<body>

<footer>
```

**Type**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting changes
- `refactor`: Code restructuring
- `perf`: Performance improvement
- `test`: Adding tests
- `chore`: Build process, tooling

**Subject**: Imperative mood, lowercase, no period, < 50 chars

**Body** (optional): Explain what and why, not how

**Footer** (optional): References to issues, breaking changes

Example:
```
feat: Add Welch PSD kernel implementation

Implements power spectral density calculation using Welch's method
with Hanning window and 50% overlap. Validated against SciPy with
rtol=1e-5, atol=1e-6.

Closes #42
```

## Development Workflow

```bash
# Build everything (harness + plugins)
make clean && make

# Build only plugins
make plugins

# Build only harness
make harness

# Run C tests
cd tests && make test

# Run Python tests
pytest tests/

# Run specific Python test suites
pytest tests/unit/test_analyzer.py -v
pytest tests/integration/test_run_command.py -v

# Validate kernels against oracles
cortex validate

# Run benchmarks (with custom name)
cortex run --all --duration 60 --run-name test-run

# Analyze results
cortex analyze --run-name test-run

# Full pipeline (auto-named with timestamp)
cortex pipeline
```

**Common workflows**:

1. **Adding a new kernel**: Follow the "Developing Kernels" section above, then validate with `cortex validate --kernel {name}`

2. **Adding datasets**: See `docs/guides/adding-datasets.md` for creating new dataset primitives in `primitives/datasets/v1/`

3. **Modifying the C engine**: Edit code in `src/engine/harness/`, rebuild with `make harness`, and run tests

4. **Updating the CLI**: Edit Python code in `src/cortex/`, changes are immediately available in editable install mode (`pip install -e .`)

5. **Adding tests**: Add C tests to `tests/test_*.c`, Python unit tests to `tests/unit/`, integration tests to `tests/integration/`

## Questions?

- Check [docs/README.md](docs/README.md) for complete documentation index
- Review existing kernels for examples
- Open a GitHub Discussion for questions
- See [docs/guides/troubleshooting.md](docs/guides/troubleshooting.md) for common issues

## License

By contributing, you agree that your contributions will be licensed under the project's MIT License.
