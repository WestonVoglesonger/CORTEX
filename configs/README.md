# Configuration Files

CORTEX configs define a full benchmark run and how each module behaves:

- **Replayer** — streams dataset samples at the true sampling rate **Fs**.
- **Scheduler** — slices the stream into fixed windows (**W**) with hop (**H**) and assigns release times and deadlines (**H/Fs**).
- **Harness** — loads plugins, calls `process()`, pins the worker thread, applies real-time policy, and times execution.
- **Kernel Plugin** — compiled shared library behind a tiny **C ABI** (`init(config)`, `process(in,out)`, `teardown`) for kernels like CAR, Notch IIR, FIR, Goertzel, etc.
- **Telemetry & Outputs** — per-window latency/throughput/jitter, memory, and energy (via RAPL); exports CSV/plots.
- **Reference Oracles** — SciPy/MNE correctness checks before timing.

The harness parses YAML and builds a small **ABI init struct** for each plugin. Plugins never read YAML; they only receive numeric runtime + kernel params via `init()`.

**EEG-first defaults:** Fs = 160 Hz, W = 160, H = 80, C = 64 (public EEG loaders). Set the per-window deadline to **H/Fs**. PC-only; energy is measured via RAPL.

---

## Files
- `cortex.yaml` — canonical run config for real experiments.
- `example.yaml` — tiny, fast config for smoke tests and CI.

---

## Top-level Schema (what each module uses)

### `system:`
- `name`, `description` — run identifiers (shown in outputs).

### `dataset:`  → **Replayer**
- `path` — dataset root/file the replayer will stream.
- `format` — loader hint (e.g., `raw`).
- `channels` — C; must match plugin runtime.
- `sample_rate_hz` — Fs; must match the dataset.

### `realtime:`  → **Harness**
- `scheduler: fifo | rr | deadline | other` — Linux policy (FIFO/RR are fixed-priority; DEADLINE enforces runtime/period/deadline).
- `priority: 1–99` — FIFO/RR priority (70–90 reduces jitter without starving the OS).
- `cpu_affinity: [cores...]` — pin worker to cores to reduce migration/jitter.
- `deadline_ms` — soft per-window budget; typically `1000 * hop / Fs`.
- `deadline: { runtime_us, period_us, deadline_us }` — only with `scheduler: deadline` (period ≈ hop/Fs).

### `power:`  → **Harness**
- `governor`, `turbo` — make timing/energy reproducible.

### `benchmark:`  → **Telemetry & Outputs**
- `metrics: [latency, jitter, throughput, memory_usage, energy_consumption]`
  - **latency** = last-sample arrival → output-ready (per window)
  - **jitter** = p95−p50, p99−p50
  - **throughput** = windows/sec
  - **memory_usage** = RSS + plugin state/workspace
  - **energy_consumption** = per-window joules (RAPL); derive **power** `P = E_window * Fs / H`
- `parameters: { duration_seconds, repeats, warmup_seconds }`
- `load_profile: idle | medium | heavy` — controlled background load

### `output:`  → **Telemetry & Outputs**
- `directory`, `format`, `include_raw_data` — where and how results are written.

### `plugins:`  → **Kernel Plugin** (feeds the ABI)
A list. Each entry defines one plugin/kernel to run.
- `name` — e.g., `car`, `notch_iir`, `fir_bandpass`, `goertzel`
- `status: draft | ready`, `spec_uri`, `spec_version` — bookkeeping while specs/oracles land
- `runtime:` (shared keys for all kernels)
  - `window_length_samples` (W), `hop_samples` (H), `channels` (C), `dtype` (`float32` now; `q15`/`q7` later), `allow_in_place`
- `params:` (kernel-specific; keep `{}` while draft)  
  examples: `{ f0_hz, Q }` for notch; `{ exclude_channels: [] }` for CAR
- `tolerances:` — abs/rel error thresholds vs. oracle (null while draft)
- `oracle:` — path to gold bundle (null while draft)

---

## Validation (harness should enforce)
- `dataset.sample_rate_hz > 0`, `dataset.channels > 0`
- For each plugin:
  - `0 < hop_samples ≤ window_length_samples`
  - `runtime.channels == dataset.channels`
- If `scheduler: deadline`, require `{ runtime_us, period_us, deadline_us }`
- If `status: ready`, require non-empty `params`, `tolerances`, and `oracle`
- Warn if privileges are insufficient for RT scheduling and fall back gracefully
