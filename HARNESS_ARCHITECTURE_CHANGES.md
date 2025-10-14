# Harness Architecture Changes

## Overview
This document tracks the architectural changes needed to align the harness implementation with documentation and improve the benchmarking approach.

## Key Changes

### 1. Sequential Plugin Execution
**Current**: All ready plugins run in parallel through one scheduler
**New**: Plugins run sequentially, one at a time

**Rationale**: 
- Eliminates CPU/memory contention between plugins
- Provides clean performance isolation for benchmarking
- Enables accurate per-plugin latency measurements

**Implementation**:
- Loop through each ready plugin individually
- Create scheduler with plugin-specific W/H/C/dtype
- Run replayer → scheduler → single plugin
- Collect telemetry, destroy scheduler, move to next plugin

### 2. Output Layout Standardization
**Current**: Single CSV in `output.directory`
**New**: `results/<run_id>/` structure

**Files**:
- `results/<run_id>/telemetry.json` (per-window records)
- `results/<run_id>/summary.csv` (per-plugin aggregates)
- `results/<run_id>/cortex.yaml` (run config snapshot)

### 3. macOS Compatibility
**Current**: Hardcoded `.so` and `-ldl` link flag
**New**: Platform-specific plugin loading

**Changes**:
- Use `.dylib` on macOS, `.so` on Linux
- Drop `-ldl` on macOS (not needed)
- Conditional compilation for platform differences

### 4. Config Schema Alignment
**Current**: Ignores many documented fields
**New**: Parse and validate documented schema

**Missing fields to add**:
- `system` section (name, description)
- `power` section (governor, turbo)
- `benchmark.metrics` array
- `plugins[*].params` (opaque key-value)
- `plugins[*].tolerances` and `plugins[*].oracle`
- `realtime.deadline.*` sub-fields

**Validation rules to enforce**:
- DEADLINE scheduler requires runtime/period/deadline fields
- Ready plugins require params/tolerances/oracle
- Platform-specific privilege warnings

### 5. Telemetry Integration
**Current**: Scheduler prints to stdout, harness doesn't populate telemetry buffer
**New**: Proper telemetry collection and JSON output

**Changes**:
- Wire scheduler callbacks to populate telemetry buffer
- Write JSON instead of CSV
- Include all documented fields (dtype, load_profile, etc.)
- Mark warmup windows in telemetry records

### 6. Heterogeneous Plugin Shapes
**Current**: Assumes uniform W/H/C/dtype across all plugins
**New**: Support per-plugin shapes (enabled by sequential execution)

**Implementation**:
- Each plugin gets its own scheduler with its specific shape
- Replayer adapts to each plugin's hop/window requirements
- Telemetry tracks shape per plugin

## Implementation Priority

### Phase 1 (Critical)
1. ✅ Sequential plugin execution - **COMPLETED**
2. ✅ macOS compatibility fixes - **COMPLETED**
3. ✅ Basic telemetry CSV output - **COMPLETED** (JSON conversion pending)

### Phase 2 (Important)
1. Config schema alignment
2. Deadline validation
3. ✅ Heterogeneous shape support - **COMPLETED**

### Phase 3 (Nice to have)
1. Summary generation
2. Energy/power metrics
3. Background load profiles

## Testing Strategy
- Unit tests for config parsing/validation
- Integration tests for sequential execution
- Cross-platform build verification
- Telemetry output validation

## Backward Compatibility
- Existing YAML configs should continue to work
- New fields are optional with sensible defaults
- Graceful degradation on unsupported platforms
