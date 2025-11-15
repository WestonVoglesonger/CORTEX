# Run Configuration (YAML) – Spec

Authoritative schema for `cortex.yaml` and `example.yaml`. The harness MUST
validate these fields, then translate a subset into `cortex_plugin_config_t`
for plugins. Plugins never read YAML.

## Implementation Status

**Not Yet Implemented** (Parsed but not used by harness):
- `system.name`, `system.description` - Run identification metadata (no struct fields exist)
- `benchmark.metrics` array - Metric selection (currently collects all metrics; no struct field exists)
- `realtime.deadline.*` (runtime_us, period_us, deadline_us) - DEADLINE scheduler parameters (no struct fields exist)
- `plugins[].params` - Kernel-specific parameters (parsed to config.h:29 but set to NULL in main.c:82-83)
- `plugins[].spec_version` - Kernel spec version (parsed to config.h:26 but never validated or used)
- `plugins[].tolerances` - Per-plugin numerical tolerance specifications (no struct field; loaded from kernel spec.yaml)
- `plugins[].oracle` - Per-plugin oracle reference paths (no struct field; referenced via kernel spec.yaml)
- `output.include_raw_data` - Raw telemetry data export flag (parsed to config.h:60 but never used)

**Temporary Implementations** (FALL 2025 - See docs/architecture/adr-001-temporary-host-power-config.md):
- `power.governor`, `power.turbo` - ⚠️ TEMPORARY Python wrapper for x86 host only
  - Linux: Full support via sysfs (requires sudo)
  - macOS: Warnings only (OS-managed, no manual control)
  - Implementation: `src/cortex/utils/power_config.py` (isolated module, zero C harness changes)
  - Removal plan: Spring 2026 redesign when device adapters exist

**Fully Implemented**:
- `dataset.*` - Used by replayer for streaming EEG data
- `realtime.scheduler`, `realtime.priority`, `realtime.cpu_affinity`, `realtime.deadline_ms` - Used by scheduler
- `benchmark.parameters.*` (duration_seconds, repeats, warmup_seconds) - Used by harness lifecycle
- `benchmark.load_profile` - Background load profile (✅ fully implemented with stress-ng integration; see replayer.c)
- `output.directory`, `output.format` - Used by telemetry writer
- `plugins[].name`, `plugins[].status`, `plugins[].spec_uri` - Used by harness for plugin loading and filtering

See [docs/development/roadmap.md](../development/roadmap.md) for implementation timeline.

## Kernel Auto-Detection

**Status:** ✅ Implemented (Phase 2)

When the `plugins:` section is **omitted** from the configuration file, CORTEX automatically discovers and runs all built kernels from the `primitives/kernels/` directory.

### Behavior

**Auto-detection mode (no `plugins:` section):**
```yaml
cortex_version: 1
dataset:
  path: "datasets/eegmmidb/converted/S001R03.float32"
  channels: 64
  sample_rate_hz: 160
# No plugins section - auto-detect mode
```
- Scans `primitives/kernels/v*/` for built kernels
- Includes all kernels with compiled shared libraries (.dylib/.so)
- Skips kernels without implementations or unbuilt kernels
- Runs all discovered kernels sequentially in alphabetical order

**Explicit mode (has `plugins:` section):**
```yaml
plugins:
  - name: "goertzel"
    status: ready
    spec_uri: "primitives/kernels/v1/goertzel@f32"
```
- Only runs explicitly listed kernels
- Empty `plugins:` section means run zero kernels (valid for testing)

### Discovery Criteria

A kernel is auto-detected if:
1. ✅ Located in `primitives/kernels/v{N}/{name}@{dtype}/` directory
2. ✅ Has `{name}.c` implementation file
3. ✅ Has compiled shared library (`lib{name}.dylib` or `lib{name}.so`)

Auto-detected kernels:
- Are marked with status: `ready`
- Load runtime config from `spec.yaml` if present
- Use default config if no spec (W=160, H=80, dtype=float32)
- Are validated same as explicitly specified kernels
- Run in alphabetical order for reproducibility

