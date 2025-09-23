# Configuration Files

CORTEX configs define a full benchmark run: dataset replay, real-time policy, telemetry, and which kernel plugins to execute.  
The harness reads this YAML and constructs a small ABI init struct for each plugin.  
Plugins never read YAML directly — they get only the numeric runtime + kernel params.  

**Defaults:** For EEG-first experiments we fix Fs=160 Hz, W=160 samples, H=80 samples, and C=64 channels (from public datasets). These values flow into the ABI init struct passed to each plugin. See `/docs/Proposal.pdf` and `/docs/ImplementationPlan.pdf` for the design rationale.


## Files
- `cortex.yaml` — canonical run config for real experiments.
- `example.yaml` — tiny, fast config for smoke tests and CI.

---

## Top‑level Schema

### `cortex_version: <int>`
Config format version for compatibility checks.

### `system:`
- `name: <string>` — run identifier (appears in outputs).
- `description: <string>` — freeform description.

### `dataset:`
- `path: <string>` — dataset root or file. Harness replays samples from here at the true Fs.  :contentReference[oaicite:4]{index=4}
- `format: <string>` — e.g., `raw` (your loader decides).
- `channels: <int>` — C; channel count expected by windows and plugins.
- `sample_rate_hz: <int>` — Fs; **must** match the dataset (e.g., 160 for EEG in v1).  :contentReference[oaicite:5]{index=5}

### `realtime:`  *(harness-only)*
Controls how the worker thread is scheduled while processing windows.
- `scheduler: fifo | rr | deadline | other` — Linux policy (FIFO/RR are fixed‑priority; DEADLINE enforces runtime/period/deadline).
- `priority: <1–99>` — only for `fifo/rr`. High (70–90) reduces jitter without starving the OS.
- `cpu_affinity: [<int> ...]` — pin worker to specific cores to reduce migration/jitter.
- `deadline_ms: <int>` — soft budget per window; typically `1000 * hop / Fs`. Your harness logs deadline misses.  :contentReference[oaicite:6]{index=6}
- `deadline:` *(only with `scheduler: deadline`)*  
  - `runtime_us` — CPU time granted per period.  
  - `period_us` — window arrival period (≈ hop/Fs).  
  - `deadline_us` — absolute completion deadline within the period.
  
The proposal/plan sets **release time and deadline = H/Fs** for each window and uses pinned threads with optional RT policy; mirror that here.  :contentReference[oaicite:7]{index=7} :contentReference[oaicite:8]{index=8}

### `power:`  *(harness-only)*
- `governor: "performance"|...` — lock frequency for stable timing/energy.
- `turbo: true|false` — disable turbo to reduce run‑to‑run variance.

### `benchmark:`  *(harness-only)*
- `metrics: [latency, jitter, throughput, memory_usage, energy_consumption]`  
  What gets recorded per window:
  - **latency** — time from last input sample arrival to output‑ready (per window).
  - **jitter** — tail‑minus‑median (report p95−p50 and p99−p50).  :contentReference[oaicite:9]{index=9}
  - **throughput** — windows/sec or samples/sec processed.
  - **memory_usage** — peak/steady RSS plus plugin‑reported state/workspace bytes.
  - **energy_consumption** — `E_window` via RAPL around `process()`; derive **power** `P = E_window * Fs / H` (mW).  :contentReference[oaicite:10]{index=10}
- `parameters:`  
  - `duration_seconds` — total replay time.  
  - `repeats` — number of full runs for variance estimates.  
  - `warmup_seconds` — skipped at start to stabilise caches/branch predictors.  :contentReference[oaicite:11]{index=11}
- `load_profile: idle|medium|heavy` — background load via stressor to test robustness.  :contentReference[oaicite:12]{index=12}

### `output:`  *(harness-only)*
- `directory: <string>` — where CSV/JSON results go.
- `format: "json"|"csv"|...` — primary format; plots are separate.
- `include_raw_data: true|false` — include raw per‑window samples (usually false).

---

## `plugins:`  *(feeds the C ABI init for each kernel)*
A list. Each entry defines **one plugin** to run.

- `name: <string>` — kernel identifier (e.g., `car`, `notch_iir`, `fir_bandpass`, `goertzel`).
- `status: draft|ready` — harness can warn/skip drafts in strict modes.
- `spec_uri: <string|null>` — link to the math spec once written.
- `spec_version: <string|null>` — spec revision (e.g., `v0.1`).

**`runtime:`** *(all kernels share these keys)*
- `window_length_samples` — W; window size. The proposal defaults to **W=160** for EEG v1.  :contentReference[oaicite:13]{index=13}
- `hop_samples` — H; step between consecutive windows (overlap if `H < W`). Default **H=80** for EEG v1.  :contentReference[oaicite:14]{index=14}
- `channels` — C; must equal `dataset.channels` (e.g., 64).  :contentReference[oaicite:15]{index=15}
- `dtype` — `"float32"` (default in v1); plan for fixed‑point (`"q15"`, `"q7"`) later.  :contentReference[oaicite:16]{index=16}
- `allow_in_place` — whether `process(in, out)` may alias buffers.

**`params:`** *(kernel‑specific; empty when draft)*  
Examples:
- `notch_iir`: `{ f0_hz, Q }`  
- `car`: `{ exclude_channels: [] }`  
- `fir_bandpass`: `{ low_hz, high_hz, num_taps, window_type }`  
- `goertzel`: `{ bins_hz: [ ... ] }`  
Person 2 will pin these mathematically and provide oracles/tolerances; until then, keep them `{}` with `status: draft`.  :contentReference[oaicite:17]{index=17}

**`tolerances:`** *(abs/rel error thresholds vs. oracle; null while draft)*

**`oracle:`** *(path to gold bundle inputs/outputs; null while draft)*

---

## Validation Rules (what the harness should check)
- `dataset.sample_rate_hz > 0`, `dataset.channels > 0`.
- For each plugin:  
  - `runtime.channels == dataset.channels`.  
  - `0 < hop_samples ≤ window_length_samples`.  
  - If `deadline_ms` omitted and you want one, compute `deadline_ms = 1000 * hop_samples / sample_rate_hz`.  :contentReference[oaicite:18]{index=18}
- If `scheduler: deadline`, require `deadline.runtime_us/period_us/deadline_us`.
- If `status: ready`, require non‑empty `params`, `tolerances`, and an `oracle`.  :contentReference[oaicite:19]{index=19}
- Warn if privileges are insufficient to apply RT policy; fall back to `SCHED_OTHER`.

---

## Defaults for EEG‑first v1 (for quick starts)
The proposal/plan fixes **Fs=160 Hz, W=160, H=80, C=64** to match public EEG loaders; use these unless your dataset differs. Real‑time deadlines are set from `H/Fs`, and all runs are PC‑only on x86/Linux with per‑window energy from RAPL.  :contentReference[oaicite:20]{index=20} :contentReference[oaicite:21]{index=21}
