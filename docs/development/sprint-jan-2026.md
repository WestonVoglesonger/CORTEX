# CORTEX Sprint Plan: January 2026
**Period**: January 13-26, 2026
**Focus**: Consolidation → Validation → Generalization
**Goal**: Transform raw capabilities into validated, documented system ready for external use

---

## Executive Summary



**Context**: Past week shipped 4 major features forming complete vertical stack (synthetic datasets, test infrastructure, auto-deploy, TCP daemon mode). These capabilities are **individually tested** (163 tests passing, multiple benchmark runs successful) but need **cross-platform validation** on Jetson hardware.

**Current State**:
- ✅ **Synthetic dataset generation**: 27 tests passing, integration validated
- ✅ **Test infrastructure**: 163 tests passing (Engine, Adapter SDK, Kernel SDK, CLI)
- ✅ **Recent benchmarks**: Local runs successful (run-2026-01-12-001 through 008)
- ✅ **Auto-deploy**: Tested on Jetson hardware, working
- ⚠️ **High-channel scalability on Jetson**: Not yet tested remotely

**Validation Status**: Stack is 80% validated. Remaining work is documentation + CSP kernel (the actual new feature).

**Revised Strategy**:
- Week 1 (Days 1-3): **CSP kernel implementation** (the real work starts immediately)
- Week 1 (Day 4): **Documentation sprint** (auto-deploy guide, changelog, release notes)
- Week 1 (Day 5): **Jetson CSP validation** + optional high-channel scalability test
- Week 2 (Days 1-5): **FLEX TIME** - Use for CSP refinement, additional trainable kernels, or productization

**Success Metric**: Demo `cortex pipeline --device nvidia@jetson --kernel csp` working end-to-end with auto-generated 1024-channel synthetic datasets by January 26.

---

## Sprint Architecture

**REVISED** (based on actual validation status - auto-deploy already works on Jetson):

```
Week 1: CSP Kernel + Documentation
├── CSP Algorithm Implementation (3 days) — PRIORITY 1
├── Documentation Sprint (1 day) — Capture auto-deploy knowledge
└── Jetson CSP Validation (1 day) — Prove cross-platform

Week 2: FLEX TIME (Multiple Options)
├── Option A: Additional trainable kernels (PCA, LDA)
├── Option B: Productization (error messages, install.sh, tutorials)
├── Option C: High-channel scalability validation on Jetson
├── Option D: Energy measurement infrastructure (RAPL, INA226)
└── Option E: Serial transport for STM32
```

**Rationale**: Since auto-deploy is validated, Week 1 can focus on **actual new feature** (CSP). Week 2 becomes strategic choice based on Week 1 learnings.

---

## Week 1: CSP Kernel + Documentation

**Objective**: Implement second trainable kernel to prove ABI v3 generalization. Document recent features.

### Day 1-3: CSP Algorithm Implementation

**SHIFTED FROM WEEK 2** - Since auto-deploy is validated, start CSP immediately.

**Goal**: Validate auto-deploy + synthetic datasets + TCP daemon as integrated system on real ARM64 hardware.

#### Pre-Flight Checklist
- [ ] Physical access to Jetson device confirmed
- [ ] SSH keypair configured (`ssh nvidia@jetson` works passwordless)
- [ ] Jetson network reachable from development machine
- [ ] Development machine has latest CORTEX build (`git pull && make clean && make all`)

#### Validation Matrix

**Phase 1: Connectivity Smoke Test** (30 minutes)
```bash
# Test 1: Manual connection (baseline)
ssh nvidia@jetson "uname -a"  # Verify ARM64 Linux

# Test 2: Auto-deploy with noop kernel (simplest case)
cortex run --device nvidia@jetson --kernel noop --duration 1 --repeats 1

# Expected: Adapter deployed, noop runs, telemetry collected, cleanup successful
# Success criteria: Zero errors, results/run-*/kernel-data/noop/telemetry.ndjson exists
```

**Phase 2: Kernel Suite Validation** (2 hours)
- [ ] **noop**: Baseline overhead measurement
- [ ] **car**: Stateless kernel, 160×64 output
- [ ] **notch_iir**: Stateless kernel with parameters (f0_hz, Q)
- [ ] **bandpass_fir**: Compute-heavy (129 taps)
- [ ] **goertzel**: Output dimension override (160×64 → 2×64)
- [ ] **welch_psd**: Output dimension override (160×64 → 129×64)
- [ ] **ica**: Trainable kernel with calibration state

For each kernel:
```bash
# Run with 64-channel PhysioNet data (baseline)
cortex run --device nvidia@jetson --kernel <kernel> --duration 5 --repeats 3

# Check for:
# 1. Zero deadline misses
# 2. P99 latency < 100ms (500ms deadline)
# 3. Device timing fields populated (device_tstart_ns, device_tend_ns)
# 4. No adapter crashes or hangs
```

**Phase 3: Synthetic Dataset Scalability** (3 hours)
- [ ] **64 channels**: Baseline (matches PhysioNet)
- [ ] **256 channels**: 4× scale-up
- [ ] **512 channels**: 8× scale-up
- [ ] **1024 channels**: 16× scale-up (Neuralink N1 scale)
- [ ] **2048 channels**: 32× scale-up (stress test)