### Use Cases

**Auto-detection mode** - Best for:
- Comprehensive benchmarking of all available kernels
- Testing after building new kernels
- Quick performance surveys

**Explicit mode** - Best for:
- Focused benchmarking of specific kernels
- Production runs with known kernel sets
- Kernel development (test single kernel)

### Current Limitations

**Multi-Dtype Support** (Spring 2026):

The current auto-detection system has known limitations when multiple data types exist for the same kernel:

1. **Alphabetical sorting limitation**: Kernels are sorted by name only, not by dtype. When `goertzel@f32`, `goertzel@q15`, and `goertzel@q7` all exist, their relative order may vary across runs.

2. **Display ambiguity**: Console output shows kernel name without dtype suffix, making it unclear which variant executed when multiple dtypes are present.

**Current Impact**: These limitations are **not observable** in Fall 2025 because only `@f32` implementations exist. They will be addressed during Spring 2026 quantization implementation.

See `docs/development/future-enhancements.md` for planned fixes and `docs/development/roadmap.md` for implementation timeline.

## Versioning
- `cortex_version: <int>` — bump on breaking changes.

## Top-level keys

### system
| Key | Type | Notes |
|---|---|---|
| name | string | Run identifier |
| description | string | Free text |

### dataset  → used by **Replayer**
| Key | Type | Notes |
|---|---|---|
| path | string | Dataset root/file |
| format | string | e.g., `raw` |
| channels | int | C |
| sample_rate_hz | int | Fs |

### realtime  → used by **Harness**
| Key | Type | Notes |
|---|---|---|
| scheduler | enum | `fifo` \| `rr` \| `deadline` \| `other` |
| priority | int | 1–99 (FIFO/RR) |
| cpu_affinity | int[] | Core IDs |
| deadline_ms | int | Usually `1000 * H / Fs` |
| deadline.runtime_us | int | DEADLINE only |
| deadline.period_us | int | DEADLINE only |
| deadline.deadline_us | int | DEADLINE only |

### power  → used by **Python Wrapper** (TEMPORARY - Fall 2025 only)
| Key | Type | Notes |
|---|---|---|
| governor | enum | CPU frequency governor (e.g., `performance`, `powersave`)<br/>⚠️ **Linux only** - Requires sudo, controls `/sys/devices/system/cpu/*/cpufreq/scaling_governor`<br/>⚠️ **macOS** - Warning only (OS-managed, no manual control) |
| turbo | bool | Disable Intel Turbo Boost / AMD Turbo Core for consistency<br/>⚠️ **Linux only** - Requires sudo, controls Intel `no_turbo` or AMD `boost` sysfs files<br/>⚠️ **macOS** - Warning only (OS-managed, no manual control) |

**TEMPORARY IMPLEMENTATION** (Fall 2025): This feature is implemented in Python wrapper layer (`src/cortex/utils/power_config.py`) as a temporary solution for x86 host benchmarking. It will be redesigned or removed in Spring 2026 when device adapters are implemented. See `docs/architecture/adr-001-temporary-host-power-config.md` for full rationale and migration plan.

**Example:**
```yaml
power:
  governor: "performance"  # Lock CPU frequency to maximum
  turbo: false             # Disable turbo boost for consistency
```

**Linux Usage (requires sudo):**
```bash
sudo PYTHONPATH=src python3 -m cortex run primitives/configs/cortex.yaml --name my_run
```

**macOS Behavior:**
Runs without errors but prints warnings that power config is OS-managed and cannot be manually controlled.

### benchmark  → used by **Telemetry**
| Key | Type | Notes |
|---|---|---|
| metrics | string[] | `latency`, `jitter`, `throughput`, `memory_usage`, `energy_consumption` |
| parameters.duration_seconds | int | Total time |
| parameters.repeats | int | Number of runs |
| parameters.warmup_seconds | int | Discard at start |
| load_profile | enum | `idle` \| `medium` \| `heavy` (see detailed section below) |

#### Background Load Profiles (`load_profile`)

