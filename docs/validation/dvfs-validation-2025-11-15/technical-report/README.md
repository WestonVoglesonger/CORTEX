# Technical Report: CPU Frequency Scaling Validation Study

**Study Date**: November 15-16, 2025
**CORTEX Version**: v0.2.0
**Platform**: macOS (Darwin 23.2.0), Apple M1

This directory contains the complete technical documentation for the three-way validation study that discovered and characterized CPU frequency scaling effects on macOS benchmark reproducibility.

---

## Study Overview

During development of CORTEX's benchmarking infrastructure, we discovered that **macOS CPU frequency scaling causes idle systems to be ~2.3× slower** than medium-load systems (geometric mean of median latencies). This finding led to the development and validation of a platform-specific methodology using sustained background load to maintain consistent CPU frequency.

### Key Findings

1. **Discovery**: macOS CPU frequency scaling causes idle systems to be ~2.3× slower than medium-load systems
2. **Solution**: Sustained background load (load_profile: "medium") maintains high CPU frequency
3. **Validation**: Three-way comparison (idle/medium/heavy) with n=1200+ samples per configuration
4. **Industry Alignment**: Approach is goal-equivalent to Linux performance governor, empirically validated

---

## Files in This Directory

### Primary Technical Reports

#### `COMPREHENSIVE_VALIDATION_REPORT.md` (1,942 lines)
Complete technical report documenting the entire validation study:
- Full experimental design and methodology
- Per-kernel analysis with statistical metrics (n=1200+ samples per kernel)
- Outlier characterization and temporal stability analysis
- Comparison to industry standards (Google Benchmark, SPEC CPU, Phoronix)
- Implications for benchmark reproducibility

**Use**: Primary reference for methodology sections, reviewer questions, complete study documentation.

#### `measurement-validity-analysis.md` (986 lines)
In-depth analysis of CORTEX's timing methodology and measurement validity:
- Comparison to SHIM (ISCA 2015) cycle-level profiling methodology
- Observer effect quantification and scale analysis (1,600× to 277,777× coarser measurement scale)
- Signal-to-noise ratio calculations (560:1 to 46,000:1)
- Evidence that frequency scaling (130% effect) dominates measurement artifacts (<1%)
- Cost-benefit analysis of measurement hardening approaches

**Use**: Addresses measurement rigor questions. Demonstrates why SHIM-style hardening (separate observer threads, hardware counters) is unnecessary at CORTEX's µs-ms measurement scale. Essential for defending measurement methodology.

### Supporting Analysis Documents

#### `detailed-results.md` (608 lines)
Complete benchmark comparison across all 4 kernels with detailed statistics:
- Per-kernel latency distributions (idle/medium/heavy configurations)
- Standard deviation and coefficient of variation analysis
- Percentile comparisons (P50, P95, P99, P99.9, Max)
- Sample counts and data quality metrics
- Full statistical tables for academic publication

**Use**: Complete dataset for paper methodology sections and supplementary materials.

#### `empirical-validation.md` (152 lines)
Statistical analysis summary of the three validation runs:
- Run 1 (idle): Baseline showing frequency scaling impact
- Run 2 (medium): Recommended baseline configuration
- Run 3 (heavy): Validation that medium locks frequency
- Geometric mean aggregation methodology
- Statistical significance analysis (p-values, effect sizes)

**Use**: Concise empirical evidence for architecture decision records (ADR-002).

#### `industry-standards.md` (321 lines)
Comprehensive analysis comparing CORTEX methodology to industry benchmarking standards:
- Google Benchmark best practices
- SPEC CPU frequency control requirements
- Phoronix Test Suite recommendations
- MLPerf reproducibility guidelines

**Use**: Demonstrates that CORTEX's approach aligns with (and in some ways exceeds) industry standards for benchmark reproducibility.

#### `quick-reference.md` (183 lines)
At-a-glance summary of key metrics and findings:
- Summary tables with key statistics
- Quick lookup for paper writing
- Cross-references to detailed sections

**Use**: Fast reference during paper writing and documentation.

---

## Raw Data and Visualizations

### Data Files
Located in parent directory (`../`):
```
run-001-idle/
├── kernel-data/
│   ├── car/telemetry.ndjson         (n=1204 samples)
│   ├── bandpass_fir/telemetry.ndjson (n=1203 samples)
│   ├── goertzel/telemetry.ndjson    (n=1203 samples)
│   └── notch_iir/telemetry.ndjson   (n=1204 samples)

run-002-medium/
└── kernel-data/ [same structure]

run-003-heavy/
└── kernel-data/ [same structure]
```

### Visualizations
```
../aggregated_median_latency_comparison.png  # Cross-kernel comparison
../cross_run_median_latency_comparison.png   # Per-kernel detailed view
../figure2_checkmark_pattern.png             # Temporal degradation pattern (checkmark)
../figure2_checkmark_pattern.pdf             # Publication-quality vector format
```

### Analysis Scripts
Custom analysis scripts are located in **[`../scripts/`](../scripts/)**:
- `calculate_statistical_significance.py` - Statistical analysis (p-values, t-tests)
- `generate_figure2_checkmark.py` - Figure generation for checkmark pattern

See **[`../scripts/README.md`](../scripts/README.md)** for usage instructions and dependencies.

---

## Relationship to Project Documentation

This validation study informed several key project documents:

### Architecture Decisions
- **ADR-002**: `docs/architecture/adr/adr-002-benchmark-reproducibility-macos.md`
  - Architecture decision record explaining the medium load baseline
  - Rationale, alternatives considered, consequences

### Methodology Documentation
- **Benchmarking Methodology**: `docs/architecture/benchmarking-methodology.md`
  - CPU frequency control section (references this study)
  - Timing and measurement validity section (links to measurement-validity-analysis.md)

