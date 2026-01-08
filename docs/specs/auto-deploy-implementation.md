# Auto-Deploy Device Adapters: Implementation Specification

**Version:** 3.1
**Date:** January 8, 2026
**Status:** Ready for Implementation
**Estimated Effort:** 425 LOC, 4.5 days

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

### 1.3 What Changed from v2.0 → v3.0

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

### 1.3.1 What Changed from v3.0 → v3.1

**ADDED (Protocol-based architecture):**
- ✅ `Deployer` Protocol interface for extensibility
- ✅ `DeployerFactory` for device string parsing
- ✅ Type-safe `DeploymentResult` and `CleanupResult` dataclasses
- ✅ Explicit separation: deployment strategy vs transport layer

**WHY:** Multiple device types planned (Jetson, STM32, RPi, FPGA). Protocol enables adding new deployers without modifying CLI or orchestration code. Cost: +125 LOC (+42%). Benefit: 10× extensibility.

**Implementation impact:**
- Functions → Classes (SSHDeployer implements Deployer protocol)
- Add `base.py` (protocol definition), `factory.py` (device parsing)
- Same CLI interface, same user experience
- +0.5 days timeline (protocol abstraction overhead)

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
| **Total LOC** | 425 |
| Protocol layer (base.py, factory.py) | 150 |
| SSH implementation (ssh_deployer.py) | 175 |
| CLI integration | 100 |
| **Timeline** | 4.5 days |
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
┌──────────────────────────────────────────────────────────────┐
│                 cortex run / cortex pipeline                  │
│                              │                                │
│                              ▼                                │
│                     parse_device_arg()                        │
│                              │                                │
│          ┌───────────────────┼──────────────────┐            │
│          ▼                   ▼                  ▼            │
│     --device           --transport         (default)         │
│     user@host           tcp://uri           local            │
│          │                   │                  │            │
│          ▼                   │                  │            │
│  ┌───────────────────┐       │                  │            │
│  │ DeployerFactory   │       │                  │            │
│  │ .from_device(str) │       │                  │            │
│  └────────┬──────────┘       │                  │            │
│           │                  │                  │            │
│           ▼                  │                  │            │
│  ┌───────────────────┐       │                  ▼            │
│  │ Deployer Protocol │       │        spawn_local_adapter()  │
│  │  - deploy()       │       │                               │
│  │  - cleanup()      │       │                               │
│  └────────┬──────────┘       │                               │
│           │                  │                               │
│           ▼                  │                               │
│  ┌───────────────────┐       │                               │
│  │ SSHDeployer       │       │                               │
│  │  - rsync          │       │                               │
│  │  - remote build   │       │                               │
│  │  - start adapter  │       │                               │
│  │  - wait for port  │───────┘                               │
│  └────────┬──────────┘       │                               │
│           │                  │                               │
│           │ DeploymentResult │                               │
│           │ (transport_uri)  │                               │
│           └──────────────────┼───────────────┐               │
│                              ▼                               │
│                     execute_benchmark()                      │
│                    (via transport_uri)                       │
│                              │                               │
│          ┌───────────────────┴──────────────┐                │
│          ▼                                  ▼                │
│     --device mode                      other modes           │
│     deployer.cleanup()                 (no cleanup)          │
│     (stop adapter, rm files)                                 │
└──────────────────────────────────────────────────────────────┘

Future extensibility:
  DeployerFactory detects device type:
    user@host     → SSHDeployer (implemented)
    stm32:serial  → JTAGDeployer (future)
    docker:image  → DockerDeployer (future)
```

### 3.2 Execution Flow: `cortex run --device nvidia@192.168.1.123 --kernel car`

```
1. Parse arguments
   ├─ --device nvidia@192.168.1.123
   ├─ Parse device string → user=nvidia, host=192.168.1.123

2. Create deployer (via factory)
   ├─ DeployerFactory.from_device_string("nvidia@192.168.1.123")
   │  ├─ Detect format: user@host → SSH deployment
   │  └─ Returns: SSHDeployer(user="nvidia", host="192.168.1.123")

