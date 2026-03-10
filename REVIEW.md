# CORTEX Review Rules

Rules for automated PR review agents. This file defines what to check, how to classify findings, and when to block merges. Sections are numbered for cross-referencing from agent prompts.

**Audience**: LLM-based review agents (Claude, Cursor, Codex, Copilot).
**Scope**: Code evaluation only. Development workflow and assistant behavior are governed by CLAUDE.md, not this file.

**Severity Levels** (used throughout):

| Level | Action | Examples |
|-------|--------|---------|
| **CRITICAL** | Block merge | ABI breaks, heap in `cortex_process()`, memory safety, primitive mutation, security holes |
| **HIGH** | Request fixes | Missing error handling, platform guards absent, test failures, memory leaks, naming violations |
| **MEDIUM** | Suggest improvement | Missing docs, code duplication, inefficient algorithms (with evidence), style inconsistency |
| **LOW** | Optional comment | Minor style, cosmetic changes, optimization ideas without measurement data |

---

## Section 1: Sacred Constraints

Six inviolable rules. Any violation is **CRITICAL** and blocks merge unconditionally.

### 1.1 ABI Is Frozen (v3)

The plugin ABI defines exactly four functions. No more, no fewer.

| Function | Required | Purpose |
|----------|----------|---------|
| `cortex_init()` | All kernels | Allocate state, validate config |
| `cortex_process()` | All kernels | Process one window of data |
| `cortex_teardown()` | All kernels | Free state |
| `cortex_calibrate()` | Trainable only | Offline batch training (ICA, CSP) |

**Block if:**
- Function signatures are modified (parameters added/removed/retyped)
- Functions are renamed (e.g., `cortex_cleanup()` instead of `cortex_teardown()`)
- New exported functions are added to the plugin interface
- `cortex_plugin.h` changes break backward compatibility with v2 kernels

### 1.2 Kernels Are Hermetic

`cortex_process()` executes in a zero-dependency sandbox. Everything needed is pre-allocated in `cortex_init()`.

**Block if:**
- `malloc`, `calloc`, `realloc`, or `free` appear inside `cortex_process()`
- File I/O (`fopen`, `fread`, `fprintf`, etc.) appears inside `cortex_process()`
- Network calls or blocking syscalls appear inside `cortex_process()`
- External library calls (beyond standard math) appear inside `cortex_process()`

**Allow:**
- Heap allocation in `cortex_init()` and `cortex_calibrate()`
- Stack-local variables in `cortex_process()`
- Calls to `cortex_param_*` accessors during `cortex_init()` only

### 1.3 Oracle Validation Precedes Measurement

No benchmark result is trustworthy without prior correctness validation against the Python/SciPy reference.

**Block if:**
- PR adds performance claims without evidence of oracle validation passing
- New kernel lacks a Python reference implementation for validation
- Validation tolerances are relaxed without justification (f32: rtol=1e-5; Q15: rtol=1e-3; FFT Q15: rtol=5e-2)

### 1.4 Primitives Are Immutable

Released files under `primitives/kernels/v{N}/` and `primitives/datasets/v{N}/` are frozen forever.

**Block if:**
- Any file under `primitives/kernels/v1/` or `primitives/datasets/v1/` is modified
- Diff shows changes to released version directories

**Allow:**
- New files in new version directories (e.g., `v2/car@f32/`)
- Changes to `primitives/configs/` (configs are mutable)
- Changes to `primitives/devices/` (device profiles are mutable)
- Changes to `primitives/adapters/` (adapter binaries are mutable)

### 1.5 Sequential Execution for Kernel Benchmarks

Kernel benchmarks run one at a time. Parallel execution invalidates measurements through CPU contention, cache thrashing, and memory bandwidth competition.

**Block if:**
- Benchmark code runs multiple kernels concurrently
- Thread pools or parallel dispatchers are introduced in kernel benchmark paths

**Exception:** Pipeline mode (`pipelines:` YAML config) intentionally runs pipelines concurrently to simulate production conditions where multiple processing chains share hardware. Resource contention is the signal in pipeline mode, not noise.

### 1.6 ABI Version Enforcement

Every plugin must reject ABI version mismatches at init time.

