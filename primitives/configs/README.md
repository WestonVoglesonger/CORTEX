# Configuration Files

This folder holds runnable configs for CORTEX. Use these to launch benchmarks; see the docs for the full schema.

## Files
- `cortex.yaml` – canonical run config for real experiments
- `example.yaml` – tiny config for smoke tests/CI

## Quick start
1. Set your dataset in `dataset.path` and verify `sample_rate_hz` & `channels`.
2. Keep EEG v1 defaults unless your data differs: Fs=160, W=160, H=80, C=64.
3. Set `realtime.deadline_ms = 1000 * H / Fs` (EEG v1 → 500 ms).
4. Define one or more `plugins:` blocks; params may be `{}` while specs are draft.

## How YAML maps to the plugin ABI
The harness converts:
- `dataset.sample_rate_hz` → `config.sample_rate_hz`
- `plugins[*].runtime.{window_length_samples,hop_samples,channels,dtype,allow_in_place}` → fields in the ABI init struct
- `plugins[*].params` → a plugin-specific params struct passed as `kernel_params`

## See also
- **Run config spec** (authoritative): `docs/RUN_CONFIG.md`
- **Telemetry spec** (metrics, files): `docs/TELEMETRY.md`
- **Plugin ABI** (header + rules): `docs/PLUGIN_INTERFACE.md`, `include/cortex/plugin.h`
