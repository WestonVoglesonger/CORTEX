# Using Device Adapters - User Guide

**Audience:** CORTEX users running benchmarks across different hardware platforms
**Prerequisites:** Basic CORTEX usage, YAML configuration knowledge
**Related Docs:** [Configuration Reference](../reference/configuration.md), [Adapter Catalog](../../primitives/adapters/v1/README.md)

---

## What Are Device Adapters?

Device adapters enable CORTEX to execute BCI kernels on different hardware platforms while maintaining consistent measurement methodology. Starting with v0.4.0, **ALL kernel execution routes through adapters** - there is no direct execution mode.

### Available Adapters

| Adapter | Platform | Transport | Use Case |
|---------|----------|-----------|----------|
| **x86@loopback** | Local x86/ARM | Socketpair | Default, testing, development |
| **jetson@tcp** | Jetson Nano | TCP network | Remote GPU execution (Phase 2) |
| **stm32@uart** | STM32H7 | Serial UART | Bare-metal embedded (Phase 3) |

**Current Status:** Only `x86@loopback` is available in v0.4.0. Network and embedded adapters coming in future releases.

---

## Quick Start

### 1. Build Adapters

Adapters are built automatically with `make all`:

```bash
make all
# Output includes:
# Building device adapters...
#   Building x86@loopback adapter...
# ✓ cortex_adapter_x86_loopback (35KB)
```

### 2. Verify Adapter Binary

```bash
ls -lh primitives/adapters/v1/x86@loopback/cortex_adapter_x86_loopback
# -rwxr-xr-x 1 user staff 35K Dec 29 12:51 cortex_adapter_x86_loopback
```

### 3. Run Benchmarks

```bash
# Use default config (auto-detects all kernels)
cortex pipeline

# Or specify config explicitly
cortex run primitives/configs/cortex.yaml
```

**That's it!** The harness automatically uses adapters. No additional configuration needed for default usage.

---

## Configuration

### Minimal Config (Auto-Detection Mode)

When the `plugins:` section is **omitted**, CORTEX auto-detects all built kernels:

```yaml
cortex_version: 1
dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  channels: 64
  sample_rate_hz: 160

# No plugins section - auto-detect all kernels and use default adapter
```

In auto-detect mode:
- All kernels in `primitives/kernels/v*/` are discovered
- Default adapter `x86@loopback` is used automatically
- Kernels run sequentially in alphabetical order

### Explicit Config (Specifying Adapter)

For precise control, explicitly list kernels and adapter:

```yaml
cortex_version: 1
dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  channels: 64
  sample_rate_hz: 160

plugins:
  - name: "noop"
    status: ready
    spec_uri: "primitives/kernels/v1/noop@f32"
    adapter_path: "primitives/adapters/v1/x86@loopback/cortex_adapter_x86_loopback"

  - name: "car"
    status: ready
    spec_uri: "primitives/kernels/v1/car@f32"
    adapter_path: "primitives/adapters/v1/x86@loopback/cortex_adapter_x86_loopback"
```

**Required fields:**
- `spec_uri`: Full path to kernel primitive
- `adapter_path`: Full path to adapter binary

---

## Running with Different Adapters

### Local Execution (x86@loopback)

Default adapter for local benchmarking:

```yaml
plugins:
  - name: "bandpass_fir"
    spec_uri: "primitives/kernels/v1/bandpass_fir@f32"
    adapter_path: "primitives/adapters/v1/x86@loopback/cortex_adapter_x86_loopback"
```

**Characteristics:**
- ✅ Fastest (socketpair IPC, ~1µs overhead)
- ✅ No network latency
- ✅ Easy debugging (same machine)
- ❌ Can't test remote hardware

### Remote Execution (jetson@tcp) - Phase 2

Network-based execution for Jetson Nano GPU testing:

```yaml
plugins:
  - name: "welch_psd"
    spec_uri: "primitives/kernels/v1/welch_psd@f32"
    adapter_path: "primitives/adapters/v1/jetson@tcp/cortex_adapter_jetson_tcp"
    params:
      host: "192.168.1.100"
      port: 9000
```

**Characteristics:**
- ✅ Tests on actual target hardware
- ✅ Measures real-world network latency
- ❌ Requires network connection
- ❌ Slower than local (TCP overhead)

