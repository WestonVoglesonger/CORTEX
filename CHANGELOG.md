# Changelog

All notable changes to CORTEX will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-12-27

### Added
- **ABI v3: Offline Calibration Support** for trainable kernels
  - New `cortex_calibrate()` function for batch training (ICA, CSP, LDA algorithms)
  - Calibration state serialization (`.cortex_state` binary format with 16-byte header)
  - State I/O utilities (`src/engine/harness/util/state_io.c`)
  - Capability flags system (`CORTEX_CAP_OFFLINE_CALIB`)
  - Backward compatible: v2 kernels work unmodified with v3 harness
- **ICA Kernel** (Independent Component Analysis)
  - First trainable kernel implementation (`primitives/kernels/v1/ica@f32/`)
  - Production-quality full FastICA with platform-agnostic linear algebra
  - Self-contained Jacobi eigendecomposition (no BLAS/LAPACK dependency)
  - Works on embedded targets (STM32, Jetson) - pure C11 + math.h
  - Python oracle with full CLI support (`--test`, `--calibrate`, `--state`)
  - Comprehensive README with calibration workflow documentation
- **Calibration Workflow**
  - `cortex calibrate` CLI command for offline batch training
  - Calibration harness binary (`src/engine/harness/cortex_calibrate`)
  - State file validation (magic number, ABI version, size checks)
  - Integration with validation and benchmarking workflows
- **Enhanced Validation**
  - `cortex validate --calibration-state` for trainable kernels
  - Test harness support for calibration state loading (`tests/test_kernel_accuracy`)
  - ICA end-to-end validation (C kernel vs Python oracle with max error ~3e-05)
- **Documentation**
  - ABI v3 specification (`docs/architecture/abi_v3_specification.md`)
  - ABI evolution history (`docs/architecture/abi_evolution.md`)
  - Migration guide (`docs/guides/migrating-to-abi-v3.md`)
  - Updated plugin interface reference with calibration API
  - Updated kernel development guide with trainable kernels section
  - All 6 existing kernel READMEs updated with v3 compatibility notes

### Changed
- **Plugin Loader** now auto-detects ABI version via `dlsym("cortex_calibrate")`
  - v2 kernels: logs `[loader] Plugin is ABI v2 compatible (no calibration support)`
  - v3 kernels: logs `[loader] Plugin is ABI v3 trainable (calibration supported)`
- **Plugin API Struct** extended with calibration function pointer and capabilities field
  - `cortex_scheduler_plugin_api_t` now includes optional `calibrate` function
  - Zero-cost abstraction: NULL pointer for v2 kernels
- **`cortex_plugin_config_t`** extended with calibration state fields
  - New fields: `calibration_state` (void*), `calibration_state_size` (uint32_t)
  - Defaults to NULL for stateless/stateful kernels

### Fixed
- Documentation inconsistencies in struct sizes (64 bytes vs 56 bytes, 24 bytes vs 20 bytes)
- Field name typo: `output_window_length` → `output_window_length_samples`
- Header location references in CLAUDE.md
- Function count ambiguity (3-function vs 4-function interface)

### Known Limitations
- Oracle validation for v2 kernels requires CLI argument support in oracle.py files
  - ICA oracle has full CLI support (reference implementation)
  - Future: Rewrite validation system in pure Python (no subprocess overhead)

### Architecture
- **Zero Runtime Overhead:** Calibration cost paid once offline, real-time `cortex_process()` unchanged
- **Hermetic Inference:** `cortex_process()` remains allocation-free, no external dependencies
- **State Portability:** Binary `.cortex_state` files use little-endian serialization
- **Incremental Migration:** v2 kernels continue working while new v3 kernels add trainable capabilities

### Migration Guide

**For Users:**
- No changes required for existing workflows
- v2 kernels (CAR, notch_iir, bandpass_fir, goertzel, welch_psd, noop) work as-is
- New trainable kernels require calibration workflow:
  ```bash
  cortex calibrate --kernel ica --dataset data.float32 --windows 500 --output model.cortex_state
  cortex validate --kernel ica --calibration-state model.cortex_state
  cortex run --kernel ica --calibration-state model.cortex_state
  ```

**For Kernel Developers:**
1. Stateless/stateful kernels: no changes needed
2. New trainable kernels: implement `cortex_calibrate()` + load state in `init()`
3. See `docs/guides/migrating-to-abi-v3.md` for full migration guide
4. Reference implementation: `primitives/kernels/v1/ica@f32/`

### Performance
- ICA calibration: ~1 second for 100 windows (64 channels)
- ICA inference: P99 latency <100µs (same as stateless kernels)
- State file size: 16KB for 64×64 unmixing matrix

### Future Work
- ABI v4 (Q2 2026): Online adaptation during `cortex_process()`
- ABI v5 (Q3 2026): Hybrid learning (offline calibration + online adaptation)
- Additional trainable kernels: CSP (motor imagery), LDA (classification)

---

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

[0.3.0]: https://github.com/WestonVoglesonger/CORTEX/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/WestonVoglesonger/CORTEX/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/WestonVoglesonger/CORTEX/releases/tag/v0.1.0
