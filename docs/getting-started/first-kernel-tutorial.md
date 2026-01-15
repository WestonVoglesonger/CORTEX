# Building Your First Custom Kernel

A hands-on tutorial that takes you from zero to a working signal processing kernel in under 2 hours.

---

## What You'll Build

You'll implement a **Simple Moving Average (SMA)** filter - a basic but essential signal processing operation that smooths noisy data by averaging recent samples. This tutorial will teach you the core concepts you need to build any CORTEX kernel.

**Why SMA?**
- Everyone understands the concept (average of last N samples)
- Shows stateful processing (maintains sample history)
- Shows parameter handling (window size configuration)
- Actually useful for smoothing noisy EEG signals
- Teaches patterns you'll use for complex kernels

**What you'll learn:**
- The three required kernel functions (`init`, `process`, `teardown`)
- How to manage state across processing windows
- How to handle runtime parameters
- How to think about real-time constraints

---

## Prerequisites

- Completed the [Quick Start Guide](quickstart.md) (you can build and run CORTEX)
- Basic C programming (pointers, structs, memory management)
- ~1-2 hours of focused time

---

## Part 1: Understanding the Kernel ABI

Every CORTEX kernel is a shared library (`.so` on Linux, `.dylib` on macOS) that exports exactly three functions:

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t* config);
void cortex_process(void* handle, const void* input, void* output);
void cortex_teardown(void* handle);
```

### The Lifecycle

```
┌─────────────────────────────────────────────────────┐
│ HARNESS                                             │
│                                                     │
│  1. cortex_init(config)                            │
│     ├─ Allocate state                              │
│     ├─ Parse parameters                            │
│     ├─ Initialize algorithm                        │
│     └─ Return handle + output dimensions           │
│                                                     │
│  2. cortex_process(handle, input, output) ← Loop   │
│     ├─ Read state from handle                      │
│     ├─ Process one window of data                  │
│     └─ Write output                                │
│                                                     │
│  3. cortex_teardown(handle)                        │
│     └─ Free all allocated memory                   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Key insight**: `init()` runs once, `process()` runs thousands of times, `teardown()` runs once. This means:
- Expensive setup belongs in `init()` (memory allocation, coefficient computation)
- `process()` must be fast and deterministic (no malloc, no I/O)
- State persists between `process()` calls via the opaque `handle`

---

## Part 2: The Algorithm

A simple moving average with window size N computes:

```
y[t] = (x[t] + x[t-1] + x[t-2] + ... + x[t-N+1]) / N
```

For each channel independently. With 64 EEG channels, we maintain 64 separate averaging windows.

**Challenge**: CORTEX processes data in windows (e.g., 160 samples at a time), but our averaging window might be only 3-5 samples. We need to maintain history across windows.

**Solution**: Circular buffer that persists in the `handle` state.

---

## Part 3: Implementation

### Step 1: Create Directory Structure

```bash
cd primitives/kernels/v1/
mkdir -p sma@f32
cd sma@f32
```

### Step 2: Write the Kernel (`sma.c`)

Create `sma.c` with the following implementation:

```c
/**
 * @file sma.c
 * @brief Simple Moving Average (SMA) filter for signal smoothing
 *
 * Applies a moving average filter to each channel independently.
 * Maintains circular buffer state across windows for continuity.
 *
 * Parameters:
 *   window_size: Number of samples to average (default: 3)
 */

#include "cortex_plugin.h"
#include "cortex_params.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

// This kernel uses ABI v3 (current version)
// ABI v3 adds calibration support, but non-trainable kernels
// simply don't export cortex_calibrate()
// Note: CORTEX_ABI_VERSION is already defined in cortex_plugin.h as 3u

#define DEFAULT_WINDOW_SIZE 3

/**
 * State structure for SMA filter
 *
 * We maintain a circular buffer of past samples for each channel.
 * This allows us to compute the moving average efficiently without
 * recomputing the sum every time.
 */
typedef struct {
    uint32_t window_length;      // W: samples per processing window
    uint32_t channels;           // C: number of EEG channels
    uint32_t sma_window_size;    // N: averaging window size

    // Circular buffer: [channels][sma_window_size]
    // Stored as flat array: buffer[c * sma_window_size + i]
    float* buffer;

    // Current write position in circular buffer (per channel)
    uint32_t* buffer_pos;

    // Sum of values in buffer (for efficient incremental update)
    float* running_sum;

    // Count of valid samples in buffer (< sma_window_size during warmup)
    uint32_t* buffer_count;

} sma_state_t;

/**
 * Initialize SMA filter
 *
 * This function:
 * 1. Validates configuration
 * 2. Parses runtime parameters (window_size)
 * 3. Allocates state buffers
 * 4. Returns handle to harness
 */
cortex_init_result_t cortex_init(const cortex_plugin_config_t* config) {
    cortex_init_result_t result = {0};

    // Validate configuration (standard ABI v3 checks)
    if (!config) return result;
    if (config->abi_version != CORTEX_ABI_VERSION) return result;  // Must be v3
    if (config->struct_size < sizeof(cortex_plugin_config_t)) return result;
    if (config->dtype != CORTEX_DTYPE_FLOAT32) return result;

    // Allocate state struct
    sma_state_t* state = (sma_state_t*)calloc(1, sizeof(sma_state_t));
    if (!state) return result;

    state->window_length = config->window_length_samples;
    state->channels = config->channels;

    // Parse runtime parameters
    // Format: "window_size=5" or empty string for defaults
    state->sma_window_size = DEFAULT_WINDOW_SIZE;
    if (config->kernel_params && config->kernel_params[0] != '\0') {
        int window_size = cortex_param_int(config->kernel_params, "window_size", DEFAULT_WINDOW_SIZE);
        if (window_size > 0 && window_size <= 100) {
            state->sma_window_size = (uint32_t)window_size;
        }
    }

    // Allocate circular buffers (one per channel)
    const size_t buffer_size = state->channels * state->sma_window_size;
    state->buffer = (float*)calloc(buffer_size, sizeof(float));
    state->buffer_pos = (uint32_t*)calloc(state->channels, sizeof(uint32_t));
    state->running_sum = (float*)calloc(state->channels, sizeof(float));
    state->buffer_count = (uint32_t*)calloc(state->channels, sizeof(uint32_t));

    if (!state->buffer || !state->buffer_pos || !state->running_sum || !state->buffer_count) {
        // Allocation failed - cleanup and return null handle
        free(state->buffer);
        free(state->buffer_pos);
        free(state->running_sum);
        free(state->buffer_count);
        free(state);
        return result;
    }

    // Return successful initialization
    // Output dimensions = input dimensions (SMA preserves shape)
    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;

    return result;
}

/**
 * Process one window of data
 *
 * For each sample in the window:
 * 1. Add new sample to circular buffer
 * 2. Update running sum
 * 3. Compute average
 * 4. Write to output
 *
 * Note: This is called repeatedly (thousands of times per benchmark).
 * Must be fast and deterministic (no malloc, no I/O).
 */
void cortex_process(void* handle, const void* input, void* output) {
    if (!handle || !input || !output) return;

    const sma_state_t* state = (const sma_state_t*)handle;
    const float* in = (const float*)input;
    float* out = (float*)output;

    const uint32_t W = state->window_length;
    const uint32_t C = state->channels;
    const uint32_t N = state->sma_window_size;

    // Data layout: time-major, interleaved channels
    // in[t*C + c] = sample at time t, channel c

    for (uint32_t t = 0; t < W; t++) {
        for (uint32_t c = 0; c < C; c++) {
            const float new_sample = in[t * C + c];

            // Get pointers for this channel's state
            float* circ_buf = state->buffer + (c * N);
            uint32_t pos = state->buffer_pos[c];
            uint32_t count = state->buffer_count[c];
            float sum = state->running_sum[c];

            // Remove old value from sum (if buffer is full)
            if (count == N) {
                sum -= circ_buf[pos];
            }

            // Add new value to circular buffer and sum
            circ_buf[pos] = new_sample;
            sum += new_sample;

            // Update position and count
            pos = (pos + 1) % N;
            if (count < N) count++;

            // Compute average
            out[t * C + c] = sum / (float)count;

            // Write back mutable state (non-const access)
            // Note: This violates const correctness but is necessary
            // for maintaining state. Better design would split state
            // into const config and mutable runtime state.
            ((sma_state_t*)state)->buffer_pos[c] = pos;
            ((sma_state_t*)state)->buffer_count[c] = count;
            ((sma_state_t*)state)->running_sum[c] = sum;
        }
    }
}

/**
 * Cleanup and free all allocated memory
 *
 * Called once when benchmark completes or harness shuts down.
 */
void cortex_teardown(void* handle) {
    if (!handle) return;

    sma_state_t* state = (sma_state_t*)handle;

    free(state->buffer);
    free(state->buffer_pos);
    free(state->running_sum);
    free(state->buffer_count);
    free(state);
}
```

### Step 3: Create Makefile

Create `Makefile`:

```makefile
# Simple Moving Average kernel Makefile
SDK_INCLUDE := ../../../../sdk/kernel/include
SDK_LIB := ../../../../sdk/kernel/lib

CC := gcc
CFLAGS := -Wall -Wextra -O3 -fPIC -I$(SDK_INCLUDE)

# Platform detection
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LIBEXT := dylib
    LDFLAGS := -dynamiclib
else
    LIBEXT := so
    LDFLAGS := -shared
endif

TARGET := libsma.$(LIBEXT)
SDK_OBJS := $(SDK_LIB)/params/cortex_params.o
LOCAL_OBJS := sma.o

all: $(TARGET)

$(TARGET): $(LOCAL_OBJS) $(SDK_OBJS)
	$(CC) $(LDFLAGS) -o $@ $^

sma.o: sma.c
	$(CC) $(CFLAGS) -c $<

clean:
	rm -f $(TARGET) $(LOCAL_OBJS)

.PHONY: all clean
```

### Step 4: Create Kernel Specification

Create `spec.yaml`:

```yaml
kernel:
  name: "sma"
  version: "v1"
  dtype: "float32"
  description: "Simple moving average filter for signal smoothing"

abi:
  input_shape:
    window_length: 160  # From config
    channels: 64        # From config
  output_shape:
    window_length: 160  # Preserved
    channels: 64        # Preserved
  stateful: true        # Maintains circular buffer state

parameters:
  - name: "window_size"
    type: "int"
    default: 3
    range: [1, 100]
    description: "Number of samples to average (higher = smoother but more lag)"

numerical:
  tolerance:
    rtol: 1.0e-5
    atol: 1.0e-6
```

### Step 5: Build Your Kernel

```bash
# Build the kernel
make clean && make

# Verify it compiled
ls -lh libsma.dylib   # macOS
ls -lh libsma.so      # Linux
```

**Expected output:**
```
-rwxr-xr-x  1 user  staff  15K Jan 14 19:00 libsma.dylib
```

---

## Part 4: Testing Your Kernel

### Quick Validation Test

Create a minimal test program to verify the algorithm works:

```c
// test_sma.c
#include "cortex_plugin.h"
#include <stdio.h>
#include <stdlib.h>

int main() {
    // Simulate config (use ABI v3)
    cortex_plugin_config_t config = {
        .abi_version = 3,  // Current ABI version
        .struct_size = sizeof(cortex_plugin_config_t),
        .dtype = CORTEX_DTYPE_FLOAT32,
        .sample_rate_hz = 160,
        .window_length_samples = 5,  // Small window for testing
        .hop_samples = 5,
        .channels = 2,  // Two channels
        .kernel_params = "window_size=3",
        .calibration_state = NULL,  // Not a trainable kernel
        .calibration_state_size = 0
    };

    // Initialize kernel
    cortex_init_result_t init_result = cortex_init(&config);
    if (!init_result.handle) {
        fprintf(stderr, "Init failed\n");
        return 1;
    }

    printf("✓ Init succeeded\n");
    printf("  Output: %u samples × %u channels\n",
           init_result.output_window_length_samples,
           init_result.output_channels);

    // Test input: [1,1, 2,2, 3,3, 4,4, 5,5] (time-major, 2 channels)
    float input[10] = {1,1, 2,2, 3,3, 4,4, 5,5};
    float output[10] = {0};

    // Process window
    cortex_process(init_result.handle, input, output);

    // Expected output for window_size=3:
    // t=0: avg([1]) = 1.00        (warmup)
    // t=1: avg([1,2]) = 1.50      (warmup)
    // t=2: avg([1,2,3]) = 2.00    (full window)
    // t=3: avg([2,3,4]) = 3.00
    // t=4: avg([3,4,5]) = 4.00

    printf("✓ Process completed\n");
    printf("  Input:  [1,1, 2,2, 3,3, 4,4, 5,5]\n");
    printf("  Output: [");
    for (int i = 0; i < 10; i++) {
        printf("%.2f", output[i]);
        if (i < 9) printf(", ");
    }
    printf("]\n");

    // Cleanup
    cortex_teardown(init_result.handle);
    printf("✓ Teardown completed\n");

    return 0;
}
```

Compile and run:

```bash
gcc -I../../../../sdk/kernel/include test_sma.c libsma.dylib -o test_sma
./test_sma
```

**Expected output:**
```
✓ Init succeeded
  Output: 5 samples × 2 channels
✓ Process completed
  Input:  [1,1, 2,2, 3,3, 4,4, 5,5]
  Output: [1.00, 1.00, 1.50, 1.50, 2.00, 2.00, 3.00, 3.00, 4.00, 4.00]
✓ Teardown completed
```

---

## Part 5: Integration with CORTEX

To use your kernel in benchmarks, you need to:

1. **Add to kernel registry** (so `make all` builds it)
2. **Create README.md** (documentation)
3. **Create oracle.py** (Python reference for validation)

For now, you can manually test it:

```bash
# Create a test config that uses your kernel
cat > /tmp/test-sma.yaml <<EOF
dataset:
  path: "primitives/datasets/v1/synthetic/pink_noise.float32"

kernels:
  - name: "sma"
    adapter_path: "primitives/adapters/v1/native/cortex_adapter_native"
    spec_uri: "primitives/kernels/v1/sma@f32/libsma.dylib"
    params: "window_size=5"

execution:
  duration_seconds: 5
  warmup_seconds: 1
  repeats: 1
EOF

# Run benchmark (assuming harness supports custom configs)
cortex run /tmp/test-sma.yaml
```

---

## Part 6: What You've Learned

Congratulations! You've built a complete CORTEX kernel. Let's review the key concepts:

### 1. The Three-Function Contract

Every kernel exports:
- `cortex_init()` - Setup (runs once)
- `cortex_process()` - Processing (runs thousands of times)
- `cortex_teardown()` - Cleanup (runs once)

### 2. State Management

- State is allocated in `init()` and freed in `teardown()`
- `process()` receives state via opaque `handle` pointer
- State persists across `process()` calls
- Use circular buffers for sample history

### 3. Performance Constraints

- NO heap allocation in `process()` (pre-allocate in `init()`)
- NO file I/O or syscalls in `process()`
- NO unbounded loops in `process()`
- Deterministic execution time required

### 4. Parameter Handling

- Use `cortex_param_*()` accessor functions
- Provide sensible defaults
- Validate parameter ranges in `init()`

### 5. Data Layout

- Time-major, interleaved channels: `data[t * C + c]`
- Input: `[W × C]` samples (e.g., 160 samples × 64 channels)
- Output: Usually same shape (unless doing dimensionality reduction)

---

## Part 7: Next Steps

Now that you understand the basics, you're ready for more complex kernels:

### Immediate Next Steps

1. **Add Oracle Validation** - See [Adding New Kernels](../guides/adding-kernels.md) Section 4
2. **Write README** - Document your kernel's math and parameters
3. **Add to Registry** - Make it auto-build with `make all`

### Advanced Techniques

- **IIR/FIR Filters**: See `primitives/kernels/v1/notch_iir@f32/` for filter state management
- **Frequency Analysis**: See `primitives/kernels/v1/goertzel@f32/` for Goertzel algorithm
- **Trainable Kernels**: See `primitives/kernels/v1/ica@f32/` for calibration API

### Complete Reference

- **Full Kernel Development Guide**: [docs/guides/adding-kernels.md](../guides/adding-kernels.md)
- **ABI Specification**: [docs/reference/plugin-interface.md](../reference/plugin-interface.md)
- **Parameter Accessor API**: [sdk/kernel/lib/params/README.md](../../sdk/kernel/lib/params/README.md)

---

## Common Pitfalls

### Memory Leaks in `init()`

**Problem:**
```c
state->buffer = calloc(...);
if (!state->buffer) {
    free(state);  // ← Forgot to free other allocations!
    return result;
}
```

**Solution:**
```c
if (!state->buffer || !state->other_buffer) {
    free(state->buffer);
    free(state->other_buffer);
    free(state);
    return result;
}
```

### Mutating Const State

**Problem:**
```c
void cortex_process(void* handle, const void* input, void* output) {
    const sma_state_t* state = (const sma_state_t*)handle;
    state->buffer_pos[c]++;  // ← Compiler error: discards const qualifier
}
```

**Solution:**
Split state into const config and mutable runtime state, or cast away const with care:
```c
((sma_state_t*)state)->buffer_pos[c]++;  // Careful: only for runtime state!
```

### Integer Overflow in Buffer Indexing

**Problem:**
```c
const size_t idx = t * state->channels + c;  // Can overflow on large windows!
```

**Solution:**
```c
const size_t idx = (size_t)t * state->channels + c;  // Cast to size_t first
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `dlopen failed: undefined symbol cortex_init` | Function not exported | Check function signatures match exactly |
| Segfault in `process()` | NULL pointer dereference | Add null checks for handle/input/output |
| Memory leak reported | Missing free in `teardown()` | Free all buffers allocated in `init()` |
| Wrong output values | Circular buffer index error | Check `pos = (pos + 1) % N` logic |
| Build fails with "cortex_plugin.h not found" | Wrong include path | Verify `-I../../../../sdk/kernel/include` |

---

## Summary

You've successfully:
- ✅ Learned the CORTEX kernel ABI
- ✅ Implemented a stateful signal processing algorithm
- ✅ Managed persistent state with circular buffers
- ✅ Handled runtime parameters
- ✅ Built and tested a working kernel

**Time invested**: 1-2 hours
**Skills gained**: Foundation for building any CORTEX kernel
**What's next**: [Complete Kernel Development Guide](../guides/adding-kernels.md)

---

**Questions or issues?** See [Troubleshooting Guide](../guides/troubleshooting.md) or open a GitHub issue.
