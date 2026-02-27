# Synthetic Dataset Generation Guide

## Overview

Synthetic dataset generation allows CORTEX to validate kernel performance at scales beyond publicly available datasets (e.g., 1024+ channels for Neuralink-scale BCI). This guide explains how to create and use synthetic datasets.

## Quick Start

1. Create a directory and write a `spec.yaml`:

```bash
mkdir my-dataset
```

```yaml
# my-dataset/spec.yaml
dataset:
  name: synthetic-pink-noise-256ch

format:
  channels: 256
  sample_rate_hz: 160.0
  window_length: 160

generation_parameters:
  signal_type: pink_noise
  duration_s: 10.0
  seed: 42
  amplitude_uv_rms: 100.0
```

2. Generate the data:

```bash
cortex generate --spec my-dataset/spec.yaml
```

3. Use the dataset:

```bash
cortex calibrate --kernel csp --dataset my-dataset --output state.cortex_state
```

The `spec.yaml` is both the input config and the output metadata — one artifact for reproducibility.

## Spec Format

### Required Fields

```yaml
format:
  channels: 64              # Number of channels (1-4096)

generation_parameters:
  signal_type: pink_noise   # "pink_noise" or "sine_wave"
  duration_s: 10.0          # Duration in seconds
```

### Optional Fields

```yaml
format:
  sample_rate_hz: 160.0     # Default: 160.0
  window_length: 160        # Default: 160

generation_parameters:
  seed: 42                  # Default: 42 (for reproducibility)
```

### Signal-Specific Parameters

**Pink noise** (1/f spectrum, realistic EEG):
```yaml
generation_parameters:
  signal_type: pink_noise
  amplitude_uv_rms: 100.0   # RMS amplitude in µV (default: 100.0)
```

**Sine wave** (known frequency, for filter validation):
```yaml
generation_parameters:
  signal_type: sine_wave
  frequency_hz: 10.0        # Required for sine_wave
  amplitude_uv_peak: 100.0  # Peak amplitude in µV (default: 100.0)
```

## Dataset Types

### Static Datasets

Pre-recorded data files. Path uniquely identifies content.

```
primitives/datasets/v1/physionet-motor-imagery/
├── spec.yaml
├── converted/S001R03.float32
└── README.md
```

### Generator Datasets

Parametric function that produces data on-demand. Same generator, different parameters = different data.

```
my-dataset/
├── spec.yaml          # You write this
└── data.float32       # cortex generate creates this
```

Both types produce the same primitive shape: `spec.yaml` + binary data.

## Reproducibility

The `spec.yaml` IS the reproducibility record. To reproduce a dataset:

```bash
# Same spec → same data (deterministic via seed)
cortex generate --spec my-dataset/spec.yaml
```

Cross-platform: same seed produces statistically equivalent output (bitwise identity not guaranteed due to FFT library differences).

## What Happens After Generation

After running `cortex generate`, the command backfills computed fields into your spec:

```yaml
# These are added automatically:
dataset:
  type: generated
  generator_primitive: primitives/datasets/v1/synthetic
  generation_timestamp: "2026-02-27T..."

format:
  type: float32
  layout: interleaved
  endian: little

recordings:
  - id: data
    path: data.float32
    duration_seconds: 10.0
    samples_per_channel: 1600
    units: "microvolts (µV)"
```

## Performance

### Memory Usage

| Channels | Approach | RAM |
|----------|----------|-----|
| ≤512 | In-memory | Proportional to data |
| >512 | Chunked + memmap | <200 MB constant |

### Generation Time

| Channels | File Size | Time |
|----------|-----------|------|
| 64 | 2.5 MB | <1s |
| 256 | 9.8 MB | ~1s |
| 1024 | 39.3 MB | ~5s |
| 2048 | 78.6 MB | ~10s |

*Measured on Apple M2 Max*

## When to Use Synthetic Data

**Use synthetic when:**
- Channel counts beyond public datasets (>128 channels)
- Controlled signal properties (known frequencies, amplitudes)
- Deterministic test data for CI/CD
- Storage is a constraint

**Use real data when:**
- Validating against published research
- Need natural EEG artifacts and variability
- Comparing results with other researchers

## Examples

### Filter Validation (Sine Wave)

```yaml
# filter-test/spec.yaml
dataset:
  name: filter-validation-10hz

format:
  channels: 64
  sample_rate_hz: 160.0

generation_parameters:
  signal_type: sine_wave
  frequency_hz: 10.0
  amplitude_uv_peak: 100.0
  duration_s: 30
  seed: 42
```

### High-Channel Scalability (Pink Noise)

```yaml
# neuralink-scale/spec.yaml
dataset:
  name: scalability-1024ch

format:
  channels: 1024
  sample_rate_hz: 160.0

generation_parameters:
  signal_type: pink_noise
  amplitude_uv_rms: 100.0
  duration_s: 120
  seed: 42
```

## See Also

- `primitives/datasets/v1/synthetic/README.md` — Generator implementation details
- `docs/reference/configuration.md` — YAML configuration reference
