# No-Op Harness Overhead Technical Report

This directory contains comprehensive technical analysis of the CORTEX harness overhead measurement study using a no-op (identity) kernel.

---

## Documents

### **HARNESS_OVERHEAD_ANALYSIS.md**
Complete technical analysis of harness overhead decomposition, environmental effects, and measurement methodology validation.

**Contents:**
- Executive summary with key findings
- Experimental methodology and configuration
- Statistical analysis (Welch's t-test, Cohen's d effect size)
- Overhead decomposition (harness vs environmental)
- Signal-to-noise ratio validation for all kernels
- Cross-profile comparison (idle vs medium)
- Measurement validity evidence
- Variability analysis (run-to-run consistency)

---

## Key Results Summary

### Harness Overhead Measurement
- **True harness overhead**: 1 µs (minimum across both profiles)
- **Components**: timing (100ns) + dispatch (50-100ns) + memcpy (800ns) + bookkeeping (100ns)
- **Stability**: Identical minimum (1µs) across idle and medium profiles

### Environmental Effects
- **Idle profile**: +4µs DVFS penalty (median = 5µs)
- **Medium profile**: +3µs stress-ng effects (median = 4µs)
- **Variability**: ±50% between runs due to macOS DVFS non-determinism

### Statistical Significance
- **Welch's t-test**: p < 0.000001 (highly significant)
- **Cohen's d**: 0.5309 (medium effect size)
- **Sample size**: n=2399 total (1199 idle, 1200 medium)

### Signal-to-Noise Validation
- **car@f32**: 8:1 to 50:1 (borderline worst-case, excellent typical)
- **notch_iir@f32**: 37:1 to 115:1 ✅
- **goertzel@f32**: 93:1 to 417:1 ✅
- **bandpass_fir@f32**: 1500:1 to 5000:1 ✅
- **Industry standard**: 10:1 SNR (all kernels exceed using median latency)

---

## Purpose

This study validates two critical CORTEX measurement methodology claims:

1. **Harness overhead is negligible** (<13% for all kernels, <3% for kernels >30µs)
2. **Environmental effects dominate** (DVFS penalty 4× larger than harness overhead)

By isolating the harness overhead using a no-op kernel that performs minimal computation (identity function), we can:
- Measure the true measurement floor (1µs)
- Separate harness overhead from environmental noise
- Validate SNR for all CORTEX kernels
- Prove that frequency scaling is the dominant measurement threat

---

## Relationship to Other Experiments

### dvfs-validation-2025-11-15 (macOS DVFS Discovery)
- **Relationship**: noop-overhead provides the harness baseline referenced in DVFS analysis
- **Finding**: DVFS effect (2.31×) is 130× larger than harness overhead (1µs)
- **Validation**: Confirms that observer effects are negligible at CORTEX's measurement scale

### linux-governor-validation-2025-12-05 (Linux DVFS Replication)
- **Relationship**: noop-overhead validates measurement methodology across both platforms
- **Finding**: Harness overhead (1µs) is platform-independent C code
- **Recommendation**: Run noop-overhead on Linux to confirm cross-platform consistency

---

## Citation

When referencing this study in papers or documentation:

> Harness dispatch overhead was measured empirically using a no-op kernel (identity function) across two load profiles (idle and medium) on macOS. The minimum latency of 1 µs (n=2399 samples) represents the true harness overhead independent of environmental factors. Environmental effects (DVFS penalty: +4µs idle, stress-ng effects: +3µs medium) are 3-4× larger than harness overhead, validating that frequency scaling is the dominant measurement threat at CORTEX's microsecond-to-millisecond scale.

**Data location**: `experiments/noop-overhead-2025-12-05/`
**Automation**: `./scripts/run-experiment.sh` (full reproducibility)

---

## Authors

- Weston Voglesonger (@WestonVoglesonger)
- With assistance from Claude Code (Anthropic)

**Last Updated**: December 6, 2025
