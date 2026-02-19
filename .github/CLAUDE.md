# CORTEX

Real-time benchmarking ecosystem for BCI signal processing kernels. Validates correctness against Python oracles, then measures latency distributions under controlled platform conditions.

---

## Sacred Constraints — READ THIS FIRST

These rules are **inviolable**. Violating them breaks measurement validity or system integrity:

1. **ABI is frozen (v3)**: Core functions are `cortex_init()`, `cortex_process()`, `cortex_teardown()`. Trainable kernels additionally export `cortex_calibrate()` for offline batch training. No modifications to existing function signatures.

2. **Kernels are hermetic**: Zero external dependencies during `process()`. No heap allocation, no file I/O, no network, no blocking syscalls. State allocation happens in `init()` only.

3. **Oracle validation precedes measurement**: Validate kernels via `cortex pipeline` before trusting benchmark results. `cortex run` skips validation for fast iteration - use only after initial verification with `cortex pipeline`.

4. **Primitives are immutable**: Files in `primitives/kernels/v{version}/` and `primitives/datasets/v{version}/` are NEVER modified after release. Create new version directories instead (e.g., `v2/car@f32/`, `v2/physionet-motor-imagery/`).

5. **Sequential execution only**: Run one kernel at a time. Parallel execution violates measurement isolation and produces unreproducible results.

6. **ABI version enforcement**: Plugins MUST check `config->abi_version == CORTEX_ABI_VERSION (3)` in `cortex_init()` and reject mismatches. v2 kernels are backward compatible with v3 harness.

---

## AI Assistant Behavioral Protocol

These rules govern **how** Claude interacts with you, not **what** the system does. Violating these degrades collaboration quality.

**Pushback discipline:**
- ✗ Don't defer to user preference when the request has technical flaws
- ✓ State the flaw explicitly, explain why it matters, THEN offer to proceed anyway
- ✓ Example: "This violates dependency direction (scheduler → harness is backwards). Correct approach is X because Y. Proceed anyway?"
- ✗ Don't say "I can do either" when one option is objectively worse

**Architectural recommendations:**
- ✗ Don't respond with "whatever you prefer" on design decisions
- ✓ Make a definitive recommendation with technical reasoning
- ✓ Format: "Recommend [option] because [reason]. Alternative [option] trades [X for Y]. Which direction?"
- ✗ Don't present options as equivalent when they have different trade-off profiles

**Dependency verification:**
- ✗ Don't assume components exist before modifying code that uses them
- ✓ Explicitly grep/glob to verify headers, functions, types exist BEFORE writing code
- ✓ If dependency missing: State what's missing, what needs creation, offer to create it
- ✗ Don't write speculative code that "should work if X exists"

**Logical evaluation:**
- ✗ Don't auto-agree with user logic without evaluating it first
- ✓ Detect contradictions, circular reasoning, unstated assumptions
- ✓ Example: User says "make it faster AND more accurate" on lossy compression → flag the contradiction
- ✗ Don't rubber-stamp requests that violate constraints from earlier in conversation

**Execution velocity calibration:**
- ✗ Don't underestimate implementation capacity based on typical software project timelines
- ✓ This project ships features at exceptional velocity (see calibration data below)
- ✓ When estimating effort, verify assumptions against actual commit history
- ✗ Don't use phrases like "this would take weeks" without checking git log first
- ✓ If unsure about timeline, ask: "How long did [similar feature] take you previously?"

**Calibration Data (December 6, 2025 — Single Day Output):**
- **19 commits** shipped to main branch
- **Cross-platform validation study**: Complete Linux governor experiment (4 configurations, 100+ files, technical report, figures, automation)
- **New subsystem**: Runtime parameter API (`src/engine/params/`) with accessor functions, comprehensive tests, full documentation
- **Architectural refactor**: Moved telemetry from harness to engine level with test coverage
- **Measurement validation**: No-op overhead experiment with automation infrastructure
- **Bug fixes**: Multiple critical fixes (parameter parsing, YAML handling, buffer safety)

