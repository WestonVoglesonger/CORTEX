# CORTEX
## Common Off-implant Runtime Test Ecosystem for BCI Kernels

### Master Specification
**Weston Voglesonger | Advisor: Dr. Raghavendra Pothukuchi**
University of North Carolina at Chapel Hill | Spring 2026

---

## Executive Summary

CORTEX is a benchmarking framework for BCI signal-processing kernels on real deployment hardware. It provides oracle-validated correctness, distributional latency reporting (P50/P95/P99), and controlled measurement under platform effects (DVFS, thermal throttling, scheduling noise). Unlike MOABB (offline accuracy evaluation) and BCI2000/OpenViBE (runtime platforms for controlled lab environments), CORTEX targets deployment-grade performance engineering on commodity edge devices—phones, wearables, and embedded Linux SoCs—where platform state dictates real-time safety as much as algorithmic complexity.

This specification establishes CORTEX's requirements by tracing from user needs through methodological principles to system capabilities and architecture. It follows a top-down structure: the BCI deployment problem motivates user needs, which reduce to five methodological principles, which are embodied in system capabilities and architecture.