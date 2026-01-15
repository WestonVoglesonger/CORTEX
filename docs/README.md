# CORTEX Documentation

Complete documentation for the CORTEX BCI Kernel Benchmarking Pipeline.

## Getting Started

Perfect for new users who want to quickly start using CORTEX.

| Document | Description |
|----------|-------------|
| [Quick Start Guide](getting-started/quickstart.md) | 5-minute setup and first benchmark |
| [Building Your First Kernel](getting-started/first-kernel-tutorial.md) | Hands-on tutorial: Implement a simple moving average filter (1-2 hours) |
| [CLI Usage Guide](getting-started/cli-usage.md) | Complete command reference and workflows |

**Start here**: If this is your first time with CORTEX, begin with the [Quick Start Guide](getting-started/quickstart.md).

---

## Reference

Authoritative technical specifications and schemas.

| Document | Description |
|----------|-------------|
| [Plugin Interface Specification](reference/plugin-interface.md) | Complete ABI v3 specification for kernel plugins |
| [Configuration Schema](reference/configuration.md) | YAML configuration file reference |
| [Telemetry Format](reference/telemetry.md) | NDJSON/CSV output schema and metrics |
| [Dataset Documentation](reference/dataset.md) | PhysioNet EEG dataset format and handling |

**Use this section**: When you need exact function signatures, configuration options, or data formats.

---

## Architecture

High-level system design and implementation rationale.

| Document | Description |
|----------|-------------|
| [System Overview](architecture/overview.md) | Component architecture and data flow |
| [Testing Strategy](architecture/testing-strategy.md) | Software testing practices, test suites, and quality assurance |
| [Benchmarking Methodology](architecture/benchmarking-methodology.md) | HIL measurement philosophy and deployment realism |
| [Platform Compatibility](architecture/platform-compatibility.md) | macOS and Linux cross-platform implementation |

**Use this section**: To understand how CORTEX works internally and why design decisions were made.

---

## Guides

Step-by-step instructions for common tasks.

| Document | Description |
|----------|-------------|
| [Adding New Kernels](guides/adding-kernels.md) | Complete guide to kernel development (spec → oracle → C → validation) |
| [Troubleshooting](guides/troubleshooting.md) | Common issues and solutions |

**Use this section**: When implementing new features or solving problems.

---

## Research & Validation Studies

Academic foundations and empirical validation of measurement practices.

| Document | Description |
|----------|-------------|
| [Literature Positioning](research/literature-positioning.md) | How CORTEX relates to existing BCI benchmarking research |
| [Benchmarking Philosophy](research/benchmarking-philosophy.md) | Realistic vs ideal performance measurement trade-offs |
| [Measurement Analysis](research/measurement-analysis.md) | Statistical analysis of small kernel measurement noise |

**Validation Studies**: Timestamped empirical experiments in [`../docs/validation/`](../docs/validation/):
- [Linux Governor Validation (2025-12-05)](../docs/validation/linux-governor-validation-2025-12-05/) - Idle Paradox and DVFS impact on latency
- [No-op Overhead (2025-12-05)](../docs/validation/noop-overhead-2025-12-05/) - Harness overhead measurement baseline
- [High-Channel Scalability (2026-01-12)](../docs/validation/high-channel-scalability-2026-01-12/) - 2048-channel synthetic dataset validation

**Use this section**: To understand theoretical foundations and see reproducibility-focused validation of measurement claims.

---

## Development

Project planning, contribution guidelines, and historical context.

| Document | Description |
|----------|-------------|
| [Project Roadmap](development/roadmap.md) | Implementation status, timeline, and current semester goals |
| [Future Enhancements](development/future-enhancements.md) | Planned features, deferred implementations, and long-term vision |
| [Archive](development/archive/) | Historical design documents |

**Use this section**: For contributing to CORTEX or understanding project evolution.

**See also**: [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines and code style.

---

## 📄 License & Citation

- **License**: MIT (see [LICENSE](../LICENSE))
- **Citation**: See [CITATION.cff](../CITATION.cff) for BibTeX
- **Dataset License**: PhysioNet EEG under ODC-By 1.0

---

## 🆘 Need Help?

1. Check [Troubleshooting Guide](guides/troubleshooting.md)
2. Search [GitHub Issues](https://github.com/WestonVoglesonger/CORTEX/issues)
3. Review [Architecture Overview](architecture/overview.md)
4. See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines