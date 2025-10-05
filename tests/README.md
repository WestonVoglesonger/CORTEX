# Tests

This directory contains test files for the CORTEX project.

## C Unit Tests

C modules (replayer, scheduler) have dedicated C unit tests:

```bash
cd tests/
make test           # Run all C tests
make test-replayer  # Run replayer tests only
make clean          # Clean up test binaries
```

### Test Coverage

#### Replayer Tests (`test_replayer.c`)
- ✅ Hop-sized chunks (verifies H samples, not W)
- ✅ Correct timing cadence (H/Fs seconds per chunk)
- ✅ EOF handling and rewind
- ✅ Various configurations (different H, Fs, C)
- ✅ Data continuity (samples in correct order)

#### Scheduler Tests (`test_scheduler.c`)
- ✅ Configuration validation
- ✅ Window formation from hop-sized chunks
- ✅ Overlapping windows (W-H sample retention)
- ✅ Buffer management (various chunk sizes)
- ✅ Multiple plugin dispatch
- ✅ Warmup period handling
- ✅ Flush functionality
- ✅ Data continuity verification

## Python Integration Tests

Higher-level integration tests use pytest:

```bash
pytest tests/
```

## Test Structure

- **Unit tests**: Individual C modules (`test_*.c`)
- **Integration tests**: End-to-end Python tests (`test_*.py`)
- **Performance benchmarks**: Actual kernel benchmarking (via configs)