### Embedded Execution (stm32@uart) - Phase 3

Serial connection to bare-metal microcontroller:

```yaml
plugins:
  - name: "notch_iir"
    spec_uri: "primitives/kernels/v1/notch_iir@f32"
    adapter_path: "primitives/adapters/v1/stm32@uart/cortex_adapter_stm32_uart"
    params:
      device: "/dev/ttyUSB0"
      baud: 921600
```

**Characteristics:**
- ✅ Real embedded performance measurement
- ✅ Validates firmware builds
- ❌ Requires physical hardware
- ❌ Slowest (UART bandwidth limits)

---

## Kernel-Specific Configuration

### Parameterized Kernels

Some kernels accept runtime parameters:

```yaml
plugins:
  - name: "notch_iir"
    spec_uri: "primitives/kernels/v1/notch_iir@f32"
    adapter_path: "primitives/adapters/v1/x86@loopback/cortex_adapter_x86_loopback"
    params:
      f0_hz: 60.0     # Notch frequency (Hz)
      Q: 30.0         # Quality factor

  - name: "goertzel"
    spec_uri: "primitives/kernels/v1/goertzel@f32"
    adapter_path: "primitives/adapters/v1/x86@loopback/cortex_adapter_x86_loopback"
    params:
      alpha_low: 8.0
      alpha_high: 13.0
      beta_low: 13.0
      beta_high: 30.0
```

See each kernel's README for available parameters.

### Trainable Kernels (ABI v3)

Trainable kernels (ICA, CSP, LDA) require calibration before execution:

**Step 1: Calibrate kernel offline**
```bash
cortex calibrate \
  --kernel ica \
  --data primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
  --output ica_S001.cortex_state
```

**Step 2: Run with calibration state**
```yaml
plugins:
  - name: "ica"
    spec_uri: "primitives/kernels/v1/ica@f32"
    adapter_path: "primitives/adapters/v1/x86@loopback/cortex_adapter_x86_loopback"
    calibration_state: "ica_S001.cortex_state"
```

The adapter automatically loads and transfers the calibration state to the kernel.

---

## Understanding Telemetry Output

Device adapters report detailed timing information in telemetry:

### Telemetry Fields

```json
{
  "plugin": "noop",
  "window_index": 0,
  "start_ts_ns": 54101856358000,
  "end_ts_ns": 54101868461000,

  "adapter_name": "x86@loopback",
  "device_tin_ns": 54101864289000,
  "device_tstart_ns": 54101864290000,
  "device_tend_ns": 54101864338000,
  "device_tfirst_tx_ns": 72340175277511248,
  "device_tlast_tx_ns": 72340175277511248
}
```

### Timing Breakdown

| Field | Meaning | Use Case |
|-------|---------|----------|
| `start_ts_ns` | Harness started send | Overall latency measurement |
| `device_tin_ns` | Adapter received data | Network latency (end recv) |
| `device_tstart_ns` | Kernel execution started | Kernel-only latency start |
| `device_tend_ns` | Kernel execution finished | Kernel-only latency end |
| `device_tfirst_tx_ns` | Started sending result | Network latency (start send) |
| `device_tlast_tx_ns` | Finished sending result | Network latency (end send) |
| `end_ts_ns` | Harness received result | Overall latency measurement |

### Derived Metrics

```python
# Kernel execution time (pure computation)
kernel_latency = device_tend_ns - device_tstart_ns

# Adapter overhead (IPC, serialization, deserialization)
adapter_overhead = (device_tin_ns - start_ts_ns) + (end_ts_ns - device_tlast_tx_ns)

# Total latency (end-to-end)
total_latency = end_ts_ns - start_ts_ns
```

---

## Environment Variables

Override runtime behavior via environment variables:

### Kernel Filtering

```bash
# Run only noop kernel
CORTEX_KERNEL_FILTER=noop cortex run primitives/configs/cortex.yaml

# Run multiple kernels (regex)
CORTEX_KERNEL_FILTER="car|noop" cortex run primitives/configs/cortex.yaml
```

### Benchmark Duration

```bash
# Short test run
CORTEX_DURATION_OVERRIDE=1 CORTEX_REPEATS_OVERRIDE=1 CORTEX_WARMUP_OVERRIDE=0 \
  cortex run primitives/configs/cortex.yaml
```

