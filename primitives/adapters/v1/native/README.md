# native Adapter

**Platform:** x86_64, arm64 (macOS, Linux)
**Transport:** Mock (socketpair - stdin/stdout)
**Purpose:** Local development, testing, and CI/CD validation

The native adapter enables running CORTEX kernels in a separate process on the same machine, communicating via stdin/stdout over a socketpair. This is the **primary adapter for Phase 1 development** and serves as the reference implementation for the CORTEX adapter protocol.

---

## Overview

```
┌──────────────┐                         ┌──────────────────┐
│   Harness    │                         │  native    │
│  (parent)    │                         │  (child process) │
│              │                         │                  │
│  scheduler ──┼─── socketpair ─────────►│  stdin/stdout    │
│  device_comm │   (full-duplex IPC)     │  protocol layer  │
│              │◄────────────────────────┤  kernel dlopen   │
└──────────────┘                         └──────────────────┘
```

**Architecture:**
1. **Harness** spawns adapter via `fork()` + `exec()`
2. **Socketpair** provides bidirectional byte stream (stdin/stdout for adapter)
3. **Adapter** runs protocol handshake (HELLO → CONFIG → ACK)
4. **Window loop:** Harness sends WINDOW chunks → Adapter processes → Returns RESULT
5. **Dynamic kernel loading:** Adapter uses `dlopen()` to load kernels from `primitives/kernels/v1/`

---

## Quick Start

### Build

```bash
# From CORTEX root
cd primitives/adapters/v1/native
make clean && make

# Verify binary created
ls -lh cortex_adapter_native
# Should be ~35KB
```

### Manual Test (Interactive)

```bash
# Run adapter (reads from stdin, writes to stdout)
./cortex_adapter_native

# Adapter sends HELLO frame immediately
# You'll see binary output (MAGIC: 0x58 0x54 0x52 0x43 "CRTX")

# Send CONFIG frame (hex input):
# ... (manual protocol testing is complex - use harness integration instead)
```

### Integrated Test (Via Harness)

```bash
# From CORTEX root - run through harness
cortex pipeline --duration 1 --repeats 1 --warmup 0

# Check telemetry for adapter fields
cat results/run-*/telemetry-*.csv | head -5
# Should see: device_tin_ns, device_tstart_ns, device_tend_ns columns
```

---

## How It Works

### 1. Initialization

**On Startup:**
```c
// adapter.c:202-223
uint32_t boot_id = generate_boot_id();  // Random ID (detects adapter restarts)

// Create transport from stdin/stdout (inherited from socketpair)
cortex_transport_t *tp = cortex_transport_mock_create_from_fds(
    STDIN_FILENO,   // Read from stdin (sv[1] from harness socketpair)
    STDOUT_FILENO   // Write to stdout
);
```

**Boot ID Generation:**
- Uses `CLOCK_MONOTONIC` timestamp XOR'd with nanoseconds
- Unique per adapter process launch
- Harness uses this to detect adapter restarts

### 2. Handshake Sequence

```
Adapter                            Harness
  │                                   │
  ├──────── HELLO ─────────────────►  │  (boot_id, "native", "noop@f32")
  │                                   │
  ◄─────── CONFIG ────────────────────┤  (session_id, kernel selection)
  │                                   │
  [dlopen kernel plugin]              │
  [cortex_init(config)]               │
  │                                   │
  ├──────── ACK ───────────────────►  │  (ready to process windows)
  │                                   │
```

**HELLO Frame:**
```c
// adapter.c:227
cortex_adapter_send_hello(
    &transport,
    boot_id,
    "native",  // adapter_name
    "noop@f32",      // Single kernel advertised (Phase 1)
    1024,            // max_window_samples
    64               // max_channels
);
```

**CONFIG Frame:**
```c
// adapter.c:238-244
cortex_adapter_recv_config(
    &transport,
    &session_id,         // OUT: Random session ID from harness
    &sample_rate_hz,     // OUT: 160, 250, etc.
    &window_samples,     // OUT: W (e.g., 160)
    &hop_samples,        // OUT: H (e.g., 80)
    &channels,           // OUT: C (e.g., 64)
    plugin_name,         // OUT: "car@f32", "noop@f32", etc.
    plugin_params        // OUT: "lowcut=8,highcut=30"
);
```