Test configuration template:
```yaml
# primitives/configs/jetson-scalability-<channels>ch.yaml
dataset:
  type: generator
  generator: primitives/datasets/v1/synthetic
  params:
    signal_type: pink_noise
    duration_sec: 30
    sample_rate_hz: 160
    num_channels: <channels>
    seed: 42

kernels:
  - name: noop  # Minimal processing for overhead measurement
    adapter_path: auto  # Auto-deploy handles this
    spec_uri: primitives/kernels/v1/noop@f32

execution:
  duration_sec: 10
  warmup_windows: 5
```

For each channel count:
```bash
cortex run --device nvidia@jetson \
  -c primitives/configs/jetson-scalability-<channels>ch.yaml

# Document:
# - P50/P95/P99 latency scaling (linear? sublinear?)
# - Memory footprint on Jetson (check with `ssh nvidia@jetson free -h`)
# - Thermal throttling (check tegrastats output)
# - Network bandwidth usage (40KB windows * hops per second)
```

**Phase 4: ICA Trainable Kernel Workflow** (1 hour)
```bash
# 1. Calibrate on development machine (x86)
cortex calibrate --kernel ica \
  --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
  --windows 500 \
  --output /tmp/ica_model.cortex_state

# 2. Validate calibration locally (x86)
cortex validate --kernel ica --state /tmp/ica_model.cortex_state

# 3. Run on Jetson with pre-trained state (ARM64)
cortex run --device nvidia@jetson --kernel ica \
  --state /tmp/ica_model.cortex_state \
  --duration 10

# Expected: State transferred via auto-deploy, ICA runs with pre-trained unmixing matrix
# Success criteria: P99 latency < 100ms, no init failures
```

**Phase 5: TCP Daemon Multi-Session Test** (30 minutes)
```bash
# Start adapter in daemon mode (persists across kernel runs)
ssh nvidia@jetson "cd /tmp && ./cortex_adapter_native tcp://:9000 &"

# Run multiple kernels sequentially without restarting adapter
cortex run --device tcp://jetson:9000 --kernel noop --duration 5
cortex run --device tcp://jetson:9000 --kernel car --duration 5
cortex run --device tcp://jetson:9000 --kernel goertzel --duration 5

# Check adapter still running: ssh nvidia@jetson "pgrep cortex_adapter"
# Success criteria: All 3 kernels execute successfully, single adapter process
```

#### Documentation Artifacts

Create `experiments/jetson-validation-2026-01-13/` with:
- [ ] `README.md` - Methodology, hardware specs, findings
- [ ] `configs/` - All test configurations used
- [ ] `results/` - Telemetry aggregates (not full NDJSON, just summaries)
- [ ] `analysis.py` - Script to generate comparison plots
- [ ] `ISSUES.md` - Every failure mode encountered, workarounds applied

**Key Questions to Answer:**
1. Does latency scale linearly with channel count on ARM64?
2. What's the maximum channel count Jetson can handle at 160Hz?
3. Are there platform-specific issues (endianness, governor, thermal)?
4. Does auto-deploy cleanup work correctly on unexpected failures?

---

### Day 4: Documentation Sprint

**Goal**: Externalize knowledge from auto-deploy work. Enable future users.

**Time-boxed to 1 day** since validation is already complete.

#### Priority 1: Auto-Deploy User Guide

**File**: `docs/guides/using-auto-deploy.md` (NEW)

**Contents**:
- Quick start example (simplest case: `--device user@host`)
- Connection modes (SSH, TCP manual, local)
- Configuration options (custom ports, IPv6, config-based device)
- Troubleshooting guide:
  - SSH authentication failures (key permissions, agent forwarding)
  - Port conflicts (adapter already running on 9000)
  - Firewall issues (blocked TCP connections)
  - Build failures on remote device (missing compiler, wrong architecture)
  - Cleanup failures (orphaned processes, stale sockets)
- Platform-specific notes (Jetson, Raspberry Pi, x86 Linux servers)
- Example workflow: Development loop (iterate locally, deploy remotely)

**Success Criteria**:
- [ ] User with fresh Jetson can follow guide start-to-finish
- [ ] Every error message from auto-deploy is documented with solution

#### Priority 2: Synthetic Datasets Tutorial

**File**: `docs/guides/synthetic-datasets.md` (AUGMENT EXISTING)

**Add sections**:
- **When to use synthetic vs real datasets**
  - Scalability testing (high channel counts)
  - Filter validation (known frequency content)
  - Kernel development (controlled signal properties)
  - Performance benchmarking (reproducible across platforms)
- **Parameter selection guide**
  - Pink noise: General-purpose EEG-like spectrum (alpha/beta/gamma bands)
  - Sine waves: Filter validation, Goertzel accuracy testing
  - Duration: Minimum for statistical stability (30s = ~240 windows)
  - Seed: Reproducibility across runs and platforms
- **Memory characteristics**
  - Chunked generation strategy (when it kicks in)
  - Disk vs memory trade-offs
  - Cleanup behavior (temp files, modified configs)
- **Real-world examples**
  - Example 1: Validate bandpass filter with 10Hz sine wave
  - Example 2: Stress test ICA at 1024 channels
  - Example 3: Cross-platform benchmarking with fixed seed

**Success Criteria**:
- [ ] User can choose correct signal type for their use case
- [ ] All example configs are tested and work

#### Priority 3: Changelog Updates

**File**: `CHANGELOG.md` (UPDATE)

Add under `## [Unreleased]`:

```markdown
### Added

- **Synthetic Dataset Generation** - Generator-based dataset primitives
  - Signal types: Pink noise (1/f spectrum), sine waves (known frequencies)
  - Scalability: Validated up to 2048 channels (Neuralink scale)
  - Memory-safe: Chunked generation (<200MB RAM regardless of channel count)
  - Deterministic: Reproducible via seed parameter
  - CLI integration: Automatic detection, transparent pre-generation
  - Addresses industry channel gap (public datasets: 128ch, modern devices: 1024-1600ch)
  - Documentation: docs/guides/synthetic-datasets.md
  - Validation: experiments/high-channel-scalability-2026-01-12/

- **Auto-Deploy Device Adapters** - SSH-based remote execution
  - One-command deployment: cortex run --device user@host --kernel <name>
  - Connection modes: SSH auto-deploy, TCP manual, local (default)
  - Custom SSH ports: user@host:2222
  - IPv6 support: user@[fe80::1]:2222
  - Config-based devices: device: "user@host" in YAML
  - Device-side validation with graceful fallback
  - Dual readiness checks (remote lsof + host socket connectivity)
  - Robust cleanup (SIGTERM → SIGKILL → killall fallback)
  - Security: Command injection prevention (shlex.quote)
  - Documentation: docs/guides/using-auto-deploy.md (NEW)
  - Specification: docs/specs/auto-deploy-implementation.md (v3.5)

- **TCP Daemon Mode** - Multi-session adapter support
  - Remote adapters serve multiple benchmarks without restarting
  - Session isolation with graceful shutdown (SIGINT/SIGTERM)
  - Accept loop with 5s timeout
  - Local transport remains single-session for measurement isolation

### Changed

- **CLI Interface** - Unified device specification
  - Replaced --transport with --device flag
  - Device resolution: CLI --device > config device: > default local://
  - Backward compatible: tcp://host:port still works as --device argument

### Removed

- **Adapter System Bloat Removal** (-321 LOC)
  - Dead CleanupError exception (never raised)
  - IPv6 bracket parsing (YAGNI)
  - Over-engineered zombie detection
  - Unused adapter_boot_id field
  - Removed SHM transport (87 LOC) - unused shared memory implementation

### Fixed

- **Critical Security & Reliability**
  - SSH command injection (CRITICAL) - Added shlex.quote() sanitization
  - Adapter readiness race (CRITICAL) - Two-phase verification (lsof + connect)
  - Resource leaks (HIGH) - Guaranteed cleanup via try/finally
  - Gap detection in protocol (MEDIUM) - Restored bitmap tracking
  - Log truncation bug - Header size accounting
  - Port validation - 1-65535 range checks

### Documentation

- 23 protocol specification fixes (frame sizes, field names, struct layouts)
- Added docs/guides/using-auto-deploy.md (user guide)
- Updated docs/specs/auto-deploy-implementation.md to v3.5
- Root directory cleanup (-65KB documentation bloat)
```

**Success Criteria**:
- [ ] All features from past 2 weeks documented in changelog
- [ ] Breaking changes clearly marked
- [ ] Migration guide included where applicable

#### Priority 4: ABI v3 Migration Guide Completion

**File**: `docs/guides/migrating-to-abi-v3.md` (COMPLETE)

**Missing sections to add**:
- **Common Migration Errors**
  - Forgetting to set capabilities flag
  - Not validating calibration_state != NULL before dereferencing
  - Calibration state endianness issues (cross-platform)
  - State size exceeding CORTEX_MAX_STATE_SIZE (256MB)
- **Testing Your v3 Kernel**
  - Unit test checklist (malloc overflow checks, NULL validation)
  - Validation workflow (cortex validate --state)
  - Benchmark comparison (with vs without calibration)
- **Cross-Platform Considerations**
  - State file portability (little-endian serialization)
  - Float precision differences (x86 vs ARM)
  - Alignment requirements (struct packing)

**Success Criteria**:
- [ ] Kernel developer can migrate v2 → v3 using only this guide
- [ ] All ICA implementation patterns documented as reference

#### Priority 5: Release Notes Draft

**File**: `docs/RELEASE_NOTES_v0.5.0.md` (NEW)

**Template**:
```markdown
# CORTEX v0.5.0 Release Notes
**Release Date**: January 26, 2026
**Codename**: "Scalability & Remote Execution"

## Highlights

- **Synthetic Dataset Generation**: Test at industry scale (2048 channels)
- **Auto-Deploy Device Adapters**: One-command remote benchmarking
- **TCP Daemon Mode**: Multi-session remote execution
- **CSP Kernel**: Second trainable kernel (motor imagery BCI)

## Breaking Changes

None - fully backward compatible with v0.4.0.

## New Features

[Details from changelog...]

## Upgrade Guide

1. Reinstall with latest dependencies: pip install -e .
2. Update configs to use --device flag (--transport deprecated)
3. Review auto-deploy documentation if using remote execution

## Known Issues

- Auto-deploy requires passwordless SSH (key-based authentication)
- Synthetic datasets with >512 channels use disk-backed generation (slower)
- CSP kernel requires PhysioNet motor imagery dataset

## Contributors

[Your name/affiliation]

## Acknowledgments

[If applicable - funding sources, hardware donations, etc.]
```

**Success Criteria**:
- [ ] Release notes ready to publish on GitHub
- [ ] All breaking changes documented
- [ ] Upgrade path is clear

---

### Day 5: Jetson CSP Validation

**Goal**: Prove CSP works cross-platform (x86 + ARM64).

#### Validation Tasks (Day 5)

```bash
# 1. Run CSP on Jetson to verify ARM64 compatibility
cortex run --device nvidia@jetson --kernel csp \
  --state /tmp/csp_model.cortex_state \
  --duration 5

# 2. Compare latency: x86 vs ARM64
# Expected: ARM64 slightly slower (~1.5-2× due to lower clock speed)

# 3. (Optional) High-channel scalability test
cortex run --device nvidia@jetson \
  -c primitives/configs/jetson-scalability-1024ch.yaml
```

