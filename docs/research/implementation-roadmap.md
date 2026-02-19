# CORTEX Implementation Roadmap: Research Synthesis

**Generated**: 2026-01-19
**Context**: Synthesis of prior art research mapped to capability table priorities

## Executive Summary

This document maps findings from three comprehensive research analyses to concrete CORTEX code changes:

- **prior-art-analysis.md** (26K words) - BCI/ML benchmarking tools
- **prior-art-expanded.md** (15K words) - Cross-domain systems benchmarking (9 domains)
- **halide-darkroom-analysis.md** (20K words) - Algorithm/schedule separation and pipeline composition

**Key Finding**: CORTEX already implements many advanced benchmarking patterns correctly. The roadmap focuses on:

1. **Extending existing infrastructure** (platform-state capture, deadline CLI)
2. **Adding new capabilities** (pipeline composition, comparative analysis)
3. **Documenting what already works** (algorithm/schedule separation)

---

## Research Validation: What CORTEX Already Does Right

### ✅ Coordinated Omission Resistance

**Research Finding** (prior-art-expanded.md):
- CORTEX does NOT suffer from Coordinated Omission (Gil Tene's measurement flaw)
- Window-based telemetry is time-independent, not request/response

**Validation**:
- `src/engine/harness/app/main.c` - Time-based window generation
- `src/engine/telemetry/telemetry.h:14` - `release_ts_ns` records every window
- No backoff on stalls - harness generates data at constant rate

**Action**: ✅ **No code changes needed** - document this in methodology section

---

### ✅ Algorithm/Schedule Separation (Halide Principle)

**Research Finding** (halide-darkroom-analysis.md):
- Halide separates WHAT (algorithm) from HOW (schedule/optimization)
- Enables portability + performance tuning

**Validation**:
- **Algorithm**: `primitives/kernels/v1/*/kernel.c` - Pure computation logic
- **Schedule**: `primitives/configs/cortex.yaml` - Runtime parameters (W, H, C, Fs)
- **Compilation**: `Makefile` - Compiler flags, vectorization (-march=native)

**Action**: ✅ **No code changes needed** - document this design principle

---

### ✅ Distributional Latency Reporting

**Research Finding** (prior-art-analysis.md):
- MLPerf Inference requires P50/P95/P99 reporting
- No BCI tool measures distributional latency

**Validation**:
- `src/engine/telemetry/telemetry.h` - Per-window latency recording
- Post-processing computes quantiles (P50, P95, P99)

**Action**: ✅ **No code changes needed** - CORTEX is already best-in-class for BCI

---

## Tier 1 Priorities: Must Build (4-9 weeks total)

### SE-9: Pipeline Composition (2-3 weeks)

**Business Value**: End-to-end latency for multi-stage BCI pipelines (bandpass → CAR → CSP)

#### Research Recommendation

**Source**: halide-darkroom-analysis.md

Use **Dark Room streaming model** (NOT Halide DAG):
- BCI pipelines are naturally sequential (no branching DAGs)
- Line-buffered execution: Window buffer → Stage 1 → Stage 2 → Stage 3
- Fast compilation (< 1 sec) vs Halide auto-scheduler (hours)

#### Current State

**Config structure** (`src/engine/harness/config/config.h:73`):
```c
cortex_plugin_entry_cfg_t plugins[CORTEX_MAX_PLUGINS];
```
- **Array of independent kernels**, not pipeline stages
- Batch mode runs kernels sequentially, no inter-stage buffers

**Execution** (`src/cortex/commands/run.py:417`):
```python
runner.run_all_kernels()  # Runs each kernel independently
```

#### Implementation Plan

**1. Extend Config Schema** (`primitives/configs/cortex.yaml`)

Add `pipeline:` section:
```yaml
pipeline:
  enabled: true
  stages:
    - name: "bandpass"
      kernel: "bandpass_fir"
      input: "dataset"
    - name: "spatial_filter"
      kernel: "car"
      input: "bandpass"
    - name: "classifier"
      kernel: "csp"
      input: "spatial_filter"
      output: "final"
```

**2. Extend Config Struct** (`src/engine/harness/config/config.h`)

Add after line 76:
```c
typedef struct cortex_pipeline_stage {
    char name[64];
    char kernel_name[64];
    char input_source[64];   /* "dataset" or previous stage name */
    char output_buffer[64];  /* Buffer identifier for next stage */
} cortex_pipeline_stage_t;

typedef struct cortex_pipeline_cfg {
    uint8_t enabled;
    cortex_pipeline_stage_t stages[CORTEX_MAX_PLUGINS];
    size_t stage_count;
} cortex_pipeline_cfg_t;
```

Add to `cortex_run_config_t`:
```c
cortex_pipeline_cfg_t pipeline;
```

**3. Implement Pipeline Orchestrator** (`src/engine/harness/pipeline/pipeline_executor.c` - NEW FILE)

```c
typedef struct pipeline_buffer {
    void *data;
    size_t size;
    uint32_t W, H, C;
} pipeline_buffer_t;

int cortex_pipeline_execute_window(
    const cortex_pipeline_cfg_t *pipeline,
    const uint8_t *input_window,
    cortex_telemetry_record_t *telem_out
) {
    pipeline_buffer_t buffers[CORTEX_MAX_PLUGINS];
    uint64_t pipeline_start_ns = cortex_now_ns();

    for (size_t i = 0; i < pipeline->stage_count; i++) {
        const cortex_pipeline_stage_t *stage = &pipeline->stages[i];

        // Resolve input buffer (dataset or previous stage output)
        pipeline_buffer_t *input = get_input_buffer(stage->input_source, buffers, i);

        // Execute kernel via adapter
        uint64_t stage_start_ns = cortex_now_ns();
        int ret = cortex_execute_kernel(stage->kernel_name, input, &buffers[i]);
        uint64_t stage_end_ns = cortex_now_ns();

        if (ret != 0) return -1;

        // Record stage-level telemetry (optional)
        log_stage_timing(stage->name, stage_start_ns, stage_end_ns);
    }

    uint64_t pipeline_end_ns = cortex_now_ns();

    // Populate telemetry with end-to-end timing
    telem_out->start_ts_ns = pipeline_start_ns;
    telem_out->end_ts_ns = pipeline_end_ns;
    strcpy(telem_out->plugin_name, "pipeline");  // Special marker

    return 0;
}
```

**4. Extend Telemetry** (`src/engine/telemetry/telemetry.h`)

Add pipeline-level fields after line 32:
```c
/* Pipeline execution metadata (only populated if pipeline.enabled = true) */
uint8_t is_pipeline;           /* 1 if this record is for pipeline execution */
uint32_t pipeline_stage_count; /* Number of stages executed */
char pipeline_stages[256];     /* Comma-separated stage names (e.g., "bandpass,car,csp") */
```

**5. Add CLI Command** (`src/cortex/commands/pipeline.py` - ALREADY EXISTS!)

Update to support pipeline execution:
```python
def execute_pipeline(config_path, run_name, verbose=False):
    """Execute multi-stage pipeline with end-to-end telemetry"""
    # Check if config has pipeline.enabled = true
    # Generate run config with pipeline orchestration
    # Invoke harness with --pipeline flag
```

#### Testing

**Unit Tests**:
- `tests/engine/test_pipeline_executor.c` - Stage chaining, buffer management
- `tests/engine/test_pipeline_telemetry.c` - End-to-end timing accuracy

**Integration Test**:
```bash
cortex pipeline --config primitives/configs/pipeline-example.yaml \
  --duration 10 --repeats 1 --warmup 0
```

Expected output:
```
Pipeline: bandpass → car → csp
End-to-end P50 latency: 8.3 ms
Stage breakdown:
  bandpass: 2.1 ms
  car:      3.5 ms
  csp:      2.7 ms
```

#### Files to Create/Modify

| File | Action | Lines |
|------|--------|-------|
| `src/engine/harness/pipeline/pipeline_executor.{c,h}` | CREATE | ~300 |
| `src/engine/harness/config/config.h` | MODIFY | +25 |
| `src/engine/telemetry/telemetry.h` | MODIFY | +3 |
| `src/cortex/commands/pipeline.py` | MODIFY | +50 |
| `primitives/configs/pipeline-example.yaml` | CREATE | ~40 |
| `tests/engine/test_pipeline_executor.c` | CREATE | ~200 |

**Total Effort**: 2-3 weeks (implementation + testing + docs)

---

### SE-7: Device Adapters USB/ADB (4-6 weeks)

**Business Value**: Enable edge devices (Jetson, phones, wearables) for real-world BCI testing

#### Research Recommendation

**Source**: prior-art-expanded.md

Reuse existing deployment patterns:
- **ADB**: Android Debug Bridge CLI for phones/tablets
- **USB Serial**: UART transport for microcontrollers
- **Adapter Protocol**: CORTEX already has device_comm.h protocol

#### Current State

**Adapter Interface** (`src/engine/harness/device/device_comm.h`):
```c
// Protocol: HELLO → CONFIG → ACK → loop: WINDOW → RESULT
```
- ✅ Transport abstraction already exists (local, TCP, UART)
- ✅ Native adapter implemented (`primitives/adapters/v1/native/adapter.c`)

**Missing**: Auto-deployment to edge devices (USB, ADB)

#### Implementation Plan

**1. ADB Deployer** (`src/cortex/deploy/adb_deployer.py` - NEW FILE)

```python
class ADBDeployer(Deployer):
    """Deploy CORTEX adapter to Android device via ADB"""

    def deploy(self, verbose=False, skip_validation=False):
        # 1. Check adb devices
        # 2. Push adapter binary: adb push adapter /data/local/tmp/
        # 3. Set execute permissions: adb shell chmod +x /data/local/tmp/adapter
        # 4. Start adapter: adb shell /data/local/tmp/adapter --port 9000
        # 5. Forward port: adb forward tcp:9000 tcp:9000
        # 6. Return transport URI: tcp://127.0.0.1:9000
```

**2. USB Serial Deployer** (`src/cortex/deploy/usb_deployer.py` - NEW FILE)

```python
class USBDeployer(Deployer):
    """Deploy CORTEX adapter to microcontroller via USB serial"""

    def deploy(self, verbose=False, skip_validation=False):
        # 1. Detect USB device: /dev/ttyUSB0 or /dev/cu.usbserial-*
        # 2. Flash firmware (if needed): esptool.py or platform-specific
        # 3. Wait for boot handshake
        # 4. Return transport URI: uart:///dev/ttyUSB0?baud=115200
```

**3. Device String Parsing** (`src/cortex/deploy/factory.py:21`)

Extend `DeployerFactory.from_device_string()`:
```python
# Current: nvidia@192.168.1.123 | tcp://... | local://
# Add:
#   android@<serial>     → ADBDeployer
#   usb://<port>         → USBDeployer
#   jetson@<ip>          → NVIDIADeployer (reuse SSH)
```

**4. UART Transport** (`sdk/adapter/lib/transport/uart.c` - NEW FILE)

Implement UART transport for `src/engine/harness/device/device_comm.c`:
```c
int cortex_transport_uart_init(const char *device, uint32_t baud_rate);
int cortex_transport_uart_send(const void *data, size_t len);
int cortex_transport_uart_recv(void *buf, size_t len, uint32_t timeout_ms);
```

Platform-specific implementations:
- Linux: `/dev/ttyUSB0` via termios
- macOS: `/dev/cu.usbserial-*` via IOKit
- Windows: `COM3` via Win32 API

#### Testing

**ADB Test**:
```bash
# 1. Connect Android phone via USB
adb devices

# 2. Deploy and run
cortex run --kernel noop --device android@<serial> --duration 10
```

**USB Test**:
```bash
# 1. Connect Arduino/ESP32 via USB
ls /dev/ttyUSB*

# 2. Deploy and run
cortex run --kernel noop --device usb:///dev/ttyUSB0 --duration 10
```

#### Files to Create/Modify

| File | Action | Lines |
|------|--------|-------|
| `src/cortex/deploy/adb_deployer.py` | CREATE | ~200 |
| `src/cortex/deploy/usb_deployer.py` | CREATE | ~150 |
| `src/cortex/deploy/factory.py` | MODIFY | +20 |
| `sdk/adapter/lib/transport/uart.c` | CREATE | ~300 |
| `sdk/adapter/lib/transport/uart.h` | CREATE | ~30 |
| `tests/deploy/test_adb_deployer.py` | CREATE | ~100 |
| `docs/user-guide/edge-deployment.md` | CREATE | ~800 |

**Total Effort**: 4-6 weeks (cross-platform testing is time-intensive)

---

## Tier 2 Priorities: Should Build (5-6 weeks total)

### SE-5 + SE-8: Platform-State Capture (2 weeks)

**Business Value**: Cross-platform benchmark fairness (EEMBC requirement)

#### Research Recommendation

**Source**: prior-art-expanded.md

EEMBC CoreMark mandates reporting:
- Compiler version and flags
- CPU governor (performance/powersave/ondemand)
- CPU frequency (current/max)
- Turbo boost state

For advanced profiling (Linux only):
- eBPF for context switches, cache misses
- perf stat integration

#### Current State

**Telemetry** (`src/engine/telemetry/telemetry.h:42-54`):
```c
typedef struct cortex_system_info {
    char os[64];
    char cpu_model[128];
    char hostname[64];
    uint64_t total_ram_mb;
    uint32_t cpu_count;
    float thermal_celsius;  // ✅ Already captured

    // Device fields also exist
} cortex_system_info_t;
```

**Config** (`primitives/configs/cortex.yaml:21-23`):
```yaml
power:
  governor: "performance"  # ❌ Documented but NOT enforced
  turbo: false
```

**Missing**:
- CPU governor/frequency not captured in telemetry
- Compiler version not recorded
- No runtime governor enforcement

#### Implementation Plan

**1. Extend Telemetry Struct** (`src/engine/telemetry/telemetry.h:54`)

Add after line 53:
```c
/* Platform state (EEMBC cross-platform fairness) */
char compiler_name[64];      /* "gcc 13.2.0", "clang 15.0.7" */
char compiler_flags[256];    /* "-O3 -march=native -ffast-math" */
char cpu_governor[32];       /* "performance", "powersave", "ondemand" (Linux) */
uint32_t cpu_freq_mhz;       /* Current CPU frequency */
uint32_t cpu_freq_max_mhz;   /* Maximum CPU frequency */
uint8_t turbo_enabled;       /* Turbo boost state (0/1) */
```

**2. Implement Platform Detection** (`src/engine/telemetry/platform_state.c` - NEW FILE)

```c
int cortex_get_cpu_governor(char *gov, size_t len) {
#ifdef __linux__
    // Read /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
    FILE *f = fopen("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "r");
    if (f) {
        fgets(gov, len, f);
        fclose(f);
        return 0;
    }
#elif __APPLE__
    // macOS doesn't expose governor - return "managed"
    strncpy(gov, "managed", len);
    return 0;
#endif
    return -1;
}

int cortex_get_cpu_frequency(uint32_t *freq_mhz, uint32_t *max_freq_mhz) {
#ifdef __linux__
    // Read /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
    // Read /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq
#elif __APPLE__
    // macOS: sysctl hw.cpufrequency_max
    size_t len = sizeof(uint64_t);
    uint64_t freq_hz;
    sysctlbyname("hw.cpufrequency_max", &freq_hz, &len, NULL, 0);
    *max_freq_mhz = freq_hz / 1000000;
    *freq_mhz = *max_freq_mhz;  // macOS doesn't expose current
    return 0;
#endif
    return -1;
}
```

**3. Capture Compiler Info at Build Time** (`Makefile`)

Add after build:
```makefile
COMPILER_INFO := $(shell $(CC) --version | head -1)
CFLAGS_RECORDED := $(CFLAGS)

# Write to generated header
echo "#define CORTEX_COMPILER \"$(COMPILER_INFO)\"" > src/engine/build_info.h
echo "#define CORTEX_CFLAGS \"$(CFLAGS_RECORDED)\"" >> src/engine/build_info.h
```

Include in harness:
```c
#include "build_info.h"
strncpy(sysinfo->compiler_name, CORTEX_COMPILER, 64);
strncpy(sysinfo->compiler_flags, CORTEX_CFLAGS, 256);
```

**4. Runtime Governor Enforcement** (`src/engine/harness/app/main.c`)

Add before benchmark starts:
```c
int cortex_enforce_governor(const char *requested_governor) {
#ifdef __linux__
    char current_gov[32];
    cortex_get_cpu_governor(current_gov, sizeof(current_gov));

    if (strcmp(current_gov, requested_governor) != 0) {
        fprintf(stderr, "WARNING: CPU governor is '%s', expected '%s'\n",
                current_gov, requested_governor);
        fprintf(stderr, "Set with: echo %s | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor\n",
                requested_governor);
        return -1;  // Fail benchmark if mismatch
    }
#endif
    return 0;
}
```

#### eBPF Integration (Future - v1.0+)

For Linux profiling:
```c
// Attach eBPF probes to track:
// - Context switches (sched:sched_switch)
// - LLC misses (perf:cache-misses)
// - Interrupts (irq:irq_handler_entry)

int cortex_ebpf_attach(void);
int cortex_ebpf_collect_stats(cortex_ebpf_stats_t *stats);
```

**Defer to v1.0+**: Requires libbpf, BCC, kernel version checks

#### Testing

**Verification**:
```bash
# 1. Run benchmark
cortex run --kernel noop --duration 10

# 2. Check telemetry output
cat results/run-2026-01-19-001/telemetry.ndjson | jq .system_info

# Expected output:
{
  "compiler_name": "gcc 13.2.0",
  "compiler_flags": "-O3 -march=native",
  "cpu_governor": "performance",
  "cpu_freq_mhz": 3500,
  "cpu_freq_max_mhz": 3500,
  "turbo_enabled": 0
}
```

**Governor enforcement test**:
```bash
# 1. Set governor to powersave
echo powersave | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# 2. Try to run benchmark
cortex run --kernel noop

# Expected: ERROR with instructions to set performance governor
```

#### Files to Create/Modify

| File | Action | Lines |
|------|--------|-------|
| `src/engine/telemetry/telemetry.h` | MODIFY | +7 |
| `src/engine/telemetry/platform_state.{c,h}` | CREATE | ~200 |
| `Makefile` | MODIFY | +10 |
| `src/engine/harness/app/main.c` | MODIFY | +30 |
| `tests/engine/test_platform_state.c` | CREATE | ~100 |

**Total Effort**: 2 weeks (cross-platform testing for macOS/Linux/Windows)

---

### SE-1: Deadline Analysis CLI (1 week)

**Business Value**: Formal real-time analysis for safety-critical BCI applications

#### Research Recommendation

**Source**: prior-art-expanded.md

LTTng snapshot methodology:
- Capture platform events during deadline violations
- Trace context switches, interrupts during missed windows
- Identify root cause (scheduler preemption vs kernel overload)

#### Current State

**Infrastructure Exists**:
- Config: `src/engine/harness/config/config.h:47` - `uint32_t deadline_ms`
- Telemetry: `src/engine/telemetry/telemetry.h:17` - `uint8_t deadline_missed`

**Missing**: CLI command to analyze deadline violations

#### Implementation Plan

**1. Add CLI Command** (`src/cortex/commands/check_deadline.py` - NEW FILE)

```python
def execute(args):
    """Analyze deadline violations from telemetry data"""

    # 1. Load telemetry.ndjson
    df = pd.read_json(args.telemetry_path, lines=True)

    # 2. Calculate deadline violations
    df['latency_ms'] = (df['end_ts_ns'] - df['start_ts_ns']) / 1e6
    violations = df[df['deadline_missed'] == 1]

    # 3. Statistical analysis
    total_windows = len(df)
    violation_count = len(violations)
    violation_rate = violation_count / total_windows * 100

    # 4. Report
    print(f"Deadline Analysis Report")
    print(f"========================")
    print(f"Total windows:       {total_windows}")
    print(f"Deadline violations: {violation_count} ({violation_rate:.2f}%)")
    print(f"Worst-case latency:  {df['latency_ms'].max():.2f} ms")
    print(f"Deadline target:     {df['deadline_ts_ns'].iloc[0] / 1e6:.2f} ms")

    # 5. Scatter plot (optional)
    if args.plot:
        import matplotlib.pyplot as plt
        plt.scatter(df.index, df['latency_ms'],
                    c=df['deadline_missed'], cmap='RdYlGn_r')
        plt.axhline(df['deadline_ts_ns'].iloc[0] / 1e6,
                    color='r', linestyle='--', label='Deadline')
        plt.xlabel('Window Index')
        plt.ylabel('Latency (ms)')
        plt.title('Real-Time Deadline Analysis')
        plt.legend()
        plt.savefig('deadline_analysis.png')
        print("Plot saved: deadline_analysis.png")

    return 0 if violation_rate == 0 else 1
```

**2. CLI Integration** (`src/cortex/__init__.py`)

Add command registration:
```python
from cortex.commands import check_deadline

parser_deadline = subparsers.add_parser('check-deadline',
    help='Analyze real-time deadline violations')
check_deadline.setup_parser(parser_deadline)
```

#### Usage

```bash
# Basic analysis
cortex check-deadline results/run-2026-01-19-001/telemetry.ndjson

# With visualization
cortex check-deadline results/run-2026-01-19-001/telemetry.ndjson --plot
```

**Expected Output**:
```
Deadline Analysis Report
========================
Total windows:       1200
Deadline violations: 3 (0.25%)
Worst-case latency:  12.3 ms
Deadline target:     10.0 ms

Violations:
  Window 235: 11.2 ms (12% overrun)
  Window 487: 10.8 ms (8% overrun)
  Window 891: 12.3 ms (23% overrun)
```

#### Advanced: LTTng Integration (Future)

For root cause analysis:
```bash
# 1. Start LTTng tracing
lttng create cortex-deadline
lttng enable-event -k sched_switch,irq_handler_entry
lttng start

# 2. Run benchmark
cortex run --kernel goertzel --duration 10

# 3. Analyze trace
lttng stop
babeltrace2 ~/lttng-traces/cortex-deadline | grep "window_891"
```

**Defer to v1.0+**: Requires LTTng setup, kernel tracepoints

#### Files to Create/Modify

| File | Action | Lines |
|------|--------|-------|
| `src/cortex/commands/check_deadline.py` | CREATE | ~100 |
| `src/cortex/__init__.py` | MODIFY | +5 |
| `docs/user-guide/deadline-analysis.md` | CREATE | ~600 |

**Total Effort**: 1 week (implementation + docs + testing)

---

### SE-2 + HE-1: Comparative Analysis CLI (1 week)

**Business Value**: CI regression detection and A/B testing for kernel optimizations

#### Research Recommendation

**Source**: prior-art-expanded.md

CI regression patterns:
- Statistical significance testing (t-test, Mann-Whitney U)
- Effect size calculation (Cohen's d)
- Baseline tagging and automatic detection

#### Current State

**Plotting exists**: `src/cortex/commands/analyze.py` - Generates comparison plots

**Missing**:
- Formal statistical testing
- Baseline management
- CLI `cortex compare` command

#### Implementation Plan

**1. Add CLI Command** (`src/cortex/commands/compare.py` - NEW FILE)

```python
def execute(args):
    """Compare two benchmark runs statistically"""

    # 1. Load baseline and current run
    baseline_df = pd.read_json(args.baseline, lines=True)
    current_df = pd.read_json(args.current, lines=True)

    # 2. Statistical tests
    from scipy import stats

    baseline_latency = baseline_df['end_ts_ns'] - baseline_df['start_ts_ns']
    current_latency = current_df['end_ts_ns'] - current_df['start_ts_ns']

    # t-test for mean difference
    t_stat, p_value = stats.ttest_ind(baseline_latency, current_latency)

    # Effect size (Cohen's d)
    mean_diff = current_latency.mean() - baseline_latency.mean()
    pooled_std = np.sqrt((baseline_latency.std()**2 + current_latency.std()**2) / 2)
    cohens_d = mean_diff / pooled_std

    # 3. Regression detection
    regression = False
    if p_value < 0.05 and cohens_d > 0.2:  # Significant + small effect
        regression = True

    # 4. Report
    print(f"Comparative Analysis Report")
    print(f"===========================")
    print(f"Baseline: {args.baseline}")
    print(f"Current:  {args.current}")
    print()
    print(f"Baseline P50: {baseline_latency.quantile(0.5) / 1e6:.2f} ms")
    print(f"Current P50:  {current_latency.quantile(0.5) / 1e6:.2f} ms")
    print(f"Difference:   {mean_diff / 1e6:.2f} ms ({mean_diff / baseline_latency.mean() * 100:.1f}%)")
    print()
    print(f"Statistical Significance:")
    print(f"  t-statistic: {t_stat:.3f}")
    print(f"  p-value:     {p_value:.4f} {'(significant)' if p_value < 0.05 else ''}")
    print(f"  Cohen's d:   {cohens_d:.3f} ({'small' if abs(cohens_d) < 0.5 else 'medium' if abs(cohens_d) < 0.8 else 'large'} effect)")
    print()

    if regression:
        print("⚠️  REGRESSION DETECTED")
        return 1
    else:
        print("✓ No significant regression")
        return 0
```

**2. Baseline Management** (`src/cortex/utils/baseline.py` - NEW FILE)

```python
def set_baseline(run_name):
    """Tag a run as the baseline for future comparisons"""
    baseline_path = Path("results/.baseline")
    baseline_path.write_text(run_name)
    print(f"✓ Baseline set: {run_name}")

def get_baseline():
    """Get the current baseline run name"""
    baseline_path = Path("results/.baseline")
    if baseline_path.exists():
        return baseline_path.read_text().strip()
    return None
```

**3. CI Integration Example** (`.github/workflows/benchmark.yml`)

```yaml
name: Benchmark CI

on: [push, pull_request]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build CORTEX
        run: make

      - name: Run benchmark
        run: cortex run --kernel goertzel --duration 10 --repeats 1

      - name: Compare to baseline
        run: |
          cortex compare \
            --baseline results/baseline/telemetry.ndjson \
            --current results/run-*/telemetry.ndjson \
            --fail-on-regression

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: benchmark-results
          path: results/
```

#### Usage

```bash
# 1. Set baseline
cortex run --kernel goertzel --duration 60 --repeats 5
cortex baseline set results/run-2026-01-19-001

# 2. Make code changes
# ... edit kernel.c ...

# 3. Compare
cortex run --kernel goertzel --duration 60 --repeats 5
cortex compare \
  --baseline results/run-2026-01-19-001/telemetry.ndjson \
  --current results/run-2026-01-19-002/telemetry.ndjson
```

#### Files to Create/Modify

| File | Action | Lines |
|------|--------|-------|
| `src/cortex/commands/compare.py` | CREATE | ~150 |
| `src/cortex/utils/baseline.py` | CREATE | ~50 |
| `src/cortex/__init__.py` | MODIFY | +5 |
| `.github/workflows/benchmark.yml` | CREATE | ~40 |

**Total Effort**: 1 week

---

### SE-3: Multi-Dtype Fixed16 (2-3 weeks)

**Business Value**: Test performance/accuracy tradeoffs for embedded deployment

#### Research Recommendation

**Source**: prior-art-expanded.md

BLAS/LAPACK validation approach:
- Scaled tolerance testing: `|result - reference| / |reference| < ε`
- Document expected degradation (e.g., "Q15 introduces 0.01% RMS error")

#### Current State

**API exists** (`sdk/kernel/include/cortex_abi_v3.h`):
```c
typedef enum {
    CORTEX_DTYPE_FLOAT32 = 0x01,
    CORTEX_DTYPE_FLOAT64 = 0x02,
    CORTEX_DTYPE_INT16   = 0x04,  // Q15 fixed-point
    CORTEX_DTYPE_INT32   = 0x08
} cortex_dtype_bitmask_t;
```

**Missing**:
- No Q15 kernel implementations
- No degradation analysis tools

#### Implementation Plan

**1. Implement Q15 Kernels** (`primitives/kernels/v1/*/kernel_q15.c`)

Example for bandpass FIR:
```c
#include <arm_math.h>  // CMSIS-DSP Q15 functions

int cortex_kernel_init_q15(const char *params, void **state_out) {
    // Allocate Q15 filter state
    fir_q15_state_t *state = malloc(sizeof(fir_q15_state_t));
    arm_fir_init_q15(&state->instance, NUM_TAPS, coeffs_q15, state->buffer, BLOCK_SIZE);
    *state_out = state;
    return 0;
}

int cortex_kernel_process_q15(void *state, const int16_t *input, int16_t *output,
                               uint32_t W, uint32_t H, uint32_t C) {
    fir_q15_state_t *s = (fir_q15_state_t *)state;
    arm_fir_q15(&s->instance, (q15_t *)input, (q15_t *)output, W);
    return 0;
}
```

**2. Add Degradation Metrics** (`src/cortex/commands/validate.py`)

```python
def compare_dtypes(kernel_name, float32_output, q15_output):
    """Compare Q15 vs FP32 accuracy"""

    # 1. Load oracle outputs
    ref = np.load(f"primitives/kernels/v1/{kernel_name}/oracle_output.npy")

    # 2. Calculate errors
    fp32_error = np.abs(float32_output - ref) / np.abs(ref)
    q15_error = np.abs(q15_output - ref) / np.abs(ref)

    # 3. Report
    print(f"Accuracy Analysis: {kernel_name}")
    print(f"FP32 RMS error: {np.sqrt(np.mean(fp32_error**2)):.6f}")
    print(f"Q15 RMS error:  {np.sqrt(np.mean(q15_error**2)):.6f}")
    print(f"Degradation:    {np.sqrt(np.mean(q15_error**2)) - np.sqrt(np.mean(fp32_error**2)):.6f}")
```

**3. Multi-Dtype Benchmarking** (`primitives/configs/dtype-comparison.yaml`)

```yaml
plugins:
  - name: "bandpass_fp32"
    spec_uri: "primitives/kernels/v1/bandpass_fir/spec.yaml"
    runtime:
      dtype: 1  # FLOAT32

  - name: "bandpass_q15"
    spec_uri: "primitives/kernels/v1/bandpass_fir/spec.yaml"
    runtime:
      dtype: 4  # INT16 (Q15)
```

#### Testing

```bash
# 1. Run dtype comparison
cortex run --config primitives/configs/dtype-comparison.yaml

# 2. Analyze results
cortex compare \
  --baseline results/run-*/bandpass_fp32/telemetry.ndjson \
  --current results/run-*/bandpass_q15/telemetry.ndjson

# Expected: Q15 is 2-4x faster but 0.01% accuracy loss
```

#### Files to Create/Modify

| File | Action | Lines |
|------|--------|-------|
| `primitives/kernels/v1/bandpass_fir/kernel_q15.c` | CREATE | ~200 |
| `primitives/kernels/v1/car/kernel_q15.c` | CREATE | ~150 |
| `primitives/kernels/v1/goertzel/kernel_q15.c` | CREATE | ~180 |
| `src/cortex/commands/validate.py` | MODIFY | +50 |
| `primitives/configs/dtype-comparison.yaml` | CREATE | ~60 |

**Total Effort**: 2-3 weeks (Q15 math is tricky, needs validation)

---

### SE-4 (NEW): Latency Decomposition via Static Analysis (2-3 weeks)

**Business Value**: Identify performance bottlenecks (compute vs memory vs I/O vs cache) to guide optimization

#### Research Recommendation

**Source**: prior-art-analysis.md (Section 11: Diagnostic Framework)

**Roofline Model Methodology**:
1. **Static analysis** → theoretical FLOPs, memory accesses
2. **Device spec** → peak FLOPS, memory bandwidth, cache sizes
3. **Measured latency** → ground truth from telemetry
4. **Decomposition** → attribute latency to: compute, memory, I/O, cache, scheduler

**Prior Art**:
- **Intel Advisor** - Auto-roofline for CPU/GPU kernels
- **NVIDIA Nsight Compute** - Bottleneck attribution (SM vs memory vs L2)
- **LIKWID** - Combines hardware counters with roofline model
- **ARM Streamline** - Mobile profiling with static analysis

**Key Insight**: Combine **theoretical bounds** (static) with **measured performance** (dynamic) to infer bottleneck sources.

#### Current State

**Dynamic measurement exists**:
- `src/engine/telemetry/telemetry.h` - Per-window end-to-end latency
- `device_tstart_ns`, `device_tend_ns` - Device-side timing

**Missing**:
- Static analysis of kernels (operation count, memory footprint)
- Device capability database (peak FLOPS, bandwidth)
- Decomposition algorithm

#### Implementation Plan

**1. Static Analyzer** (`sdk/kernel/tools/cortex_analyze_kernel.py` - NEW FILE)

Parse kernel C code to extract:
- **Operation count**: Multiply-accumulates, FLOPs
- **Memory accesses**: Input/output bytes, intermediate buffers
- **Cache footprint**: Working set size
- **Arithmetic intensity**: FLOPs / bytes (roofline metric)

Example output:
```python
def analyze_kernel(kernel_path, W, H, C):
    """Static analysis of kernel computational requirements"""

    # Parse kernel.c using pycparser or regex
    ops = count_operations(kernel_path)  # FIR: W * num_taps * C MACs

    input_bytes = W * H * C * 4  # float32
    output_bytes = W * C * 4
    working_set_bytes = estimate_cache_footprint(kernel_path)

    return {
        'operations': ops,
        'flops': ops * 2,  # MAC = multiply + add
        'input_bytes': input_bytes,
        'output_bytes': output_bytes,
        'working_set_bytes': working_set_bytes,
        'arithmetic_intensity': ops * 2 / (input_bytes + output_bytes)
    }
```

**2. Device Capability Database** (`src/cortex/device_specs.yaml` - NEW FILE)

```yaml
# Per-device computational limits
devices:
  - name: "Apple M1"
    cpu_model: "Apple M1"
    cores: 8
    peak_gflops: 2600  # 8 cores * 3.2 GHz * 8-wide NEON * 2 (FMA) / 1000
    memory_bandwidth_gbps: 68.25
    l1_cache_kb: 192  # Per-core
    l2_cache_mb: 12
    l3_cache_mb: 8  # Shared

  - name: "Snapdragon 888"
    cpu_model: "Snapdragon 888"
    cores: 8
    peak_gflops: 480  # Cortex-X1 + A78 + A55
    memory_bandwidth_gbps: 51.2
    l1_cache_kb: 128
    l2_cache_mb: 8
    l3_cache_mb: 4

  - name: "Intel i7-12700K"
    cpu_model: "12th Gen Intel Core i7-12700K"
    cores: 12
    peak_gflops: 1536  # P-cores with AVX2
    memory_bandwidth_gbps: 76.8  # DDR5-4800
    l1_cache_kb: 960
    l2_cache_mb: 12
    l3_cache_mb: 25
```

Auto-detection:
```python
def detect_device_spec(cpu_model):
    """Match telemetry cpu_model to device spec database"""
    specs = load_yaml("src/cortex/device_specs.yaml")
    for device in specs['devices']:
        if device['cpu_model'] in cpu_model:
            return device
    return None  # Use conservative defaults
```

**3. Decomposition Algorithm** (`src/cortex/commands/diagnose.py` - NEW FILE)

```python
def decompose_latency(telemetry_record, kernel_analysis, device_spec):
    """Decompose measured latency into components"""

    measured_ns = telemetry_record['end_ts_ns'] - telemetry_record['start_ts_ns']

    # 1. Theoretical compute time (lower bound)
    flops_required = kernel_analysis['flops']
    peak_gflops = device_spec['peak_gflops']
    theoretical_compute_ns = (flops_required / (peak_gflops * 1e9)) * 1e9

    # 2. Theoretical memory time (if memory-bound)
    bytes_transferred = kernel_analysis['input_bytes'] + kernel_analysis['output_bytes']
    bandwidth_gbps = device_spec['memory_bandwidth_gbps']
    theoretical_memory_ns = (bytes_transferred / (bandwidth_gbps * 1e9)) * 1e9

    # 3. Roofline prediction
    arithmetic_intensity = kernel_analysis['arithmetic_intensity']
    machine_balance = peak_gflops / bandwidth_gbps  # FLOP/byte at balance point

    if arithmetic_intensity < machine_balance:
        # Memory-bound
        predicted_ns = theoretical_memory_ns
        bottleneck = "memory"
    else:
        # Compute-bound
        predicted_ns = theoretical_compute_ns
        bottleneck = "compute"

    # 4. I/O overhead (adapter protocol)
    io_overhead_ns = 0
    if 'device_tin_ns' in telemetry_record:
        # Time between harness start and device input complete
        io_overhead_ns = telemetry_record['device_tin_ns'] - telemetry_record['start_ts_ns']

    # 5. Cache effects (inferred from working set vs cache size)
    cache_penalty_ns = 0
    working_set_mb = kernel_analysis['working_set_bytes'] / (1024 * 1024)
    if working_set_mb > device_spec['l3_cache_mb']:
        # Working set exceeds L3 → DRAM latency penalty
        # Estimate: Extra cycles for cache misses
        cache_miss_rate = estimate_cache_miss_rate(working_set_mb, device_spec)
        cache_penalty_ns = measured_ns * cache_miss_rate * 0.1  # Heuristic

    # 6. Scheduler/OS overhead (residual)
    compute_ns = max(theoretical_compute_ns, predicted_ns * 0.8)  # Account for non-peak execution
    memory_ns = theoretical_memory_ns if bottleneck == "memory" else 0
    scheduler_ns = measured_ns - compute_ns - memory_ns - io_overhead_ns - cache_penalty_ns

    # Ensure non-negative
    scheduler_ns = max(0, scheduler_ns)

    return {
        'measured_ns': measured_ns,
        'theoretical_compute_ns': theoretical_compute_ns,
        'theoretical_memory_ns': theoretical_memory_ns,
        'bottleneck': bottleneck,
        'decomposition': {
            'compute_ns': compute_ns,
            'memory_ns': memory_ns,
            'io_overhead_ns': io_overhead_ns,
            'cache_penalty_ns': cache_penalty_ns,
            'scheduler_ns': scheduler_ns
        },
        'efficiency': predicted_ns / measured_ns  # How close to theoretical limit
    }
```

**4. CLI Command**

```bash
cortex diagnose results/run-2026-01-19-001/telemetry.ndjson \
  --kernel bandpass_fir \
  --plot
```

**Output**:
```
Latency Decomposition Report: bandpass_fir
==========================================

Configuration:
  Window: 256 samples
  Channels: 64
  FIR taps: 128

Device: Apple M1 (8 cores, 2600 GFLOPS, 68.25 GB/s)

Static Analysis:
  Operations:     2,097,152 (256 * 128 * 64 MACs)
  FLOPs:          4,194,304 (2 ops per MAC)
  Input bytes:    65,536 (256 * 64 * 4)
  Output bytes:   65,536
  Working set:    512 KB (state + coefficients)
  Arithmetic intensity: 32.0 FLOP/byte

Roofline Analysis:
  Machine balance: 38.1 FLOP/byte (2600 GFLOPS / 68.25 GB/s)
  Kernel intensity: 32.0 FLOP/byte
  Bottleneck: MEMORY-BOUND ⚠️  (intensity < balance)

Theoretical Bounds:
  Theoretical compute time: 1.61 ms (100% core utilization)
  Theoretical memory time:  1.92 ms (100% bandwidth)
  Predicted (memory-bound): 1.92 ms

Measured Performance (P50):
  End-to-end latency: 4.8 ms
  Efficiency: 40% (predicted / measured)

Latency Breakdown:
  ┌─────────────────────────────────────────────┐
  │ Compute:   1.8 ms ███████░░░░░░░░░░░░░░░░░░ │ 38%
  │ Memory:    1.9 ms ████████░░░░░░░░░░░░░░░░░ │ 40%
  │ I/O:       0.3 ms █░░░░░░░░░░░░░░░░░░░░░░░░ │  6%
  │ Cache:     0.2 ms █░░░░░░░░░░░░░░░░░░░░░░░░ │  4%
  │ Scheduler: 0.6 ms ██░░░░░░░░░░░░░░░░░░░░░░░ │ 12%
  └─────────────────────────────────────────────┘
  Total:     4.8 ms ███████████████████████████ 100%

Optimization Recommendations:
  1. MEMORY-BOUND: Reduce memory traffic
     - Increase tile size to improve cache locality
     - Use SIMD intrinsics to reduce load/store count
     - Consider blocked FIR algorithm

  2. LOW EFFICIENCY (40%): System overhead detected
     - Check CPU governor (should be 'performance')
     - Reduce scheduler overhead (increase priority, affinity)
     - Profile with perf stat to identify context switches

  3. CACHE PENALTY: Working set (512 KB) fits in L2
     - No L3 cache misses expected
     - Consider prefetching for streaming data
```

**5. Visualization**

Roofline plot:
```python
import matplotlib.pyplot as plt

def plot_roofline(device_spec, kernel_analysis, measured_latency):
    # Roofline ceiling lines
    peak_gflops = device_spec['peak_gflops']
    bandwidth_gbps = device_spec['memory_bandwidth_gbps']

    # Operational intensity range
    intensity = np.logspace(-2, 3, 100)  # 0.01 to 1000 FLOP/byte

    # Compute roof
    compute_roof = np.full_like(intensity, peak_gflops)

    # Memory roof
    memory_roof = intensity * bandwidth_gbps

    # Roofline (minimum of both)
    roofline = np.minimum(compute_roof, memory_roof)

    # Kernel performance point
    kernel_intensity = kernel_analysis['arithmetic_intensity']
    kernel_gflops = kernel_analysis['flops'] / (measured_latency * 1e-9) / 1e9

    plt.loglog(intensity, compute_roof, 'r--', label='Compute Bound')
    plt.loglog(intensity, memory_roof, 'b--', label='Memory Bound')
    plt.loglog(intensity, roofline, 'k-', linewidth=2, label='Roofline')
    plt.plot(kernel_intensity, kernel_gflops, 'go', markersize=10, label='bandpass_fir (measured)')

    plt.xlabel('Arithmetic Intensity (FLOP/byte)')
    plt.ylabel('Performance (GFLOPS)')
    plt.title(f'Roofline Model: {device_spec["name"]}')
    plt.legend()
    plt.grid(True, which='both', alpha=0.3)
    plt.savefig('roofline.png', dpi=150)
```

#### Advanced: Hardware Counter Integration (Linux only)

For more accurate decomposition, use `perf stat`:

```python
def measure_with_counters(kernel_cmd):
    """Run kernel with hardware performance counters"""
    result = subprocess.run([
        'perf', 'stat',
        '-e', 'cycles,instructions,cache-misses,cache-references,branches,branch-misses',
        kernel_cmd
    ], capture_output=True, text=True)

    # Parse perf output
    counters = parse_perf_output(result.stderr)

    return {
        'ipc': counters['instructions'] / counters['cycles'],
        'cache_miss_rate': counters['cache-misses'] / counters['cache-references'],
        'branch_miss_rate': counters['branch-misses'] / counters['branches']
    }
```

Extend telemetry struct:
```c
// Add to cortex_telemetry_record_t
uint64_t perf_cycles;
uint64_t perf_instructions;
uint64_t perf_cache_misses;
float ipc;  // Instructions per cycle
```

**Defer to v1.0+**: Requires Linux perf, privileged access

#### Testing

**Unit test**: Static analyzer
```python
def test_analyze_fir_kernel():
    analysis = analyze_kernel('primitives/kernels/v1/bandpass_fir/kernel.c', W=256, H=80, C=64)
    assert analysis['operations'] == 256 * 128 * 64  # W * taps * C
    assert analysis['arithmetic_intensity'] > 10  # FIR is compute-intensive
```

**Integration test**: End-to-end decomposition
```bash
# 1. Run benchmark
cortex run --kernel bandpass_fir --duration 10

# 2. Diagnose
cortex diagnose results/run-*/telemetry.ndjson --kernel bandpass_fir

# Expected: Identifies bottleneck (compute vs memory)
```

**Validation**: Compare to perf stat
```bash
# Run with hardware counters
perf stat -e cycles,instructions,cache-misses cortex run --kernel bandpass_fir

# Verify IPC matches static prediction
```

#### Files to Create/Modify

| File | Action | Lines |
|------|--------|-------|
| `sdk/kernel/tools/cortex_analyze_kernel.py` | CREATE | ~300 |
| `src/cortex/device_specs.yaml` | CREATE | ~100 |
| `src/cortex/commands/diagnose.py` | CREATE | ~400 |
| `src/cortex/utils/roofline.py` | CREATE | ~200 |
| `src/cortex/__init__.py` | MODIFY | +5 |
| `docs/user-guide/performance-analysis.md` | CREATE | ~1200 |

**Total Effort**: 2-3 weeks (static analysis parsing is complex, roofline model requires validation)

**Priority Justification**: This is **Tier 2** (should build) because:
- ✅ High ROI: Directly guides optimization (memory vs compute tradeoffs)
- ✅ Differentiating: No BCI benchmarking tool does this
- ✅ Builds on existing infrastructure (telemetry already captures timing)
- ✅ Research-validated (Intel Advisor, Nsight Compute, roofline model)

---

## Tier 3 Priorities: Nice to Have (Defer to v1.0+)

### Auto-Tuning Framework

**Research Finding** (halide-darkroom-analysis.md):
- Halide auto-scheduler uses learned cost model + beam search
- Searches split/tile/vectorize/parallel schedules

**CORTEX Application**:
- Auto-tune window size (W), hop (H), SIMD width
- Generate optimal configs per device

**Defer Reason**: Requires extensive training data, months of effort

---

### HdrHistogram Integration

**Research Finding** (prior-art-expanded.md):
- Better percentile accuracy than pandas quantile
- Handles bimodal distributions

**CORTEX Application**:
- Replace `df.quantile(0.95)` with HdrHistogram

**Defer Reason**: Current pandas approach is sufficient for v0.5.0

---

### eBPF Profiling

**Research Finding** (prior-art-expanded.md):
- Linux-only, requires kernel 4.9+
- Trace context switches, cache misses during benchmark

**CORTEX Application**:
- Diagnose deadline violations with kernel-level visibility

**Defer Reason**: Platform-specific, not cross-platform

---

## Documentation Priorities

### High Priority (Week 1)

1. **Algorithm/Schedule Separation** (`docs/architecture/design-principles.md`)
   - Document that CORTEX already implements Halide's core principle
   - Show mapping: kernel.c → algorithm, config.yaml → schedule

2. **Coordinated Omission Analysis** (`docs/methodology/measurement-correctness.md`)
   - Explain why CORTEX avoids Gil Tene's flaw
   - Compare to wrk/wrk2 issue

3. **Cross-Platform Fairness** (`docs/user-guide/reproducibility.md`)
   - EEMBC requirements for fair comparison
   - How to set CPU governor, disable turbo

### Medium Priority (Week 2)

4. **Pipeline Composition Tutorial** (`docs/tutorials/multi-stage-pipelines.md`)
   - How to define bandpass → CAR → CSP pipeline
   - Interpreting end-to-end latency

5. **Edge Deployment Guide** (`docs/user-guide/edge-deployment.md`)
   - ADB deployment to Android
   - USB deployment to microcontrollers

---

## Summary: Implementation Timeline

| Priority | Capability | Effort | Files Changed | Business Value |
|----------|-----------|--------|---------------|----------------|
| **Tier 1** | Pipeline Composition (SE-9) | 2-3 weeks | 6 files | End-to-end BCI latency |
| **Tier 1** | USB/ADB Adapters (SE-7) | 4-6 weeks | 7 files | Edge device support |
| **Tier 2** | Platform-State Capture (SE-5, SE-8) | 2 weeks | 5 files | Cross-platform fairness |
| **Tier 2** | Deadline Analysis CLI (SE-1) | 1 week | 3 files | Real-time verification |
| **Tier 2** | Comparative Analysis CLI (SE-2, HE-1) | 1 week | 4 files | CI regression detection |
| **Tier 2** | Multi-Dtype Fixed16 (SE-3) | 2-3 weeks | 5 files | Embedded optimization |
| **Tier 2** | **Latency Decomposition (SE-4)** | **2-3 weeks** | **6 files** | **Bottleneck identification** |

**Total Effort**: 14-19 weeks (~3.5-5 months) for all Tier 1 & Tier 2 priorities

---

## Next Steps

1. **Review this document** with Raghav and team
2. **Prioritize capabilities** based on upcoming deliverables
3. **Start with SE-1 or SE-2** (1 week each, high ROI, low risk)
4. **Parallel track**: Documentation while implementing SE-9

**Recommended First Sprint** (Week 1-2):
- SE-1: Deadline Analysis CLI (1 week) - ✅ Low effort, high visibility
- SE-2: Comparative Analysis CLI (1 week) - ✅ Enables CI integration
- **Docs**: Algorithm/schedule separation, Coordinated Omission

This establishes CORTEX's methodology credibility while building toward pipeline composition (SE-9).

---

**Document Metadata**:
- **Created**: 2026-01-19
- **Author**: Claude Code + Weston Vogle-Songer
- **Research Sources**:
  - `docs/research/prior-art-analysis.md` (26K words)
  - `docs/research/prior-art-expanded.md` (15K words)
  - `docs/research/halide-darkroom-analysis.md` (20K words)
- **Codebase Version**: CORTEX v0.5.0 (commit c7ef252)