**Kernel Loading:**
```c
// adapter.c:247-254
kernel_plugin_t kernel_plugin;
load_kernel_plugin(
    plugin_name,         // "car@f32"
    sample_rate_hz,
    window_samples,
    hop_samples,
    channels,
    plugin_params,       // "lowcut=8,highcut=30"
    NULL,                // calibration_state (Phase 1: not used)
    0,                   // calibration_state_size
    &kernel_plugin
);

// Internally calls:
// 1. dlopen("primitives/kernels/v1/car@f32/libcar.dylib")
// 2. dlsym("cortex_init", "cortex_process", "cortex_teardown")
// 3. cortex_init(&config)
```

### 3. Window Processing Loop

```c
// adapter.c:283-336
while (1) {
    // Receive chunked WINDOW (40KB → 5×8KB chunks)
    cortex_protocol_recv_window_chunked(
        &transport,
        sequence,          // Expected sequence (0, 1, 2, ...)
        window_buf,        // OUT: float32 array (W×C samples)
        window_size,
        &received_window_samples,
        &received_channels,
        CORTEX_WINDOW_TIMEOUT_MS  // 10 seconds
    );

    // Timestamp: tin AFTER reassembly complete
    uint64_t tin = get_timestamp_ns();

    // Execute kernel
    uint64_t tstart = get_timestamp_ns();
    kernel_plugin.process(
        kernel_plugin.kernel_handle,
        window_buf,   // Input: W×C float32
        output_buf    // Output: W'×C' float32 (may differ from input)
    );
    uint64_t tend = get_timestamp_ns();

    // Send RESULT with timing
    uint64_t tfirst_tx = get_timestamp_ns();
    cortex_adapter_send_result(
        &transport,
        session_id,    // Must match CONFIG session_id
        sequence,      // Must match WINDOW sequence
        tin,           // Input complete timestamp
        tstart,        // Kernel start
        tend,          // Kernel end
        tfirst_tx,     // First byte tx
        tfirst_tx,     // Last byte tx (approximation)
        output_buf,
        kernel_plugin.output_window_length_samples,
        kernel_plugin.output_channels
    );

    sequence++;  // Increment for next window
}
```

**Timing Semantics:**
- **tin:** Set AFTER last WINDOW_CHUNK received and decoded to host format
- **tstart:** Set immediately before `cortex_process()` call
- **tend:** Set immediately after `cortex_process()` returns
- **tfirst_tx:** Set before sending RESULT frame
- **tlast_tx:** Set after sending RESULT frame (TODO: improve accuracy)

**Why tin is after reassembly:**
- Measures time from "input ready for processing" to "output sent"
- Includes protocol decoding overhead (chunking, endian conversion)
- Excludes network transmission time (chunks sent separately)

### 4. Graceful Shutdown

```c
// adapter.c:299-301
int ret = cortex_protocol_recv_window_chunked(...);
if (ret < 0) {
    // Timeout or error (harness closed connection)
    break;  // Exit loop
}

// Cleanup
free(window_buf);
free(output_buf);
unload_kernel_plugin(&kernel_plugin);  // dlclose, cortex_teardown
transport.close(transport.ctx);
free(tp);
```

**Shutdown Triggers:**
- **Harness closes socketpair:** `recv()` returns EOF, protocol returns `CORTEX_ECONNRESET`
- **Timeout:** No WINDOW received within 10 seconds (returns `CORTEX_ETIMEDOUT`)
- **Error:** Protocol error (CRC mismatch, invalid frame, etc.)

---

## Dynamic Kernel Loading

### Plugin Path Resolution

