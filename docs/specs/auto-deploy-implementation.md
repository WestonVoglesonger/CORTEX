# Auto-Deploy Device Adapters: Implementation Specification

**Version:** 3.5
**Date:** January 8, 2026
**Status:** Ready for Implementation (Production-Hardened)
**Estimated Effort:** 445 LOC, 4.5 days

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

Enable remote benchmarking on external devices with automatic deployment. User provides device connection string, system handles deployment, build, and execution.

**Initial scope (v3.1):** SSH-accessible devices (Jetson, Raspberry Pi, Linux SBCs)
**Planned (Spring 2026):** Serial/JTAG devices (STM32, embedded ARM)

### 1.2 User Experience

```bash
# Remote device (auto-deploy via SSH)
cortex run --device nvidia@192.168.1.123 --kernel car

# Manual connection (adapter already running)
cortex run --device tcp://192.168.1.123:9000 --kernel car

# Local (default)
cortex run --kernel car
```

**That's it. One flag, format determines behavior, zero configuration.**

**How it works:** The `--device` flag accepts multiple formats:
- **Auto-deploy formats** (system handles setup): `user@host`, `stm32:port` (future)
- **Manual formats** (adapter already running): `tcp://host:port`, `serial:///dev/device`, `shm://name`
- Format determines whether deployment happens or system just connects

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
- ✅ `--device` flag for device specification

### 1.3.1 What Changed from v3.0 → v3.1

**ADDED (Protocol-based architecture):**
- ✅ `Deployer` Protocol interface for extensibility
- ✅ `DeployerFactory` for unified device string parsing
- ✅ Type-safe `DeploymentResult` and `CleanupResult` dataclasses
- ✅ Explicit separation: deployment strategy vs transport layer
- ✅ **Unified `--device` flag** (replaces separate `--device` + `--transport`)

**WHY:** Multiple device types planned (SSH: Jetson/RPi, Serial: STM32 in Spring 2026). Protocol enables adding new deployers without modifying CLI or orchestration code. Cost: +125 LOC (+42%). Benefit: 10× extensibility.

**Unified flag rationale:** Format self-documents intent (`user@host` = auto-deploy, `tcp://host:port` = manual connection). Simpler mental model, one concept instead of two, cleaner CLI.

**Implementation impact:**
- Functions → Classes (SSHDeployer implements Deployer protocol)
- Add `base.py` (protocol definition), `factory.py` (device parsing + manual routing)
- Simpler CLI: one flag instead of two
- +0.5 days timeline (protocol abstraction overhead)

### 1.4 Core Principles

