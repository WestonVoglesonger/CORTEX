# CORTEX SDK Development Tools

Standalone binaries for kernel development, validation, and offline training.

---

## Overview

The CORTEX SDK provides two essential development tools:

| Tool | Purpose | Use Case |
|------|---------|----------|
| **cortex_calibrate** | Offline kernel training | Train ICA, CSP kernels on batch data |
| **cortex_validate** | Oracle validation | Verify C kernels match Python/SciPy references |

**Key Characteristics:**
- Standalone binaries (no Python dependencies at runtime)
- ABI v3 compatible (support both v2/v3 kernels)
- Minimal dependencies (C11, pthread, libdl on Linux)
- Built from SDK library (`libcortex.a`)
- Platform-agnostic (macOS, Linux)

---

## cortex_calibrate

### Purpose

Trains trainable kernels (ICA, CSP) on batch calibration data and serializes learned parameters to `.cortex_state` files for runtime loading.

**Workflow:**
```
Calibration Dataset (.float32)
        ↓
  cortex_calibrate
  (calls kernel's cortex_calibrate())
        ↓
  Trained Model (.cortex_state)
        ↓
  Runtime Inference
  (cortex run loads state in cortex_init())
```

### Usage

```bash
cortex_calibrate --plugin <spec_uri> \
                 --dataset <path> \
                 --windows <N> \
                 --output <state_file> \
                 [options]
```

**Required Arguments:**
- `--plugin PATH` - Plugin spec URI (e.g., `primitives/kernels/v1/ica@f32`)
- `--dataset PATH` - Calibration dataset (`.float32` binary file)
- `--windows N` - Number of windows to use for training
- `--output PATH` - Output `.cortex_state` file path

**Optional Arguments:**
- `--channels N` - Number of channels (default: 64)
- `--window-length N` - Window length in samples (default: 160)
- `--sample-rate N` - Sample rate in Hz (default: 160)
- `--verbose` - Show verbose output
- `--help` - Display help message

### Examples

**Train ICA kernel on subject S001:**
```bash
sdk/kernel/tools/cortex_calibrate \
  --plugin primitives/kernels/v1/ica@f32 \
  --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
  --windows 500 \
  --output ica_S001.cortex_state \
  --verbose
```

**Train CSP kernel with custom parameters:**
```bash
sdk/kernel/tools/cortex_calibrate \
  --plugin primitives/kernels/v1/csp@f32 \
  --dataset my_dataset.float32 \
  --windows 1000 \
  --channels 32 \
  --window-length 256 \
  --sample-rate 256 \
  --output csp_session1.cortex_state
```

**Quick calibration for testing (10 windows):**
```bash
sdk/kernel/tools/cortex_calibrate \
  --plugin primitives/kernels/v1/ica@f32 \
  --dataset primitives/datasets/v1/fake/synthetic.float32 \
  --windows 10 \
  --output ica_test.cortex_state
```

### Output Format

**Success:**
```
[calibrate] CORTEX Calibration Harness (ABI v3)
[calibrate] Plugin:   primitives/kernels/v1/ica@f32
[calibrate] Dataset:  S001R03.float32
[calibrate] Windows:  500
[calibrate] Output:   ica_S001.cortex_state
[calibrate] Config:   C=64, W=160, Fs=160 Hz
[calibrate] Loading plugin...
[calibrate] Loading dataset (12800000 samples)...
[calibrate] Calling cortex_calibrate()...
[calibrate] Training complete (elapsed: 23.4s)
[calibrate] State saved to ica_S001.cortex_state (33792 bytes)
```

