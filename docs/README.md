# CORTEX Documentation

Complete documentation for the CORTEX BCI Kernel Benchmarking Pipeline.

## Getting Started

Perfect for new users who want to quickly start using CORTEX.

| Document | Description |
|----------|-------------|
| [Quick Start Guide](getting-started/quickstart.md) | 5-minute setup and first benchmark |
| [CLI Usage Guide](getting-started/cli-usage.md) | Complete command reference and workflows |

**Start here**: If this is your first time with CORTEX, begin with the [Quick Start Guide](getting-started/quickstart.md).

---

## Reference

Authoritative technical specifications and schemas.

| Document | Description |
|----------|-------------|
| [Plugin Interface Specification](reference/plugin-interface.md) | Complete ABI v2 specification for kernel plugins |
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