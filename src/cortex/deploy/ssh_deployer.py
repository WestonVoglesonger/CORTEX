"""
SSHDeployer - Deploy via SSH to remote Linux devices.

Targets: Jetson, Raspberry Pi, Linux SBCs, cloud VMs
Strategy: rsync → remote build → start adapter daemon
"""

import subprocess
import time
import os
from typing import Optional

from .base import DeploymentResult, CleanupResult
from .exceptions import DeploymentError


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
        ssh_port: int = 22,
        adapter_port: int = 9000
    ):
        """
        Initialize SSH deployer.

        Args:
            user: SSH username (e.g., "nvidia")
            host: IP or hostname (e.g., "192.168.1.123" or "jetson.local")
            ssh_port: SSH port (default: 22)
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
        self.ssh_port = ssh_port
        self.adapter_port = adapter_port
        self.remote_dir = "~/cortex-temp"
        self.adapter_pid: Optional[int] = None

    def _ssh_cmd(self, command: str) -> list[str]:
        """Build SSH command with custom port."""
        return [
            "ssh",
            "-p", str(self.ssh_port),
            f"{self.user}@{self.host}",
            command
        ]

    def _run_ssh(self, command: str, check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
        """Run SSH command and return result."""
        cmd = self._ssh_cmd(command)
        return subprocess.run(cmd, check=check, capture_output=capture_output, text=True)

    def _check_passwordless_ssh(self) -> None:
        """
        Verify passwordless SSH is configured.

        Raises:
            DeploymentError: If passwordless SSH is not set up
        """
        # Test SSH without password authentication
        test_cmd = [
            "ssh",
            "-p", str(self.ssh_port),
            "-o", "PasswordAuthentication=no",
            "-o", "BatchMode=yes",  # Fail immediately if password needed
            "-o", "ConnectTimeout=5",
            f"{self.user}@{self.host}",
            "echo OK"
        ]

        result = subprocess.run(test_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise DeploymentError(
                f"❌ Passwordless SSH not configured for {self.user}@{self.host}\n\n"
                f"Auto-deploy requires passwordless SSH authentication.\n"
                f"This is a one-time setup that takes 30 seconds.\n\n"
                f"🔧 Setup Instructions:\n\n"
                f"  1. Run this command on your Mac:\n"
                f"     ssh-copy-id {'-p ' + str(self.ssh_port) + ' ' if self.ssh_port != 22 else ''}{self.user}@{self.host}\n\n"
                f"  2. Enter your password when prompted (last time!)\n\n"
                f"  3. Test it worked:\n"
                f"     ssh {'-p ' + str(self.ssh_port) + ' ' if self.ssh_port != 22 else ''}{self.user}@{self.host} \"echo 'Success!'\"\n"
                f"     (should NOT ask for password)\n\n"
                f"  4. Re-run your cortex command\n\n"
                f"📚 Why: SSH keys are more secure than passwords and enable automation.\n"
                f"   Learn more: https://www.ssh.com/academy/ssh/copy-id\n\n"
                f"❓ Troubleshooting:\n"
                f"   - If ssh-copy-id doesn't exist: brew install ssh-copy-id\n"
                f"   - If you don't have an SSH key: ssh-keygen -t rsa -b 4096\n"
                f"   - Manual setup: cat ~/.ssh/id_rsa.pub | ssh {self.user}@{self.host} \"mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys\""
            )

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
        try:
            # Detect OS and architecture
            uname_s = self._run_ssh("uname -s").stdout.strip().lower()
            uname_m = self._run_ssh("uname -m").stdout.strip()
            hostname = self._run_ssh("hostname").stdout.strip()

            # Check for build tools
            build_tools_check = self._run_ssh("which gcc make", check=False)
            build_tools = build_tools_check.returncode == 0

            # Try to get OS version
            os_version = "unknown"
            lsb_result = self._run_ssh("lsb_release -d 2>/dev/null || cat /etc/os-release 2>/dev/null | head -1", check=False)
            if lsb_result.returncode == 0:
                os_version = lsb_result.stdout.strip()

            return {
                "platform": uname_s,
                "arch": uname_m,
                "ssh": True,
                "build_tools": build_tools,
                "hostname": hostname,
                "os_version": os_version
            }
        except subprocess.CalledProcessError as e:
            raise DeploymentError(
                f"Failed to detect capabilities on {self.user}@{self.host}:{self.ssh_port}\n"
                f"Error: {e.stderr if e.stderr else str(e)}\n\n"
                f"Troubleshooting:\n"
                f"  1. Verify SSH access: ssh -p {self.ssh_port} {self.user}@{self.host}\n"
                f"  2. Check network: ping {self.host}\n"
                f"  3. Ensure SSH server running on device"
            )

    def deploy(self, verbose: bool = False, skip_validation: bool = False) -> DeploymentResult:
        """
        Deploy via SSH: rsync → build → validate → start adapter.

        Steps:
            0. Check passwordless SSH configured
            1. rsync code to ~/cortex-temp/
            2. ssh "make clean && make all"
            3. Validation (optional, device-side with graceful fallback)
            4. ssh "nohup .../cortex_adapter_native tcp://:9000 &"
            5. Readiness checks (both remote + host)

        Args:
            verbose: Stream build/validation output to console
            skip_validation: Skip device-side validation (faster, trust local validation)

        Returns:
            DeploymentResult with transport_uri and metadata

        Raises:
            DeploymentError: If rsync, build, or validation fails
        """
        # Step 0: Pre-flight check - Verify passwordless SSH
        if verbose:
            print(f"[0/5] Checking SSH configuration...")
        self._check_passwordless_ssh()

        # Step 1: Detect capabilities
        if verbose:
            print(f"[1/5] Detecting capabilities on {self.host}...")
        capabilities = self.detect_capabilities()

        if not capabilities["build_tools"]:
            raise DeploymentError(
                f"Build tools not found on {self.host}\n"
                f"Install required packages:\n"
                f"  sudo apt install build-essential\n"
                f"  # or equivalent for your distro"
            )

        # Step 2: rsync code
        if verbose:
            print(f"[2/5] Deploying code to {self.host}...")

        local_dir = os.getcwd()
        rsync_cmd = [
            "rsync",
            "-av" if verbose else "-a",
            "--exclude=.git",
            "--exclude=results",
            "--exclude=*.o",
            "--exclude=*.dylib",
            "--exclude=*.so",
            "--exclude=__pycache__",
            "--exclude=.pytest_cache",
            f"-e", f"ssh -p {self.ssh_port}",
            f"{local_dir}/",
            f"{self.user}@{self.host}:{self.remote_dir}/"
        ]

        try:
            subprocess.run(rsync_cmd, check=True, capture_output=not verbose)
        except subprocess.CalledProcessError as e:
            raise DeploymentError(
                f"rsync failed to {self.host}\n"
                f"Command: {' '.join(rsync_cmd)}\n"
                f"Error: {e.stderr if hasattr(e, 'stderr') and e.stderr else str(e)}\n\n"
                f"Troubleshooting:\n"
                f"  1. Verify SSH access: ssh -p {self.ssh_port} {self.user}@{self.host}\n"
                f"  2. Check disk space on device: ssh {self.user}@{self.host} df -h\n"
                f"  3. Verify write permissions: ssh {self.user}@{self.host} ls -ld ~"
            )

        # Step 3: Build on device
        if verbose:
            print(f"[3/5] Building on device...")

        build_cmd = f"cd {self.remote_dir} && make clean && make all"
        try:
            result = self._run_ssh(build_cmd, capture_output=not verbose)
            if verbose and result.stdout:
                print(result.stdout)
        except subprocess.CalledProcessError as e:
            error_output = e.stderr if e.stderr else str(e)
            raise DeploymentError(
                f"Build failed on {self.host}\n\n"
                f"Last lines of build output:\n{error_output[-1000:]}\n\n"
                f"Debug:\n"
                f"  ssh -p {self.ssh_port} {self.user}@{self.host} \"cd {self.remote_dir} && make clean && make all V=1\""
            )

        # Step 4: Validation (optional, device-side)
        validation_status = "skipped"
        if not skip_validation:
            if verbose:
                print(f"[4/5] Validating kernels...")

            # Check if Python/SciPy available
            python_check = self._run_ssh("which python3 && python3 -c 'import scipy'", check=False)

            if python_check.returncode == 0:
                # Python available, run validation
                # Use PYTHONPATH to make cortex module importable from rsync'd source
                validate_cmd = f"cd {self.remote_dir} && PYTHONPATH={self.remote_dir}/src python3 -m cortex.commands.validate"
                try:
                    result = self._run_ssh(validate_cmd, capture_output=not verbose)
                    if verbose and result.stdout:
                        print(result.stdout)
                    validation_status = "passed"
                except subprocess.CalledProcessError as e:
                    raise DeploymentError(
                        f"Validation failed on {self.host}\n"
                        f"Output: {e.stderr if e.stderr else e.stdout}\n\n"
                        f"This indicates kernel correctness issues. Fix before benchmarking."
                    )
            else:
                # Python not available, warn but continue
                if verbose:
                    print(f"  ⚠️  Python/SciPy not available on device, skipping validation")
                    print(f"      (Validation should be done on host before deployment)")
                validation_status = "unavailable"

        # Step 5: Start adapter
        if verbose:
            print(f"[5/5] Starting adapter...")

        adapter_path = f"{self.remote_dir}/primitives/adapters/v1/native/cortex_adapter_native"
        start_cmd = (
            f"nohup {adapter_path} tcp://:{self.adapter_port} "
            f"> /tmp/cortex-adapter.log 2>&1 & "
            f"echo $! > /tmp/cortex-adapter.pid && "
            f"cat /tmp/cortex-adapter.pid"
        )

        try:
            result = self._run_ssh(start_cmd)
            self.adapter_pid = int(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as e:
            raise DeploymentError(
                f"Failed to start adapter on {self.host}\n"
                f"Error: {e}\n\n"
                f"Check adapter log:\n"
                f"  ssh -p {self.ssh_port} {self.user}@{self.host} cat /tmp/cortex-adapter.log"
            )

        # Step 6: Wait for adapter ready (dual checks: remote + host)
        if verbose:
            print(f"  Waiting for adapter (PID {self.adapter_pid}) to be ready...")

        ready = False
        for attempt in range(30):  # 30 second timeout
            time.sleep(1)

            # Remote check: adapter bound to port
            remote_check = self._run_ssh(f"lsof -i :{self.adapter_port}", check=False)
            remote_ready = remote_check.returncode == 0

            # Host check: host can connect to adapter
            host_check = subprocess.run(
                ["nc", "-z", self.host, str(self.adapter_port)],
                check=False,
                capture_output=True
            )
            host_ready = host_check.returncode == 0

            if remote_ready and host_ready:
                ready = True
                break
            elif verbose and attempt % 5 == 0:
                print(f"  ... waiting (remote_ready={remote_ready}, host_ready={host_ready})")

        if not ready:
            # Fetch logs for debugging
            log_result = self._run_ssh("tail -40 /tmp/cortex-adapter.log", check=False)
            log_output = log_result.stdout if log_result.returncode == 0 else "(could not fetch log)"

            raise DeploymentError(
                f"Adapter failed to start on {self.host} (timeout after 30s)\n\n"
                f"Remote adapter log (last 40 lines):\n{log_output}\n\n"
                f"Troubleshooting:\n"
                f"  # Check if port in use:\n"
                f"  ssh -p {self.ssh_port} {self.user}@{self.host} \"lsof -i :{self.adapter_port}\"\n\n"
                f"  # Kill conflicting process:\n"
                f"  ssh -p {self.ssh_port} {self.user}@{self.host} \"kill $(lsof -t -i :{self.adapter_port})\"\n\n"
                f"  # Check firewall:\n"
                f"  ssh -p {self.ssh_port} {self.user}@{self.host} \"sudo iptables -L\""
            )

        if verbose:
            print(f"  ✓ Adapter ready at tcp://{self.host}:{self.adapter_port}")

        return DeploymentResult(
            success=True,
            transport_uri=f"tcp://{self.host}:{self.adapter_port}",
            adapter_pid=self.adapter_pid,
            metadata={
                **capabilities,
                "validation": validation_status
            }
        )

    def cleanup(self) -> CleanupResult:
        """
        Stop adapter and delete files.

        Shutdown sequence (robust):
            1. SIGTERM: ssh "kill $(cat /tmp/cortex-adapter.pid)"
               Wait 5 seconds for graceful shutdown

            2. SIGKILL: ssh "kill -9 $(cat /tmp/cortex-adapter.pid)"
               Force kill if SIGTERM failed

            3. Cleanup files: ssh "rm -rf ~/cortex-temp /tmp/cortex-adapter.*"

        Returns:
            CleanupResult(success=True, errors=[])

        Note:
            Never raises exceptions. All errors captured in result.errors.
        """
        errors = []

        try:
            # Step 1: SIGTERM (graceful shutdown)
            self._run_ssh(f"kill $(cat /tmp/cortex-adapter.pid) 2>/dev/null || true", check=False)
            time.sleep(5)  # Wait for graceful shutdown

            # Step 2: SIGKILL (force kill if still running)
            self._run_ssh(f"kill -9 $(cat /tmp/cortex-adapter.pid) 2>/dev/null || true", check=False)

        except Exception as e:
            errors.append(f"Failed to stop adapter: {e}")

        try:
            # Step 3: Cleanup files
            self._run_ssh(f"rm -rf {self.remote_dir} /tmp/cortex-adapter.*", check=False)
        except Exception as e:
            errors.append(f"Failed to cleanup files: {e}")

        return CleanupResult(
            success=len(errors) == 0,
            errors=errors
        )
