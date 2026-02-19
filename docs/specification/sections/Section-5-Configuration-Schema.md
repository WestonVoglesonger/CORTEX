# **Section 5: Configuration Schema**

## **5.1 Overview**

CORTEX v1.0 uses YAML-based configuration files to define benchmark runs. A conformant implementation MUST support YAML 1.2 syntax and MUST validate configurations against the schema defined in this section. Configuration files specify dataset parameters, real-time constraints, kernel selection, and telemetry output settings.

### **5.1.1 Design Rationale**

YAML was selected for the following reasons:

1. **Human Readability**: Research users can read and modify configurations without specialized tools
2. **Comment Support**: Inline documentation of parameter choices (critical for reproducibility)
3. **Complex Nesting**: Natural representation of hierarchical structures (kernel parameters, runtime constraints)
4. **Industry Adoption**: Proven standard in infrastructure automation (Kubernetes, Ansible, CI/CD)

The schema balances **verbosity** and **usability** through automatic kernel discovery (Section 5.1.7) while preserving explicit control when needed.

### **5.1.2 Versioning**

Configuration files MUST include a `cortex_version` field. This specification defines version `1`. Implementations MUST reject configurations with unrecognized versions.

Future versions MAY introduce breaking changes to field names, semantics, or validation rules. Minor extensions (new optional fields) SHOULD NOT increment the version number.

### **5.1.3 Platform-Specific Fields**

Some fields are **parsed but unused** on certain platforms due to OS limitations:

- `power.governor`, `power.turbo`: Ignored on macOS (no userspace CPU frequency control)
- `realtime.scheduler: "rr"`: Not supported on macOS (only `fifo`, `deadline`, `other`)
- `realtime.deadline.*`: Linux `SCHED_DEADLINE` parameters (not available on macOS)

Implementations MUST parse these fields without error but MAY log warnings when they have no effect. This design preserves cross-platform configuration portability.

### **5.1.4 Future Extensibility**

The following fields are **parsed but not currently used** by the harness:

- `system.name`, `system.description`: Run metadata (no database storage in v1.0)
- `benchmark.metrics`: Metric selection array (v1.0 collects all metrics)
- `output.include_raw_data`: Raw telemetry export flag (reserved for future use)

Implementations MUST accept these fields without error. They are reserved for future functionality and MUST NOT be repurposed for other uses.

---

## **5.2 YAML Structure**

### **5.2.1 Schema Definition**

A conformant run configuration MUST be valid YAML 1.2 with the following structure:

```yaml
cortex_version: 1                    # REQUIRED

system:                              # OPTIONAL
  name: string                       # Human-readable identifier
  description: string                # Run purpose or notes

dataset:                             # REQUIRED
  path: string                       # Filesystem path to dataset
  format: "float32"                  # Data type (only float32 in v1.0)
  channels: integer                  # Number of input channels (C)
  sample_rate_hz: integer            # Sampling rate in Hz (Fs)

realtime:                            # REQUIRED
  scheduler: string                  # "fifo" | "rr" | "deadline" | "other"
  priority: integer                  # Real-time priority (1-99)
  cpu_affinity: [integer, ...]       # CPU core IDs for pinning
  deadline_ms: integer               # Per-window deadline (milliseconds)
  deadline:                          # OPTIONAL (Linux SCHED_DEADLINE)
    runtime_us: integer              # Runtime budget (microseconds)
    period_us: integer               # Period (microseconds)
    deadline_us: integer             # Relative deadline (microseconds)

power:                               # OPTIONAL
  governor: string                   # "performance" | "powersave" | "ondemand"
  turbo: boolean                     # Disable turbo boost for stability

benchmark:                           # REQUIRED
  metrics: [string, ...]             # OPTIONAL: Metric selection (future)
  parameters:                        # REQUIRED
    duration_seconds: integer        # Total benchmark duration
    repeats: integer                 # Number of repetitions
    warmup_seconds: integer          # Warmup period before measurements
  load_profile: string               # "idle" | "medium" | "heavy"

output:                              # REQUIRED
  directory: string                  # Output directory path
  format: string                     # "ndjson" | "csv"
  include_raw_data: boolean          # OPTIONAL: Export raw telemetry (future)

plugins:                             # OPTIONAL (see Section 5.1.7)
  - name: string                     # Kernel name
    status: string                   # "draft" | "ready"
    spec_uri: string                 # Path to kernel spec directory
    spec_version: string             # OPTIONAL: Kernel version
    adapter_path: string             # Path to adapter binary (REQUIRED)
    params:                          # OPTIONAL: Kernel-specific parameters
      key: value                     # Arbitrary key-value pairs
    calibration_state: string        # OPTIONAL: Path to .cortex_state file
```

