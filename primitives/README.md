# CORTEX Primitives

**Composable Building Blocks for BCI Benchmarking**

This directory contains the **primitives** that form the foundation of CORTEX benchmarking experiments. Inspired by AWS's philosophy of composable services, primitives are self-contained, reusable components that researchers combine to create custom benchmark configurations.

## Philosophy: AWS-Inspired Composability

Just as AWS provides primitive services (EC2, S3, Lambda) that users compose into complex architectures, CORTEX provides primitive components that researchers compose into benchmark experiments:

- **Kernels** = Signal processing algorithms (like Lambda functions)
- **Configs** = Experiment templates (like CloudFormation templates)
- **Future: Adapters** = Hardware interfaces (like EC2 instance types)

Each primitive is:
- **Self-contained**: Complete with specification, implementation, oracle, and documentation
- **Versioned**: Multiple versions can coexist (v1, v2) for reproducibility
- **Composable**: Mix and match to create custom benchmark pipelines
- **Validated**: Each comes with validation oracle and comprehensive tests

## Directory Structure

```
primitives/
├── kernels/           # Signal processing kernel implementations
│   ├── v1/            # Version 1 kernels (stable)
│   │   ├── bandpass_fir@f32/
│   │   ├── car@f32/
│   │   ├── goertzel@f32/
│   │   └── notch_iir@f32/
│   └── v2/            # Version 2 kernels (future)
│
└── configs/           # Benchmark configuration templates
    ├── cortex.yaml    # Production benchmark config
    └── generated/     # Auto-generated configs (gitignored)
```

## Primitives Categories

### 1. Kernels (`primitives/kernels/`)

**What**: C implementations of signal processing algorithms optimized for BCI applications

**Why**: Provide reusable, validated, high-performance DSP building blocks

**Structure**: Each kernel is a complete, self-documenting package:
```
kernels/v1/{name}@{dtype}/
├── spec.yaml          # Formal specification (dimensions, tolerances, params)
├── {name}.c           # C implementation using CORTEX plugin ABI
├── oracle.py          # Reference implementation for validation
├── Makefile           # Build configuration
└── README.md          # Algorithm documentation
```

**Available Kernels**:
- **`bandpass_fir@f32`**: FIR bandpass filter (8-30 Hz, 129 taps)
- **`car@f32`**: Common Average Reference (artifact rejection)
- **`goertzel@f32`**: Goertzel algorithm (alpha/beta band power)
- **`notch_iir@f32`**: IIR notch filter (60 Hz powerline removal)

**Usage**:
```bash
# List available kernels
cortex list

# Build all kernel plugins
make plugins

# Build specific kernel
make -C primitives/kernels/v1/goertzel@f32

# Validate kernel implementation
cortex validate --kernel goertzel --verbose
```

### 2. Configs (`primitives/configs/`)

**What**: YAML configuration templates defining complete benchmark experiments

**Why**: Provide reproducible, shareable experiment definitions

**Structure**: Each config specifies:
- System parameters (name, description)
- Dataset configuration (path, format, sample rate)
- Realtime requirements (scheduler, priority, affinity)
- Power management (governor, turbo)
- Benchmark parameters (duration, repeats, warmup)
- Plugin pipeline (which kernels to load and their parameters)

**Primary Config**: `cortex.yaml`
```yaml
cortex_version: 1

# Dataset configuration
dataset:
  path: "datasets/eegmmidb/converted/S001R03.float32"
  sample_rate_hz: 160
  channels: 64

# Benchmark parameters
benchmark:
  parameters:
    duration_seconds: 125
    repeats: 3
    warmup_seconds: 5

# Kernel pipeline
plugins:
  - name: "goertzel"
    spec_uri: "primitives/kernels/v1/goertzel@f32"
    spec_version: "1.0.0"
```

**Usage**:
```bash
# Run benchmark with config
cortex run primitives/configs/cortex.yaml

# Generate custom config for specific kernel
cortex config goertzel my-config.yaml

# Direct harness execution
./src/engine/harness/cortex run primitives/configs/cortex.yaml
```

## Adding New Primitives

### Adding a New Kernel

Complete guide: See [`docs/guides/adding-kernels.md`](../docs/guides/adding-kernels.md)