**Success criteria**:
- [ ] CSP runs successfully on ARM64
- [ ] State file transfers correctly (endianness validation)
- [ ] Latency still meets deadline (<100ms)
- [ ] (Stretch) 1024-channel synthetic dataset works on Jetson

#### Week 2 Planning

Based on Day 5 results, choose Week 2 focus:
- **Option A**: Additional trainable kernels (PCA, LDA) - Proves ABI v3 scales to 3+ kernels
- **Option B**: Productization sprint - Error messages, install.sh, tutorials
- **Option C**: Energy measurement - RAPL integration, INA226 sensor support
- **Option D**: Continue CSP refinement - Regularization, multi-class support
- **Option E**: Serial transport - STM32 embedded device support

---

## Week 2: FLEX TIME

**Objective**: Strategic choice based on Week 1 outcomes. Use freed-up time for highest-value work.

**Decision Point**: End of Week 1 Day 5 - evaluate CSP completion status and choose direction.

---

## CSP Kernel Implementation Details

**NOTE**: This section moved to Week 1 Days 1-3 since auto-deploy is already validated.

### Background: Common Spatial Patterns (CSP)

**Scientific Context**:
- **Domain**: Motor imagery BCI (imagining left vs right hand movement)
- **Problem**: Raw EEG has poor signal-to-noise ratio for motor imagery detection
- **Solution**: CSP finds spatial filters that maximize variance difference between classes
- **Applications**: P300 spellers, wheelchair control, prosthetic limbs

**Algorithm Overview**:
1. **Input**: Two classes of EEG data (left hand vs right hand imagery)
2. **Calibration**: Compute covariance matrices, solve generalized eigenvalue problem
3. **Output**: Spatial filters (W matrix) that project channels to discriminative subspace
4. **Real-time**: Apply W to incoming windows (simple matrix multiplication)

**Why CSP for CORTEX:**
- Validates trainable kernel workflow (same as ICA: calibrate → validate → run)
- Scientifically important (widely used in motor imagery BCI)
- Computationally simple in inference (just matrix-vector multiply)
- PhysioNet dataset has motor imagery tasks (R04, R08, R12 runs)

---

### Day 1-3: Algorithm Implementation

#### Task 1: CSP Algorithm Research (4 hours)

**Goal**: Understand CSP well enough to implement from scratch.

**Resources**:
- [x] MNE-Python CSP implementation (reference)
- [x] Original paper: Ramoser et al. (2000) "Optimal spatial filtering of single trial EEG during imagined hand movement"
- [x] Tutorial: Blankertz et al. (2008) "Optimizing Spatial Filters for Robust EEG Single-Trial Analysis"

**Key questions**:
1. What's the generalized eigenvalue problem formulation? (Cₗw = λCᵣw)
2. How many components to keep? (Typically 2-6 for motor imagery)
3. What's the calibration data structure? (Multiple trials per class)
4. How to handle covariance matrix regularization? (Add λI for numerical stability)

**Deliverable**:
- [ ] Pseudocode for CSP calibration algorithm
- [ ] Pseudocode for CSP inference (apply filters)
- [ ] Notes on numerical stability considerations

#### Task 2: Directory Structure Setup (15 minutes)

```bash
mkdir -p primitives/kernels/v1/csp@f32
cd primitives/kernels/v1/csp@f32

# Create files
touch csp.c
touch Makefile
touch README.md
touch spec.yaml
touch oracle.py
touch requirements-oracle.txt
```

**spec.yaml template**:
```yaml
name: "csp"
version: "1.0.0"
dtype: "float32"
description: "Common Spatial Pattern (CSP) spatial filtering for motor imagery BCI"
category: "spatial_filtering"
abi_version: 3
trainable: true

parameters:
  n_components:
    type: integer
    default: 4
    description: "Number of CSP components to extract (top-N and bottom-N)"

input:
  window_length_samples: 160  # 1 second at 160 Hz
  num_channels: 64

output:
  window_length_samples: 160  # Preserved (time dimension unchanged)
  num_channels: "n_components"  # Reduced to CSP components

calibration:
  required: true
  min_windows: 200  # 100 per class minimum
  parameters:
    n_classes:
      type: integer
      default: 2
      description: "Number of motor imagery classes (e.g., left vs right hand)"

tolerances:
  rtol: 1e-4  # Looser than ICA (eigenvalue decomposition has more numerical error)
  atol: 1e-4
```

#### Task 3: C Implementation (2 days)

**File**: `primitives/kernels/v1/csp@f32/csp.c`

**Implementation checklist**:
- [ ] `cortex_calibrate()` - Offline training
  - [ ] Parse calibration parameters (n_components, n_classes)
  - [ ] Allocate memory for covariance matrices (C per class)
  - [ ] Compute per-class covariance from input windows
  - [ ] Solve generalized eigenvalue problem (Cₗw = λCᵣw)
  - [ ] Extract top-N and bottom-N eigenvectors
  - [ ] Return calibration state (W matrix: C × n_components)

- [ ] `cortex_init()` - Load pre-trained filters
  - [ ] Validate calibration state not NULL
  - [ ] Deserialize W matrix from calibration state
  - [ ] Validate dimensions match config (C channels, n_components)
  - [ ] Allocate runtime state (workspace buffers if needed)
  - [ ] Set capabilities = CORTEX_CAP_OFFLINE_CALIB