### **5.2.2 Field Semantics**

#### **cortex_version**
- **Type**: Integer
- **Requirement**: REQUIRED
- **Valid Values**: `1` for this specification
- **Purpose**: Schema version identification

Implementations MUST reject files with `cortex_version != 1`.

#### **system**
- **Type**: Object
- **Requirement**: OPTIONAL
- **Fields**:
  - `name` (string): Short identifier for the run
  - `description` (string): Free-text description

These fields are parsed but not used in v1.0. They are reserved for future run tracking and metadata export.

#### **dataset**
- **Type**: Object
- **Requirement**: REQUIRED
- **Fields**:
  - `path` (string): Absolute or relative path to dataset file or directory
  - `format` (string): Data encoding. MUST be `"float32"` in v1.0
  - `channels` (integer): Number of input channels. MUST be > 0
  - `sample_rate_hz` (integer): Sampling rate in Hz. MUST be > 0

The `path` field MUST refer to a readable file or directory. Implementations MUST verify accessibility during validation.

#### **realtime**
- **Type**: Object
- **Requirement**: REQUIRED
- **Fields**:
  - `scheduler` (string): Scheduling policy. Valid values:
    - `"fifo"`: SCHED_FIFO (Linux), TIME_CONSTRAINT_POLICY (macOS)
    - `"rr"`: SCHED_RR (Linux only, not supported on macOS)
    - `"deadline"`: SCHED_DEADLINE (Linux only, requires `deadline.*` fields)
    - `"other"`: SCHED_OTHER (Linux), THREAD_STANDARD_POLICY (macOS)
  - `priority` (integer): Real-time priority. MUST be in range [1, 99] for FIFO/RR. Ignored for `other` scheduler
  - `cpu_affinity` (array of integers): List of CPU core IDs for thread pinning. Empty array means no affinity
  - `deadline_ms` (integer): Window processing deadline in milliseconds. MUST be > 0

**SCHED_DEADLINE Parameters** (Linux only, OPTIONAL):
- `deadline.runtime_us`: CPU time budget per period (microseconds)
- `deadline.period_us`: Scheduling period (microseconds)
- `deadline.deadline_us`: Relative deadline (microseconds)

If `scheduler: "deadline"`, implementations MUST validate that all three `deadline.*` fields are present. On platforms without `SCHED_DEADLINE` support, implementations MUST reject this configuration.

The `cpu_affinity` array is converted to a bitmask internally. For example, `[0, 2]` becomes bitmask `0x5` (cores 0 and 2 enabled).

#### **power**
- **Type**: Object
- **Requirement**: OPTIONAL
- **Fields**:
  - `governor` (string): CPU frequency governor. Common values: `"performance"`, `"powersave"`, `"ondemand"`. Platform-specific
  - `turbo` (boolean): If `false`, disable turbo boost for measurement stability

These fields are **parsed but not used** on macOS. Linux implementations MAY use them to configure CPU power management if running with sufficient privileges.

