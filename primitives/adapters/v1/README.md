# CORTEX Device Adapters (v1)

**Directory:** `primitives/adapters/v1/`
**Purpose:** Hardware-In-the-Loop (HIL) testing for BCI kernels across platforms
**ABI Version:** 1 (adapter protocol, not to be confused with kernel ABI v2/v3)

Device adapters enable running CORTEX kernels on different hardware platforms while maintaining consistent telemetry and validation. The harness **always** uses adapters (no direct execution mode), ensuring unified measurement methodology across local and remote execution.

---

## Overview

```
Harness (x86 workstation)
    ↓
Device Adapter (abstraction layer)
    ↓
Kernel Execution (x86, Jetson, STM32, etc.)
```

**Key Benefits:**
- **Consistent telemetry:** Same metrics for local and remote execution
- **Platform validation:** Verify kernels work identically across architectures
- **Real-world testing:** Measure actual hardware latency, not simulation
- **Unified workflow:** Same `cortex pipeline` command for all platforms

---

## Available Adapters

| Adapter | Platform | Transport | Status | Use Case |
|---------|----------|-----------|--------|----------|
| **[native](native/)** | x86_64, arm64 (macOS/Linux) | Mock (socketpair) | ✅ Complete | Local development, CI/CD, reference implementation |
| **jetson-nano@tcp** | Jetson Nano (aarch64) | TCP Client | ⬜ Planned (Phase 2) | Remote GPU-accelerated processing |
| **stm32-h7@uart** | STM32H7 (Cortex-M7) | UART | ⬜ Planned (Phase 3) | Bare-metal embedded validation |

---

## native

**Platform:** x86_64, arm64 (macOS, Linux)
**Transport:** Mock (socketpair - stdin/stdout)
**Status:** ✅ Complete (Phase 1)

### Purpose

Primary adapter for **local development and testing**. Runs kernels in a separate process on the same machine, communicating via socketpair IPC. Serves as the **reference implementation** for the CORTEX adapter protocol.

### Architecture

```
Harness (parent process)
    ↓ fork() + exec()
native Adapter (child process)
    ↓ dlopen()
Kernel Plugin (.dylib/.so)
```

**Key Features:**
- **Dynamic kernel loading:** Uses `dlopen()` to load kernels from `primitives/kernels/v1/`
- **ABI version detection:** Auto-detects v2 vs v3 kernels (checks for `cortex_calibrate` symbol)
- **Full protocol support:** HELLO, CONFIG, ACK, WINDOW_CHUNK, RESULT frames
- **Device-side timing:** Captures 5 timestamps (tin, tstart, tend, tfirst_tx, tlast_tx)

### Performance

| Metric | Value | Overhead vs Direct |
|--------|-------|-------------------|
| Protocol overhead | ~50µs | Socketpair latency |
| Kernel time (car) | 28µs | +2µs (7%) |
| Round-trip (40KB window) | ~350µs | N/A |

**Conclusion:** Overhead is negligible (<10%) for development/testing.

### Usage

```bash
# Build
cd primitives/adapters/v1/native
make

# Run via harness
cortex pipeline --duration 1 --repeats 1

# Check telemetry includes device timestamps
cat results/run-*/telemetry-*.csv | head -5
# Should see: device_tin_ns, device_tstart_ns, device_tend_ns
```

### Documentation

**Complete guide:** [native/README.md](native/README.md)

---

## jetson-nano@tcp (Planned - Phase 2)

**Platform:** NVIDIA Jetson Nano (aarch64, Ubuntu 18.04+)
**Transport:** TCP Client (connects to harness)
**Status:** ⬜ Planned

### Purpose

Remote execution on **GPU-accelerated embedded platform**. Validates kernels on ARM64 with CUDA support, measures real-world network latency.

### Architecture (Planned)

```
Harness (x86 workstation)
    ↓ TCP (LAN or WiFi)
jetson-nano@tcp Daemon (Jetson Nano)
    ↓ dlopen()
Kernel Plugin (.so, aarch64)
```

**Why TCP instead of UART:**
- Jetson has Gigabit Ethernet (much faster than UART)
- 40KB windows @ 2Hz = 80 KB/s (trivial for TCP, painful for UART)
- Easier debugging (can use Wireshark, netcat, etc.)