- [ ] `cortex_process()` - Apply spatial filters
  - [ ] Input validation (handle, input, output not NULL)
  - [ ] Matrix multiply: output = W^T × input (n_components × C) × (C × T) = (n_components × T)
  - [ ] Copy filtered data to output buffer

- [ ] `cortex_teardown()` - Cleanup
  - [ ] Free W matrix
  - [ ] Free workspace buffers

**Linear algebra helper functions**:
```c
// Compute covariance matrix: C = X^T × X / (n-1)
static void compute_covariance(const float *X, size_t rows, size_t cols, float *C);

// Generalized eigenvalue problem: Ax = λBx
// Returns eigenvalues in descending order, eigenvectors in columns of V
static int generalized_eigen(const float *A, const float *B, size_t n,
                              float *eigenvalues, float *V);

// Matrix multiply: C = A × B (m×k, k×n -> m×n)
static void matrix_multiply(const float *A, const float *B, size_t m, size_t k, size_t n, float *C);

// Regularize covariance: C = C + lambda * I (numerical stability)
static void regularize_covariance(float *C, size_t n, float lambda);
```

**Generalized eigenvalue decomposition strategy**:
- **Option 1 (Simple)**: Use Cholesky decomposition to reduce to standard eigenvalue problem
  - Compute L such that B = L × L^T (Cholesky of class average covariance)
  - Transform: L^-1 × A × L^-T → standard eigenvalue problem
  - Solve with Jacobi iteration (reuse ICA code)

- **Option 2 (Robust)**: Power iteration for top-k eigenvectors
  - Iteratively find dominant eigenvectors
  - Deflate and repeat for next component
  - More stable for ill-conditioned matrices

**Recommendation**: Start with Option 1 (Cholesky + Jacobi). It's cleaner and reuses ICA infrastructure.

**Memory safety**:
- [ ] SIZE_MAX overflow checks before all malloc() calls
- [ ] NULL checks after all malloc() calls
- [ ] Free all allocations on error paths

**Makefile template** (copy from ICA, adjust paths):
```makefile
KERNEL_NAME = csp
DTYPE = f32
TARGET = lib$(KERNEL_NAME).dylib  # .so on Linux
SDK_ROOT = ../../../../sdk/kernel
CFLAGS = -Wall -Wextra -O2 -std=c11 -fPIC -I$(SDK_ROOT)/include
LDFLAGS = -shared -L$(SDK_ROOT)/lib -lcortex -lm

$(TARGET): $(KERNEL_NAME).c
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)

clean:
	rm -f $(TARGET)
```

#### Task 4: Python Oracle (1 day)

**File**: `primitives/kernels/v1/csp@f32/oracle.py`

**Implementation checklist**:
- [ ] CLI interface matching ICA pattern:
  ```python
  # Test mode (no state)
  ./oracle.py --test --input data.float32 --output expected.float32 \
              --channels 64 --window-length 160

  # Calibration mode
  ./oracle.py --calibrate --input data.float32 --labels labels.npy \
              --n-components 4 --output model.cortex_state

  # Inference with state
  ./oracle.py --state model.cortex_state --input data.float32 \
              --output filtered.float32 --channels 64 --window-length 160
  ```

- [ ] Use MNE-Python CSP as reference implementation
  ```python
  from mne.decoding import CSP

  csp = CSP(n_components=4, reg=None, log=False)
  csp.fit(X_train, y_train)  # X: (trials, channels, samples), y: (trials,)
  X_filtered = csp.transform(X_test)
  ```

- [ ] State serialization matching `.cortex_state` format:
  - Magic: 0x43525458
  - Version: 3
  - ABI: 3
  - Payload size
  - Payload: W matrix (C × n_components) in row-major, little-endian float32

- [ ] Handle multi-trial calibration data:
  - Input: Single .float32 file with concatenated trials
  - Labels: .npy file with per-window class labels (0, 1, ..., n_classes-1)
  - Reshape to (trials, channels, samples) for MNE-Python CSP

**requirements-oracle.txt**:
```
numpy>=1.20.0
mne>=1.0.0
scipy>=1.7.0
```

**Validation script** (copy from ICA, adapt for CSP):
```python
def validate_csp_output(c_output, python_output, rtol=1e-4, atol=1e-4):
    """Compare C kernel output against Python oracle."""
    c_data = np.fromfile(c_output, dtype=np.float32)
    py_data = np.fromfile(python_output, dtype=np.float32)

    assert c_data.shape == py_data.shape, f"Shape mismatch: {c_data.shape} vs {py_data.shape}"

    # CSP output can have sign ambiguity (eigenvectors are unique up to sign)
    # Check both polarities
    diff_positive = np.abs(c_data - py_data)
    diff_negative = np.abs(c_data + py_data)
    diff = np.minimum(diff_positive, diff_negative)

    max_error = np.max(diff)
    assert np.allclose(c_data, py_data, rtol=rtol, atol=atol) or \
           np.allclose(c_data, -py_data, rtol=rtol, atol=atol), \
           f"Max error: {max_error} (exceeds tolerance)"
```

---

### Day 4: Validation & Testing

#### Task 1: Build & Unit Test (2 hours)