#### **benchmark**
- **Type**: Object
- **Requirement**: REQUIRED
- **Fields**:
  - `metrics` (array of strings): OPTIONAL. Reserved for future metric selection. Valid values: `"latency"`, `"jitter"`, `"throughput"`, `"memory_usage"`, `"energy_consumption"`. Currently ignored (all metrics collected)
  - `parameters` (object): REQUIRED
    - `duration_seconds` (integer): Total benchmark duration. MUST be > 0
    - `repeats` (integer): Number of independent runs. MUST be ≥ 1
    - `warmup_seconds` (integer): Initial warmup period to discard. MUST be ≥ 0
  - `load_profile` (string): Background CPU load. Valid values:
    - `"idle"`: No artificial load (default)
    - `"medium"`: Moderate load (N/2 CPUs at 50% utilization)
    - `"heavy"`: High load (N CPUs at 90% utilization)

The `load_profile` feature requires the `stress-ng` system utility. If not available, implementations MUST fall back to `idle` mode with a warning message.

**Platform-Specific Recommendation**: On macOS, `load_profile: "medium"` is RECOMMENDED for reproducible results due to dynamic frequency scaling. See Section 5.2.3 for details.

#### **output**
- **Type**: Object
- **Requirement**: REQUIRED
- **Fields**:
  - `directory` (string): Output directory path. Created if it does not exist
  - `format` (string): Telemetry output format. Valid values: `"ndjson"` (default), `"csv"`
  - `include_raw_data` (boolean): OPTIONAL. Reserved for future raw telemetry export. Currently ignored

Implementations MUST create the output directory if it does not exist. If creation fails due to permissions or filesystem errors, validation MUST fail.

#### **plugins**
- **Type**: Array of objects
- **Requirement**: OPTIONAL (see Section 5.1.7)
- **Maximum Length**: 16 (defined by `CORTEX_MAX_PLUGINS`)

Each plugin entry MUST have the following fields:
- `name` (string): Kernel identifier. MUST match kernel directory name
- `status` (string): Kernel maturity level. Valid values: `"draft"`, `"ready"`
- `spec_uri` (string): Path to kernel specification directory (e.g., `primitives/kernels/v1/notch_iir@f32`)
- `adapter_path` (string): Path to device adapter binary. REQUIRED in explicit mode

Optional fields:
- `spec_version` (string): Kernel version (e.g., `"1.0.0"`). Parsed but not validated in v1.0
- `params` (object): Kernel-specific runtime parameters (see Section 5.3.4)
- `calibration_state` (string): Path to calibration state file for trainable kernels (ABI v3)

### **5.2.3 Platform-Specific Guidance**

#### **macOS Frequency Scaling**

On macOS, dynamic voltage and frequency scaling (DVFS) causes up to **49% performance variance** in idle mode. This degrades reproducibility of benchmark results.

**Recommended Configuration for macOS**:
```yaml
benchmark:
  load_profile: "medium"  # Forces frequency to remain elevated
```

**Empirical Evidence** (Fall 2025 validation on M1 MacBook Pro):

| Kernel | Idle Mean (µs) | Medium Mean (µs) | Variance |
|--------|----------------|------------------|----------|
| bandpass_fir | 4969 | 2554 | -48.6% |
| car | 36 | 20 | -45.5% |
| goertzel | 417 | 196 | -53.0% |
| notch_iir | 115 | 61 | -47.4% |

The `medium` load profile sustains background CPU activity sufficient to prevent frequency downscaling, improving measurement stability.

**Linux Alternative**: Users with root privileges MAY manually set the CPU governor:
```bash
sudo cpupower frequency-set --governor performance
```
Then use `load_profile: "idle"` in the configuration. This achieves equivalent stability without artificial load.

### **5.2.4 Validation Rules**

Implementations MUST enforce the following validation rules before executing a benchmark:

1. **Required Fields**:
   - `cortex_version`, `dataset`, `realtime`, `benchmark`, `output` MUST be present
   - `dataset.path`, `dataset.format`, `dataset.channels`, `dataset.sample_rate_hz` MUST be present
   - `realtime.scheduler`, `realtime.priority`, `realtime.cpu_affinity`, `realtime.deadline_ms` MUST be present
   - `benchmark.parameters.duration_seconds`, `benchmark.parameters.repeats`, `benchmark.parameters.warmup_seconds` MUST be present
   - `output.directory`, `output.format` MUST be present

