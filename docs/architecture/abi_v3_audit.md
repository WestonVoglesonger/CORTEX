# ABI v3 Migration Audit

**Date**: 2025-12-27
**Purpose**: Catalog all files referencing ABI v2 that need updating for v3 migration

---

## Executive Summary

**Total files requiring updates**: 35+ files identified
**Scope**: Core ABI definition, all 8 kernels, harness, CLI, tests, documentation

---

## 1. Core ABI Definition Files

### Critical (Source of Truth)

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `sdk/kernel/include/cortex_plugin.h` | ABI v2 definition | **BREAKING**: Increment to v3, add `cortex_calibrate()`, extend structs | **P0** |

---

## 2. Kernel Implementations (All Reference ABI v2)

### Existing Kernels (Backward Compatibility Required)

| Kernel | File | Update Required | Notes |
|--------|------|-----------------|-------|
| CAR | `primitives/kernels/v1/car@f32/car.c` | README update (ABI v3 compatible note) | Stateless, no calibration |
| Notch IIR | `primitives/kernels/v1/notch_iir@f32/notch_iir.c` | README update (ABI v3 compatible note) | Stateful (filter history), no calibration |
| Bandpass FIR | `primitives/kernels/v1/bandpass_fir@f32/bandpass_fir.c` | README update (ABI v3 compatible note) | Stateful (tail buffer), no calibration |
| Goertzel | `primitives/kernels/v1/goertzel@f32/goertzel.c` | README update (ABI v3 compatible note) | Stateless, no calibration |
| Welch PSD | `primitives/kernels/v1/welch_psd@f32/welch_psd.c` | README update (ABI v3 compatible note) | Stateless, no calibration |
| Noop | `primitives/kernels/v1/noop@f32/noop.c` | README update (ABI v3 compatible note) | Trivial baseline |

### New Kernel (Reference v3 Implementation)

| Kernel | Files | Update Required | Notes |
|--------|-------|-----------------|-------|
| ICA | `primitives/kernels/v1/ica@f32/` | **NEW**: Full implementation with `cortex_calibrate()` | Reference for trainable kernels |

---

## 3. Harness Implementation Files

### Plugin Loading

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `src/engine/harness/app/main.c` | v2 init flow | Add `calibrate` subcommand, state loading | **P0** |
| `src/engine/harness/config/config.c` | v2 config schema | Parse `calibration_state` field from YAML | **P1** |
| `sdk/kernel/lib/loader/` | (Need to find loader code) | Add `dlsym("cortex_calibrate")` detection, v2/v3 version negotiation | **P0** |

### Scheduler

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `src/engine/scheduler/scheduler.h` | Uses `cortex_init_result_t` | Update struct reference (now has `capabilities` field) | **P1** |
| `src/engine/scheduler/scheduler.c` | Uses `cortex_init_result_t` | Update struct usage | **P1** |

### New Utilities

| File | Purpose | Priority |
|------|---------|----------|
| `sdk/kernel/lib/state_io/state_io.c` | **NEW**: Serialize/deserialize calibration state | **P0** |
| `sdk/kernel/include/cortex_state_io.h` | **NEW**: Header for state I/O | **P0** |

---

## 4. CLI Implementation (Python)

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `src/cortex/commands/calibrate.py` | **NEW** | Implement `cortex calibrate` command | **P0** |
| `src/cortex/commands/run.py` | v2 run logic | Add `--calibration-state` argument parsing | **P1** |
| `src/cortex/commands/validate.py` | v2 validation | Handle calibration state in validation workflow | **P1** |

---

## 5. Test Files

### Existing Tests (Regression Prevention)

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `tests/test_kernel_accuracy.c` | v2 oracle validation | Ensure v2 kernels still validate with v3 harness | **P0** |
| `tests/test_scheduler.c` | v2 scheduler tests | Update for extended `cortex_init_result_t` | **P1** |

### New Tests

| File | Purpose | Priority |
|------|---------|----------|
| `tests/test_abi_compatibility.c` | **NEW**: v2/v3 backward compatibility tests | **P0** |
| `tests/test_calibration.c` | **NEW**: Calibration workflow tests | **P0** |

---

## 6. Documentation Files

### Reference Documentation (Technical Specs)

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `docs/reference/plugin-interface.md` | ABI v2 specification | **REWRITE**: Full v3 specification (calibration, capabilities, structs) | **P0** |
| `docs/reference/configuration.md` | v2 config schema | Add `calibration_state` field documentation | **P1** |
| `docs/reference/telemetry.md` | v2 telemetry | Add calibration metrics (if applicable) | **P2** |

### Architecture Documentation

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `docs/architecture/overview.md` | Mentions plugin system | Update plugin system section with calibration phase | **P1** |
| `docs/architecture/testing-strategy.md` | v2 testing approach | Add calibration testing strategy | **P2** |
| `docs/architecture/benchmarking-methodology.md` | v2 methodology | Document calibration phase in methodology | **P2** |
| `docs/architecture/platform-compatibility.md` | Platform notes | Note calibration state serialization for adapters | **P2** |
| `docs/architecture/abi_evolution.md` | **NEW** | Document v1 → v2 → v3 history and rationale | **P0** |

### Guide Documentation (Tutorials)

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `docs/guides/adding-kernels.md` | v2 kernel tutorial | Add "Trainable Kernels" section with calibration implementation guide | **P0** |
| `docs/guides/calibration-workflow.md` | **NEW** | User guide for calibration workflow | **P0** |
| `docs/guides/migrating-to-abi-v3.md` | **NEW** | Migration guide for kernel authors | **P0** |
| `docs/guides/adding-datasets.md` | Dataset conversion | Note calibration data requirements | **P2** |
| `docs/guides/troubleshooting.md` | v2 issues | Add calibration-specific troubleshooting | **P2** |

### Getting Started Documentation

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `docs/getting-started/quickstart.md` | v2 quick start | Add calibration example (if applicable) | **P2** |
| `docs/getting-started/cli-usage.md` | v2 CLI commands | Add `cortex calibrate` command documentation | **P1** |

### Development Documentation

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `docs/development/roadmap.md` | Mentions ABI | Update with v3 completion, note v4 (online adaptation) | **P2** |
| `docs/development/future-enhancements.md` | Future plans | Add v4 online calibration as future enhancement | **P2** |

### Top-Level Documentation

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `README.md` | Mentions kernel interface | Note ABI v3 support in features | **P1** |
| `docs/README.md` | Documentation index | Add links to calibration guides, ABI evolution | **P1** |
| `docs/FAQ.md` | v2 FAQs | Add calibration FAQs | **P2** |
| `CLAUDE.md` | **Sacred Constraints**: ABI v2 | Update constraint #6 to v3, add calibration to terminology | **P0** |
| `CONTRIBUTING.md` | v2 contribution guide | Update kernel contribution section for v3 | **P1** |
| `CHANGELOG.md` | Current changelog | Add `[0.3.0]` section with breaking changes | **P0** |

### Release Documentation

| File | Purpose | Priority |
|------|---------|----------|
| `docs/releases/v0.3.0.md` | **NEW**: v3 release notes | **P0** |

---

## 7. Other Files Referencing ABI

### Copilot/AI Instructions

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `copilot-instructions.md` | Mentions ABI v2 | Update to v3, note calibration capabilities | **P2** |

### Primitives Documentation

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| `primitives/README.md` | Primitives philosophy | Note calibration state as primitive (if applicable) | **P2** |
| `primitives/kernels/README.md` | Kernel overview | Update with v3 capabilities, calibration section | **P1** |
| `primitives/configs/README.md` | Config overview | Document `calibration_state` config field | **P1** |

### Kernel-Specific READMEs

