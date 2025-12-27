# CORTEX Device Adapter Implementation Guide v1

This guide shows adapter developers how to implement the CORTEX device adapter interface. Adapters enable running CORTEX kernels on different hardware targets (x86, ARM, FPGA, ASIC, microcontrollers).

---

## Overview

**Adapter responsibilities**:
- Load kernels (via dlopen or static registry)
- Manage memory and buffers
- Provide accurate timestamps
- Expose platform capabilities (governor control, performance counters, etc.)

**Adapter types**:
- **Local**: In-process function calls (e.g., native x86_64 execution)
- **Remote**: Network/serial communication (e.g., embedded target over TCP/UART)

---

## Quick Start

### Minimal Adapter (No Capabilities)

```c
#include "cortex_adapter.h"
#include "cortex_plugin.h"  /* For ABI verification and dtype helpers */
#include <dlfcn.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>

typedef struct {
    void *kernel_handle;     /* dlopen handle */
    void *kernel_ctx;        /* cortex_init() result */
    void *input_buffer;      /* Allocated once, reused */
    void *output_buffer;     /* Allocated once, reused */
    size_t output_bytes;     /* Output buffer size */

    /* Kernel ABI functions */
    cortex_init_result_t (*kernel_init)(const cortex_plugin_config_t *);
    void (*kernel_process)(void *, const void *, void *);
    void (*kernel_teardown)(void *);
    uint32_t (*kernel_abi_version)(void);
} local_adapter_ctx_t;

static cortex_timestamp_t adapter_now(void *ctx) {
    (void)ctx;
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);

    cortex_timestamp_t result;
    result.value = (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
    result.freq_hz = 0;  /* 0 = nanoseconds */
    result.source = "CLOCK_MONOTONIC";
    return result;
}

static int32_t adapter_init(void *ctx, const cortex_adapter_config_t *cfg) {
    local_adapter_ctx_t *adapter = (local_adapter_ctx_t *)ctx;

    /* 1. Validate ABI version */
    if (cfg->abi_version != CORTEX_ADAPTER_ABI_VERSION) {
        return -2;  /* ABI version mismatch */
    }

    /* 2. XOR constraint: exactly one of kernel_path or kernel_id must be non-NULL */
    if ((cfg->kernel_path == NULL) == (cfg->kernel_id == NULL)) {
        return -3;  /* XOR violation */
    }

    /* 3. Validate dtype (one-hot enforcement) */
    size_t elem_size = cortex_dtype_size_bytes(cfg->dtype);
    if (elem_size == 0) {
        return -4;  /* Invalid dtype (not one-hot) */
    }

    /* 4. Load kernel (using kernel_path for this example) */
    if (cfg->kernel_path != NULL) {
        adapter->kernel_handle = dlopen(cfg->kernel_path, RTLD_NOW | RTLD_LOCAL);
        if (!adapter->kernel_handle) {
            return -6;  /* dlopen failed */
        }
    } else {
        /* Static registry lookup (adapter-specific) */
        return -6;  /* Not implemented in this example */
    }

    /* 5. Resolve kernel ABI symbols */
    adapter->kernel_abi_version = dlsym(adapter->kernel_handle, "cortex_plugin_abi_version");
    adapter->kernel_init = dlsym(adapter->kernel_handle, "cortex_init");
    adapter->kernel_process = dlsym(adapter->kernel_handle, "cortex_process");
    adapter->kernel_teardown = dlsym(adapter->kernel_handle, "cortex_teardown");

    if (!adapter->kernel_init || !adapter->kernel_process || !adapter->kernel_teardown) {
        dlclose(adapter->kernel_handle);
        return -6;  /* Missing ABI symbols */
    }

    /* 6. Verify kernel ABI version */
    if (adapter->kernel_abi_version && adapter->kernel_abi_version() != CORTEX_ABI_VERSION) {
        dlclose(adapter->kernel_handle);
        return -2;  /* Kernel ABI version mismatch */
    }

    /* 7. Build kernel config */
    cortex_plugin_config_t kernel_cfg = {0};
    kernel_cfg.abi_version = CORTEX_ABI_VERSION;
    kernel_cfg.struct_size = sizeof(cortex_plugin_config_t);
    kernel_cfg.sample_rate_hz = cfg->sample_rate_hz;
    kernel_cfg.window_length_samples = cfg->window_length_samples;
    kernel_cfg.hop_samples = cfg->hop_samples;
    kernel_cfg.channels = cfg->channels;
    kernel_cfg.dtype = cfg->dtype;
    kernel_cfg.allow_in_place = 0;  /* Separate buffers */
    kernel_cfg.kernel_params = cfg->kernel_params;
    kernel_cfg.kernel_params_size = cfg->kernel_params_size;

    /* 8. Initialize kernel */
    cortex_init_result_t init_result = adapter->kernel_init(&kernel_cfg);
    if (init_result.handle == NULL) {
        dlclose(adapter->kernel_handle);
        return -8;  /* Kernel init failed */
    }

    adapter->kernel_ctx = init_result.handle;

    /* 9. Allocate buffers (ONCE, reused across process_window calls) */
    /* Check for integer overflow using same pattern as scheduler */
    size_t input_bytes;
    if (__builtin_mul_overflow(cfg->window_length_samples, cfg->channels, &input_bytes) ||
        __builtin_mul_overflow(input_bytes, elem_size, &input_bytes)) {
        adapter->kernel_teardown(adapter->kernel_ctx);
        dlclose(adapter->kernel_handle);
        return -7;  /* Integer overflow */
    }

    size_t output_bytes;
    size_t output_samples = init_result.output_window_length_samples;
    if (__builtin_mul_overflow(output_samples, init_result.output_channels, &output_bytes) ||
        __builtin_mul_overflow(output_bytes, elem_size, &output_bytes)) {
        adapter->kernel_teardown(adapter->kernel_ctx);
        dlclose(adapter->kernel_handle);
        return -7;  /* Integer overflow */
    }

    adapter->input_buffer = malloc(input_bytes);
    adapter->output_buffer = malloc(output_bytes);
    adapter->output_bytes = output_bytes;

    if (!adapter->input_buffer || !adapter->output_buffer) {
        /* Clean up any successful allocations */
        free(adapter->input_buffer);
        free(adapter->output_buffer);
        adapter->kernel_teardown(adapter->kernel_ctx);
        dlclose(adapter->kernel_handle);
        return -7;  /* Allocation failed */
    }

    return 0;  /* Success */
}

static int32_t adapter_process_window(void *ctx, const void *in, size_t in_bytes,
                                      cortex_adapter_result_t *out) {
    local_adapter_ctx_t *adapter = (local_adapter_ctx_t *)ctx;

    /* 1. Copy input to adapter's buffer (for safety) */
    memcpy(adapter->input_buffer, in, in_bytes);

    /* 2. Stamp t_in if harness requested it */
    uint64_t t_in = out->t_in;
    if (t_in == CORTEX_TIMESTAMP_ADAPTER_STAMPS) {
        t_in = adapter_now(ctx).value;
    }

    /* 3. Start timing */
    uint64_t t_start = adapter_now(ctx).value;

    /* 4. Process window */
    adapter->kernel_process(adapter->kernel_ctx, adapter->input_buffer, adapter->output_buffer);

    /* 5. End timing */
    uint64_t t_end = adapter_now(ctx).value;

    /* 6. Populate result */
    out->output = adapter->output_buffer;  /* Valid until next call */
    out->output_bytes = adapter->output_bytes;
    out->t_in = t_in;
    out->t_start = t_start;
    out->t_end = t_end;
    out->deadline = t_in + 500000000ULL;  /* 500ms deadline (example) */

    return 0;
}

static void adapter_cleanup(void *ctx) {
    local_adapter_ctx_t *adapter = (local_adapter_ctx_t *)ctx;

    if (adapter->kernel_ctx) {
        adapter->kernel_teardown(adapter->kernel_ctx);
    }
    if (adapter->kernel_handle) {
        dlclose(adapter->kernel_handle);
    }
    free(adapter->input_buffer);
    free(adapter->output_buffer);

    /* Free the adapter context itself (allocated in cortex_adapter_get_v1) */
    free(adapter);
}

/* Adapter discovery function (REQUIRED export) */
int32_t cortex_adapter_get_v1(cortex_adapter_t *out, size_t out_size) {
    /* 1. Verify struct size */
    if (out_size < sizeof(cortex_adapter_t)) {
        return -1;  /* Caller's struct too small */
    }

    /* 2. Allocate adapter context */
    local_adapter_ctx_t *ctx = calloc(1, sizeof(local_adapter_ctx_t));
    if (!ctx) {
        return -7;  /* Allocation failed */
    }

    /* 3. Populate adapter struct */
    memset(out, 0, sizeof(cortex_adapter_t));
    out->device_id = "x86_64-native-local";
    out->arch = "x86_64";
    out->os = "linux";

    out->now = adapter_now;
    out->init = adapter_init;
    out->process_window = adapter_process_window;
    out->cleanup = adapter_cleanup;

    out->capabilities = 0;  /* No optional capabilities */
    out->context = ctx;

    return 0;
}
```

