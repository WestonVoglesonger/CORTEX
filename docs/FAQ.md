# Frequently Asked Questions (FAQ)

Quick answers to common questions about CORTEX parameters, configuration, and usage.

## Parameters & Configuration

### What are the default window parameters?

**Fixed Parameters (EEG v1)**:
- **Sampling Rate (Fs)**: 160 Hz
- **Window Length (W)**: 160 samples (1.0 second)
- **Hop (H)**: 80 samples (0.5 seconds, 50% overlap)
- **Channels (C)**: 64
- **Deadline**: H/Fs = 500 ms per window

These parameters are configured in `configs/cortex.yaml` and can be customized per benchmark.

### What is the Plugin ABI version?

**Current ABI Version**: 2

ABI v2 introduced breaking changes from v1:
- `cortex_init()` now returns `cortex_init_result_t` (includes output dimensions)
- Eliminates need for separate `cortex_get_info()` function

See [docs/reference/plugin-interface.md](reference/plugin-interface.md) for complete ABI specification.

### What data types are supported?

**Currently Supported**:
- `float32` (f32) - All v1 kernels

**Future Support** (Spring 2026):
- `q15` - 16-bit fixed-point
- `q7` - 8-bit fixed-point

### What are the kernel-specific parameters?

**Current Limitation**: All v1 kernels use hardcoded parameters (`kernel_params` not yet wired in harness):

- **notch_iir**: f0=60 Hz, Q=30
- **fir_bandpass**: numtaps=129, passband=[8,30] Hz
- **goertzel**: alpha (8-13 Hz), beta (13-30 Hz)
- **car**: No parameters (uses all channels)

### What output formats are supported?

**Telemetry Formats**:
- **NDJSON** (default) - Newline-Delimited JSON, streaming-friendly
- **CSV** - Legacy format for Excel/spreadsheets

Set in `configs/cortex.yaml`:
```yaml
output:
  format: "ndjson"  # or "csv"
```

---

## Real-Time Scheduling

### What real-time schedulers are supported?

**Linux**:
- `SCHED_FIFO` - First-in-first-out real-time scheduling
- `SCHED_RR` - Round-robin real-time scheduling
- `SCHED_OTHER` - Standard non-real-time scheduling

**macOS**:
- Real-time scheduling not supported (uses standard scheduling)
- Warning logged, benchmarks continue normally

**SCHED_DEADLINE**:
- Currently parsed from config but NOT implemented
- Planned for future enhancement

### What is the deadline enforcement model?

**Per-Window Deadline Checking**:
- Deadline calculated as: `release_time + (H / Fs)`
- For default params: `deadline = 500 ms`
- Check performed: `deadline_missed = (end_timestamp > deadline_timestamp)`
- Reported in telemetry output (`deadline_missed` field)

**NOT SCHED_DEADLINE policy** - that Linux scheduler policy is not currently implemented.

---

## Dataset

### What dataset does CORTEX use?