### Output Directory

```bash
# Custom output location
CORTEX_OUTPUT_DIR=/tmp/my_results cortex run primitives/configs/cortex.yaml
```

---

## Troubleshooting

### "Adapter binary not found"

**Error:**
```
[harness] failed to spawn adapter for 'noop': adapter binary not found
```

**Solution:**
```bash
# Rebuild adapters
make -C primitives/adapters/v1/x86@loopback/

# Verify binary exists
ls primitives/adapters/v1/x86@loopback/cortex_adapter_x86_loopback

# Check permissions
chmod +x primitives/adapters/v1/x86@loopback/cortex_adapter_x86_loopback
```

### "Kernel library not found"

**Error:**
```
[adapter] Failed to load kernel: dlopen() error
```

**Solution:**
```bash
# Build missing kernel
make -C primitives/kernels/v1/noop@f32/

# Verify shared library exists
ls primitives/kernels/v1/noop@f32/libnoop.{dylib,so}
```

### Adapter Process Hangs

**Symptom:** Benchmark never completes, adapter process visible in `ps`

**Diagnosis:**
```bash
# Check adapter stderr
tail -f /tmp/cortex_adapter_*.log

# Kill hanging adapter
pkill cortex_adapter
```

**Common causes:**
1. Infinite loop in kernel `cortex_process()`
2. Missing timeout in adapter recv() calls
3. Deadlock in IPC mechanism

**Prevention:**
- Use `CORTEX_DURATION_OVERRIDE=1` for testing
- Monitor adapter stderr output
- Ensure kernels have bounded execution time

### High Latency Values

**Symptom:** `latency_ns` shows milliseconds instead of microseconds

**Diagnosis:**
```bash
# Check which adapter is running
grep adapter_name results/run-*/kernel-data/*/telemetry.ndjson
```

**Expected latencies (x86@loopback):**
- noop: ~1-10 µs
- car: ~20-100 µs
- notch_iir: ~50-200 µs
- bandpass_fir: ~2-5 ms
- goertzel: ~100-500 µs
- welch_psd: ~500-2000 µs

