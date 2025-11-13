# Troubleshooting Guide

Common issues when building, running, and analyzing CORTEX benchmarks.

## Table of Contents

- [Build Issues](#build-issues)
- [Plugin Loading Errors](#plugin-loading-errors)
- [Runtime Errors](#runtime-errors)
- [Performance Issues](#performance-issues)
- [Platform-Specific Issues](#platform-specific-issues)
- [Dataset Issues](#dataset-issues)
- [Analysis & CLI Issues](#analysis--cli-issues)

---

## Build Issues

### `make: command not found`

**Symptom**: `bash: make: command not found`

**Cause**: Build tools not installed

**Solution**:
```bash
# macOS
xcode-select --install

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install build-essential

# Fedora/RHEL
sudo dnf groupinstall "Development Tools"
```

---

### `gcc: command not found`

**Symptom**: `gcc: command not found` or `clang: command not found`

**Cause**: C compiler not installed

**Solution**:
```bash
# macOS (install Xcode CLT)
xcode-select --install

# Linux (install GCC)
sudo apt-get install gcc  # Ubuntu/Debian
sudo dnf install gcc      # Fedora/RHEL
```

---

### Compiler warnings about implicit declarations

**Symptom**: `warning: implicit declaration of function 'X'`

**Cause**: Missing include headers

**Solution**:
```c
// Add appropriate headers
#include <stdlib.h>  // malloc, calloc, free
#include <string.h>  // memcpy, memset
#include <math.h>    // sin, cos, sqrt, isnan
#include <stdio.h>   // printf, fprintf
```

---

### `fatal error: 'cortex_plugin.h' file not found`

**Symptom**: Kernel build fails with missing header

**Cause**: Incorrect include path in Makefile

**Solution**:
```makefile
# Ensure Makefile has correct include path
CFLAGS = -I../../../../src/engine/include  # From primitives/kernels/v1/{name}@f32/
```

---

### Link errors: `undefined reference to 'pthread_create'`

**Symptom**: Linker errors about pthread functions

**Cause**: Missing `-lpthread` flag

**Solution**:
```makefile
# Add to LDFLAGS in Makefile
LDFLAGS = -lpthread -lm
```

---

## Plugin Loading Errors

### `dlopen failed: image not found`

**Symptom**: Plugin fails to load with "image not found"

**Cause**: Plugin file doesn't exist or wrong extension

**Solution**:
```bash
# Check if plugin exists
ls -la primitives/kernels/v1/notch_iir@f32/libnotch_iir.*

# Rebuild if missing
cd primitives/kernels/v1/notch_iir@f32 && make

# Verify correct extension for platform
# macOS: .dylib
# Linux: .so
```

---

### `ABI version mismatch`

**Symptom**: `[kernel] ABI version mismatch: got X, expected Y`

**Cause**: Plugin compiled against different ABI version

**Solution**:
```bash
# Rebuild all plugins
make clean && make plugins

# Or rebuild specific plugin
cd primitives/kernels/v1/{name}@f32 && make clean && make
```

---

### `symbol not found: _cortex_init`

**Symptom**: Plugin loads but functions not found

**Cause**: Missing or incorrectly named plugin functions

**Solution**:
Ensure kernel implements exact function signatures:
```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config);
void cortex_process(void *handle, const void *input, void *output);
void cortex_teardown(void *handle);
```

---

## Runtime Errors

### `realtime scheduling not supported on this platform`

**Symptom**: Warning during execution (macOS)

**Cause**: macOS doesn't support SCHED_FIFO/SCHED_RR

**Solution**: This is expected behavior on macOS. Benchmarks will run without real-time scheduling. For true real-time testing, use Linux.

---

### `Permission denied` when setting realtime priority

**Symptom**: `setpriority failed` or similar on Linux

**Cause**: Insufficient privileges for real-time scheduling

**Solution**:
```bash
# Option 1: Run with sudo (not recommended for production)
sudo ./src/engine/harness/cortex run primitives/configs/cortex.yaml

# Option 2: Set capabilities (better)
sudo setcap cap_sys_nice=eip ./src/engine/harness/cortex

# Option 3: Disable realtime in config
# Edit primitives/configs/cortex.yaml:
realtime:
  scheduler: other  # Instead of fifo/rr
  priority: 0
```

---

### High deadline miss rate (> 5%)

**Symptom**: Many windows missing deadlines

**Cause**: System overloaded or kernel too slow

**Diagnosis**:
```bash
# Check system load
top
htop

# Run shorter duration to isolate issue
cortex run --kernel {name} --duration 10

# Check median latency in results
jq '.end_ts_ns - .start_ts_ns | . / 1000000' results/run-*/kernel-data/*/telemetry.ndjson | head -20
```

**Solutions**:
1. Close other applications
2. Disable background processes
3. Increase deadline (edit `primitives/configs/cortex.yaml: realtime.deadline_ms`)
4. Optimize kernel implementation
5. Use faster hardware

---

### Segmentation fault during benchmark

**Symptom**: `Segmentation fault (core dumped)`

**Likely causes**:
1. Buffer overflow in kernel
2. Null pointer dereference
3. Uninitialized memory access

**Debug steps**:
```bash
# Run with debugger
gdb ./src/engine/harness/cortex
(gdb) run run primitives/configs/cortex.yaml

# When it crashes:
(gdb) backtrace
(gdb) print variable_name

# Or use valgrind
valgrind --leak-check=full ./src/engine/harness/cortex run primitives/configs/cortex.yaml
```

---

## Performance Issues

### Unexpectedly high latency

**Symptom**: Kernel latency >> expected (e.g., notch IIR > 100 µs)

**Diagnosis**:
```bash
# Check if debug mode enabled
grep '\-O0' primitives/kernels/v1/{name}@f32/Makefile

# Should have optimization enabled
grep '\-O2' primitives/kernels/v1/{name}@f32/Makefile
```

**Solution**:
```makefile
# Edit Makefile, change:
CFLAGS = -Wall -Wextra -O0  # Debug
# To:
CFLAGS = -Wall -Wextra -O2  # Optimized
```

Then rebuild:
```bash
cd primitives/kernels/v1/{name}@f32 && make clean && make
```

---

### Bimodal latency distribution

**Symptom**: Two distinct peaks in latency CDF plot

**Causes**:
1. CPU frequency scaling (turbo boost)
2. Thermal throttling
3. Context switches
4. Cache effects

**Solutions**:
```bash
# Linux: Disable CPU frequency scaling
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Increase warmup period
cortex run --all --warmup 10

# Pin to specific CPU core (edit primitives/configs/cortex.yaml)
realtime:
  cpu_affinity: [2]  # Use dedicated core
```

---

## Platform-Specific Issues

### macOS: `dyld: Library not loaded`

**Symptom**: Dynamic library loading fails

**Cause**: Library path issues

**Solution**:
```bash
# Check library dependencies
otool -L primitives/kernels/v1/{name}@f32/lib{name}.dylib

# Rebuild with correct flags
cd primitives/kernels/v1/{name}@f32 && make clean && make
```

---

### Linux: `.so` file has wrong permissions

**Symptom**: `permission denied` when loading plugin

**Solution**:
```bash
# Fix permissions
chmod 755 primitives/kernels/v1/*/lib*.so

# Or rebuild
make plugins
```

---

### macOS: Clock resolution warning

**Symptom**: `clock_gettime resolution: X ns (expected < 1000 ns)`

**Cause**: macOS has microsecond (1000 ns) clock resolution vs Linux nanosecond

**Solution**: This is expected. For nanosecond precision, use Linux. macOS benchmarks are still valid, just less precise.

---

## Dataset Issues

### `dataset file not found`

**Symptom**: `Error: could not open dataset file`

**Cause**: Invalid path in config or file doesn't exist

**Solution**:
```bash
# Check configured path
grep "path:" primitives/configs/cortex.yaml

# Verify file exists
ls -lh datasets/eegmmidb/converted/S001R03.float32

# Fix path in config if needed
vim primitives/configs/cortex.yaml
```

---

### `dataset too short for duration`

**Symptom**: Benchmark ends prematurely or loops excessively

**Cause**: Dataset smaller than requested benchmark duration

**Solution**:
```bash
# Check dataset size
ls -lh datasets/eegmmidb/converted/*.float32

# Calculate duration (assuming 64ch @ 160Hz float32)
# bytes / (64 channels * 160 samples/sec * 4 bytes/float) = seconds

# Either use shorter duration:
cortex run --kernel {name} --duration 60

# Or use longer dataset file
```

---

### Wrong number of channels error

**Symptom**: `channel mismatch` or corrupted data

**Cause**: Config specifies different channel count than dataset

**Solution**:
```bash
# Check dataset metadata
cat datasets/eegmmidb/converted/*_metadata.json

# Update config to match
vim primitives/configs/cortex.yaml
# Ensure:
dataset:
  channels: 64  # Match actual dataset
```

---

## Analysis & CLI Issues

### `cortex: command not found`

**Symptom**: Shell doesn't recognize `cortex` command

**Cause**: CORTEX package not installed or virtual environment not activated

**Solution**:
```bash
# Install CORTEX in editable mode
pip install -e .

# Or activate your virtual environment first
source my_venv/bin/activate  # or venv/bin/activate
pip install -e .
```

---

### Python import errors

**Symptom**: `ModuleNotFoundError: No module named 'pandas'`

**Cause**: Python dependencies not installed

**Solution**:
```bash
# Install dependencies
pip install -e .

# Or install individually
pip install pandas numpy matplotlib seaborn pyyaml tqdm colorama
```

---

### Analysis produces empty plots

**Symptom**: Plots generated but no data shown

**Cause**: No telemetry files or wrong format

**Diagnosis**:
```bash
# Check if telemetry files exist
ls -lh results/run-*/kernel-data/*/telemetry.*

# Check NDJSON format
head -2 results/run-*/kernel-data/*/telemetry.ndjson
```

**Solution**:
```bash
# Ensure format is correct in config
grep "format:" primitives/configs/cortex.yaml
# Should be: format: "ndjson" or format: "csv"

# Rerun benchmark if needed
cortex run --all
```

---

### `jq: command not found` (when following examples)

**Symptom**: jq examples don't work

**Cause**: jq not installed (optional dependency)

**Solution**:
```bash
# macOS
brew install jq

# Ubuntu/Debian
sudo apt-get install jq

# Or use Python instead
python3 -c "import json; print(json.load(open('file.ndjson')))"
```

---

## Getting More Help

If your issue isn't listed here:

1. **Check documentation**:
   - [Quick Start Guide](../getting-started/quickstart.md)
   - [CLI Usage](../getting-started/cli-usage.md)
   - [Architecture Overview](../architecture/overview.md)
   - [Platform Compatibility](../architecture/platform-compatibility.md)

2. **Search GitHub Issues**:
   - [github.com/WestonVoglesonger/CORTEX/issues](https://github.com/WestonVoglesonger/CORTEX/issues)

3. **Enable verbose logging**:
   ```bash
   cortex validate --kernel {name} --verbose
   cortex run --kernel {name} --verbose
   ```

4. **Check system info**:
   ```bash
   # Platform
   uname -a
   
   # Compiler version
   gcc --version
   
   # Python version
   python3 --version
   
   # Disk space
   df -h .
   ```

5. **Open a GitHub Issue** with:
   - Platform (OS, architecture)
   - CORTEX version (git commit hash)
   - Steps to reproduce
   - Error message (full output)
   - Relevant config files
