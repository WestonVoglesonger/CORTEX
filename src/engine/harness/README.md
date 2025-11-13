## Harness Module

Purpose: Orchestrate replayer → scheduler → plugins behind the stable ABI, apply runtime policy (affinity/scheduling), persist telemetry, and manage run lifecycle per `docs/RUN_CONFIG.md` and `docs/TELEMETRY.md`. Loads kernel specifications from the registry to configure plugin runtime parameters.

### Responsibilities
- Parse YAML config (`configs/*.yaml`) and validate per `docs/RUN_CONFIG.md`.
- Load kernel specifications from registry (`kernels/v1/{name}@{dtype}/spec.yaml`) to populate runtime parameters.
- Build `cortex_scheduler_config_t` and per‑plugin `cortex_plugin_config_t` (YAML + specs → struct mapping).
- Load plugins via `dlopen`/`dlsym` and register with the scheduler (only when `status: ready`; otherwise skipped).
- Start replayer; forward hop‑sized chunks to `cortex_scheduler_feed_samples`.
- Enforce warm‑up vs measured windows; run for duration and repeats.
- Record per‑window telemetry. Week 3: print timing to stdout and optionally write a basic CSV if a telemetry path is provided. (JSON writers and summaries are planned.)
- Apply realtime attributes (policy, priority, CPU affinity) with graceful degradation.
- Planned: background load (stress‑ng) and RAPL energy (Linux only).

### File Layout
- `src/harness/app/main.c` — CLI entrypoint; loads YAML; orchestrates lifecycle.
- `src/harness/config/config.{h,c}` — YAML parsing, kernel spec loading, and validation; mapping to structs.
- `src/harness/loader/loader.{h,c}` — `dlopen`/`dlsym` helpers; build `cortex_scheduler_plugin_api_t`.
- `src/harness/telemetry/telemetry.{h,c}` — Basic CSV writer (Week 3). JSON + summaries planned.
- `src/harness/util/util.{h,c}` — time helpers and run‑id utilities.
- `src/harness/Makefile` — builds `cortex` binary (links scheduler and replayer).
- Planned: `energy_rapl.{h,c}` (Linux) and `bg_load.{h,c}`.

Build notes: link with `-ldl -lpthread -lm` (and `-lrt` on some Linux distros if needed); guard RAPL and realtime with `#ifdef __linux__`.

### YAML + Spec → Struct Mapping
- **YAML parsing**: `dataset.*`, `realtime.*`, `benchmark.*`, `output.*`, `plugins[*].{name, spec_uri, spec_version, params}`.
- **Spec loading**: `kernels/v1/{name}@{dtype}/spec.yaml` → extracts `input_shape` (W), `dtype`, tolerances.
- **Runtime derivation**: `W` (from spec), `H = W/2`, `C` (from dataset), `dtype` (from spec).
- **Final mapping**:
  - `dataset.sample_rate_hz` → `cortex_replayer_config_t.sample_rate_hz`, `cortex_scheduler_config_t.sample_rate_hz`.
  - `dataset.channels` → `replayer.channels`, `scheduler.channels`, and all plugin configs.
  - `spec.input_shape[0]` → `scheduler.window_length_samples` and plugin config.
  - `spec.dtype` → ABI dtype and scheduler dtype.
  - `plugins[*].params` → passed to plugin `init()` as `kernel_params`.
  - `realtime.scheduler`/`priority`/`cpu_affinity` → `scheduler.scheduler_policy`/`realtime_priority`/`cpu_affinity_mask` (list → bitmask).
  - `benchmark.parameters.warmup_seconds` → `scheduler.warmup_seconds`.
  - `benchmark.parameters.duration_seconds`, `repeats` → harness loop control.
  - `output.directory`, `output.format` → telemetry writers.

Validation: enforce rules from `docs/RUN_CONFIG.md` (Fs>0, C>0, 0 < H ≤ W, channels match, DEADLINE fields if used, required fields for `status: ready`). Kernel specs are validated for compatibility with dataset parameters.

### Kernel Registry Integration

The harness loads kernel specifications from `kernels/v1/{name}@{dtype}/spec.yaml` to configure runtime parameters:

- **Spec discovery**: `plugins[*].spec_uri` references registry path (e.g., `"kernels/v1/car@f32"`)
- **Parameter extraction**: Loads `input_shape` (W), `dtype`, and validation tolerances
- **Runtime derivation**:
  - `window_length_samples = spec.input_shape[0]`
  - `hop_samples = window_length_samples / 2` (50% overlap default)
  - `channels = dataset.channels` (from YAML, not spec)
  - `dtype = spec.dtype`
- **Validation**: Ensures spec parameters are compatible with dataset and realtime constraints

### Run Lifecycle
1) Parse YAML config and validate per `docs/RUN_CONFIG.md`.
2) Load kernel specifications from registry for each plugin with `spec_uri`.
3) Derive runtime parameters (W, H, C, dtype) from specs + dataset config.
4) Initialize scheduler with derived parameters; compute warm‑up windows.
5) Load and register plugins with `status: ready` (skips all others). If none, run replayer→scheduler only.
6) Start replayer with callback that forwards chunks to scheduler.
7) Run until `duration_seconds` elapses; repeat `repeats` times.
8) Flush scheduler; stop replayer.
9) Telemetry: print timing to stdout; if an output directory is configured, write a basic CSV.
10) Teardown scheduler.

### Telemetry (per `docs/TELEMETRY.md`)
- Week 3: per‑window stdout logs and basic CSV (plugin, window_index, release_ts_ns, deadline_ts_ns, start_ts_ns, end_ts_ns, deadline_missed, W, H, C, Fs).
- Planned: run_id, dtype, load_profile, warmup flag, energy_j/power_mw, and summary aggregates (p50/p95/p99, miss rate).

### Background Load Profiles
- Planned: idle / medium / heavy mapped to stress‑ng (Linux). Disabled on non‑Linux.

### Cross‑Platform & Privileges
- Realtime (`SCHED_FIFO`), affinity, RAPL and stress‑ng are Linux‑specific; harness must degrade gracefully on macOS/CI.

### Quick Start
- Build: `make -C src/engine/harness`
- Run: `./src/engine/harness/cortex run primitives/configs/example.yaml`

### Immediate Milestones
- M2: JSON writer + summary computation.
- M3: RAPL energy (Linux), background load, and CLI flags for overrides.