**If latencies 100× higher:** Check CPU frequency scaling (see [Configuration Guide](../reference/configuration.md#background-load-profiles))

### Memory Leaks

**Detection:**
```bash
# Run under Valgrind (slow but thorough)
valgrind --leak-check=full \
  env CORTEX_DURATION_OVERRIDE=1 CORTEX_REPEATS_OVERRIDE=1 \
  cortex run primitives/configs/cortex.yaml
```

**Expected output:**
```
==12345== All heap blocks were freed -- no leaks are possible
```

---

## Performance Tuning

### CPU Frequency Scaling

**macOS:**
```yaml
benchmark:
  load_profile: "medium"  # Locks CPU frequency
```

**Linux:**
```bash
# Set performance governor
sudo cpupower frequency-set --governor performance

# Then use idle load profile
benchmark:
  load_profile: "idle"
```

### Real-Time Scheduling (Linux Only)

```yaml
realtime:
  scheduler: "fifo"
  priority: 80
  cpu_affinity: [0, 1]
```

**Requires:** `sudo` or `CAP_SYS_NICE` capability

**Effect:** Reduces jitter, improves worst-case latency

### Dataset Size

For quick tests, use smaller datasets:

```yaml
dataset:
  path: "primitives/datasets/v1/fake/synthetic.float32"  # Smaller
  channels: 32  # Fewer channels = faster
```

---

## Best Practices

### ✅ DO

1. **Use auto-detection for comprehensive benchmarks**
   ```yaml
   # No plugins section - runs all kernels
   cortex_version: 1
   dataset: { ... }
   ```

2. **Test with noop kernel first**
   ```bash
   CORTEX_KERNEL_FILTER=noop cortex run config.yaml
   ```
   Verifies adapter works before testing complex kernels.

3. **Use medium load profile on macOS**
   ```yaml
   benchmark:
     load_profile: "medium"
   ```
   Prevents frequency scaling artifacts.

4. **Commit calibration state files**
   ```bash
   git add ica_S001.cortex_state
   ```
   Ensures trainable kernels are reproducible.

5. **Check telemetry for anomalies**
   ```bash
   # Look for deadline misses
   jq 'select(.deadline_missed == 1)' results/run-*/telemetry.ndjson
   ```

### ❌ DON'T

1. **Don't bypass adapters** - There is no direct execution mode in v0.4.0+

2. **Don't ignore adapter stderr**
   ```bash
   # WRONG: Redirects stderr to /dev/null
   cortex run config.yaml 2>/dev/null
   ```

3. **Don't use idle profile on macOS**
   ```yaml
   # WRONG: Causes 2.3× latency increase
   benchmark:
     load_profile: "idle"
   ```

4. **Don't run kernels in parallel**
   CORTEX enforces sequential execution for measurement isolation.

5. **Don't modify adapter binaries manually**
   Always rebuild with `make`:
   ```bash
   make -C primitives/adapters/v1/x86@loopback/ clean all
   ```

---

## Examples

### Example 1: Quick Smoke Test

```bash
# Test single kernel, 1 second, 1 repeat
CORTEX_KERNEL_FILTER=noop \
CORTEX_DURATION_OVERRIDE=1 \
CORTEX_REPEATS_OVERRIDE=1 \
CORTEX_WARMUP_OVERRIDE=0 \
  cortex run primitives/configs/cortex.yaml
```

### Example 2: Comprehensive Benchmark

```yaml
# config.yaml
cortex_version: 1
dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  channels: 64
  sample_rate_hz: 160

benchmark:
  parameters:
    duration_seconds: 120
    repeats: 5
    warmup_seconds: 10
  load_profile: "medium"

# Auto-detect all kernels
```

```bash
cortex pipeline --config config.yaml
```

### Example 3: Trainable Kernel Workflow

```bash
# Step 1: Calibrate
cortex calibrate \
  --kernel ica \
  --data primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32 \
  --output ica_S001.cortex_state

# Step 2: Create config
cat > ica_benchmark.yaml <<EOF
cortex_version: 1
dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  channels: 64
  sample_rate_hz: 160

plugins:
  - name: "ica"
    spec_uri: "primitives/kernels/v1/ica@f32"
    adapter_path: "primitives/adapters/v1/x86@loopback/cortex_adapter_x86_loopback"
    calibration_state: "ica_S001.cortex_state"
EOF

# Step 3: Run benchmark
cortex run ica_benchmark.yaml
```

---

## Advanced: Custom Adapter Paths

For testing custom adapters during development:

```yaml
plugins:
  - name: "noop"
    spec_uri: "primitives/kernels/v1/noop@f32"
    adapter_path: "/Users/myname/dev/my_custom_adapter/cortex_adapter_custom"
```

**Note:** Use absolute paths for adapters outside the CORTEX tree.

---

## Next Steps

- **Explore adapter internals:** [Adapter Protocol Spec](../reference/adapter-protocol.md)
- **Implement custom adapter:** [Adding Adapters Tutorial](adding-adapters.md)
- **View adapter catalog:** [Available Adapters](../../primitives/adapters/v1/README.md)
- **Understand telemetry:** [Telemetry Reference](../reference/telemetry.md)

---

## FAQ

**Q: Can I still run kernels without adapters?**
A: No. Starting with v0.4.0, ALL execution routes through adapters. This ensures consistent telemetry and enables future HIL testing.

**Q: Which adapter should I use?**
A: Use `x86@loopback` for local benchmarking (current default). Future releases will add network and embedded adapters.

**Q: Do adapters affect benchmark results?**
A: Yes, but minimally. x86@loopback adds ~1-2µs overhead (measured in `experiments/noop-overhead-2025-12-05/`). Device timing fields let you factor out adapter overhead.

**Q: Can I run multiple kernels simultaneously?**
A: No. CORTEX enforces sequential execution for measurement isolation. Running kernels in parallel would cause CPU contention and invalidate results.

**Q: How do I debug adapter issues?**
A: Adapter stderr is captured by harness. Check terminal output or use:
```bash
cortex run config.yaml 2>&1 | grep "\[adapter\]"
```

---

## Getting Help

- **Documentation:** [`docs/`](../)
- **Troubleshooting Guide:** [`docs/guides/troubleshooting.md`](troubleshooting.md)
- **GitHub Issues:** https://github.com/WestonVoglesonger/CORTEX/issues
- **Example Configs:** `primitives/configs/`