### Planned Features

- **TCP daemon:** Listens on port 8080, accepts harness connection
- **Cross-compilation:** Build on x86, deploy to Jetson
- **CUDA integration:** Measure GPU kernel execution time
- **Network resilience:** Automatic reconnect on connection loss

### Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| TCP latency (LAN) | ~1-5ms | Gigabit Ethernet |
| Kernel time (car) | ~50µs | ARM Cortex-A57 @ 1.4GHz |
| Round-trip (40KB) | ~10ms | Network + processing |

### Gating Criteria (Phase 2)

1. TCP connection stable (no drops over 1000 windows)
2. All 8 kernels execute correctly on Jetson
3. Telemetry shows realistic network latency
4. No memory leaks (valgrind validation)
5. Daemon runs stable for extended periods

---

## stm32-h7@uart (Planned - Phase 3)

**Platform:** STM32H7 (Cortex-M7 @ 480MHz)
**Transport:** UART (921600 baud)
**Status:** ⬜ Planned

### Purpose

**Bare-metal embedded validation** on microcontroller. Proves kernels work on resource-constrained devices, measures interrupt-driven timing with DWT cycle counter.

### Architecture (Planned)

```
Harness (x86 workstation)
    ↓ USB-to-serial (UART @ 921600 baud)
stm32-h7@uart Firmware (STM32H7)
    ↓ Static linking (no dlopen)
Kernel Code (compiled into firmware)
```

**Why UART for STM32:**
- STM32H7 doesn't have Ethernet (UART is primary I/O)
- 921600 baud ≈ 92 KB/s (sufficient for 40KB windows @ 2Hz = 80 KB/s)
- Flow control via protocol chunking (prevents buffer overflow)

### Planned Features

- **Static kernel table:** All 8 kernels linked into firmware (no dynamic loading)
- **DWT timestamps:** Sub-microsecond resolution using Data Watchpoint and Trace unit
- **Hardware FPU:** M7 has IEEE-754 float32 FPU
- **Interrupt-driven:** UART RX/TX via DMA interrupts

### Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| UART latency | ~10ms | 921600 baud serialization time |
| Kernel time (car) | ~200µs | Cortex-M7 @ 480MHz (slower than A57) |
| DWT resolution | <1µs | 480MHz cycle counter |

### Memory Constraints

| Resource | Available | Usage (Estimated) |
|----------|-----------|------------------|
| Flash | 2MB | ~500KB (firmware + 6 kernels) |
| RAM | 512KB | ~100KB (window + kernel state) |

**Largest window:** 160 samples × 64 channels × 4 bytes = 40KB (fits in RAM)

### Gating Criteria (Phase 3)

1. Firmware builds and flashes (no linker errors)
2. UART stable at 921600 baud (no frame corruption)
3. At least 3 kernels execute correctly (noop, car, notch_iir)
4. DWT timestamps accurate (<1µs resolution)
5. Float math matches oracle (M7 hardware FPU)

---

## Adapter Selection Guide

### Decision Tree

**Question 1: Is the kernel on the same machine as the harness?**
- **Yes** → Use **native**
- **No** → Go to Question 2

**Question 2: Does the device have a network interface?**
- **Yes** (Jetson, Pi, x86 server) → Use **jetson-nano@tcp** (or equivalent)
- **No** (bare-metal embedded) → Use **stm32-h7@uart** (or equivalent)

**Question 3: Do you need GPU acceleration?**
- **Yes** → Use **jetson-nano@tcp** (CUDA support)
- **No** → Use **native** or **stm32-h7@uart**

**Question 4: Are you benchmarking transport overhead?**
- **Yes** → Use **native** (minimal overhead, isolates kernel time)
- **No** → Any adapter is fine

### Comparison Table

| Feature | native | jetson-nano@tcp | stm32-h7@uart |
|---------|--------------|-----------------|---------------|
| **Latency** | ~350µs | ~10ms | ~20ms |
| **Throughput** | 500 MB/s | 100 MB/s | 90 KB/s |
| **Setup** | Trivial | Easy (network) | Moderate (flash firmware) |
| **Debugging** | Easy (strace) | Medium (ssh) | Hard (JTAG) |
| **Platform** | macOS, Linux | Ubuntu 18.04+ | Bare-metal |
| **Kernel Loading** | Dynamic (dlopen) | Dynamic | Static (compiled in) |
| **Use Case** | Dev/Test/CI | Remote ARM/GPU | Embedded validation |

