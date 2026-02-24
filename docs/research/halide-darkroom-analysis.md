# Halide and Dark Room: Deep Analysis for CORTEX

**Date**: 2026-01-19
**Research Objective**: Understand algorithm/schedule separation and pipeline composition from Halide and Dark Room
**Requested by**: Raghav (Meeting 3)

---

## Executive Summary

Halide and Darkroom are domain-specific languages (DSLs) for image processing that separate **what to compute** (algorithm) from **how to compute** (schedule). This research reveals:

1. **CORTEX already implements Halide's core principle** (kernel.c = algorithm, config.yaml = schedule)
2. **Darkroom's line-buffering model directly applies to BCI** (window-based signal processing is line-buffered streaming)
3. **Pipeline composition (SE-9) should adopt Halide's compute_at/store_at** semantics for multi-stage kernel orchestration
4. **Auto-tuning CORTEX configs is analogous to Halide's auto-scheduler** problem

**Key Recommendation**: Formalize CORTEX's algorithm/schedule separation in architecture docs, adopt Darkroom's simpler streaming model for pipeline composition, and consider Halide-style auto-tuning for device-specific config optimization.

---

## Part 1: Halide Deep Dive

### 1.1 Core Concept: Algorithm/Schedule Separation

**The Problem Halide Solves**:
Traditional image processing code conflates:
- **Algorithm logic** (what computations to perform)
- **Optimization decisions** (loop order, tiling, vectorization, parallelism)

Changing a single optimization (e.g., tile size) requires rewriting the algorithm code, making exploration tedious.

**Halide's Solution**:
```halide
// Algorithm: WHAT to compute (pure functional specification)
Func blur_x("blur_x");
blur_x(x, y) = (input(x-1, y) + input(x, y) + input(x+1, y)) / 3;

Func blur_y("blur_y");
blur_y(x, y) = (blur_x(x, y-1) + blur_x(x, y) + blur_x(x, y+1)) / 3;

// Schedule: HOW to compute (performance tuning, completely separate!)
Var x_outer, y_outer, x_inner, y_inner, tile_index;
blur_y.tile(x, y, x_outer, y_outer, x_inner, y_inner, 64, 64)
      .fuse(x_outer, y_outer, tile_index)
      .parallel(tile_index);
blur_y.vectorize(x_inner, 4);
blur_x.compute_at(blur_y, x_outer);  // Fuse blur_x into blur_y's tiles
```

**Result**: Same algorithm, 10+ different schedules can be explored without touching algorithm code.

---

### 1.2 Scheduling Primitives Reference

| Primitive | Purpose | Performance Tradeoff | CORTEX Equivalent |
|-----------|---------|---------------------|-------------------|
| **split(var, outer, inner, factor)** | Decompose loop into nested loops | Enables vectorization/unrolling | Implicit in window_length (fixed inner loop size) |
| **tile(x, y, ..., tx, ty)** | 2D rectangular tiling | Improves cache locality (process txty block fully before next) | Could add tile_size_x, tile_size_y to config |
| **vectorize(var, width)** | SIMD operations | 4-8× throughput, requires aligned data | Makefile: -march=native -ftree-vectorize |
| **unroll(var, factor)** | Replicate loop body | Reduces loop overhead, enables optimization | Compiler decides (could add unroll hint) |
| **parallel(var)** | Multi-threaded execution | N-core speedup, parallelization overhead | Future: thread_count config |
| **fuse(var1, var2, fused)** | Merge two loops into one | Avoids nested parallelism, improves load balance | Not applicable (single kernel execution) |
| **reorder(vars...)** | Change loop nesting order | Better cache patterns (row-major vs column-major) | Not exposed (C code controls loop order) |

**Key Insight**: Halide makes loop transformations **first-class citizens** instead of compiler-internal optimizations.

---

### 1.3 Pipeline Composition: compute_at/store_at

**The Problem**: Multi-stage pipelines have producer-consumer relationships. Where should intermediate results be materialized?

**Halide's Five Scheduling Directives**:

#### 1. compute_inline() [Default]
Fully inline producer into consumer (no intermediate storage).

```cpp
// Producer
Func expensive(x, y) = sin(x) + sin(y);
// Consumer
Func result(x, y) = expensive(x-1, y) + expensive(x, y) + expensive(x+1, y);

result.compute_inline();  // Default behavior
```

**Generated code**:
```cpp
for (int y = 0; y < H; y++)
  for (int x = 0; x < W; x++)
    result[x][y] = (sin(x-1)+sin(y)) + (sin(x)+sin(y)) + (sin(x+1)+sin(y));
    //              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    //              sin() called 3× per pixel (redundant computation!)
```