**PhysioNet EEG Motor Movement/Imagery Dataset**:
- **Source**: [PhysioNet](https://physionet.org/content/eegmmidb/1.0.0/)
- **License**: Open Data Commons Attribution 1.0 (ODC-By 1.0)
- **Sampling Rate**: 160 Hz
- **Channels**: 64 (10-10 montage)
- **Format**: EDF+ (converted to float32 raw)
- **Subjects Used**: S001-S010
- **Runs Used**: R03-R14 (motor/imagery tasks)

**Citation**:
```
Schalk, G., McFarland, D.J., Hinterberger, T., Birbaumer, N., Wolpaw, J.R.
BCI2000: A General-Purpose Brain-Computer Interface (BCI) System.
IEEE Transactions on Biomedical Engineering 51(6):1034-1043, 2004.
```

### What units are used for EEG data?

**Microvolts (µV)**:
- All kernels process and report values in µV
- Native EDF format physical units

---

## Build & Platform

### What are the platform-specific plugin extensions?

- **macOS**: `.dylib` (dynamic library)
- **Linux**: `.so` (shared object)

**Build flags**:
- macOS: `-dynamiclib`
- Linux: `-shared -fPIC`

Use `$(LIBEXT)` variable in Makefiles for cross-platform compatibility.

### What compilers are supported?

- **macOS**: Clang (via Xcode Command Line Tools)
- **Linux**: GCC or Clang with C11 support

**Minimum versions**:
- GCC 5.0+
- Clang 3.5+

---

## Benchmarking

### How long should benchmarks run?

**Recommendations** (see [CLI Usage Guide](getting-started/cli-usage.md#benchmark-duration-guidelines)):

- **Quick test**: 30 seconds (60 windows @ 500ms deadline)
- **Development**: 125 seconds (250 windows, ~5% error bars)
- **Publication**: 300+ seconds (600+ windows, ~3% error bars)

**Warmup**: At least 5 seconds to allow CPU frequency scaling stabilization

### Why is my latency bimodal (two peaks)?

**Common causes**:
- CPU frequency scaling (turbo boost on/off)
- Thermal throttling
- Context switches
- Cache effects

**Solutions**:
```bash
# Linux: Disable CPU frequency scaling
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Increase warmup period
./cortex.py run --all --warmup 10

# Pin to specific CPU core
# Edit configs/cortex.yaml:
realtime:
  cpu_affinity: [2]
```

### What's a "good" latency for EEG kernels?

**Expected ranges** (for W=160, C=64, Fs=160Hz):
- **CAR**: < 50 µs (simple mean subtraction)
- **Notch IIR**: 10-30 µs (biquad filter)
- **FIR Bandpass**: 30-80 µs (FIR convolution)
- **Goertzel**: 20-60 µs (bandpower extraction)

**All should be << 500 ms deadline** for real-time compliance.

---

## Validation & Testing

### What are the numerical tolerances?

**Float32 vs Oracle**:
- **Relative tolerance (rtol)**: 1e-5
- **Absolute tolerance (atol)**: 1e-6

Defined in `kernels/v1/{name}@f32/spec.yaml`

### How do I validate a kernel?

```bash
# Validate specific kernel (required - testing all at once not implemented)
./cortex.py validate --kernel notch_iir
./cortex.py validate --kernel goertzel --verbose

# Or use test binary directly
./tests/test_kernel_accuracy --kernel goertzel --windows 10 --verbose
```

---

## Common Issues

### "dylib not found" error (macOS)

```bash
# Rebuild plugin
cd kernels/v1/{name}@f32 && make clean && make

# Verify plugin exists
ls -la kernels/v1/{name}@f32/lib{name}.dylib
```

### "Permission denied" for real-time scheduling (Linux)

```bash
# Option 1: Run with sudo (not recommended)
sudo ./src/harness/cortex run configs/cortex.yaml

# Option 2: Set capabilities (better)
sudo setcap cap_sys_nice=eip ./src/harness/cortex

# Option 3: Disable real-time in config
# Edit configs/cortex.yaml:
realtime:
  scheduler: other
```

### High deadline miss rate

**Diagnosis**:
```bash
# Check system load
htop

# Run shorter test
./cortex.py run --kernel {name} --duration 10

# Check median latency
jq '.end_ts_ns - .start_ts_ns | . / 1000000' results/*/telemetry.ndjson | head
```

**Solutions**:
1. Close other applications
2. Increase deadline in config
3. Optimize kernel implementation
4. Use faster hardware

---

## Additional Help

- **Quick Start**: [docs/getting-started/quickstart.md](getting-started/quickstart.md)
- **Troubleshooting**: [docs/guides/troubleshooting.md](guides/troubleshooting.md)
- **Full Documentation**: [docs/README.md](README.md)
- **GitHub Issues**: [github.com/WestonVoglesonger/CORTEX/issues](https://github.com/WestonVoglesonger/CORTEX/issues)