**Quick start**:
```bash
# 1. Create kernel directory
mkdir -p primitives/kernels/v1/mykernel@f32
cd primitives/kernels/v1/mykernel@f32

# 2. Create required files
# - spec.yaml: Formal specification
# - mykernel.c: C implementation
# - oracle.py: Reference implementation
# - Makefile: Build configuration
# - README.md: Documentation

# 3. Implement the CORTEX plugin ABI
# See existing kernels for examples

# 4. Build and validate
make
python oracle.py --test data.npy --output output.npy
cortex validate --kernel mykernel

# 5. Register in config
# Edit primitives/configs/cortex.yaml to add plugin entry
```

**Critical Requirements**:
- ✅ Makefile include path: `-I../../../../src/engine/include`
- ✅ Implement all required ABI functions: `init`, `execute`, `destroy`
- ✅ Match spec.yaml dimensions exactly (input_shape, output_shape)
- ✅ Provide Python oracle for validation
- ✅ Document algorithm in README.md

### Adding a New Config Template

```bash
# 1. Create YAML file in primitives/configs/
cp primitives/configs/cortex.yaml primitives/configs/my-experiment.yaml

# 2. Customize parameters
# - dataset: Point to your dataset
# - plugins: Select kernel pipeline
# - benchmark: Set duration, repeats
# - realtime: Configure scheduling

# 3. Validate config
cortex run primitives/configs/my-experiment.yaml --dry-run

# 4. Run experiment
cortex run primitives/configs/my-experiment.yaml
```

## Versioning Strategy

**Why Versioning**: Ensures reproducibility across experiments

**Version Scheme**:
- **v1/**: Stable, production-ready kernels
- **v2/**: Next-generation kernels (breaking changes)
- **v{N}/**: Future versions as algorithms evolve

**Coexistence**: Multiple versions can exist simultaneously:
```
primitives/kernels/
├── v1/goertzel@f32/      # Original implementation
└── v2/goertzel@f32/      # Optimized version (future)
```

Experiments reference specific versions in their configs:
```yaml
plugins:
  - name: "goertzel"
    spec_uri: "primitives/kernels/v1/goertzel@f32"  # Pin to v1
```

## Design Principles

1. **Composability**: Primitives combine to form complex experiments
2. **Self-Documentation**: Each primitive includes complete specification
3. **Validation**: Oracle-based correctness verification
4. **Reproducibility**: Version pinning ensures consistent results
5. **Extensibility**: Add new primitives without modifying core
6. **Performance**: C implementations for real-time constraints

## Future Primitives (Roadmap)

**Device Adapters**:
```
primitives/adapters/
├── cyton@8ch/         # OpenBCI Cyton (8 channels)
├── ganglion@4ch/      # OpenBCI Ganglion (4 channels)
└── unicorn@8ch/       # g.tec Unicorn Hybrid Black (8 channels)
```

**Preprocessing Pipelines**:
```
primitives/pipelines/
├── erp-analysis.yaml
├── motor-imagery.yaml
└── ssvep-detection.yaml
```

**Benchmark Profiles**:
```
primitives/profiles/
├── embedded-low-power.yaml    # MCU constraints
├── fpga-high-throughput.yaml  # FPGA targeting
└── cloud-batch-processing.yaml
```

## Integration with CORTEX

**CLI Integration**:
- `cortex list` → Discovers kernels in `primitives/kernels/`
- `cortex build` → Compiles kernel plugins
- `cortex config` → Generates configs using kernel specs
- `cortex run` → Loads configs from `primitives/configs/`
- `cortex validate` → Uses oracles for correctness checks

**C Engine Integration**:
- Harness dynamically loads kernel plugins from `primitives/kernels/v*/`
- Plugin ABI defined in `src/engine/include/cortex_plugin.h`
- Scheduler coordinates multi-kernel pipelines
- Replayer streams data to kernel instances

**Build System Integration**:
- Root `Makefile` auto-discovers kernels via glob: `primitives/kernels/v*/*@*/`
- Each kernel has independent Makefile
- Top-level `make plugins` builds all discovered kernels

## References

- **Plugin ABI Specification**: [`docs/reference/plugin-interface.md`](../docs/reference/plugin-interface.md)
- **Adding Kernels Guide**: [`docs/guides/adding-kernels.md`](../docs/guides/adding-kernels.md)
- **Configuration Reference**: [`docs/reference/configuration.md`](../docs/reference/configuration.md)
- **Architecture Overview**: [`docs/architecture/overview.md`](../docs/architecture/overview.md)

---

**Questions?** See [`docs/FAQ.md`](../docs/FAQ.md) or open an issue on GitHub.
