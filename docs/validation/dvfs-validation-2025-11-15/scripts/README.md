# Analysis Scripts for Validation Study

This directory contains analysis scripts used to process the validation study data and generate figures for the technical report and paper.

## Scripts

### `calculate_statistical_significance.py`

Calculates statistical significance for Idle vs Medium comparison across all kernels.

**Purpose**: Generate p-values and t-statistics for paper Section 6.1

**Method**: Welch's t-test on log-transformed latencies (appropriate for log-normal latency distributions)

**Usage**:
```bash
cd experiments/dvfs-validation-2025-11-15/scripts
python3 calculate_statistical_significance.py
```

**Output**:
- Console table showing t-statistics and p-values for each kernel
- LaTeX snippet for paper inclusion
- Confirms statistical significance (p < 0.001) across all kernels

**Dependencies**:
- Python 3.x
- numpy
- scipy

**Example output**:
```
================================================================================
STATISTICAL SIGNIFICANCE ANALYSIS: Idle vs Medium
================================================================================
Kernel          n_idle   n_medium   t-statistic  p-value      Significant?
================================================================================
bandpass_fir    1203     1203       47.32        0.00e+00     ***
car             1204     1204       12.84        0.00e+00     ***
goertzel        1203     1203       23.41        0.00e+00     ***
notch_iir       1204     1204       31.19        0.00e+00     ***
```

---

### `generate_figure2_checkmark.py`

Generates Figure 2: Aggregated Kernel Latency by Load Profile showing the "checkmark pattern".

**Purpose**: Visualize aggregated median latencies across load profiles using geometric mean

**Usage**:
```bash
cd experiments/dvfs-validation-2025-11-15/scripts
python3 generate_figure2_checkmark.py
```

**Output**:
- `../figure2_checkmark_pattern.png` (300 DPI, publication quality)
- `../figure2_checkmark_pattern.pdf` (vector format)

**Dependencies**:
- Python 3.x
- matplotlib
- numpy

**Generated figure shows**:
- Medium: 123.1 µs (baseline, optimal)
- Heavy: 183.3 µs (1.49× slower due to contention)
- Idle: 284.3 µs (2.31× slower due to frequency scaling - the "Idle Paradox")

---

## Running from Project Root

If running from the project root directory, use:

```bash
# Statistical significance
python3 experiments/dvfs-validation-2025-11-15/scripts/calculate_statistical_significance.py

# Generate figure
python3 experiments/dvfs-validation-2025-11-15/scripts/generate_figure2_checkmark.py
```

---

## Data Sources

Both scripts read from:
- `../run-001-idle/kernel-data/*/telemetry.ndjson`
- `../run-002-medium/kernel-data/*/telemetry.ndjson`
- `../run-003-heavy/kernel-data/*/telemetry.ndjson` (figure script only)

All scripts use relative paths assuming execution from the `scripts/` directory.

---

## Regenerating Analysis

To regenerate all analysis artifacts:

```bash
cd experiments/dvfs-validation-2025-11-15/scripts

# 1. Calculate statistical significance
python3 calculate_statistical_significance.py > ../../technical-report/statistical-analysis-output.txt

# 2. Generate figures
python3 generate_figure2_checkmark.py
```

This recreates:
- Statistical significance tables
- Figure 2 (checkmark pattern)

---

## Notes

- **Frozen scripts**: These scripts document the analysis performed for the November 2025 validation study
- **Historical artifact**: Scripts are preserved as-is for reproducibility
- **Data integrity**: Scripts read raw NDJSON telemetry (not processed/aggregated data)
- **Future studies**: Create new script directories for future validation studies

---

## Related Documentation

- **Technical Report**: [`../technical-report/`](../technical-report/)
- **Raw Data**: [`../run-001-idle/`](../run-001-idle/), [`../run-002-medium/`](../run-002-medium/), [`../run-003-heavy/`](../run-003-heavy/)
- **Validation Overview**: [`../README.md`](../README.md)

---

**Last Updated**: December 5, 2025 (moved from root `scripts/` to validation directory)
