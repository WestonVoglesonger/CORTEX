# Synthetic Dataset Generator

Universal signal generator for CORTEX scalability testing and validation.

## Overview

This generator primitive creates synthetic EEG-like signals for testing kernel performance at scales beyond publicly available datasets. Primary use case: validate CORTEX at modern BCI hardware scales (256-2048 channels) where no public datasets exist.

## Signal Types

### 1. Pink Noise (`pink_noise`)

1/f noise with realistic EEG spectral properties.

**Algorithm:** FFT-based spectrum shaping
**Amplitude:** RMS (root mean square) of zero-mean signal
**Use case:** Scalability benchmarking, realistic signal statistics

**Example:**
```yaml
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "pink_noise"
    duration_s: 120
    amplitude_uv_rms: 100.0
    seed: 42
  channels: 1024
  sample_rate_hz: 160
```

### 2. Sine Wave (`sine_wave`)

Pure sinusoidal waveform at specified frequency.

**Amplitude:** Peak amplitude (signal ranges from -amp to +amp)
**Use case:** Filter validation (passband preservation, stopband rejection)

**Example:**
```yaml
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "sine_wave"
    frequency_hz: 10.0
    duration_s: 30
    amplitude_uv_peak: 100.0
    seed: 42
  channels: 64
  sample_rate_hz: 160
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `signal_type` | string | **required** | "sine_wave" or "pink_noise" |
| `duration_s` | float | **required** | Total duration in seconds |
| `frequency_hz` | float | 10.0 | Sine frequency (sine_wave only) |
| `amplitude_uv_peak` | float | 100.0 | Peak amplitude in µV (sine_wave only) |
| `amplitude_uv_rms` | float | 100.0 | RMS amplitude in µV (pink_noise only) |
| `seed` | integer | 42 | Random seed for reproducibility |

**Note:** Amplitude semantics differ by signal type:
- **Sine wave:** Peak amplitude (signal = `amp * sin(2πft)`)
- **Pink noise:** RMS amplitude (std dev of zero-mean signal)

## Memory Characteristics

### High-Channel Generation (>512 channels)

- **Algorithm:** Chunked generation with memory-mapped output
- **Batch size:** 128 channels per iteration
- **Peak transient memory:** ~60-80 MB per batch (float64 FFT workspace)
- **Output:** Disk-backed (memmap), not loaded into RAM
- **Scalability:** Generates 2048ch × 120s (631 MB) with <200 MB peak RAM

**Example:**
```bash
# Generate 2048-channel dataset
python primitives/datasets/v1/synthetic/generator.py \\
  pink_noise 2048 160 60.0 output.float32 \\
  --amplitude_uv_rms=100 --seed=42

# Output: 2048ch × 9600 samples × 4 bytes = 78.6 MB file
# Peak RAM: <200 MB during generation
```

### Low-Channel Generation (≤512 channels)

- **Algorithm:** Full in-memory generation
- **Memory:** Entire dataset in RAM (e.g., 512ch × 19200 samples × 4 bytes = 39 MB)
- **Speed:** Slightly faster (no disk I/O)
- **Return type:** Returns `np.ndarray` directly

## Reproducibility

### Same Platform

**Identical seed produces bitwise-identical output** (within NumPy floating-point precision).

```python
gen = SyntheticGenerator()
data1 = gen.generate("pink_noise", 64, 160, 1.0, {'seed': 42})
data2 = gen.generate("pink_noise", 64, 160, 1.0, {'seed': 42})
np.array_equal(data1, data2)  # True (on same platform)
```

### Cross-Platform

**Identical seed produces statistically equivalent output:**
- Same mean, std dev, RMS
- Same spectral properties (1/f slope for pink noise)
- Minor numerical differences (<1e-6 relative error) due to FFT library variations (MKL vs OpenBLAS vs FFTW)

**Recommendation:** For validation testing, use fixed seeds and compare on same platform. For scalability benchmarking, statistical properties are sufficient.

## Usage Examples

### High-Channel Scalability Testing

```yaml
# cortex_scalability_test.yaml
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "pink_noise"
    duration_s: 120
    amplitude_uv_rms: 100.0
    seed: 42
  channels: 1024
  sample_rate_hz: 160