2. **Type Validation**:
   - All integer fields MUST be integers (not floats or strings)
   - All string fields MUST be strings
   - All boolean fields MUST be booleans
   - `cpu_affinity` MUST be an array of integers
   - `plugins` MUST be an array of objects

3. **Range Validation**:
   - `cortex_version` MUST equal 1
   - `dataset.channels` MUST be > 0
   - `dataset.sample_rate_hz` MUST be > 0
   - `realtime.priority` MUST be in [1, 99] if scheduler is `fifo` or `rr`
   - `realtime.deadline_ms` MUST be > 0
   - `benchmark.parameters.duration_seconds` MUST be > 0
   - `benchmark.parameters.repeats` MUST be ≥ 1
   - `benchmark.parameters.warmup_seconds` MUST be ≥ 0
   - `plugins` array length MUST be ≤ 16 (CORTEX_MAX_PLUGINS)

4. **Enum Validation**:
   - `dataset.format` MUST be `"float32"` in v1.0
   - `realtime.scheduler` MUST be `"fifo"`, `"rr"`, `"deadline"`, or `"other"`
   - `benchmark.load_profile` MUST be `"idle"`, `"medium"`, or `"heavy"`
   - `output.format` MUST be `"ndjson"` or `"csv"`
   - `plugins[i].status` MUST be `"draft"` or `"ready"`

5. **Semantic Validation**:
   - `dataset.path` MUST refer to an accessible file or directory
   - If `realtime.scheduler` is `"deadline"`, all `deadline.*` fields MUST be present
   - Each `plugins[i].spec_uri` MUST point to a valid kernel specification directory
   - If plugins are specified, each entry MUST include `adapter_path`

6. **Cross-Field Validation**:
   - For each plugin, `runtime.channels` (from kernel spec) MUST equal `dataset.channels`
   - CPU core IDs in `cpu_affinity` MUST be valid for the target system

Implementations MUST report validation errors with the field path and reason (e.g., `"realtime.priority: value 150 exceeds maximum 99"`).

### **5.2.5 Default Values**

If the `plugins` section is omitted, implementations MUST enable auto-detection mode (see Section 5.1.7). All other top-level sections are REQUIRED and have no defaults.

Within the `benchmark` section:
- If `load_profile` is omitted, default to `"idle"`

### **5.2.6 Example Configurations**

#### **Example 1: Auto-Detection Mode**
```yaml
cortex_version: 1

dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  format: "float32"
  channels: 64
  sample_rate_hz: 160

realtime:
  scheduler: fifo
  priority: 90
  cpu_affinity: [0]
  deadline_ms: 500

benchmark:
  parameters:
    duration_seconds: 120
    repeats: 5
    warmup_seconds: 10
  load_profile: "medium"

output:
  directory: "results"
  format: "ndjson"

# No plugins section - automatically discover all built kernels
```

This configuration runs all built kernels from `primitives/kernels/v1/` in alphabetical order.

#### **Example 2: Explicit Plugin Selection**
```yaml
cortex_version: 1

system:
  name: "notch-filter-test"
  description: "Test notch filter with European power line frequency"

dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  format: "float32"
  channels: 64
  sample_rate_hz: 160

realtime:
  scheduler: fifo
  priority: 85
  cpu_affinity: [0]
  deadline_ms: 500

power:
  governor: "performance"
  turbo: false

benchmark:
  metrics: [latency, jitter, throughput]
  parameters:
    duration_seconds: 60
    repeats: 3
    warmup_seconds: 5
  load_profile: "idle"

output:
  directory: "results/notch-test"
  format: "ndjson"
  include_raw_data: false

plugins:
  - name: "notch_iir"
    status: ready
    spec_uri: "primitives/kernels/v1/notch_iir@f32"
    spec_version: "1.0.0"
    adapter_path: "primitives/adapters/v1/native/cortex_adapter_native"
    params:
      f0_hz: 50.0  # European power line (50Hz)
      Q: 35.0      # Narrow notch
```