**Block if:**
- A kernel's `cortex_init()` does not check `config->abi_version`
- Check is present but uses wrong constant (must be `CORTEX_ABI_VERSION`, currently 3)
- v2 backward compatibility is broken (v2 kernels checking `== 2` must still work with v3 harness)

---

## Section 2: ABI Rules

Detailed rules for the plugin binary interface, extending Section 1.1.

### Function Signatures

The canonical signatures live in `sdk/kernel/include/cortex_plugin.h`. Review against that file, not from memory.

**CRITICAL:**
- Return type changes on any ABI function
- Parameter type or count changes on any ABI function
- Removing `cortex_calibrate()` from a kernel that previously exported it

**HIGH:**
- Kernel that claims to be trainable but does not export `cortex_calibrate()`
- Missing `CORTEX_CAP_OFFLINE_CALIB` capability flag on a trainable kernel

### Backward Compatibility

The v3 harness supports v2 kernels. This means:
- Harness detects kernel version and sends the correct `abi_version` value
- v2 kernels check `config->abi_version == 2` (this is correct for them)
- v3 kernels check `config->abi_version == CORTEX_ABI_VERSION` (resolves to 3)

**CRITICAL:** Changes that would cause the harness to send wrong version to v2 kernels.

### Capability Flags

Kernels advertise features via bitmask. Currently defined:
- `CORTEX_CAP_OFFLINE_CALIB` -- kernel supports `cortex_calibrate()`

**HIGH:** Trainable kernel missing capability flag. **MEDIUM:** Non-trainable kernel setting calibration flag.

---

## Section 3: Coding Conventions

### C Code

| Rule | Severity | Details |
|------|----------|---------|
| C11 standard | **HIGH** | Compile with `-std=c11`. No GNU extensions unless guarded. |
| `snake_case` functions | **HIGH** | Public functions use `cortex_` prefix. Example: `cortex_init()`, `cortex_mul_size_overflow()`. |
| `_t` suffix on types | **MEDIUM** | All typedefs end in `_t`. Example: `cortex_init_result_t`. |
| `SCREAMING_SNAKE_CASE` macros | **MEDIUM** | All macros use `CORTEX_` prefix. Example: `CORTEX_ABI_VERSION`. |
| Overflow-safe allocation | **CRITICAL** | Use `cortex_mul_size_overflow()` before any size multiplication for allocation. Reject bare `malloc(n * sizeof(T))`. |
| NULL checks after allocation | **HIGH** | Every `malloc`/`calloc` result must be checked before use. |
| Platform guards | **HIGH** | macOS-specific code requires `#ifdef __APPLE__`. Linux-specific code requires appropriate guards. No hardcoded `.so` or `.dylib`. |
| Makefile `$(LIBEXT)` | **HIGH** | Library extensions resolved via variable, not hardcoded. `.dylib` on macOS, `.so` on Linux. |

### Python Code

| Rule | Severity | Details |
|------|----------|---------|
| DI protocol pattern | **HIGH** | Classes with `self.fs` must use `self.fs.read_file()` / `self.fs.write_file()` / `self.fs.open()`. Never raw `open()`. |
| `ProcessHandle` protocol | **HIGH** | Use `ProcessHandle` (poll, wait, terminate, kill). Never raw `subprocess.Popen` in service classes. |
| `YamlConfigLoader` | **HIGH** | Use DI config loader. Never raw `yaml.safe_load()` in service classes. |
| Test location | **MEDIUM** | Unit tests in `tests/cli/unit/`, integration tests in `tests/cli/integration/`. |
| Test framework | **MEDIUM** | Use `pytest`. Test files follow `test_{component}.py` pattern. |

### Test Commands

- Build and run C tests: `make tests` (plural, not `make test`)
- Run Python tests: `python -m pytest tests/cli/`
- Full verification: `make clean && make all && make tests`

**HIGH:** PR introduces `make test` (singular) anywhere. Correct command is `make tests`.

---

## Section 4: Architecture Alignment

Review PRs against the target architecture defined in the write-up documents (see Section 7 for paths).

### Dependency Direction

Legal dependency arrows:

```
harness → scheduler
harness → replayer
harness → telemetry
scheduler → telemetry
```

