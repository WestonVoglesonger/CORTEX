# Validation Runs: CPU Frequency Scaling Discovery (Nov 15, 2025)

## Purpose

These three benchmark runs provide the empirical foundation for CORTEX's macOS benchmark reproducibility methodology. They validate the discovery that CPU frequency scaling causes idle systems to be **~2× slower** than medium-load systems (aggregated across all kernels using geometric mean) and demonstrate that sustained background load maintains consistent frequency.

## Runs

1. **run-001-idle**: No background load (demonstrates frequency scaling problem)
2. **run-002-medium**: 4 CPUs @ 50% load via stress-ng (recommended baseline)
3. **run-003-heavy**: 8 CPUs @ 90% load via stress-ng (validates frequency locking)

## Key Findings

| Metric | Idle | Medium | Heavy |
|--------|------|--------|-------|
| Aggregated median latency (geometric mean) | ~284 µs | ~123 µs | ~180 µs |
| Performance vs medium | **~2.3× slower** | baseline | ~1.5× slower |
| CPU frequency state | Scaled down | Locked high | Locked high |
| Interpretation | ❌ Invalid | ✅ Baseline | 🧪 Validation |

### Aggregation Method

**Geometric mean** is used to aggregate median latencies across all four kernels (bandpass_fir, car, goertzel, notch_iir) because:
- Kernels span multiple orders of magnitude (tens to thousands of microseconds)
- Geometric mean ensures each kernel contributes proportionally rather than being dominated by the largest kernel
- This is the statistically appropriate method for multiplicative relationships

**Calculation**: Geometric mean = exp(mean(log(median_latencies))) for each load profile.

### Interpretation

1. **Idle → Medium (~2.3× slower)**: Proves macOS frequency scaling is actively degrading performance
2. **Medium → Heavy (~1.5× slower)**: Proves both maintain high frequency (slowdown is CPU contention, not frequency)
3. **Conclusion**: Medium load achieves goal-equivalence to Linux performance governor

## Files Structure

```
experiments/dvfs-validation-2025-11-15/
├── README.md                         # This file
├── config-idle.yaml                  # Configuration for idle run
├── config-medium.yaml                # Configuration for medium run
├── config-heavy.yaml                 # Configuration for heavy run
├── figures/                          # Generated visualizations
│   ├── aggregated_median_latency_comparison.png
│   ├── cross_run_median_latency_comparison.png
│   ├── figure2_checkmark_pattern.png
│   └── figure2_checkmark_pattern.pdf
├── run-001-idle/                     # Idle profile results
│   ├── SUMMARY.md
│   └── kernel-data/
│       ├── bandpass_fir/telemetry.ndjson (n=1203)
│       ├── car/telemetry.ndjson (n=1204)
│       ├── goertzel/telemetry.ndjson (n=1203)
│       └── notch_iir/telemetry.ndjson (n=1204)
├── run-002-medium/                   # Medium profile results (recommended baseline)
│   ├── SUMMARY.md
│   └── kernel-data/ (n=1200+ per kernel)
├── run-003-heavy/                    # Heavy profile results (validation)
│   ├── SUMMARY.md
│   └── kernel-data/ (n=1200+ per kernel)
├── scripts/                          # Analysis scripts
│   ├── README.md
│   ├── calculate_statistical_significance.py
│   └── generate_figure2_checkmark.py
└── technical-report/                 # Complete technical analysis
    ├── README.md
    ├── COMPREHENSIVE_VALIDATION_REPORT.md
    ├── measurement-validity-analysis.md
    ├── detailed-results.md
    ├── empirical-validation.md
    ├── industry-standards.md
    └── quick-reference.md
```

**Note**: HTML reports and CSV exports have been excluded to save space. Raw NDJSON telemetry files are preserved for full reproducibility.

## System Configuration

**Platform**: macOS (Darwin 23.2.0)

**Benchmark Parameters**:
- Duration: 120 seconds per kernel
- Repeats: 5 per kernel
- Warmup: 10 seconds
- Sample size: n=1200+ per kernel per configuration

**Load Profiles**:
- **idle**: No background load
- **medium**: `stress-ng --cpu 4 --cpu-load 50`
- **heavy**: `stress-ng --cpu 8 --cpu-load 90`

**System specifications** captured in each `telemetry.ndjson` file (hostname, CPU model, memory, thermal state).

## Technical Report

Complete analysis and documentation available in the **[technical-report/](technical-report/)** directory:

### Comprehensive Reports
- **Complete validation study**: [`technical-report/COMPREHENSIVE_VALIDATION_REPORT.md`](technical-report/COMPREHENSIVE_VALIDATION_REPORT.md) - Full experimental design, methodology, and analysis (1,942 lines)
- **Measurement validity**: [`technical-report/measurement-validity-analysis.md`](technical-report/measurement-validity-analysis.md) - SHIM comparison, observer effect analysis, SNR calculations (986 lines)
- **Detailed results**: [`technical-report/detailed-results.md`](technical-report/detailed-results.md) - Complete statistical tables for all kernels (608 lines)

### Supporting Analysis
- **Empirical validation**: [`technical-report/empirical-validation.md`](technical-report/empirical-validation.md) - Statistical summary and significance testing
- **Industry comparison**: [`technical-report/industry-standards.md`](technical-report/industry-standards.md) - Comparison to Google Benchmark, SPEC CPU, Phoronix
- **Quick reference**: [`technical-report/quick-reference.md`](technical-report/quick-reference.md) - At-a-glance metrics and findings