This configuration runs a single kernel with custom parameters.

### **5.2.7 Kernel Auto-Detection**

When the `plugins` section is **omitted** from the configuration file, implementations MUST automatically discover and run all built kernels.

**Discovery Algorithm**:
1. Scan directories matching pattern `primitives/kernels/v{N}/{name}@{dtype}/`
2. For each directory, check for:
   - Implementation file `{name}.c`
   - Compiled shared library `lib{name}.dylib` (macOS) or `lib{name}.so` (Linux)
3. If both exist, include the kernel in the run
4. Load runtime configuration from `spec.yaml` if present
5. If `spec.yaml` is missing, use default configuration (W=160, H=80, C from dataset, dtype=float32)
6. Sort discovered kernels alphabetically by name for reproducibility

**Auto-Detection vs. Explicit Mode**:

| Feature | Auto-Detection | Explicit |
|---------|----------------|----------|
| Configuration verbosity | Minimal (no `plugins:` section) | Full specification required |
| Kernel selection | All built kernels | User-specified subset |
| Parameter customization | Defaults from `spec.yaml` | Custom `params` per kernel |
| Use case | Comprehensive benchmarking | Focused testing, production |

**Empty Plugins Array**: If the configuration includes an empty `plugins: []` array, implementations MUST run zero kernels. This is valid for testing the harness infrastructure without kernel execution.

**Kernel Filtering**: Implementations MAY provide a runtime mechanism (e.g., environment variable `CORTEX_KERNEL_FILTER`) to filter auto-detected kernels without modifying the configuration file. This is OPTIONAL and not part of the normative schema.

---

## **5.3 Kernel Specification Format**

Each kernel MUST provide a `spec.yaml` file in its directory (e.g., `primitives/kernels/v1/notch_iir@f32/spec.yaml`). This file defines the kernel's ABI contract, numerical tolerances, and validation requirements.

### **5.3.1 Schema Definition**

CORTEX v1.0 supports **two specification formats**:

1. **Modern Format** (RECOMMENDED): Kernel metadata nested under `kernel:` key
2. **Legacy Format**: Flat structure with top-level `name`, `version`, `dtype`

Implementations MUST support both formats for backward compatibility. The legacy format is deprecated and SHOULD NOT be used for new kernels.

#### **Modern Format**
```yaml
kernel:
  name: string                       # Kernel identifier
  version: string                    # Semantic version
  dtype: string                      # Data type (e.g., "float32")
  description: string                # OPTIONAL: Brief description
  trainable: boolean                 # OPTIONAL: Requires calibration (default: false)

abi:
  version: integer                   # OPTIONAL: ABI version (default: 1)
  capabilities: [string, ...]        # OPTIONAL: Required capabilities
  input_shape: [integer, integer]    # [window_length, channels]
  output_shape: [integer, integer]   # [window_length, channels]
  stateful: boolean                  # OPTIONAL: Maintains state (default: false)

numerical:
  tolerances:
    float32:                         # Per-dtype tolerances
      rtol: float                    # Relative tolerance
      atol: float                    # Absolute tolerance
    quantized:                       # OPTIONAL: For q15/q7 variants
      rtol: float
      atol: float

oracle:
  path: string                       # Path to oracle script (e.g., "oracle.py")
  function: string                   # Oracle function name
  dependencies: [string, ...]        # OPTIONAL: Required packages

calibration:                         # OPTIONAL: For trainable kernels
  min_windows: integer               # Minimum calibration data
  recommended_windows: integer
  max_duration_sec: integer

algorithm:                           # OPTIONAL: Algorithm metadata
  family: string
  variant: string
  # ... kernel-specific fields

references:                          # OPTIONAL: Citations
  - string                           # Bibliography entries
```