**CRITICAL** violations (reverse dependencies):
- `scheduler → harness`
- `telemetry → scheduler`
- `telemetry → harness`
- `replayer → harness`

### Harness Role

The harness is a pure orchestrator. It coordinates subsystems but does not implement signal processing, scheduling policy, or telemetry format logic.

**HIGH:** Harness code that embeds scheduling decisions, telemetry formatting, or data processing logic instead of delegating to the appropriate subsystem.

### Adapter Architecture

Device adapters follow a 4-layer model (see Adapter System Write-Up):
1. Transport layer (TCP, serial, local socketpair)
2. Wire protocol (framing, serialization)
3. Adapter logic (plugin loading, execution)
4. Platform abstraction (OS-specific timing, threading)

**HIGH:** Adapter code that collapses layers or creates cross-layer dependencies.

### Python CLI Architecture

```
CLI commands → HarnessRunner (DI: FileSystemService, ProcessExecutor, ConfigLoader)
            → TelemetryAnalyzer (DI: Logger, FileSystemService)
            → Results (SUMMARY.md, plots)
```

**HIGH:**
- CLI command directly calling `subprocess.Popen` instead of going through `ProcessExecutor`
- Service class using `open()` instead of `self.fs` methods
- Constructor that does not accept DI dependencies for external resources

---

## Section 5: Measurement Validity

These rules protect the scientific integrity of benchmark results.

### Sequential Execution

**CRITICAL:** Any change that allows concurrent kernel execution during benchmarking (not pipeline mode).

Why: CPU core contention, memory bandwidth competition, and cache invalidation produce non-reproducible measurements. Each kernel must have exclusive access to hardware resources during its benchmark window.

### Oracle-First Workflow

**HIGH:** Performance optimization PRs that do not demonstrate oracle validation still passes after changes.

Validation tolerances:
- float32 kernels: `rtol=1e-5`
- Q15 kernels: `rtol=1e-3`
- FFT Q15: `rtol=5e-2`

### Distributional Reporting

**HIGH:** Code that reports only arithmetic mean latency. All latency reporting must include P50, P95, and P99 percentiles.

Why: Mean latency hides tail behavior. A kernel with 10us mean and 500us P99 is qualitatively different from one with 10us mean and 15us P99. Real-time systems fail on tails, not averages.

### DVFS Awareness

**MEDIUM:** Benchmark configurations that do not account for CPU frequency scaling.

Known measurement traps:
- **Idle Paradox**: Idle systems exhibit 2-4x worse latency due to DVFS downclocking
- **Schedutil Trap**: Linux `schedutil` governor produces worse latency than fixed-frequency `performance` governor due to frequency transition overhead

Flag benchmark results collected without specifying governor or load conditions.

### Deadline Tracking

**HIGH:** Telemetry changes that remove or weaken deadline miss tracking (`end_ts > deadline_ts`). Deadline miss rate is a primary metric for real-time viability assessment.

---

## Section 6: Naming Standards

Common mistakes that AI-generated code and human contributors make. Flag all occurrences.

| # | Wrong | Correct | Severity |
|---|-------|---------|----------|
| 1 | `cortex_cleanup()`, `cleanup()` | `cortex_teardown()` | **CRITICAL** (ABI) |
| 2 | ABI version 1 or 2 in new code | ABI version 3 (`CORTEX_ABI_VERSION`) | **CRITICAL** |
| 3 | `make test` | `make tests` (plural) | **HIGH** |
| 4 | `plugin_abi.h`, headers in `primitives/` | `sdk/kernel/include/cortex_plugin.h` | **HIGH** |
| 5 | `run-configs/` | `primitives/configs/` | **HIGH** |
| 6 | "8 kernels", "4 kernels" | 9 f32 + 8 Q15 = 17 kernels | **MEDIUM** |
| 7 | Parallel kernel benchmarking | Sequential execution (one kernel at a time) | **CRITICAL** |
| 8 | Editing files in `v1/` | Create `v2/` directory for changes | **CRITICAL** |
| 9 | Benchmarking without oracle validation | Validate first via `cortex pipeline` or `cortex validate` | **HIGH** |
| 10 | Reporting arithmetic mean latency | Report P50/P95/P99 percentiles | **HIGH** |