kernels:
  - name: "ica"
    deadline_us: 500000
```

```bash
cortex run cortex_scalability_test.yaml
# Generation: ~10 seconds for 1024ch × 120s
# Benchmark: Results in results/run-<timestamp>/
# Manifest: results/run-<timestamp>/dataset/generation_manifest.yaml
```

### Filter Validation

```yaml
# cortex_filter_validation.yaml
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "sine_wave"
    frequency_hz: 10.0
    duration_s: 30
    amplitude_uv_peak: 100.0
  channels: 64
  sample_rate_hz: 160

kernels:
  - name: "bandpass_fir"  # Passband: 8-30Hz
    deadline_us: 500000
```

Expected result: Output preserves 10Hz signal (in passband).

### Command-Line Generation

```bash
# Generate 2048-channel pink noise
python primitives/datasets/v1/synthetic/generator.py \\
  pink_noise 2048 160 60.0 /tmp/test_data.float32 \\
  --amplitude_uv_rms=100 --seed=42

# Use in benchmark
cortex run --dataset /tmp/test_data.float32
```

## Technical Details

### FFT-Based Pink Noise

**Algorithm:**
1. Generate complex white noise in frequency domain: `N(0,1) + i*N(0,1)`
2. Shape spectrum as `1/sqrt(f)` for pink noise (-3dB/octave)
3. Set DC bin to zero (no DC offset)
4. Inverse FFT to time domain
5. Enforce zero-mean (subtract sample mean)
6. Normalize to target RMS: `signal * (target_rms / actual_rms)`

**Vectorization:**
- All channels in a batch processed simultaneously
- Single `np.fft.irfft()` call for entire batch (axis=1)
- ~10× faster than per-channel loop

**RNG:** Uses `np.random.default_rng()` (modern Generator API, not legacy `np.random.seed()`).

### Sine Wave

**Simple implementation:**
```python
t = np.arange(n_samples) / sample_rate_hz
signal = amplitude_uv_peak * np.sin(2 * np.pi * frequency_hz * t)
```

Replicated across all channels (identical signal per channel).

## Performance

| Channel Count | Duration | File Size | Generation Time | Peak RAM |
|---------------|----------|-----------|-----------------|----------|
| 64 | 60s | 2.5 MB | <1s | <50 MB |
| 256 | 60s | 9.8 MB | ~1s | <100 MB |
| 512 | 60s | 19.7 MB | ~2s | ~50 MB (in-memory) |
| 1024 | 60s | 39.3 MB | ~5s | <150 MB |
| 2048 | 60s | 78.6 MB | ~10s | <200 MB |

*Measured on Apple M2 Max, Python 3.11.6, NumPy 1.26.2*

## Future Extensions (v2)

### Additional Signal Types
- `white_noise`: Flat spectrum (remove 1/f shaping)
- `chirp`: Frequency sweep for filter response characterization

### Edge Case Injection (v1.1)
- `dc_offset`: Add DC offset for robustness testing
- `nan_rate`: Inject NaN samples for error handling validation
- `saturation_level`: Clip signal to test numerical limits

### Generative Models (v2)
- Train GAN/VAE on PhysioNet for realistic EEG-like signals
- Use for adaptive/branching kernel validation (when implemented)

## Citation

If you use this generator in research, please cite the CORTEX project and note the synthetic nature of the data:

```
Dataset: CORTEX Synthetic Generator v1 (pink noise, 1024 channels, 120s, seed=42)
Generated: primitives/datasets/v1/synthetic/generator.py
Project: https://github.com/user/cortex
```

## See Also

- `examples/high_channel_scalability.yaml` - Example scalability test config
- `examples/filter_validation.yaml` - Example filter validation config
- `docs/guides/synthetic-datasets.md` - Conceptual guide
- `experiments/high-channel-scalability-2026-01-XX/` - Benchmarking results