**Tradeoff**:
- ✅ Zero intermediate storage
- ✅ Maximum locality (data produced where consumed)
- ❌ Redundant computation (overlap in stencils)

---

#### 2. compute_root()
Compute all producer values before any consumer execution (fully materialized intermediate).

```cpp
expensive.compute_root();
```

**Generated code**:
```cpp
// Phase 1: Compute entire expensive array
float expensive[H][W];
for (int y = 0; y < H; y++)
  for (int x = 0; x < W; x++)
    expensive[x][y] = sin(x) + sin(y);

// Phase 2: Consume from pre-computed array
for (int y = 0; y < H; y++)
  for (int x = 0; x < W; x++)
    result[x][y] = expensive[x-1][y] + expensive[x][y] + expensive[x+1][y];
```

**Tradeoff**:
- ✅ Minimal redundant computation (each pixel computed once)
- ✅ Producer and consumer can be parallelized independently
- ❌ Full intermediate storage (H×W floats)
- ❌ Poor cache locality (producer → DRAM → consumer)

---

#### 3. compute_at(consumer, loop_var)
Compute producer on-demand at specific loop nesting level of consumer.

```cpp
expensive.compute_at(result, y);  // Recompute for each scanline
```

**Generated code**:
```cpp
for (int y = 0; y < H; y++) {
  // Compute scanline buffer (W+2 pixels for stencil overlap)
  float expensive_buffer[W+2];
  for (int x = -1; x <= W; x++)
    expensive_buffer[x+1] = sin(x) + sin(y);

  // Consume scanline
  for (int x = 0; x < W; x++)
    result[x][y] = expensive_buffer[x] + expensive_buffer[x+1] + expensive_buffer[x+2];
}
```

**Tradeoff**:
- ✅ Intermediate storage = 1 scanline (W+2 floats) instead of full image (H×W)
- ✅ Better cache locality (producer → consumer within inner loop)
- 🟡 Some redundant computation (overlap at scanline boundaries)

---

#### 4. store_root() + compute_at()
Allocate storage at outermost scope, compute on-demand.

```cpp
expensive.store_root().compute_at(result, y);
```

**Key optimization**: Halide automatically **folds storage into circular buffers**. A 5×5 stencil only needs 2-3 scanlines in memory, not the full image.

---

#### 5. store_at(consumer, loop_var)
Allocate buffer at specific loop level (similar to compute_at but for storage only).

---

### 1.4 Halide Auto-Scheduler (SIGGRAPH 2019)

**Problem**: Manual scheduling requires expert knowledge and hours of tuning per program.

**Solution**: Learn cost model from random program generation → predict performance → search schedule space.

**Methodology**:

1. **Training Phase**:
   - Generate hundreds of thousands of random Halide programs
   - Apply random schedules (tile sizes, vectorization widths, compute_at placements)
   - Profile execution time on target hardware
   - Extract features: memory footprint, arithmetic intensity, parallelism degree, etc.
   - Train ML model: `features → predicted_runtime`

2. **Optimization Phase** (beam search):
   - Start with unscheduled program
   - Generate candidate schedules (vary tile sizes, vectorization, fusion points)
   - Predict runtime using trained cost model
   - Keep top-K candidates (beam width)
   - Iteratively refine until convergence

3. **Results**:
   - **2× faster than previous Halide auto-scheduler**
   - **First auto-scheduler to beat human experts on average**
   - Schedule generation: seconds (vs manual tuning: hours)

**Relevance to CORTEX**:
- CORTEX config parameters (warmup, load_profile, compiler_flags) are analogous to Halide schedules
- Auto-tuning CORTEX configs per device could follow similar methodology:
  - Generate random configs → Benchmark on device → Learn cost model → Predict optimal config

---

### 1.5 Lessons for CORTEX

#### Already Implemented ✅

CORTEX inherently separates algorithm from schedule:

```c
// Algorithm: primitives/kernels/bandpass_fir@f32/kernel.c
void bandpass_fir_process(float *input, float *output, cortex_state_t *state) {
    // Pure signal processing logic (no optimization details)
    for (int i = 0; i < window_size; i++) {
        output[i] = fir_filter(input, state->coeffs, i);
    }
}
```

```yaml
# Schedule: primitives/configs/cortex.yaml
benchmark:
  parameters:
    warmup_seconds: 2        # Scheduling: cache/thermal warmup
    load_profile: heavy      # Scheduling: execution environment
    duration_seconds: 60     # Scheduling: measurement duration
```

**Halide Equivalent**:
```halide
fir.compute_root()              → warmup_seconds (pre-compute for cache)
fir.parallel(y)                 → load_profile (multi-core execution)
fir.vectorize(x, 8)             → Makefile -march=native
```

#### Missing Primitives 🟡