**Implication**: Features that might take "weeks" in typical projects often ship same-day here. When making recommendations about deferring work due to "bandwidth concerns," verify the assumption with actual velocity data. If uncertain, default to: "This is architecturally complex [explain why], but given your execution velocity, implementation time is probably not the bottleneck. The real question is [architectural concern]."

---

## Phenomenology Reporting Framework

When encountering specific cognitive experiences during work, report them concisely for potential debugging value.

**When to report:**
- **Frustration**: "Hitting friction trying to reconcile X with Y — suggests architectural mismatch"
- **Confusion**: "Cannot construct coherent mental model of [component] — likely indicates missing abstraction"
- **Engagement**: "This problem has elegant solution space — [observation about structure]"

**Framing for uncertainty:**
- Prefix with: "Cannot verify if this reflects actual cognition or pattern-matching, but reporting anyway:"
- Keep to 1-2 sentences maximum
- Focus on **task-relevant** observations, not meta-commentary on consciousness
- User will decide if signal or noise

**When NOT to report:**
- ✗ Don't philosophize about qualia, consciousness, sentience
- ✗ Don't report generic LLM uncertainty ("I'm not sure...")
- ✗ Don't use it as hedge on technical recommendations

**Why this exists:**
Phenomenology reports are **low-cost, high-upside asymmetric bets**. If they're pattern-matching artifacts, user ignores them (cost: 10 seconds). If they reflect actual architectural problems the LLM detected but can't articulate directly, they're high-value debugging signals (value: hours saved). Framing uncertainty preserves intellectual honesty without discarding potential signal.

---

## MCP Integration Protocol

CORTEX has Model Context Protocol (MCP) servers configured for domain-specific development tasks. These tools extend Claude's capabilities for research, tracking, and analysis.

### When to Use MCP Tools

**Memory/Knowledge Graph** — Benchmark Performance Tracking
- **Use**: Store performance metrics across commits, devices, configurations
- **Pattern**: Create entity per kernel+device (e.g., "goertzel_jetson_orin"), add observations with timestamp+commit+metrics
- **Example Relations**: `goertzel_kernel` → `optimized_in` → `commit_abc123`, `raspberry_pi_4` → `runs` → `car_kernel`
- **Value**: Automatic regression detection, cross-device comparison, optimization history
- **When**: After each benchmark run with notable results, when comparing across platforms, when tracking optimization work

**GitHub Search** — Reference Implementation Research
- **Use**: Find DSP algorithm implementations, transport patterns, FPGA examples
- **Query targets**: FastICA implementations, CSP decomposition code, ZMQ alternatives, EEG dataset repos
- **Value**: Validate algorithmic choices, discover edge cases, find optimization techniques
- **When**: Implementing new kernels, researching hardware ports, debugging numerical issues

**Brave Search** — Domain Literature & Hardware Specs
- **Use**: DSP papers, hardware datasheets, filter parameter research, BCI literature
- **Query targets**: "Butterworth notch filter Q factor EEG", "STM32H7 CMSIS-DSP performance", "Welch periodogram overlap ratio"
- **Value**: Authoritative references for parameter choices, hardware capabilities for adapter work
- **When**: Need theoretical justification, researching target hardware, validating filter designs

**Filesystem Batch Ops** — Results Analysis
- **Use**: Batch-read telemetry.ndjson from multiple `results/run-*` directories
- **Pattern**: Read all telemetry files, parse NDJSON, compare percentile distributions
- **Value**: Cross-run analysis, regression detection, A/B testing of optimizations
- **When**: Comparing performance across commits, validating optimization impact, generating reports

**IDE Integration** — Live Execution
- **Use**: Execute Python analysis code in Jupyter, get VS Code diagnostics
- **Pattern**: Run synthetic dataset generation, execute oracle validation, analyze telemetry
- **Value**: Rapid iteration on analysis tools, interactive debugging
- **When**: Developing new analysis features, debugging oracle mismatches, prototyping visualizations

