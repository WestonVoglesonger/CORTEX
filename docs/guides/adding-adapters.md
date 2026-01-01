# Adding Device Adapters - Step-by-Step Tutorial

**Audience:** Developers implementing new device adapters for CORTEX
**Prerequisites:** C programming, understanding of the [adapter protocol](../reference/adapter-protocol.md)
**Estimated Time:** 4-8 hours for basic adapter
**Reference Implementation:** `primitives/adapters/v1/native/`

---

## Overview

Device adapters enable CORTEX to execute kernels on different hardware platforms (x86, ARM, embedded systems). This tutorial walks through implementing a custom adapter from scratch.

### What You'll Build

A complete device adapter that:
1. ✅ Communicates with harness via wire protocol
2. ✅ Loads and executes CORTEX kernel plugins
3. ✅ Returns telemetry data (output + timing)
4. ✅ Handles errors gracefully
5. ✅ Passes all conformance tests

### Prerequisites

Before starting, ensure you have:
- [ ] CORTEX SDK installed (`sdk/adapter/` directory)
- [ ] C11 compiler (GCC 7+ or Clang 10+)
- [ ] Understanding of wire protocol (read [`docs/reference/adapter-protocol.md`](../reference/adapter-protocol.md))
- [ ] Reference adapter built (`make -C primitives/adapters/v1/native/`)

---

## Step 1: Choose Transport Layer

Your adapter needs a transport mechanism to communicate with the harness. Choose based on your hardware:

| Transport | Use Case | SDK Implementation |
|-----------|----------|--------------------|
| **Socketpair** | Local execution (same machine) | `sdk/adapter/lib/transport/local/mock.c` |
| **TCP** | Network execution (Jetson, remote x86) | `sdk/adapter/lib/transport/network/tcp_client.c` |
| **UART** | Embedded systems (STM32, ESP32) | `sdk/adapter/lib/transport/serial/uart_posix.c` |

**For this tutorial, we'll use socketpair** (simplest to test locally).

---

## Step 2: Create Adapter Directory Structure

```bash
# Create directory following naming convention: platform@transport
mkdir -p primitives/adapters/v1/myboard@local

cd primitives/adapters/v1/myboard@local

# Create required files
touch adapter.c
touch Makefile
touch README.md
```

---

## Step 3: Write Minimal Adapter Skeleton

Create `adapter.c` with minimal protocol implementation:

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

// SDK includes
#include "cortex_wire.h"
#include "cortex_protocol.h"
#include "cortex_transport.h"

int main(void) {
    cortex_transport_t transport;
    cortex_protocol_t protocol;

    // Step 1: Initialize transport (stdin/stdout for socketpair)
    if (cortex_transport_init_stdio(&transport) != 0) {
        fprintf(stderr, "[adapter] Failed to initialize transport\n");
        return 1;
    }

    // Step 2: Initialize protocol layer
    cortex_protocol_init(&protocol, &transport);

    // Step 3: Send HELLO frame
    cortex_wire_hello_t hello = {
        .adapter_boot_id = (uint32_t)time(NULL),  // Simple boot ID
        .adapter_abi_version = 1,
        .num_kernels = 0,  // No kernels yet
        .max_window_samples = 512,
        .max_channels = 64,
    };
    strncpy(hello.adapter_name, "myboard@local", sizeof(hello.adapter_name));

    if (cortex_protocol_send_hello(&protocol, &hello, NULL) != 0) {
        fprintf(stderr, "[adapter] Failed to send HELLO\n");
        return 1;
    }

    // Step 4: Receive CONFIG frame
    cortex_wire_config_t config;
    uint8_t *calibration_state = NULL;
    if (cortex_protocol_recv_config(&protocol, &config, &calibration_state) != 0) {
        fprintf(stderr, "[adapter] Failed to receive CONFIG\n");
        return 1;
    }

    // Step 5: Send ACK
    cortex_wire_ack_t ack = {
        .session_id = config.session_id,
        .error_code = 0,
        .output_width = config.window_length_samples,
        .output_height = config.channels,
    };

    if (cortex_protocol_send_ack(&protocol, &ack) != 0) {
        fprintf(stderr, "[adapter] Failed to send ACK\n");
        return 1;
    }

    fprintf(stderr, "[adapter] Handshake complete\n");

    // TODO: Add window processing loop

    cortex_transport_teardown(&transport);
    return 0;
}
```

---

## Step 4: Add Kernel Loading

Now add dynamic kernel loading via `dlopen()`:

```c
#include <dlfcn.h>
#include "cortex_plugin.h"

// Add after handshake, before window loop:

// Load kernel plugin
void *kernel_lib = NULL;
char kernel_path[512];