```c
// adapter.c:98-124
// Input: plugin_name = "car@f32"
// Output: lib_path = "primitives/kernels/v1/car@f32/libcar.dylib" (macOS)
//         lib_path = "primitives/kernels/v1/car@f32/libcar.so"    (Linux)

// Extract base name (before '@')
const char *at_sign = strchr(plugin_name, '@');
size_t base_len = (size_t)(at_sign - plugin_name);
memcpy(lib_name, plugin_name, base_len);  // "car"

// Construct path
#ifdef __APPLE__
snprintf(lib_path, sizeof(lib_path),
         "primitives/kernels/v1/%s/lib%s.dylib",
         plugin_name,  // "car@f32"
         lib_name);    // "car"
#else
snprintf(lib_path, sizeof(lib_path),
         "primitives/kernels/v1/%s/lib%s.so",
         plugin_name, lib_name);
#endif
```

### Symbol Loading

```c
// adapter.c:127-143
void *dl = dlopen(lib_path, RTLD_NOW | RTLD_LOCAL);

cortex_init_fn init_fn = (cortex_init_fn)dlsym(dl, "cortex_init");
cortex_process_fn process_fn = (cortex_process_fn)dlsym(dl, "cortex_process");
cortex_teardown_fn teardown_fn = (cortex_teardown_fn)dlsym(dl, "cortex_teardown");
cortex_calibrate_fn calibrate_fn = (cortex_calibrate_fn)dlsym(dl, "cortex_calibrate");

// Detect ABI version (v2 vs v3)
uint32_t kernel_abi_version = (calibrate_fn != NULL) ? 3 : 2;
```

**ABI Version Detection:**
- **v2 kernels:** Export `cortex_init`, `cortex_process`, `cortex_teardown` only
- **v3 kernels:** Additionally export `cortex_calibrate` (trainable kernels)
- Adapter detects v3 by checking if `cortex_calibrate` symbol exists
- Passes correct `abi_version` to kernel's `cortex_init()`

### Kernel Initialization

```c
// adapter.c:149-170
cortex_plugin_config_t config = {
    .abi_version = kernel_abi_version,  // 2 or 3
    .struct_size = sizeof(cortex_plugin_config_t),
    .sample_rate_hz = 160,
    .window_length_samples = 160,
    .hop_samples = 80,
    .channels = 64,
    .dtype = 1,  // CORTEX_DTYPE_FLOAT32
    .allow_in_place = 0,
    .kernel_params = "lowcut=8,highcut=30",  // String from CONFIG
    .kernel_params_size = strlen(...),
    .calibration_state = NULL,   // Phase 1: not used
    .calibration_state_size = 0
};

cortex_init_result_t result = init_fn(&config);
void *kernel_handle = result.handle;  // Opaque kernel state
uint32_t output_window_samples = result.output_window_length_samples;
uint32_t output_channels = result.output_channels;
```

**Output Shape:**
- Kernels may change output dimensions (e.g., CSP reduces channels)
- `cortex_init()` returns actual output shape in `result` struct
- Adapter allocates output buffer based on returned dimensions
- RESULT frame includes actual output shape for harness validation

---

## Telemetry Integration

### Device-Side Timing

**Timestamps captured on adapter:**
```
tin:       AFTER window reassembly complete (input ready)
tstart:    BEFORE cortex_process() call
tend:      AFTER cortex_process() returns
tfirst_tx: BEFORE sending RESULT frame
tlast_tx:  AFTER sending RESULT frame
```

**Telemetry Record (Harness Side):**
```csv
kernel,window,deadline_ns,tin_ns,tout_ns,device_tin_ns,device_tstart_ns,device_tend_ns,device_tfirst_tx_ns,device_tlast_tx_ns
car,0,500000000,1234567890000000,1234567891000000,1234567890123456,1234567890150000,1234567890180000,1234567890185000,1234567890190000
```

**Latency Analysis:**
```
Processing latency (pure kernel):  device_tend_ns - device_tstart_ns
Total latency (adapter-side):     device_tlast_tx_ns - device_tin_ns
Round-trip latency (harness-side): tout_ns - tin_ns
```

**Why device timestamps are important:**
- Measures **actual kernel execution time** on device
- Excludes harness overhead (scheduling, telemetry recording)
- Enables cross-platform comparison (loopback vs Jetson vs STM32)
- Isolates transport latency (network, UART)

---

## Supported Kernels

