# CORTEX Datasets

**EEG Datasets for Benchmarking BCI Signal Processing**

This directory contains EEG datasets used for benchmarking kernel implementations and validating CORTEX performance across different signal characteristics.

## Purpose

Datasets serve three critical functions in CORTEX:

1. **Benchmarking**: Provide realistic signal inputs for latency/throughput measurements
2. **Validation**: Enable correctness verification via oracle comparison
3. **Reproducibility**: Ensure consistent experimental conditions across runs

## Directory Structure

```
datasets/
├── tools/                    # Dataset conversion and preparation utilities
│   ├── convert_edf_to_float32.py    # EDF → float32 converter
│   ├── download_edf.sh              # Download EEG Motor Movement/Imagery Database
│   └── README.md                    # Tool documentation
│
├── eegmmidb/                # EEG Motor Movement/Imagery Database (PhysioNet)
│   ├── raw/                 # Original .edf files (not in git)
│   └── converted/           # Converted .float32 files (not in git)
│
└── synthetic/               # Generated test signals (optional)
    └── chirp_160hz_64ch.float32
```

**Note**: Raw and converted datasets are **not committed to git** (excluded via `.gitignore`). Users must download and convert datasets locally using the provided tools.

## Dataset Format

**CORTEX Standard Format**: Raw float32 binary

**Structure**:
```
[channel_0_sample_0, channel_1_sample_0, ..., channel_C-1_sample_0,
 channel_0_sample_1, channel_1_sample_1, ..., channel_C-1_sample_1,
 ...
 channel_0_sample_N-1, channel_1_sample_N-1, ..., channel_C-1_sample_N-1]
```

**Properties**:
- **Endianness**: Native (little-endian on x86/ARM)
- **Data type**: 32-bit IEEE 754 floating point
- **Layout**: Interleaved channels (sample-major ordering)
- **No header**: Pure binary data (metadata in separate YAML config)

**Why this format?**
- ✅ Zero-copy `mmap()` loading for minimal latency
- ✅ No parsing overhead (unlike CSV, EDF)
- ✅ Direct memory representation for streaming
- ✅ Deterministic file size: `samples × channels × 4 bytes`

## Available Datasets

### 1. EEG Motor Movement/Imagery Database (Primary Dataset)

