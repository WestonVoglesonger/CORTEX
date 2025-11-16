# Fall 2025 CPU Frequency Scaling Research

This directory contains the empirical research and analysis that led to the "medium load baseline" methodology for macOS benchmarks.

## Overview

During development of CORTEX's benchmarking infrastructure for Fall 2025 academic deliverables, we discovered that **macOS CPU frequency scaling causes up to 49% performance variance** in idle mode. This finding led to the development and validation of a platform-specific methodology using sustained background load to maintain consistent CPU frequency.

## Key Findings

1. **Discovery**: macOS CPU frequency scaling causes 49% performance variance between idle and loaded states
2. **Solution**: Sustained background load (load_profile: "medium") maintains high CPU frequency
3. **Validation**: Three-way comparison (idle/medium/heavy) with n=1200+ samples per configuration
4. **Industry Comparison**: Our approach goal-equivalent to Linux performance governor, empirically validated

## Files in This Directory

### `industry-standards.md`
**Originally**: `BENCHMARK_METHODOLOGY_ANALYSIS.md`

Comprehensive analysis comparing CORTEX methodology to industry standards:
- Google Benchmark best practices
- SPEC CPU frequency control requirements
- Phoronix Test Suite recommendations
- MLPerf reproducibility guidelines

**Use**: Demonstrates that our approach aligns with (and in some ways exceeds) industry standards for benchmark reproducibility.

### `empirical-validation.md`
**Originally**: `THREE_RUN_ANALYSIS_SUMMARY.md`

Statistical analysis of the three validation runs:
- Run 1 (idle): Baseline showing frequency scaling impact
- Run 2 (medium): Recommended baseline configuration
- Run 3 (heavy): Validation that medium locks frequency

**Key Data**: The 49% discovery, 36% contention validation, statistical significance analysis.

**Use**: Provides empirical evidence for ADR-002 decision rationale.

### `detailed-results.md`
**Originally**: `BENCHMARK_COMPARISON_REPORT.md`

Complete benchmark comparison across all 4 kernels with detailed statistics:
- Per-kernel latency distributions
- Standard deviation analysis
- Percentile comparisons (P50, P95, P99)
- Sample counts and data quality metrics

**Use**: Full dataset for academic publication methodology section.

### `quick-reference.md`
**Originally**: `QUICK_REFERENCE.md`

At-a-glance summary of key metrics and findings.

**Use**: Quick lookup for paper writing, documentation references.

## Validation Data

The raw telemetry data (NDJSON format) from these three benchmark runs is preserved in:

```
results/validation-2025-11-15/
├── run-001-idle/       # Idle mode (no background load)
├── run-002-medium/     # Medium load (4 CPUs @ 50%)
└── run-003-heavy/      # Heavy load (8 CPUs @ 90%)
```

Each run contains:
- `SUMMARY.md` - Aggregate statistics
- `kernel-data/*/telemetry.ndjson` - Raw timestamped telemetry (n=1200+ samples per kernel)

## Relationship to Other Documentation

This research supports and is referenced by:

### Primary Documentation
- **ADR-002**: `docs/architecture/adr/adr-002-benchmark-reproducibility-macos.md`
  - Architecture decision record explaining the medium load baseline
  - Includes rationale, alternatives considered, consequences

- **Configuration Guide**: `docs/reference/configuration.md`
  - Platform-specific recommendations section
  - When to use each load profile

- **Methodology**: `docs/architecture/benchmarking-methodology.md`
  - CPU frequency control section
  - Comparison to industry standards

### Supporting Documentation
- **Quickstart Guide**: `docs/getting-started/quickstart.md`
  - stress-ng installation requirements

- **Roadmap**: `docs/development/roadmap.md`
  - Power config deferral explanation

## Academic Use

These findings form the methodological foundation for Fall 2025 benchmark deliverables.

### For Paper Methodology Section

**Recommended citation approach**:

> To address CPU frequency scaling on macOS (which lacks manual governor control), we employ sustained background CPU load to maintain consistent processor frequency. Our approach was empirically validated through three-way comparison (idle/medium/heavy load profiles) across 4 computational kernels with n=1200+ samples per configuration. Results demonstrated that idle mode exhibits 49% performance degradation due to frequency scaling, while medium load maintains high frequency with minimal contention overhead (validated by 36% difference vs. heavy load). This methodology achieves goal-equivalence to Linux performance governor while being empirically validated rather than assumed.

**Data availability statement**:

> Validation data including raw telemetry (NDJSON format) and analysis is available in the CORTEX repository: `results/validation-2025-11-15/` and `docs/research/fall-2025-frequency-scaling-analysis/`. Complete methodology rationale documented in ADR-002.

### For Reviewer Questions

Common questions and where to find answers:

**Q: "Why background load instead of disabling frequency scaling?"**
- **A**: See `industry-standards.md` and ADR-002
- macOS doesn't expose manual governor control (unlike Linux)
- Background load achieves same goal (empirically validated)

**Q: "How do you know this approach is valid?"**
- **A**: See `empirical-validation.md`
- Three-way comparison proves frequency control works
- Medium vs heavy delta proves both lock frequency

**Q: "What is the performance overhead?"**
- **A**: See `detailed-results.md`
- 36% vs heavy (CPU contention)
- But "theoretical minimum" (idle with locked freq) not achievable on macOS

**Q: "How does this compare to standards?"**
- **A**: See `industry-standards.md`
- Goal-equivalent to Linux performance governor
- Actually stronger: empirically validated vs assumed

## Workshop Paper Potential

The findings in this directory could form the basis for a workshop paper on macOS benchmark reproducibility:

**Potential Title**: "Addressing CPU Frequency Scaling in macOS Benchmark Reproducibility: A Platform-Specific Methodology"

**Target Venues**: ReQuEST, WDDD (Duplicating, Deconstructing, and Debunking workshop)

**Key Contributions**:
1. First empirical characterization of macOS frequency scaling impact on benchmarks (49% variance)
2. Platform-specific methodology achieving goal-equivalence to industry standards
3. Empirical validation framework (three-way comparison approach)

See workshop paper outline (if created) for full structure.

## Reproducibility

To reproduce these findings:

1. **Platform**: macOS (Darwin 23.2.0 or similar)
2. **Install dependencies**: `brew install stress-ng`
3. **Configure**: Set `load_profile: idle|medium|heavy` in `primitives/configs/cortex.yaml`
4. **Run**: `cortex pipeline` or `cortex run <kernel>`
5. **Analyze**: Results in `results/run-<timestamp>/`

System specifications for original runs are embedded in telemetry NDJSON files.

## Maintenance

**This is frozen research**: These files document a specific point-in-time discovery (November 2025). They should not be modified except for:
- Fixing typos or formatting
- Adding clarifying notes in separate sections
- Updating cross-references if documentation structure changes

For future benchmark methodology updates, create new research directories with appropriate timestamps.

## Authors

- Weston Voglesonger (@WestonVoglesonger)
- With assistance from Claude Code (Anthropic)

## Last Updated

2025-11-16: Research directory created, analysis files preserved from repository root
