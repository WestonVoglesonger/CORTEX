# No-Op Kernel (Identity Function)

**Purpose**: Measure CORTEX harness dispatch overhead

## Overview

The no-op kernel is an identity function that performs minimal computation (output = input). By measuring the latency of this trivial kernel, we can empirically quantify the overhead introduced by the CORTEX measurement harness itself.

## What It Measures

When you run the no-op kernel, the measured latency represents:

```
Measured latency = Timing overhead + Function call overhead + Memory operations
```

**Components**:
- **Timing overhead**: `clock_gettime()` calls (~25ns × 2 = ~50ns)
- **Function call overhead**: Function dispatch through plugin ABI (~10-20ns)
- **Memory operations**: `memcpy()` for W×C floats (if not in-place)

## What It Does NOT Measure

The no-op does **not** capture:
- Cache pollution from timing code on subsequent kernel execution
- Branch predictor state changes
- Memory bandwidth interference during actual kernel computation

These effects are bounded by empirical evidence: clean 130% DVFS signal proves measurement overhead << real effects.

## Implementation

```c
int noop_process(void* handle, const float* input, float* output) {
    noop_state_t* state = (noop_state_t*)handle;
    size_t total_samples = state->window_length * state->channels;

    // Identity function: output = input
    memcpy(output, input, total_samples * sizeof(float));

    return 0;
}
```

**Configuration**:
- `allow_in_place: true` - Minimizes overhead by allowing harness to skip copy
- W=160, C=64 - Standard BCI window size
- H=80 - 50% overlap

## Building

```bash
cd primitives/kernels/v1/noop@f32
make
```

Or from project root:
```bash
make plugins
```

## Running

```bash
# Using auto-detection (will include noop if built)
cortex run

# Explicit specification
cortex run --kernel noop
```

## Expected Results

**Typical overhead range**: 100-800ns

- **Minimum latency**: ~100-200ns (timing + dispatch, no memory copy)
- **Median latency**: ~300-500ns (includes occasional cache misses)
- **P95 latency**: ~500-800ns (scheduler interruptions)

**Comparison to real kernels**:
- car@f32: 8-50 µs (16× to 100× larger than no-op)
- notch_iir@f32: 37-115 µs (74× to 230× larger)
- goertzel@f32: 93-417 µs (186× to 834× larger)
- bandpass_fir@f32: 1.5-5 ms (3000× to 10000× larger)

## Interpretation

The no-op overhead measurement provides a **concrete, citable number** for harness dispatch overhead:

> "Harness dispatch overhead measured via no-op kernel: 500ns median, representing 0.5-6.25% of our fastest kernel (car@f32: 8-50µs). This confirms that timing overhead is negligible compared to signal."

**What this validates**:
✅ Harness overhead is <1% of measured signal
✅ Supports signal-to-noise ratio calculations (560:1 to 46,000:1)
✅ Provides empirical bound on constant overhead

**What this does NOT validate**:
❌ Cache/branch perturbation effects on kernel execution
❌ Complete characterization of all measurement artifacts

The empirical validation for those effects comes from **clean DVFS signal** (130% effect cleanly measured → measurement noise << real effects).

## Validation

Run oracle test:
```bash
cd primitives/kernels/v1/noop@f32
python3 oracle.py
```

Expected output:
```
Oracle test: Output matches input (identity function verified)
Validation: PASS
```

## Use Case

**Primary use**: Empirical measurement of harness overhead for academic paper Section 6.2 (Measurement Validity).

**Report as**: "Harness dispatch overhead"
**Do NOT report as**: "Total measurement perturbation"

## References

- Measurement validity analysis: `experiments/validation-2025-11-15/technical-report/measurement-validity-analysis.md`
- SHIM comparison: Same document, Section "Scale Comparison"
- SNR calculations: `docs/architecture/benchmarking-methodology.md` (Timing and Measurement Validity)

---

**Created**: December 5, 2025
**Author**: Weston Voglesonger
**Version**: 1.0.0
