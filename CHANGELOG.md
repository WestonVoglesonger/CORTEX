# Changelog

All notable changes to CORTEX will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2024-11-12

### Changed
- **BREAKING:** Reorganized repository structure with AWS-inspired primitives architecture
  - Source code moved to unified `src/` directory
    - Python CLI: `cortex_cli/` → `src/cortex/`
    - C engine: `src/{harness,replayer,scheduler}/` → `src/engine/{harness,replayer,scheduler}/`
    - Plugin ABI: `include/cortex_plugin/` → `src/engine/include/cortex_plugin/`
  - Composable primitives layer created in `primitives/`
    - Kernels: `kernels/` → `primitives/kernels/`
    - Configs: `configs/` → `primitives/configs/`
  - Dataset utilities: `scripts/` → `datasets/tools/`
- **BREAKING:** Python package renamed from `cortex_cli` to `cortex`
  - Import statements: `from cortex_cli` → `from cortex`
  - Internal module: `cortex_cli.core` → `cortex.utils`
- **BREAKING:** All path references updated across codebase (~275 changes across 62 files)
  - Makefiles updated (9 files)
  - C source includes updated (8 files)
  - Python imports updated (11 files)
  - Documentation updated (18 files)
  - Config files updated (2 files)

### Added
- Modern `pyproject.toml` for Python packaging (PEP 517/518 compliant)
  - Single source of truth for all dependencies
  - Optional dependency groups: `datasets`, `dev`
  - Pip-installable with `cortex` command entry point
- CHANGELOG.md for version tracking (this file)
- .editorconfig for consistent code formatting across editors
- primitives/README.md explaining composable primitives philosophy
- datasets/README.md documenting datasets and conversion tools
- Comprehensive pre-reorganization analysis (275 path references catalogued)

### Removed
- Deprecated requirements.txt files (consolidated into pyproject.toml)
  - Root requirements.txt
  - scripts/requirements.txt
- Duplicate docs/reference/channel_order.json (canonical version in datasets/)
- Root directory clutter: 50% reduction (14 directories → 7)

### Fixed
- Inconsistent dependency management (now single source in pyproject.toml)
- Scattered source code layout (now organized by purpose: system vs primitives)
- Ambiguous directory structure (now semantically clear)

### Migration Guide

**For Users:**
1. Reinstall with new package structure:
   ```bash
   pip uninstall cortex-bci  # If previously installed
   pip install .              # Core functionality
   pip install ".[datasets]"  # With dataset conversion tools
   ```

2. Update any scripts that import cortex_cli:
   ```python
   # OLD
   from cortex_cli.commands import analyze
   from cortex_cli.core.config import load_config

   # NEW
   from cortex.commands import analyze
   from cortex.utils.config import load_config
   ```

3. Update any scripts with hardcoded paths:
   - `kernels/` → `primitives/kernels/`
   - `configs/` → `primitives/configs/`
   - `scripts/` → `datasets/tools/`

**For Developers:**
1. Kernel development paths updated:
   - New location: `primitives/kernels/v1/your_kernel@f32/`
   - Include path: `-I../../../../src/engine/include`

2. Binary path updated:
   - `./src/harness/cortex` → `./src/engine/harness/cortex`

3. See CONTRIBUTING.md for full development guide with new structure

### Architecture Philosophy

This release introduces an **AWS-inspired primitives architecture**:

- **src/**: System implementation (engine + CLI) - how CORTEX works
- **primitives/**: Composable building blocks - what researchers compose
  - kernels/: Signal processing primitives
  - configs/: Configuration primitives
  - adapters/: I/O primitives (future)

CORTEX provides fundamental building blocks rather than prescriptive solutions, enabling researchers to compose novel experimental workflows.

---

## [0.1.0] - 2024-11-10

### Initial Release

- BCI kernel benchmarking pipeline
- Signal processing kernel framework
- Dataset replay system
- Real-time scheduling with time dilation
- Comprehensive documentation
- EEG Motor Movement/Imagery dataset support
- Multiple signal processing kernels (CAR, bandpower, coherence, etc.)
- Python CLI for analysis and visualization
- Cross-platform support (Linux, macOS)

---

[0.2.0]: https://github.com/WestonVoglesonger/CORTEX/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/WestonVoglesonger/CORTEX/releases/tag/v0.1.0