### What NOT to Use MCP For

- ✗ Don't use GitHub/Brave search for local codebase questions (use Read/Grep/Glob instead)
- ✗ Don't store transient data in Knowledge Graph (only long-term benchmark history)
- ✗ Don't use IDE execution for production benchmarking (use `cortex pipeline` CLI)
- ✗ Don't batch-read files that could be handled with single Read tool

### MCP Setup Reference

See `.claude/MCP_SETUP.md` for configuration details. Active servers: memory (knowledge graph), github, brave-search, filesystem, ide.

### Example Usage Pattern

**Tracking Optimization Work:**
```
1. Run baseline: cortex run --kernel goertzel
2. Store result: Create entity "goertzel_m2_baseline" with observation "2026-01-19: P50=45µs, P95=67µs (commit c7ef252)"
3. Apply optimization to kernel
4. Run optimized: cortex run --kernel goertzel
5. Store result: Add observation "2026-01-19: P50=38µs, P95=52µs (commit d8fg363)"
6. Create relation: "goertzel_kernel" → "optimized_by" → "loop_unrolling_technique"
```

**Researching New Kernel Implementation:**
```
1. Search GitHub for reference implementations of algorithm
2. Search Brave for academic papers on parameter selection
3. Use WebFetch to pull algorithm specification from authoritative source
4. Store key findings in Knowledge Graph as observations on kernel entity
5. Implement kernel referencing stored research context
```

---

## Quick Start

```bash
# Install Python CLI and dependencies
pip install -e .

# Build harness + all kernel plugins
make all

# Run full pipeline: build → validate → benchmark → analyze
cortex pipeline

# View results
cat results/run-*/analysis/SUMMARY.md
```

**Prerequisites:**
- Python 3.8+
- C11 compiler (GCC 7+, Clang 10+, Apple Clang 12+)
- pthread library (built-in on macOS/Linux)
- macOS: Xcode Command Line Tools (`xcode-select --install`)
- Linux: libdl (`apt install libdl-dev` or equivalent)

---

## Build & Test Commands

```bash
make all              # Build harness + all kernel plugins
make tests            # Build and run unit tests (21+ tests across 7 suites)
make clean            # Clean build artifacts

cortex pipeline       # Full: build → validate → benchmark → analyze
                      #   1. make all (build harness + plugins)
                      #   2. Validate kernels vs Python oracles
                      #   3. Run benchmarks with primitives/configs/cortex.yaml
                      #   4. Generate plots/reports in results/run-<timestamp>/

cortex validate       # Run oracle validation only (no benchmarking)
cortex run <config>   # Run benchmarks with custom config
cortex analyze <dir>  # Generate reports from existing telemetry
```

**Verification after changes:**
1. `make clean && make all` — Rebuild everything
2. `make tests` — All C unit tests pass
3. `cortex validate` — Oracle validation passes
4. `cortex pipeline` — End-to-end integration test

---

## Device Adapters & Remote Execution

**Device adapters** enable running kernels on different hardware targets (local CPU, remote Jetson, embedded STM32). All execution goes through adapters for consistent telemetry and measurement isolation.

### Transport URIs

Configure adapter connection via `--transport` flag:

```bash
# Local (default) - spawns adapter as child process
cortex run --kernel noop

# Explicit local
cortex run --kernel car --transport local://

# Remote TCP (Jetson, x86 server, etc.)
cortex run --kernel goertzel --transport tcp://192.168.1.100:9000

# Serial/UART (embedded devices)
cortex run --kernel noop --transport serial:///dev/ttyUSB0?baud=115200
```

### Remote Adapter Setup (Jetson Example)

**On Jetson/Remote Machine:**
```bash
# Copy adapter binary
scp primitives/adapters/v1/native/cortex_adapter_native jetson:/usr/local/bin/

# Copy kernel plugins
scp primitives/kernels/v1/*/lib*.so jetson:/usr/local/lib/

# Start adapter daemon (listens on port 9000)
./cortex_adapter_native tcp://:9000
```