```bash
cd primitives/kernels/v1/csp@f32

# Build kernel
make clean && make

# Verify ABI symbols
nm libcsp.dylib | grep cortex
# Expected: cortex_init, cortex_process, cortex_teardown, cortex_calibrate

# Test calibration workflow
# 1. Extract motor imagery trials from PhysioNet
cd ../../../../datasets/tools
python3 extract_motor_imagery.py \
  --input ../physionet-motor-imagery/raw/S001R04.edf \
  --output /tmp/motor_imagery_trials.float32 \
  --labels /tmp/motor_imagery_labels.npy \
  --events "left_hand,right_hand"

# 2. Calibrate Python oracle
cd ../../primitives/kernels/v1/csp@f32
./oracle.py --calibrate \
  --input /tmp/motor_imagery_trials.float32 \
  --labels /tmp/motor_imagery_labels.npy \
  --n-components 4 \
  --channels 64 \
  --output /tmp/csp_oracle.cortex_state

# 3. Calibrate C kernel via SDK tool
../../../../sdk/kernel/tools/cortex_calibrate \
  libcsp.dylib \
  /tmp/motor_imagery_trials.float32 \
  --labels /tmp/motor_imagery_labels.npy \
  --n-components 4 \
  --output /tmp/csp_c.cortex_state

# 4. Compare calibration states
python3 -c "
import numpy as np
import struct

def load_state(path):
    with open(path, 'rb') as f:
        magic, version, abi, size = struct.unpack('<IIII', f.read(16))
        data = np.frombuffer(f.read(), dtype=np.float32)
    return data

oracle_W = load_state('/tmp/csp_oracle.cortex_state')
c_W = load_state('/tmp/csp_c.cortex_state')

print(f'Oracle W shape: {oracle_W.shape}')
print(f'C W shape: {c_W.shape}')
print(f'Max difference: {np.max(np.abs(oracle_W - c_W))}')
assert np.allclose(oracle_W, c_W, rtol=1e-4, atol=1e-4), 'Calibration mismatch!'
print('✓ Calibration validation passed')
"
```

**Success criteria**:
- [ ] Kernel builds without warnings
- [ ] All ABI v3 symbols present
- [ ] Calibration produces identical W matrices (within tolerance)

#### Task 2: End-to-End CLI Validation (2 hours)

```bash
# Full workflow via cortex CLI
cd /Users/westonvoglesonger/Projects/CORTEX

# 1. Calibrate
cortex calibrate --kernel csp \
  --dataset /tmp/motor_imagery_trials.float32 \
  --labels /tmp/motor_imagery_labels.npy \
  --n-components 4 \
  --windows 200 \
  --output /tmp/csp_model.cortex_state

# 2. Validate accuracy (C kernel vs Python oracle)
cortex validate --kernel csp \
  --state /tmp/csp_model.cortex_state \
  --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R04.float32

# Expected output:
# [validate] Testing CSP kernel with state...
# [validate] C kernel output: /tmp/cortex_validate_c_output.float32
# [validate] Python oracle output: /tmp/cortex_validate_oracle_output.float32
# [validate] Max error: 2.34e-05 (within tolerance 1e-4)
# [validate] ✓ CSP kernel validation PASSED

# 3. Benchmark performance
cortex run --kernel csp \
  --state /tmp/csp_model.cortex_state \
  --duration 10 \
  --repeats 3

# Check results
cat results/run-*/kernel-data/csp/telemetry.ndjson | \
  jq -s '[.[] | select(.window_id > 5)] |
         {p50: (map(.latency_ns) | sort | .[length/2]),
          p99: (map(.latency_ns) | sort | .[length*99/100])}'

# Expected: P99 < 100ms (500ms deadline for 80-sample hop at 160Hz)
```

**Success criteria**:
- [ ] `cortex calibrate` completes without errors
- [ ] `cortex validate` shows max error < 1e-4
- [ ] `cortex run` produces telemetry with zero deadline misses
- [ ] P99 latency < 10ms (CSP is just matrix multiply, should be fast)

#### Task 3: Jetson Cross-Platform Test (1 hour)

```bash
# Run on Jetson to verify ARM64 compatibility
cortex run --device nvidia@jetson --kernel csp \
  --state /tmp/csp_model.cortex_state \
  --duration 5

# Compare latency: x86 vs ARM64
# Expected: ARM64 slightly slower (~1.5-2× due to lower clock speed)
```

**Success criteria**:
- [ ] CSP runs successfully on ARM64
- [ ] State file transfers correctly (endianness validation)
- [ ] Latency still meets deadline (<100ms)

---

### Day 5: Documentation & Release

#### Task 1: CSP Kernel README (3 hours)

**File**: `primitives/kernels/v1/csp@f32/README.md`

**Sections**:
1. **Overview**
   - What is CSP?
   - Motor imagery BCI context
   - Relation to other spatial filters (ICA, PCA, CAR)

2. **Algorithm**
   - Mathematical formulation (generalized eigenvalue problem)
   - Calibration process (per-class covariance, eigen decomposition)
   - Inference process (spatial filtering via matrix multiply)

3. **Calibration Workflow**
   - Data requirements (labeled trials, minimum 100 per class)
   - Example: Extract motor imagery from PhysioNet
   - Command: `cortex calibrate --kernel csp ...`

4. **Validation**
   - How to verify correctness (cortex validate)
   - Expected tolerance (rtol=1e-4)

5. **Benchmarking**
   - Performance characteristics (should be ~2-5ms for 64ch → 4 components)
   - Comparison with other kernels

6. **Parameters**
   - n_components: How many CSP filters (typical: 2-6)
   - Regularization (if implemented)

7. **Scientific References**
   - Ramoser et al. (2000) - original paper
   - Blankertz et al. (2008) - practical tutorial
   - MNE-Python CSP - reference implementation

