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

    def _check_build_tools(self) -> None:
        """
        Verify build tools (gcc, make) are available on device.

        Raises:
            DeploymentError: If build tools not found or SSH connection fails
        """
        try:
            result = self._run_ssh("command -v gcc >/dev/null && command -v make >/dev/null", check=False)
            if result.returncode != 0:
                raise DeploymentError(
                    f"Build tools (gcc, make) not found on {self.host}\n"
                    f"Install required packages:\n"
                    f"  sudo apt install build-essential\n"
                    f"  # or equivalent for your distro"
                )
        except subprocess.CalledProcessError as e:
            raise DeploymentError(
                f"Failed to check build tools on {self.user}@{self.host}:{self.ssh_port}\n"
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

        # Step 1: Check build tools
        if verbose:
            print(f"[1/5] Checking build tools on {self.host}...")
        self._check_build_tools()

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

        build_cmd = f"cd {self.remote_dir} && make clean && make build-only"
        try:
            result = self._run_ssh(build_cmd, capture_output=True)  # Always capture for log fetch
            self._build_output = result.stdout  # Store for fetch_logs()
            if verbose and result.stdout:
                print(result.stdout)
        except subprocess.CalledProcessError as e:
            error_output = e.stderr if e.stderr else str(e)
            self._build_output = error_output  # Capture errors too
            raise DeploymentError(
                f"Build failed on {self.host}\n\n"
                f"Last lines of build output:\n{error_output[-1000:]}\n\n"
                f"Debug:\n"
                f"  ssh -p {self.ssh_port} {self.user}@{self.host} \"cd {self.remote_dir} && make clean && make all V=1\""
            )

        # Step 4: Validation (optional, device-side)
        validation_status = "skipped"
        self._validation_output = None  # Initialize
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
                    result = self._run_ssh(validate_cmd, capture_output=True)  # Always capture for log fetch
                    self._validation_output = result.stdout  # Store for fetch_logs()
                    if verbose and result.stdout:
                        print(result.stdout)
                    validation_status = "passed"
                except subprocess.CalledProcessError as e:
                    error_output = e.stderr if e.stderr else e.stdout
                    self._validation_output = error_output  # Capture errors too
                    raise DeploymentError(
                        f"Validation failed on {self.host}\n"
                        f"Output: {error_output}\n\n"
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

        # Start adapter in background with all I/O streams redirected to prevent SSH hanging
        # Critical: Redirect stdin (<), stdout (>), and stderr (2>&1) to close SSH streams
        start_cmd = (
            f"cd {self.remote_dir} && "
            f"nohup ./primitives/adapters/v1/native/cortex_adapter_native tcp://:{self.adapter_port} "
            f"</dev/null >/tmp/cortex-adapter.log 2>&1 & "
            f"echo $! | tee /tmp/cortex-adapter.pid"
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

        # Step 6: Wait for adapter ready
        if verbose:
            print(f"  Waiting for adapter (PID {self.adapter_pid}) to be ready...")

        ready = False
        for attempt in range(5):  # 5 second timeout
            time.sleep(1)

            # Check if adapter bound to port
            check = self._run_ssh(f"lsof -i :{self.adapter_port}", check=False)
            if check.returncode == 0:
                ready = True
                break

        if not ready:
            # Fetch logs for debugging
            log_result = self._run_ssh("tail -40 /tmp/cortex-adapter.log", check=False)
            log_output = log_result.stdout if log_result.returncode == 0 else "(could not fetch log)"

            raise DeploymentError(
                f"Adapter failed to start on {self.host} (timeout after 5s)\n\n"
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
                "validation": validation_status
            }
        )

    def fetch_logs(self, output_dir: str) -> dict[str, any]:
        """
        Fetch deployment logs from remote device and save to output_dir.

        This method MUST be called BEFORE cleanup() to retrieve logs before deletion.

        Args:
            output_dir: Directory to save logs (e.g., results/run-*/deployment/)

        Returns:
            {
                "success": bool,
                "files_fetched": ["adapter.log", "build.log", ...],
                "errors": ["adapter.log: file not found", ...],
                "sizes": {"adapter.log": 2847, "build.log": 15234}
            }

        Side effects:
            Creates output_dir/ if it doesn't exist
            Writes files: adapter.log, build.log, validation.log, metadata.json, README.txt

        Error handling:
            Never raises exceptions (returns errors in result dict)
            Missing files are logged as errors but don't fail the operation
            Large files (>10MB) are truncated with warning
        """
        import os
        import json
        from datetime import datetime

        os.makedirs(output_dir, exist_ok=True)

        files_fetched = []
        errors = []
        sizes = {}
        MAX_LOG_SIZE = 10_000_000  # 10MB

        # 1. Fetch adapter log from remote
        try:
            result = self._run_ssh("cat /tmp/cortex-adapter.log", check=False)
            if result.returncode == 0:
                adapter_log_path = os.path.join(output_dir, "adapter.log")

                # Size limit check (10MB)
                content = result.stdout
                if len(content) > MAX_LOG_SIZE:
                    errors.append("adapter.log: truncated (>10MB)")
                    content = content[-MAX_LOG_SIZE:]  # Keep last 10MB
                    content = "[... truncated to last 10MB ...]\n" + content

                with open(adapter_log_path, 'w') as f:
                    f.write(content)

                files_fetched.append("adapter.log")
                sizes["adapter.log"] = len(content)
            else:
                errors.append(f"adapter.log: {result.stderr}")
        except Exception as e:
            errors.append(f"adapter.log: {str(e)}")

        # 2. Write build output (captured during deploy)
        if hasattr(self, '_build_output') and self._build_output:
            try:
                build_log_path = os.path.join(output_dir, "build.log")
                content = self._build_output

                # Size limit check
                if len(content) > MAX_LOG_SIZE:
                    errors.append("build.log: truncated (>10MB)")
                    content = content[-MAX_LOG_SIZE:]
                    content = "[... truncated to last 10MB ...]\n" + content

                with open(build_log_path, 'w') as f:
                    f.write(content)

                files_fetched.append("build.log")
                sizes["build.log"] = len(content)
            except Exception as e:
                errors.append(f"build.log: {str(e)}")

        # 3. Write validation output (captured during deploy)
        if hasattr(self, '_validation_output') and self._validation_output:
            try:
                validation_log_path = os.path.join(output_dir, "validation.log")
                content = self._validation_output

                # Size limit check
                if len(content) > MAX_LOG_SIZE:
                    errors.append("validation.log: truncated (>10MB)")
                    content = content[-MAX_LOG_SIZE:]
                    content = "[... truncated to last 10MB ...]\n" + content

                with open(validation_log_path, 'w') as f:
                    f.write(content)

                files_fetched.append("validation.log")
                sizes["validation.log"] = len(content)
            except Exception as e:
                errors.append(f"validation.log: {str(e)}")

        # 4. Write metadata.json
        try:
            metadata = {
                "deployment": {
                    "device_string": f"{self.user}@{self.host}",
                    "transport_uri": f"tcp://{self.host}:{self.adapter_port}",
                    "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "adapter_pid": self.adapter_pid,
                    "success": True
                },
                "device": {
                    "hostname": self.host,
                    "ssh_port": self.ssh_port,
                    "adapter_port": self.adapter_port
                },
                "logs": {
                    "adapter_log": "adapter.log" if "adapter.log" in files_fetched else None,
                    "build_log": "build.log" if "build.log" in files_fetched else None,
                    "validation_log": "validation.log" if "validation.log" in files_fetched else None,
                    "adapter_log_size_bytes": sizes.get("adapter.log"),
                    "build_log_size_bytes": sizes.get("build.log"),
                    "validation_log_size_bytes": sizes.get("validation.log"),
                    "fetch_timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "fetch_errors": errors
                }
            }

            metadata_path = os.path.join(output_dir, "metadata.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            files_fetched.append("metadata.json")
        except Exception as e:
            errors.append(f"metadata.json: {str(e)}")

        # 5. Write README.txt
        try:
            readme_path = os.path.join(output_dir, "README.txt")
            readme_content = """# Deployment Logs

This directory contains logs and metadata from remote device deployment.

Files:
  adapter.log     - Adapter stdout/stderr from /tmp/cortex-adapter.log on device
  build.log       - Build output from 'make clean && make all' on device
  validation.log  - Validation output from 'cortex validate' on device
  metadata.json   - Deployment metadata (device info, timestamps, file sizes)

These logs are fetched BEFORE cleanup() deletes remote files.
They are useful for debugging deployment failures and adapter issues.

Note: Logs >10MB are truncated to prevent disk space issues.
"""
            with open(readme_path, 'w') as f:
                f.write(readme_content)

            files_fetched.append("README.txt")
        except Exception as e:
            errors.append(f"README.txt: {str(e)}")

        return {
            "success": len(errors) == 0,
            "files_fetched": files_fetched,
            "errors": errors,
            "sizes": sizes
        }

    def cleanup(self) -> CleanupResult:
        """
        Stop adapter and delete files.

        Shutdown sequence (robust):
            1. Read PID file if it exists
            2. Kill process tree (parent + children) with SIGTERM
               Wait 5 seconds for graceful shutdown
            3. Kill process tree with SIGKILL if still running
            4. Fallback: killall cortex_adapter_* by name
            5. Verify processes are gone
            6. Delete temp files

        Returns:
            CleanupResult(success=True, errors=[])

        Note:
            Never raises exceptions. All errors captured in result.errors.
        """
        errors = []

        # Step 1: Get PID (prefer file, fallback to stored value)
        pid = None
        try:
            result = self._run_ssh("cat /tmp/cortex-adapter.pid 2>/dev/null || echo ''", check=False)
            pid_str = result.stdout.strip()
            if pid_str:
                pid = int(pid_str)
            elif hasattr(self, 'adapter_pid') and self.adapter_pid:
                # Fallback to PID stored during deploy()
                pid = self.adapter_pid
        except (ValueError, subprocess.CalledProcessError):
            # Last resort: use stored PID
            if hasattr(self, 'adapter_pid') and self.adapter_pid:
                pid = self.adapter_pid

        # Step 2: Kill process tree (graceful)
        try:
            if pid:
                # Kill parent + children (handles bash wrapper + actual adapter)
                self._run_ssh(f"pkill -TERM -P {pid} 2>/dev/null || true", check=False)
                self._run_ssh(f"kill -TERM {pid} 2>/dev/null || true", check=False)
                time.sleep(5)  # Wait for graceful shutdown

                # Step 3: SIGKILL if still running
                self._run_ssh(f"pkill -KILL -P {pid} 2>/dev/null || true", check=False)
                self._run_ssh(f"kill -KILL {pid} 2>/dev/null || true", check=False)
                time.sleep(1)

        except Exception as e:
            errors.append(f"Failed to stop adapter via PID: {e}")

        # Step 4: Fallback - kill by exact binary name (handles double-forked daemons)
        try:
            # Use killall with exact binary name (more reliable than pkill pattern matching)
            self._run_ssh("killall -9 cortex_adapter_native 2>/dev/null || true", check=False)
            time.sleep(3)  # Wait for kernel to fully reap processes after SIGKILL
        except Exception as e:
            errors.append(f"Failed to killall adapter: {e}")

        # Step 5: Verify processes are gone
        try:
            # Check for any remaining adapter processes
            result = self._run_ssh("pgrep -f cortex_adapter_native || echo ''", check=False)
            if result.stdout.strip():
                pids = result.stdout.strip()
                errors.append(f"Adapter processes still running after SIGKILL: {pids}")
        except Exception as e:
            errors.append(f"Failed to verify adapter stopped: {e}")

        # Step 6: Cleanup files (only after killing processes)
        try:
            self._run_ssh(f"rm -rf {self.remote_dir} /tmp/cortex-adapter.*", check=False)
        except Exception as e:
            errors.append(f"Failed to cleanup files: {e}")

        return CleanupResult(
            success=len(errors) == 0,
            errors=errors
        )
