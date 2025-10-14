## Harness Module

Purpose: Orchestrate replayer → scheduler → plugins behind the stable ABI, apply runtime policy (affinity/scheduling), persist telemetry, and manage run lifecycle per `docs/RUN_CONFIG.md` and `docs/TELEMETRY.md`.

### Responsibilities
- Parse YAML config (`configs/*.yaml`) and validate per `docs/RUN_CONFIG.md`.
- Build `cortex_scheduler_config_t` and per‑plugin `cortex_plugin_config_t` (YAML → struct mapping).
- Load plugins via `dlopen`/`dlsym` and register with the scheduler (only when `status: ready`; otherwise skipped).
- Start replayer; forward hop‑sized chunks to `cortex_scheduler_feed_samples`.
- Enforce warm‑up vs measured windows; run for duration and repeats.
- Record per‑window telemetry. Week 3: print timing to stdout and optionally write a basic CSV if a telemetry path is provided. (JSON writers and summaries are planned.)
- Apply realtime attributes (policy, priority, CPU affinity) with graceful degradation.
- Planned: background load (stress‑ng) and RAPL energy (Linux only).

### File Layout
- `src/harness/app/main.c` — CLI entrypoint; loads YAML; orchestrates lifecycle.
- `src/harness/config/config.{h,c}` — YAML parsing and validation; mapping to structs.
- `src/harness/loader/loader.{h,c}` — `dlopen`/`dlsym` helpers; build `cortex_scheduler_plugin_api_t`.
- `src/harness/telemetry/telemetry.{h,c}` — Basic CSV writer (Week 3). JSON + summaries planned.
- `src/harness/util/util.{h,c}` — time helpers and run‑id utilities.
- `src/harness/Makefile` — builds `cortex` binary (links scheduler and replayer).
- Planned: `energy_rapl.{h,c}` (Linux) and `bg_load.{h,c}`.

Build notes: link with `-ldl -lpthread -lm` (and `-lrt` on some Linux distros if needed); guard RAPL and realtime with `#ifdef __linux__`.

### YAML → Struct Mapping
- `dataset.sample_rate_hz` → `cortex_replayer_config_t.sample_rate_hz`, `cortex_scheduler_config_t.sample_rate_hz`.
- `dataset.channels` → `replayer.channels`, `scheduler.channels`.
- `plugins[*].runtime.window_length_samples` → `scheduler.window_length_samples` and plugin config.
- `plugins[*].runtime.hop_samples` → `scheduler.hop_samples` and plugin config.
- `plugins[*].runtime.dtype` → ABI dtype (float32 initial).
- `realtime.scheduler`/`priority`/`cpu_affinity` → `scheduler.scheduler_policy`/`realtime_priority`/`cpu_affinity_mask` (list → bitmask).
- `benchmark.parameters.warmup_seconds` → `scheduler.warmup_seconds`.
- `benchmark.parameters.duration_seconds`, `repeats` → harness loop control.
- `output.directory`, `output.format` → telemetry writers.

Validation: enforce rules from `docs/RUN_CONFIG.md` (Fs>0, C>0, 0 < H ≤ W, channels match, DEADLINE fields if used, required fields for `status: ready`).

### Run Lifecycle
1) Parse YAML; validate.
2) Initialize scheduler; compute warm‑up windows.
3) Load and register plugins with `status: ready` (skips all others). If none, run replayer→scheduler only.
4) Start replayer with callback that forwards chunks to scheduler.
5) Run until `duration_seconds` elapses; repeat `repeats` times.
6) Flush scheduler; stop replayer.
7) Telemetry: print timing to stdout; if an output directory is configured, write a basic CSV.
8) Teardown scheduler.

### Telemetry (per `docs/TELEMETRY.md`)
- Week 3: per‑window stdout logs and basic CSV (plugin, window_index, release_ts_ns, deadline_ts_ns, start_ts_ns, end_ts_ns, deadline_missed, W, H, C, Fs).
- Planned: run_id, dtype, load_profile, warmup flag, energy_j/power_mw, and summary aggregates (p50/p95/p99, miss rate).

### Background Load Profiles
- Planned: idle / medium / heavy mapped to stress‑ng (Linux). Disabled on non‑Linux.

### Cross‑Platform & Privileges
- Realtime (`SCHED_FIFO`), affinity, RAPL and stress‑ng are Linux‑specific; harness must degrade gracefully on macOS/CI.

### Quick Start
- Build: `make -C src/harness`
- Run: `./src/harness/cortex run configs/example.yaml`

### Immediate Milestones
- M2: JSON writer + summary computation.
- M3: RAPL energy (Linux), background load, and CLI flags for overrides.


