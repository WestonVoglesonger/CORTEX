# Configuration Files

CORTEX configs define a full benchmark run and how each **module** behaves:

- **Replayer** — streams dataset samples at the true sampling rate **Fs**. :contentReference[oaicite:0]{index=0}
- **Scheduler** — slices the stream into fixed windows (W) with hop (H) and assigns **release times** and **deadlines** (H/Fs). :contentReference[oaicite:1]{index=1}
- **Harness** — loads plugins, calls `process()`, pins the worker thread, applies real-time policy, and times execution. :contentReference[oaicite:2]{index=2}
- **Kernel Plugin** — compiled shared library behind a tiny **C ABI** (`init/config`, `process(in,out)`, `teardown`) for CAR, notch IIR, FIR, Goertzel, etc. :contentReference[oaicite:3]{index=3}
- **Telemetry & Outputs** — per-window latency/throughput/jitter, memory, and energy via RAPL; exports CSV/plots. :contentReference[oaicite:4]{index=4}
- **Reference Oracles** — SciPy/MNE correctness checks before timing. :contentReference[oaicite:5]{index=5}

The harness parses YAML and builds a small **ABI init struct** for each plugin. Plugins never read YAML; they only receive numeric runtime + kernel params via `init()`. :contentReference[oaicite:6]{index=6}

**EEG-first defaults:** Fs=160 Hz, W=160, H=80, C=64 (public EEG loaders). Set the **deadline** to H/Fs. PC-only; energy from RAPL. :contentReference[oaicite:7]{index=7}

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
- `sample_rate_hz` — **Fs**; must match the dataset. :contentReference[oaicite:8]{index=8}

### `realtime:`  → **Harness**
- `scheduler: fifo|rr|deadline|other` — Linux policy (FIFO/RR are fixed-priority; DEADLINE enforces runtime/period/deadline).
- `priority: 1–99` — only for FIFO/RR (pick 70–90 to avoid starvation).
- `cpu_affinity: [cores...]` — pin worker to cores to reduce migration/jitter.
- `deadline_ms` — soft budget per window; typically `1000 * hop / Fs`.
- `deadline: { runtime_us, period_us, deadline_us }` — only for `scheduler: deadline` (period ≈ hop/Fs). :contentReference[oaicite:9]{index=9}

### `power:`  → **Harness**
- `governor`, `turbo` — make timing/energy reproducible.

### `benchmark:`  → **Telemetry & Outputs**
- `metrics: [latency, jitter, throughput, memory_usage, energy_consumption]`
  - **latency** = last-sample-arrival → output-ready (per window),
  - **jitter** = p95−p50, p99−p50,
  - **energy** = per-window joules (RAPL), derive **power** `P = E_window * Fs / H`. :contentReference[oaicite:10]{index=10}
- `parameters: { duration_seconds, repeats, warmup_seconds }`
- `load_profile: idle|medium|heavy` — controlled background load.

### `output:`  → **Telemetry & Outputs**
- `directory`, `format`, `include_raw_data` — where and how results are written.

### `plugins:`  → **Kernel Plugin** (feeds the ABI)
Each entry defines one kernel plugin to run.
- `name` — e.g., `car`, `notch_iir`, `fir_bandpass`, `goertzel`.
- `status: draft|ready`, `spec_uri`, `spec_version` — bookkeeping while specs/oracles land.
- `runtime:` (shared keys)
  - `window_length_samples` (W), `hop_samples` (H), `channels` (C), `dtype` (`float32` now; `q15/q7` later), `allow_in_place`.
- `params:` (kernel-specific; keep `{}` while draft)  
  examples: `{ f0_hz, Q }` for notch; `{ exclude_channels: [] }` for CAR.
- `tolerances:` — abs/rel error thresholds versus oracle (null while draft).
- `oracle:` — path to gold bundle (null while draft). :contentReference[oaicite:11]{index=11}

---

## Validation (harness should enforce)
- `dataset.sample_rate_hz > 0`, `dataset.channels > 0`.
- For each plugin: `0 < hop_samples ≤ window_length_samples`, and `runtime.channels == dataset.channels`.
- If `scheduler: deadline`, require `{runtime_us, period_us, deadline_us}`.
- If `status: ready`, require non-empty `params`, `tolerances`, and `oracle`. :contentReference[oaicite:12]{index=12}