### Configuration Guidance
- **Configuration Guide**: `docs/reference/configuration.md`
  - Platform-specific recommendations
  - When to use each load profile

### Supporting Documentation
- **Quickstart Guide**: `docs/getting-started/quickstart.md` - stress-ng installation
- **Roadmap**: `docs/development/roadmap.md` - Power config deferral explanation

---

## Academic Use

### For Paper Methodology Sections

**Recommended citation approach**:

> To address CPU frequency scaling on macOS (which lacks manual governor control), we employ sustained background CPU load to maintain consistent processor frequency. Our approach was empirically validated through three-way comparison (idle/medium/heavy load profiles) across 4 computational kernels with n=1200+ samples per configuration. Results demonstrated that idle mode exhibits ~2.3× slower performance due to frequency scaling (geometric mean of median latencies), while medium load maintains high frequency with minimal contention overhead (validated by ~1.5× difference vs. heavy load). This methodology achieves goal-equivalence to Linux performance governor while being empirically validated rather than assumed.

**Data availability statement**:

> Validation data including raw telemetry (NDJSON format) and complete technical analysis is available in the CORTEX repository: `experiments/dvfs-validation-2025-11-15/` (data) and `experiments/dvfs-validation-2025-11-15/technical-report/` (analysis). Complete methodology rationale is documented in ADR-002.

### For Reviewer Questions

Common questions and where to find answers:

| Question | Answer Location |
|----------|----------------|
| "Why background load instead of disabling frequency scaling?" | `industry-standards.md` and ADR-002 (macOS doesn't expose manual governor control) |
| "How do you know this approach is valid?" | `empirical-validation.md` (three-way comparison proves frequency control works) |
| "What is the performance overhead?" | `detailed-results.md` (36% vs heavy due to CPU contention, not frequency) |
| "How does this compare to standards?" | `industry-standards.md` (goal-equivalent to Linux performance governor, empirically validated) |
| "Could measurement artifacts explain the effect?" | `measurement-validity-analysis.md` (frequency scaling 35-208× larger than possible measurement noise) |

---

## Reproducibility

### Prerequisites
- **Platform**: macOS (Darwin 23.2.0 or similar, Apple Silicon or Intel)
- **Dependencies**: `brew install stress-ng`
- **CORTEX**: Clone repository and build (see main README)

### Reproduction Steps

1. **Configure** load profiles in `primitives/configs/cortex.yaml`:
   ```yaml
   load_profile: "idle"   # or "medium" or "heavy"
   ```

2. **Run** benchmarks:
   ```bash
   cortex pipeline  # Runs all configured kernels
   # OR
   cortex run <kernel-name>  # Single kernel
   ```

3. **Analyze** results:
   ```bash
   cortex analyze results/run-<timestamp>/
   ```

### System Specifications
Original validation runs used:
- Apple M1 (8 cores), 8GB RAM
- macOS Darwin 23.2.0
- Apple Clang compiler
- CORTEX v0.2.0
- EEG Motor Movement/Imagery Database (PhysioNet)

System specifications are also embedded in telemetry NDJSON files (`_type: system_info`).

---

## Workshop Paper Potential

The findings in this directory could form the basis for a workshop paper on macOS benchmark reproducibility:

**Potential Title**: "Addressing CPU Frequency Scaling in macOS Benchmark Reproducibility: A Platform-Specific Methodology"

**Target Venues**:
- ReQuEST (Reproducible Quality-Efficient Systems Tournament)
- WDDD (Duplicating, Deconstructing, and Debunking workshop)

**Key Contributions**:
1. First empirical characterization of macOS frequency scaling impact on benchmarks (~2.3× degradation)
2. Platform-specific methodology achieving goal-equivalence to industry standards
3. Empirical validation framework (three-way comparison approach)
4. Measurement validity analysis (SHIM comparison, observer effect quantification)

---

## Maintenance

**This is frozen research**: These files document a specific point-in-time study (November 2025). They should not be modified except for:
- Fixing typos or formatting
- Adding clarifying notes in separate sections
- Updating cross-references if project structure changes

For future benchmark methodology updates or validation studies, create new directories with appropriate timestamps (e.g., `results/validation-2026-XX-XX/`).

---

## Citation

If you use this validation methodology or reference these findings, please cite:

```
Weston Voglesonger. (2025). CORTEX CPU Frequency Scaling Validation Study.
Technical Report, dvfs-validation-2025-11-15.
Available: https://github.com/[your-org]/CORTEX/tree/main/experiments/dvfs-validation-2025-11-15/
```

---

## Authors

- Weston Voglesonger (@WestonVoglesonger)
- With assistance from Claude Code (Anthropic)

## Timeline

- **2025-11-15**: Initial validation runs conducted
- **2025-11-16**: Analysis completed, research directory created
- **2025-12-05**: Reorganized as technical report (supplementary materials for validation data)

---

## Related Work

### Industry Benchmarking Standards
- Google Benchmark: CPU frequency pinning best practices
- SPEC CPU: Performance governor requirements
- Phoronix Test Suite: Reproducibility guidelines

### Academic Systems Research
- SHIM (ISCA 2015): Computer Performance Microscopy with fine-grained measurement
- MNE-Python: BCI analysis tooling
- BCI2000: Real-time brain-computer interface framework

### Reproducibility Research
- PLOS Computational Biology: Ten simple rules for documenting scientific software
- NIH Workshops: Computational reproducibility challenges
- ACM Reproducibility Initiatives

---

For questions about this validation study or to report issues with reproducibility, please open an issue in the main CORTEX repository.
