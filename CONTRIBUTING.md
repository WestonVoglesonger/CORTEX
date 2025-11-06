# Contributing to CORTEX

Thank you for your interest in contributing to CORTEX! This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful, collaborative, and professional. Focus on technical merit and constructive feedback.

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
   mkdir -p kernels/v1/{name}@f32
   cd kernels/v1/{name}@f32
   ```

2. **Required files**:
   - `spec.yaml` - Machine-readable specification
   - `README.md` - Full documentation with equations
   - `oracle.py` - Python reference implementation
   - `{name}.c` - C implementation
   - `Makefile` - Build script

3. **Implementation requirements**:
   - Implement `cortex_init()`, `cortex_process()`, `cortex_teardown()`
   - Check `config->abi_version == CORTEX_ABI_VERSION`
   - Allocate persistent state in `init()`, free in `teardown()`
   - **No allocations in `process()`** - all memory must be pre-allocated
   - Handle NaNs gracefully (see docs/reference/kernels.md)

4. **Validation**:
   ```bash
   # Build your kernel
   make
   
   # Test oracle implementation
   python oracle.py
   
   # Validate C implementation against oracle
   ./cortex validate --kernel {name} --verbose
   ```

5. **Testing**:
   ```bash
   # Run kernel in harness
   ./cortex run --kernel {name} --duration 30
   
   # Analyze results
   ./cortex analyze results/batch_{timestamp}
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

- [ ] All unit tests pass: `make tests`
- [ ] Kernel accuracy tests pass: `./cortex validate`
- [ ] Build succeeds on both macOS and Linux
- [ ] No compiler warnings with `-Wall -Wextra`
- [ ] Documentation updated for changes

### Test Coverage

- Unit tests for new components (see tests/)
- Integration tests for end-to-end workflows
- Numerical validation against oracles (within tolerance)
- Cross-platform builds (macOS .dylib + Linux .so)

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
# Build everything
make clean && make

# Run specific tests
make -C tests test-replayer
make -C tests test-scheduler

# Validate kernels
./cortex validate

# Run benchmarks
./cortex run --all --duration 60

# Analyze results
./cortex analyze results/batch_{timestamp}

# Full pipeline
./cortex pipeline
```

## Questions?

- Check [docs/README.md](docs/README.md) for complete documentation index
- Review existing kernels for examples
- Open a GitHub Discussion for questions
- See [docs/guides/troubleshooting.md](docs/guides/troubleshooting.md) for common issues

## License

By contributing, you agree that your contributions will be licensed under the project's MIT License.
