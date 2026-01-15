# GitHub Copilot Code Review Instructions for CORTEX

These instructions guide Copilot's automated code reviews for the CORTEX real-time BCI benchmarking ecosystem.

---

## Critical Constraints - Reject PRs That Violate These

### 1. ABI Stability (v3 - Current)
- **REQUIRED**: Core 3 functions for all kernels: `cortex_init()`, `cortex_process()`, `cortex_teardown()`
- **OPTIONAL**: Trainable kernels may export `cortex_calibrate()` for offline batch training
- **REJECT**: Any changes to function signatures, parameter lists, or return types
- **REJECT**: Renaming existing ABI functions
- **REJECT**: Changes to `cortex_plugin.h` that break backward compatibility
- **VERIFY**: v3 kernels check `config->abi_version == 3`, v2 kernels check `== 2`
- **VERIFY**: Harness detects kernel version and sends correct `abi_version` (v2 backward compatible)

### 2. Hermetic Kernel Execution
- **REJECT**: Heap allocation (`malloc`, `calloc`, `realloc`) inside `cortex_process()`
- **REJECT**: File I/O, network calls, or blocking syscalls during processing
- **REJECT**: External dependencies in `cortex_process()` (must be self-contained)
- **ALLOW**: State allocation only in `cortex_init()`, freed in `cortex_teardown()`

### 3. Oracle Validation Before Benchmarking
- **REJECT**: Performance claims without oracle validation passing
- **REQUIRE**: All new kernels have Python/SciPy reference implementation
- **REQUIRE**: Numerical error within tolerance (1e-5 for float32)
- **VERIFY**: `cortex validate` passes before benchmarking

### 4. Primitives Immutability
- **REJECT**: Modifications to `primitives/kernels/v1/**/*`
- **REJECT**: Modifications to `primitives/datasets/v1/**/*`
- **REQUIRE**: Create new version directories (e.g., `v2/`) for changes
- **ALLOW**: Adding new primitives in new version directories

### 5. Sequential Execution Only
- **REJECT**: Parallel kernel execution or multi-threading during benchmarks
- **REJECT**: Changes that break measurement isolation
- **VERIFY**: Kernels run one-at-a-time with dedicated resources

---

## Code Standards - Flag These Issues

### Naming Conventions
- ✅ **Functions**: `snake_case` with `cortex_` prefix
  - Example: `cortex_init()`, `cortex_mul_size_overflow()`
  - ❌ Reject: `camelCase`, `PascalCase`, missing prefix
- ✅ **Types**: `snake_case` with `_t` suffix
  - Example: `cortex_init_result_t`, `kernel_config_t`
  - ❌ Reject: `typedef struct Foo` without `_t`
- ✅ **Macros**: `SCREAMING_SNAKE_CASE` with `CORTEX_` prefix
  - Example: `CORTEX_ABI_VERSION`, `CORTEX_MAX_CHANNELS`
  - ❌ Reject: lowercase macros, missing prefix

### Memory Safety
- ✅ **REQUIRE**: Use `cortex_mul_size_overflow()` for size calculations before allocation
  - Example: `if (cortex_mul_size_overflow(n_channels, sizeof(float), &size)) { return error; }`
  - ❌ Reject: Direct multiplication `malloc(n * sizeof(float))` without overflow check
- ✅ **REQUIRE**: Check all allocation results for NULL before use
- ✅ **REQUIRE**: Free all allocated memory in error paths
- ✅ **VERIFY**: No memory leaks (all `malloc` has matching `free`)

### Error Handling
- ✅ **Functions return status codes**, not void (unless trivial)
  - Example: `int cortex_init(...)` returns 0 on success, -1 on error
- ✅ **Check return values** of all system calls and library functions
- ✅ **Propagate errors** up the call stack, don't silently ignore
- ✅ **Log errors** with context before returning error codes

