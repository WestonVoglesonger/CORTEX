# Run Configuration (YAML) – Spec

Authoritative schema for `cortex.yaml` and `example.yaml`. The harness MUST
validate these fields, then translate a subset into `cortex_plugin_config_t`
for plugins. Plugins never read YAML.

## Implementation Status

**Not Yet Implemented** (Parsed but not used by harness):
- `system.name`, `system.description` - Run identification metadata (no struct fields exist)
- `power.governor`, `power.turbo` - CPU power management settings (no struct fields exist)
- `benchmark.metrics` array - Metric selection (currently collects all metrics; no struct field exists)
- `realtime.deadline.*` (runtime_us, period_us, deadline_us) - DEADLINE scheduler parameters (no struct fields exist)
- `plugins[].params` - Kernel-specific parameters (parsed to config.h:29 but set to NULL in main.c:82-83)
- `plugins[].spec_version` - Kernel spec version (parsed to config.h:26 but never validated or used)
- `plugins[].tolerances` - Per-plugin numerical tolerance specifications (no struct field; loaded from kernel spec.yaml)
- `plugins[].oracle` - Per-plugin oracle reference paths (no struct field; referenced via kernel spec.yaml)
- `output.include_raw_data` - Raw telemetry data export flag (parsed to config.h:60 but never used)

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

### power  → used by **Harness**
| Key | Type | Notes |
|---|---|---|
| governor | enum | e.g., `performance` |
| turbo | bool | Disable turbo for stability |

### benchmark  → used by **Telemetry**
| Key | Type | Notes |
|---|---|---|
| metrics | string[] | `latency`, `jitter`, `throughput`, `memory_usage`, `energy_consumption` |
| parameters.duration_seconds | int | Total time |
| parameters.repeats | int | Number of runs |
| parameters.warmup_seconds | int | Discard at start |
| load_profile | enum | `idle` \| `medium` \| `heavy` |

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
