# Adding Dataset Primitives

Dataset primitives follow the same versioned, immutable patterns as kernels. This guide walks through creating a new dataset primitive for CORTEX.

## Overview

Datasets are first-class primitives in CORTEX, with:
- **Versioned structure**: `primitives/datasets/v1/{name}/`
- **Immutability**: v1 is frozen after release; changes go in v2
- **Direct path references**: Users specify paths directly in configs (relative or absolute)
- **Self-documenting**: spec.yaml + README.md describe the dataset

---

## Directory Structure

```
primitives/datasets/v1/{name}/
├── spec.yaml           # Metadata (required)
├── README.md           # Documentation (required)
├── converted/          # Processed .float32 files
│   └── {id}.float32
└── raw/                # Original source files (gitignored)
```

---

## Creating a New Dataset

### Step 1: Create Directory Structure

```bash
mkdir -p primitives/datasets/v1/my-dataset/converted
mkdir -p primitives/datasets/v1/my-dataset/raw
```

### Step 2: Write spec.yaml

```yaml
dataset:
  name: "my-dataset"
  description: "Brief description of what this dataset contains"
  source_url: "https://example.com/dataset"  # optional
  license: "CC-BY-4.0"  # or appropriate license

format:
  type: "float32"
  channels: 64
  sample_rate_hz: 160
  endian: "little"      # optional, default: little
  layout: "interleaved" # optional, default: interleaved

recordings:
  - id: "recording001"
    description: "Subject 1, Task A"
    duration_seconds: 125.0
    # file: optional (convention: converted/{id}.float32)

  - id: "recording002"
    description: "Subject 1, Task B"
    duration_seconds: 125.0
```

**Key fields**:
- `name`: Dataset identifier (lowercase, hyphens for multi-word)
- `description`: One-line summary
- `source_url`: Where the data came from (optional but recommended)
- `license`: Data license (important for redistribution)
- `format.type`: Data type (`float32`, `q15`, `q7`)
- `format.channels`: Number of EEG channels
- `format.sample_rate_hz`: Sampling rate in Hz
- `recordings`: List of individual recording files

**Convention over configuration**:
- File paths default to `converted/{id}.float32`
- Only specify `file` field for exceptions (e.g., `synthetic.float32`)

### Step 3: Add Dataset Files

```bash
# Place processed .float32 files in converted/
cp processed_data.float32 primitives/datasets/v1/my-dataset/converted/recording001.float32

# Optionally keep original source in raw/ (gitignored)
cp original.edf primitives/datasets/v1/my-dataset/raw/
```

**File format**: Interleaved float32 binary
- Shape: `[samples, channels]` row-major
- Units: Microvolts (µV)
- Endianness: Little-endian (standard)

### Step 4: Write README.md

Document your dataset thoroughly:

```markdown
# My Dataset Name

## Overview

[One paragraph: what this dataset is, who collected it, what tasks/conditions]

## Source

- **URL**: https://example.com/dataset
- **Citation**: Author et al. (2024). "Dataset paper." *Journal*.
- **License**: CC-BY-4.0

## Format

- **Channels**: 64 (10-20 system)
- **Sample Rate**: 160 Hz
- **Data Type**: float32 (interleaved)
- **Units**: Microvolts (µV)

## Recordings

| ID | Description | Duration | Subjects |
|----|-------------|----------|----------|
| recording001 | Task A | 125s | S001 |
| recording002 | Task B | 125s | S001 |

## Usage

Specify the direct path to the .float32 file in your config:

\`\`\`yaml
dataset:
  path: "primitives/datasets/v1/my-dataset/converted/recording001.float32"
\`\`\`

## Preprocessing

[Document any preprocessing steps: filtering, artifact rejection, etc.]

## Known Issues

[Any quirks, missing channels, data quality notes]
```

### Step 5: Verify Files

```bash
# Check that .float32 files exist
ls -lh primitives/datasets/v1/my-dataset/converted/

# Verify file size matches expected samples
# Expected size = samples * channels * 4 bytes (float32)
# Example: 20000 samples * 64 channels * 4 = 5,120,000 bytes
```