---

## Adding Capabilities

### Governor Control (Linux cpufreq)

```c
static int32_t adapter_set_governor(void *ctx, const char *mode) {
    (void)ctx;

    /* Write to /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor */
    FILE *fp = fopen("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "w");
    if (!fp) {
        return -1;
    }

    fprintf(fp, "%s\n", mode);
    fclose(fp);
    return 0;
}

/* In cortex_adapter_get_v1(): */
out->capabilities = CORTEX_CAP_GOVERNOR;
out->set_governor = adapter_set_governor;
```

### Performance Counters (Linux perf_event)

```c
#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <unistd.h>

typedef struct {
    int fd_instructions;
    int fd_cycles;
    /* ... other counters */
} pmc_ctx_t;

static int32_t adapter_read_counters(void *ctx, cortex_adapter_counters_t *out) {
    pmc_ctx_t *pmc = (pmc_ctx_t *)((local_adapter_ctx_t *)ctx)->pmc_context;

    uint64_t instructions = 0, cycles = 0;
    read(pmc->fd_instructions, &instructions, sizeof(uint64_t));
    read(pmc->fd_cycles, &cycles, sizeof(uint64_t));

    out->instructions = instructions;
    out->cycles = cycles;
    /* ... populate other counters */

    return 0;
}

/* In cortex_adapter_get_v1(): */
out->capabilities |= CORTEX_CAP_PMC;
out->read_counters = adapter_read_counters;
```