// Construct path: config.plugin_name is like "primitives/kernels/v1/car@f32"
snprintf(kernel_path, sizeof(kernel_path), "%s/lib%s.dylib",
         config.plugin_name, basename(config.plugin_name));

kernel_lib = dlopen(kernel_path, RTLD_NOW);
if (!kernel_lib) {
    fprintf(stderr, "[adapter] Failed to load kernel: %s\n", dlerror());
    return 1;
}

// Resolve ABI functions
cortex_init_fn_t     cortex_init     = dlsym(kernel_lib, "cortex_init");
cortex_process_fn_t  cortex_process  = dlsym(kernel_lib, "cortex_process");
cortex_teardown_fn_t cortex_teardown = dlsym(kernel_lib, "cortex_teardown");

if (!cortex_init || !cortex_process || !cortex_teardown) {
    fprintf(stderr, "[adapter] Kernel missing required ABI functions\n");
    return 1;
}

// Initialize kernel
cortex_plugin_config_t plugin_config = {
    .abi_version = CORTEX_ABI_VERSION,
    .window_length_samples = config.window_length_samples,
    .hop_samples = config.hop_samples,
    .channels = config.channels,
    .sample_rate_hz = config.sample_rate_hz,
    .dtype = CORTEX_DTYPE_FLOAT32,
    .calibration_state = calibration_state,
    .calibration_state_size = config.calibration_state_size,
};
strncpy(plugin_config.kernel_params, config.plugin_params,
        sizeof(plugin_config.kernel_params));

cortex_init_result_t init_result = cortex_init(&plugin_config);
if (init_result.error_code != 0) {
    fprintf(stderr, "[adapter] Kernel initialization failed: %d\n",
            init_result.error_code);
    return 1;
}

void *kernel_handle = init_result.handle;

fprintf(stderr, "[adapter] Kernel loaded and initialized\n");
```

---

## Step 5: Implement Window Processing Loop

Add the main execution loop:

```c
// Allocate buffers
size_t input_size = config.window_length_samples * config.channels * sizeof(float);
size_t output_size = ack.output_width * ack.output_height * sizeof(float);

float *input_buffer = malloc(input_size);
float *output_buffer = malloc(output_size);

if (!input_buffer || !output_buffer) {
    fprintf(stderr, "[adapter] Failed to allocate buffers\n");
    return 1;
}

// Main window processing loop
for (;;) {
    // Receive windowed input (may be chunked)
    cortex_wire_window_chunk_t chunk_info;
    uint32_t sequence = 0;

    if (cortex_protocol_recv_window(&protocol, input_buffer, input_size,
                                    &chunk_info, &sequence) != 0) {
        fprintf(stderr, "[adapter] Failed to receive window\n");
        break;
    }

    // Record device timing
    uint64_t device_tin_ns = get_time_ns();
    uint64_t device_tstart_ns = get_time_ns();

    // Execute kernel
    cortex_process_result_t result = cortex_process(
        kernel_handle,
        input_buffer,
        output_buffer
    );

    uint64_t device_tend_ns = get_time_ns();

    // Check for kernel errors
    if (result.error_code != 0) {
        // Send ERROR frame
        cortex_wire_error_t error = {
            .error_code = result.error_code,
            .sequence = sequence,
        };
        snprintf(error.error_message, sizeof(error.error_message),
                 "Kernel execution failed");
        cortex_protocol_send_error(&protocol, &error);
        continue;
    }

    // Send RESULT frame
    cortex_wire_result_t wire_result = {
        .session_id = config.session_id,
        .sequence = sequence,
        .error_code = 0,
        .device_tin_ns = device_tin_ns,
        .device_tstart_ns = device_tstart_ns,
        .device_tend_ns = device_tend_ns,
        .device_tfirst_tx_ns = get_time_ns(),
        .output_size = output_size,
        .output_width = ack.output_width,
        .output_height = ack.output_height,
    };

    if (cortex_protocol_send_result(&protocol, &wire_result, output_buffer) != 0) {
        fprintf(stderr, "[adapter] Failed to send RESULT\n");
        break;
    }

    wire_result.device_tlast_tx_ns = get_time_ns();
}

// Cleanup
cortex_teardown(kernel_handle);
free(input_buffer);
free(output_buffer);
free(calibration_state);
dlclose(kernel_lib);
```

---

## Step 6: Add Timing Helper

Implement nanosecond-precision timing:

```c
#include <time.h>

static uint64_t get_time_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}
```

---

## Step 7: Create Makefile

Create `Makefile` for building your adapter:

```makefile
CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2
CFLAGS += -I../../../../sdk/adapter/include
CFLAGS += -I../../../../sdk/kernel/include

# Platform detection
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LDFLAGS = -ldl -lpthread
else
    LDFLAGS = -ldl -lpthread
endif