**Phase 1 (Current):**
- All 6 kernels from `primitives/kernels/v1/`:
  - `car@f32` — Common Average Reference
  - `notch_iir@f32` — 60Hz line noise removal
  - `bandpass_fir@f32` — 8-30Hz passband filter
  - `goertzel@f32` — Alpha/beta bandpower
  - `welch_psd@f32` — Power spectral density
  - `noop@f32` — Identity function (overhead baseline)

**HELLO frame currently advertises only `noop@f32`** (line 227), but adapter supports all kernels via dynamic loading.

**Future (Phase 1.1):**
- Advertise all 6 kernels in HELLO frame
- Harness selects kernel from advertised list
- Validation: Reject CONFIG if kernel not in HELLO list

---

## Building and Debugging

### Build from Scratch

```bash
# Clean everything
cd primitives/adapters/v1/native
make clean

# Build SDK dependencies first
cd ../../../../sdk/adapter/lib/protocol && make clean && make
cd ../transport && make clean && make
cd ../adapter_helpers && make clean && make

# Build adapter
cd ../../../../primitives/adapters/v1/native
make

# Verify
./cortex_adapter_native --version  # Should print usage or run
```

### Debug Flags

**Enable verbose logging:**
```bash
# Add -DDEBUG to CFLAGS in Makefile
CFLAGS = -Wall -Wextra -O0 -g -std=c11 -DDEBUG

make clean && make

# Run with stderr logging
./cortex_adapter_native 2>adapter.log
```

**Use valgrind:**
```bash
# Check for memory leaks
valgrind --leak-check=full --show-leak-kinds=all \
    ./cortex_adapter_native < test_input.bin > test_output.bin 2>valgrind.log

# Should report: "All heap blocks were freed -- no leaks are possible"
```

**Use strace (Linux) / dtruss (macOS):**
```bash
# Linux
strace -e trace=read,write,open,close,mmap -s 1000 \
    ./cortex_adapter_native 2>strace.log

# macOS (requires sudo)
sudo dtruss -t read -t write -t open -t close \
    ./cortex_adapter_native 2>dtruss.log
```

### Common Build Errors

**"dlopen failed: image not found"**
- Kernel library not found
- Solution: Run from CORTEX root directory (adapter expects relative path `primitives/kernels/v1/`)
- Or set `DYLD_LIBRARY_PATH` (macOS) / `LD_LIBRARY_PATH` (Linux)

**"Failed to load kernel symbols"**
- Kernel doesn't export required symbols (`cortex_init`, `cortex_process`, `cortex_teardown`)
- Solution: Check kernel exports: `nm -g primitives/kernels/v1/car@f32/libcar.dylib | grep cortex`

**"Kernel init failed"**
- `cortex_init()` returned NULL handle
- Solution: Check kernel logs, verify parameters are valid
- Common cause: Invalid `kernel_params` string format

---

## Troubleshooting

### "Failed to create transport"

**Symptom:** Adapter exits immediately with error

**Cause:** `cortex_transport_mock_create_from_fds()` failed

**Debug:**
```bash
# Check stdin/stdout are valid
ls -l /proc/self/fd/0 /proc/self/fd/1  # Linux
lsof -p $$ | grep std                   # macOS

# Verify SDK mock transport built correctly
ls -l ../../../../sdk/adapter/lib/transport/local/mock.o
```

### "Failed to send HELLO"

**Symptom:** Adapter crashes after transport creation

**Cause:** Protocol send failure (broken pipe, stdout closed)

**Debug:**
- Check harness actually spawned adapter with socketpair
- Verify harness is reading from its end of socketpair
- Add debug logging: `fprintf(stderr, "Sending HELLO...\n");`

### "Failed to receive CONFIG"

**Symptom:** Adapter hangs or times out waiting for CONFIG

**Causes:**
1. Harness didn't send CONFIG (check harness logs)
2. Protocol mismatch (MAGIC not found)
3. CRC mismatch (corruption in transport)

**Debug:**
```bash
# Capture stdin bytes
./cortex_adapter_native < /dev/null 2>&1 | hexdump -C

# Check for MAGIC: 58 54 52 43 (little-endian "CRTX")
# If missing, harness isn't sending valid frames
```