See [`technical-report/README.md`](technical-report/README.md) for complete documentation, academic citation guidance, and reviewer Q&A.

### Project Documentation
- **Decision rationale (ADR-002)**: [`docs/architecture/adr/adr-002-benchmark-reproducibility-macos.md`](../../docs/architecture/adr/adr-002-benchmark-reproducibility-macos.md)
- **Benchmarking methodology**: [`docs/architecture/benchmarking-methodology.md`](../../docs/architecture/benchmarking-methodology.md) (CPU frequency control and timing validity sections)
- **Configuration guidance**: [`docs/reference/configuration.md`](../../docs/reference/configuration.md) (Platform-Specific Recommendations)

## Academic Citation

If citing this validation data in publications:

> Voglesonger, W. (2025). CORTEX Benchmark Reproducibility Validation Runs: macOS CPU Frequency Scaling Analysis. GitHub repository: https://github.com/WestonVoglesonger/CORTEX
>
> Validation data: `experiments/dvfs-validation-2025-11-15/`
>
> Methodology: Three-way comparison (idle/medium/heavy load profiles) across 4 computational kernels with n=1200+ samples per configuration. Results demonstrate that idle systems are **~2.3× slower** than medium-load systems (geometric mean of median latencies), validating sustained background load as frequency control methodology for macOS platforms.

## Configuration Files

For reproducibility, the exact configurations used to generate these runs are preserved:

```
experiments/dvfs-validation-2025-11-15/
├── config-idle.yaml      # Run 001: Idle profile configuration
├── config-medium.yaml    # Run 002: Medium profile configuration
└── config-heavy.yaml     # Run 003: Heavy profile configuration
```

Each configuration specifies:
- All 4 BCI kernels (car, notch_iir, goertzel, bandpass_fir)
- Kernel parameters (e.g., notch frequency=60Hz, goertzel target=10Hz)
- Duration: 120s per kernel
- Repeats: 5 per kernel
- Warmup: 10s
- Load profile: idle / medium / heavy

## Reproducibility

To reproduce these exact results:

1. **Platform**: macOS (Darwin 23.x or similar), Apple Silicon recommended
2. **Install dependencies**: `brew install stress-ng`
3. **Dataset**: Use `datasets/eegmmidb/converted/S001R03.float32`
4. **Build kernels**: `make plugins`
5. **Run experiments** using provided configurations:

```bash
# Idle profile (demonstrates DVFS problem)
cortex run --config experiments/dvfs-validation-2025-11-15/config-idle.yaml \
  --run-name validation-idle

# Medium profile (recommended baseline)
cortex run --config experiments/dvfs-validation-2025-11-15/config-medium.yaml \
  --run-name validation-medium

# Heavy profile (validates frequency locking)
cortex run --config experiments/dvfs-validation-2025-11-15/config-heavy.yaml \
  --run-name validation-heavy
```

6. **Analyze**: Use scripts in [`scripts/`](scripts/) directory for statistical analysis

**Expected results**:
- Sample size: n=1200+ per kernel per configuration (4 kernels × 3 profiles = 12 runs total)
- Idle ~2.3× slower than medium (geometric mean across kernels)
- Heavy ~1.5× slower than medium (validates frequency locking)

**Important**: Results may vary slightly due to system-specific factors (CPU model, thermal conditions, background processes), but the **~2× slower** idle→medium performance difference should be consistent across macOS systems.

## Data Integrity

**Checksums** (for archival verification):
```bash
find . -name "*.ndjson" -exec shasum -a 256 {} \;
```

Run this command to verify NDJSON files have not been modified.

## Analysis Scripts

Custom analysis scripts used for this validation study are in the **[scripts/](scripts/)** directory:

### Statistical Analysis
```bash
cd scripts/
python3 calculate_statistical_significance.py
```
Generates p-values and t-statistics confirming statistical significance (p < 0.001) for idle vs medium comparison across all kernels.

### Figure Generation
```bash
cd scripts/
python3 generate_figure2_checkmark.py
```
Generates `figure2_checkmark_pattern.png` and `.pdf` showing the aggregated "checkmark pattern" across load profiles.

See **[scripts/README.md](scripts/README.md)** for detailed documentation, dependencies, and usage instructions.

## Regenerating Built-in Reports

The built-in HTML reports and CSV exports can be regenerated using the `cortex analyze` command:

```bash
# Regenerate for a specific run
cortex analyze --run-name run-001-idle

# Or regenerate all runs
for run in run-001-idle run-002-medium run-003-heavy; do
    cortex analyze --run-name $run
done
```

This generates:
- Analysis plots (PNG format): `<run-dir>/analysis/*.png`
- Summary statistics: `<run-dir>/analysis/SUMMARY.md`

The repository stays lean by tracking only source NDJSON files and custom analysis scripts while preserving full reproducibility.

## Archival Status

**Repository**: Tracked in git (essential validation data)
**External Archive**: [TBD - will be archived to Zenodo upon paper submission with DOI]

## Maintenance Notes

**This is frozen validation data**: These files document a specific point-in-time discovery (November 2025). They should not be modified except for:
- Adding clarifying documentation
- Fixing metadata errors
- Adding external archive links (Zenodo DOI)

For future validation runs, create new directories with appropriate timestamps (e.g., `validation-YYYY-MM-DD/`).

## Authors

- Weston Voglesonger (@WestonVoglesonger)
- With assistance from Claude Code (Anthropic)

## Last Updated

2025-11-26: Updated notch_iir idle data (22→1204 samples), regenerated analysis, standardized on geometric mean aggregation (~2.3× slower idle vs medium)