#### **Legacy Format**
```yaml
name: string
version: string
dtype: string
description: string                  # OPTIONAL

runtime:
  window_length_samples: integer
  hop_samples: integer
  channels: integer
  allow_in_place: boolean

params: {}                           # Kernel-specific parameters

tolerances:
  rtol: float
  atol: float

author: string                       # OPTIONAL
purpose: string                      # OPTIONAL
category: string                     # OPTIONAL
complexity: string                   # OPTIONAL
```

The legacy format is simpler but lacks per-dtype tolerances and trainability support. Implementations MUST detect the format by checking for the presence of a top-level `kernel:` key.

### **5.3.2 Field Semantics**

#### **kernel** (Modern Format)
- `name`: MUST match the kernel directory name
- `version`: SHOULD follow semantic versioning (e.g., `"1.0.0"`)
- `dtype`: Data type identifier. Valid values in v1.0: `"float32"`
- `description`: OPTIONAL human-readable description
- `trainable`: If `true`, kernel requires offline calibration (ABI v3 feature)

#### **abi**
- `version`: ABI version. MUST be `1` or `3`. Default is `1`
- `capabilities`: Array of required capabilities. Valid values:
  - `"offline_calibration"`: Requires `cortex_calibrate()` before use
- `input_shape`: `[W, C]` where W is window length and C is channels. Use `null` for runtime-determined values (e.g., `[160, null]` means W=160, C from dataset)
- `output_shape`: `[W_out, C_out]`. Output dimensions. Use `null` for runtime-determined values
- `stateful`: If `true`, kernel maintains internal state across windows

**Shape Inference Rules**:
- If `input_shape[1]` is `null`, implementations MUST substitute `dataset.channels`
- If `output_shape[1]` is `null`, implementations MUST substitute `dataset.channels`
- Window length (`input_shape[0]`) MUST be specified explicitly in v1.0

#### **numerical**
- `tolerances.float32.rtol`: Relative tolerance for floating-point validation (typically 1.0e-5)
- `tolerances.float32.atol`: Absolute tolerance for near-zero values (typically 1.0e-6)
- `tolerances.quantized`: OPTIONAL. Tolerances for quantized variants (q15, q7)

Tolerances define acceptable error when comparing kernel output to oracle output. See Section 6 (Validation Protocol) for usage.

#### **oracle**
- `path`: Relative path to oracle implementation (e.g., `"oracle.py"`)
- `function`: Oracle function name. The oracle module MUST export this function
- `dependencies`: OPTIONAL. List of Python packages required to run the oracle

Implementations MUST resolve `path` relative to the kernel directory.

#### **calibration** (Trainable Kernels Only)
- `min_windows`: Minimum number of training windows for convergence
- `recommended_windows`: Recommended training set size
- `max_duration_sec`: Typical calibration duration

This section is REQUIRED if `trainable: true`.

#### **algorithm** (Optional Metadata)
- `family`: Algorithm family (e.g., `"Independent Component Analysis"`)
- `variant`: Specific variant (e.g., `"FastICA with symmetric decorrelation"`)
- Additional fields MAY be included for documentation purposes

#### **references** (Optional Metadata)
- Array of bibliography entries (typically academic papers)

### **5.3.3 Runtime Parameters**

Kernels MAY accept runtime parameters specified in the run configuration `plugins[i].params` object. Parameters are kernel-specific and defined by the kernel developer.

**Common Parameter Patterns**:

| Kernel | Parameters | Description |
|--------|------------|-------------|
| `notch_iir` | `f0_hz`, `Q` | Notch frequency (Hz) and quality factor |
| `goertzel` | `alpha_low`, `alpha_high`, `beta_low`, `beta_high` | Frequency bands for power estimation |
| `car` | `exclude_channels` | Channel indices to exclude from reference |

Implementations MUST pass parameters to the kernel via the accessor API defined in `sdk/kernel/lib/params/README.md`. Parameters are serialized as JSON and made available through `cortex_params_get_*()` functions.

**Example Parameter Usage**:
```yaml
plugins:
  - name: "notch_iir"
    params:
      f0_hz: 60.0  # Notch at 60Hz
      Q: 30.0      # Quality factor
```

