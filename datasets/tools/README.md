# CORTEX Dataset Conversion Scripts

This directory contains scripts for preparing EEG datasets for use with the CORTEX benchmarking harness.

## Prerequisites

Python 3.8+ with dependencies:

```bash
pip3 install -r requirements.txt
```

## Quick Start

1. Download EDF files:
```bash
cd scripts
chmod +x download_edf.sh
./download_edf.sh
```

2. Convert to float32 binary:
```bash
python3 convert_edf_to_float32.py S001R03 S001R07 S001R11
```

## Usage

### Download Script

```bash
# Download from default subject (S001)
./download_edf.sh

# Download from different subject
./download_edf.sh S002
```

Downloads 3 sessions from PhysioNet:
- R03: Left/right fist motor task (first run)
- R07: Left/right fist motor task (repeat)
- R11: Both fists/both feet motor task (repeat)

Output: `datasets/eegmmidb/raw/S001R*.edf`

### Conversion Script

```bash
# Convert specific sessions
python3 convert_edf_to_float32.py S001R03 S001R07 S001R11

# Convert all EDF files in raw/ directory
python3 convert_edf_to_float32.py --all
```

Output:
- `datasets/eegmmidb/converted/S001R03.float32` - Binary data
- `datasets/eegmmidb/converted/S001R03_metadata.json` - Metadata
- `datasets/eegmmidb/channel_order.json` - Channel mapping (shared)

## Output Format

### Float32 Binary Format

Interleaved samples: `[sample0_ch0, sample0_ch1, ..., sample0_ch63, sample1_ch0, ...]`

- Data type: 32-bit IEEE 754 floating point
- Byte order: Native (little-endian on x86/ARM)
- Layout: Row-major (samples × channels)
- Size: 4 bytes per value
- Units: Microvolts (µV) - automatically converted by pyedflib

### Metadata JSON

```json
{
  "source": "S001R03.edf",
  "sample_rate_hz": 160,
  "channels": 64,
  "samples_per_channel": 19840,
  "duration_seconds": 124.0,
  "dtype": "float32",
  "format": "interleaved [samples, channels]",
  "units": "microvolts (µV)"
}
```

### Channel Order JSON

```json
{
  "source": "PhysioNet EEG Motor Movement/Imagery Dataset",
  "format": "EDF signal order 0-63 (annotation channel excluded)",
  "sample_rate_hz": 160,
  "total_signals_in_edf": 65,
  "eeg_channels": 64,
  "channels": ["Fc5", "Fc3", "Fc1", ...]
}
```

## Using with CORTEX

The main configuration `configs/cortex.yaml` will be updated to use the EDF data as the default dataset.

## Dataset Information

- **Source**: PhysioNet EEG Motor Movement/Imagery Dataset v1.0.0
- **URL**: https://physionet.org/content/eegmmidb/1.0.0/
- **License**: Open Data Commons Attribution 1.0 (ODC-By 1.0)
- **Citation**: Schalk et al., IEEE Trans Biomed Eng 51(6):1034-1043, 2004
- **Structure**: 65 signals per file (64 EEG + 1 annotation), we use only EEG

## Extending to Other Sessions

To add more sessions, modify `download_edf.sh`:

```bash
SESSIONS=("${SUBJECT}R03" "${SUBJECT}R07" "${SUBJECT}R11" "${SUBJECT}R05")  # Add more
```

Then re-run both download and conversion scripts.

## Troubleshooting

**pyedflib import error**: Install dependencies with `pip3 install -r requirements.txt`

**curl not found**: Install curl (pre-installed on macOS, `apt-get install curl` on Linux)

**Permission denied**: Make script executable with `chmod +x download_edf.sh`

**File not found**: Ensure you run scripts from the `scripts/` directory

**Channel count warnings**: The dataset has 65 signals (64 EEG + 1 annotation). This is normal.

**Sample count mismatch**: If channels have different sample counts, the script uses the minimum.