**1. Format Determines Behavior**
- Auto-deploy formats: `user@host` (SSH), `stm32:port` (JTAG, future)
- Manual formats: `tcp://host:port`, `serial:///dev/device`, `shm://name`
- User doesn't choose "mode"—format implies intent
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
┌──────────────────────────────────────────────────────────────────┐
│                  cortex run / cortex pipeline                     │
│                               │                                   │
│                               ▼                                   │
│                      --device <string>                            │
│                               │                                   │
│                               ▼                                   │
│                    DeployerFactory.parse()                        │
│         (format detection: @, tcp://, stm32:, etc.)               │
│                               │                                   │
│          ┌────────────────────┼────────────────────┐              │
│          ▼                    ▼                    ▼              │
│    Auto-Deploy          Manual Connect       (default)           │
│    user@host            tcp://host:port       local://           │
│    stm32:port                                                     │
│          │                    │                    │              │
│          ▼                    │                    │              │
│  ┌───────────────────┐        │                    │              │
│  │ Deployer Protocol │        │                    │              │
│  │  - deploy()       │        │                    │              │
│  │  - cleanup()      │        │                    │              │
│  └────────┬──────────┘        │                    │              │
│           │                   │                    │              │
│           ▼                   │                    │              │
│  ┌───────────────────┐        │                    │              │
│  │ SSHDeployer       │        │                    │              │
│  │  - rsync          │        │                    ▼              │
│  │  - remote build   │        │          spawn_local_adapter()   │
│  │  - start adapter  │        │                                   │
│  │  - wait for port  │        │                                   │
│  └────────┬──────────┘        │                                   │
│           │                   │                                   │
│           │ DeploymentResult  │                                   │
│           │ (transport_uri)   │                                   │
│           └───────────────────┼───────────────────┐               │
│                               ▼                                   │
│                      execute_benchmark()                          │
│                     (via transport_uri)                           │
│                               │                                   │
│            ┌──────────────────┴────────────────┐                  │
│            ▼                                   ▼                  │
│      Auto-deploy mode                    Manual/local            │
│      deployer.cleanup()                  (no cleanup)            │
│      (stop adapter, rm files)                                    │
└──────────────────────────────────────────────────────────────────┘

Format-based routing (DeployerFactory):
  user@host          → SSHDeployer (auto-deploy)
  stm32:serial       → JTAGDeployer (auto-deploy, future)
  tcp://host:port    → Manual connection (adapter already running)
  serial:///dev/tty  → Manual connection (adapter already running)
  shm://name         → Manual connection (adapter already running)
  local://           → Local adapter (default)
```

### 3.2 Execution Flow: `cortex run --device nvidia@192.168.1.123 --kernel car`

```
1. Parse arguments
   ├─ --device nvidia@192.168.1.123
   ├─ --kernel car

2. Route based on format (via factory)
   ├─ DeployerFactory.parse("nvidia@192.168.1.123")
   │  ├─ Detect format: contains '@' → SSH auto-deploy
   │  └─ Returns: SSHDeployer(user="nvidia", host="192.168.1.123")
   │
   │  # If format was tcp://192.168.1.123:9000 instead:
   │  #   Detect format: starts with tcp:// → Manual connection
   │  #   Returns: ManualTransport(uri="tcp://192.168.1.123:9000")
   │  #   Skip deployment, go straight to step 4

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

**The `--device` flag accepts multiple formats. Format determines behavior automatically—no mode selection required.**

### 4.1 Format Category A: Auto-Deploy

**When format contains** `@` or starts with deployer prefix (`stm32:`, etc.)

**Behavior:** System handles deployment, build, execution, cleanup

**Examples:**

#### SSH Auto-Deploy (`user@host`)

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

**What happens:**
1. Parse: `user=nvidia, host=192.168.1.123`
2. Deploy: rsync → remote build → start adapter
3. Run: benchmark via tcp://192.168.1.123:9000
4. Cleanup: stop adapter, delete files

**Key properties:**
- ✅ One command, zero setup
- ✅ Ephemeral (fresh build every time)
- ✅ Device clean after run
- ❌ Rebuild overhead (~60s per run)

#### JTAG Auto-Deploy (`stm32:` prefix) - Future

```bash
cortex run --device stm32:/dev/ttyUSB0 --kernel car
# Cross-compile → flash firmware → run benchmark → close port
```

---

### 4.2 Format Category B: Manual Connection

**When format starts with** `tcp://`, `serial://`, `shm://`, or `local://`

**Behavior:** Connect to existing adapter (no deployment, no cleanup)

**Use case:** Fast iteration, debugging, persistent adapter

**Examples:**

```bash
# TCP (adapter already running on remote device)
cortex run --device tcp://192.168.1.123:9000 --kernel car

# Serial (firmware already running on STM32)
cortex run --device serial:///dev/ttyUSB0?baud=115200 --kernel car

# Shared memory (local high-performance IPC)
cortex run --device shm://bench01 --kernel car

# Local (default, socketpair)
cortex run --device local:// --kernel car
cortex run --kernel car  # Same as above (default)
```

**What happens:**
1. Parse transport URI
2. Connect to adapter at specified endpoint
3. Run benchmark
4. **No cleanup** (user manages adapter lifecycle)

**Key properties:**
- ✅ Zero deployment overhead (instant)
- ✅ Fast iteration (no rebuild)
- ✅ Full control over adapter lifecycle
- ❌ Manual setup required
- ❌ State persists between runs

**Setup example (TCP):**
```bash
# One-time setup (on device):
ssh nvidia@192.168.1.123
cd cortex && make all
./primitives/adapters/v1/native/cortex_adapter_native tcp://:9000 &

# Fast iteration (on host):
cortex run --device tcp://192.168.1.123:9000 --kernel car    # Instant
cortex run --device tcp://192.168.1.123:9000 --kernel noop   # Instant
# ... repeat 20 times, saves 20 × 60s = 20 minutes
```

---

### 4.3 Deployment Strategy Reference

**The Deployer protocol enables different deployment strategies. Format determines which deployer is used:**

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

**Key differences from SSH:**
- `DeploymentResult.adapter_pid` will be `None` (firmware always listening, no process)
- `cleanup()` means "close serial port + optionally reset device" (no files to remove)
- Firmware is persistent across reboots (unlike ephemeral SSH deployment)

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

**Design Constraint:** Protocol is designed for SSH → STM32 transition (Spring 2026). Don't over-engineer for speculative use cases (FPGA, cloud functions, etc.) until requirements are concrete. The interface may evolve when building JTAGDeployer—that's expected and healthy.

---

### 4.4 Format Detection Logic

**DeployerFactory uses format patterns to route requests:**

```python
def parse_device_string(device: str) -> Union[Deployer, str]:
    """
    Parse device string, return Deployer (auto-deploy) or transport URI (manual).

    Auto-deploy formats (return Deployer):
        user@host          → SSHDeployer
        stm32:serial       → JTAGDeployer (future)

    Manual formats (return transport URI string):
        tcp://host:port    → "tcp://host:port"
        serial:///dev/tty  → "serial:///dev/tty"
        shm://name         → "shm://name"
        local://           → "local://"

    Default:
        None or empty      → "local://"
    """

    if not device:
        return "local://"  # Default

    if '@' in device:
        # SSH auto-deploy
        user, host = device.split('@', 1)
        return SSHDeployer(user, host)

    if device.startswith('stm32:'):
        # JTAG auto-deploy (future)
        return JTAGDeployer(device)

    if device.startswith(('tcp://', 'serial://', 'shm://', 'local://')):
        # Manual connection (transport URI)
        return device  # Return URI string as-is

    raise ValueError(f"Unknown device format: {device}")
```

**Examples:**
```bash
# Auto-deploy (returns Deployer object)
cortex run --device nvidia@192.168.1.123           # SSHDeployer
cortex run --device stm32:/dev/ttyUSB0             # JTAGDeployer (future)

# Manual connection (returns transport URI string)
cortex run --device tcp://192.168.1.123:9000       # "tcp://192.168.1.123:9000"
cortex run --device serial:///dev/ttyUSB0          # "serial:///dev/ttyUSB0"

# Default
cortex run --kernel car                            # "local://"
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
    def from_device_string(device: str) -> Union[Deployer, str]:
        """Parse device string, return deployer or transport URI."""

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
- Pipeline integration (skip host build/validate when using auto-deploy)

**Files:**
- `src/cortex/commands/run.py` (50 LOC changes)
- `src/cortex/commands/pipeline.py` (50 LOC changes)

**Key Integration Logic:**

```python
# Helper function (shared between run.py and pipeline.py)
def resolve_device_string(args, config) -> str:
    """Resolve device with priority: CLI --device > config > default"""
    if hasattr(args, 'device') and args.device:
        return args.device
    if config and 'device' in config:
        return config['device']
    return "local://"

# pipeline.py (and similar for run.py)
def execute(args):
    # Load config (if using config mode)
    config = load_config(args.config) if args.config else {}

    # Resolve device string with priority chain
    device_string = resolve_device_string(args, config)

    # Parse device string (returns Deployer or transport URI)
    result = DeployerFactory.from_device_string(device_string)

    if isinstance(result, Deployer):
        # Auto-deploy mode: deployer handles build + validation
        print("Remote device mode:")
        print("  → Build: On device (via deployment)")
        print("  → Validate: On device (if Python available)")
        print("  → Benchmark: On device")

        deploy_result = result.deploy(
            verbose=args.verbose,
            skip_validation=args.skip_validate
        )

        try:
            # Skip host build/validate (deployer already did it)
            results_dir = runner.run_all_kernels(
                ..., transport_uri=deploy_result.transport_uri
            )
        finally:
            result.cleanup()

    elif result != "local://":
        # Manual mode: adapter already running, just connect
        print(f"Connecting to existing adapter: {result}")
        results_dir = runner.run_all_kernels(..., transport_uri=result)

    else:
        # Local mode: build + validate + run on host (existing behavior)
        if not args.skip_build:
            smart_build(...)
        if not args.skip_validate:
            validate.execute(...)
        results_dir = runner.run_all_kernels(...)
```

**Success Criteria:**
- [ ] `cortex run --device nvidia@192.168.1.123 --kernel car` works end-to-end
- [ ] `cortex pipeline --device nvidia@192.168.1.123` works (skips host build/validate)
- [ ] `cortex pipeline --device nvidia@192.168.1.123 --skip-validate` skips device validation
- [ ] Device validation gracefully degrades if Python missing
- [ ] Config `device:` field works (priority 2)
- [ ] CLI `--device` overrides config (priority 1)
- [ ] Priority chain fully tested (all 3 levels)

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
from typing import Protocol, Optional, runtime_checkable
from dataclasses import dataclass

@dataclass
class DeploymentResult:
    """Result of successful deployment."""
    success: bool
    transport_uri: str           # e.g., "tcp://192.168.1.123:9000"
    adapter_pid: Optional[int]   # Remote PID (None for embedded/always-on adapters)
    metadata: dict[str, any]     # Platform info, build time, etc.

    # Note: adapter_pid=None is a first-class case for:
    #   - Embedded devices (STM32 firmware always listening)
    #   - Persistent adapters (daemon already running)
    #   - Hardware accelerators (FPGA, no process concept)

@dataclass
class CleanupResult:
    """Result of cleanup operation."""
    success: bool
    errors: list[str]            # Any non-fatal issues encountered

@runtime_checkable
class Deployer(Protocol):
    """
    Interface for device deployment strategies.

    All deployers must implement these methods to integrate with
    cortex run/pipeline commands.

    @runtime_checkable decorator enables isinstance() checks:
        deployer = SSHDeployer(...)
        assert isinstance(deployer, Deployer)  # Works at runtime
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
            - Device no longer responding to protocol messages (if applicable)
            - Resources released (files, processes, ports, etc.)
            - Device in clean state for next deployment

        Note:
            Must not raise exceptions (errors go in CleanupResult.errors)

            What "cleanup" means is deployer-specific:
                - SSH: kill process, rm files
                - Serial: close port, optionally reset device
                - Docker: stop container, remove image (optional)
        """
        ...
```

#### DeployerFactory

```python
from typing import Union

class DeployerFactory:
    """Factory for parsing device strings into deployers or transport URIs."""

    @staticmethod
    def from_device_string(device: str) -> Union[Deployer, str]:
        """
        Parse device string and return deployer (auto-deploy) or transport URI (manual).

        Args:
            device: Device connection string (or None for local default)

        Returns:
            - Deployer instance for auto-deploy formats (user@host, stm32:)
            - Transport URI string for manual formats (tcp://, serial://, etc.)

        Auto-deploy formats (return Deployer):
            user@host              → SSHDeployer(user, host, port=22)
            user@host:2222         → SSHDeployer(user, host, port=2222)
            user@[fe80::1]         → SSHDeployer(user, "fe80::1", port=22)
            user@[fe80::1]:2222    → SSHDeployer(user, "fe80::1", port=2222)
            stm32:serial           → JTAGDeployer(device) [future]

        Manual formats (return transport URI string):
            tcp://host:port   → "tcp://host:port"
            serial:///dev/tty → "serial:///dev/tty?baud=115200"
            shm://name        → "shm://name"
            local://          → "local://"

        Raises:
            ValueError: If format not recognized

        Example (auto-deploy):
            result = DeployerFactory.from_device_string("nvidia@192.168.1.123")
            if isinstance(result, Deployer):
                deploy_result = result.deploy()
                transport_uri = deploy_result.transport_uri
                # ... run benchmark with transport_uri ...
                result.cleanup()

        Example (manual):
            result = DeployerFactory.from_device_string("tcp://192.168.1.123:9000")
            if isinstance(result, str):
                transport_uri = result  # Adapter already running
                # ... run benchmark with transport_uri ...
                # No cleanup needed (adapter is persistent)
        """
        if not device:
            return "local://"  # Default to local adapter

        if '@' in device:
            # Parse SSH format: user@host[:port]
            # Also handle IPv6: user@[fe80::1][:port]
            user, host_part = device.split('@', 1)

            # Check for IPv6 brackets
            if host_part.startswith('['):
                # IPv6: user@[fe80::1] or user@[fe80::1]:2222
                bracket_end = host_part.find(']')
                if bracket_end == -1:
                    raise ValueError(f"Malformed IPv6 address: {device}")
                host = host_part[1:bracket_end]  # Strip brackets
                remainder = host_part[bracket_end+1:]
                port = int(remainder[1:]) if remainder.startswith(':') else 22
            else:
                # IPv4 or hostname: user@host or user@host:port
                if ':' in host_part:
                    host, port_str = host_part.rsplit(':', 1)
                    port = int(port_str)
                else:
                    host = host_part
                    port = 22

            return SSHDeployer(user, host, port=port)

        if device.startswith('stm32:'):
            raise NotImplementedError("JTAGDeployer not yet implemented (Spring 2026)")

        # Manual transport formats - return URI as-is
        if device.startswith(('tcp://', 'serial://', 'shm://', 'local://')):
            return device

        raise ValueError(
            f"Unknown device format: {device}\n"
            f"Expected: user@host | tcp://host:port | serial:///dev/device | "
            f"shm://name | local:// | stm32:device"
        )
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

        Port Collision Handling:
            Fixed adapter_port=9000 will randomly fail if port already in use.
            Two strategies available:

            1. User-specified port:
               SSHDeployer(user, host, adapter_port=9001)
               Caller's responsibility to avoid conflicts

            2. Ephemeral port (future):
               adapter_port=0 → Adapter binds to OS-assigned ephemeral port
               Requires protocol enhancement: adapter reports bound port in HELLO
               Not implemented in v1 (needs HELLO message extension)

            Current implementation: Strategy 1 (user-specified, default 9000)
            Known limitation: May fail if 9000 already bound
            Workaround: Pass explicit adapter_port or kill conflicting process
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

    def deploy(self, verbose: bool = False, skip_validation: bool = False) -> DeploymentResult:
        """
        Deploy via SSH: rsync → build → validate → start adapter.

        Steps:
            1. rsync code to ~/cortex-temp/
               - Exclude: .git, results, *.o, *.dylib, *.so, __pycache__

            2. ssh "cd ~/cortex-temp && make clean && make all"
               - Native build on device
               - Stream output if verbose=True

            3. Validation (optional, device-side):
               If not skip_validation:
                   - Check: ssh "which python3 && python3 -c 'import scipy'"
                   - If available: ssh "cd ~/cortex-temp && cortex validate"
                   - If missing: Print warning, continue
                   - If validation fails: Raise DeploymentError

               Rationale: Full Linux devices (Jetson, RPi) can install Python/SciPy.
                         Device-side validation catches target-specific bugs.
                         Graceful fallback if Python missing (user can validate locally).

            4. ssh "nohup .../cortex_adapter_native tcp://:9000 &"
               - Capture PID: echo $! > /tmp/cortex-adapter.pid

            5. Readiness checks (both remote + host):
               Remote check: ssh "lsof -i :9000" (adapter bound to port)
               Host check: nc -z host 9000 (host can connect to adapter)
               Both must succeed (retry 30s timeout with exponential backoff)

               Why both checks:
                 - Remote only: Doesn't verify network connectivity
                 - Host only: Doesn't detect adapter crash after bind
                 - Both: Full verification that harness can communicate

               Failure modes:
                 - Remote fails: Adapter didn't start (check logs)
                 - Host fails: Firewall/network issue (check route, ping host)

        Args:
            verbose: Stream build/validation output to console
            skip_validation: Skip device-side validation (faster, trust local validation)

        Returns:
            DeploymentResult(
                success=True,
                transport_uri=f"tcp://{self.host}:{self.adapter_port}",
                adapter_pid=<remote PID>,
                metadata={
                    **capabilities,
                    "validation": "passed" | "skipped" | "unavailable"
                }
            )

        Files on device after deployment:
            ~/cortex-temp/                   # Source code + built binaries
            /tmp/cortex-adapter.pid          # PID file
            /tmp/cortex-adapter.log          # Adapter logs

        Raises:
            DeploymentError: If rsync, build, or validation fails
        """
        ...

    def cleanup(self) -> CleanupResult:
        """
        Stop adapter and delete files.

        Shutdown sequence (robust):
            1. SIGTERM: ssh "kill $(cat /tmp/cortex-adapter.pid)"
               Wait 5 seconds for graceful shutdown

            2. SIGKILL: ssh "kill -9 $(cat /tmp/cortex-adapter.pid) 2>/dev/null || true"
               Force kill if SIGTERM failed

            3. Cleanup files: ssh "rm -rf ~/cortex-temp /tmp/cortex-adapter.*"

        Rationale:
            SIGTERM alone is insufficient if adapter is hung or unresponsive.
            SIGKILL ensures process termination (unkillable except by kernel).
            5-second timeout balances graceful shutdown vs user wait time.

        Returns:
            CleanupResult(success=True, errors=[])

        Note:
            Never raises exceptions. All errors captured in result.errors.
        """
        ...
```

---

### 6.2 JTAGDeployer (Future - Spring 2026)

**JTAGDeployer implements deployment for embedded devices (STM32, bare metal ARM).**

**⚠️ DRAFT INTERFACE**: This design is speculative and will likely change during implementation (Spring 2026). Included for architectural completeness, but expect significant revisions based on actual STM32 requirements, OpenOCD limitations, and cross-compilation complexities. Do NOT implement this interface yet—it serves as a placeholder to guide protocol design decisions.

#### Key Differences from SSHDeployer

```python
class JTAGDeployer:
    """
    Deploys via JTAG/SWD: cross-compile → validate → flash firmware.

    Target devices: STM32, embedded ARM Cortex-M
    Requirements: OpenOCD, arm-none-eabi-gcc (host-side)
    """

    def __init__(self, device: str):
        """
        Args:
            device: Serial device path (e.g., "/dev/ttyUSB0", "stm32:/dev/ttyUSB0")
        """
        self.device = device

    def deploy(self, verbose: bool = False, skip_validation: bool = False) -> DeploymentResult:
        """
        Deploy via JTAG: cross-compile → validate → flash.

        Steps:
            1. Cross-compile on host:
               - Use arm-none-eabi-gcc (ARM Cortex-M toolchain)
               - Build for target architecture (e.g., STM32H7)

            2. Validation (REQUIRED on host):
               If not skip_validation:
                   - Run cortex validate (host-side oracle)
                   - MUST pass before flashing
                   - No fallback (Python impossible on embedded device)

               Rationale: Embedded devices lack Python interpreter.
                         Host validation is the ONLY opportunity to verify correctness.
                         Flashing unvalidated code wastes time (flash + test cycle is slow).

            3. Flash firmware via OpenOCD:
               - openocd -f interface/stlink.cfg -f target/stm32h7x.cfg -c "program firmware.elf verify reset exit"

            4. Verify connection:
               - Open serial port (e.g., /dev/ttyUSB0 @ 115200 baud)
               - Wait for HELLO message from adapter firmware

        Args:
            verbose: Stream build/flash output to console
            skip_validation: Skip host validation (NOT RECOMMENDED - no device-side validation possible)

        Returns:
            DeploymentResult(
                success=True,
                transport_uri=f"serial://{self.device}?baud=115200",
                adapter_pid=None,  # Firmware is always listening (no process concept)
                metadata={
                    "platform": "stm32",
                    "arch": "cortex-m7",
                    "validation": "passed" | "skipped"
                }
            )

        Raises:
            DeploymentError: If cross-compile, validation, or flash fails
        """
        ...

    def cleanup(self) -> CleanupResult:
        """
        Cleanup for embedded device.

        Actions:
            - Close serial port
            - Optionally: Reset device via OpenOCD

        Note:
            Firmware is persistent across reboots (no files to delete).
            Unlike SSH, there's no ephemeral state to clean up.
        """
        ...
```

#### Validation Strategy Comparison

| Deployer | Build Location | Validation Location | Fallback if Missing |
|----------|----------------|---------------------|---------------------|
| **SSHDeployer** | Device (native) | Device (preferred) | Warn, continue |
| **JTAGDeployer** | Host (cross-compile) | Host (required) | Fail (no fallback) |

**Why the difference:**
- SSH targets are full Linux (can install Python/SciPy)
- Embedded targets are bare metal (no OS, no Python possible)

---

### 6.3 Legacy Functions (Deprecated)

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

#### `cortex run` (unified --device flag)

```bash
cortex run [OPTIONS]

Options:
  --kernel TEXT       Run specific kernel
  --all               Run all kernels
  --config PATH       Config file path
  --device TEXT       Device connection string (auto-deploy or manual)
  --duration INT      Override duration
  --repeats INT       Override repeats
  --warmup INT        Override warmup
  --skip-validate     Skip oracle validation (faster, trust correctness)
  --verbose           Show detailed output
  --help              Show help

Examples:
  # Local execution (default):
  cortex run --kernel car

  # Auto-deploy formats (system handles setup):
  cortex run --device nvidia@192.168.1.123 --kernel car        # SSH to Jetson
  cortex run --device pi@raspberrypi.local --kernel car        # SSH to RPi
  cortex run --device nvidia@jetson.local --kernel car         # SSH via mDNS

  # Skip validation (faster iteration, trust correctness):
  cortex run --device nvidia@192.168.1.123 --kernel car --skip-validate

  # Manual connection formats (adapter already running):
  cortex run --device tcp://192.168.1.123:9000 --kernel car    # TCP connection
  cortex run --device serial:///dev/ttyUSB0 --kernel car       # Serial/UART
  cortex run --device shm://bench01 --kernel car               # Shared memory
  cortex run --device local:// --kernel car                    # Explicit local

  # Future auto-deploy formats:
  cortex run --device stm32:/dev/ttyUSB0 --kernel car          # JTAG/SWD (Spring 2026)
```

**Format determines behavior:**
- `user@host` → Auto-deploy via SSH (rsync + build + start adapter)
- `tcp://host:port` → Connect to existing adapter (no deployment)
- `serial://`, `shm://`, `local://` → Direct transport connection
- `stm32:device` → Auto-deploy via JTAG/SWD (future)

#### `cortex pipeline` (unified --device flag)

```bash
cortex pipeline [OPTIONS]

Run full pipeline: build → validate → run → analyze

Options:
  --device TEXT       Device connection string (auto-deploy or manual)
  --skip-build        Skip build step
  --skip-validate     Skip validation
  --duration INT      Override duration
  --repeats INT       Override repeats
  --warmup INT        Override warmup
  --verbose           Show detailed output
  --help              Show help

Examples:
  # Local pipeline (default):
  cortex pipeline

  # Remote auto-deploy (deploys once, runs all kernels, cleans up):
  cortex pipeline --device nvidia@192.168.1.123
  cortex pipeline --device pi@raspberrypi.local

  # Manual connection (adapter already running):
  cortex pipeline --device tcp://192.168.1.123:9000

  # Future embedded deployment:
  cortex pipeline --device stm32:/dev/ttyUSB0
```

**Special behavior for pipeline:**
- **Auto-deploy mode**: Deploys ONCE at start → runs ALL kernels → cleans up ONCE at end
- **Manual mode**: Connects to existing adapter → runs ALL kernels (no cleanup)
- Faster than running kernels individually (avoids repeated deployment overhead)

---

### 8.2 Config-Based Device Specification

**Device can be specified in YAML config files for reproducibility.**

#### Config Schema Addition

```yaml
# cortex.yaml (or custom config)
cortex_version: 1

system:
  name: "cortex"
  description: "EEG-first benchmark"

dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  format: "float32"
  channels: 64
  sample_rate_hz: 160

# NEW: Optional device field
# Specifies target device for benchmarking
# CLI --device flag overrides this value
device: "nvidia@192.168.1.123"  # or "tcp://192.168.1.123:9000", etc.

benchmark:
  metrics: [latency, jitter, throughput]
  parameters:
    duration_seconds: 30
    repeats: 3
    warmup_seconds: 5
```

#### Priority Resolution

**Device string is resolved with following priority:**

```
1. CLI --device flag            (highest priority)
2. Config device: field
3. Default "local://"           (lowest priority)
```

**Implementation:**
```python
def resolve_device_string(args, config) -> str:
    """
    Resolve device string with 3-level priority chain.

    Returns:
        Device string for DeployerFactory.from_device_string()
    """
    # Priority 1: CLI --device flag
    if hasattr(args, 'device') and args.device:
        return args.device

    # Priority 2: Config device: field
    if config and 'device' in config:
        return config['device']

    # Priority 3: Default local
    return "local://"
```

#### Usage Examples

**Example 1: Config specifies device**
```yaml
# jetson_config.yaml
device: "nvidia@192.168.1.123"
benchmark:
  duration_seconds: 60
```
```bash
cortex run --config jetson_config.yaml --kernel car
# Auto-deploys to Jetson from config
```

**Example 2: CLI overrides config**
```bash
cortex run --config jetson_config.yaml --device pi@192.168.1.200 --kernel car
# Config says Jetson, CLI overrides to RPi
```

**Example 3: Config with manual connection**
```yaml
# manual_config.yaml
device: "tcp://192.168.1.123:9000"
```
```bash
cortex run --config manual_config.yaml --kernel car
# Connects to existing adapter (no auto-deploy)
```

**Example 4: Priority test (CLI overrides config)**
```yaml
# test_config.yaml
device: "nvidia@jetson"  # Priority 2
```
```bash
cortex run --config test_config.yaml --device pi@raspberrypi --kernel car
# Result: Uses pi@raspberrypi (CLI --device overrides config)
```

---

### 8.3 Debugging Features (Nice-to-Have)

**These features are optional enhancements for troubleshooting deployment issues.**

#### --print-commands Flag

```bash
cortex run --device nvidia@192.168.1.123 --kernel car --print-commands
```

**Behavior:** Print all SSH/rsync commands before executing them, enabling users to:
- Reproduce deployment steps manually
- Debug permission issues
- Understand what automation is doing
- Copy-paste commands for experimentation

**Example output:**
```
[CMD] rsync -av --exclude='.git' --exclude='results' ... nvidia@192.168.1.123:~/cortex-temp/
[CMD] ssh -p 22 nvidia@192.168.1.123 "cd ~/cortex-temp && make clean && make all"
[CMD] ssh -p 22 nvidia@192.168.1.123 "which python3 && python3 -c 'import scipy'"
[CMD] ssh -p 22 nvidia@192.168.1.123 "nohup ~/cortex-temp/.../cortex_adapter_native tcp://:9000 > /tmp/cortex-adapter.log 2>&1 & echo \$! > /tmp/cortex-adapter.pid"
[CMD] nc -z 192.168.1.123 9000
```

**Implementation:** Add `print_commands: bool` parameter to SSHDeployer, log to stderr before subprocess.run()

**Value:** Low implementation cost (~10 LOC), high debugging value for SSH/network issues

#### Remote Log Tail on Failure

**Behavior:** When adapter fails to start, automatically fetch last 40 lines of remote log

**Example:**
```
Error: Adapter failed to start on remote device

Port 9000 not responding after 30 seconds.

Remote adapter log (last 40 lines):
  [2026-01-08 14:32:15] cortex_adapter_native starting...
  [2026-01-08 14:32:15] Binding to tcp://:9000
  [2026-01-08 14:32:15] ERROR: Address already in use (errno 98)
  [2026-01-08 14:32:15] Fatal: Cannot bind to port 9000
  [2026-01-08 14:32:15] Exiting with code 1

Troubleshooting:
  # Check if port in use:
  ssh nvidia@192.168.1.123 "lsof -i :9000"

  # Kill conflicting process:
  ssh nvidia@192.168.1.123 "kill \$(lsof -t -i :9000)"
```

**Implementation:** Add `fetch_logs()` method to SSHDeployer, call on deployment failure

**Value:** Saves manual SSH → cat log round-trip, immediately shows root cause

---

## 9. Error Handling

### 9.1 Error Scenarios

**1. Invalid --device format:**
```
Error: Unknown device format: '192.168.1.123'

Expected formats:
  Auto-deploy:  user@host | stm32:device
  Manual:       tcp://host:port | serial:///dev/device | shm://name | local://

Examples (auto-deploy):
  cortex run --device nvidia@192.168.1.123 --kernel car
  cortex run --device pi@raspberrypi.local --kernel car

Examples (manual):
  cortex run --device tcp://192.168.1.123:9000 --kernel car
  cortex run --device serial:///dev/ttyUSB0 --kernel car
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
- [ ] Config `device:` field works (auto-deploy from config)
- [ ] CLI `--device` overrides config `device:` field
- [ ] Priority resolution: CLI --device > config > local (3 levels)

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
    Execute benchmark via tcp://192.168.1.123:9000
    Results → results/run-*/kernel-data/<kernel>/

  Note: Pipeline runs kernels internally (not via subprocess cortex run)
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
cortex run --device tcp://192.168.1.123:9000 --kernel car
```

**5. Cleanup:**
```bash
ssh nvidia@192.168.1.123 "kill \$(cat /tmp/cortex-adapter.pid)"
ssh nvidia@192.168.1.123 "rm -rf ~/cortex-temp /tmp/cortex-adapter.*"
```

**This entire process is automated by `cortex run --device nvidia@192.168.1.123`.**

---

**End of Specification**