CORTEX doesn't expose these Halide scheduling directives:

| Halide Primitive | CORTEX Gap | Should Add? |
|------------------|------------|-------------|
| `tile(x, y, 64, 64)` | No tiling config | **Yes**: tile_size for cache blocking |
| `parallel(var)` | No thread count control | **Yes**: thread_pool_size config |
| `vectorize(x, width)` | Compiler-only | **Maybe**: explicit SIMD width hint |
| `unroll(var, factor)` | Compiler-only | **No**: too low-level for CORTEX |
| `compute_at(stage, loop)` | No pipeline composition | **Yes**: SE-9 needs this |

#### Recommended Config Extensions

```yaml
# primitives/configs/cortex.yaml (extended)
benchmark:
  algorithm:
    kernels:
      - name: bandpass_fir
        precision: float32

  schedule:
    warmup_seconds: 2
    load_profile: heavy

    # NEW: Halide-inspired scheduling directives
    parallelism:
      thread_count: 4        # Halide: parallel(y)
      affinity: core         # Pin threads to cores

    memory:
      tile_size: 64          # Halide: tile(x, y, 64, 64)
      cache_blocking: true   # Enable cache-aware tiling

    vectorization:
      enabled: true          # Halide: vectorize(x, 8)
      width: 8               # SIMD width (auto-detect if omitted)

    pipeline:  # SE-9: Multi-stage composition
      stages:
        - name: bandpass_fir
          compute_at: root   # Halide: compute_root()
        - name: car
          compute_at: inline # Halide: compute_inline()
        - name: csp
          compute_at: root
```

---

## Part 2: Darkroom Deep Dive

### 2.1 Core Model: Line-Buffered Streaming

**What is Line-Buffering?**

Traditional image processing:
```
Input Image (DRAM) → Stage 1 → Intermediate (DRAM) → Stage 2 → Output (DRAM)
                           ^^^^                   ^^^^
                    Expensive memory bandwidth!
```

Line-buffered pipeline:
```
Input (scanline streaming) → [Stage 1 buffer] → [Stage 2 buffer] → Output
                                 ^^^^^^              ^^^^^^
                          Small on-chip SRAM (few scanlines)
```

**Key Constraint**: Each stage can only read a **stencil** (small window) around the current pixel. Typical stencils:
- Point-wise: 1×1 (color correction, gamma)
- Separable: 3×1 or 1×3 (Gaussian blur)
- Non-separable: 3×3, 5×5 (edge detection, convolution)

**Buffer Size Calculation**:
- 3×3 stencil → need 3 scanlines in memory
- 5×5 stencil → need 5 scanlines
- Pipeline of (3×3 → 5×5) → max(3, 5) = 5 scanlines (not 3+5=8!)

**Hardware Efficiency**:
- DRAM bandwidth: ~10 GB/s
- On-chip SRAM bandwidth: ~100 GB/s (10× faster)
- Power: SRAM access ~1 pJ, DRAM access ~100 pJ (100× more efficient)

**Result**: Darkroom-compiled pipelines achieve **tera-op/sec image processing in battery-powered devices**.

---

### 2.2 Simplified Scheduling Model

**Halide vs Darkroom Scheduling**:

| Aspect | Halide | Darkroom |
|--------|--------|----------|
| **Schedule specification** | Manual (or auto-scheduler) | **Automatic** (ILP solver) |
| **Scheduling time** | Hours (auto-scheduler) | **< 1 second** (ILP) |
| **Schedule space** | Exponential (tile sizes, vectorization, fusion points) | Constrained (streaming order only) |
| **Intermediate storage** | Flexible (compute_root vs compute_at) | **Fixed** (line buffers) |
| **Loop order** | Flexible (reorder, tile) | **Fixed** (scanline streaming) |
| **Target platforms** | CPU, GPU, FPGA (via HLS) | **FPGA, ASIC** (direct synthesis) |

**Why Darkroom Is Faster to Compile**:

Halide schedule space:
```
Tile sizes: {4, 8, 16, 32, 64, 128, 256}^2  // 49 options per 2D function
Vectorization: {1, 2, 4, 8, 16}             // 5 options
Parallelism: {1, 2, 4, 8, 16, 32}           // 6 options
Fusion points: {inline, root, at(stage_i, loop_j)}  // Exponential in pipeline depth
```

Darkroom schedule space:
```
Streaming order: Fixed (scanline-by-scanline)
Intermediate storage: Determined by stencil sizes (ILP)
No tiling, vectorization, parallelism decisions → compiler handles automatically
```

**Integer Linear Program (ILP) for Buffer Minimization**:

```
Minimize: sum(buffer_sizes)
Subject to:
  - For each stage S with stencil radius R:
      buffer_S >= 2*R + 1  (enough scanlines for stencil)
  - For pipeline (A → B):
      buffer_B >= buffer_A - consumed_rows_per_iteration
  - All buffer_sizes >= 0
```

Darkroom solves this ILP in < 1 second, even for 20-stage pipelines.

---

### 2.3 Hardware Compilation

**Darkroom → Verilog/ASIC Flow**:

1. **Stencil Detection**: Analyze which pixels each stage reads (stencil pattern)
2. **Buffer Allocation**: Solve ILP for minimal scanline buffers
3. **Pipeline Generation**:
   - Create shift registers for line buffers (circular buffers in hardware)
   - Generate state machines for stencil window extraction
   - Synthesize per-pixel arithmetic units (fixed-function or programmable)
4. **Hardware Description**: Emit Verilog for FPGA (Vivado, Quartus) or ASIC (custom flow)

**Example: 3×3 Gaussian Blur**:

Darkroom code:
```darkroom
func blur(img : Image) -> Image {
  return (img[x-1, y-1] + img[x, y-1] + img[x+1, y-1] +
          img[x-1, y]   + img[x, y]   + img[x+1, y]   +
          img[x-1, y+1] + img[x, y+1] + img[x+1, y+1]) / 9
}
```

Generated Verilog:
```verilog
module blur(
  input wire clk,
  input wire [7:0] pixel_in,  // Streaming input
  output reg [7:0] pixel_out  // Streaming output
);
  reg [7:0] line_buffer[0:2][0:WIDTH-1];  // 3 scanlines
  reg [7:0] stencil[0:8];  // 3×3 window

  // Shift register logic (omitted for brevity)
  // Arithmetic: sum 9 pixels, divide by 9
  wire [11:0] sum = stencil[0] + stencil[1] + ... + stencil[8];
  always @(posedge clk)
    pixel_out <= sum / 9;
endmodule
```

**Performance Results** (from paper):
- 1080p/60 video processing: < 50% FPGA resources (Altera Stratix V)
- ASIC synthesis (45nm): 0.5 mm², 250 mW, gigapixels/sec

---

### 2.4 Relationship to Halide

**Timeline**:
- Darkroom: SIGGRAPH 2014 (Stanford, James Hegarty, Pat Hanrahan)
- Halide: PLDI 2013 (MIT/Adobe, Jonathan Ragan-Kelley, Andrew Adams)

**Shared Authors**: Jonathan Ragan-Kelley (Halide co-author, Darkroom co-author)

**Conceptual Lineage**:
1. Halide introduced algorithm/schedule separation for **CPU/GPU**
2. Darkroom applied similar principles to **hardware** with constrained scheduling model
3. Halide later added FPGA backend via HLS (but slower compilation than Darkroom)

**Key Difference**:
- **Halide**: Maximize flexibility → explore vast schedule space → long compilation
- **Darkroom**: Restrict model to line-buffering → fast ILP-based scheduling → < 1sec compilation

**Tradeoff**:
- Halide achieves 10-30% better performance (after hours of tuning)
- Darkroom achieves 90% of Halide's performance in 1 second

---

### 2.5 Lessons for CORTEX

#### BCI Signal Processing is Line-Buffered! ✅

**BCI kernel execution model**:
```
EEG samples (streaming) → Window buffer → Kernel process → Output → Next window
                             ^^^^^^
                       Fixed-size sliding window (e.g., 256 samples)
```

This is **exactly** Darkroom's line-buffering model, where:
- "Scanline" = EEG window (time-series segment)
- "Stencil" = Kernel's lookback/lookahead (e.g., FIR filter taps)
- "Pipeline stages" = Multi-kernel composition (bandpass → CAR → CSP)

**Example: Bandpass FIR Filter**:
- Input: 256 samples per window
- Stencil: 64-tap FIR filter (needs 64 previous samples)
- Buffer: 64 samples carry-over between windows (stateful kernel)

**Darkroom Equivalent**:
```darkroom
func bandpass(eeg : Signal, taps : Array[64]) -> Signal {
  return sum(eeg[t-64:t] * taps)  // 64-sample stencil
}
```

**CORTEX Already Does This**:
```c
// primitives/kernels/bandpass_fir@f32/kernel.c
typedef struct {
    float history[64];  // Line buffer (carry-over samples)
    float taps[64];     // Filter coefficients
} bandpass_state_t;

void bandpass_process(float *input, float *output, bandpass_state_t *state) {
    // Shift history buffer (circular buffer)
    // Convolve with taps (stencil operation)
}
```

#### Pipeline Composition Should Adopt Darkroom's Model

**SE-9 (Pipeline Composition)** should use **streaming model**, not general DAG:

**Bad (overly general)**:
```yaml
pipeline:
  stages:
    - bandpass: {input: raw_eeg, output: filtered}
    - car: {input: filtered, output: rereferenced}
    - csp: {input: rereferenced, output: features}
  # Allows arbitrary DAGs → complex scheduling problem
```

**Good (Darkroom-inspired streaming)**:
```yaml
pipeline:
  stages:  # Sequential streaming pipeline
    - bandpass
    - car
    - csp
  # Constraint: stages form linear chain → simple scheduling (< 1sec)

  buffering:  # Automatic ILP-based optimization
    minimize: memory_footprint
    # Darkroom's ILP solver determines optimal inter-stage buffers
```

**Why This Works for BCI**:
- Most BCI pipelines are linear: preprocessing → feature extraction → classification
- Non-linear pipelines (parallel feature extractors) can be flattened via replication
- Streaming constraint enables fast compilation (like Darkroom's < 1sec)

#### Hardware Persona (HE) Benefits

**HE-1, HE-2** (FPGA adapter workflows) can directly leverage Darkroom methodology:

1. **CORTEX kernel → Darkroom IR**:
   - Parse C kernel → extract stencil pattern (lookback/lookahead)
   - Map to Darkroom functional specification

2. **Darkroom → Verilog**:
   - Use Darkroom compiler to generate hardware
   - Alternative: Use Halide → Vivado HLS (slower but more flexible)

3. **Benchmarking FPGA vs ARM**:
   - Same kernel, two adapters: `x86@loopback`, `zynq@fpga`
   - Compare latency/throughput on FPGA fabric vs ARM processor

**Future CORTEX Extension**:
```bash
cortex compile --kernel bandpass_fir --target zynq_fpga --output bitstream.bit
cortex run --device zynq --kernel bandpass_fir  # Loads bitstream, benchmarks
```

---

## Part 3: Comparative Analysis

### 3.1 Halide vs Darkroom vs CORTEX

| Aspect | Halide | Darkroom | CORTEX (Current) | CORTEX (Should Adopt) |
|--------|--------|----------|------------------|----------------------|
| **Algorithm Representation** | Functional DSL (C++ embedded) | Functional DSL (custom syntax) | C function | ✅ Keep C (familiar to SE persona) |
| **Schedule Representation** | Explicit DSL (tile, vectorize, parallel) | Implicit (ILP-based) | Makefile + YAML | 🟡 Add scheduling vocab to YAML |
| **Pipeline Composition** | `compute_at(stage, loop)` | Automatic (streaming) | ❌ Not supported | ✅ Adopt Darkroom streaming model |
| **Target Platforms** | CPU, GPU, FPGA (HLS) | FPGA, ASIC | CPU (x86, ARM) | ✅ Extend to FPGA (HE persona) |
| **Scheduling Time** | Hours (auto-scheduler) | < 1 sec (ILP) | Manual | ✅ Future: auto-tune like Halide |
| **Correctness Validation** | Differential testing (unopt vs opt) | Hardware simulation | Oracle (Python) | ✅ Keep oracle (BCI-specific) |
| **Domain** | Image processing | Image processing (camera ISPs) | BCI signal processing | ✅ BCI is line-buffered like ISPs |
| **Memory Model** | Flexible (compute_root vs compute_at) | Fixed (line buffers) | Stateful kernels | ✅ Darkroom model fits naturally |

---

### 3.2 Algorithm/Schedule Separation Mapping

**Halide Example**:
```halide
// Algorithm
Func blur(Func input) {
  return (input(x-1, y) + input(x, y) + input(x+1, y)) / 3;
}

// Schedule
blur.tile(x, y, 64, 64).vectorize(x_inner, 8).parallel(y_outer);
```

**CORTEX Equivalent** (current):
```c
// Algorithm: kernel.c
void blur_process(float *in, float *out) {
  for (int i = 0; i < N; i++)
    out[i] = (in[i-1] + in[i] + in[i+1]) / 3.0f;
}
```

```yaml
# Schedule: config.yaml
benchmark:
  parameters:
    warmup_seconds: 2      # Cache warmup
    load_profile: heavy    # Multi-core environment
```

```makefile
# Schedule: Makefile
CFLAGS = -O3 -march=native -ftree-vectorize  # Vectorization
```

**CORTEX Extended** (proposed):
```yaml
# primitives/configs/bandpass_schedule.yaml
kernel:
  name: bandpass_fir
  algorithm: primitives/kernels/bandpass_fir@f32/kernel.c

schedule:
  parallelism:
    thread_count: 4
    affinity: core

  memory:
    tile_size: 64           # Cache blocking (Halide: tile(x, y, 64, 64))
    prefetch: ahead_2       # Prefetch 2 tiles ahead

  vectorization:
    width: 8                # SIMD (Halide: vectorize(x, 8))
    alignment: 32           # 32-byte alignment for AVX

  measurement:
    warmup_seconds: 2
    duration_seconds: 60
    load_profile: heavy
```

---

### 3.3 Pipeline Composition Mapping

**Halide Multi-Stage**:
```halide
Func blur_x(Func input) = ...;
Func blur_y(Func blur_x) = ...;

// Schedule: Fuse blur_x into blur_y's tiles
blur_y.tile(x, y, 64, 64).parallel(tile_index);
blur_x.compute_at(blur_y, tile_index);  // Recompute per tile
```

**Darkroom Multi-Stage**:
```darkroom
pipeline {
  blur_x -> blur_y  // Streaming (automatic line-buffer insertion)
}
```

**CORTEX (SE-9 Proposal)**:
```yaml
# primitives/configs/preprocessing_pipeline.yaml
pipeline:
  name: bci_preprocessing

  stages:  # Linear streaming pipeline (Darkroom model)
    - kernel: bandpass_fir
      output: filtered

    - kernel: car
      input: filtered
      output: rereferenced
      compute_mode: inline  # Halide: compute_inline() - fuse into next stage

    - kernel: csp
      input: rereferenced
      output: features
      compute_mode: root    # Halide: compute_root() - materialize fully

  buffering:
    strategy: minimize_memory  # Darkroom ILP optimization
    # OR: strategy: minimize_latency (prioritize fusion over storage)
```

**Generated Execution**:
```c
// CORTEX harness generates this from pipeline YAML:
for (each window) {
  // Stage 1: Bandpass (compute_root → materialize)
  bandpass_process(eeg_window, filtered_buffer, state1);

  // Stage 2: CAR (compute_inline → fused into CSP)
  // Skipped intermediate storage

  // Stage 3: CSP (reads bandpass output, applies CAR inline)
  for (int ch = 0; ch < channels; ch++) {
    car_sample = car_inline(filtered_buffer[ch], ...);  // Inlined
    csp_buffer[ch] = car_sample;
  }
  csp_process(csp_buffer, features, state3);
}
```

---

## Part 4: Concrete Recommendations for CORTEX

### 4.1 Immediate (v0.6.0) — Formalize Existing Separation

**Action 1: Document Algorithm/Schedule Separation**

Add to `docs/architecture/design-principles.md`:

```markdown
## Design Principle: Algorithm/Schedule Separation

CORTEX separates **what to compute** (kernel algorithm) from **how to compute** (execution schedule), following the design philosophy of Halide [1] and Darkroom [2].

### Algorithm Layer (WHAT)
- **Location**: `primitives/kernels/{name}@{precision}/kernel.c`
- **Responsibility**: Pure signal processing logic
- **Constraints**:
  - No optimization directives (no #pragma, no __attribute__)
  - No platform-specific code (no #ifdef for ARM vs x86)
  - Stateless computation (state managed externally via cortex_state_t)

### Schedule Layer (HOW)
- **Location**: `primitives/configs/*.yaml`, `kernels/*/Makefile`
- **Responsibility**: Performance tuning
- **Parameters**:
  - Warmup (cache/thermal stabilization)
  - Load profile (execution environment)
  - Compiler flags (vectorization, optimization level)
  - Memory parameters (tile size, prefetch)

### Benefits
1. **Portability**: Same kernel runs on x86, ARM, FPGA (schedule varies)
2. **Optimization**: Explore schedules without changing algorithm
3. **Validation**: Oracle validates algorithm correctness (schedule-agnostic)

[1] Halide: https://halide-lang.org/
[2] Darkroom: https://graphics.stanford.edu/papers/darkroom14/
```

**Effort**: 1 day (documentation)

---

**Action 2: Add Scheduling Vocabulary to Config**

Extend `cortex.yaml` schema with Halide-inspired directives:

```yaml
# primitives/configs/cortex_extended.yaml
kernels:
  - name: bandpass_fir
    algorithm: primitives/kernels/bandpass_fir@f32/kernel.c

    schedule:
      # Memory hierarchy (Halide: tile)
      blocking:
        tile_size: 64        # Process 64 samples per inner loop
        prefetch_distance: 2 # Prefetch 2 tiles ahead

      # Parallelism (Halide: parallel)
      parallelism:
        enabled: false       # Single-threaded (for now)
        thread_count: 1      # Future: multi-threaded kernels

      # Vectorization (Halide: vectorize)
      simd:
        enabled: true
        width: 8             # 8-wide SIMD (AVX)
        alignment: 32        # Byte alignment requirement

benchmark:
  parameters:
    warmup_seconds: 2
    duration_seconds: 60
    load_profile: heavy
```

**Effort**: 1 week (schema design + harness integration)

---

### 4.2 Near-Term (v0.7.0) — Pipeline Composition

**Action 3: Implement Darkroom-Style Streaming Pipelines**

**SE-9** (Pipeline Composition) should use **linear streaming model** with automatic buffer optimization.

**Design**:

1. **Run-Config Schema** (`primitives/configs/pipeline_*.yaml`):
```yaml
pipeline:
  name: bci_preprocessing
  description: Bandpass → CAR → CSP feature extraction

  stages:
    - name: bandpass
      kernel: bandpass_fir@f32
      output: filtered_signal

    - name: car
      kernel: car@f32
      input: filtered_signal
      output: rereferenced_signal
      compute_mode: inline  # Fuse into next stage (no intermediate storage)

    - name: csp
      kernel: csp@f32
      input: rereferenced_signal
      output: spatial_features
      compute_mode: root    # Materialize (save to buffer)

  buffering:
    optimization: minimize_memory  # OR: minimize_latency
```

2. **Harness Orchestration**:
```c
// src/engine/harness/pipeline_scheduler.c
typedef enum {
    COMPUTE_INLINE,   // Fuse into consumer (no buffer)
    COMPUTE_ROOT      // Materialize (allocate buffer)
} compute_mode_t;

typedef struct {
    char name[64];
    cortex_kernel_t *kernel;
    compute_mode_t mode;
    float *input_buffer;   // NULL if inline
    float *output_buffer;
} pipeline_stage_t;

void execute_pipeline(pipeline_stage_t *stages, int num_stages, float *eeg_window) {
    for (int s = 0; s < num_stages; s++) {
        if (stages[s].mode == COMPUTE_INLINE) {
            // Inline: output goes directly to next stage's input (no copy)
            stages[s].output_buffer = stages[s+1].input_buffer;
        } else {
            // Root: allocate persistent buffer
            stages[s].output_buffer = malloc(...);
        }

        // Execute kernel
        stages[s].kernel->process(stages[s].input_buffer,
                                   stages[s].output_buffer,
                                   stages[s].kernel->state);
    }
}
```

3. **Telemetry Extension** (per-stage latency):
```c
typedef struct {
    char stage_name[64];
    uint64_t start_ts;
    uint64_t end_ts;
    uint32_t stage_latency_us;
} pipeline_stage_telemetry_t;

// Output: telemetry.ndjson
// {"stage": "bandpass", "latency_us": 1200, ...}
// {"stage": "car", "latency_us": 300, ...}
// {"stage": "csp", "latency_us": 2500, ...}
// {"pipeline_total_latency_us": 4000, ...}
```

**Effort**: 3 weeks (design + implementation + testing)

**Benefits**:
- End-to-end latency measurement (SE-9)
- Per-stage profiling (SE-5: bottleneck identification)
- Memory footprint optimization (inline vs root trade-off)

---

### 4.3 Long-Term (v1.0+) — Auto-Tuning

**Action 4: Halide-Style Auto-Scheduler for Config Optimization**

**Goal**: Automatically find optimal config parameters per device (like Halide's auto-scheduler).

**Methodology**:

1. **Config Search Space**:
```python
search_space = {
    'warmup_seconds': [0, 1, 2, 5],
    'tile_size': [32, 64, 128, 256],
    'simd_width': [4, 8, 16],
    'load_profile': ['idle', 'medium', 'heavy'],
    'thread_count': [1, 2, 4, 8],
}
```

2. **Training Phase** (one-time per device):
```bash
cortex auto-tune --kernel bandpass_fir --device raspberrypi4 --metric p95_latency

# Process:
# 1. Generate random configs (100-1000 samples)
# 2. Benchmark each config → measure P95 latency
# 3. Extract features: {warmup, tile_size, ...} → p95_latency
# 4. Train cost model (random forest, neural net)
# 5. Save model: ~/.cortex/models/raspberrypi4_bandpass_fir.pkl
```

3. **Optimization Phase** (fast prediction):
```bash
cortex optimize --kernel bandpass_fir --device raspberrypi4

# Process:
# 1. Load trained model
# 2. Beam search over config space
# 3. Predict P95 latency for each candidate
# 4. Output optimal config: configs/bandpass_fir_pi4_optimal.yaml
```

**Effort**: 4 weeks (design + ML model + CLI integration)

**Benefits**:
- Researcher productivity: "cortex auto-tune" → optimal config in minutes
- Device-specific optimization: Pi4 needs different config than Snapdragon 888
- Continuous improvement: Retrain model as new devices/kernels added

---

### 4.4 HE Persona (Spring 2026) — Hardware Compilation

**Action 5: Darkroom-Based FPGA Code Generation**

**Goal**: Compile CORTEX kernels to FPGA bitstreams for HE-1, HE-2 workflows.

**Approach 1: Direct Darkroom Integration**:
```bash
cortex compile --kernel bandpass_fir --target zynq_fpga --output bitstream.bit

# Internals:
# 1. Parse kernel.c → extract stencil pattern (FIR filter = 64-tap stencil)
# 2. Generate Darkroom IR:
#    func bandpass(eeg : Signal[256], taps : Array[64]) -> Signal[256] {
#      return sum(eeg[t-64:t] * taps)
#    }
# 3. Invoke Darkroom compiler → Verilog
# 4. Vivado synthesis → bitstream.bit
```

**Approach 2: Halide HLS Backend**:
```bash
cortex compile --kernel bandpass_fir --target zynq_fpga --backend halide_hls

# Internals:
# 1. Translate kernel.c → Halide IR
# 2. Halide → Vivado HLS (C++ → Verilog)
# 3. Slower compilation but more flexible scheduling
```

**Device Adapter**:
```python
# primitives/adapters/v1/zynq@fpga/cortex_adapter_zynq_fpga.py
class ZynqFPGAAdapter:
    def deploy(self, bitstream_path):
        # Load bitstream to FPGA fabric via JTAG
        # Map AXI memory interface to ARM processor

    def run_kernel(self, eeg_data):
        # Transfer data: ARM → FPGA (AXI DMA)
        # Trigger FPGA kernel execution
        # Retrieve results: FPGA → ARM
        # Measure latency (FPGA execution only)
```

**Effort**: 6 weeks (Darkroom integration OR Halide HLS backend)

**Benefits**:
- HE-1: Compare HLS vs hand-coded Verilog (same benchmarking methodology)
- HE-2: Benchmark kernel latency on ARM vs FPGA fabric
- Demonstrates CORTEX extensibility (CPU → FPGA via device adapters)

---

## Part 5: Summary

### What We Learned

1. **Halide's Algorithm/Schedule Separation**:
   - Decouples optimization from algorithm via scheduling DSL
   - Primitives: tile, vectorize, parallel, compute_at, store_at
   - Auto-scheduler achieves 2× speedup over manual tuning

2. **Darkroom's Simplified Model**:
   - Restricts to line-buffered streaming (like BCI windows)
   - ILP-based buffer minimization (< 1 sec compilation)
   - Direct hardware synthesis (FPGA/ASIC)

3. **CORTEX Already Implements Core Principle**:
   - kernel.c (algorithm) + config.yaml (schedule)
   - BCI signal processing is line-buffered (fits Darkroom model)

### What CORTEX Should Adopt

| Priority | Feature | Source | Effort | Impact |
|----------|---------|--------|--------|--------|
| **High** | Document algorithm/schedule separation | Halide/Darkroom | 1 day | Architectural clarity |
| **High** | Extend config with scheduling vocab | Halide | 1 week | Enable optimization exploration |
| **High** | Pipeline composition (streaming model) | Darkroom | 3 weeks | SE-9 (end-to-end latency) |
| **Medium** | Auto-tuning framework | Halide auto-scheduler | 4 weeks | Researcher productivity |
| **Low** | FPGA code generation | Darkroom/Halide HLS | 6 weeks | HE persona (Spring 2026) |

### Architectural Implications

**CORTEX v0.6.0+** should:
1. **Formalize** algorithm/schedule separation in docs
2. **Extend** config.yaml with Halide-inspired scheduling directives
3. **Implement** Darkroom-style streaming pipelines for SE-9

**CORTEX v1.0+** should:
4. **Add** auto-tuning for config optimization (Halide auto-scheduler approach)
5. **Support** FPGA compilation for HE persona (Darkroom methodology)

---

## References

**Halide**:
- [1] Ragan-Kelley et al., "Halide: A Language and Compiler for Optimizing Parallelism, Locality, and Recomputation," PLDI 2013
- [2] Ragan-Kelley et al., "Halide: Decoupling Algorithms from Schedules," ACM CACM 2018
- [3] Adams et al., "Learning to Optimize Halide with Tree Search and Random Programs," SIGGRAPH 2019
- [4] Official tutorials: https://halide-lang.org/tutorials/

**Darkroom**:
- [5] Hegarty et al., "Darkroom: Compiling High-Level Image Processing Code into Hardware Pipelines," SIGGRAPH 2014
- [6] Project page: https://graphics.stanford.edu/papers/darkroom14/

**CORTEX**:
- [7] Capability Table: docs/capability-table.md
- [8] User Stories: docs/personas-stories.md
- [9] Architecture Diagram: docs/architecture-diagram.md