**Status:** ✅ Fully implemented in `src/engine/replayer/replayer.c`

Background load profiles simulate system stress during benchmarking to test kernel robustness under realistic operating conditions.

**Available Profiles:**

| Profile | Description | stress-ng Parameters | Use Case |
|---------|-------------|---------------------|----------|
| `idle` | No artificial load | (none) | Clean baseline measurements, default mode |
| `medium` | Moderate CPU load | `--cpu N/2 --cpu-load 50%` | Simulate typical system usage |
| `heavy` | High CPU load | `--cpu N --cpu-load 90%` | Stress test under heavy contention |

Where `N` = number of CPU cores on the system.

**Dependency:**

Load profiles require the **stress-ng** system tool:

- **macOS**: `brew install stress-ng`
- **Linux (Ubuntu/Debian)**: `sudo apt install stress-ng`
- **Linux (RHEL/Fedora)**: `sudo yum install stress-ng`

**Graceful Fallback:**

If `stress-ng` is not installed:
- System prints: `[load] stress-ng not found in PATH, running without background load`
- Automatically falls back to `idle` mode (no artificial load)
- Benchmark continues normally without errors

**Example Configuration:**

```yaml
benchmark:
  parameters:
    duration_seconds: 120
    repeats: 5
    warmup_seconds: 10
  load_profile: "medium"  # Requires stress-ng installed
```

**Console Output:**

When `stress-ng` is available:
```
[load] started background load: medium (PID 12345, 4 CPUs @ 50% load)
```

When `stress-ng` is not installed:
```
[load] stress-ng not found in PATH, running without background load
```

**Recommended Usage:**

- **Development/Testing**: Use `idle` for reproducible baseline measurements
- **Production Validation**: Use `medium` or `heavy` to validate robustness
- **Continuous Integration**: Use `idle` (stress-ng may not be in CI environment)

**Implementation Details:**

See `src/engine/replayer/replayer.c` (lines 350-455) for the complete background load implementation including:
- stress-ng process spawning via `fork()`/`execv()`
- Automatic CPU count detection
- Process lifecycle management (start/stop)
- Graceful error handling

### output  → used by **Telemetry**
| Key | Type | Notes |
|---|---|---|
| directory | string | Output folder |
| format | enum | `ndjson` \| `csv` (default: `ndjson`) |
| include_raw_data | bool | Usually false |

### plugins  → feeds **ABI init** per plugin
Array of objects:

**plugins[i]**
| Key | Type | Notes |
|---|---|---|
| name | string | `car`, `notch_iir`, `bandpass_fir`, `goertzel`, … |
| status | enum | `draft` \| `ready` |
| spec_uri | string\|null | Path to kernel spec (e.g., `primitives/kernels/v1/car@f32`) |
| spec_version | string\|null | Kernel spec version (e.g., `1.0.0`) |

**plugins[i].runtime**
| Key | Type | Notes |
|---|---|---|
| window_length_samples | int | W |
| hop_samples | int | H |
| channels | int | C (== dataset.channels) |
| dtype | enum | `float32` \| `q15` \| `q7` |
| allow_in_place | bool | In-place allowed |

**plugins[i].params**
- Object (kernel-specific). Examples:
  - notch: `{ f0_hz, Q }`
  - car: `{ exclude_channels: [] }`

**plugins[i].tolerances**
- Object (abs/rel), or null while draft.

**plugins[i].oracle**
- String path to gold bundle, or null while draft.

## Derived defaults (EEG v1)
- Fs = 160, W = 160, H = 80, C = 64.
- `deadline_ms = 1000 * H / Fs = 500`.

## Validation rules (harness MUST enforce)
- `sample_rate_hz > 0`, `channels > 0`.
- For each plugin:
  - `0 < hop_samples ≤ window_length_samples`.
  - `runtime.channels == dataset.channels`.
- If `scheduler: deadline` → require runtime/period/deadline.
- If `status: ready` → `params`, `tolerances`, `oracle` non-empty.
- Warn and degrade gracefully if RT privileges missing.