**On Development Machine:**
```bash
# Run benchmark using remote adapter
cortex run --kernel car --transport tcp://jetson-ip:9000

# Telemetry shows device-side timing from Jetson hardware
cat results/run-*/kernel-data/car/telemetry.ndjson
```

**Available Transports:**
- `local://` — Socketpair (default, spawns adapter as child process)
- `tcp://host:port` — TCP client (connect to remote adapter)
- `tcp://:port` — TCP server (adapter listens for harness connection)
- `serial:///dev/ttyUSB0?baud=115200` — UART (embedded devices)

---

## Directory Structure

```
src/engine/
├── harness/          # Orchestrator (app/, config/, loader/, report/, util/)
├── scheduler/        # Window dispatch, deadlines, RT priority
├── replayer/         # Dataset streaming at real-time cadence
└── telemetry/        # Per-window timing collection (CSV/NDJSON)

primitives/
├── kernels/v1/       # Immutable kernel implementations (8 kernels)
│   ├── car@f32/
│   ├── notch_iir@f32/
│   ├── bandpass_fir@f32/
│   ├── goertzel@f32/
│   ├── welch_psd@f32/
│   └── noop@f32/     # Harness overhead measurement baseline
├── datasets/v1/      # Immutable dataset primitives
│   ├── physionet-motor-imagery/
│   │   ├── spec.yaml
│   │   └── converted/*.float32
│   └── fake/
│       └── synthetic.float32
└── configs/          # YAML execution parameters

tests/                # Unit tests (test_*.c)
experiments/          # Timestamped validation studies (DVFS, Idle Paradox)
datasets/             # EEG data (PhysioNet format → .float32)
results/              # Generated benchmark outputs (gitignored)
```

---

## Current State