---

## Usage Examples

### In Config Files

```yaml
# primitives/configs/my-experiment.yaml
dataset:
  path: "primitives/datasets/v1/my-dataset/converted/recording001.float32"
  channels: 64
  sample_rate_hz: 160
```

### Running Benchmarks

```bash
# Run with default config
cortex pipeline

# Run with custom config
cortex run --config my-experiment.yaml
```

---

## Best Practices

### Naming Conventions

- **Dataset names**: Lowercase, hyphens for spaces
  - ✅ `physionet-motor-imagery`
  - ❌ `PhysioNet_Motor_Imagery`

- **Recording IDs**: Alphanumeric, underscores OK
  - ✅ `S001R03`, `subject_01_task_a`
  - ❌ `Subject 1 (Task A)`

### Data Organization

- Keep raw source files in `raw/` (add to .gitignore)
- Only commit processed `.float32` files in `converted/`
- Document preprocessing steps in README.md

### Versioning

- **v1 is immutable**: Never modify files in `v1/` after release
- **Create v2 for changes**: New preprocessing, additional recordings, format changes
- **Update configs**: Point to new version when ready

Example migration:
```bash
# Create v2 with improved preprocessing
mkdir -p primitives/datasets/v2/my-dataset/converted
# ... add improved data ...

# Update config
dataset:
  path: "my-dataset@v2/recording001"  # Changed from v1
```

### Checksums (Optional)

For data integrity, add checksums to spec.yaml:

```yaml
recordings:
  - id: "recording001"
    file: "converted/recording001.float32"
    checksum: "sha256:abc123..."  # Generated with: sha256sum recording001.float32
```

---

## Common Patterns

### Multi-Subject Datasets

```yaml
recordings:
  - id: "S001R03"
    description: "Subject 1, Run 3"
  - id: "S002R03"
    description: "Subject 2, Run 3"
  - id: "S003R03"
    description: "Subject 3, Run 3"
```

### Task-Based Recordings

```yaml
recordings:
  - id: "baseline-eyes-open"
    description: "Resting state, eyes open"
  - id: "motor-left"
    description: "Left hand motor imagery"
  - id: "motor-right"
    description: "Right hand motor imagery"
```

### Synthetic/Test Data

```yaml
dataset:
  name: "synthetic-sine"
  description: "Synthetic sine waves for testing"

recordings:
  - id: "10hz-sine"
    file: "10hz_sine.float32"  # Exception: not in converted/
    description: "Pure 10Hz sine wave"
```

---

## Troubleshooting

### "Dataset file not found"

```
failed to load config: primitives/datasets/v1/my-dataset/converted/recording001.float32
```

**Solution**: Verify the .float32 file exists at the specified path

### "Invalid path in config"

```
invalid config: dataset.path cannot be empty
```

**Solution**: Ensure dataset path is specified in config file

---

## Migration from Old Structure

If you have datasets in `datasets/` directory:

```bash
# 1. Create primitive structure
mkdir -p primitives/datasets/v1/old-dataset/converted

# 2. Move files
cp datasets/old-dataset/*.float32 primitives/datasets/v1/old-dataset/converted/

# 3. Create spec.yaml (see above)

# 4. Update configs to use new paths
# Old: dataset: { path: "datasets/old-dataset/file.float32" }
# New: dataset: { path: "primitives/datasets/v1/old-dataset/converted/file.float32" }

# 5. Test
cortex validate

# 6. Optional: Remove old files
# rm -rf datasets/old-dataset/
```

---

## Related Documentation

- [Plugin Interface](../reference/plugin-interface.md) - ABI specification
- [Configuration Reference](../reference/configuration.md) - YAML schema
- [Architecture Overview](../architecture/overview.md) - System design

---

## Example: physionet-motor-imagery

See `primitives/datasets/v1/physionet-motor-imagery/` for a complete reference implementation.
