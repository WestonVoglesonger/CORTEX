# EDF Dataset Preparation Implementation

## Overview

This document details the implementation of EDF dataset preparation for the CORTEX benchmarking harness, enabling the use of real EEG data from the PhysioNet EEG Motor Movement/Imagery Dataset instead of synthetic test data.

## Background

### Previous State
- Replayer expected raw float32 binary files in interleaved format
- Only synthetic test data available (`datasets/fake/test.raw`)
- Configuration pointed to non-existent `datasets/cortex` path
- No tools for converting real EEG datasets

### Requirements
- Download real EEG data from PhysioNet
- Convert EDF+ format to float32 binary for replayer compatibility
- Maintain existing replayer interface (no code changes needed)
- Provide comprehensive metadata and documentation
- Support easy extension to other subjects/sessions

## Architectural Decisions

### 1. Python-Based Conversion Pipeline

**Decision**: Use Python scripts for EDF conversion rather than integrating EDFlib into C code.

**Rationale**:
- **Simplicity**: Avoids complex C library dependencies in core harness
- **Flexibility**: Easy to modify for different datasets or formats
- **Maintainability**: Python ecosystem has robust EDF support (pyedflib)
- **Separation of Concerns**: Keep harness focused on benchmarking, not data conversion

### 2. Offline Conversion Strategy

**Decision**: Convert EDF files to float32 binary format once, then use repeatedly.

**Rationale**:
- **Performance**: Avoid runtime conversion overhead during benchmarking
- **Consistency**: Same data format across all experiments
- **Storage Efficiency**: Float32 is more compact than raw EDF
- **Compatibility**: Matches existing replayer expectations exactly

### 3. Metadata-Driven Approach

**Decision**: Generate JSON metadata files alongside binary data.

**Rationale**:
- **Documentation**: Human-readable dataset information
- **Validation**: Verify conversion correctness
- **Flexibility**: Easy to extend with additional metadata
- **Debugging**: Troubleshoot data issues without parsing binary

### 4. Channel Exclusion Strategy

**Decision**: Explicitly exclude annotation channel (signal 64) from EDF files.

**Rationale**:
- **Data Integrity**: Only process actual EEG signals
- **Consistency**: Ensure all files have exactly 64 channels
- **Clarity**: Make exclusion explicit in code and documentation
- **Future-Proofing**: Handle datasets with different annotation structures

## Implementation Details

### Directory Structure

```
scripts/
├── convert_edf_to_float32.py    # Main conversion script
├── download_edf.sh              # Download helper
├── requirements.txt             # Python dependencies
└── README.md                    # Usage documentation

datasets/eegmmidb/
├── raw/                         # Git-ignored EDF files
│   ├── S001R03.edf
│   ├── S001R07.edf
│   └── S001R11.edf
├── converted/                   # Binary data + metadata
│   ├── S001R03.float32         # Git-ignored binary
│   ├── S001R03_metadata.json   # Committed metadata
│   ├── S001R07.float32
│   ├── S001R07_metadata.json
│   ├── S001R11.float32
│   └── S001R11_metadata.json
└── channel_order.json           # Committed channel mapping
```

### Data Format Specifications

#### Float32 Binary Format
- **Layout**: Interleaved samples `[sample0_ch0, sample0_ch1, ..., sample0_ch63, sample1_ch0, ...]`
- **Data Type**: 32-bit IEEE 754 floating point
- **Byte Order**: Native (little-endian on x86/ARM)
- **Units**: Microvolts (µV) - automatically converted by pyedflib
- **Size**: 4 bytes per value

#### Metadata JSON Structure
```json
{
  "source": "S001R03.edf",
  "sample_rate_hz": 160,
  "channels": 64,
  "samples_per_channel": 20000,
  "duration_seconds": 125.0,
  "dtype": "float32",
  "format": "interleaved [samples, channels]",
  "units": "microvolts (µV)",
  "notes": "Converted from EDF+ (64 EEG channels, annotation channel excluded)"
}
```

#### Channel Order JSON Structure
```json
{
  "source": "PhysioNet EEG Motor Movement/Imagery Dataset",
  "dataset_url": "https://physionet.org/content/eegmmidb/1.0.0/",
  "format": "EDF signal order 0-63 (annotation channel excluded)",
  "sample_rate_hz": 160,
  "total_signals_in_edf": 64,
  "eeg_channels": 64,
  "channels": ["Fc5.", "Fc3.", "Fc1.", ...],
  "notes": "Channel order is identical across all sessions in dataset."
}
```

### Critical Implementation Fixes

#### 1. Channel Labels Timing Bug
**Issue**: Accessing `f.getSignalLabels()` after `f.close()` caused runtime errors.

**Fix**: Extract channel labels before closing the EDF file handle.

```python
# Save channel labels before closing file
channel_labels = f.getSignalLabels()[:64]
f.close()
```

#### 2. Channel Count Validation
**Issue**: EDF files had 64 signals instead of expected 65 (no annotation channel).

**Fix**: Added warning for unexpected signal counts and explicit handling.

```python
if n_signals_in_file != 65:
    print(f"  Warning: Expected 65 signals (64 EEG + 1 annotation), got {n_signals_in_file}")
```

#### 3. Sample Count Consistency
**Issue**: Potential mismatch in sample counts across channels.

**Fix**: Validate all channels have same sample count, use minimum if different.