The kernel accesses parameters in C:
```c
double f0_hz = cortex_params_get_double(params, "f0_hz", 60.0);  // Default 60.0
double Q = cortex_params_get_double(params, "Q", 30.0);
```

If a parameter is not provided, implementations MUST use the kernel's default value. Kernels MUST document available parameters in their README files.

### **5.3.4 Validation Rules**

Implementations MUST validate kernel specifications during configuration loading:

1. **Required Fields** (Modern Format):
   - `kernel.name`, `kernel.version`, `kernel.dtype` MUST be present
   - `abi.input_shape`, `abi.output_shape` MUST be present
   - `numerical.tolerances.float32.rtol`, `numerical.tolerances.float32.atol` MUST be present
   - `oracle.path`, `oracle.function` MUST be present

2. **Required Fields** (Legacy Format):
   - `name`, `version`, `dtype` MUST be present
   - `runtime.window_length_samples`, `runtime.hop_samples`, `runtime.channels` MUST be present
   - `tolerances.rtol`, `tolerances.atol` MUST be present

3. **Type Validation**:
   - All integer fields MUST be integers
   - All float fields MUST be floats or integers
   - All boolean fields MUST be booleans
   - `abi.input_shape`, `abi.output_shape` MUST be 2-element arrays

4. **Semantic Validation**:
   - `oracle.path` MUST point to an existing file
   - If `trainable: true`, `calibration` section MUST be present
   - If `abi.version: 3`, `capabilities` MUST include `"offline_calibration"`

5. **Cross-Field Validation**:
   - `kernel.name` MUST match the kernel directory name
   - `kernel.dtype` MUST match the directory suffix (e.g., `@f32` → `dtype: "float32"`)

Implementations MUST report validation errors with the file path and specific issue.

### **5.3.5 Example Specifications**

#### **Example 1: Stateless Kernel (Modern Format)**
```yaml
kernel:
  name: "goertzel"
  version: "1.0.0"
  dtype: "float32"

abi:
  input_shape: [160, null]  # W=160, C from dataset
  output_shape: [2, null]   # 2 frequency bands, C from dataset
  stateful: false

numerical:
  tolerances:
    float32:
      rtol: 1.0e-5
      atol: 1.0e-6

oracle:
  path: "oracle.py"
  function: "goertzel_bandpower_ref"
  dependencies: ["numpy"]
```

#### **Example 2: Stateful Kernel (Modern Format)**
```yaml
kernel:
  name: "notch_iir"
  version: "1.0.0"
  dtype: "float32"

abi:
  input_shape: [160, null]
  output_shape: [160, null]
  stateful: true            # IIR filter maintains state

numerical:
  tolerances:
    float32:
      rtol: 1.0e-5
      atol: 1.0e-6
    quantized:
      rtol: 1.0e-3
      atol: 1.0e-3

oracle:
  path: "oracle.py"
  function: "notch_ref"
  dependencies: ["scipy"]
```

#### **Example 3: Trainable Kernel (Modern Format)**
```yaml
kernel:
  name: "ica"
  version: "v1"
  dtype: "float32"
  description: "Independent Component Analysis for artifact removal"
  trainable: true

abi:
  version: 3
  capabilities:
    - offline_calibration
  input_shape:
    window_length: 160
    channels: 64
  output_shape:
    window_length: 160
    channels: 64
  stateful: false

calibration:
  min_windows: 100
  recommended_windows: 500
  max_duration_sec: 300

algorithm:
  family: "Independent Component Analysis"
  variant: "FastICA (symmetric decorrelation)"
  nonlinearity: "tanh"
  max_iterations: 200
  tolerance: 1.0e-4

numerical:
  tolerance:
    rtol: 1.0e-4
    atol: 1.0e-5

oracle:
  calibrate_function: "calibrate_ica"
  apply_function: "apply_ica"
  path: "oracle.py"
  dependencies: ["numpy", "scipy", "sklearn"]

references:
  - "Hyvärinen, A., & Oja, E. (2000). Independent component analysis: algorithms and applications. Neural networks, 13(4-5), 411-430."
```