8. **Limitations**
   - Requires balanced classes (equal trials per class)
   - Sensitive to overfitting (needs sufficient calibration data)
   - Assumes stationary signal statistics

**Success criteria**:
- [ ] BCI researcher can understand CSP from README alone
- [ ] All commands are copy-pasteable and work
- [ ] Scientific context is accurate

#### Task 2: Update Documentation Index (1 hour)

**Files to update**:

1. **CLAUDE.md**:
   ```markdown
   **Kernels:** 8 validated implementations
   - `car` — Common Average Reference
   - `notch_iir` — 60Hz line noise removal
   - `bandpass_fir` — 8-30Hz passband
   - `goertzel` — Alpha/beta bandpower
   - `welch_psd` — Power spectral density
   - `ica` — Independent Component Analysis (trainable)
   - `csp` — Common Spatial Patterns (trainable)  # NEW
   - `noop` — Identity function (baseline)
   ```

2. **docs/guides/adding-kernels.md**:
   - Add CSP as second trainable kernel example
   - Update "Trainable Kernels" section with generalization patterns

3. **docs/architecture/abi_v3_specification.md**:
   - Add CSP to "Example Implementations" section
   - Document any new calibration patterns discovered

4. **primitives/kernels/README.md**:
   - Update kernel count (7 → 8)
   - Add CSP to kernel catalog table

**Success criteria**:
- [ ] CSP is discoverable from documentation
- [ ] All cross-references are updated

#### Task 3: Example Configuration (30 minutes)

**File**: `primitives/configs/cortex-csp-motor-imagery.yaml`

```yaml
# CSP Motor Imagery BCI Configuration
# Demonstrates trainable kernel with labeled multi-class data

system:
  name: "CSP Motor Imagery Classification"
  description: "Common Spatial Pattern spatial filtering for left vs right hand imagery"

dataset:
  # Pre-processed motor imagery trials (labeled)
  path: "datasets/motor-imagery/trials_S001.float32"
  labels: "datasets/motor-imagery/labels_S001.npy"  # Per-window class labels
  sample_rate_hz: 160
  num_channels: 64

kernels:
  - name: csp
    adapter_path: primitives/adapters/v1/native/cortex_adapter_native
    spec_uri: primitives/kernels/v1/csp@f32
    params: "n_components=4"  # Extract 4 CSP components
    calibration_state: "results/calibration/csp_model.cortex_state"

execution:
  window_length_samples: 160  # 1 second window
  hop_length_samples: 80      # 50% overlap
  duration_sec: 30
  warmup_windows: 10
  load_profile: "medium"      # Consistent CPU frequency

output:
  directory: "results/csp-motor-imagery"
  telemetry_format: "ndjson"
```

**Success criteria**:
- [ ] Config is self-documenting
- [ ] Works end-to-end with CSP kernel
- [ ] Demonstrates trainable kernel workflow

#### Task 4: Release Preparation (1 hour)

**Checklist**:
- [ ] All tests passing (`make tests`)
- [ ] Oracle validation passing (`cortex validate --kernel csp`)
- [ ] Jetson cross-platform test successful
- [ ] Documentation complete (README, CHANGELOG, release notes)
- [ ] Example configs tested
- [ ] Git status clean (no uncommitted changes)

**Release commands**:
```bash
# Tag release
git tag -a v0.5.0 -m "Release v0.5.0: Scalability & Remote Execution"

# Push to GitHub
git push origin main
git push origin v0.5.0

# Create GitHub Release (manual via web UI)
# - Title: "v0.5.0: Scalability & Remote Execution"
# - Body: Copy from docs/RELEASE_NOTES_v0.5.0.md
# - Attach: None (source code auto-attached by GitHub)
```

**Success criteria**:
- [ ] Release tagged in git
- [ ] GitHub release published
- [ ] Release notes accurate and complete

---

## Alternative: Productization Sprint

**If Week 1 validation reveals major issues**, pivot to this plan:

### Goal: Make existing features bulletproof

**Week 1: Remain as planned** (validation exposes issues)

**Week 2: Production Hardening**

#### Day 1-2: Error Message Audit
- [ ] Run every failure mode deliberately (bad config, missing files, network errors)
- [ ] Document every error message
- [ ] Improve clarity ("Connection refused" → "Cannot reach adapter on jetson:9000. Check SSH access and firewall.")
- [ ] Add error codes to documentation

#### Day 3: Installation Experience
- [ ] Write `install.sh` script (one-command setup)
- [ ] Test on fresh Ubuntu 22.04 VM
- [ ] Test on fresh macOS 14
- [ ] Document prerequisites clearly
- [ ] Add troubleshooting for common install failures

#### Day 4: 100-Benchmark Stress Test
- [ ] Run Jetson validation 100 times in loop
- [ ] Document every edge case encountered
- [ ] Fix intermittent failures
- [ ] Add retry logic where appropriate

#### Day 5: Tutorial Workflows
- [ ] Tutorial 1: First benchmark on local machine
- [ ] Tutorial 2: Remote execution on Jetson
- [ ] Tutorial 3: Trainable kernel workflow (ICA)
- [ ] Tutorial 4: High-channel scalability testing
- [ ] Tutorial 5: Multi-kernel comparison study

---

## Success Criteria Summary

### Week 1 Exit Criteria
- [ ] All 8 kernels run successfully on Jetson via auto-deploy
- [ ] Synthetic datasets validated at 64, 256, 512, 1024, 2048 channels
- [ ] ICA trainable kernel workflow works on remote hardware
- [ ] TCP daemon mode tested with multiple kernels
- [ ] 4 documentation artifacts created (auto-deploy guide, synthetic datasets tutorial, changelog, release notes)
- [ ] No P0/P1 bugs discovered during validation