| File | Update Required | Priority |
|------|-----------------|----------|
| `primitives/kernels/v1/car@f32/README.md` | Add "ABI v3 Compatible (stateless)" note | **P1** |
| `primitives/kernels/v1/notch_iir@f32/README.md` | Add "ABI v3 Compatible (stateful)" note | **P1** |
| `primitives/kernels/v1/bandpass_fir@f32/README.md` | Add "ABI v3 Compatible (stateful)" note | **P1** |
| `primitives/kernels/v1/goertzel@f32/README.md` | Add "ABI v3 Compatible (stateless)" note | **P1** |
| `primitives/kernels/v1/welch_psd@f32/README.md` | Add "ABI v3 Compatible (stateless)" note | **P1** |
| `primitives/kernels/v1/noop@f32/README.md` | Add "ABI v3 Compatible (trivial baseline)" note | **P1** |
| `primitives/kernels/v1/ica@f32/README.md` | **NEW**: Full calibration workflow documentation | **P0** |

### Experiment Reports

| Files | Update Required | Priority |
|-------|-----------------|----------|
| `experiments/*/technical-report/*.md` | Reference ABI version in methodology sections | **P3** (Low - archival) |

---

## 8. Build System Files

| File | Current State | Update Required | Priority |
|------|---------------|-----------------|----------|
| Root `Makefile` | Builds all kernels | Ensure ICA kernel auto-discovered | **P1** |
| `pyproject.toml` | Package version | Bump version to 0.3.0 (if applicable) | **P1** |

---

## Update Strategy

### Phase 1: Core ABI (P0)
1. `sdk/kernel/include/cortex_plugin.h` - Define v3 structs/functions
2. `docs/reference/plugin-interface.md` - Document v3 specification
3. `docs/architecture/abi_evolution.md` - History and rationale

### Phase 2: Harness Implementation (P0)
4. Harness loader - v3 detection and backward compatibility
5. State I/O utilities - Serialization/deserialization
6. CLI calibrate command - User-facing calibration workflow

### Phase 3: Reference Implementation (P0)
7. ICA kernel - Full v3 implementation with `cortex_calibrate()`
8. ICA oracle - Python reference for validation
9. ICA README - Calibration workflow documentation

### Phase 4: Migration Documentation (P0-P1)
10. `docs/guides/migrating-to-abi-v3.md` - Migration guide
11. `docs/guides/calibration-workflow.md` - User guide
12. `docs/guides/adding-kernels.md` - Update with trainable kernels
13. `CLAUDE.md` - Sacred Constraints update
14. `CHANGELOG.md` - Release notes

### Phase 5: Kernel Documentation (P1)
15. All 6 existing kernel READMEs - Compatibility notes
16. `primitives/kernels/README.md` - v3 overview

### Phase 6: Testing (P0)
17. Backward compatibility tests
18. Calibration workflow tests
19. ICA oracle validation

### Phase 7: Secondary Documentation (P1-P2)
20. Configuration, CLI, architecture docs
21. README updates
22. CONTRIBUTING update

### Phase 8: Cleanup (P2-P3)
23. FAQ, troubleshooting, roadmap updates
24. Experiment reports (if needed)

---

## Risk Mitigation

**Backward Compatibility Testing Critical**:
- Ensure all 6 existing v2 kernels compile and validate with v3 harness
- Test scenarios:
  - ✅ v2 kernel + v3 harness (MUST work)
  - ❌ v3 kernel + v2 harness (MUST fail gracefully with clear error)

**Documentation Consistency**:
- Cross-reference all docs after updates to ensure no conflicting information
- Grep for "ABI v2" references after migration to catch stragglers

**Version Detection Logic**:
- Harness MUST correctly detect v2 vs. v3 kernels
- Error messages MUST be clear when version mismatch occurs

---

## Validation Checklist

Before declaring v3 complete:

- [ ] All P0 files updated
- [ ] All P1 files updated
- [ ] No stale "ABI v2" references in documentation
- [ ] All 6 existing kernels validate with v3 harness
- [ ] ICA kernel validates (calibrate + process)
- [ ] Backward compatibility tests pass
- [ ] Cross-platform builds work (macOS + Linux)
- [ ] CHANGELOG documents breaking changes
- [ ] Migration guide tested by migrating one v2 kernel to v3

---

**Status**: Phase 1 Complete - Audit cataloged 35+ files requiring updates.

**Next**: Begin Phase 2 (ABI v3 Core Design).
