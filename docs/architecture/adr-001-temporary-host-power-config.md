# ADR-001: Temporary Host Power Configuration for Fall 2025

## Status

Accepted (Fall 2025) - Temporary implementation, planned for refactoring in Spring 2026

## Context

### Problem

CPU frequency scaling on x86 Linux hosts causes benchmark data to be invalid:
- Idle system runs at lower CPU frequencies (~1.2 GHz) to save power
- Loaded system runs at higher CPU frequencies (~3.5 GHz) due to background processes
- This creates a paradox: benchmarks with background load run FASTER than idle benchmarks
- The 48% performance anomaly makes comparative benchmark data meaningless

### Academic Requirement

Fall 2025 final deliverable requires accurate comparative benchmark data for presentation/paper. Without this data, the semester work appears to be "a lot of system design without much to show for it."

### Architectural Constraint

Device adapters (STM32H7, Jetson Orin Nano) are not scheduled until Spring 2026. We cannot properly design power configuration without understanding:
- How device adapters will handle platform-specific settings
- Whether devices self-configure or receive config via protocol
- Platform-specific abstractions (STM32 clock config vs x86 governor vs Jetson nvpmodel)

##Decision

Implement **temporary host power configuration in Python wrapper layer** with the following constraints:

1. **Scope**: x86 host machine only (not device adapters)
2. **Location**: Python wrapper (`src/cortex/utils/power_config.py`) - ZERO changes to C harness
3. **Platform Support**: Linux (full), macOS (warnings only)
4. **Mechanism**: Context manager pattern for automatic cleanup
5. **Documentation**: Clearly marked as TEMPORARY with Spring 2026 removal/refactoring plan

### Implementation Details

**New Files:**
- `src/cortex/utils/power_config.py` (~300 lines, isolated module)

**Modified Files:**
- `src/cortex/utils/runner.py` (+15 lines, context manager wrapper)
- `src/cortex/commands/check_system.py` (+5 lines, update messages)

**Config Schema:** No changes (power.governor/turbo fields already exist)

**Kernel ABI:** No changes (zero impact on core engine)

## Consequences

### Positive

1. **Enables Fall 2025 Deliverable**: Provides accurate comparative benchmark data for academic requirement
2. **Minimal Technical Debt**: Isolated Python module, easy to remove or rename
3. **No Core Engine Impact**: C harness unchanged, kernel ABI stable
4. **Low Implementation Cost**: ~6 hours to implement, ~4-6 hours to refactor in Spring 2026
5. **Clear Migration Path**: Documented removal/refactoring strategy

### Negative

1. **Platform Limitations**: Only works on Linux (macOS gets warnings)
2. **Temporary Solution**: Will require refactoring when device adapters exist
3. **Requires Root**: Linux users must run with sudo for power config
4. **Incomplete Abstraction**: Doesn't solve device power management

### Risks

1. **Spring 2026 Refactoring**: Estimated 4-6 hours to rename or remove
   - Mitigation: Well-documented, isolated module, backward-compatible config evolution planned

2. **User Confusion**: Temporary nature may not be obvious
   - Mitigation: Docstrings, ADR, roadmap updates all document temporary status

3. **Platform Support Gap**: macOS users don't get power control
   - Mitigation: Clear warnings, functionality degrades gracefully

## Alternatives Considered

### Alternative 1: Remove Background Load Feature

**Pros:** No power config needed, simpler PR
**Cons:** Discards completed work, limits research value, no comparative data

**Rejected:** Would prevent Fall deliverable

### Alternative 2: Wait for Spring 2026 Device Adapters

**Pros:** Proper architecture, no technical debt
**Cons:** Misses Fall deliverable, no benchmark data this semester

**Rejected:** Academic requirement is hard deadline

### Alternative 3: Implement Full Device Adapter Now

**Pros:** Correct architecture, no refactoring later
**Cons:** Pulls Spring 2026 work forward, significant scope increase (~40 hours)

**Rejected:** Too much work for Fall semester timeline

### Alternative 4: Manual User Setup Only

**Pros:** Zero code changes
**Cons:** Error-prone, poor user experience, unreliable data

**Rejected:** Doesn't ensure reproducibility

## Spring 2026 Migration Plan

When device adapters are implemented:

**Option A: Rename to Host-Specific**
```python
# Rename function
apply_power_config() → apply_host_power_config()

# Add device delegation
with apply_host_power_config(config['power'].get('host')):
    with device_adapter.apply_power_config(config['power'].get('device')):
        run_harness(...)
```

**Option B: Remove Entirely**
```
# If device adapters handle all power management:
- Delete src/cortex/utils/power_config.py
- Remove wrapper from runner.py
- Delegate to device adapters
```

**Config Evolution (Backward Compatible):**
```yaml
# Fall 2025 (current)
power:
  governor: "performance"
  turbo: false

# Spring 2026 (backward compatible extension)
power:
  host:  # NEW - if missing, falls back to root level
    governor: "performance"
  device:  # NEW - platform-specific
    platform: "nvidia_jetson"
    mode: "max_performance"
```

## References

- Issue: CPU frequency scaling causing 48% performance anomaly
- Project Roadmap: `docs/development/roadmap.md` (device adapters Spring 2026)
- Implementation: `src/cortex/utils/power_config.py`
- Integration: `src/cortex/utils/runner.py`

## Authors

- Weston Voglesonger
- Date: 2025-11-15
- Reviewed By: N/A (solo project decision)