### Week 2 Exit Criteria (CSP Path)
- [ ] CSP kernel implemented in pure C11
- [ ] Python oracle with full CLI support
- [ ] Validation passes (max error < 1e-4)
- [ ] Benchmarks show P99 < 10ms
- [ ] Works on both x86 and ARM64 (Jetson)
- [ ] Comprehensive README with motor imagery context
- [ ] Example config tested end-to-end
- [ ] Release v0.5.0 tagged and published

### Week 2 Exit Criteria (Productization Path)
- [ ] All error messages are clear and actionable
- [ ] `install.sh` works on Ubuntu and macOS
- [ ] 100-benchmark stress test passes with zero failures
- [ ] 5 tutorial workflows documented and tested
- [ ] Known issues list is comprehensive
- [ ] Troubleshooting guide covers all common failures

---

## Risk Mitigation

### High-Risk Items

1. **Jetson hardware access**
   - **Risk**: No physical Jetson available
   - **Mitigation**: Test on x86 Linux server instead (still validates auto-deploy)
   - **Impact**: Reduced ARM64 validation, but core features still tested

2. **CSP algorithm complexity**
   - **Risk**: Generalized eigenvalue decomposition harder than expected
   - **Mitigation**: Use Cholesky reduction to standard eigenvalue problem (reuse ICA code)
   - **Fallback**: Implement simpler trainable kernel (PCA) instead

3. **PhysioNet dataset unsuitable for CSP**
   - **Risk**: Motor imagery data has poor class separation
   - **Mitigation**: Use synthetic data with known class structure for validation
   - **Impact**: Less scientifically interesting, but still proves ABI v3 generalization

4. **Time estimate too aggressive**
   - **Risk**: 5 days for CSP is insufficient
   - **Mitigation**: Timebox to basic implementation, defer advanced features (regularization, multi-class)
   - **Fallback**: Release v0.5.0 with synthetic datasets + auto-deploy, defer CSP to v0.5.1

### Low-Risk Items

1. **Documentation time**: Unlikely to overrun (writing is straightforward)
2. **Jetson validation time**: Can parallelize (run overnight)
3. **Build failures**: Already validated locally, CI should catch issues

---

## Open Questions

### For User to Resolve

1. **Jetson Access**: Do you have physical access to Jetson right now?
   - Yes → Proceed as planned
   - No → Use x86 Linux server or defer to later sprint

2. **CSP Priority**: Is motor imagery scientifically important for your research goals?
   - Yes → CSP is valuable addition
   - No → Consider PCA or defer trainable kernel work

3. **Sprint Commitment**: Can you dedicate 2 full weeks to this sprint?
   - Yes → Proceed with plan
   - No → Consider extending timeline or reducing scope

4. **Release Timeline**: Is January 26 a hard deadline?
   - Yes → Be aggressive with scope cuts if needed
   - No → Can extend Week 2 if CSP takes longer

### For Later Resolution

1. **Serial transport priority**: When do you need STM32 support? (Q2 2026?)
2. **Energy measurement**: RAPL/INA226 integration timeline? (Q2 2026?)
3. **Fixed-point quantization**: Q15/Q7 kernels priority? (Q2-Q3 2026?)

---

## Appendix: Command Reference

### Jetson Validation Commands

```bash
# Pre-flight check
ssh nvidia@jetson "uname -a"

# Single kernel test
cortex run --device nvidia@jetson --kernel noop --duration 1 --repeats 1

# Full kernel suite
for kernel in noop car notch_iir bandpass_fir goertzel welch_psd ica csp; do
  echo "Testing $kernel..."
  cortex run --device nvidia@jetson --kernel $kernel --duration 5 --repeats 3
done

# Scalability test
for channels in 64 256 512 1024 2048; do
  echo "Testing ${channels} channels..."
  cortex run --device nvidia@jetson \
    -c primitives/configs/jetson-scalability-${channels}ch.yaml
done

# ICA trainable workflow
cortex calibrate --kernel ica --dataset data.float32 --windows 500 --output model.cortex_state
cortex validate --kernel ica --state model.cortex_state
cortex run --device nvidia@jetson --kernel ica --state model.cortex_state --duration 10

# TCP daemon multi-session
ssh nvidia@jetson "cd /tmp && ./cortex_adapter_native tcp://:9000 &"
cortex run --device tcp://jetson:9000 --kernel noop --duration 5
cortex run --device tcp://jetson:9000 --kernel car --duration 5
```

### CSP Development Commands

```bash
# Build
cd primitives/kernels/v1/csp@f32 && make clean && make

# Calibrate
cortex calibrate --kernel csp --dataset data.float32 --labels labels.npy --n-components 4 --output model.cortex_state

# Validate
cortex validate --kernel csp --state model.cortex_state

# Benchmark
cortex run --kernel csp --state model.cortex_state --duration 10
```

---

## Notes

- **Flexibility**: This plan is aggressive but achievable given your demonstrated velocity
- **Scope Control**: Week 1 validation will inform Week 2 decisions - be ready to pivot
- **Communication**: Update this document with actual findings as you progress
- **Retrospective**: Day 5 reflection is critical for course-correcting Week 2

**Remember**: The goal is not just to ship features, but to **validate the integrated system** and **prove ABI v3 generalization**. If validation exposes issues, fixing them is higher priority than CSP implementation.