---

## Protocol Compatibility

All adapters implement the same protocol:

1. **HELLO** (Adapter → Harness): Advertise capabilities
2. **CONFIG** (Harness → Adapter): Select kernel and configure
3. **ACK** (Adapter → Harness): Ready to process
4. **WINDOW_CHUNK** (Harness → Adapter): Input data (chunked)
5. **RESULT** (Adapter → Harness): Output + timing
6. **ERROR** (Either direction): Error reporting

**Wire format:**
- Little-endian integers/floats
- CRC32 validation (IEEE 802.3 polynomial)
- MAGIC prefix: `0x43525458` ("CRTX")
- Frame size: 64KB max (8KB chunks for WINDOW)

**See:** [`../../../sdk/adapter/lib/protocol/README.md`](../../../sdk/adapter/lib/protocol/README.md)

---

## Creating a New Adapter

### Step-by-Step Guide

**1. Choose transport:**
- Local: Mock (socketpair)
- Network: TCP Client
- Serial: UART POSIX

**2. Implement protocol:**
```c
#include "cortex_transport.h"
#include "cortex_protocol.h"
#include "cortex_adapter_helpers.h"

// Create transport
cortex_transport_t *transport = cortex_transport_tcp_client_create("192.168.1.100", 8080, 5000);

// Send HELLO
cortex_adapter_send_hello(transport, boot_id, "my_adapter", "car@f32", 1024, 64);

// Receive CONFIG
cortex_adapter_recv_config(transport, &session_id, &sample_rate, ...);

// Load kernel (platform-specific)
// ...

// Send ACK
cortex_adapter_send_ack(transport);

// Window loop
while (1) {
    cortex_protocol_recv_window_chunked(transport, sequence, window_buf, ...);
    uint64_t tin = get_timestamp_ns();

    kernel_process(handle, window_buf, output_buf);

    cortex_adapter_send_result(transport, session_id, sequence, tin, tstart, tend, ...);
    sequence++;
}
```

**3. Build:**
```makefile
# Link against SDK libraries
INCLUDES = -I../../../sdk/adapter/include
PROTOCOL_OBJS = ../../../sdk/adapter/lib/protocol/protocol.o \
                ../../../sdk/adapter/lib/protocol/crc32.o
TRANSPORT_OBJS = ../../../sdk/adapter/lib/transport/network/tcp_client.o
ADAPTER_HELPERS_OBJS = ../../../sdk/adapter/lib/adapter_helpers/adapter_helpers.o

$(TARGET): adapter.o $(PROTOCOL_OBJS) $(TRANSPORT_OBJS) $(ADAPTER_HELPERS_OBJS)
	$(CC) -o $@ $^ $(LIBS)
```

**4. Test:**
```bash
# Manual protocol test
./my_adapter

# Integrated test via harness
# (Add adapter_path to primitives/configs/cortex.yaml)
cortex pipeline
```

**5. Document:**
- Create `README.md` (usage, architecture, troubleshooting)
- Create `config.yaml` (metadata, transport settings)
- Update this catalog

**Full tutorial:** *(TODO: `docs/guides/adding-adapters.md`)*

---

## Telemetry Fields

All adapters populate these device-side timing fields in telemetry:

| Field | Type | Description |
|-------|------|-------------|
| `device_tin_ns` | uint64 | Input complete timestamp (ns, device clock) |
| `device_tstart_ns` | uint64 | Kernel start timestamp |
| `device_tend_ns` | uint64 | Kernel end timestamp |
| `device_tfirst_tx_ns` | uint64 | First result byte transmitted |
| `device_tlast_tx_ns` | uint64 | Last result byte transmitted |
| `adapter_name` | string | Adapter identifier (e.g., "native") |

**Timing semantics:**
- **tin:** Set AFTER last WINDOW_CHUNK received and decoded
- **tstart:** Set immediately before `cortex_process()` call
- **tend:** Set immediately after `cortex_process()` returns
- **tfirst_tx:** Set before sending RESULT frame
- **tlast_tx:** Set after sending RESULT frame

