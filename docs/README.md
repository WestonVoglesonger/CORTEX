# CORTEX Documentation

Complete documentation for the CORTEX BCI Kernel Benchmarking Pipeline.

## 🚀 Getting Started

Perfect for new users who want to quickly start using CORTEX.

| Document | Description |
|----------|-------------|
| [Quick Start Guide](getting-started/quickstart.md) | 5-minute setup and first benchmark |
| [CLI Usage Guide](getting-started/cli-usage.md) | Complete command reference and workflows |

**Start here**: If this is your first time with CORTEX, begin with the [Quick Start Guide](getting-started/quickstart.md).

---

## 📖 Reference

Authoritative technical specifications and schemas.

| Document | Description |
|----------|-------------|
| [Plugin Interface Specification](reference/plugin-interface.md) | Complete ABI v2 specification for kernel plugins |
| [Kernel Specifications](reference/kernels.md) | Mathematical definitions for all signal processing kernels |
| [Configuration Schema](reference/configuration.md) | YAML configuration file reference |
| [Telemetry Format](reference/telemetry.md) | NDJSON/CSV output schema and metrics |
| [Dataset Documentation](reference/dataset.md) | PhysioNet EEG dataset format and handling |

**Use this section**: When you need exact function signatures, configuration options, or data formats.

---

## 🏗️ Architecture

High-level system design and implementation rationale.

| Document | Description |
|----------|-------------|
| [System Overview](architecture/overview.md) | Component architecture and data flow |
| [Testing Strategy](architecture/testing-strategy.md) | HIL methodology and validation approach |
| [Sequential Execution](architecture/sequential-execution.md) | Design rationale for sequential plugin execution |
| [Platform Compatibility](architecture/platform-compatibility.md) | macOS and Linux cross-platform implementation |

**Use this section**: To understand how CORTEX works internally and why design decisions were made.

---

## 📝 Guides

Step-by-step instructions for common tasks.

| Document | Description |
|----------|-------------|
| [Adding New Kernels](guides/adding-kernels.md) | Complete guide to kernel development (spec → oracle → C → validation) |
| [Benchmark Duration Guidelines](guides/benchmark-duration.md) | Statistical rigor and recommended benchmark lengths |
| [Dataset Preparation](guides/dataset-preparation.md) | Converting EDF+ files to CORTEX format |
| [Troubleshooting](guides/troubleshooting.md) | Common issues and solutions |

**Use this section**: When implementing new features or solving problems.

---

## 🔧 Development

Project planning, contribution guidelines, and historical context.

| Document | Description |
|----------|-------------|
| [Project Roadmap](development/roadmap.md) | Implementation status, timeline, and future plans |
| [Developer Guide](development/developer-guide.md) | Development workflows and code conventions (see CLAUDE.md for AI assistant version) |
| [Archive](development/archive/) | Historical design documents |

**Use this section**: For contributing to CORTEX or understanding project evolution.

**External development docs**:
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines, code style, PR process
- [CLAUDE.md](../CLAUDE.md) - AI assistant instructions (comprehensive dev guide)

---

## 📚 Complete Document Index

### By Category

**Getting Started** (2 docs)
- [quickstart.md](getting-started/quickstart.md) - 5-minute setup
- [cli-usage.md](getting-started/cli-usage.md) - CLI reference

**Reference** (5 docs)
- [plugin-interface.md](reference/plugin-interface.md) - Plugin ABI v2
- [kernels.md](reference/kernels.md) - Kernel math specs
- [configuration.md](reference/configuration.md) - YAML schema
- [telemetry.md](reference/telemetry.md) - Output formats
- [dataset.md](reference/dataset.md) - EEG data format

**Architecture** (4 docs)
- [overview.md](architecture/overview.md) - System design
- [testing-strategy.md](architecture/testing-strategy.md) - HIL methodology
- [sequential-execution.md](architecture/sequential-execution.md) - Execution model
- [platform-compatibility.md](architecture/platform-compatibility.md) - Cross-platform

**Guides** (4 docs)
- [adding-kernels.md](guides/adding-kernels.md) - Kernel development
- [benchmark-duration.md](guides/benchmark-duration.md) - Statistical guidelines
- [dataset-preparation.md](guides/dataset-preparation.md) - EDF conversion
- [troubleshooting.md](guides/troubleshooting.md) - Common issues

**Development** (2+ docs)
- [roadmap.md](development/roadmap.md) - Project timeline
- [developer-guide.md](development/developer-guide.md) - Dev workflows
- [archive/](development/archive/) - Historical docs

**Total**: 17 documentation files

---

## 🔍 Finding What You Need

### I want to...

- **Run my first benchmark** → [Quick Start Guide](getting-started/quickstart.md)
- **Understand the CLI commands** → [CLI Usage](getting-started/cli-usage.md)
- **Add a new signal processing kernel** → [Adding Kernels](guides/adding-kernels.md)
- **Understand the plugin API** → [Plugin Interface](reference/plugin-interface.md)
- **Configure a custom run** → [Configuration Schema](reference/configuration.md)
- **Interpret benchmark results** → [Telemetry Format](reference/telemetry.md)
- **Fix a build error** → [Troubleshooting](guides/troubleshooting.md)
- **Understand how CORTEX works** → [System Overview](architecture/overview.md)
- **Convert an EDF dataset** → [Dataset Preparation](guides/dataset-preparation.md)
- **See project status** → [Roadmap](development/roadmap.md)
- **Contribute code** → [CONTRIBUTING.md](../CONTRIBUTING.md)

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
4. Consult [CLAUDE.md](../CLAUDE.md) for comprehensive development guide

**Contributing**: See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines