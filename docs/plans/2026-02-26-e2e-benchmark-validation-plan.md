# End-to-End Benchmark Validation Plan (Post-Refactor Regression Check)

**Date:** 2026-02-26
**Asana Task:** 1213459506207181
**Goal:** Validate system integrity and establish fresh baselines after the Dec 2025 – Feb 2026 refactoring wave. No backwards-compatibility concerns — no external users exist yet.

---

## Context

Since the last full validation (Dec 2025), six major changes landed touching the same core files (runner.py: 24 commits, main.c: 21 commits):

| Area | Risk | What Changed |
|------|------|-------------|
| SE-3 Q15 kernels | HIGH | Directory layout, scheduler buffer semantics (void* + element_size), replayer conversion, adapter protocol, kernel discovery |
| SE-8 Pipelines | HIGH | Concurrent harness spawning, chain data flow, shape propagation, stage_index telemetry |
| SE-7 Tail attribution | MEDIUM | New scipy dependency, tier 2/3 analysis, decompose command refactor |
| SE-5 Latency analysis | MEDIUM | Device primitives, predict/decompose/compare commands, profile removal |
| C engine hardening | LOW | Chain failure telemetry, cleanup paths |
| Statistical CI | LOW | t-distribution CI on mean, new output fields |

The test suite has strong unit coverage (322+ Python, 73+ C) but a critical gap: **no test runs a real kernel binary through the harness**. All integration tests mock the subprocess. This validation fills that gap with actual execution.

---

## Validation Phases

### Phase 0: Prerequisites (5 min)

Ensure the build system and test suites are healthy before any benchmark work.

| Step | Command | Pass Criteria |
|------|---------|---------------|
| 0.1 Clean build | `make clean && make all` | Exit 0, 17 kernel binaries produced (9 f32 + 8 Q15) |
| 0.2 C unit tests | `make tests` | All 73+ tests pass |
| 0.3 Python tests | `python -m pytest tests/cli/ -q` | All 322+ tests pass |
| 0.4 Kernel enumeration | `cortex list` | Lists all 17 kernels with correct dtype tags |

**Why this matters:** If the build or test suites are broken, no downstream validation is meaningful. The Q15 directory restructuring changed build paths — this catches it.

### Phase 1: Oracle Validation (10 min)

Verify numerical correctness of all kernels against Python/SciPy reference.

| Step | Command | Pass Criteria |
|------|---------|---------------|
| 1.1 All f32 kernels | `cortex validate --kernel <name>` for each of 9 f32 kernels | PASS (rtol=1e-5) |
| 1.2 All Q15 kernels | `cortex validate --kernel <name> --dtype q15` for each of 8 Q15 kernels | PASS (rtol=1e-3; FFT Q15: rtol=5e-2) |
| 1.3 Trainable round-trip | `cortex calibrate --kernel ica ...` then `cortex validate --kernel ica --state ica.cortex_state` | Calibration completes, validation passes |

**Scope addition:** Step 1.3 exercises the trainable kernel pipeline (ABI v3 `cortex_calibrate()`), which was touched during the Q15 refactor. Not in original Asana scope but high regression risk.

### Phase 2: Single-Kernel Benchmarks (15 min)

Run standard benchmark config to establish fresh baselines.

| Step | Command | Pass Criteria |
|------|---------|---------------|
| 2.1 Full benchmark | `cortex pipeline --duration 30` | Completes without error, SUMMARY.md generated |
| 2.2 Sanity check | Inspect SUMMARY.md latencies | P50/P95/P99 are plausible (no absurd values like 0µs or >100ms for lightweight kernels) |
| 2.3 CI fields present | Inspect SUMMARY.md | 95% CI values present for each kernel |
| 2.4 Deadline compliance | `cortex check-deadline --run-name <new_run>` | 0% miss rate for all kernels |

**Note:** No previous baselines to compare against (no external users). This run establishes the post-refactor baseline for future comparisons.

### Phase 3: Harness Overhead Baseline (5 min)

Confirm the measurement floor hasn't regressed.

| Step | Command | Pass Criteria |
|------|---------|---------------|
| 3.1 Noop f32 idle | `cortex run --kernel noop --duration 30` | Median ≤ 5µs, min ≤ 2µs |
| 3.2 Noop Q15 | `cortex run --kernel noop --dtype q15 --duration 30` | Comparable to f32 (noop is memcpy, dtype shouldn't matter much) |
| 3.3 Overhead analysis | `cortex decompose --run-name <noop_run> --device m1-macos` | Harness overhead ≤ 2µs |

**Scope addition:** Step 3.2 runs noop@q15 — a new kernel variant that exercises the replayer's float32→Q15 conversion path and scheduler's void* buffer handling. This is the simplest possible Q15 test and should be included.

### Phase 4: Pipeline Mode & Chain Execution (10 min)

Verify SE-8 multi-kernel chains produce correct telemetry.

| Step | Command | Pass Criteria |
|------|---------|---------------|
| 4.1 Basic chain | `cortex pipeline --chain "notch_iir,bandpass_fir,car" --duration 15` | Completes, per-stage breakdown in analysis |
| 4.2 Stage telemetry | Inspect telemetry NDJSON | `stage_index` field: 0, 1, 2 for each stage; no 0xFFFFFFFF in chain records |
| 4.3 Chain statistics | Check SUMMARY.md | Per-stage P50/P95/P99 + e2e values present, no NaN |
| 4.4 YAML pipeline mode | Create config with `pipelines:` section, run with `cortex run --config pipeline.yaml` | Concurrent harness processes spawn and complete |

### Phase 5: DVFS Spot-Check (10 min)

Verify the Idle Paradox still reproduces.

| Step | Command | Pass Criteria |
|------|---------|---------------|
| 5.1 Idle run | `cortex run --kernel car --duration 30` (no load) | Record P50 |
| 5.2 Medium run | `cortex run --kernel car --duration 30 --load-profile medium` | Record P50 |
| 5.3 Ratio check | Compute idle_P50 / medium_P50 | Ratio > 1.5× (published: 2.31×). Exact value will vary by machine state. |

### Phase 6: New CLI Commands Smoke Test (5 min)

Verify recently added commands don't crash on the happy path.

| Step | Command | Pass Criteria |
|------|---------|---------------|
| 6.1 System check | `cortex check-system` | Runs without crash, produces table |
| 6.2 Predict | `cortex predict --device m1-macos --kernel car` | Produces latency estimate |
| 6.3 Decompose | `cortex decompose --run-name <latest> --device m1-macos` | Tier 1 always present, Tier 2/3 conditional on data sufficiency |
| 6.4 Compare | `cortex compare --baseline <phase2_run> --candidate <phase3_noop_run>` | Produces comparison table (smoke test — commands run without crash) |
| 6.5 Check deadline | `cortex check-deadline --run-name <latest>` | Exit 0 if no misses |
| 6.6 Generate | `cortex generate --signal pink_noise --channels 64 --duration 10 --output-dir /tmp/cortex-test-gen` | Dataset created, spec.yaml valid |

### Phase 7: Generator Pipeline Integration (5 min)

Verify synthetic datasets work in pipeline mode (SE-8 follow-up).

| Step | Command | Pass Criteria |
|------|---------|---------------|
| 7.1 Generator in run | `cortex run --kernel noop` with generator config | Completes, telemetry produced |
| 7.2 Generator in pipeline | Config with `pipelines:` + generator dataset | Concurrent runs complete with generated data |

---

## Success Criteria (from Asana + additions)

**Original (Asana):**
- [ ] All 17 kernels pass oracle validation
- [ ] Latency distributions are plausible (establish new post-refactor baselines)
- [ ] No new deadline misses on noop or lightweight kernels
- [ ] Pipeline chain telemetry produces correct per-stage breakdown
- [ ] Harness overhead ≤ 2µs (noop baseline)

**Additional (from research):**
- [ ] Clean build produces 17 kernel binaries (9 f32 + 8 Q15)
- [ ] All C unit tests pass (73+)
- [ ] All Python tests pass (322+)
- [ ] `cortex list` enumerates all 17 kernel variants
- [ ] Noop Q15 runs successfully (replayer conversion + void* scheduler)
- [ ] Trainable kernel round-trip works (calibrate → validate)
- [ ] New CLI commands don't crash on happy path (check-system, predict, decompose, compare, check-deadline, generate)
- [ ] Generator datasets work in pipeline mode
- [ ] 95% CI values present in SUMMARY.md output
- [ ] `cortex compare` runs successfully against two fresh runs

---

## Estimated Duration

| Phase | Duration |
|-------|----------|
| Phase 0: Prerequisites | 5 min |
| Phase 1: Oracle Validation | 10 min |
| Phase 2: Single-Kernel Benchmarks | 15 min |
| Phase 3: Harness Overhead | 5 min |
| Phase 4: Pipeline Mode | 10 min |
| Phase 5: DVFS Spot-Check | 10 min |
| Phase 6: CLI Smoke Tests | 5 min |
| Phase 7: Generator Integration | 5 min |
| **Total** | **~65 min** |

---

## Artifacts

After completion:
1. `docs/validation/e2e-regression-2026-02-26/` — Results directory with telemetry, analysis, comparison
2. Updated Asana task with pass/fail results per phase
3. If regressions found: bug tickets filed with telemetry evidence

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Q15 directory restructuring broke build paths | Medium | HIGH | Phase 0 catches this immediately |
| CLI commands crash on fresh telemetry | Low | LOW | Phase 6 smoke tests all commands |
| Trainable kernel state format changed | Low | HIGH | Phase 1.3 validates full round-trip |
| Noop Q15 overhead significantly different from f32 | Low | LOW | Phase 3.2 — expected to be similar since noop is memcpy |
| Generator integration broken in pipeline mode | Low | MEDIUM | Phase 7 validates specifically |
