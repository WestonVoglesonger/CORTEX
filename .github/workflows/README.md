# CORTEX CI/CD Pipeline

This directory contains GitHub Actions workflows for continuous integration and testing.

## Workflows

### `ci.yml` - Main CI Pipeline

Runs on every push and pull request to `main` and `develop` branches.

#### Jobs

**C Unit Tests** (`test`)
- Platform: Ubuntu Latest
- Tests C modules (replayer, scheduler)
- Steps:
  - Install build dependencies (gcc, make)
  - Build all C test binaries
  - Run all tests (13 total: 5 replayer + 8 scheduler)
- Duration: ~10 seconds

## Running Locally

```bash
cd tests/
make tests          # Run all C tests (13 tests)
make test-replayer  # Replayer only (5 tests)
make test-scheduler # Scheduler only (8 tests)
make clean          # Clean up binaries
```

## Test Coverage

### Replayer Module (5 tests)
- Hop-sized chunk streaming
- Timing cadence (H/Fs seconds)
- EOF handling and rewind
- Various configurations (MCU to HALO)
- Data continuity

### Scheduler Module (8 tests)
- Configuration validation
- Window formation from chunks
- Overlapping windows (W-H retention)
- Buffer management
- Multiple plugin dispatch
- Warmup period handling
- Flush functionality
- Data continuity


## Troubleshooting

### Tests Failing on CI
1. **Build failures**: Check gcc/make installation
2. **Test failures**: Run locally to reproduce: `cd tests && make tests`
3. **Header issues**: Verify `#include` paths are correct

### Platform-Specific Notes
- **macOS**: Real-time scheduling warnings are expected (not available)
- **Linux**: Full real-time support available
- **CI (Ubuntu)**: Real-time warnings expected (unprivileged container)

## Future Enhancements

- [ ] Add code coverage reporting (lcov/gcov)
- [ ] Add performance regression tests
- [ ] Add integration tests (replayer → scheduler → plugin)
- [ ] Add Python wrapper tests (when implemented)
- [ ] Add release workflow for tagged versions
- [ ] Test on multiple architectures (ARM, x86_64)