#### **Example 4: No-Op Kernel (Legacy Format)**
```yaml
name: "noop"
version: "1.0.0"
dtype: "float32"
description: "Identity function for measuring harness overhead"

runtime:
  window_length_samples: 160
  hop_samples: 80
  channels: 64
  allow_in_place: true

params: {}

tolerances:
  rtol: 1.0e-7
  atol: 1.0e-9

author: "Weston Voglesonger"
purpose: "Harness overhead measurement"
category: "benchmark"
complexity: "O(1)"
```

---

## **5.4 Rationale**

### **5.4.1 Why YAML Over JSON/TOML?**

**JSON** lacks comment support, making it unsuitable for research configurations where parameter choices require documentation for reproducibility.

**TOML** has inconsistent complex nesting support and less ecosystem adoption in infrastructure tools.

**YAML** provides:
- Rich comment syntax for inline documentation
- Natural hierarchical structure for kernel parameters
- Wide tool support (editors, validators, parsers)
- Industry standard status (Kubernetes, CI/CD, Ansible)

### **5.4.2 Why Auto-Detection?**

Manual kernel listing in configurations creates maintenance burden:
1. New kernels require configuration updates
2. "Run all benchmarks" workflows are verbose
3. Risk of forgetting to include kernels in comprehensive tests

Auto-detection:
- Reduces configuration verbosity
- Ensures new built kernels are automatically included
- Preserves explicit control when needed (researchers can still list specific kernels)

The design trades configuration explicitness for usability. The trade-off is appropriate for research prototyping while preserving production use cases.

### **5.4.3 Why Parsed-But-Unused Fields?**

Three categories justify accepting unused fields:

1. **Platform Differences**: `power.governor` works on Linux but not macOS. Rejecting it on macOS breaks cross-platform configurations
2. **Future Extensibility**: `system.name`, `benchmark.metrics` are reserved for planned features. Accepting them now avoids migration pain
3. **Documentation Value**: Even if unused, fields like `system.description` provide context for human readers

Implementations SHOULD log warnings for unused fields to inform users, but MUST NOT reject configurations.

### **5.4.4 Why Two Kernel Spec Formats?**

The **legacy format** predates multi-dtype support and trainable kernels. It remains in use for the `noop` kernel (a simple benchmark primitive).

The **modern format** supports:
- Per-dtype tolerances (necessary for quantized variants)
- Trainability metadata (ABI v3 calibration requirements)
- Structured ABI versioning

Supporting both formats:
- Preserves backward compatibility with existing kernels
- Avoids forcing immediate migration of simple kernels
- Documents recommended practice (modern format) while accepting legacy

Future versions MAY deprecate the legacy format after all kernels migrate.

### **5.4.5 Why Maximum 16 Plugins?**

The `CORTEX_MAX_PLUGINS` limit (16) reflects:
1. **Stack Allocation**: Plugin metadata is stack-allocated for simplicity. Large arrays risk stack overflow
2. **Practical Constraints**: Current repository has 8 kernels. 16 provides 2× headroom
3. **Performance**: More plugins increase benchmark duration linearly. 16 is reasonable for overnight runs

The limit MAY be increased in future versions if workloads demand it. The static limit simplifies implementation and avoids dynamic allocation in performance-critical paths.

---

## **5.5 Conformance**

An implementation conforms to this specification if:

1. It accepts all valid YAML files matching the schema in Section 5.2
2. It rejects invalid files with descriptive error messages
3. It enforces all validation rules in Sections 5.2.4 and 5.3.4
4. It supports both modern and legacy kernel specification formats
5. It implements auto-detection mode when `plugins` is omitted
6. It handles platform-specific fields gracefully (parse but may ignore)
7. It respects the `CORTEX_MAX_PLUGINS` limit

Implementations MAY provide extensions (e.g., environment variable overrides, additional output formats) as long as they remain compatible with this specification.

---

**End of Section 5**