### Real-Time Scheduling (POSIX)

```c
#include <sched.h>
#include <pthread.h>

static int32_t adapter_set_rt_priority(void *ctx, int32_t priority) {
    (void)ctx;

    struct sched_param param;
    param.sched_priority = priority;

    if (pthread_setschedparam(pthread_self(), SCHED_FIFO, &param) != 0) {
        return -1;
    }

    return 0;
}

/* In cortex_adapter_get_v1(): */
out->capabilities |= CORTEX_CAP_REALTIME;
out->set_rt_priority = adapter_set_rt_priority;
```

### Thermal Monitoring (Linux hwmon)

```c
static int32_t adapter_read_thermal(void *ctx, float *temp_celsius) {
    (void)ctx;

    FILE *fp = fopen("/sys/class/hwmon/hwmon0/temp1_input", "r");
    if (!fp) {
        return -1;
    }

    int temp_millidegrees;
    fscanf(fp, "%d", &temp_millidegrees);
    fclose(fp);

    *temp_celsius = (float)temp_millidegrees / 1000.0f;
    return 0;
}

/* In cortex_adapter_get_v1(): */
out->capabilities |= CORTEX_CAP_THERMAL;
out->read_thermal = adapter_read_thermal;
```

---

## Static Kernel Registry (No dlopen)

For platforms without dynamic loading (embedded, bare-metal):