# SDK libraries
PROTOCOL_LIB = ../../../../sdk/adapter/lib/protocol
TRANSPORT_LIB = ../../../../sdk/adapter/lib/transport/local

LIBS = $(PROTOCOL_LIB)/protocol.o \
       $(PROTOCOL_LIB)/crc32.o \
       $(TRANSPORT_LIB)/mock.o

TARGET = cortex_adapter_myboard_local

all: $(TARGET)

$(TARGET): adapter.c $(LIBS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

clean:
	rm -f $(TARGET)

.PHONY: all clean
```

---

## Step 8: Build and Test

```bash
# Build adapter
make

# Test with CORTEX harness
cd ../../../../  # Back to CORTEX root

# Create minimal config
cat > /tmp/test_myboard.yaml <<EOF
cortex_version: 1
dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  channels: 64
  sample_rate_hz: 160
plugins:
  - name: "noop"
    status: ready
    spec_uri: "primitives/kernels/v1/noop@f32"
    adapter_path: "primitives/adapters/v1/myboard@local/cortex_adapter_myboard_local"
EOF

# Run test
env CORTEX_DURATION_OVERRIDE=1 CORTEX_REPEATS_OVERRIDE=1 \
    ./src/engine/harness/cortex run /tmp/test_myboard.yaml
```

**Expected output:**
```
[adapter] Handshake complete
[adapter] Kernel loaded and initialized
[telemetry] plugin=noop latency_ns=... deadline_missed=0
```

---

## Step 9: Error Handling Best Practices

Add robust error handling:

```c
// Always send ERROR frames instead of silent failures
static void send_error_frame(cortex_protocol_t *protocol,
                             uint32_t error_code,
                             uint32_t sequence,
                             const char *message) {
    cortex_wire_error_t error = {
        .error_code = error_code,
        .sequence = sequence,
    };
    snprintf(error.error_message, sizeof(error.error_message), "%s", message);
    cortex_protocol_send_error(protocol, &error);
}

// Example usage in window loop:
if (recv_window_failed) {
    send_error_frame(&protocol, CORTEX_E_TRANSPORT_FAILED, sequence,
                     "Failed to receive window data");
    break;  // Or continue depending on policy
}
```

**Key Principles:**
1. **Never hang** - all recv() calls must have timeouts
2. **Send ERROR frames** - don't fail silently
3. **Log to stderr** - harness captures adapter stderr
4. **Validate all inputs** - check payload sizes, CRC, session IDs
5. **Clean up resources** - free buffers, dlclose(), teardown

---

## Step 10: Conformance Testing

Verify your adapter passes all tests:

```bash
# Test 1: Protocol conformance
make -C tests test-protocol

# Test 2: Adapter smoke test
make -C tests test-adapter-smoke

# Test 3: All kernels
env CORTEX_DURATION_OVERRIDE=1 ./src/engine/harness/cortex run \
    primitives/configs/cortex.yaml
```

**Pass criteria:**
- ✅ No crashes or hangs
- ✅ All 6 kernels execute successfully
- ✅ Telemetry output looks reasonable (latencies < 10ms for noop)
- ✅ No valgrind errors (see [Testing section](#memory-leak-testing))

---

## Advanced Topics

### Supporting Trainable Kernels

Trainable kernels (ICA, CSP, LDA) require calibration state:

```c
// In CONFIG handler:
if (config.calibration_state_size > 0) {
    calibration_state = malloc(config.calibration_state_size);
    if (!calibration_state) {
        send_error_frame(&protocol, CORTEX_E_OUT_OF_MEMORY, 0,
                         "Failed to allocate calibration state");
        return 1;
    }

    // State data follows CONFIG struct in payload
    // (Already handled by cortex_protocol_recv_config)
}

// Pass to kernel init
plugin_config.calibration_state = calibration_state;
plugin_config.calibration_state_size = config.calibration_state_size;
```

### Dimension-Changing Kernels

Some kernels change output dimensions (e.g., Welch PSD, Goertzel):

```c
// After cortex_init(), query actual output dimensions
uint32_t actual_output_width = init_result.output_width;
uint32_t actual_output_height = init_result.output_height;

// Report in ACK
ack.output_width = actual_output_width;
ack.output_height = actual_output_height;

// Allocate correct output buffer size
size_t output_size = actual_output_width * actual_output_height * sizeof(float);
output_buffer = malloc(output_size);
```

### Memory-Constrained Platforms

For embedded systems with limited RAM:

```c
// Advertise constraints in HELLO
hello.max_window_samples = 256;  // Smaller than default 512
hello.max_channels = 32;         // Fewer channels

// Harness will respect these limits when selecting kernels
```

### Network Adapters (TCP)

For remote execution (Jetson, cloud):

```c
// Replace stdio transport with TCP client
cortex_transport_t transport;
if (cortex_transport_init_tcp_client(&transport, "192.168.1.100", 9000) != 0) {
    fprintf(stderr, "[adapter] Failed to connect to harness\n");
    return 1;
}

// Rest of code identical - protocol layer abstracts transport
```

---

## Troubleshooting

### Adapter Hangs During Handshake

**Symptom:** Adapter process starts but never prints "Handshake complete"

**Diagnosis:**
```bash
# Run with verbose logging
strace -e read,write ./cortex_adapter_myboard_local

# Check if HELLO frame was sent
# Should see write() calls with MAGIC bytes: 58 54 52 43
```

**Common causes:**
1. Transport not initialized (forgot `cortex_transport_init_stdio()`)
2. CRC mismatch (endianness bug)
3. Protocol version mismatch

### Kernel Fails to Load

**Symptom:** `dlopen()` returns NULL

**Diagnosis:**
```bash
# Check if kernel library exists
ls -l primitives/kernels/v1/noop@f32/libnoop.dylib

# Check linker errors
LD_DEBUG=all ./cortex_adapter_myboard_local 2>&1 | grep libnoop
```

**Solutions:**
1. Build kernel first: `make -C primitives/kernels/v1/noop@f32/`
2. Use absolute path: `realpath()` on `config.plugin_name`
3. Check library extension (`.dylib` on macOS, `.so` on Linux)

### Telemetry Shows Huge Latencies

**Symptom:** `latency_ns` values in millions (seconds instead of microseconds)

**Diagnosis:**
```bash
# Check timing implementation
# Should use CLOCK_MONOTONIC, not CLOCK_REALTIME
```

**Fix:**
```c
// WRONG: Uses wall clock (affected by NTP adjustments)
clock_gettime(CLOCK_REALTIME, &ts);

// CORRECT: Uses monotonic clock
clock_gettime(CLOCK_MONOTONIC, &ts);
```

### Memory Leak Testing

Run your adapter under Valgrind:

```bash
# Build with debug symbols
make CFLAGS="-g -O0" clean all

# Run under Valgrind
valgrind --leak-check=full --show-leak-kinds=all \
    env CORTEX_DURATION_OVERRIDE=1 CORTEX_REPEATS_OVERRIDE=1 \
    ./src/engine/harness/cortex run /tmp/test_myboard.yaml
```

**Expected output:**
```
==12345== HEAP SUMMARY:
==12345==     in use at exit: 0 bytes in 0 blocks
==12345==   total heap usage: ... allocs, ... frees
==12345== All heap blocks were freed -- no leaks are possible
```

---

## Checklist

Before submitting your adapter, verify:

**Code Quality:**
- [ ] No compiler warnings (`-Wall -Wextra`)
- [ ] Valgrind clean (no leaks, no invalid accesses)
- [ ] Error handling on all allocations
- [ ] All resources cleaned up in teardown

**Protocol Compliance:**
- [ ] Sends HELLO with correct ABI version (1)
- [ ] Validates session_id in CONFIG
- [ ] Reports correct output dimensions in ACK
- [ ] Includes device timing in RESULT
- [ ] Sends ERROR frames instead of silent failures

**Testing:**
- [ ] All 6 reference kernels execute successfully
- [ ] Telemetry values look reasonable
- [ ] No hangs or crashes
- [ ] Passes test-protocol, test-adapter-smoke

**Documentation:**
- [ ] README.md with usage instructions
- [ ] Build instructions in README
- [ ] Known limitations documented
- [ ] Example config YAML provided

---

## Next Steps

After completing this tutorial, you should:

1. **Read the transport layer docs:** [`sdk/adapter/lib/transport/README.md`](../../sdk/adapter/lib/transport/README.md)
2. **Study reference implementations:**
   - native: `primitives/adapters/v1/native/`
   - TCP client template: `sdk/adapter/lib/transport/network/tcp_client.c`
   - UART template: `sdk/adapter/lib/transport/serial/uart_posix.c`
3. **Contribute your adapter:** Open a PR to add your adapter to `primitives/adapters/v1/`

---

## References

- **Wire Protocol Spec:** [`docs/reference/adapter-protocol.md`](../reference/adapter-protocol.md)
- **SDK Documentation:** [`sdk/adapter/README.md`](../../sdk/adapter/README.md)
- **Adapter Catalog:** [`primitives/adapters/v1/README.md`](../../primitives/adapters/v1/README.md)
- **Using Adapters Guide:** [`docs/guides/using-adapters.md`](using-adapters.md)
- **Kernel Plugin API:** [`docs/reference/plugin-interface.md`](../reference/plugin-interface.md)

---

## Getting Help

- **GitHub Issues:** https://github.com/WestonVoglesonger/CORTEX/issues
- **Adapter Examples:** `primitives/adapters/v1/`
- **SDK Source:** `sdk/adapter/lib/`
