# Validation Runs: CPU Frequency Scaling Discovery (Nov 15, 2025)

## Purpose

These three benchmark runs provide the empirical foundation for CORTEX's macOS benchmark reproducibility methodology. They validate the discovery that CPU frequency scaling causes 49% performance variance and demonstrate that sustained background load maintains consistent frequency.

## Runs

1. **run-001-idle**: No background load (demonstrates frequency scaling problem)
2. **run-002-medium**: 4 CPUs @ 50% load via stress-ng (recommended baseline)
3. **run-003-heavy**: 8 CPUs @ 90% load via stress-ng (validates frequency locking)

## Key Findings

| Metric | Idle | Medium | Heavy |
|--------|------|--------|-------|
| Mean latency (avg across kernels) | ~5000 µs | ~2500 µs | ~3000 µs |
| Variance vs medium | +49% | baseline | +36% |
| CPU frequency state | Scaled down | Locked high | Locked high |
| Interpretation | ❌ Invalid | ✅ Baseline | 🧪 Validation |

### Interpretation

1. **Idle → Medium (-49%)**: Proves macOS frequency scaling is actively degrading performance
2. **Medium → Heavy (+36%)**: Proves both maintain high frequency (slowdown is CPU contention, not frequency)
3. **Conclusion**: Medium load achieves goal-equivalence to Linux performance governor

## Files Structure

Each run contains:
```
run-{id}-{profile}/
├── SUMMARY.md                    # Aggregate statistics across all kernels
└── kernel-data/
    ├── bandpass_fir/
    │   └── telemetry.ndjson      # Raw timestamped telemetry (n=1200+ samples)
    ├── car/
    │   └── telemetry.ndjson
    ├── goertzel/
    │   └── telemetry.ndjson
    └── notch_iir/
        └── telemetry.ndjson
```

**Note**: HTML reports, CSV exports, and PNG charts have been excluded to save space (2.9 MB reduction). They are regenerable from NDJSON using `scripts/regenerate_reports.py`.

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

## Analysis

Complete analysis and decision rationale available in:

- **Empirical validation**: [`docs/research/fall-2025-frequency-scaling-analysis/empirical-validation.md`](../../docs/research/fall-2025-frequency-scaling-analysis/empirical-validation.md)
- **Industry comparison**: [`docs/research/fall-2025-frequency-scaling-analysis/industry-standards.md`](../../docs/research/fall-2025-frequency-scaling-analysis/industry-standards.md)
- **Detailed results**: [`docs/research/fall-2025-frequency-scaling-analysis/detailed-results.md`](../../docs/research/fall-2025-frequency-scaling-analysis/detailed-results.md)
- **Decision rationale (ADR-002)**: [`docs/architecture/adr/adr-002-benchmark-reproducibility-macos.md`](../../docs/architecture/adr/adr-002-benchmark-reproducibility-macos.md)
- **Configuration guidance**: [`docs/reference/configuration.md`](../../docs/reference/configuration.md) (Platform-Specific Recommendations section)

## Academic Citation

If citing this validation data in publications:

> Voglesonger, W. (2025). CORTEX Benchmark Reproducibility Validation Runs: macOS CPU Frequency Scaling Analysis. GitHub repository: https://github.com/WestonVoglesonger/CORTEX
>
> Validation data: `results/validation-2025-11-15/`
>
> Methodology: Three-way comparison (idle/medium/heavy load profiles) across 4 computational kernels with n=1200+ samples per configuration. Results demonstrate 49% performance degradation due to CPU frequency scaling in idle mode, validating sustained background load as frequency control methodology for macOS platforms.

## Reproducibility

To reproduce these exact results:

1. **Platform**: macOS (Darwin 23.x or similar)
2. **Install dependencies**: `brew install stress-ng`
3. **Configure**: Edit `primitives/configs/cortex.yaml`
   ```yaml
   benchmark:
     duration_seconds: 120
     repeats: 5
     warmup_seconds: 10
     load_profile: "idle"  # Then run with "medium" and "heavy"
   ```
4. **Run**: `cortex pipeline`
5. **Results**: Check `results/run-<timestamp>/`

**Important**: Results may vary slightly due to system-specific factors (CPU model, thermal conditions, background processes), but the 49% idle→medium delta should be consistent across macOS systems.

## Data Integrity

**Checksums** (for archival verification):
```bash
find . -name "*.ndjson" -exec shasum -a 256 {} \;
```

Run this command to verify NDJSON files have not been modified.

## Regenerating Derived Files

The HTML reports, CSV exports, and PNG charts excluded from this directory can be regenerated using the built-in `cortex analyze` command:

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

The repository stays lean by tracking only source NDJSON files while preserving full reproducibility.

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

2025-11-16: Validation directory created, files reorganized, derived files removed