### "Failed to load kernel: {name}"

**Symptom:** Adapter exits after receiving CONFIG

**Causes:**
1. Kernel library not found (wrong path)
2. Kernel doesn't export required symbols
3. Kernel init() failed

**Debug:**
```bash
# Verify kernel exists
ls -l primitives/kernels/v1/car@f32/libcar.dylib

# Check exports
nm -g primitives/kernels/v1/car@f32/libcar.dylib | grep cortex

# Run with dlopen verbose errors
DYLD_PRINT_LIBRARIES=1 ./cortex_adapter_native  # macOS
LD_DEBUG=libs ./cortex_adapter_native           # Linux
```

### Adapter Hangs in Window Loop

**Symptom:** Adapter stops responding, no output

**Causes:**
1. Waiting for WINDOW that never arrives (harness stalled)
2. `cortex_process()` hangs (kernel bug)
3. Deadlock in protocol layer

**Debug:**
```bash
# Attach debugger
gdb ./cortex_adapter_native
(gdb) attach <pid>
(gdb) where  # Check stack trace

# Or send signal to get backtrace
kill -ABRT <pid>
# Check core dump or stderr for backtrace
```

### Performance Lower Than Expected

**Symptom:** Kernel time (tend - tstart) much higher than direct execution

**Causes:**
1. Kernel allocating memory in process() (violates hermetic constraint)
2. CPU frequency scaling (check governor: `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`)
3. Logging/debug code left enabled

**Debug:**
```bash
# Profile with perf (Linux)
perf record -g ./cortex_adapter_native
perf report

# Check CPU frequency
watch -n1 'grep MHz /proc/cpuinfo'  # Linux
sudo powermetrics --samplers cpu   # macOS
```

---

## Performance

Measured on **MacBook Pro M1 (arm64)**:

| Metric | Loopback | Direct Execution | Overhead |
|--------|----------|------------------|----------|
| Protocol overhead | ~50µs | N/A | Socketpair latency |
| Kernel time (car) | 28µs | 26µs | +2µs (7%) |
| Kernel time (bandpass_fir) | 95µs | 92µs | +3µs (3%) |
| Round-trip (40KB window) | ~350µs | N/A | Full cycle |

**Breakdown (40KB window, car kernel):**
```
Receive WINDOW chunks (5×):   150µs  (socketpair recv + reassembly)
Kernel execution:               28µs  (cortex_process)
Send RESULT:                    50µs  (socketpair send + framing)
Protocol overhead:              ~20µs (CRC, endian conversion)
Total:                          ~248µs
```

**Overhead is acceptable** (<10%) for development/testing use case.

---

## Future Enhancements

**Phase 1.1:**
- Advertise all 6 kernels in HELLO (not just noop)
- Support calibration state in CONFIG (for ICA, CSP)
- Improve tlast_tx accuracy (DMA interrupts or post-send timestamp)

**Phase 2:**
- Multi-kernel adapter (load multiple kernels, switch via CONFIG)
- Kernel hot-reloading (dlclose old, dlopen new without restart)
- Performance mode (skip timing for max throughput)

**Phase 3:**
- Error frame support (report kernel failures gracefully)
- Streaming mode (continuous windows without per-window handshake)
- Compression (optional gzip for WINDOW/RESULT over slow transports)

---

## See Also

- **SDK Protocol Documentation:** [`../../../../sdk/adapter/lib/protocol/README.md`](../../../../sdk/adapter/lib/protocol/README.md)
- **SDK Transport Documentation:** [`../../../../sdk/adapter/lib/transport/README.md`](../../../../sdk/adapter/lib/transport/README.md)
- **Adapter Helpers API:** [`../../../../sdk/adapter/include/cortex_adapter_helpers.h`](../../../../sdk/adapter/include/cortex_adapter_helpers.h)
- **Kernel Plugin ABI:** [`../../../../sdk/kernel/include/cortex_plugin.h`](../../../../sdk/kernel/include/cortex_plugin.h)
- **Implementation Plan:** [`../../../../ADAPTER_IMPLEMENTATION.md`](../../../../ADAPTER_IMPLEMENTATION.md)