```c
#include "cortex_plugin.h"

/* Kernel implementations (statically linked) */
extern cortex_init_result_t car_init(const cortex_plugin_config_t *);
extern void car_process(void *, const void *, void *);
extern void car_teardown(void *);
extern uint32_t car_abi_version(void);

extern cortex_init_result_t notch_iir_init(const cortex_plugin_config_t *);
extern void notch_iir_process(void *, const void *, void *);
extern void notch_iir_teardown(void *);
extern uint32_t notch_iir_abi_version(void);

typedef struct {
    const char *id;
    cortex_init_result_t (*init)(const cortex_plugin_config_t *);
    void (*process)(void *, const void *, void *);
    void (*teardown)(void *);
    uint32_t (*abi_version)(void);
} kernel_registry_entry_t;

static const kernel_registry_entry_t KERNEL_REGISTRY[] = {
    {"car", car_init, car_process, car_teardown, car_abi_version},
    {"notch_iir", notch_iir_init, notch_iir_process, notch_iir_teardown, notch_iir_abi_version},
    {NULL, NULL, NULL, NULL, NULL}  /* Sentinel */
};

static const kernel_registry_entry_t* lookup_kernel(const char *id) {
    for (int i = 0; KERNEL_REGISTRY[i].id != NULL; i++) {
        if (strcmp(KERNEL_REGISTRY[i].id, id) == 0) {
            return &KERNEL_REGISTRY[i];
        }
    }
    return NULL;
}

/* In adapter_init(): */
if (cfg->kernel_id != NULL) {
    const kernel_registry_entry_t *entry = lookup_kernel(cfg->kernel_id);
    if (!entry) {
        return -6;  /* Kernel not found in registry */
    }

    adapter->kernel_abi_version = entry->abi_version;
    adapter->kernel_init = entry->init;
    adapter->kernel_process = entry->process;
    adapter->kernel_teardown = entry->teardown;
}
```

---

## Clock Source Examples

### Cycle Counter (ARM Cortex-M with DWT)

```c
#include <stdint.h>

#define DWT_CYCCNT   (*(volatile uint32_t *)0xE0001004)
#define DWT_CONTROL  (*(volatile uint32_t *)0xE0001000)
#define SCB_DEMCR    (*(volatile uint32_t *)0xE000EDFC)

static void dwt_init(void) {
    SCB_DEMCR |= 0x01000000;   /* Enable trace */
    DWT_CONTROL |= 1;          /* Enable CYCCNT */
}

static cortex_timestamp_t adapter_now(void *ctx) {
    (void)ctx;
    cortex_timestamp_t result;
    result.value = (uint64_t)DWT_CYCCNT;
    result.freq_hz = 180000000ULL;  /* 180 MHz CPU */
    result.source = "DWT_CYCCNT";
    return result;
}
```

### FPGA Free-Running Counter

```c
#define FPGA_TIMER_BASE 0x40000000
#define FPGA_TIMER_FREQ 100000000ULL  /* 100 MHz */

static cortex_timestamp_t adapter_now(void *ctx) {
    (void)ctx;
    volatile uint64_t *timer = (volatile uint64_t *)FPGA_TIMER_BASE;

    cortex_timestamp_t result;
    result.value = *timer;
    result.freq_hz = FPGA_TIMER_FREQ;
    result.source = "FPGA_TIMER";
    return result;
}
```

---

## Remote Adapter (TCP)

For running kernels on a different machine:

```c
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

typedef struct {
    int sockfd;
    size_t max_output_bytes;  /* Buffer capacity for bounds checking */
    /* ... additional fields ... */
} tcp_adapter_ctx_t;

static int32_t tcp_adapter_init(void *ctx, const cortex_adapter_config_t *cfg) {
    tcp_adapter_ctx_t *adapter = (tcp_adapter_ctx_t *)ctx;

    /* 1. Connect to remote adapter */
    /* WARNING: This example uses plain TCP without encryption or authentication.
     * Production deployments MUST use TLS, SSH tunnel, or VPN to protect
     * kernel data and prevent unauthorized execution. See PROTOCOL.md Security. */
    adapter->sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if (adapter->sockfd < 0) {
        return -6;  /* socket() failed */
    }

    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(9000);
    inet_pton(AF_INET, "192.168.1.100", &addr.sin_addr);

    if (connect(adapter->sockfd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(adapter->sockfd);
        return -6;  /* connect() failed */
    }

    /* 2. Receive HELLO message */
    cortex_hello_msg_t hello;
    recv_hello(adapter->sockfd, &hello);

    /* 3. Send LOAD_KERNEL message */
    cortex_load_kernel_msg_t load_msg = {0};
    /* ... populate from cfg ... */
    send_load_kernel(adapter->sockfd, &load_msg);

    /* 4. Receive init result and output buffer size */
    int32_t result;
    if (recv(adapter->sockfd, &result, sizeof(result), MSG_WAITALL) != sizeof(result)) {
        close(adapter->sockfd);
        return -6;  /* recv() failed */
    }
    if (result != 0) {
        close(adapter->sockfd);
        return result;
    }

    /* 5. Calculate and store maximum output buffer size for bounds checking */
    /* (Remote adapter would send output_channels, output_samples in INIT_RESULT) */
    size_t elem_size = cortex_dtype_size_bytes(cfg->dtype);
    size_t output_samples = cfg->window_length_samples;  /* Simplified: use config */
    size_t max_output_bytes;
    if (__builtin_mul_overflow(output_samples, cfg->channels, &max_output_bytes) ||
        __builtin_mul_overflow(max_output_bytes, elem_size, &max_output_bytes)) {
        close(adapter->sockfd);
        return -7;  /* Integer overflow */
    }
    adapter->max_output_bytes = max_output_bytes;

    return 0;
}

static int32_t tcp_adapter_process_window(void *ctx, const void *in, size_t in_bytes,
                                          cortex_adapter_result_t *out) {
    tcp_adapter_ctx_t *adapter = (tcp_adapter_ctx_t *)ctx;

    /* 1. Send PROCESS_WINDOW message */
    cortex_process_window_msg_t msg;
    msg.t_in = out->t_in;
    msg.input_bytes = (uint32_t)in_bytes;
    if (send(adapter->sockfd, &msg, sizeof(msg), 0) != sizeof(msg)) {
        return -6;  /* send() failed */
    }
    if (send(adapter->sockfd, in, in_bytes, 0) != (ssize_t)in_bytes) {
        return -6;  /* send() failed */
    }

    /* 2. Receive RESULT message */
    cortex_result_msg_t result_msg;
    if (recv(adapter->sockfd, &result_msg, sizeof(result_msg), MSG_WAITALL) != sizeof(result_msg)) {
        return -6;  /* recv() failed */
    }

    /* 3. CRITICAL: Validate output_bytes before receiving into buffer */
    if (result_msg.output_bytes > adapter->max_output_bytes) {
        /* Protocol violation: remote sent more data than buffer can hold */
        return -8;  /* Buffer overflow prevented */
    }

    /* 4. Receive output data with validated size */
    ssize_t received = recv(adapter->sockfd, out->output, result_msg.output_bytes, MSG_WAITALL);
    if (received != (ssize_t)result_msg.output_bytes) {
        return -6;  /* recv() incomplete */
    }

    out->output_bytes = result_msg.output_bytes;
    out->t_in = result_msg.t_in;
    out->t_start = result_msg.t_start;
    out->t_end = result_msg.t_end;
    out->deadline = result_msg.deadline;

    return 0;
}
```

See `PROTOCOL.md` for complete wire format specification.

---

## Testing Your Adapter

### Verification Checklist

- [ ] **ABI version check**: Reject mismatched `abi_version`
- [ ] **XOR constraint**: Enforce exactly one of `kernel_path`/`kernel_id` non-NULL
- [ ] **Dtype one-hot**: Validate using `cortex_dtype_size_bytes()`
- [ ] **Buffer allocation**: Allocate ONCE in init(), reuse in process_window()
- [ ] **Buffer lifetime**: Output valid until next process_window() OR cleanup()
- [ ] **Clock consistency**: All timestamps use same clock source (adapter->now())
- [ ] **t_in sentinel**: Handle `CORTEX_TIMESTAMP_ADAPTER_STAMPS` correctly
- [ ] **Capability flags**: Only set bits for implemented capabilities
- [ ] **Memory safety**: No leaks, proper cleanup on error paths

### Unit Test Example