---

## Section 7: Write-Up Cross-References

Each subsystem has an authoritative write-up document that defines its target architecture. When reviewing changes to a subsystem, consult the corresponding write-up for architectural intent.

| Component | Write-Up Path | Scope |
|-----------|---------------|-------|
| Harness | `paper/Harness Write-Up.{docx,pdf}` | Orchestrator design, subsystem coordination, build/run lifecycle |
| Adapter system | `paper/Adapter System Write-Up.{docx,pdf}` | 4-layer adapter model, transport abstraction, plugin loading |
| Wire protocol | `paper/Wire Protocol Write-Up.{docx,pdf}` | Framing format, message types, serialization |
| Kernel system | `paper/Kernel System Write-Up.{docx,pdf}` | ABI spec, plugin lifecycle, parameter API, hermetic execution |
| Replayer | `paper/Replayer Write-Up.{docx,pdf}` | Dataset streaming, cadence control, chunk delivery |
| Controller | `paper/Controller Write-Up.{docx,pdf}` | Experiment orchestration, multi-run coordination |
| Strand | `paper/Strand Write-Up.{docx,pdf}` | Thread model, RT priority, core affinity |
| Device provisioning | `paper/Device Provisioning Write-Up.{docx,pdf}` | Remote setup, SSH deployment, binary transfer |
| Latency decomposition | `paper/Latency Decomposition Write-Up.{docx,pdf}` | Compute/memory/overhead breakdown, PMU integration |
| Unified architecture | `paper/CORTEX-Shelob Unified Architecture.{docx,pdf}` | System-wide design, component relationships, data flow |

**How to use during review:**
1. Identify which subsystem the PR modifies
2. Consult the corresponding write-up for target architecture
3. Flag deviations as **HIGH** with a reference to the specific write-up section that disagrees
4. If the PR intentionally diverges from the write-up, require the PR description to explain why

---

## Section 8: Target Architecture Deltas

Known divergences between the current codebase and the target architecture described in the write-ups. Review agents should not flag these as issues -- they are tracked and intentional.

This section starts sparse and grows as deltas are identified.

| Component | Delta | Status | Notes |
|-----------|-------|--------|-------|
| Adapter | Transport layer uses raw TCP sockets; write-up specifies abstract transport trait | Planned | Will be addressed in extended adapter support (Apr 2026) |
| Replayer | Current implementation reworked to match write-up spec | Aligned | As of commit 87ba5e6 |
| Controller | Not yet implemented as distinct subsystem | Planned | Currently embedded in Python CLI `run` command |
| Strand | Thread model exists in scheduler; not yet extracted as named subsystem | Planned | Architectural extraction deferred until adapter work completes |
| Wire protocol | Basic framing implemented; full message type catalog incomplete | In progress | Core message types functional, extension types pending |

**When reviewing PRs that touch delta areas:**
- Do not block merges for known deltas listed above
- Do block merges that increase divergence from the target architecture without justification
- Flag PRs that resolve a delta so this table can be updated

---

## Review Output Format

When reporting findings, use this structure:

```
[SEVERITY] Category (Section N.M): One-line summary

Explanation of the issue with specific file and line references.

**Fix:** Concrete action the author should take.
**Reference:** Path to relevant spec, write-up, or code.
```

Example:

```
[CRITICAL] Hermetic violation (Section 1.2): Heap allocation in cortex_process()

primitives/kernels/v2/car@f32/car.c:87 calls malloc() inside cortex_process().
All allocations must occur in cortex_init().

**Fix:** Move buffer allocation to cortex_init() and store pointer in kernel state.
**Reference:** sdk/kernel/include/cortex_plugin.h (ABI v3 spec)
```

---

## Approval Criteria

**Approve** when:
- Zero CRITICAL findings
- All HIGH findings resolved
- Tests pass (`make tests` for C, `python -m pytest tests/cli/` for Python)
- Oracle validation passes (if kernel code changed)

**Request changes** when:
- Any CRITICAL finding present
- Unresolved HIGH findings
- Tests failing

**Comment without blocking** when:
- Only MEDIUM/LOW findings remain
- Suggestions are stylistic or optional