**Failure (plugin doesn't support calibration):**
```
[calibrate] Error: Plugin does not export cortex_calibrate() function
[calibrate] This kernel is not trainable (stateless or stateful only)
```

### Integration with Python CLI

The `cortex calibrate` Python command wraps this binary:

```bash
# These are equivalent:
cortex calibrate --kernel ica --dataset S001R03.float32 --windows 500

sdk/kernel/tools/cortex_calibrate \
  --plugin primitives/kernels/v1/ica@f32 \
  --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
  --windows 500 \
  --output ica_S001.cortex_state
```

**Python wrapper advantages:**
- Automatic plugin spec resolution (`--kernel ica` → `primitives/kernels/v1/ica@f32`)
- Default dataset path handling
- Output path auto-generation (kernel + subject naming)

**Direct binary advantages:**
- No Python dependency
- Custom dataset paths
- Scriptable (shell scripts, CI pipelines)
- Easier debugging (LLDB/GDB)

---

## cortex_validate

### Purpose

Validates C kernel implementations against Python/SciPy reference implementations (oracles) to ensure numerical correctness before benchmarking.

**Critical Rule:** NEVER benchmark a kernel without oracle validation passing. Incorrect kernels produce meaningless performance data.

**Workflow:**
```
EEG Dataset (.float32)
        ↓
    ┌───────┴────────┐
    ↓                ↓
C Kernel        Python Oracle
(cortex_process)   (scipy/numpy)
    ↓                ↓
  Output A       Output B
    └───────┬────────┘
            ↓
    Element-wise Comparison
    (rtol=1e-5, atol=1e-6)
            ↓
        PASS / FAIL
```

### Usage

```bash
cortex_validate [--kernel <name>] [options]
```

**Optional Arguments:**
- `--kernel NAME` - Test specific kernel (e.g., `car`, `notch_iir`)
- `--data PATH` - Custom dataset path (default: PhysioNet S001R03)
- `--state PATH` - Calibration state for trainable kernels
- `--windows N` - Number of windows to test (default: 10)
- `--verbose` - Show detailed output
- `--help` - Display help message

**Behavior:**
- No `--kernel`: Tests ALL kernels in `primitives/kernels/v1/`
- With `--kernel`: Tests only specified kernel

### Examples

**Validate all kernels:**
```bash
sdk/kernel/tools/cortex_validate
```
Output:
```
[validate] Testing car...            PASS (10 windows, max_error=1.2e-7)
[validate] Testing notch_iir...      PASS (10 windows, max_error=3.4e-7)
[validate] Testing bandpass_fir...   PASS (10 windows, max_error=2.1e-7)
[validate] Testing goertzel...       PASS (10 windows, max_error=5.6e-8)
[validate] Testing welch_psd...      PASS (10 windows, max_error=8.9e-7)
[validate] Testing noop...           PASS (10 windows, max_error=0.0e+0)

Summary: 8/8 kernels passed
```

**Validate specific kernel with verbose output:**
```bash
sdk/kernel/tools/cortex_validate --kernel car --verbose
```
Output:
```
[validate] Kernel: car
[validate] Dataset: S001R03.float32 (64 ch, 80000 samples)
[validate] Testing 10 windows...

Window 0:
  C output:      [-0.0234, 0.0156, -0.0089, ...]
  Python output: [-0.0234, 0.0156, -0.0089, ...]
  Max abs error: 1.2e-7
  Max rel error: 3.4e-6
  Status: PASS

Window 1:
  ...

Summary: PASS (10/10 windows, max_error=1.2e-7)
```

**Validate trainable kernel with calibration state:**
```bash
sdk/kernel/tools/cortex_validate \
  --kernel ica \
  --state ica_S001.cortex_state \
  --windows 50 \
  --verbose
```

**Validate with custom dataset:**
```bash
sdk/kernel/tools/cortex_validate \
  --kernel bandpass_fir \
  --data my_eeg_recording.float32 \
  --windows 100
```

### Tolerance Specification

**Comparison criteria:**
```c
// Relative tolerance: 1e-5 (0.001%)
// Absolute tolerance: 1e-6

for each element:
    abs_error = |c_output - py_output|
    rel_error = abs_error / max(|py_output|, 1e-9)

    if (abs_error <= atol || rel_error <= rtol):
        PASS
    else:
        FAIL
```

**Why these tolerances?**
- **f32 precision**: ~7 decimal digits, 1e-5 rtol leaves safety margin
- **IIR filter accumulation**: Small errors compound over time
- **FFT numerical stability**: Welch PSD has minor phase variations

### Output Interpretation

**PASS:**
```
[validate] Testing notch_iir... PASS (10 windows, max_error=3.4e-7)
```
- All elements within tolerance
- Kernel ready for benchmarking
- Proceed with `cortex run`

**FAIL:**
```
[validate] Testing custom_kernel... FAIL (window 3/10)
[validate] Mismatch at element 128: C=0.0234, Python=0.0189, error=2.4e-3
[validate] Max error exceeds tolerance (rtol=1e-5)
```
- Kernel implementation incorrect
- DO NOT benchmark (meaningless results)
- Debug algorithm implementation

**Oracle not found:**
```
[validate] Testing custom_kernel... SKIP (no oracle implementation)
```
- Python reference missing in `src/cortex/oracles/`
- Create oracle before validation

### Integration with Python CLI

The `cortex validate` Python command wraps this binary:

```bash
# These are equivalent:
cortex validate

sdk/kernel/tools/cortex_validate
```

```bash
# Test specific kernel
cortex validate --kernel car

sdk/kernel/tools/cortex_validate --kernel car
```

**Python wrapper features:**
- Automatic test discovery
- HTML report generation
- CI integration (exit codes)
- Color-coded output

---

## Building the Tools

### From SDK directory

```bash
# Build both tools
cd sdk
make

# Or from project root
make sdk

# Verify build
ls -lh sdk/kernel/tools/cortex_calibrate    # ~50KB
ls -lh sdk/kernel/tools/cortex_validate     # ~35KB
```

### Manual build

```bash
cd sdk/kernel/tools

# Build calibrate
gcc -Wall -Wextra -O2 -std=c11 -I../include \
    calibrate.c -o cortex_calibrate \
    -L../lib -lcortex -lpthread -lm

# Build validate
gcc -Wall -Wextra -O2 -std=c11 -I../include \
    validate.c -o cortex_validate \
    -L../lib -lcortex -lpthread -lm

# Linux: add -ldl flag
gcc ... -L../lib -lcortex -ldl -lpthread -lm
```

### Dependencies

**Build-time:**
- C11 compiler (GCC 7+, Clang 10+)
- SDK library (`libcortex.a`)
- SDK headers (`sdk/kernel/include/`)

**Runtime:**
- POSIX threads (`pthread`)
- Math library (`libm`)
- Dynamic linker (`libdl` on Linux, built-in on macOS)
- Python 3.8+ (for oracles in cortex_validate)

---

## Workflow Integration

### Development Workflow

```bash
# 1. Implement kernel
cd primitives/kernels/v1/my_kernel@f32
# ... write my_kernel.c ...

# 2. Build kernel
make

# 3. Validate against oracle
sdk/kernel/tools/cortex_validate --kernel my_kernel --verbose

# 4. If PASS, benchmark
cortex run --kernel my_kernel

# 5. If FAIL, debug and repeat
```

### Trainable Kernel Workflow

```bash
# 1. Implement cortex_calibrate() in kernel
cd primitives/kernels/v1/ica@f32
# ... implement cortex_calibrate() ...
make

# 2. Calibrate on batch data
sdk/kernel/tools/cortex_calibrate \
  --plugin primitives/kernels/v1/ica@f32 \
  --dataset primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
  --windows 500 \
  --output ica_S001.cortex_state

# 3. Validate trained kernel
sdk/kernel/tools/cortex_validate \
  --kernel ica \
  --state ica_S001.cortex_state \
  --windows 10

# 4. Benchmark with state
cortex run --kernel ica --calibration-state ica_S001.cortex_state
```

### CI Pipeline Integration

```yaml
# .github/workflows/validate.yml
- name: Build SDK
  run: make sdk

- name: Validate all kernels
  run: sdk/kernel/tools/cortex_validate

- name: Test ICA calibration
  run: |
    sdk/kernel/tools/cortex_calibrate \
      --plugin primitives/kernels/v1/ica@f32 \
      --dataset test_data.float32 \
      --windows 10 \
      --output ica_test.cortex_state

    sdk/kernel/tools/cortex_validate \
      --kernel ica \
      --state ica_test.cortex_state
```

---

## Troubleshooting

### cortex_calibrate Issues

**Error: "Plugin does not export cortex_calibrate()"**
- **Cause:** Kernel is stateless/stateful (v2) or incomplete v3
- **Fix:** Implement `cortex_calibrate()` function in kernel
- **Check:** `nm -g libmy_kernel.dylib | grep cortex_calibrate` (should appear)

**Error: "Failed to load plugin"**
- **Cause:** Plugin library not found or wrong path
- **Fix:** Verify plugin path exists: `ls primitives/kernels/v1/ica@f32/libica.dylib`
- **macOS:** Use `.dylib`, Linux use `.so`

**Error: "calibrate() returned failure"**
- **Cause:** Training failed (convergence, invalid data, allocation)
- **Fix:** Check verbose output, verify dataset format (interleaved float32)
- **Debug:** Run under debugger: `lldb cortex_calibrate -- --plugin ...`

**Warning: "State file unusually large"**
- **Cause:** Kernel saved excessive data (full dataset instead of model)
- **Fix:** Review `cortex_state_save()` call - only save learned parameters
- **Example:** ICA should save unmixing matrix (~33KB), NOT full calibration data

### cortex_validate Issues

**Error: "Oracle not found"**
- **Cause:** No Python reference in `src/cortex/oracles/`
- **Fix:** Implement oracle before validation
- **Create:** `src/cortex/oracles/my_kernel.py` with `process(input) -> output`

**Failure: "Max error exceeds tolerance"**
- **Cause:** Algorithm mismatch between C and Python
- **Debug steps:**
  1. Verify filter coefficients match (print from both)
  2. Check intermediate values (add debug prints)
  3. Test on simple synthetic data (DC offset, pure sine)
  4. Compare element-by-element with `--verbose`
- **Common issues:**
  - Integer vs float division (`80/160` → 0 instead of 0.5)
  - Uninitialized state (missing `calloc` or `memset`)
  - Buffer indexing errors (row-major vs column-major)
  - Sign errors in IIR feedback

**Error: "Failed to load dataset"**
- **Cause:** Dataset missing or wrong format
- **Fix:** Verify file exists and is float32 binary
- **Check size:** `stat -f%z <file>` (macOS) or `stat -c%s <file>` (Linux)
- **Expected:** Multiple of `4 * channels` bytes

**Segmentation fault**
- **Cause:** Memory corruption (buffer overflow, use-after-free)
- **Debug:** Run under ASAN:
  ```bash
  # Rebuild with sanitizer
  CFLAGS="-fsanitize=address -g" make

  # Run
  sdk/kernel/tools/cortex_validate --kernel my_kernel
  ```

---

## Platform-Specific Notes

### macOS

**Plugin extension:** `.dylib`
```bash
cortex_calibrate --plugin primitives/kernels/v1/ica@f32/libica.dylib ...
```

**Debugging:**
```bash
lldb sdk/kernel/tools/cortex_calibrate -- --plugin ... --dataset ...
(lldb) run
(lldb) bt   # backtrace on crash
```

**Code signing:** Tools are not signed, may require:
```bash
xattr -d com.apple.quarantine sdk/kernel/tools/cortex_*
```

### Linux

**Plugin extension:** `.so`
```bash
cortex_calibrate --plugin primitives/kernels/v1/ica@f32/libica.so ...
```

**Library path:** Ensure `libcortex.a` linkable:
```bash
export LD_LIBRARY_PATH=$PWD/sdk/kernel/lib:$LD_LIBRARY_PATH
```

**Debugging:**
```bash
gdb --args sdk/kernel/tools/cortex_validate --kernel car
(gdb) run
(gdb) bt
```

**Permissions:** Some systems require `chmod +x`:
```bash
chmod +x sdk/kernel/tools/cortex_*
```

---

## Advanced Usage

### Custom Oracle Implementations

To validate against custom references:

**1. Create oracle in `src/cortex/oracles/my_kernel.py`:**
```python
import numpy as np

def process(input_data: np.ndarray) -> np.ndarray:
    """
    Args:
        input_data: [W, C] float32 array
    Returns:
        output_data: [W, C] float32 array
    """
    # Your reference implementation
    return output_data
```

**2. Run validation:**
```bash
sdk/kernel/tools/cortex_validate --kernel my_kernel
```

### Batch Calibration

Calibrate on multiple subjects:

```bash
for subject in S001 S002 S003; do
  sdk/kernel/tools/cortex_calibrate \
    --plugin primitives/kernels/v1/ica@f32 \
    --dataset primitives/datasets/v1/physionet-motor-imagery/converted/${subject}R03.float32 \
    --windows 500 \
    --output ica_${subject}.cortex_state
done
```

### Calibration State Inspection

States are binary files, inspect with:

```bash
# View file size
ls -lh ica_S001.cortex_state

# Hex dump header (first 64 bytes)
hexdump -C ica_S001.cortex_state | head -4

# Expected format:
# 00000000  43 4f 52 54 45 58 00 01  00 00 84 00 00 00 00 00
#           C  O  R  T  E  X [version] [size.......]
```

Load in C:
```c
void *state_data;
uint32_t state_size, state_version;
cortex_state_load("ica_S001.cortex_state", &state_data, &state_size, &state_version);
printf("Loaded %u bytes (version %u)\n", state_size, state_version);
```

---

## See Also

- **API Reference:** `sdk/kernel/include/README.md` - Plugin ABI v3 specification
- **Library Documentation:** `sdk/kernel/README.md` - SDK architecture
- **Quick Start:** `sdk/README.md` - SDK overview and examples
- **Adding Kernels:** `docs/guides/adding-kernels.md` - Kernel development tutorial
- **Trainable Kernels:** `docs/guides/migrating-to-abi-v3.md` - ABI v3 calibration workflow

---

## Quick Reference

**Validate all kernels:**
```bash
sdk/kernel/tools/cortex_validate
```

**Train ICA kernel:**
```bash
sdk/kernel/tools/cortex_calibrate \
  --plugin primitives/kernels/v1/ica@f32 \
  --dataset S001R03.float32 \
  --windows 500 \
  --output ica.cortex_state
```

**Validate trained kernel:**
```bash
sdk/kernel/tools/cortex_validate \
  --kernel ica \
  --state ica.cortex_state
```

**Build tools:**
```bash
make sdk
```