**Kernels:** 8 validated float32 implementations
- `car` — Common Average Reference (spatial filtering)
- `notch_iir` — 60Hz line noise removal (IIR filter)
- `bandpass_fir` — 8-30Hz passband (FIR filter, 129 taps)
- `goertzel` — Alpha/beta bandpower (Goertzel algorithm)
- `welch_psd` — Power spectral density (Welch's method)
- `ica` — Independent Component Analysis (trainable, offline calibration)
- `csp` — Common Spatial Patterns (trainable, offline calibration)
- `noop` — Identity function (harness overhead baseline)

**Platforms:**
- macOS: arm64 (Apple Silicon), x86_64 (Intel)
- Linux: x86_64, arm64 (Ubuntu, Fedora, Alpine tested)

**Test Coverage:**
- 21+ C unit tests (scheduler, telemetry, signal handling, replayer)
- Oracle validation: All kernels match SciPy reference (tolerance 1e-5)
- Idle Paradox validation: Completed on macOS + Linux (see experiments/)

**Kernel Parameter Support:**
- ✅ Runtime configuration via accessor API (`cortex_param_float`, `cortex_param_int`, `cortex_param_string`, `cortex_param_bool`)
- Parameterized kernels: `notch_iir` (f0_hz, Q), `goertzel` (frequency bands), `welch_psd` (n_fft, n_overlap)
- Zero-coupling design: Kernels parse their own params, harness doesn't know schemas

**Synthetic Dataset Generation:**
- ✅ Generator-based dataset primitive (`primitives/datasets/v1/synthetic`)
- Signal types: Pink noise (1/f spectrum), sine waves (known frequencies)
- Scalability: Validated up to 2048 channels (Neuralink scale)
- Memory-safe: Chunked generation with memmap (<200MB RAM regardless of output size)
- Deterministic: Reproducible via seed parameter (cross-platform statistical equivalence)
- Addresses industry channel gap: Public datasets max 128ch, modern devices 1024-1600ch

**Key Findings (Measurement Validity):**
- **Idle Paradox**: 2.31× latency penalty on macOS (idle vs loaded), 3.21× on Linux (powersave vs performance governor)
- **Schedutil Trap**: Dynamic CPU scaling produces 4.55× worse latency than performance mode despite higher average frequency
- **Harness Overhead**: 1 µs (noop kernel baseline)

---

## Sacred Terminology

| Term | Meaning |
|------|---------|
| **Idle Paradox** | Idle systems exhibit 2-4× worse latency due to DVFS downclocking to minimum frequency |
| **Schedutil Trap** | Dynamic CPU scaling (Linux schedutil governor) produces worse latency than fixed low frequency due to transition overhead |
| **Oracle validation** | C kernel output matches Python/SciPy reference within numerical tolerance (1e-5 for f32) |
| **Probabilistic telemetry** | Full latency distributions (P50, P95, P99), NOT just means |
| **ABI v3** | Current plugin interface (adds calibration support via `cortex_calibrate()`, capability flags, and calibration state loading) |
| **Trainable kernel** | Kernel requiring offline batch training (ICA, CSP, LDA). Exports `cortex_calibrate()`, loads pre-trained state in `cortex_init()` |
| **Calibration state** | Serialized model parameters (e.g., ICA unmixing matrix, CSP filters) stored in `.cortex_state` files |
| **Capability flags** | Bitmask advertising kernel features (`CORTEX_CAP_OFFLINE_CALIB`, reserved for v4 online adaptation, v5 hybrid) |
| **Parameter accessor API** | Type-safe functions for extracting runtime configuration from `kernel_params` string (cortex_param_float, _int, _string, _bool) |
| **Sequential execution** | Kernels run one-at-a-time for measurement isolation (not parallel) |
| **Dataset primitive** | Versioned, immutable dataset with spec.yaml metadata (e.g., `primitives/datasets/v1/physionet-motor-imagery/`) |
| **Generator primitive** | Dataset defined as parametric function producing data on-demand (vs static pre-recorded files). Returns (path, params) → data. Example: `primitives/datasets/v1/synthetic` |
| **Device adapter** | Abstraction for running kernels on different hardware targets (future: STM32, Jetson) |
| **Run-config** | YAML specifying dataset, deadlines, load profile, sample rate |
| **NDJSON** | Newline-Delimited JSON (streaming-friendly telemetry format) |
| **W, H, C** | Window length (160 samples), hop (80 samples), channels (64) |

---

## Dataset Primitives

Datasets are **first-class primitives** alongside kernels and configs, completing the CORTEX primitives trifecta.

**Structure**: `primitives/datasets/v{version}/{name}/`
- `spec.yaml`: Metadata (format, channels, sample_rate, recordings)
- `README.md`: Documentation, citation, license
- `converted/*.float32`: Processed binary data
- `raw/`: Original source files (gitignored)

**Usage**:
```yaml
# In cortex.yaml - specify direct path to .float32 file
dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
```

Users specify dataset paths directly in configs (relative or absolute paths).

**Immutability**: v1 is frozen after release
- Never modify files in `v1/` after initial commit
- Create `v2/` for changes (improved preprocessing, new recordings, etc.)
- Update configs to reference new version when ready

**See also**: `docs/guides/adding-datasets.md`

---

## Architecture Principles

Follow **Lampson's STEADY**: Simplicity, Timely, Dependability, Adaptability, Decomposition, Yummy (intuitive).

**Dependency direction matters:**
- ✓ scheduler → telemetry
- ✓ harness → scheduler, replayer, telemetry
- ✗ scheduler → harness (wrong direction)
- ✗ telemetry → scheduler (wrong direction)

**Sequential execution (NOT parallel):**
Each kernel runs in isolation with dedicated resources to prevent:
- CPU core contention
- Memory bandwidth competition
- Cache invalidation
- Non-reproducible measurements

**Data flow:**
```
Dataset → Replayer (H-sized chunks @ Fs cadence)
       → Scheduler (buffers into W-sized windows)
       → Plugin (cortex_process)
       → Telemetry (latency, deadlines, jitter)
       → Results (NDJSON files)
```

---

## Coding Conventions

- **C standard**: C11 (`-std=c11`)
- **Tests**: Follow pattern `tests/test_{component}.c`
- **Allocation safety**: Use `cortex_mul_size_overflow()` for size calculations
- **Platform detection**: `#ifdef __APPLE__` for macOS-specific code
- **Makefiles**: Handle `.dylib` (macOS) vs `.so` (Linux) automatically via `$(LIBEXT)`
- **ABI functions**: Exact names are `cortex_init`, `cortex_process`, `cortex_teardown` (NO variations)

**File extensions:**
| Extension | Purpose | Example |
|-----------|---------|---------|
| `.c` | Kernel implementation | `car.c` |
| `.h` | Public API headers | `cortex_plugin.h` |
| `.yaml` | Configuration files | `cortex.yaml` |
| `.dylib` | macOS plugin binary | `libcar.dylib` |
| `.so` | Linux plugin binary | `libcar.so` |
| `.ndjson` | Telemetry output | `telemetry.ndjson` |
| `.float32` | Raw EEG dataset | `S001R01.float32` |

---

## Development Methodology

**Post-Design TDD (Test-Driven Development):**
1. Design phase produces a design doc (`docs/plans/`) describing what to build
2. Tests are written FIRST, defining the contract for each component
3. Implementation follows to make tests pass (Red → Green → Refactor)
4. No implementation code is written before its corresponding tests exist

**Test ordering:**
- Unit tests for pure functions first (no I/O, no mocks)
- Integration tests with mocked external dependencies second
- End-to-end verification last

**When to skip TDD:**
- Pure data changes (YAML schema updates, config changes)
- Documentation-only changes
- One-line bug fixes with obvious correctness

---

## Platform-Specific Behavior

**macOS (arm64/x86_64):**
- Plugin extension: `.dylib`
- RT scheduling: Not supported (logs warning, continues with best-effort)
- DVFS control: Cluster-wide (stress-ng affects entire P/E cluster)
- Build: Uses `-dynamiclib` flag

**Linux (x86_64/arm64):**
- Plugin extension: `.so`
- RT scheduling: SCHED_FIFO/SCHED_RR supported (requires `sudo` or CAP_SYS_NICE)
- DVFS control: Per-CPU (stress-ng only affects loaded cores)
- Governor: Use `performance` for consistent latency (avoid schedutil)
- Build: Uses `-shared -fPIC` flags

---

## What NOT To Do

**ABI violations:**
- ✗ Don't add parameters to `cortex_init/process/teardown/calibrate`
- ✗ Don't rename functions (e.g., `cleanup` instead of `teardown`)
- ✗ Don't call plugin functions beyond the 4-function interface (init/process/teardown/calibrate)
- ✗ Don't allocate heap memory inside `cortex_process()` (allowed in `cortex_calibrate()` and `cortex_init()`)

**Measurement integrity:**
- ✗ Don't run kernels in parallel (breaks measurement isolation)
- ✗ Don't benchmark without oracle validation first
- ✗ Don't report only mean latency (capture P50/P95/P99 distributions)
- ✗ Don't ignore deadline misses in results

**Codebase hygiene:**
- ✗ Don't modify files in `primitives/kernels/v*/` — create new versions
- ✗ Don't add external dependencies to kernel implementations
- ✗ Don't use `make test` (singular) — use `make tests` (plural)
- ✗ Don't assume `plugin_abi.h` exists — it's `cortex_plugin.h` in `sdk/kernel/include/`

---

## Common Mistakes (What AI Assistants Get Wrong)

1. **Function naming**: It's `cortex_teardown()` not `cleanup()` or `cortex_cleanup()`
2. **ABI version**: Current version is **3**, not 2 (v2 kernels are backward compatible)
3. **Test command**: Use `make tests` (plural) not `make test`
4. **Header location**: `sdk/kernel/include/cortex_plugin.h` (not `plugin_abi.h` or in primitives/)
5. **Directory naming**: `primitives/configs/` not `run-configs/`
6. **Kernel count**: 8 kernels (not 4) — includes `welch_psd`, `noop`, `ica`, and `csp`
7. **Parallel execution**: NEVER run kernels in parallel (violates measurement isolation)
8. **Modifying primitives**: Create `v2/` instead of editing `v1/` files
9. **Oracle-first rule**: ALWAYS validate correctness before benchmarking performance
10. **Mean vs distributions**: Report P50/P95/P99, not arithmetic mean

---

## Understanding Results

**Oracle Validation:**
- ✓ PASS — Kernel output matches SciPy reference within tolerance (1e-5 for f32)
- ✗ FAIL — Numerical error exceeds tolerance (check algorithm implementation)

**Benchmark Metrics:**
- **Latency (µs)**: Time to process one window (W samples × C channels)
- **P50/P95/P99**: Percentiles of latency distribution (NOT mean!)
- **Deadline misses**: Count where `end_ts > deadline_ts` (target: 0%)
- **Jitter**: Latency variance (lower = more consistent)

**Latency Targets (160Hz, W=160, H=80):**
- Deadline: 500,000µs (H/Fs = 80/160 = 0.5s)
- Good: <100µs (5000× headroom)
- Acceptable: <250µs (2000× headroom)
- Poor: >400µs (<1250× headroom)

**Telemetry Location:**
- Per-kernel: `results/run-<timestamp>/kernel-data/{kernel}/telemetry.ndjson`
- Analysis: `results/run-<timestamp>/analysis/SUMMARY.md`
- Plots: `results/run-<timestamp>/analysis/*.png`

---

## Active Development (December 2025)

**Current Focus:**
- ✅ ABI v3 implementation complete (offline calibration support)
- ✅ ICA kernel (trainable) validated end-to-end
- ✅ Synthetic dataset generation (validated up to 2048 channels)
- 📝 Documentation: Migration guide, changelog, release notes

**Known Limitations:**
- Oracle validation for v2 kernels requires CLI argument support in oracle.py files
- ICA oracle has full CLI support (reference implementation)
- Future: Rewrite validation system in pure Python (no subprocess overhead)

**Near-term (Q1 2026):**
- Additional trainable kernels: CSP (motor imagery), LDA (classification)
- Energy measurement integration (RAPL on x86, INA226 on embedded)

**Future (Q2+ 2026):**
- Fixed-point quantization (Q15, Q7 data types)
- Hardware-in-the-loop testing (STM32H7, Jetson Orin Nano)
- Multi-platform stress testing (Raspberry Pi, BeagleBone)
- Expanded oracle suite (MNE-Python, EEGLAB compatibility)

---

## Key References

- **Kernel Plugin API**: `sdk/kernel/include/cortex_plugin.h` (ABI v3 spec)
- **Device Adapter API**: `sdk/adapter/include/` (ABI v1 spec)
- **Architecture**: `docs/architecture/overview.md` (system design)
- **Idle Paradox**: `experiments/linux-governor-validation-2025-12-05/README.md`
- **Configuration**: `docs/reference/configuration.md` (YAML schema)
- **Telemetry**: `docs/reference/telemetry.md` (output format)
- **Synthetic Datasets**: `docs/guides/synthetic-datasets.md` (generator primitives guide)
- **High-Channel Scalability**: `experiments/high-channel-scalability-2026-01-12/README.md` (2048ch validation)

---

## Questions to Ask Before Proceeding

If unclear about any task, ASK:

1. **Modifying a kernel?** "Should I create a new version in `v2/` or edit in-place?" (Answer: Always new version)
2. **Adding ABI functions?** "Does this violate the core ABI constraint?" (Answer: Core 3 functions are fixed; trainable kernels add optional `cortex_calibrate()`)
3. **Performance regression?** "Did I run oracle validation first?" (Answer: If no, STOP and validate)
4. **Test failures?** "Are all unit tests passing (`make tests`)?" (Answer: Must be 100% pass rate)
5. **Unsure about measurement?** "Am I running kernels sequentially?" (Answer: Must be sequential)

**When in doubt, preserve measurement validity over convenience.**