**Latency calculations:**
```
Processing latency:  device_tend_ns - device_tstart_ns
Total adapter-side:  device_tlast_tx_ns - device_tin_ns
Round-trip (harness): tout_ns - tin_ns
```

**Note:** Device timestamps use device clock (not synchronized with harness). Only relative timing within adapter is meaningful for cross-clock comparison.

---

## Build System Integration

### Directory Structure

```
primitives/adapters/v1/
├── README.md (this file)
├── native/
│   ├── README.md
│   ├── adapter.c
│   └── Makefile
├── jetson-nano@tcp/ (future)
│   ├── README.md
│   ├── daemon/
│   │   ├── adapter_daemon.c
│   │   └── Makefile
│   └── config.yaml
└── stm32-h7@uart/ (future)
    ├── README.md
    ├── firmware/
    │   ├── main.c
    │   ├── kernel_registry.c
    │   ├── linker.ld
    │   └── Makefile
    └── config.yaml
```

### Top-Level Makefile

```makefile
# Makefile (CORTEX root)
.PHONY: adapters

adapters:
	$(MAKE) -C primitives/adapters/v1/native
	# Future: jetson-nano@tcp, stm32-h7@uart

all: harness adapters
```

### Harness Configuration

```yaml
# primitives/configs/cortex.yaml
plugins:
  - name: "car@f32"
    path: "primitives/kernels/v1/car@f32"
    adapter_path: "primitives/adapters/v1/native/cortex_adapter_native"
    adapter_config: ""  # Empty for loopback
```

---

## FAQ

### Why always use adapters (even for local execution)?

**Consistency:** Same measurement methodology for all platforms. Eliminates "works locally but fails on device" issues.

**Isolation:** Adapter runs in separate process, preventing kernel bugs from crashing harness.

**Telemetry:** Device-side timing is captured uniformly, enabling cross-platform comparison.

### What's the overhead of the adapter layer?

**native:** ~50µs per window (7% overhead for typical kernels)
**jetson-nano@tcp:** ~5-10ms (mostly network latency)
**stm32-h7@uart:** ~10-20ms (UART serialization time)

**Overhead is acceptable** for validation/testing use case (not production real-time BCI).

### Can I run multiple adapters simultaneously?

**No.** CORTEX executes kernels **sequentially** (one at a time) for measurement isolation. Parallel execution would introduce:
- CPU core contention
- Memory bandwidth competition
- Non-reproducible timing

### How do I debug adapter crashes?

1. **Check stderr:** Adapter logs errors to stderr (captured by harness)
2. **Use strace/dtruss:** Trace syscalls to see protocol I/O
3. **Attach gdb:** `gdb ./adapter -p <pid>` after spawning
4. **Valgrind:** Check for memory leaks/corruption
5. **Core dumps:** Enable with `ulimit -c unlimited`, inspect with `gdb ./adapter core`

### Can adapters support multiple kernels?

**Yes.** HELLO frame advertises multiple kernels, CONFIG selects one. Phase 1 `native` advertises only `noop@f32`, but Phase 1.1 will advertise all 8 kernels.

### What if my platform doesn't fit these categories?

**Create a custom adapter:**
1. Choose appropriate transport (or create new one)
2. Implement protocol handshake and window loop
3. Use SDK libraries (`cortex_protocol`, `cortex_transport`, `cortex_adapter_helpers`)
4. Submit PR with documentation

**Examples of custom adapters:**
- Raspberry Pi (use TCP or UART POSIX transport)
- ESP32 (create custom UART transport with ESP-IDF)
- FPGA (create custom SPI or PCIe transport)

---

## See Also

- **SDK Documentation:** [`../../../sdk/adapter/README.md`](../../../sdk/adapter/README.md)
- **Protocol Specification:** [`../../../sdk/adapter/lib/protocol/README.md`](../../../sdk/adapter/lib/protocol/README.md)
- **Transport Layer:** [`../../../sdk/adapter/lib/transport/README.md`](../../../sdk/adapter/lib/transport/README.md)
- **Implementation Plan:** [`../../../ADAPTER_IMPLEMENTATION.md`](../../../ADAPTER_IMPLEMENTATION.md)
- **Adding New Adapters:** *(TODO: `docs/guides/adding-adapters.md`)*
