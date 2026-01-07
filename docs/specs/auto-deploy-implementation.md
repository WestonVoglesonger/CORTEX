# Auto-Deploy Device Adapters: Implementation Specification

**Version:** 3.0
**Date:** January 6, 2026
**Status:** Ready for Implementation
**Estimated Effort:** 400 LOC, 4 days

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Design Philosophy](#2-design-philosophy)
3. [Architecture Overview](#3-architecture-overview)
4. [Execution Modes](#4-execution-modes)
5. [Implementation Phases](#5-implementation-phases)
6. [API Reference](#6-api-reference)
7. [File Structure](#7-file-structure)
8. [CLI Interface](#8-cli-interface)
9. [Error Handling](#9-error-handling)
10. [Testing Strategy](#10-testing-strategy)
11. [Timeline & Milestones](#11-timeline--milestones)
12. [Success Criteria](#12-success-criteria)
13. [Appendix A: Full Flow Example](#appendix-a-full-flow-example)
14. [Appendix B: Manual Jetson Deployment](#appendix-b-manual-jetson-deployment)

---

## 1. Executive Summary

### 1.1 Goal

Enable remote benchmarking on any SSH-accessible device with automatic deployment. User provides `user@host`, system handles the rest.

### 1.2 User Experience

```bash
# Remote device (auto-deploy)
cortex run --device nvidia@192.168.1.123 --kernel car

# Local (default)
cortex run --kernel car

# Manual transport (power user)
cortex run --transport tcp://192.168.1.123:9000 --kernel car
```

**That's it. Three modes, zero configuration.**

### 1.3 What Changed from v2.0

**REMOVED (600 LOC saved):**
- ❌ Network scanning / auto-discovery
- ❌ Device registry (`~/.cortex/devices.yaml`)
- ❌ SSH config reading/writing
- ❌ `cortex device scan` command
- ❌ Interactive device selection prompts
- ❌ mDNS/Avahi discovery

**WHY:** Auto-discovery is slower (8.5s scan) than typing `user@host` (2s). Complexity for negative value.

**KEPT:**
- ✅ SSH-based deployment (rsync + remote build)
- ✅ Ephemeral execution (deploy → run → cleanup)
- ✅ `--device` flag for remote execution
- ✅ `--transport` flag for manual adapter management

### 1.4 Core Principles

**1. User Provides Connection String**
- Standard SSH format: `user@host`
- Works with IPs: `nvidia@192.168.1.123`
- Works with hostnames: `nvidia@jetson.local`
- Works with DNS: `ubuntu@server.example.com`

**2. Ephemeral Deployment**
- Deploy → Build → Run → Cleanup (every time)
- No persistent state on device
- Device returns to clean state after benchmark

**3. Zero Configuration**
- No setup ceremony
- No device registration
- No state management
- Just provide SSH connection, it works

### 1.5 Validation

**Proven on Real Hardware (January 6, 2026):**
- ✅ Manual deployment to Jetson Nano (ARM64) validated
- ✅ SSH connectivity confirmed (nvidia@192.168.1.123)
- ✅ Remote build successful (rsync → make all)
- ✅ Adapter lifecycle tested (nohup, PID tracking, cleanup)
- ✅ WiFi benchmarking validated (25.5ms P50 network overhead)

### 1.6 Metrics

| Metric | Value |
|--------|-------|
| **Total LOC** | 400 |
| Core implementation | 300 |
| CLI integration | 100 |
| **Timeline** | 4 days |
| **Risk Level** | Low (validated manually) |

---

## 2. Design Philosophy

### 2.1 Core Principles

**1. Leverage Standard Tools**
- SSH is universal, battle-tested, secure
- `user@host` syntax is familiar to anyone who uses SSH
- No custom protocols, no special configuration

**2. Ephemeral Execution**
- Device starts clean, ends clean
- No state tracking, no cache invalidation
- Every run is reproducible (fresh build)

**3. Simplicity Over Automation**
- Typing `user@host` takes 2 seconds
- Auto-discovery takes 8.5 seconds + complexity
- Choose simple over "clever"

**4. Fail Fast with Clear Errors**
- If SSH fails, show exactly what to check
- If build fails, show last 20 lines of output
- Every error includes actionable next steps

### 2.2 What We DON'T Do

- ❌ Auto-discover devices (user provides connection)
- ❌ Manage SSH keys (user responsibility)
- ❌ Install build tools on device (prerequisite)
- ❌ Cache builds across runs (too complex for v1)
- ❌ Support Windows targets (Linux/macOS only)

---

## 3. Architecture Overview

### 3.1 Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                cortex run / cortex pipeline              │
│                           │                              │
│                           ▼                              │
│                  parse_device_arg()                      │
│                           │                              │
│         ┌─────────────────┼─────────────────┐           │
│         ▼                 ▼                 ▼           │
│    --device         --transport        (default)        │
│    user@host         tcp://uri          local           │
│         │                 │                 │           │
│         ▼                 │                 ▼           │
│   ephemeral_deploy()      │        spawn_local_adapter()│
│   ┌──────────────┐        │                             │
│   │ 1. rsync     │        │                             │
│   │ 2. build     │        │                             │
│   │ 3. start     │        │                             │
│   │ 4. wait      │────────┘                             │
│   └──────────────┘        │                             │
│         │                 │                             │
│         └─────────────────┼─────────────────┐           │
│                           ▼                             │
│                  execute_benchmark()                    │
│                           │                             │
│         ┌─────────────────┴─────────────────┐           │
│         ▼                                   ▼           │
│    --device mode                       other modes      │
│    cleanup_device()                    (no cleanup)     │
│    (stop adapter, rm files)                             │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Execution Flow: `cortex run --device nvidia@192.168.1.123 --kernel car`

```
1. Parse arguments
   ├─ --device nvidia@192.168.1.123
   ├─ Split on '@' → user=nvidia, host=192.168.1.123

2. Deploy (ephemeral)
   ├─ rsync code: ~/CORTEX/ → nvidia@192.168.1.123:~/cortex-temp/
   │  └─ Exclude: .git, results, *.o, *.dylib, *.so
   │
   ├─ Remote build: ssh nvidia@192.168.1.123 "cd ~/cortex-temp && make clean && make all"
   │  └─ Stream output if --verbose
   │
   ├─ Start adapter: ssh nvidia@192.168.1.123 "nohup ~/cortex-temp/.../cortex_adapter_native tcp://:9000 &"
   │  ├─ Capture PID: echo $! > /tmp/cortex-adapter.pid
   │  └─ Wait for port: nc -z 192.168.1.123 9000 (retry 30s)

3. Run benchmark
   ├─ Use transport: tcp://192.168.1.123:9000
   ├─ Execute kernel: car
   └─ Save results: results/run-*/kernel-data/car/telemetry.ndjson

4. Cleanup
   ├─ Stop adapter: ssh nvidia@192.168.1.123 "kill $(cat /tmp/cortex-adapter.pid)"
   └─ Delete files: ssh nvidia@192.168.1.123 "rm -rf ~/cortex-temp /tmp/cortex-adapter.*"

5. Done
   └─ Device is clean (no CORTEX artifacts)
```

---

## 4. Execution Modes

### 4.1 Mode A: Local Execution (Default)

**When:**
- No `--device` or `--transport` specified

**Behavior:**
```bash
cortex run --kernel car
# Uses local adapter (current behavior, unchanged)
```

---

### 4.2 Mode B: Remote Auto-Deploy

**When:**
- User provides `--device user@host`

**Behavior:**
```bash
cortex run --device nvidia@192.168.1.123 --kernel car

# System does:
# 1. Parse: user=nvidia, host=192.168.1.123
# 2. Deploy: rsync → remote build → start adapter
# 3. Run: benchmark via tcp://192.168.1.123:9000
# 4. Cleanup: stop adapter, delete files
```

**Supported formats:**
```bash
# IP address
cortex run --device nvidia@192.168.1.123 --kernel car

# Hostname (.local mDNS)
cortex run --device nvidia@jetson.local --kernel car

# DNS name
cortex run --device ubuntu@server.example.com --kernel car

# Cloud VM
cortex run --device ubuntu@ec2-54-123-45-67.compute.amazonaws.com --kernel car
```

**Key properties:**
- ✅ Works with any SSH-accessible device
- ✅ Ephemeral (always fresh build)
- ✅ Device clean after run
- ❌ Rebuilds every time (~60s overhead)

---

### 4.3 Mode C: Manual Transport

**When:**
- User provides `--transport <uri>` flag

**Behavior:**
```bash
cortex run --transport tcp://192.168.1.123:9000 --kernel car

# System does:
# 1. Connect to adapter at tcp://192.168.1.123:9000
# 2. Run benchmark
# 3. No deployment, no cleanup (user manages lifecycle)
```

**Use case:**
- User has manually deployed adapter
- User wants persistent adapter (fast iteration)
- Testing/debugging adapter issues

---

### 4.4 Priority Resolution

```python
def determine_execution_mode(args):
    # 1. CLI --device (highest priority)
    if args.device:
        user, host = args.device.split('@')
        return AutoDeployMode(user=user, host=host)

    # 2. CLI --transport
    if args.transport:
        return ManualTransportMode(uri=args.transport)

    # 3. Default: local
    return LocalMode()
```

**Examples:**
```bash
# Override is always CLI first
cortex run --device nvidia@jetson config.yaml  # Uses nvidia@jetson (ignores config)
cortex run --transport local:// config.yaml    # Forces local (ignores config)
```

---

## 5. Implementation Phases

### Phase 1: SSH Deployment (2 days, 300 LOC)

**Deliverables:**
- SSH deployment subsystem
- Remote build orchestration
- Adapter lifecycle management

**Files:**
- `src/cortex/deploy/ssh_deployer.py` (300 LOC)

**Functions:**
```python
def ephemeral_deploy(user, host, verbose=False):
    """Deploy code, build remotely, start adapter."""

def cleanup_deployment(user, host):
    """Stop adapter, delete files."""
```

**Success Criteria:**
- [ ] Can rsync code to remote device
- [ ] Can build remotely via `make all`
- [ ] Can start adapter as background daemon
- [ ] Can stop adapter and cleanup files

---

### Phase 2: CLI Integration (1 day, 100 LOC)

**Deliverables:**
- Add `--device` flag to `cortex run` and `cortex pipeline`
- Mode resolution logic

**Files:**
- `src/cortex/commands/run.py` (50 LOC changes)
- `src/cortex/commands/pipeline.py` (50 LOC changes)

**Success Criteria:**
- [ ] `cortex run --device nvidia@192.168.1.123 --kernel car` works end-to-end
- [ ] `cortex pipeline --device nvidia@192.168.1.123` works
- [ ] CLI flags override config

---

### Phase 3: Testing & Polish (1 day)

**Deliverables:**
- Unit tests for deployment logic
- Integration test on real Jetson
- Error message polish
- Documentation

**Files:**
- `tests/deploy/test_ssh_deployer.py` (100 LOC)
- `docs/guides/remote-deployment.md` (100 LOC)

**Success Criteria:**
- [ ] All unit tests pass
- [ ] Manual Jetson validation successful
- [ ] Clear error messages for common failures
- [ ] User guide complete

---

## 6. API Reference

### 6.1 Core Functions

#### `ephemeral_deploy()`

```python
def ephemeral_deploy(
    user: str,
    host: str,
    verbose: bool = False
) -> Tuple[bool, Optional[int]]:
    """
    Deploy code, build, and start adapter on remote device.

    Args:
        user: SSH username (e.g., "nvidia")
        host: IP or hostname (e.g., "192.168.1.123" or "jetson.local")
        verbose: Stream build output

    Returns:
        (success: bool, adapter_pid: Optional[int])

    Flow:
        1. rsync code to ~/cortex-temp/
        2. ssh "cd ~/cortex-temp && make clean && make all"
        3. ssh "nohup .../cortex_adapter_native tcp://:9000 & echo $!"
        4. wait for port 9000 ready (timeout 30s)
        5. return (True, pid) or (False, None)

    Files on device after success:
        ~/cortex-temp/                   # Code
        /tmp/cortex-adapter.pid          # PID file
        /tmp/cortex-adapter.log          # Logs
    """
```

#### `cleanup_deployment()`

```python
def cleanup_deployment(
    user: str,
    host: str
) -> bool:
    """
    Stop adapter and delete all CORTEX files from device.

    Args:
        user: SSH username
        host: IP or hostname

    Returns:
        True if cleanup successful

    Commands:
        ssh "kill $(cat /tmp/cortex-adapter.pid) 2>/dev/null || true"
        ssh "rm -rf ~/cortex-temp /tmp/cortex-adapter.*"
    """
```

---

## 7. File Structure

```
src/cortex/
├── deploy/
│   ├── __init__.py
│   └── ssh_deployer.py         # ephemeral_deploy(), cleanup() (300 LOC)
├── commands/
│   ├── run.py                  # Update: add --device flag (50 LOC)
│   └── pipeline.py             # Update: add --device flag (50 LOC)

tests/
└── deploy/
    └── test_ssh_deployer.py    # Deployment logic tests (100 LOC)

docs/guides/
└── remote-deployment.md        # User guide (100 LOC)
```

**Total:** ~400 LOC

---

## 8. CLI Interface

### 8.1 Updated Commands

#### `cortex run` (add --device flag)

```bash
cortex run [OPTIONS]

Options:
  --kernel TEXT       Run specific kernel
  --all               Run all kernels
  --config PATH       Config file path
  --device TEXT       Remote device (user@host)
  --transport TEXT    Transport URI (manual mode)
  --duration INT      Override duration
  --repeats INT       Override repeats
  --warmup INT        Override warmup
  --verbose           Show detailed output
  --help              Show help

Examples:
  # Local execution (default):
  cortex run --kernel car

  # Remote auto-deploy:
  cortex run --device nvidia@192.168.1.123 --kernel car
  cortex run --device nvidia@jetson.local --kernel car

  # Manual transport:
  cortex run --transport tcp://192.168.1.123:9000 --kernel car
```

**Priority:** `--device` > `--transport` > default (local)

#### `cortex pipeline` (add --device flag)

```bash
cortex pipeline [OPTIONS]

Run full pipeline: build → validate → run → analyze

Options:
  --device TEXT       Remote device (run all kernels on remote)
  --transport TEXT    Transport URI (manual mode)
  --skip-build        Skip build step
  --skip-validate     Skip validation
  --duration INT      Override duration
  --repeats INT       Override repeats
  --warmup INT        Override warmup
  --verbose           Show detailed output
  --help              Show help

Examples:
  # Local pipeline:
  cortex pipeline

  # Remote pipeline (auto-deploy once, run all kernels, cleanup):
  cortex pipeline --device nvidia@192.168.1.123

  # Manual transport:
  cortex pipeline --transport tcp://192.168.1.123:9000
```

**Special behavior for pipeline:**
- Deploys ONCE at start
- Runs ALL kernels sequentially
- Cleans up ONCE at end
- Faster than running kernels individually

---

## 9. Error Handling

### 9.1 Error Scenarios

**1. Invalid --device format:**
```
Error: Invalid device format: '192.168.1.123'

Expected format: user@host

Examples:
  cortex run --device nvidia@192.168.1.123 --kernel car
  cortex run --device pi@raspberrypi.local --kernel car
  cortex run --device ubuntu@server.example.com --kernel car
```

**2. SSH connection failed:**
```
Error: SSH connection failed to nvidia@192.168.1.123

Possible causes:
  - Device is offline (check: ping 192.168.1.123)
  - SSH server not running (on device: sudo systemctl start ssh)
  - Wrong credentials (test: ssh nvidia@192.168.1.123)
  - Passwordless SSH not set up (run: ssh-copy-id nvidia@192.168.1.123)

Troubleshooting:
  ssh -v nvidia@192.168.1.123
```

**3. Build failed on device:**
```
Error: Build failed on remote device

Last 20 lines of build output:
  gcc: error: foo.c: No such file or directory
  make: *** [Makefile:42: foo.o] Error 1

Possible causes:
  - Missing source files (check rsync completed)
  - Build tools not installed (on device: sudo apt install build-essential)

Debug:
  ssh nvidia@192.168.1.123 "cd ~/cortex-temp && make clean && make all V=1"
```

**4. Adapter failed to start:**
```
Error: Adapter failed to start on remote device

Port 9000 not responding after 30 seconds.

Troubleshooting:
  # Check adapter logs:
  ssh nvidia@192.168.1.123 "cat /tmp/cortex-adapter.log"

  # Check if port in use:
  ssh nvidia@192.168.1.123 "lsof -i :9000"

  # Try running adapter manually:
  ssh nvidia@192.168.1.123 "cd ~/cortex-temp && ./primitives/adapters/.../cortex_adapter_native tcp://:9000"
```

---

## 10. Testing Strategy

### 10.1 Unit Tests (~100 LOC)

```python
# tests/deploy/test_ssh_deployer.py
def test_ephemeral_deploy_success(mocker):
    """Test successful deployment flow."""
    mock_ssh = mocker.patch('subprocess.run')
    mock_ssh.return_value.returncode = 0

    success, pid = ephemeral_deploy('nvidia', '192.168.1.123')
    assert success is True
    assert pid is not None

def test_ephemeral_deploy_build_failure(mocker):
    """Test build failure handling."""
    mock_ssh = mocker.patch('subprocess.run')
    mock_ssh.return_value.returncode = 1  # Build failed

    success, pid = ephemeral_deploy('nvidia', '192.168.1.123')
    assert success is False

def test_cleanup_deployment(mocker):
    """Test cleanup removes all files."""
    mock_ssh = mocker.patch('subprocess.run')
    mock_ssh.return_value.returncode = 0

    result = cleanup_deployment('nvidia', '192.168.1.123')
    assert result is True
```

### 10.2 Integration Test (Manual)

```bash
# Manual validation on real Jetson:
pytest tests/integration/test_jetson_deploy.py -v

# Test flow:
# 1. cortex run --device nvidia@192.168.1.123 --kernel noop
# 2. Verify: results generated, device clean after
```

---

## 11. Timeline & Milestones

**Total:** 4 days (1 week)

### Days 1-2: Core Implementation

**Phase 1:** SSH Deployment
- rsync code deployment
- Remote build orchestration
- Adapter lifecycle (start/stop)
- Cleanup logic

**Milestone:** Can deploy to Jetson, run benchmark, cleanup

### Day 3: Integration

**Phase 2:** CLI Integration
- Add `--device` flag to `run` and `pipeline`
- Mode resolution logic
- Error handling

**Milestone:** `cortex run --device nvidia@jetson` works

### Day 4: Testing & Polish

**Phase 3:** Testing & Documentation
- Unit tests
- Manual Jetson validation
- Error message polish
- User documentation

**Milestone:** Feature-complete, tested, documented

---

## 12. Success Criteria

### 12.1 Must-Have

**Functional:**
- [ ] `cortex run --device nvidia@192.168.1.123 --kernel car` works end-to-end
- [ ] `cortex pipeline --device nvidia@192.168.1.123` runs all kernels remotely
- [ ] Device is clean after benchmark (no files left)
- [ ] Rebuild happens every run (ephemeral)
- [ ] Works with IP addresses, hostnames, and DNS names

**Error Handling:**
- [ ] Invalid format shows helpful error
- [ ] SSH failure shows actionable instructions
- [ ] Build failure shows last 20 lines of output
- [ ] All errors include troubleshooting steps

**Testing:**
- [ ] Unit tests pass (SSH deployment)
- [ ] Manual Jetson validation successful

**Documentation:**
- [ ] User guide complete (`docs/guides/remote-deployment.md`)
- [ ] Troubleshooting guide included

### 12.2 Acceptance Test

**First-time user workflow:**

```bash
# 1. Find device IP
ping jetson-nano.local
# 192.168.1.123

# 2. Set up passwordless SSH
ssh-copy-id nvidia@192.168.1.123

# 3. Run benchmark
cortex run --device nvidia@192.168.1.123 --kernel car

# Expected output:
# [1/5] Connecting to nvidia@192.168.1.123...
# [2/5] Deploying code... ✓ (152 files, 2.3 MB in 4.8s)
# [3/5] Building on device... ✓ (58.2s)
# [4/5] Starting adapter... ✓ (PID 4579, port ready)
# [5/5] Running benchmark... ✓ (180 windows, 90.5s)
# [6/6] Cleaning up device... ✓
#
# Results: results/run-2026-01-06-001/kernel-data/car/
# Device returned to clean state.

# 4. Verify device is clean
ssh nvidia@192.168.1.123 "ls ~/cortex-temp"
# ls: cannot access '~/cortex-temp': No such file or directory
# ✓ Clean!
```

---

## Appendix A: Full Flow Example

**Scenario:** User runs `cortex pipeline --device nvidia@192.168.1.123`

### Step-by-Step Execution

```
[User Command]
  cortex pipeline --device nvidia@192.168.1.123

[1. Mode Resolution]
  --device flag present → AutoDeployMode
  Parse: user=nvidia, host=192.168.1.123

[2. Deployment]
  rsync ~/Projects/CORTEX/ → nvidia@192.168.1.123:~/cortex-temp/
    Exclude: .git, results, *.o, *.dylib, *.so
    Time: ~5 seconds

  ssh nvidia@192.168.1.123 "cd ~/cortex-temp && make clean && make all"
    Build harness: ✓
    Build adapters: ✓
    Build kernels: ✓ (6 kernels)
    Time: ~60 seconds

  ssh nvidia@192.168.1.123 "nohup ~/cortex-temp/.../cortex_adapter_native tcp://:9000 &"
    Capture PID: 4579
    Save: /tmp/cortex-adapter.pid

  Wait for port ready: nc -z 192.168.1.123 9000
    Retry every 1s, timeout 30s
    Success after ~2 seconds

[3. Run Pipeline]
  For each kernel in [car, notch_iir, bandpass_fir, goertzel, welch_psd, noop]:
    cortex run --transport tcp://192.168.1.123:9000 --kernel <kernel>
    Results → results/run-*/kernel-data/<kernel>/

  Total benchmark time: ~6 × 5s = 30s (with short duration)

[4. Cleanup]
  ssh nvidia@192.168.1.123 "kill 4579"
    Adapter process stopped

  ssh nvidia@192.168.1.123 "rm -rf ~/cortex-temp /tmp/cortex-adapter.*"
    All files deleted

[5. Complete]
  Total time: 5s + 60s + 2s + 30s + 1s = 98s
  Device state: Clean (no CORTEX files)
  Results: results/run-2026-01-06-001/ (6 kernels)
```

---

## Appendix B: Manual Jetson Deployment

**Reference for understanding what auto-deploy automates.**

### Prerequisites

- Jetson on WiFi (same network as Mac)
- SSH server running: `sudo systemctl start ssh`
- Build tools installed: `sudo apt install build-essential`
- Passwordless SSH: `ssh-copy-id nvidia@192.168.1.123`

### Manual Steps

**1. Deploy code:**
```bash
rsync -av --exclude='.git' --exclude='results' --exclude='*.o' \
    --exclude='*.dylib' --exclude='*.so' --exclude='__pycache__' \
    . nvidia@192.168.1.123:~/cortex-temp/
```

**2. Build on device:**
```bash
ssh nvidia@192.168.1.123 "cd ~/cortex-temp && make clean && make all"
```

**3. Start adapter:**
```bash
ssh nvidia@192.168.1.123 \
  "nohup ~/cortex-temp/primitives/adapters/v1/native/cortex_adapter_native tcp://:9000 \
  > /tmp/cortex-adapter.log 2>&1 & echo \$! > /tmp/cortex-adapter.pid"
```

**4. Run benchmark:**
```bash
cortex run --transport tcp://192.168.1.123:9000 --kernel car
```

**5. Cleanup:**
```bash
ssh nvidia@192.168.1.123 "kill \$(cat /tmp/cortex-adapter.pid)"
ssh nvidia@192.168.1.123 "rm -rf ~/cortex-temp /tmp/cortex-adapter.*"
```

**This entire process is automated by `cortex run --device nvidia@192.168.1.123`.**

---

**End of Specification**