```c
#include "cortex_adapter.h"
#include <assert.h>

void test_xor_constraint(void) {
    cortex_adapter_t adapter;
    cortex_adapter_get_v1(&adapter, sizeof(adapter));

    cortex_adapter_config_t cfg = {0};
    cfg.abi_version = CORTEX_ADAPTER_ABI_VERSION;

    /* Test 1: Both NULL - should fail early (no cleanup needed) */
    cfg.kernel_path = NULL;
    cfg.kernel_id = NULL;
    assert(adapter.init(adapter.context, &cfg) == -3);

    /* Test 2: Both non-NULL - should fail early (no cleanup needed) */
    cfg.kernel_path = "foo.so";
    cfg.kernel_id = "bar";
    assert(adapter.init(adapter.context, &cfg) == -3);

    /* Test 3: Exactly one - should succeed (assuming kernel exists) */
    cfg.kernel_path = "libnoop.so";
    cfg.kernel_id = NULL;
    assert(adapter.init(adapter.context, &cfg) == 0);

    /* IMPORTANT: Always cleanup after successful init */
    adapter.cleanup(adapter.context);

    /* NOTE: If testing multiple successful scenarios, cleanup is required
     * between each init() call to prevent resource leaks. Failed init() calls
     * that return early (before resource allocation) do not require cleanup. */
}
```

---

## Build Instructions

**Important**: All adapters MUST link the pre-built `cortex_adapter_abi.o` to export the ABI version symbol for dlsym() discovery.

### Linux (x86_64)
```bash
# Top-level Makefile builds the ABI object once
make -C /path/to/CORTEX primitives/adapters/v1/cortex_adapter_abi.o

# Link adapter with ABI object
gcc -shared -fPIC -o libcortex_adapter_native.so \
    adapter.c \
    ../cortex_adapter_abi.o \
    -I../../kernels/v1 -I. \
    -ldl -lm -lpthread
```

### macOS (arm64)
```bash
# Top-level Makefile builds the ABI object once
make -C /path/to/CORTEX primitives/adapters/v1/cortex_adapter_abi.o

# Link adapter with ABI object
clang -dynamiclib -fPIC -o libcortex_adapter_native.dylib \
    adapter.c \
    ../cortex_adapter_abi.o \
    -I../../kernels/v1 -I. \
    -lm -lpthread
```

### Cross-Compile (ARM Cortex-M7, bare-metal)
```bash
# Compile ABI object for target
arm-none-eabi-gcc -c -O2 -mcpu=cortex-m7 -mthumb \
    -I. \
    cortex_adapter_abi.c -o cortex_adapter_abi.o

# Compile adapter
arm-none-eabi-gcc -c -O2 -mcpu=cortex-m7 -mthumb \
    -I../../kernels/v1 -I. \
    adapter.c -o adapter.o

# Link together (for static linking in bare-metal)
arm-none-eabi-ar rcs libadapter.a adapter.o cortex_adapter_abi.o
```

---

## Further Reading

- **cortex_adapter.h**: Complete interface reference
- **PROTOCOL.md**: Wire format for remote adapters
- **cortex_plugin.h**: Kernel ABI interface (for ABI verification)
- **docs/architecture/device-adapters.md**: High-level design rationale (future)

---

## FAQ

**Q**: Do I need to implement all capability functions?
**A**: No. Only set capability bits for implemented features and provide corresponding function pointers.

**Q**: Can I allocate new buffers on every process_window() call?
**A**: You CAN, but it's inefficient. Best practice: allocate once in init(), reuse.

**Q**: What if my platform doesn't have CLOCK_MONOTONIC?
**A**: Use any monotonic clock source. Set `timestamp_freq_hz` and `source` fields appropriately in your `now()` implementation.

**Q**: Can I use kernel_path and kernel_id simultaneously?
**A**: NO. Exactly one must be non-NULL (XOR constraint). Violating this returns error -3.

**Q**: How do I test my adapter?
**A**: Start with the `noop` kernel (identity function). If that works, try `car`, then more complex kernels.

**Q**: What if init() fails halfway through?
**A**: Clean up all allocated resources before returning error code. Harness won't call cleanup() on init() failure.

**Q**: Can I change cortex_adapter_t.device_id after init()?
**A**: NO. All adapter identification fields (`device_id`, `arch`, `os`) are immutable after `cortex_adapter_get_v1()` returns.