3. Deploy (ephemeral)
   ├─ deployer.detect_capabilities()
   │  └─ Returns: {platform: "linux", arch: "arm64", ssh: True}
   │
   ├─ deployer.deploy(verbose=False)
   │  ├─ rsync code: ~/CORTEX/ → nvidia@192.168.1.123:~/cortex-temp/
   │  │  └─ Exclude: .git, results, *.o, *.dylib, *.so
   │  │
   │  ├─ Remote build: ssh "cd ~/cortex-temp && make clean && make all"
   │  │  └─ Stream output if verbose=True
   │  │
   │  ├─ Start adapter: ssh "nohup .../cortex_adapter_native tcp://:9000 &"
   │  │  ├─ Capture PID: echo $! > /tmp/cortex-adapter.pid
   │  │  └─ Wait for port: nc -z 192.168.1.123 9000 (retry 30s)
   │  │
   │  └─ Returns: DeploymentResult(
   │        success=True,
   │        transport_uri="tcp://192.168.1.123:9000",
   │        adapter_pid=4579,
   │        metadata={"platform": "linux", "arch": "arm64"}
   │      )

4. Run benchmark
   ├─ Use: deployment_result.transport_uri
   ├─ Execute kernel: car (via tcp://192.168.1.123:9000)
   └─ Save results: results/run-*/kernel-data/car/telemetry.ndjson

5. Cleanup
   ├─ deployer.cleanup()
   │  ├─ Stop adapter: ssh "kill $(cat /tmp/cortex-adapter.pid)"
   │  ├─ Delete files: ssh "rm -rf ~/cortex-temp /tmp/cortex-adapter.*"
   │  └─ Returns: CleanupResult(success=True, errors=[])

6. Done
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

### 4.2.1 Deployment Strategies

**The Deployer protocol enables different deployment strategies based on device capabilities:**

#### SSHDeployer (Initial Implementation)

**Target devices:** Jetson, Raspberry Pi, Linux SBCs, cloud VMs
**Device string format:** `user@host`
**Requirements:** SSH server, build tools (gcc, make)
**Deployment method:**
- Copy source via rsync
- Build on device (`make all`)
- Start adapter as daemon (nohup)

**Pros:**
- ✅ Device compiles for its own architecture (no cross-compile)
- ✅ Works over network (WiFi, Ethernet, internet)
- ✅ Standard SSH tooling (no custom protocols)

**Cons:**
- ❌ Requires build tools on device (~500 MB)
- ❌ Rebuild overhead every run (~60s)

#### JTAGDeployer (Future: STM32, Bare Metal)

**Target devices:** STM32, ESP32, bare metal ARM
**Device string format:** `stm32:serial` or `stm32:/dev/ttyUSB0`
**Requirements:** Cross-compiler on host, JTAG/SWD programmer
**Deployment method:**
- Cross-compile on host (arm-none-eabi-gcc)
- Flash firmware via OpenOCD/st-flash
- No build on device (pre-compiled binary)

**Pros:**
- ✅ Works on resource-constrained devices (no compiler needed)
- ✅ Deterministic binary (host-compiled)

**Cons:**
- ❌ Requires cross-compilation toolchain setup
- ❌ Flashing slower than network deployment

#### DockerDeployer (Future: Containers)

**Target devices:** Docker-enabled hosts
**Device string format:** `docker:image-name`
**Deployment method:**
- Build container locally (`docker build`)
- Push to registry / copy via docker save
- Run adapter in container

**Pros:**
- ✅ Isolated environment
- ✅ Reproducible builds

#### PersistentDeployer (Future: Fast Iteration)

**Target devices:** Any (caches adapter between runs)
**Deployment method:**
- Deploy once, reuse adapter across benchmarks
- Only rebuild if source changed (checksum)

**Pros:**
- ✅ Eliminates rebuild overhead (0s vs 60s)

**Cons:**
- ❌ Requires state tracking (breaks ephemeral principle)

**Why Protocol Matters:** Adding JTAGDeployer or DockerDeployer requires **0 changes** to CLI or orchestration code. Just implement the `Deployer` interface and add detection logic to `DeployerFactory`.

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

### Phase 1: Deployment Framework (2.5 days, 325 LOC)

**Deliverables:**
- Protocol layer (abstract interface)
- Factory pattern (device string parsing)
- SSH deployment implementation

**Files:**
- `src/cortex/deploy/base.py` (100 LOC)
- `src/cortex/deploy/factory.py` (50 LOC)
- `src/cortex/deploy/ssh_deployer.py` (175 LOC)

**Key classes:**
```python
# base.py
class Deployer(Protocol):
    def detect_capabilities(self) -> dict: ...
    def deploy(self, verbose: bool) -> DeploymentResult: ...
    def cleanup(self) -> CleanupResult: ...

@dataclass
class DeploymentResult:
    success: bool
    transport_uri: str
    adapter_pid: Optional[int]
    metadata: dict

# factory.py
class DeployerFactory:
    @staticmethod
    def from_device_string(device: str) -> Deployer:
        """Parse device string, return appropriate deployer."""

# ssh_deployer.py
class SSHDeployer:
    def __init__(self, user: str, host: str): ...
    def deploy(self, verbose: bool) -> DeploymentResult:
        """rsync + build + start adapter"""
    def cleanup(self) -> CleanupResult:
        """kill adapter + rm files"""
```

**Success Criteria:**
- [ ] Protocol interface documented with type hints
- [ ] Factory can parse `user@host` format
- [ ] SSHDeployer can rsync code to remote device
- [ ] SSHDeployer can build remotely via `make all`
- [ ] SSHDeployer can start adapter as background daemon
- [ ] SSHDeployer can stop adapter and cleanup files
- [ ] Returns type-safe DeploymentResult and CleanupResult

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

### 6.0 Deployer Protocol (Core Interface)

**The `Deployer` protocol defines the contract all deployment strategies must implement.**

#### Protocol Definition

```python
from typing import Protocol, Optional
from dataclasses import dataclass

@dataclass
class DeploymentResult:
    """Result of successful deployment."""
    success: bool
    transport_uri: str           # e.g., "tcp://192.168.1.123:9000"
    adapter_pid: Optional[int]   # Remote PID (None if not applicable)
    metadata: dict[str, any]     # Platform info, build time, etc.

@dataclass
class CleanupResult:
    """Result of cleanup operation."""
    success: bool
    errors: list[str]            # Any non-fatal issues encountered

class Deployer(Protocol):
    """
    Interface for device deployment strategies.

    All deployers must implement these methods to integrate with
    cortex run/pipeline commands.
    """

    def detect_capabilities(self) -> dict[str, any]:
        """
        Detect device platform, architecture, and available tools.

        Returns:
            Dictionary with device metadata:
            {
                "platform": "linux" | "stm32" | "docker",
                "arch": "arm64" | "x86_64" | "cortex-m4",
                "ssh": bool,  # SSH available
                "build_tools": bool,  # gcc/make available
                ...
            }

        Raises:
            DeploymentError: If device unreachable or detection fails
        """
        ...

    def deploy(self, verbose: bool = False) -> DeploymentResult:
        """
        Deploy code, build (if needed), start adapter.

        Args:
            verbose: Stream build output to user

        Returns:
            DeploymentResult with transport_uri and metadata

        Raises:
            DeploymentError: If deployment fails at any step

        Postconditions:
            - Adapter is running and listening on transport_uri
            - Device has all necessary files to run benchmarks
            - Cleanup must be called after benchmarking
        """
        ...

    def cleanup(self) -> CleanupResult:
        """
        Stop adapter and remove all deployment artifacts.

        Returns:
            CleanupResult indicating success/failure

        Postconditions:
            - Adapter process stopped
            - All deployment files removed
            - Device returned to pre-deployment state

        Note:
            Must not raise exceptions (errors go in CleanupResult.errors)
        """
        ...
```

#### DeployerFactory

```python
class DeployerFactory:
    """Factory for creating deployers from device strings."""

    @staticmethod
    def from_device_string(device: str) -> Deployer:
        """
        Parse device string and return appropriate deployer.

        Args:
            device: Device connection string

        Returns:
            Deployer instance for the device type

        Supported formats:
            user@host         → SSHDeployer
            stm32:serial      → JTAGDeployer (future)
            docker:image      → DockerDeployer (future)

        Raises:
            ValueError: If format not recognized

        Example:
            deployer = DeployerFactory.from_device_string("nvidia@192.168.1.123")
            result = deployer.deploy()
            # ... run benchmark ...
            deployer.cleanup()
        """
        if '@' in device:
            user, host = device.split('@')
            return SSHDeployer(user, host)
        elif device.startswith('stm32:'):
            raise NotImplementedError("JTAGDeployer not yet implemented")
        elif device.startswith('docker:'):
            raise NotImplementedError("DockerDeployer not yet implemented")
        else:
            raise ValueError(f"Unsupported device format: {device}")
```

---

### 6.1 SSHDeployer (Initial Implementation)

**SSHDeployer implements the Deployer protocol for SSH-accessible devices.**

#### Class Definition

```python
class SSHDeployer:
    """
    Deploys via SSH: rsync → remote build → start adapter.

    Target devices: Jetson, Raspberry Pi, Linux SBCs, cloud VMs
    Requirements: SSH server, build tools (gcc, make)
    """

    def __init__(
        self,
        user: str,
        host: str,
        port: int = 22,
        adapter_port: int = 9000
    ):
        """
        Initialize SSH deployer.

        Args:
            user: SSH username (e.g., "nvidia")
            host: IP or hostname (e.g., "192.168.1.123" or "jetson.local")
            port: SSH port (default: 22)
            adapter_port: Port for adapter to listen on (default: 9000)
        """
        self.user = user
        self.host = host
        self.port = port
        self.adapter_port = adapter_port

    def detect_capabilities(self) -> dict[str, any]:
        """
        Detect device platform via SSH.

        Commands run:
            uname -s          # OS (Linux/Darwin)
            uname -m          # Architecture (arm64/x86_64)
            which gcc make    # Build tools available

        Returns:
            {
                "platform": "linux",
                "arch": "arm64",
                "ssh": True,
                "build_tools": True,
                "hostname": "jetson-nano",
                "os_version": "Ubuntu 20.04"
            }
        """
        ...

    def deploy(self, verbose: bool = False) -> DeploymentResult:
        """
        Deploy via SSH.

        Steps:
            1. rsync code to ~/cortex-temp/
               - Exclude: .git, results, *.o, *.dylib, *.so, __pycache__
            2. ssh "cd ~/cortex-temp && make clean && make all"
               - Stream output if verbose=True
            3. ssh "nohup .../cortex_adapter_native tcp://:9000 &"
               - Capture PID: echo $! > /tmp/cortex-adapter.pid
            4. Wait for port: nc -z host 9000 (retry 30s timeout)

        Returns:
            DeploymentResult(
                success=True,
                transport_uri=f"tcp://{self.host}:{self.adapter_port}",
                adapter_pid=<remote PID>,
                metadata=<capabilities dict>
            )

        Files on device after deployment:
            ~/cortex-temp/                   # Source code
            /tmp/cortex-adapter.pid          # PID file
            /tmp/cortex-adapter.log          # Adapter logs

        Raises:
            DeploymentError: If any step fails
        """
        ...

    def cleanup(self) -> CleanupResult:
        """
        Stop adapter and delete files.

        Commands:
            ssh "kill $(cat /tmp/cortex-adapter.pid) 2>/dev/null || true"
            ssh "rm -rf ~/cortex-temp /tmp/cortex-adapter.*"

        Returns:
            CleanupResult(success=True, errors=[])

        Note:
            Never raises exceptions. All errors captured in result.errors.
        """
        ...
```

---

### 6.2 Legacy Functions (Deprecated)

**The following functions are deprecated in favor of the Deployer protocol:**

#### `ephemeral_deploy()` (DEPRECATED)

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
│   ├── __init__.py             # Export: Deployer, DeployerFactory, DeploymentResult
│   ├── base.py                 # Deployer protocol, result types (100 LOC)
│   ├── factory.py              # DeployerFactory.from_device_string() (50 LOC)
│   ├── ssh_deployer.py         # SSHDeployer class (175 LOC)
│   └── exceptions.py           # DeploymentError, CleanupError (25 LOC)
├── commands/
│   ├── run.py                  # Update: add --device flag (50 LOC)
│   └── pipeline.py             # Update: add --device flag (50 LOC)

tests/
└── deploy/
    ├── test_deployer_protocol.py  # Protocol conformance tests (50 LOC)
    └── test_ssh_deployer.py       # SSHDeployer tests (100 LOC)

docs/guides/
└── remote-deployment.md        # User guide (100 LOC)
```

**Total:** ~600 LOC (implementation: 400, tests: 150, docs: 50)
**Core implementation:** 425 LOC (protocol: 150, SSH: 175, CLI: 100)

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

### 10.1 Unit Tests (~150 LOC)

#### Protocol Conformance Tests

```python
# tests/deploy/test_deployer_protocol.py
def test_ssh_deployer_implements_protocol():
    """Verify SSHDeployer conforms to Deployer protocol."""
    from cortex.deploy.base import Deployer
    from cortex.deploy.ssh_deployer import SSHDeployer

    deployer = SSHDeployer("nvidia", "192.168.1.123")
    assert isinstance(deployer, Deployer)
    assert hasattr(deployer, 'detect_capabilities')
    assert hasattr(deployer, 'deploy')
    assert hasattr(deployer, 'cleanup')

def test_deployment_result_structure():
    """Ensure DeploymentResult has required fields."""
    from cortex.deploy.base import DeploymentResult

    result = DeploymentResult(
        success=True,
        transport_uri="tcp://192.168.1.123:9000",
        adapter_pid=1234,
        metadata={"platform": "linux", "arch": "arm64"}
    )
    assert result.success is True
    assert result.transport_uri.startswith("tcp://")
    assert result.adapter_pid == 1234

def test_deployer_factory_ssh_format():
    """Test factory creates SSHDeployer for user@host format."""
    from cortex.deploy.factory import DeployerFactory
    from cortex.deploy.ssh_deployer import SSHDeployer

    deployer = DeployerFactory.from_device_string("nvidia@192.168.1.123")
    assert isinstance(deployer, SSHDeployer)
    assert deployer.user == "nvidia"
    assert deployer.host == "192.168.1.123"

def test_deployer_factory_invalid_format():
    """Test factory raises on invalid format."""
    from cortex.deploy.factory import DeployerFactory

    with pytest.raises(ValueError):
        DeployerFactory.from_device_string("192.168.1.123")  # Missing user@
```

#### SSHDeployer Tests

```python
# tests/deploy/test_ssh_deployer.py
def test_ssh_deploy_success(mocker):
    """Test successful deployment flow."""
    from cortex.deploy.ssh_deployer import SSHDeployer

    mock_subprocess = mocker.patch('subprocess.run')
    mock_subprocess.return_value.returncode = 0

    deployer = SSHDeployer("nvidia", "192.168.1.123")
    result = deployer.deploy()

    assert result.success is True
    assert result.transport_uri == "tcp://192.168.1.123:9000"
    assert result.adapter_pid is not None

def test_ssh_deploy_build_failure(mocker):
    """Test build failure handling."""
    from cortex.deploy.ssh_deployer import SSHDeployer
    from cortex.deploy.exceptions import DeploymentError

    mock_subprocess = mocker.patch('subprocess.run')
    mock_subprocess.return_value.returncode = 1  # Build failed

    deployer = SSHDeployer("nvidia", "192.168.1.123")
    with pytest.raises(DeploymentError):
        deployer.deploy()

def test_ssh_cleanup_success(mocker):
    """Test cleanup removes all files."""
    from cortex.deploy.ssh_deployer import SSHDeployer

    mock_subprocess = mocker.patch('subprocess.run')
    mock_subprocess.return_value.returncode = 0

    deployer = SSHDeployer("nvidia", "192.168.1.123")
    result = deployer.cleanup()

    assert result.success is True
    assert len(result.errors) == 0
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

**Total:** 4.5 days (1 week)

### Days 1-2.5: Core Implementation

**Phase 1:** Deployment Framework
- Protocol layer (base.py: Deployer interface, result types)
- Factory pattern (factory.py: device string parsing)
- SSH implementation (ssh_deployer.py: rsync + build + start)
- Exception types (exceptions.py: DeploymentError, CleanupError)

**Breakdown:**
- Day 1: Protocol + Factory (150 LOC)
- Days 2-2.5: SSHDeployer implementation (175 LOC)

**Milestone:** Can deploy to Jetson via protocol, run benchmark, cleanup

### Day 3: Integration

**Phase 2:** CLI Integration
- Add `--device` flag to `run` and `pipeline`
- Integrate DeployerFactory for mode resolution
- Error handling and user messaging

**Milestone:** `cortex run --device nvidia@jetson` works end-to-end

### Day 4-4.5: Testing & Polish

**Phase 3:** Testing & Documentation
- Protocol conformance tests (50 LOC)
- SSHDeployer unit tests (100 LOC)
- Manual Jetson validation
- Error message polish
- User documentation

**Milestone:** Feature-complete, tested, documented

**Protocol Overhead:** +0.5 days for abstraction layer (+42% LOC, +12.5% time)
**Benefit:** Future deployers (JTAG, Docker) require 0 CLI changes

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
