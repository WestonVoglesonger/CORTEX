# Synthetic Dataset Generation Guide

## Overview

Synthetic dataset generation allows CORTEX to validate kernel performance at scales beyond publicly available datasets. This guide explains the conceptual differences between static and generator-based datasets, and how to use them effectively.

## Dataset Primitives: Two Types

### Static Datasets

**Traditional model:** A dataset is a collection of pre-recorded data files.

```
primitives/datasets/v1/physionet-motor-imagery/
├── spec.yaml                # Metadata
├── converted/               # Pre-generated .float32 files
│   └── S001R03.float32     # Static data (4.9 MB)
└── README.md
```

**Characteristics:**
- Files exist before benchmarking
- Content is immutable after release
- Path uniquely identifies content
- Example: PhysioNet EEG recordings

**Usage:**
```yaml
dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  format: "float32"
  channels: 64
  sample_rate_hz: 160
```

### Generator Datasets

**New model:** A dataset is a *parametric function* that produces data on-demand.

```
primitives/datasets/v1/synthetic/
├── spec.yaml           # Parameter schema
├── generator.py        # Generation function
├── README.md
└── examples/           # Example configs
```

**Characteristics:**
- Files generated at benchmark time
- Content determined by parameters (function arguments)
- Path identifies *generator*, not content
- Example: Synthetic pink noise, sine waves

**Usage:**
```yaml
dataset:
  path: "primitives/datasets/v1/synthetic"  # Points to generator
  params:                                    # Function arguments
    signal_type: "pink_noise"
    duration_s: 120
    amplitude_uv_rms: 100.0
    seed: 42
  channels: 1024
  sample_rate_hz: 160
```

## Key Conceptual Distinction

### Static Primitives: 1:1 Mapping

```
path → data (immutable)
```

Once released, `v1/physionet-motor-imagery/S001R03.float32` always contains the same bytes.

### Generator Primitives: Function Evaluation

```
(path, params) → data (deterministic but parametric)
```

The generator code at `v1/synthetic/` is immutable, but the *data it produces* depends on parameters. Different params = different data from same generator.

**Example:**
```yaml
# Configuration A
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "sine_wave"
    frequency_hz: 10.0
  channels: 64

# Configuration B
dataset:
  path: "primitives/datasets/v1/synthetic"  # SAME path
  params:
    signal_type: "pink_noise"                 # DIFFERENT params
  channels: 1024                              # DIFFERENT data
```

Both use the same generator primitive, but produce entirely different datasets.

## Reproducibility Model

### For Static Datasets

**Path is sufficient:** If you know the path, you can retrieve the exact data.

```yaml
dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
# This fully specifies the dataset
```

### For Generator Datasets

**Path + params required:** You need both the generator and its parameters.

```yaml
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "pink_noise"
    duration_s: 120
    seed: 42
  channels: 1024
  sample_rate_hz: 160
# All of this is needed to reproduce the dataset
```

**Solution:** CORTEX automatically saves a generation manifest to results:

```
results/run-<timestamp>/
└── dataset/
    └── generation_manifest.yaml  # Complete reproduction recipe
```

The manifest contains:
- Generator primitive path and version
- All generation parameters
- Output characteristics (channels, samples, file size)
- Timestamp for audit trail

**To reproduce a run:**
1. Load the generation manifest
2. Extract parameters
3. Re-run generator with same parameters (same platform → bitwise identical; cross-platform → statistically equivalent)

## When to Use Each Type

### Use Static Datasets When:

- You need real EEG data with natural artifacts and variability
- You're validating against published research using standard datasets
- You want to compare results with other researchers
- Dataset size is manageable (<500 MB)

**Example:** Oracle validation with PhysioNet

### Use Generator Datasets When:

- You need channel counts beyond public datasets (>128 channels)
- You want controlled signal properties (known frequencies, amplitudes)
- You need deterministic test data for CI/CD
- You want to test edge cases (DC offsets, NaN injection)
- Storage is a constraint (generate on-demand vs storing GB files)

**Example:** Scalability testing at 1024 channels (Neuralink scale)

## Workflow Differences

### Static Dataset Workflow

```bash
# 1. Download dataset once
cortex download physionet

# 2. Run benchmark many times
cortex run --config my_config.yaml  # Uses pre-downloaded data
cortex run --config my_config.yaml  # Same data, instant start
```

**Characteristics:**
- One-time download cost
- Zero generation overhead
- Consistent across all runs

### Generator Dataset Workflow

```bash
# Run benchmark (generation happens automatically)
cortex run --config my_config.yaml
# [cortex] Detected synthetic dataset generator
# [cortex] Generating pink_noise signal...
# [cortex] 1024ch × 19200 samples... 100% complete
# [cortex] Generated file: /tmp/cortex_gen_abc123.float32
# [cortex] Running harness...
```

**Characteristics:**
- Generation on every run (unless you pregenerate)
- Small overhead (e.g., 5 seconds for 1024ch × 120s)
- Parameters can vary per run

### Pregeneration Strategy

To avoid regeneration overhead, you can pregenerate and use as static:

```bash
# Generate once
python primitives/datasets/v1/synthetic/generator.py \\
  pink_noise 1024 160 120.0 /tmp/test_data.float32 \\
  --amplitude_uv_rms=100 --seed=42

# Use many times
cortex run --config <(cat <<EOF
dataset:
  path: "/tmp/test_data.float32"
  format: "float32"
  channels: 1024
  sample_rate_hz: 160
# ... rest of config
EOF
)
```