**Source**: PhysioNet - [EEG Motor Movement/Imagery Database](https://physionet.org/content/eegmmidb/1.0.0/)

**Description**:
- 109 subjects performing motor movement and imagery tasks
- 64-channel EEG recorded at 160 Hz
- Various experimental runs (eyes open, eyes closed, task execution)

**Specifications**:
- **Channels**: 64 (10-20 system)
- **Sample Rate**: 160 Hz
- **Format (raw)**: EDF (European Data Format)
- **Format (converted)**: float32 binary

**Download & Convert**:
```bash
# Download sample subjects (1-10)
cd datasets/eegmmidb
bash ../tools/download_edf.sh

# Convert EDF → float32
python ../tools/convert_edf_to_float32.py \
  raw/S001/S001R03.edf \
  converted/S001R03.float32

# Verify file size
# Expected: 160 Hz × 64 channels × 60 seconds × 4 bytes = 2,457,600 bytes
ls -lh converted/S001R03.float32
```

**Citation**:
```
Schalk, G., McFarland, D.J., Hinterberger, T., Birbaumer, N., Wolpaw, J.R.
BCI2000: A General-Purpose Brain-Computer Interface (BCI) System.
IEEE Transactions on Biomedical Engineering 51(6):1034-1043, 2004.
```

### 2. Synthetic Test Signals (Development)

**Purpose**: Controlled signals for unit testing and algorithm validation

**Generation** (future):
```python
import numpy as np

# Generate 60s of 160 Hz, 64-channel chirp signal
Fs = 160
duration = 60
channels = 64
samples = Fs * duration

t = np.arange(samples) / Fs
chirp = np.sin(2 * np.pi * (10 + 5*t) * t)  # 10-15 Hz chirp
data = np.tile(chirp, (channels, 1)).T.astype(np.float32)

# Save as interleaved float32
data.tofile('datasets/synthetic/chirp_160hz_64ch.float32')
```

## Dataset Conversion Tools

### convert_edf_to_float32.py

**Purpose**: Convert EDF (European Data Format) files to CORTEX float32 format

**Usage**:
```bash
python datasets/tools/convert_edf_to_float32.py <input.edf> <output.float32>
```

**Features**:
- Reads multi-channel EDF files using `pyedflib`
- Converts all channels to float32
- Interleaves channels (sample-major ordering)
- Validates output file size

**Requirements**:
```bash
pip install -e .[datasets]  # Installs pyedflib + numpy
```

**Example**:
```bash
# Convert single file
python datasets/tools/convert_edf_to_float32.py \
  datasets/eegmmidb/raw/S001/S001R03.edf \
  datasets/eegmmidb/converted/S001R03.float32

# Batch convert all runs for subject 1
for edf in datasets/eegmmidb/raw/S001/*.edf; do
  base=$(basename "$edf" .edf)
  python datasets/tools/convert_edf_to_float32.py \
    "$edf" \
    "datasets/eegmmidb/converted/${base}.float32"
done
```

### download_edf.sh

**Purpose**: Download EEG Motor Movement/Imagery Database from PhysioNet

**Usage**:
```bash
cd datasets/eegmmidb
bash ../tools/download_edf.sh [num_subjects]
```

**Arguments**:
- `num_subjects` (optional): Number of subjects to download (default: 10)

**Example**:
```bash
# Download first 5 subjects
cd datasets/eegmmidb
bash ../tools/download_edf.sh 5

# Downloads to datasets/eegmmidb/raw/S001/ through S005/
```

**Requirements**:
- `wget` or `curl` (auto-detected)
- Internet connection
- ~2 GB disk space per 10 subjects

## Adding New Datasets

### Option 1: From EDF Files

```bash
# 1. Organize raw files
mkdir -p datasets/my-dataset/raw
cp /path/to/*.edf datasets/my-dataset/raw/

# 2. Convert to float32
mkdir -p datasets/my-dataset/converted
for edf in datasets/my-dataset/raw/*.edf; do
  base=$(basename "$edf" .edf)
  python datasets/tools/convert_edf_to_float32.py \
    "$edf" \
    "datasets/my-dataset/converted/${base}.float32"
done

# 3. Create metadata YAML
cat > datasets/my-dataset/info.yaml <<EOF
dataset:
  name: "My Dataset"
  source: "Institution/Study Name"
  sample_rate_hz: 256
  channels: 32
  format: "float32"
  description: "Brief description of dataset"
EOF

# 4. Update config to reference dataset
# Edit primitives/configs/cortex.yaml:
#   dataset:
#     path: "datasets/my-dataset/converted/recording.float32"
#     sample_rate_hz: 256
#     channels: 32
```

### Option 2: Generate Synthetic Data

```python
import numpy as np

# Parameters
Fs = 160  # Sample rate (Hz)
duration = 60  # Duration (seconds)
channels = 64

# Generate signal (example: alpha oscillation + noise)
samples = Fs * duration
t = np.arange(samples) / Fs
alpha = np.sin(2 * np.pi * 10 * t)  # 10 Hz alpha rhythm
noise = np.random.normal(0, 0.1, samples)
signal = alpha + noise

# Replicate across channels (interleaved)
data = np.tile(signal, (channels, 1)).T.astype(np.float32)

# Save
output_path = 'datasets/synthetic/alpha_160hz_64ch.float32'
data.tofile(output_path)

# Verify size
expected_bytes = samples * channels * 4
actual_bytes = os.path.getsize(output_path)
assert expected_bytes == actual_bytes
print(f"✓ Generated {output_path} ({actual_bytes:,} bytes)")
```

## Dataset Configuration

Datasets are referenced in benchmark configs (`primitives/configs/*.yaml`):

```yaml
dataset:
  path: "datasets/eegmmidb/converted/S001R03.float32"
  format: "float32"
  channels: 64
  sample_rate_hz: 160
```

**Key Parameters**:
- `path`: Relative path from CORTEX root
- `format`: Always `"float32"` for CORTEX
- `channels`: Number of channels (must match data file)
- `sample_rate_hz`: Sampling frequency (must match data file)

**Validation**:
```bash
# Verify dataset matches config
cortex validate --config primitives/configs/cortex.yaml
```

## Dataset Best Practices

### Storage

- ✅ **DO**: Store raw and converted datasets in `datasets/`
- ✅ **DO**: Add dataset directories to `.gitignore` (already configured)
- ✅ **DO**: Document dataset sources and citations
- ❌ **DON'T**: Commit large binary files to git
- ❌ **DON'T**: Mix datasets from different studies without clear organization

### Naming Conventions

- **Directories**: `datasets/<study-name>/`
- **Raw files**: `datasets/<study-name>/raw/*.edf`
- **Converted files**: `datasets/<study-name>/converted/*.float32`
- **Metadata**: `datasets/<study-name>/info.yaml`

### File Size Estimation

```python
# Calculate expected file size
samples = sample_rate_hz * duration_seconds
channels = num_channels
bytes_per_float32 = 4

file_size_bytes = samples * channels * bytes_per_float32
file_size_mb = file_size_bytes / (1024 * 1024)

print(f"Expected file size: {file_size_mb:.2f} MB")
```

**Example**:
- 160 Hz, 64 channels, 60 seconds
- File size = 160 × 64 × 60 × 4 = 2,457,600 bytes (~2.34 MB)

## Troubleshooting

### Issue: EDF conversion fails

**Symptoms**: `pyedflib` import error or conversion crashes

**Solutions**:
```bash
# Install dataset tools dependencies
pip install -e .[datasets]

# Verify pyedflib installation
python -c "import pyedflib; print(pyedflib.__version__)"

# Check EDF file integrity
file datasets/eegmmidb/raw/S001/S001R03.edf
# Should show: "European Data Format"
```

### Issue: File size mismatch

**Symptoms**: Converted file size doesn't match expected

**Diagnosis**:
```python
import os
import pyedflib

# Read EDF metadata
edf_file = 'datasets/eegmmidb/raw/S001/S001R03.edf'
f = pyedflib.EdfReader(edf_file)
print(f"Channels: {f.signals_in_file}")
print(f"Sample rate: {f.getSampleFrequency(0)} Hz")
print(f"Samples: {f.getNSamples()[0]}")
print(f"Duration: {f.file_duration} seconds")

# Calculate expected output size
channels = f.signals_in_file
samples = f.getNSamples()[0]
expected_bytes = channels * samples * 4
print(f"Expected output: {expected_bytes:,} bytes")

# Check actual output
float32_file = 'datasets/eegmmidb/converted/S001R03.float32'
actual_bytes = os.path.getsize(float32_file)
print(f"Actual output: {actual_bytes:,} bytes")
print(f"Match: {expected_bytes == actual_bytes}")
```

### Issue: Dataset not found during benchmark

**Symptoms**: `cortex run` fails with "Dataset file not found"

**Solutions**:
```bash
# Verify path is relative from CORTEX root
ls -lh datasets/eegmmidb/converted/S001R03.float32

# Check config path matches actual file location
cat primitives/configs/cortex.yaml | grep "path:"

# Ensure file has read permissions
chmod 644 datasets/eegmmidb/converted/*.float32
```

## References

- **Dataset Documentation**: [`docs/reference/dataset.md`](../docs/reference/dataset.md)
- **PhysioNet EEG MMI Database**: https://physionet.org/content/eegmmidb/1.0.0/
- **EDF Format Specification**: https://www.edfplus.info/specs/edf.html
- **Configuration Reference**: [`docs/reference/configuration.md`](../docs/reference/configuration.md)

---

**Questions?** See [`docs/FAQ.md`](../docs/FAQ.md) or open an issue on GitHub.