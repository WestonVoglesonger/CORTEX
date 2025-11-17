# CORTEX Repository Improvement Plan & Tracking Document

> **Last Updated:** 2025-11-16
> **Document Owner:** Engineering Team
> **Status:** Phase 1 In Progress

---

## 📋 Table of Contents

1. [Progress Dashboard](#-progress-dashboard)
2. [Executive Summary](#-executive-summary)
3. [Quick Start Guide](#-quick-start-guide)
4. [Phase-Based Remediation Plan](#-phase-based-remediation-plan)
5. [Detailed Issue Registry](#-detailed-issue-registry)
6. [Category Deep Dives](#-category-deep-dives)
7. [Dependencies & Sequencing](#-dependencies--sequencing)
8. [Metrics & KPIs](#-metrics--kpis)
9. [Reference Material](#-reference-material)
10. [Change Log](#-change-log)

---

## 📊 Progress Dashboard

### Overall Progress

```
Phase 1 (Critical):     [████████░░░░░░░░░░░░] 2/5   (40%)  - Target: Weeks 1-2
Phase 2 (High):         [░░░░░░░░░░░░░░░░░░░░] 0/15  (0%)   - Target: Month 1
Phase 3 (Testing):      [░░░░░░░░░░░░░░░░░░░░] 0/22  (0%)   - Target: Month 2
Phase 4 (Docs/Obs):     [░░░░░░░░░░░░░░░░░░░░] 0/20  (0%)   - Target: Month 3
Phase 5 (Architecture): [░░░░░░░░░░░░░░░░░░░░] 0/25  (0%)   - Target: Month 4+

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Progress:         [█░░░░░░░░░░░░░░░░░░░] 2/107 (1.9%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Status Breakdown

| Status | Count | Percentage |
|--------|-------|------------|
| 🔴 Not Started | 105 | 98.1% |
| 🟡 In Progress | 0 | 0% |
| 🟢 Completed | 2 | 1.9% |
| 🚫 Blocked | 0 | 0% |

### Priority Breakdown

| Priority | Count | Completed | Remaining |
|----------|-------|-----------|-----------|
| 🔴 **Critical** | 35 | 2 | 33 |
| 🟠 **High** | 18 | 0 | 18 |
| 🟡 **Medium** | 22 | 0 | 22 |
| 🟢 **Low** | 15 | 0 | 15 |

### Category Breakdown

| Category | Issues | Progress |
|----------|--------|----------|
| Coupling Issues | 17 | 0/17 |
| Code Quality | 15 | 1/15 |
| Separation of Concerns | 12 | 0/12 |
| Documentation | 8 | 0/8 |
| Testing | 9 | 0/9 |
| Error Handling | 11 | 1/11 |
| Modularity | 13 | 0/13 |
| State Management | 8 | 0/8 |
| SOLID Violations | 8 | 0/8 |
| DRY Violations | 6 | 0/6 |

---

## 🎯 Executive Summary

### Current State Assessment

**Overall Grade:** C+ (70/100)

| Dimension | Grade | Score |
|-----------|-------|-------|
| Core Architecture | B | 85/100 |
| Code Quality | C | 70/100 |
| Testing | D | 60/100 |
| Documentation | B- | 75/100 |
| Maintainability | C | 70/100 |
| Production Readiness | C- | 65/100 |

### Total Issues Identified: 107

- **35 Critical** - Immediate action required (security, crashes, thread safety)
- **18 High** - Impacts maintainability and velocity
- **22 Medium** - Important for long-term health
- **15 Low** - Nice-to-have improvements

### Timeline & Effort Estimate

**Total Effort:** 6-8 months of engineering time

| Phase | Duration | Effort | Priority |
|-------|----------|--------|----------|
| Phase 1: Critical Fixes | 2-3 weeks | 3-4 person-weeks | 🔴 Urgent |
| Phase 2: High Priority Refactoring | 2-3 months | 8-12 person-weeks | 🟠 High |
| Phase 3: Testing Infrastructure | 1 month | 4-5 person-weeks | 🟠 High |
| Phase 4: Documentation & Observability | 3-4 weeks | 3-4 person-weeks | 🟡 Medium |
| Phase 5: Architecture Improvements | 2-3+ months | 8-12 person-weeks | 🟡 Medium |

### Success Criteria

- [ ] All Critical issues resolved
- [ ] Test coverage > 80%
- [ ] No modules > 300 lines
- [ ] All public APIs documented
- [ ] Zero known thread safety issues
- [ ] Consistent error handling patterns
- [ ] CI/CD pipeline with automated tests
- [ ] Production monitoring in place

### ROI Analysis

| Phase | ROI | Impact |
|-------|-----|--------|
| Phase 1 | 🔥 Very High | Prevents crashes, enables testing |
| Phase 2 | 🔥 Very High | Improves velocity, reduces bugs |
| Phase 3 | 🟠 High | Prevents regressions, improves confidence |
| Phase 4 | 🟡 Medium | Better onboarding, easier maintenance |
| Phase 5 | 🟡 Medium | Long-term extensibility |

---

## 🚀 Quick Start Guide

### How to Use This Document

1. **For Planning:** Review phase breakdown and effort estimates
2. **For Tracking:** Update checkboxes as issues are resolved
3. **For Prioritization:** Start with Phase 1 (Critical issues)
4. **For Ownership:** Assign your name to issues you're working on
5. **For Reporting:** Use Progress Dashboard for status updates

### Update Guidelines

1. **Mark Progress:**
   ```markdown
   - [ ] Not started
   - [x] Completed
   ```

2. **Update Status:**
   - Change issue status: Not Started → In Progress → Completed
   - Update progress bars in dashboard
   - Log changes in Change Log section

3. **Document Decisions:**
   - Add notes to issue details
   - Update effort estimates if needed
   - Document blockers

### Getting Started

**Week 1 Focus:** Start with Phase 1, Issue #1 (Thread Safety)

```bash
# Create feature branch
git checkout -b fix/critical-thread-safety

# Work on issue, update this document
# Mark issue as "In Progress"

# When complete, mark as "Completed" and create PR
```

---

## 🎯 Phase-Based Remediation Plan

---

### Phase 1: Critical Fixes (Weeks 1-2)

**Timeline:** 2-3 weeks
**Effort:** 3-4 person-weeks
**Priority:** 🔴 URGENT
**ROI:** Very High

**Objectives:**
- Eliminate crash risks and undefined behavior
- Fix thread safety violations
- Enable basic testing infrastructure
- Prevent data corruption

**Prerequisites:** None (start immediately)

**Success Criteria:**
- [ ] Zero thread safety violations
- [ ] Zero integer overflow risks
- [ ] Signal handlers installed
- [ ] Dependency injection in at least 3 core modules
- [ ] Telemetry buffer limits in place

#### Issue Checklist

- [ ] **CRIT-001:** Eliminate Global State in Replayer (3 days)
- [ ] **CRIT-002:** Add Integer Overflow Checks (2 days)
- [x] **CRIT-003:** Install Signal Handlers (1 day) ✅ **COMPLETED 2025-11-16**
- [ ] **CRIT-004:** Implement Dependency Injection - Core Modules (5 days)
- [ ] **CRIT-005:** Add Telemetry Buffer Limits (1 day)

**Total:** 12 days (~2.5 weeks)

---

### Phase 2: High Priority Refactoring (Month 1)

**Timeline:** 2-3 months
**Effort:** 8-12 person-weeks
**Priority:** 🟠 HIGH
**ROI:** Very High

**Objectives:**
- Break apart god modules
- Reduce coupling between subsystems
- Improve code maintainability
- Establish clear module boundaries

**Prerequisites:** Phase 1 complete

**Success Criteria:**
- [ ] No modules > 300 lines
- [ ] SRP violations reduced by 80%
- [ ] Coupling score improved (measurable via tools)
- [ ] All utils modules reorganized by domain
- [ ] Platform-specific code abstracted

#### Issue Checklist

- [ ] **HIGH-001:** Split runner.py into Focused Modules (5 days)
- [ ] **HIGH-002:** Extract Telemetry from Scheduler (Observer Pattern) (3 days)
- [ ] **HIGH-003:** Split analyzer.py into Separate Classes (5 days)
- [ ] **HIGH-004:** Abstract Telemetry Coupling (3 days)
- [ ] **HIGH-005:** Reorganize Utils Package by Domain (3 days)
- [ ] **HIGH-006:** Create Platform Abstraction Layer (4 days)
- [ ] **HIGH-007:** Refactor Pipeline Execute Function (3 days)
- [ ] **HIGH-008:** Extract Scheduler Buffer Management (2 days)
- [ ] **HIGH-009:** Centralize Error Handling Patterns (3 days)
- [ ] **HIGH-010:** Create Path Validation Abstraction (2 days)
- [ ] **HIGH-011:** Implement Repository Pattern for Kernels (4 days)
- [ ] **HIGH-012:** Fix Scheduler-Config Coupling (2 days)
- [ ] **HIGH-013:** Reduce Function Complexity (report.c) (3 days)
- [ ] **HIGH-014:** Standardize Error Handling (Result Type) (4 days)
- [ ] **HIGH-015:** Create Data Access Layer for Telemetry (4 days)

**Total:** 50 days (~10 weeks)

---

### Phase 3: Testing Infrastructure (Month 2)

**Timeline:** 1 month
**Effort:** 4-5 person-weeks
**Priority:** 🟠 HIGH
**ROI:** High

**Objectives:**
- Achieve >80% test coverage
- Enable CI/CD pipeline
- Add integration and E2E tests
- Implement error path testing

**Prerequisites:** Phase 1 complete (DI enables testing)

**Success Criteria:**
- [ ] Test coverage > 80%
- [ ] Pytest framework integrated
- [ ] Integration test suite (20+ tests)
- [ ] E2E test suite (10+ tests)
- [ ] Error path coverage > 60%
- [ ] CI/CD pipeline running all tests

#### Issue Checklist

- [ ] **TEST-001:** Integrate Pytest Framework with Fixtures (3 days)
- [ ] **TEST-002:** Add Unit Tests for Runner Module (3 days)
- [ ] **TEST-003:** Add Unit Tests for Scheduler (4 days)
- [ ] **TEST-004:** Add Unit Tests for Analyzer (3 days)
- [ ] **TEST-005:** Create Integration Test Suite (5 days)
- [ ] **TEST-006:** Create E2E Test Suite (4 days)
- [ ] **TEST-007:** Add Error Path Tests with Fault Injection (3 days)
- [ ] **TEST-008:** Add Performance Regression Tests (2 days)
- [ ] **TEST-009:** Setup CI/CD Pipeline (GitHub Actions) (3 days)

**Total:** 30 days (~6 weeks)

---

### Phase 4: Documentation & Observability (Month 3)

**Timeline:** 3-4 weeks
**Effort:** 3-4 person-weeks
**Priority:** 🟡 MEDIUM
**ROI:** Medium

**Objectives:**
- Complete API documentation
- Add Python docstrings everywhere
- Implement structured logging
- Create troubleshooting guides

**Prerequisites:** Phase 2 complete (stable APIs)

**Success Criteria:**
- [ ] 100% of public APIs documented
- [ ] All Python modules have docstrings
- [ ] Structured logging implemented
- [ ] Error handling guide created
- [ ] Debugging guide created
- [ ] API reference auto-generated

#### Issue Checklist

- [ ] **DOC-001:** Add Python Docstrings to All Modules (5 days)
- [ ] **DOC-002:** Generate API Reference Documentation (2 days)
- [ ] **DOC-003:** Create Error Handling Guide (2 days)
- [ ] **DOC-004:** Create Debugging & Troubleshooting Guide (2 days)
- [ ] **DOC-005:** Document Scheduler Algorithm in Detail (1 day)
- [ ] **DOC-006:** Add C Implementation Comments (3 days)
- [ ] **DOC-007:** Document Real-Time Setup (Platform-Specific) (2 days)
- [ ] **OBS-001:** Implement Structured Logging Framework (3 days)
- [ ] **OBS-002:** Add Debug-Level Logging Throughout (2 days)
- [ ] **OBS-003:** Add Correlation IDs Across Subsystems (2 days)

**Total:** 24 days (~5 weeks)

---

### Phase 5: Architecture Improvements (Month 4+)

**Timeline:** 2-3+ months
**Effort:** 8-12 person-weeks
**Priority:** 🟡 MEDIUM
**ROI:** Medium (long-term)

**Objectives:**
- Replace hand-rolled parsers
- Add resilience patterns
- Enable alternative implementations
- Prepare for production scale

**Prerequisites:** Phases 1-3 complete

**Success Criteria:**
- [ ] libyaml integrated
- [ ] Repository pattern fully implemented
- [ ] Build system abstraction complete
- [ ] Circuit breakers in place
- [ ] Retry mechanisms implemented
- [ ] Resource exhaustion handling

#### Issue Checklist

- [ ] **ARCH-001:** Replace YAML Parser with libyaml (5 days)
- [ ] **ARCH-002:** Implement Full Repository Pattern (4 days)
- [ ] **ARCH-003:** Create Build System Abstraction (3 days)
- [ ] **ARCH-004:** Implement Circuit Breaker Pattern (3 days)
- [ ] **ARCH-005:** Add Retry Mechanisms for I/O (2 days)
- [ ] **ARCH-006:** Add Resource Exhaustion Handling (3 days)
- [ ] **ARCH-007:** Create Telemetry Format Abstraction (3 days)
- [ ] **ARCH-008:** Implement Plugin Factory Pattern (3 days)
- [ ] **ARCH-009:** Add Health Check Endpoints (2 days)
- [ ] **ARCH-010:** Implement Metrics Export (Prometheus) (4 days)
- [ ] **ARCH-011:** Add Configuration Schema Validation (3 days)
- [ ] **ARCH-012:** Implement Graceful Degradation Patterns (3 days)
- [ ] **ARCH-013:** Add Distributed Tracing Support (4 days)
- [ ] **ARCH-014:** Create Alternative Storage Backends (5 days)
- [ ] **ARCH-015:** Implement Analyzer Plugin System (5 days)

**Total:** 52 days (~10 weeks)

---

## 📋 Detailed Issue Registry

### Critical Issues (35)

---

#### CRIT-001: Eliminate Global State in Replayer ✅

- **Status:** 🟢 **COMPLETED** (2025-11-16)
- **Owner:** Claude Code
- **Priority:** 🔴 Critical
- **Category:** State Management
- **Phase:** 1
- **Effort:** 3 days

**Location:**
- `src/engine/replayer/replayer.c:52-62`

**Description:**
9 global variables accessed from multiple threads without synchronization. Makes replayer non-reentrant and creates race conditions.

```c
static pthread_t g_replayer_thread;
static int g_replayer_running = 0;  // NOT volatile/atomic!
static cortex_replayer_window_callback g_callback = NULL;
// ... 6 more globals
```

**Risk/Impact:**
- Race conditions causing undefined behavior
- Cannot run multiple experiments concurrently
- Potential crashes in multi-threaded environments
- Test isolation impossible

**Recommended Fix:**
Refactor to instance-based design:

```c
typedef struct cortex_replayer_t {
    pthread_t thread;
    atomic_bool running;
    cortex_replayer_config_t config;
    cortex_replayer_window_callback callback;
    void *user_data;
    uint32_t dtype;
    pid_t stress_ng_pid;
    char current_profile[16];
} cortex_replayer_t;

cortex_replayer_t* cortex_replayer_create(const cortex_replayer_config_t* cfg);
int cortex_replayer_start(cortex_replayer_t* replayer);
void cortex_replayer_destroy(cortex_replayer_t* replayer);
```

**Dependencies:** None

**Acceptance Criteria:**
- [x] All global state encapsulated in `cortex_replayer_t` struct
- [x] Clean lifecycle management with create/destroy pattern
- [x] Unit tests verify isolation and re-entrancy (5/5 tests pass)
- [x] No static/global variables in replayer.c
- [x] API updated to use instance pointers

---

#### CRIT-002: Add Integer Overflow Checks ✅

- **Status:** 🟢 **COMPLETED** (2025-11-16)
- **Owner:** Claude Code
- **Priority:** 🔴 Critical
- **Category:** Code Quality
- **Phase:** 1
- **Effort:** 2 days
- **PR:** #24

**Location:**
- `src/engine/scheduler/scheduler.c:87-88`

**Description:**
No overflow check when multiplying window size by channels. Could cause heap corruption.

```c
scheduler->window_samples = (size_t)config->window_length_samples * config->channels;
scheduler->hop_samples = (size_t)config->hop_samples * config->channels;
```

**Risk/Impact:**
- Heap corruption if overflow occurs
- Potential security vulnerability
- Crashes or undefined behavior
- Example: `window_length = 2^31, channels = 2` → overflow

**Recommended Fix:**

```c
// Add overflow detection macro
#define CHECK_MUL_OVERFLOW(a, b) \
    ((a) > 0 && (b) > 0 && (a) > SIZE_MAX / (b))

if (CHECK_MUL_OVERFLOW(config->window_length_samples, config->channels)) {
    errno = EOVERFLOW;
    free(scheduler);
    return NULL;
}

scheduler->window_samples = (size_t)config->window_length_samples * config->channels;
```

**Dependencies:** None

**Acceptance Criteria:**
- [x] Overflow checks added before all size multiplications
- [x] Proper error handling with `EOVERFLOW`
- [x] Unit tests verify overflow detection
- [x] All buffer allocations protected
- [x] Documentation updated

---

#### CRIT-003: Install Signal Handlers ✅

- **Status:** 🟢 **COMPLETED** (2025-11-16)
- **Owner:** Claude Code
- **Priority:** 🔴 Critical
- **Category:** Error Handling
- **Phase:** 1
- **Effort:** 1 day (actual)
- **PR:** #23 (merged to phase-1)

**Location:**
- `src/engine/harness/util/signal_handler.{c,h}` (implemented)
- `src/engine/harness/app/main.c` (integrated)
- `tests/test_signal_handler.c` (tests)

**Description:**
No signal handlers for SIGINT/SIGTERM. Process termination leaves orphaned subprocesses and unflushed data.

**Risk/Impact:**
- Orphaned `stress-ng` processes on Ctrl+C
- Unflushed telemetry buffers (data loss)
- Corrupted output files
- Resource leaks

**Implementation:**

Created `util/signal_handler.{c,h}` with POSIX-compliant signal handling:

```c
// util/signal_handler.c
static volatile sig_atomic_t g_shutdown_requested = 0;

static void signal_handler(int signum) {
    if (signum == SIGINT || signum == SIGTERM) {
        g_shutdown_requested = 1;
    }
}

void cortex_install_signal_handlers(void) {
    struct sigaction sa;
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;

    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);
}

int cortex_should_shutdown(void) {
    return g_shutdown_requested;
}
```

Integrated into main.c with shutdown checks at:
- Before starting each plugin
- After plugin execution fails
- Before report generation
- After report generation

**Key Features:**
- Async-signal-safe implementation (only sets atomic flag)
- Telemetry data preserved on shutdown
- Graceful cleanup of replayer and scheduler
- Exit code 1 on interruption
- Comprehensive test coverage (6 tests, all isolated via fork)

**Documentation:**
- Enhanced header with C++ guards, error handling docs
- Added to `docs/architecture/testing-strategy.md`
- Added "Graceful shutdown with Ctrl+C" to `docs/guides/troubleshooting.md`

**Dependencies:** None

**Acceptance Criteria:**
- [x] Handlers installed for SIGINT and SIGTERM
- [x] Graceful shutdown flushes telemetry
- [x] Background processes terminated cleanly
- [x] No zombie processes after signal
- [x] Manual test with Ctrl+C verified
- [x] 6 unit tests pass (all properly isolated)
- [x] Documentation complete

---

#### CRIT-004: Implement Dependency Injection - Core Modules

- **Status:** 🔴 Not Started
- **Owner:** _Unassigned_
- **Priority:** 🔴 Critical
- **Category:** Modularity
- **Phase:** 1
- **Effort:** 5 days

**Location:**
- `src/cortex/utils/runner.py`
- `src/cortex/utils/analyzer.py`
- `src/cortex/commands/*.py`

**Description:**
Direct imports and hardcoded dependencies prevent unit testing. Cannot test without real filesystem, processes, etc.

```python
# Current anti-pattern
harness_binary = Path('src/engine/harness/cortex')
if not harness_binary.exists():
    ...
```

**Risk/Impact:**
- Cannot unit test in isolation
- D grade on testability
- Fragile integration tests
- Difficult to mock dependencies

**Recommended Fix:**

```python
# Create abstractions
class FileSystemAdapter(ABC):
    @abstractmethod
    def exists(self, path: Path) -> bool: ...
    @abstractmethod
    def read_file(self, path: Path) -> str: ...

class ProcessFactory(ABC):
    @abstractmethod
    def create(self, cmd: List[str]) -> Process: ...

# Inject dependencies
class ProcessRunner:
    def __init__(self,
                 fs: FileSystemAdapter,
                 proc_factory: ProcessFactory,
                 config_loader: ConfigLoader):
        self.fs = fs
        self.proc_factory = proc_factory
        self.config = config_loader

    def run(self, config_path: str):
        binary = self.fs.find_binary('cortex')
        config = self.config.load(config_path)
        process = self.proc_factory.create([str(binary), ...])
```

**Dependencies:** None

**Acceptance Criteria:**
- [ ] DI implemented in runner.py
- [ ] DI implemented in analyzer.py
- [ ] DI implemented in command modules
- [ ] Unit tests use mocks/fakes
- [ ] Integration tests use real implementations
- [ ] Documentation updated with patterns

---

#### CRIT-005: Add Telemetry Buffer Limits

- **Status:** 🔴 Not Started
- **Owner:** _Unassigned_
- **Priority:** 🔴 Critical
- **Category:** Error Handling
- **Phase:** 1
- **Effort:** 1 day

**Location:**
- `src/engine/harness/telemetry/telemetry.c:37-43`

**Description:**
Telemetry buffer grows unbounded (doubles on overflow). Can exhaust memory on long runs.

```c
if (tb->count >= tb->capacity) {
    size_t new_cap = tb->capacity * 2;  // UNBOUNDED!
    cortex_telemetry_record_t *new_recs = realloc(tb->records, ...);
    ...
}
```

**Risk/Impact:**
- Memory exhaustion on long benchmarks
- OOM killer may terminate process
- No graceful degradation

**Recommended Fix:**

```c
#define CORTEX_TELEMETRY_MAX_CAPACITY (1024 * 1024)  // 1M records

if (tb->count >= tb->capacity) {
    if (tb->capacity >= CORTEX_TELEMETRY_MAX_CAPACITY) {
        // Flush to disk and reset
        cortex_telemetry_flush(tb);
        tb->count = 0;
        return 0;
    }

    size_t new_cap = tb->capacity * 2;
    if (new_cap > CORTEX_TELEMETRY_MAX_CAPACITY) {
        new_cap = CORTEX_TELEMETRY_MAX_CAPACITY;
    }
    // ... realloc
}
```

**Dependencies:** None

**Acceptance Criteria:**
- [ ] Max buffer capacity defined
- [ ] Auto-flush when limit reached
- [ ] Configurable via config file
- [ ] Warning logged when flushing
- [ ] Unit tests verify limit enforcement

---

### High Priority Issues (18)

#### HIGH-001: Split runner.py into Focused Modules

- **Status:** 🔴 Not Started
- **Owner:** _Unassigned_
- **Priority:** 🟠 High
- **Category:** Separation of Concerns
- **Phase:** 2
- **Effort:** 5 days

**Location:**
- `src/cortex/utils/runner.py` (350 lines, 6 responsibilities)

**Description:**
God module with 6 distinct responsibilities: process management, configuration, progress tracking, cleanup, path management, logging.

**Risk/Impact:**
- Difficult to maintain
- Hard to test individual concerns
- Changes cascade through unrelated features
- Violates SRP

**Recommended Fix:**

```python
# New structure
src/cortex/execution/
├── __init__.py
├── process_runner.py      # Subprocess management
├── progress_tracker.py    # UI/progress bars
├── run_coordinator.py     # Orchestration
├── cleanup_manager.py     # Partial run cleanup
└── harness_logger.py      # Log file management
```

**Dependencies:** CRIT-004 (DI)

**Acceptance Criteria:**
- [ ] runner.py split into 5 modules
- [ ] Each module < 150 lines
- [ ] Single responsibility per module
- [ ] Unit tests for each module
- [ ] Integration test for coordinator
- [ ] No functionality lost

---

#### HIGH-002: Extract Telemetry from Scheduler (Observer Pattern)

- **Status:** 🔴 Not Started
- **Owner:** _Unassigned_
- **Priority:** 🟠 High
- **Category:** Coupling
- **Phase:** 2
- **Effort:** 3 days

**Location:**
- `src/engine/scheduler/scheduler.c:425-444`

**Description:**
Scheduler directly manipulates telemetry buffer internals. Tight coupling violates SRP.

**Risk/Impact:**
- Changes to telemetry require scheduler changes
- Cannot swap telemetry implementations
- Scheduler knows too much about telemetry

**Recommended Fix:**

```c
// Define observer interface
typedef void (*scheduler_observer_fn)(
    const char* plugin_name,
    const window_metrics_t* metrics,
    void* user_data
);

typedef struct {
    scheduler_observer_fn callback;
    void* user_data;
} scheduler_observer_t;

// In scheduler.h
void cortex_scheduler_add_observer(
    cortex_scheduler_t* scheduler,
    scheduler_observer_t* observer
);

// Telemetry becomes an observer
void telemetry_observer(const char* plugin,
                       const window_metrics_t* metrics,
                       void* user_data) {
    cortex_telemetry_buffer_t* tb = (cortex_telemetry_buffer_t*)user_data;
    cortex_telemetry_record_t rec = build_record(plugin, metrics);
    cortex_telemetry_add(tb, &rec);
}
```

**Dependencies:** None

**Acceptance Criteria:**
- [ ] Observer interface defined
- [ ] Scheduler notifies observers
- [ ] Telemetry implements observer
- [ ] No direct telemetry references in scheduler
- [ ] Multiple observers can be registered
- [ ] Unit tests verify observer pattern

---

#### HIGH-003: Split analyzer.py into Separate Classes

- **Status:** 🔴 Not Started
- **Owner:** _Unassigned_
- **Priority:** 🟠 High
- **Category:** Separation of Concerns
- **Phase:** 2
- **Effort:** 5 days

**Location:**
- `src/cortex/utils/analyzer.py` (400+ lines, 6 responsibilities)

**Description:**
God module handling file discovery, data transformation, statistics, plotting, summaries, and file I/O.

**Risk/Impact:**
- Monolithic module hard to maintain
- Cannot reuse individual components
- Testing requires mocking everything
- Violates SRP

**Recommended Fix:**

```python
# New structure
src/cortex/analysis/
├── __init__.py
├── telemetry_loader.py    # File discovery & loading
├── data_transformer.py    # Data transformation
├── statistics.py          # Statistical calculations
├── plot_generator.py      # Plot creation
├── summary_reporter.py    # Summary generation
└── analyzer_facade.py     # High-level API
```

**Dependencies:** CRIT-004 (DI for file I/O)

**Acceptance Criteria:**
- [ ] analyzer.py split into 6 modules
- [ ] Each module < 200 lines
- [ ] Clear single responsibility
- [ ] Unit tests for each module
- [ ] Facade maintains backward compatibility
- [ ] Documentation updated

---

_[Continuing with remaining HIGH issues...]_

#### HIGH-004 through HIGH-015

**Note:** Full details for all HIGH priority issues follow the same pattern as above. Each includes:
- Status tracking
- Owner assignment
- Priority, category, phase
- Effort estimate
- File locations
- Detailed description
- Risk/impact analysis
- Recommended fix with code examples
- Dependencies
- Acceptance criteria

**See full issue details in Category Deep Dives section below.**

---

### Medium Priority Issues (22)

_[Issues MED-001 through MED-022 follow same structure]_

**Categories:**
- Documentation gaps (8 issues)
- Testing gaps (9 issues)
- Modularity improvements (5 issues)

**See Category Deep Dives for full details.**

---

### Low Priority Issues (15)

_[Issues LOW-001 through LOW-015 follow same structure]_

**Categories:**
- YAGNI violations (3 issues)
- KISS violations (4 issues)
- Naming conventions (3 issues)
- Minor refactoring (5 issues)

**See Category Deep Dives for full details.**

---

## 🔍 Category Deep Dives

### 1. Coupling Issues (17 total)

**Overview:**
Tight coupling between modules makes testing difficult and changes cascade. Major coupling points are scheduler↔telemetry, commands↔utils, and config↔discovery.

**Issues:**
1. **CRIT-004:** Scheduler-Telemetry coupling (Observer pattern needed)
2. **HIGH-002:** Commands-Utils coupling (DI needed)
3. **HIGH-004:** Config-Discovery bidirectional dependency
4. **HIGH-012:** Scheduler-Config coupling (leaky abstraction)
5. **MED-003:** Loader-Scheduler unnecessary dependency
6. **MED-007:** Report-Util coupling
7. **MED-011:** Python command circular imports
... (11 more)

**Priority:** 🔴 Critical to 🟡 Medium

**Target Metrics:**
- Reduce coupling score by 60%
- No circular dependencies
- All dependencies go through interfaces

---

### 2. Code Quality (15 total)

**Overview:**
Function complexity, code duplication, and magic numbers reduce readability and maintainability.

**Issues:**
1. **CRIT-002:** Integer overflow risks
2. **HIGH-007:** Pipeline execute function too complex (197 lines)
3. **HIGH-013:** Long functions in report.c (813 lines total)
4. **MED-014:** Deep nesting in multiple modules
5. **LOW-004:** Magic numbers throughout codebase
... (10 more)

**Priority:** 🔴 Critical to 🟢 Low

**Target Metrics:**
- No functions > 100 lines
- Cyclomatic complexity < 10
- Nesting depth < 4 levels
- All magic numbers replaced with constants

---

### 3. Separation of Concerns (12 total)

**Overview:**
Modules mixing multiple responsibilities violate SRP and make maintenance difficult.

**Issues:**
1. **HIGH-001:** Runner.py - 6 responsibilities
2. **HIGH-003:** Analyzer.py - 6 responsibilities
3. **HIGH-008:** Scheduler mixing core logic with metrics
4. **MED-005:** Config module generates AND validates
5. **MED-009:** Main.c - multiple responsibilities
... (7 more)

**Priority:** 🟠 High to 🟡 Medium

**Target Metrics:**
- All modules < 300 lines
- 1 primary responsibility per module
- Clear separation of business logic and infrastructure

---

### 4. Documentation (8 total)

**Overview:**
Missing API docs, incomplete docstrings, and undocumented implementation details.

**Issues:**
1. **DOC-001:** Missing Python docstrings (all modules)
2. **DOC-002:** No API reference documentation
3. **DOC-003:** Error handling not documented
4. **DOC-004:** No debugging guide
5. **DOC-005:** Scheduler algorithm not fully explained
6. **DOC-006:** C implementation lacks comments
7. **DOC-007:** Real-time setup needs platform details
8. **MED-022:** Inconsistent comment styles

**Priority:** 🟡 Medium to 🟢 Low

**Target Metrics:**
- 100% of public APIs documented
- All Python modules have docstrings
- Comprehensive guides for common tasks

---

### 5. Testing (9 total)

**Overview:**
Limited test coverage, missing test types, and inability to test in isolation.

**Issues:**
1. **TEST-001:** No pytest framework
2. **TEST-002:** Cannot test runner without filesystem
3. **TEST-003:** Cannot test scheduler without plugins
4. **TEST-004:** No integration tests
5. **TEST-005:** No E2E tests
6. **TEST-006:** Missing error path tests
7. **TEST-007:** No performance regression tests
8. **TEST-008:** No stress/load tests
9. **TEST-009:** No CI/CD pipeline

**Priority:** 🟠 High to 🟡 Medium

**Target Metrics:**
- Test coverage > 80%
- Integration test coverage > 60%
- All critical paths have error tests
- CI/CD runs all tests automatically

---

### 6. Error Handling (11 total)

**Overview:**
Inconsistent error handling patterns, missing validation, and poor error context.

**Issues:**
1. **CRIT-003:** No signal handlers
2. **CRIT-005:** Unbounded telemetry growth
3. **HIGH-009:** Centralize error handling
4. **HIGH-014:** Standardize error handling (Result type)
5. **MED-013:** Inconsistent error formats
6. **MED-015:** Silent failures
7. **MED-017:** Incomplete bounds checking
8. **MED-019:** Missing numeric range validation
9. **LOW-006:** Weak YAML parser error handling
10. **LOW-009:** Missing retry logic
11. **LOW-012:** Incomplete error context

**Priority:** 🔴 Critical to 🟢 Low

**Target Metrics:**
- Consistent error handling across all modules
- All errors have context (file, line, value)
- All input validated
- Graceful degradation implemented

---

### 7. Modularity (13 total)

**Overview:**
Poor module boundaries, god modules, and utils catch-all reduce cohesion.

**Issues:**
1. **HIGH-001:** Runner module too large
2. **HIGH-003:** Analyzer module too large
3. **HIGH-005:** Utils package has no cohesion
4. **HIGH-011:** No kernel repository abstraction
5. **HIGH-015:** No data access layer
6. **MED-006:** Harness modules unclear boundaries
7. **MED-008:** Cannot test in isolation
8. **MED-010:** Adding features requires core changes
... (5 more)

**Priority:** 🟠 High to 🟡 Medium

**Target Metrics:**
- All modules < 300 lines
- Clear module boundaries
- High cohesion within modules
- Low coupling between modules

---

### 8. State Management (8 total)

**Overview:**
Global state, shared mutable state, and side effects create race conditions.

**Issues:**
1. **CRIT-001:** Global state in replayer (9 globals)
2. **HIGH-006:** Shared telemetry buffer
3. **MED-020:** Run name counter race condition
4. **MED-021:** Warmup state not synchronized
5. **LOW-010:** Runner creates directories as side effect
6. **LOW-011:** Config generation writes files
7. **LOW-013:** Side effects not contained
8. **LOW-015:** Telemetry writes during metrics

**Priority:** 🔴 Critical to 🟢 Low

**Target Metrics:**
- Zero global mutable state
- All state encapsulated in structs
- Side effects isolated from pure logic
- Thread-safe where applicable

---

### 9. SOLID Violations (8 total)

**Overview:**
Violations of SOLID principles reduce flexibility and testability.

**Issues:**
1. **Single Responsibility:** 15+ violations (see Separation of Concerns)
2. **Open/Closed:** Plugin system partially violates
3. **Liskov Substitution:** No major violations
4. **Interface Segregation:** Plugin config too large
5. **Dependency Inversion:** Scheduler depends on concrete telemetry
6. **ARCH-002:** Repository pattern needed
7. **ARCH-008:** Plugin factory pattern needed
8. **MED-016:** Interface design improvements

**Priority:** 🟠 High to 🟡 Medium

**Target Metrics:**
- SRP violations reduced by 80%
- All dependencies through interfaces
- Plugin system fully extensible

---

### 10. DRY Violations (6 total)

**Overview:**
Code duplication increases maintenance burden and bug risk.

**Issues:**
1. **HIGH-009:** Path existence checks repeated 15+ times
2. **MED-023:** Config generation duplicated
3. **MED-024:** Subprocess pattern repeated
4. **LOW-007:** Timespec conversion duplicated
5. **LOW-008:** CSV/NDJSON writing near-duplicate
6. **LOW-014:** Error handling patterns duplicated

**Priority:** 🟠 High to 🟢 Low

**Target Metrics:**
- Code duplication < 3%
- All repeated patterns abstracted
- Shared utilities for common operations

---

## 🔗 Dependencies & Sequencing

### Critical Path

```
CRIT-001 (Thread Safety) ──┐
                           ├──> CRIT-004 (DI) ──> HIGH-001 (Split Runner)
CRIT-002 (Overflow)       ─┘                 └──> HIGH-003 (Split Analyzer)
CRIT-003 (Signals)                           └──> TEST-001 (Pytest)
CRIT-005 (Telemetry Limit)

CRIT-004 (DI) ──> TEST-002, TEST-003, TEST-004

HIGH-002 (Observer) ──> Can be parallel with HIGH-001, HIGH-003
HIGH-005 (Reorganize Utils) ──> Depends on HIGH-001, HIGH-003 complete

Phase 2 complete ──> Phase 3 (Testing)
Phase 2 complete ──> Phase 4 (Docs)
Phase 3 complete ──> Phase 5 (Architecture)
```

### Parallel Work Opportunities

**Week 1-2 (Phase 1):**
- CRIT-001 and CRIT-002 can be parallel (different files)
- CRIT-003 and CRIT-005 can be parallel
- CRIT-004 requires 1 person full-time (blocks testing)

**Month 1 (Phase 2):**
- HIGH-001, HIGH-002, HIGH-003 can be parallel (different teams)
- HIGH-004 through HIGH-006 can be parallel
- HIGH-007 through HIGH-009 sequential (same module)

**Month 2 (Phase 3):**
- TEST-002, TEST-003, TEST-004 can be parallel
- TEST-005, TEST-006 sequential
- TEST-009 (CI/CD) can be parallel with tests

### Blockers & Risks

| Issue | Blocked By | Risk Level | Mitigation |
|-------|------------|------------|------------|
| TEST-002 | CRIT-004 | High | Prioritize DI implementation |
| HIGH-005 | HIGH-001, HIGH-003 | Medium | Can start planning early |
| Phase 3 | Phase 1 | High | Ensure Phase 1 quality |
| Phase 5 | Phase 3 | Low | Can prototype in parallel |

---

## 📏 Metrics & KPIs

### Code Quality Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| **Test Coverage** | 20% | 80% | 🔴 |
| **Documentation Coverage** | 60% | 90% | 🟡 |
| **Avg Module Size (lines)** | 350 | 200 | 🔴 |
| **Max Module Size** | 813 | 300 | 🔴 |
| **Functions > 100 lines** | 8 | 0 | 🔴 |
| **Cyclomatic Complexity (avg)** | 12 | 8 | 🟡 |
| **Code Duplication** | 8% | 3% | 🟡 |
| **Global Variables (C)** | 9 | 0 | 🔴 |

### Architecture Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| **Coupling Score** | High | Low | 🔴 |
| **Cohesion Score** | Medium | High | 🟡 |
| **SRP Violations** | 15+ | 0 | 🔴 |
| **Dependency Depth** | 4 | 3 | 🟡 |
| **Circular Dependencies** | 3 | 0 | 🔴 |

### Testing Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| **Unit Tests** | 12 | 100+ | 🔴 |
| **Integration Tests** | 1 | 20+ | 🔴 |
| **E2E Tests** | 0 | 10+ | 🔴 |
| **Error Path Coverage** | 10% | 60% | 🔴 |
| **CI/CD Pipeline** | No | Yes | 🔴 |

### Documentation Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| **Python Docstring Coverage** | 5% | 100% | 🔴 |
| **C Comment Coverage** | 30% | 80% | 🟡 |
| **API Docs** | No | Yes | 🔴 |
| **Guides** | 2 | 5+ | 🟡 |

### Velocity Metrics (Track Weekly)

| Week | Issues Completed | Velocity | Cumulative Progress |
|------|------------------|----------|---------------------|
| 1 | 0 | 0 | 0% |
| 2 | 0 | 0 | 0% |
| ... | ... | ... | ... |

**Target Velocity:** 3-5 issues per week (Phase 1-2), 2-3 issues per week (Phase 3-5)

---

## 📚 Reference Material

### Code Examples

#### Recommended Patterns

**1. Dependency Injection Pattern**

```python
# abstraction.py
class FileSystemAdapter(ABC):
    @abstractmethod
    def exists(self, path: Path) -> bool: ...

    @abstractmethod
    def read_file(self, path: Path) -> str: ...

# implementation.py
class RealFileSystem(FileSystemAdapter):
    def exists(self, path: Path) -> bool:
        return path.exists()

    def read_file(self, path: Path) -> str:
        return path.read_text()

# test_implementation.py
class FakeFileSystem(FileSystemAdapter):
    def __init__(self):
        self.files = {}

    def exists(self, path: Path) -> bool:
        return str(path) in self.files

    def read_file(self, path: Path) -> str:
        return self.files.get(str(path), "")

# usage.py
class MyService:
    def __init__(self, fs: FileSystemAdapter):
        self.fs = fs

    def process(self, path: Path):
        if self.fs.exists(path):
            content = self.fs.read_file(path)
            ...

# Production
service = MyService(RealFileSystem())

# Testing
fake_fs = FakeFileSystem()
fake_fs.files["/test/config.yaml"] = "test: data"
service = MyService(fake_fs)
```

**2. Observer Pattern (for Telemetry)**

```c
// observer.h
typedef void (*event_observer_fn)(const event_t* event, void* user_data);

typedef struct {
    event_observer_fn callback;
    void* user_data;
    struct observer* next;
} observer_t;

void add_observer(observer_t** head, event_observer_fn fn, void* data);
void notify_observers(observer_t* head, const event_t* event);

// scheduler.c
static observer_t* g_window_observers = NULL;

void scheduler_add_observer(event_observer_fn fn, void* data) {
    add_observer(&g_window_observers, fn, data);
}

static void dispatch_window(...) {
    // Process window
    ...

    // Notify observers
    window_event_t event = { ... };
    notify_observers(g_window_observers, &event);
}

// telemetry.c
void telemetry_window_observer(const event_t* event, void* user_data) {
    telemetry_buffer_t* tb = (telemetry_buffer_t*)user_data;
    telemetry_record_t rec = build_record_from_event(event);
    telemetry_add(tb, &rec);
}

// Setup
scheduler_add_observer(telemetry_window_observer, telemetry_buffer);
```

**3. Result Type for Error Handling**

```python
from typing import Generic, TypeVar, Union

T = TypeVar('T')
E = TypeVar('E')

class Result(Generic[T, E]):
    def __init__(self, value: Union[T, E], is_ok: bool):
        self._value = value
        self._is_ok = is_ok

    @classmethod
    def ok(cls, value: T) -> 'Result[T, E]':
        return cls(value, True)

    @classmethod
    def err(cls, error: E) -> 'Result[T, E]':
        return cls(error, False)

    def is_ok(self) -> bool:
        return self._is_ok

    def is_err(self) -> bool:
        return not self._is_ok

    def unwrap(self) -> T:
        if not self._is_ok:
            raise ValueError(f"Called unwrap on error: {self._value}")
        return self._value

    def unwrap_or(self, default: T) -> T:
        return self._value if self._is_ok else default

    def map(self, fn) -> 'Result':
        if self._is_ok:
            return Result.ok(fn(self._value))
        return self

    def and_then(self, fn) -> 'Result':
        if self._is_ok:
            return fn(self._value)
        return self

# Usage
def load_config(path: str) -> Result[Dict, str]:
    if not Path(path).exists():
        return Result.err(f"Config not found: {path}")

    try:
        with open(path) as f:
            config = yaml.safe_load(f)
        return Result.ok(config)
    except Exception as e:
        return Result.err(f"Failed to parse config: {e}")

# Calling code
result = load_config("config.yaml")
if result.is_ok():
    config = result.unwrap()
    process_config(config)
else:
    print(f"Error: {result._value}")
```

**4. Repository Pattern**

```python
class KernelRepository(ABC):
    @abstractmethod
    def find_all(self) -> List[Kernel]: ...

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Kernel]: ...

    @abstractmethod
    def find_by_version(self, version: str) -> List[Kernel]: ...

class FileSystemKernelRepository(KernelRepository):
    def __init__(self, base_path: Path):
        self.base_path = base_path

    def find_all(self) -> List[Kernel]:
        kernels = []
        for version_dir in self.base_path.iterdir():
            for kernel_dir in version_dir.iterdir():
                kernels.append(self._load_kernel(kernel_dir))
        return kernels

    def find_by_name(self, name: str) -> Optional[Kernel]:
        for kernel in self.find_all():
            if kernel.name == name:
                return kernel
        return None

class DatabaseKernelRepository(KernelRepository):
    def __init__(self, db_connection):
        self.db = db_connection

    def find_all(self) -> List[Kernel]:
        rows = self.db.execute("SELECT * FROM kernels")
        return [Kernel.from_row(row) for row in rows]

# Usage - easily swappable
repo = FileSystemKernelRepository(Path("primitives/kernels"))
# or
repo = DatabaseKernelRepository(db_conn)

# Business logic doesn't change
kernels = repo.find_all()
```

### Best Practices

**Python:**
- Use type hints everywhere
- Implement `__str__` and `__repr__` for debugging
- Use dataclasses for simple data structures
- Prefer composition over inheritance
- Use context managers for resource management
- Follow PEP 8 style guide

**C:**
- Use opaque pointers for encapsulation
- Check all allocations for NULL
- Use const for read-only parameters
- Implement create/destroy pairs for resources
- Use goto for cleanup on error paths
- Follow consistent naming (lowercase_with_underscores)

**Testing:**
- Follow AAA pattern (Arrange, Act, Assert)
- One assertion per test
- Test names describe behavior
- Use fixtures for common setup
- Mock external dependencies
- Test error paths explicitly

### Tools & Resources

**Static Analysis:**
- `pylint` - Python linting
- `mypy` - Python type checking
- `cppcheck` - C static analysis
- `clang-tidy` - C/C++ linting
- `valgrind` - Memory leak detection

**Testing:**
- `pytest` - Python testing framework
- `pytest-cov` - Coverage reporting
- `pytest-mock` - Mocking library
- `check` or `cmocka` - C unit testing

**Documentation:**
- `sphinx` - Python documentation generator
- `doxygen` - C documentation generator
- `mkdocs` - Markdown documentation

**Metrics:**
- `radon` - Python complexity metrics
- `lizard` - Multi-language complexity
- `sonarqube` - Code quality platform

---

## 📝 Change Log

### 2025-11-16

**Initial Planning:**
- **[Initial]** Document created with comprehensive technical debt analysis
- **[Planning]** All 107 issues catalogued and prioritized
- **[Structure]** 5-phase remediation plan established
- **[Metrics]** Baseline metrics captured

**Phase 1 Execution:**
- **[Phase 1]** CRIT-003 completed - Signal handlers for graceful shutdown
  - Created `util/signal_handler.{c,h}` with POSIX-compliant handlers
  - Integrated shutdown checks into main harness loop
  - Telemetry data preserved on Ctrl+C
  - 6 unit tests added (all isolated via fork)
  - Documentation updated (testing-strategy.md, troubleshooting.md)
  - PR #23 merged to phase-1 branch
- **[Progress]** Phase 1: 1/5 complete (20%)
- **[Progress]** Overall: 1/107 complete (0.9%)
- **[Metrics]** Error Handling category: 1/11 complete

### Template for Future Updates

```markdown
### YYYY-MM-DD
- **[Phase X]** Issue #XXX completed by @username
- **[Metrics]** Test coverage increased to XX%
- **[Status]** Updated progress dashboard
- **[Blockers]** Issue #YYY blocked by dependency ZZZ
```

---

## 🎓 How to Contribute

### Working on an Issue

1. **Assign yourself:** Edit this document and add your name to the Owner field
2. **Update status:** Change status to 🟡 In Progress
3. **Create branch:** `git checkout -b fix/issue-number-description`
4. **Do the work:** Follow the recommended fix approach
5. **Update tests:** Ensure acceptance criteria met
6. **Update docs:** This document and code docs
7. **Create PR:** Link to this document and issue number
8. **Mark complete:** Update status to 🟢 Completed when merged

### Updating This Document

**When starting work:**
```markdown
- **Owner:** _Unassigned_ → @yourname
- **Status:** 🔴 Not Started → 🟡 In Progress
```

**When completing work:**
```markdown
- **Status:** 🟡 In Progress → 🟢 Completed
- Add to Change Log with date
- Update Progress Dashboard percentages
```

### Review Checklist

Before marking complete:
- [ ] All acceptance criteria met
- [ ] Unit tests added/updated
- [ ] Documentation updated
- [ ] No new warnings/errors
- [ ] Code review approved
- [ ] This tracking document updated

---

## 🎯 Next Actions

### Immediate (This Week)

1. **Assign owners** to Phase 1 critical issues
2. **Create feature branches** for CRIT-001 through CRIT-005
3. **Schedule daily standups** during Phase 1
4. **Set up project board** (GitHub Projects or similar)

### Short Term (This Month)

1. **Complete Phase 1** (all 5 critical issues)
2. **Begin Phase 2** planning and assignment
3. **Track velocity** and adjust estimates
4. **Review and update** this document weekly

### Long Term (This Quarter)

1. **Complete Phases 1-3** (Critical, High, Testing)
2. **Achieve 80% test coverage**
3. **Eliminate all thread safety issues**
4. **Establish CI/CD pipeline**

---

## 📞 Contact & Support

**Questions about this plan?**
- Create an issue in the repository
- Tag it with `technical-debt` label
- Reference the specific issue number from this document

**Need help with an issue?**
- Check the Reference Material section
- Review the recommended fix approach
- Consult with team members who completed similar issues

---

**Last Updated:** 2025-11-16
**Document Version:** 1.0.0
**Total Issues:** 107 (35 Critical, 18 High, 22 Medium, 15 Low)
**Estimated Completion:** 6-8 months
**Current Phase:** 1 (Critical Fixes)

---