```python
n_samples_per_channel = f.getNSamples()[:n_channels]
if not all(n == n_samples_per_channel[0] for n in n_samples_per_channel):
    print(f"  Warning: Channels have different sample counts: {set(n_samples_per_channel)}")
    n_samples = min(n_samples_per_channel)
```

#### 4. Error Handling Robustness
**Issue**: Download failures could go unnoticed.

**Fix**: Added `curl -f` flag and exit code checking.

```bash
if curl -f --show-error -o "$OUTPUT_DIR/${session}.edf" \
        "${BASE_URL}/${SUBJECT}/${session}.edf"; then
    echo "  ✓ ${session}.edf downloaded successfully"
else
    echo "  ✗ Failed to download ${session}.edf"
    exit 1
fi
```

## Configuration Changes

### Updated `configs/cortex.yaml`

```yaml
dataset:
  path: "datasets/eegmmidb/converted/S001R03.float32"  # Changed from "datasets/cortex"
  format: "float32"  # Changed from "raw"
  channels: 64  # Unchanged
  sample_rate_hz: 160  # Unchanged

# Added missing power section
power:
  governor: "performance"
  turbo: false
```

### Updated `.gitignore`

```gitignore
# EDF dataset files (large, don't commit)
datasets/eegmmidb/raw/*.edf
datasets/eegmmidb/raw/*.event

# Converted float32 files (large, optional to commit)
datasets/eegmmidb/converted/*.float32

# Keep metadata and channel order (small, commit these)
!datasets/eegmmidb/converted/*_metadata.json
!datasets/eegmmidb/channel_order.json
```

## Usage Guidelines

### Quick Start
```bash
# Download EDF files
cd scripts
./download_edf.sh

# Convert to float32 binary
python3 convert_edf_to_float32.py S001R03 S001R07 S001R11

# Use with harness
cd ../src/harness
./cortex run ../../configs/cortex.yaml
```

### Extending to Other Subjects
```bash
# Download different subject
./download_edf.sh S002

# Convert new subject
python3 convert_edf_to_float32.py S002R03 S002R07 S002R11

# Update cortex.yaml path
# dataset.path: "datasets/eegmmidb/converted/S002R03.float32"
```

## Verification Results

### Download Verification
- ✅ Successfully downloaded 3 EDF files (~2.5MB each)
- ✅ Successfully downloaded 3 event files (~638B each)
- ✅ Robust error handling with curl exit codes
- ✅ File size verification in output

### Conversion Verification
- ✅ Successfully converted 3 EDF files to float32 binary (~4.9MB each)
- ✅ Generated metadata JSON files for each session
- ✅ Created channel order JSON with 64 channel labels
- ✅ Handled 64 signals instead of expected 65 (no annotation channel)

### Data Integrity Verification
- ✅ **Samples**: 20,000 samples per channel (125 seconds at 160Hz)
- ✅ **Channels**: Exactly 64 EEG channels
- ✅ **Format**: Interleaved float32 binary
- ✅ **Units**: Microvolts (µV) with realistic range [-521, 600]
- ✅ **Duration**: 125.0 seconds per session

### Integration Verification
- ✅ Harness builds successfully with new configuration
- ✅ Replayer can load float32 binary files
- ✅ Configuration points to valid dataset path
- ✅ All metadata files committed to version control

## Benefits

### 1. Real Data Availability
- **Before**: Only synthetic test data available
- **After**: Real EEG data from gold-standard PhysioNet dataset
- **Impact**: Enables realistic performance benchmarking

### 2. Production-Ready Dataset
- **Before**: No standardized dataset for benchmarking
- **After**: Consistent, well-documented dataset with metadata
- **Impact**: Reproducible experiments across team members

### 3. Easy Extension
- **Before**: No tools for adding new datasets
- **After**: Parameterized scripts for different subjects/sessions
- **Impact**: Simple to expand dataset coverage

### 4. Comprehensive Documentation
- **Before**: No dataset documentation
- **After**: Complete usage guide, troubleshooting, and format specs
- **Impact**: Easy onboarding for new team members

## Future Enhancements

### 1. Additional Subjects
- Extend to subjects S002, S003, etc.
- Add more session types (R01, R02, R04, etc.)
- Support different motor tasks

### 2. Dataset Validation
- Add automated data quality checks
- Implement signal-to-noise ratio validation
- Add artifact detection

### 3. Format Support
- Support other EEG formats (BDF, GDF)
- Add real-time streaming capabilities
- Implement data augmentation

### 4. Integration Improvements
- Add dataset selection in configuration
- Implement automatic dataset validation
- Add dataset versioning

## Lessons Learned

### 1. Channel Handling Complexity
EDF files can have varying numbers of signals. The PhysioNet dataset had 64 signals instead of the expected 65, requiring flexible handling in the conversion script.

### 2. Metadata Importance
JSON metadata files proved invaluable for debugging and validation. They provide human-readable information that's essential for understanding dataset characteristics.

### 3. Error Handling Criticality
Robust error handling in download scripts prevents silent failures that could lead to incomplete datasets and confusing debugging sessions.

### 4. Git Integration Strategy
Using `.gitignore` patterns with negation rules allows committing small metadata files while excluding large binary datasets, balancing version control benefits with repository size.

## Conclusion

The EDF dataset preparation implementation successfully provides CORTEX with a production-ready EEG dataset while maintaining the existing replayer interface. The Python-based conversion pipeline offers flexibility and maintainability, while comprehensive documentation ensures easy adoption and extension.

The implementation demonstrates the importance of robust error handling, comprehensive metadata, and flexible design patterns when integrating external data sources into existing systems.