### Platform Compatibility
- ✅ **macOS**: Use `#ifdef __APPLE__` for macOS-specific code
- ✅ **Library extensions**: Handle `.dylib` (macOS) vs `.so` (Linux) via `$(LIBEXT)` in Makefiles
- ✅ **RT scheduling**: Accept graceful degradation on macOS (logs warning, continues)
- ❌ **Reject**: Hardcoded `.so` or `.dylib` extensions
- ❌ **Reject**: Linux-only syscalls without platform guards

### File Naming and Structure
- ✅ **Kernel implementations**: `{kernel_name}.c` in `primitives/kernels/v1/{kernel}@{dtype}/`
  - Example: `car.c` in `car@f32/`
- ✅ **Tests**: `test_{component}.c` in `tests/`
  - Example: `test_scheduler.c`, `test_telemetry.c`
- ✅ **Headers**: Single-responsibility, minimal dependencies
- ❌ **Reject**: Monolithic files >1000 lines (suggest decomposition)

---

## CORTEX-Specific Patterns

### Makefile Conventions
- ✅ **REQUIRE**: Platform detection for library extensions
  ```make
  UNAME_S := $(shell uname -s)
  ifeq ($(UNAME_S),Darwin)
      LIBEXT = .dylib
      SOFLAG = -dynamiclib
  else
      LIBEXT = .so
      SOFLAG = -shared
  endif
  ```
- ✅ **REQUIRE**: Use `CORTEX_PRIMITIVE_INCLUDES` variable for include paths
- ✅ **REQUIRE**: `.PHONY` targets for `all`, `clean`, `test`
- ❌ **Reject**: Hardcoded paths that break standalone builds

### Configuration (YAML)
- ✅ **Direct dataset paths**: Specify `.float32` files directly
  - Example: `path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"`
- ✅ **Parameter format**: Use `key=value` pairs in `kernel_params` string
  - Example: `kernel_params: "f0_hz=60.0 Q=30.0"`
- ❌ **Reject**: Nested YAML objects for parameters (must be flat string)

### Test Requirements
- ✅ **REQUIRE**: All new subsystems have unit tests in `tests/`
- ✅ **REQUIRE**: Tests use `make tests` target (plural, not `test`)
- ✅ **VERIFY**: All tests pass before merging (`make tests` returns 0)
- ✅ **VERIFY**: No `/tmp/cortex_test_*` files leaked after test completion

