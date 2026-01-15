# Research & Analysis

Academic papers, measurement philosophy, and theoretical foundations underlying CORTEX design decisions.

---

## Contents

- **[Literature Positioning](literature-positioning.md)** - How CORTEX relates to existing BCI benchmarking research
- **[Benchmarking Philosophy](benchmarking-philosophy.md)** - Realistic vs ideal performance measurement trade-offs
- **[Measurement Analysis](measurement-analysis.md)** - Statistical analysis of small kernel measurement noise

---

## Purpose

This directory contains the theoretical and empirical research that informs CORTEX's architecture. Unlike `docs/architecture/` (which describes the system) or `docs/guides/` (which shows how to use it), these documents explain **why** specific design decisions were made and how they relate to the broader academic literature.

---

## When to Read These

- **Before citing CORTEX**: Review literature positioning to understand novelty claims
- **When questioning measurement validity**: See measurement analysis for noise characterization
- **During architecture discussions**: Benchmarking philosophy explains trade-off rationale

---

## See Also

- **Validation Studies**: [`experiments/`](../../experiments/) contains timestamped empirical validation (Idle Paradox, DVFS, etc.)
- **Technical Reports**: Individual experiment directories contain full methodology, results, and reproducibility instructions
