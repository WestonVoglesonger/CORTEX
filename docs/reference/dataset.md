# EEG Dataset for CORTEX Simulation 


## Subject Identifiers

This dataset was obtained via PhysioNet, where it is publicly available. It originates from a publication in the IEEE Trans BioMed Eng. academic journal.

**Paper**: [BCI2000: a general-purpose brain-computer interface (BCI) system](https://pubmed.ncbi.nlm.nih.gov/15188875/)

**Dataset:** [EEG Motor Movement/Imagery Dataset](https://physionet.org/content/eegmmidb/1.0.0/S001/#files-panel)

**Authors**: Gerwin Schalk 1, Dennis J McFarland, Thilo Hinterberger, Niels Birbaumer, Jonathan R Wolpaw

**Date published:** September 2009

**Journal**: IEEE Transactions on Biomedical Engineering (Volume 51, Issue 6, June 2004)

**Citation**: Schalk, G., McFarland, D.J., Hinterberger, T., Birbaumer, N., Wolpaw, J.R. BCI2000: A General-Purpose Brain-Computer Interface (BCI) System. IEEE Transactions on Biomedical Engineering 51(6):1034-1043, 2004.

**Abstract:** A set of 64-channel EEGs from subjects who performed a series of motor/imagery tasks. This data set consists of over 1500 one- and two-minute EEG recordings, obtained from 109 volunteers.

## Contextual Information
### Experiment

**License:** Open Data Commons Attribution 1.0 (ODC-By 1.0). 

* Subjects performed different motor/imagery tasks while 64-channel EEG were recorded using the BCI2000 system (http://www.bci2000.org).
* each subject performed a total of 14 experimental runs: Two one-minute baseline runs, one with eyes open and one with eyes closed, and three two-minute runs of each of the four following tasks:
    * A target appears on either the left or the right side of the screen. The subject opens and closes the corresponding fist until the target disappears. Then the subject relaxes.
    * A target appears on either the left or the right side of the screen. The subject **imagines** opening and closing the corresponding fist until the target disappears. Then the subject relaxes.
    * A target appears on either the top or the bottom of the screen. The subject opens and closes either both fists (if the target is on top) or both feet (if the target is on the bottom) until the target disappears. Then the subject relaxes.
    * A target appears on either the top or the bottom of the screen. The subject **imagines** opening and closing either both fists (if the target is on top) or both feet (if the target is on the bottom) until the target disappears. Then the subject relaxes.

### Data Collection
**Dataset Format:** EDF+

**Sampling Rate**: 160 Hz

**Channels**: 64 EEG + an annotation channel


## Selection (frozen for this project)
- **Subjects used**: `S001–S010`  _(adjust if you want a different fixed subset)_.
- **Sessions / runs**: **R03–R14** (motor/imagery tasks; three repeats of each of four tasks). We exclude R01–R02 (baselines) for now.
- **File format**: EDF+ per subject/run (plus a matching `.event` file). 

## Fixed Parameters
- **Sampling rate (Fs)**: **160 Hz**  
- **Window length (W)**: **160 samples** (1.0 s)  
- **Hop (H)**: **80 samples** (0.5 s)  
- **Channels (C)**: **64**

## Channel Order
- **Source of truth**: EDF header **signal order 0–63** for each file. We snapshot channel names from the first used record and reuse that order for all processing.
- **Montage reference**: Official 64-electrode 10–10 montage figure provided with the dataset documentation (numbers under each label show the order 1–64; EDF signals are 0–63).
- **Saved snapshot**: [channel_order.json](channel_order.json) (array of 64 channel names in EDF order)

## Units
- **EEG potentials**: Physical units as recorded in the EDF header, typically **microvolts (µV)**. All CORTEX kernels process and report values in µV.

## Reference Scheme
- **As recorded in EDF** (dataset page does not impose a single fixed reference). To ensure consistency across runs, you can apply **common average reference (CAR)** by explicitly including the CAR kernel in your pipeline configuration.

## Annotations / Labels (kept for optional analyses)
- EDF annotation channel (and `.event` file) encodes **T0/T1/T2**:
  - **T0**: rest  
  - **T1**: onset of left fist (runs 3/4/7/8/11/12) or both fists (runs 5/6/9/10/13/14)  
  - **T2**: onset of right fist (3/4/7/8/11/12) or both feet (5/6/9/10/13/14)  
  We don’t require labels for our baseline kernels, but we keep them for sanity 

## Preprocessing (before any kernels)
- **None** beyond decoding EDF format. The dataset is used as-is with:
  - No filtering applied before kernel processing
  - No artifact rejection
  - No resampling (native Fs = 160 Hz)
- **Re-referencing**: Common Average Reference (CAR) can be applied by explicitly including it as a kernel in your pipeline configuration. By default, no re-referencing is applied.
- **Data quality**: This dataset consists of raw EEG recordings without preprocessing, as documented in the original BCI2000 publication.

---

## Dataset Preparation

### Overview

CORTEX currently requires EDF files to be converted to float32 binary format. The replayer is hardcoded to read float32 data. Conversion scripts and tools are provided in the `scripts/` directory.

**Note:** Dtype flexibility (Q15/Q7 support) is architecturally designed but not yet implemented. See [future-enhancements.md](../development/future-enhancements.md#quantization-support-q15q7) for planned quantization support in Spring 2026.

### Quick Start

```bash
# 1. Download EDF files from PhysioNet
cd scripts
./download_edf.sh

# 2. Convert to float32 binary
python3 convert_edf_to_float32.py S001R03 S001R07 S001R11

# 3. Verify conversion
ls -lh ../datasets/eegmmidb/converted/
```

### Directory Structure

```
datasets/eegmmidb/
├── raw/                         # Git-ignored EDF files
│   ├── S001R03.edf
│   └── ...
├── converted/                   # Binary data + metadata
│   ├── S001R03.float32         # Git-ignored binary
│   ├── S001R03_metadata.json   # Committed metadata
│   └── ...
└── channel_order.json           # Committed channel mapping
```

### Data Format

**Float32 Binary Format:**
- **Layout**: Interleaved samples `[sample0_ch0, ..., sample0_ch63, sample1_ch0, ...]`
- **Data Type**: 32-bit IEEE 754 floating point, little-endian
- **Units**: Microvolts (µV)
- **Size**: 4 bytes per value

**Metadata JSON** (per session):
```json
{
  "source": "S001R03.edf",
  "sample_rate_hz": 160,
  "channels": 64,
  "samples_per_channel": 20000,
  "duration_seconds": 125.0,
  "dtype": "float32",
  "format": "interleaved [samples, channels]",
  "units": "microvolts (µV)"
}
```

### Configuration

Update `configs/cortex.yaml` to point to converted dataset:

```yaml
dataset:
  path: "datasets/eegmmidb/converted/S001R03.float32"
  format: "float32"
  channels: 64
  sample_rate_hz: 160
```

### Extending to Other Subjects

```bash
# Download different subject
./download_edf.sh S002

# Convert new subject
python3 convert_edf_to_float32.py S002R03 S002R07 S002R11

# Update cortex.yaml
# dataset.path: "datasets/eegmmidb/converted/S002R03.float32"
```

### Verification

After conversion, verify:
- Binary files created: `*.float32` (~4.9MB each)
- Metadata files created: `*_metadata.json`
- Channel order file: `channel_order.json`
- Sample count: 20,000 per channel (125s at 160Hz)

### Troubleshooting

**Download failures:**
```bash
# Check network connectivity and retry
./download_edf.sh
```

**Conversion errors:**
```bash
# Ensure dependencies installed
pip install -r requirements.txt

# Check EDF file integrity
python3 -c "import pyedflib; f = pyedflib.EdfReader('S001R03.edf'); print(f.signals_in_file)"
```

**Missing metadata:**
- Metadata files are auto-generated during conversion
- Check `datasets/eegmmidb/converted/*_metadata.json`
- Re-run conversion if missing