## Versioning and Immutability

### Static Datasets

**Primitive is the data:**
- `v1/physionet-motor-imagery/S001R03.float32` never changes after release
- New recordings → create `v2/physionet-motor-imagery/` with new files

### Generator Datasets

**Primitive is the code:**
- `v1/synthetic/generator.py` never changes after release
- Different signal properties → change *parameters*, not code
- Algorithm improvements → create `v2/synthetic/` with new generator.py

**Example evolution:**
```
v1/synthetic/generator.py:
  - Supports: sine_wave, pink_noise
  - Algorithm: FFT-based pink noise

v2/synthetic/generator.py:  # Future
  - Supports: sine_wave, pink_noise, white_noise, chirp
  - Algorithm: Improved autoregressive pink noise (faster)
  - New parameters: dc_offset, nan_rate
```

Users specify which version in their config:
```yaml
dataset:
  path: "primitives/datasets/v2/synthetic"  # Explicit version
```

## Performance Characteristics

### Memory Usage

|  Approach | 64ch | 512ch | 1024ch | 2048ch |
|-----------|------|-------|--------|--------|
| **Static** (load file) | 2.5 MB RAM | 20 MB | 40 MB | 80 MB |
| **Generator** (low-ch) | 2.5 MB RAM | 20 MB | N/A | N/A |
| **Generator** (high-ch) | N/A | N/A | <150 MB | <200 MB |

High-channel generator uses chunked generation with memory-mapped output, keeping RAM usage constant regardless of output size.

### Generation Time

| Channel Count | File Size | Generation Time |
|---------------|-----------|-----------------|
| 64 | 2.5 MB | <1s |
| 256 | 9.8 MB | ~1s |
| 512 | 19.7 MB | ~2s |
| 1024 | 39.3 MB | ~5s |
| 2048 | 78.6 MB | ~10s |

*Measured on Apple M2 Max with vectorized FFT implementation*

### Comparison

**Static datasets:**
- ✓ Zero generation overhead
- ✓ Consistent across runs
- ✗ Storage cost (GB-scale for high-channel)
- ✗ Limited to available recordings

**Generator datasets:**
- ✓ Minimal storage (just code)
- ✓ Arbitrary channel counts
- ✓ Controlled signal properties
- ✗ Generation overhead (~5s for 1024ch)
- ✗ Requires NumPy/SciPy

## Best Practices

### 1. Always Save Manifests

Generation manifests are your reproducibility lifeline. Never delete them.

```bash
# Good: Keep results directory
results/run-2026-01-12-153000/
└── dataset/generation_manifest.yaml  # ← KEEP THIS

# Bad: Delete results after extracting telemetry
rm -rf results/run-*  # ← DON'T DO THIS
```

### 2. Document Your Seeds

For scientific work, document your random seeds in publications:

> "Synthetic datasets were generated using CORTEX v1.0 synthetic generator with pink noise (seed=42, amplitude RMS=100µV, 1024 channels, 120s duration)."

### 3. Validate Once, Benchmark Many

If using generators for kernel validation:
1. Generate dataset once
2. Manually verify properties (FFT spectrum, amplitude, etc.)
3. Pregenerate file for repeated use
4. This avoids questioning "was the bug in the kernel or generator?"

### 4. Use Explicit Versions

Don't rely on implicit versioning:

```yaml
# Good: Explicit version
dataset:
  path: "primitives/datasets/v1/synthetic"

# Bad: Implicit (what if v2 exists?)
dataset:
  path: "primitives/datasets/synthetic"  # Which version?
```

### 5. Test Cross-Platform Reproducibility

If sharing results across platforms:
```python
# Test that statistical properties match
data1 = generate(..., seed=42)  # Platform A
data2 = generate(..., seed=42)  # Platform B

assert np.isclose(data1.mean(), data2.mean(), rtol=1e-9)
assert np.isclose(data1.std(), data2.std(), rtol=1e-9)
# Bitwise identity not guaranteed (FFT library differences)
```

## Troubleshooting

### "Generator returned file path but harness expects array"

**Cause:** High-channel mode returns file path, but old code expects ndarray.

**Solution:** Update to latest CORTEX CLI which handles both return types.

### "Channels mismatch: params.channels != dataset.channels"

**Cause:** Specified channels in two places.

**Solution:** Only specify in `dataset.channels`, not `dataset.params.channels`:

```yaml
# Wrong:
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    channels: 1024  # ← Remove this
  channels: 1024

# Correct:
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "pink_noise"
  channels: 1024  # ← Only here
```

### "Generation too slow"

**Options:**
1. Pregenerate file and use as static dataset
2. Reduce duration or channel count
3. Check CPU governor (use `performance` on Linux)
4. Upgrade to v2 generator with faster algorithms (future)

### "Manifest not found in results"

**Cause:** Generator integration not called, or run failed before manifest save.

**Solution:** Ensure you're using `cortex run` (not direct harness invocation). Check that run completed successfully.

## See Also

- `primitives/datasets/v1/synthetic/README.md` - Technical details
- `primitives/datasets/v1/synthetic/examples/` - Example configurations
- `experiments/high-channel-scalability-2026-01-XX/` - Scalability benchmarking results
- `docs/reference/configuration.md` - YAML configuration reference