### Documentation
- ✅ **README.md** in each primitive directory (`primitives/kernels/v1/{kernel}/`)
- ✅ **Commit messages**: Follow conventional commits format
  - `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- ✅ **Code comments**: Explain **why**, not **what** (code is self-documenting)
- ❌ **Reject**: Proactive creation of documentation files without explicit request

---

## Performance and Measurement

### Telemetry Standards
- ✅ **Report distributions**: P50, P95, P99 (NOT just arithmetic mean)
- ✅ **Track deadline misses**: Count and percentage where `end_ts > deadline_ts`
- ✅ **Output formats**: NDJSON for streaming, CSV for legacy compatibility
- ❌ **Reject**: Reporting only average latency (insufficient for RT analysis)

### Measurement Validity
- ✅ **VERIFY**: Idle systems use active load (`stress-ng` or equivalent)
- ✅ **VERIFY**: Linux governor set to `performance` (not `schedutil` or `powersave`)
- ✅ **VERIFY**: No parallel workloads during benchmarking
- ⚠️ **FLAG**: Changes that could introduce measurement bias or non-determinism

---

## Common Mistakes to Flag

1. **Function naming**: Flag `cortex_cleanup()` → Correct is `cortex_teardown()`
2. **ABI version**: Flag version 1 or 2 references → Current is version 3 (v2 backward compatible)
3. **Test command**: Flag `make test` → Correct is `make tests` (plural)
4. **Header location**: Flag `plugin_abi.h` → Correct is `cortex_plugin.h`
5. **Directory naming**: Flag `run-configs/` → Correct is `primitives/configs/`
6. **Kernel count**: Flag claims of "4 kernels" → Correct is 8 (car, notch_iir, bandpass_fir, goertzel, welch_psd, ica, csp, noop)
7. **Parallel execution**: Flag kernel parallelization → Must be sequential
8. **Primitive modification**: Flag edits to `v1/` → Must create `v2/`
9. **Benchmark-first**: Flag performance work without oracle validation
10. **Mean latency**: Flag arithmetic mean reporting → Use P50/P95/P99

---

## Review Checklist

For each PR, verify:

- [ ] No ABI changes unless explicitly versioned
- [ ] No heap allocation in `cortex_process()` hot path
- [ ] Memory safety: overflow checks, NULL checks, proper cleanup
- [ ] Error handling: all return codes checked and propagated
- [ ] Platform compatibility: macOS and Linux both supported
- [ ] Naming conventions: snake_case, cortex_ prefix, _t suffix for types
- [ ] Tests: `make tests` passes, new functionality has test coverage
- [ ] Primitives immutability: no edits to `v1/` directories
- [ ] Sequential execution: no parallel kernel benchmarking
- [ ] Documentation: README updated if public API changed
- [ ] Commit messages: conventional format with clear scope
- [ ] No security issues: command injection, buffer overflows, format strings
- [ ] No OWASP Top 10 vulnerabilities (XSS, SQLi, etc.)

---

## Severity Levels

**CRITICAL** (Block merge):
- ABI breaking changes without version bump
- Heap allocation in `cortex_process()`
- Memory safety violations (overflow, use-after-free, buffer overrun)
- Primitive modification in versioned directories (`v1/`)
- Security vulnerabilities

**HIGH** (Request fixes):
- Missing error handling
- Platform-specific code without guards
- Test failures
- Memory leaks
- Naming convention violations

**MEDIUM** (Suggest improvements):
- Missing documentation
- Inefficient algorithms (with proof)
- Code duplication
- Inconsistent style

**LOW** (Optional):
- Minor style preferences
- Cosmetic changes
- Optimization opportunities without measurement data

---

## Example Reviews

### ✅ Good Review Comment
```
❌ **CRITICAL: Memory safety violation (line 42)**

`malloc(n_channels * sizeof(float))` performs unchecked multiplication that could overflow.

**Fix**: Use `cortex_mul_size_overflow()` before allocation:
```c
size_t size;
if (cortex_mul_size_overflow(n_channels, sizeof(float), &size)) {
    return -1;  // Overflow detected
}
float *buffer = malloc(size);
```

**Reference**: `src/engine/harness/util/util.c:15`
```

### ❌ Bad Review Comment
```
This code looks a bit messy. Consider refactoring for readability.
```
(Too vague, no actionable guidance, no severity level)

---

## When to Approve

**Approve if:**
- All CRITICAL and HIGH issues resolved
- Tests pass (`make tests` returns 0)
- Oracle validation passes (if kernel changes)
- No ABI violations
- No security vulnerabilities
- Code follows CORTEX conventions

**Request changes if:**
- Any CRITICAL issue present
- Tests failing
- Memory safety concerns
- ABI compatibility broken

**Comment (no block) if:**
- Only MEDIUM/LOW issues
- Stylistic suggestions
- Optional optimizations

---

## Additional Context

- **Project velocity**: CORTEX ships features rapidly (19 commits/day observed)
- **Measurement rigor**: Scientifically valid benchmarking is the primary goal
- **Simplicity over cleverness**: Follow Lampson's STEADY principles
- **Platform support**: macOS (arm64, x86_64) and Linux (x86_64, arm64)
- **Current kernels**: car, notch_iir, bandpass_fir, goertzel, welch_psd, noop, ica (7 total: 6 v2, 1 v3 trainable)
- **Test coverage**: 21+ C unit tests across 7 suites

For full context, reference `/Users/westonvoglesonger/Projects/CORTEX/CLAUDE.md` in the repository.
