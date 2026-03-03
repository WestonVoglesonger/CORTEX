"""
SSHDeployer - Deploy via SSH to remote Linux devices.

Targets: Jetson, Raspberry Pi, Linux SBCs, cloud VMs
Strategy: rsync → remote build → start adapter daemon
"""

import shlex
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
        # Validate port ranges
        if not (1 <= ssh_port <= 65535):
            raise ValueError(f"SSH port must be 1-65535, got {ssh_port}")
        if not (1 <= adapter_port <= 65535):
            raise ValueError(f"Adapter port must be 1-65535, got {adapter_port}")

        self.user = user
        self.host = host
        self.ssh_port = ssh_port
        self.adapter_port = adapter_port
        self.remote_dir = "$HOME/cortex-temp"  # Use $HOME instead of ~ for shell expansion in quoted contexts
        self.adapter_pid: Optional[int] = None

    def _ssh_cmd(self, command: str) -> list[str]:
        """Build SSH command with custom port and keepalives."""
        return [
            "ssh",
            "-p", str(self.ssh_port),
            "-o", "ServerAliveInterval=60",
            "-o", "ServerAliveCountMax=10",
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

    def _inhibit_sleep(self, verbose: bool = False) -> None:
        """
        Prevent device from sleeping during benchmark.

        Masks sleep targets via sudo -n. Requires NOPASSWD sudoers
        (installed by `cortex setup-device`). Non-fatal on failure.
        """
        mask_result = self._run_ssh(
            "sudo -n systemctl mask sleep.target suspend.target hibernate.target 2>/dev/null",
            check=False
        )
        if mask_result.returncode == 0:
            self._sleep_inhibit_method = "mask"
            if verbose:
                print("  ✓ Masked sleep/suspend/hibernate targets")
            return

        self._sleep_inhibit_method = None
        if verbose:
            print(
                "  ⚠️  Could not inhibit sleep (sudo failed)\n"
                "      Device may sleep during long benchmarks.\n"
                f"      Fix: cortex setup-device {self.user}@{self.host}"
            )

    def _configure_governor(self, governor: str = "performance", verbose: bool = False) -> None:
        """
        Set CPU frequency governor on device.

        Reads current governor, sets to target if different.
        Non-fatal: warns if sudo fails (benchmark continues with current governor).
        """
        # Read current governor
        result = self._run_ssh(
            "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null",
            check=False
        )
        if result.returncode != 0:
            if verbose:
                print("  ⚠️  Could not read CPU governor (cpufreq not available)")
            return

        current = result.stdout.strip()
        if current == governor:
            if verbose:
                print(f"  ✓ CPU governor already set to {governor}")
            return

        # Store original for cleanup
        self._original_governor = current

        if verbose:
            print(f"  CPU governor: {current} → {governor}...")

        # Set governor on all CPUs
        set_result = self._run_ssh(
            f"echo {governor} | sudo -n tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor >/dev/null",
            check=False
        )
        if set_result.returncode == 0:
            # Verify and report new frequency
            freq_result = self._run_ssh(
                "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null",
                check=False
            )
            freq_str = ""
            if freq_result.returncode == 0:
                freq_khz = int(freq_result.stdout.strip())
                freq_str = f" ({freq_khz // 1000} MHz)"
            if verbose:
                print(f"  ✓ CPU governor set to {governor}{freq_str}")
        else:
            if verbose:
                print(
                    f"  ⚠️  Could not set governor to {governor} (sudo failed)\n"
                    f"      Benchmark will run with {current} governor.\n"
                    f"      Fix: cortex setup-device {self.user}@{self.host}"
                )

    def _configure_pmu_access(self, verbose: bool = False) -> None:
        """
        Ensure perf_event_paranoid allows unprivileged PMU access.

        Checks kernel.perf_event_paranoid and sets it to -1 via sudo if needed.
        Non-fatal: warns if sudo fails (PMU counters just won't be available).
        """
        result = self._run_ssh("cat /proc/sys/kernel/perf_event_paranoid", check=False)
        if result.returncode != 0:
            if verbose:
                print("  ⚠️  Could not read perf_event_paranoid (PMU may not work)")
            return

        current = result.stdout.strip()
        if current == "-1":
            if verbose:
                print(f"  ✓ perf_event_paranoid={current} (PMU access OK)")
            return

        if verbose:
            print(f"  perf_event_paranoid={current}, setting to -1 for PMU access...")

        set_result = self._run_ssh(
            "sudo -n sysctl -w kernel.perf_event_paranoid=-1", check=False
        )
        if set_result.returncode == 0:
            if verbose:
                print("  ✓ PMU access configured (perf_event_paranoid=-1)")
        else:
            if verbose:
                print(
                    f"  ⚠️  Could not set perf_event_paranoid (sudo failed)\n"
                    f"      PMU counters may not be available.\n"
                    f"      Fix: cortex setup-device {self.user}@{self.host}"
                )

    def deploy(self, verbose: bool = False, skip_validation: bool = False,
               governor: str = "performance") -> DeploymentResult:
        """
        Deploy via SSH: rsync → build → validate → start adapter.

        Steps:
            0. Check passwordless SSH configured
            1. Check build tools
            2. Configure device (PMU, governor, sleep inhibit)
            3. rsync code to ~/cortex-temp/
            4. ssh "make clean && make all"
            5. Validation (optional, device-side with graceful fallback)
            6. ssh "nohup .../cortex_adapter_native tcp://:9000 &"

        Args:
            verbose: Stream build/validation output to console
            skip_validation: Skip device-side validation (faster, trust local validation)
            governor: CPU frequency governor to set on device (default: "performance")

        Returns:
            DeploymentResult with transport_uri and metadata

        Raises:
            DeploymentError: If rsync, build, or validation fails
        """
        # Step 0: Pre-flight check - Verify passwordless SSH
        if verbose:
            print(f"[1/6] Checking SSH configuration...")
        self._check_passwordless_ssh()

        # Step 1: Check build tools
        if verbose:
            print(f"[1/6] Checking build tools on {self.host}...")
        self._check_build_tools()

        # Step 1.5: Configure device (governor, PMU, sleep)
        if verbose:
            print(f"[2/6] Configuring device (governor, PMU, sleep inhibit)...")
        self._configure_governor(governor=governor, verbose=verbose)
        self._configure_pmu_access(verbose=verbose)
        self._inhibit_sleep(verbose=verbose)

        # Step 3: rsync code
        if verbose:
            print(f"[3/6] Deploying code to {self.host}...")

        local_dir = os.getcwd()
        rsync_cmd = [
            "rsync",
            "-av" if verbose else "-a",
            "--exclude=.git",
            "--exclude=results",
            "--exclude=venv",
            "--exclude=.venv",
            "--exclude=my_venv",
            "--exclude=node_modules",
            "--exclude=docs",
            "--exclude=paper",
            "--exclude=*.o",
            "--exclude=*.dylib",
            "--exclude=*.so",
            "--exclude=__pycache__",
            "--exclude=.pytest_cache",
            "--exclude=.claude",
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

        # Step 4: Build on device
        if verbose:
            print(f"[4/6] Building on device...")

        # Don't quote remote_dir - it needs shell expansion and is not user input
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

        # Step 5: Validation (optional, device-side)
        validation_status = "skipped"
        self._validation_output = None  # Initialize
        if not skip_validation:
            if verbose:
                print(f"[5/6] Validating kernels...")

            # Check if Python/SciPy available
            python_check = self._run_ssh("which python3 && python3 -c 'import scipy'", check=False)

            if python_check.returncode == 0:
                # Python available, run validation
                # Use PYTHONPATH to make cortex module importable from rsync'd source
                # Don't quote remote_dir - it needs shell expansion and is not user input
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

        # Step 6: Start adapter
        if verbose:
            print(f"[6/6] Starting adapter...")

        # Launch adapter as a fully detached daemon. The SSH channel may hang if the
        # backgrounded process inherits any file descriptors from the pty, so we:
        #   1. Use setsid to create a new session (detach from controlling terminal)
        #   2. Redirect all standard fds away from the SSH channel
        #   3. Use a timeout on the SSH call in case it still hangs
        #   4. Read the PID file separately if the start command times out
        # Don't quote remote_dir - it needs shell expansion and is not user input
        adapter_bin = "./primitives/adapters/v1/native/cortex_adapter_native"
        adapter_args = f"tcp://:{shlex.quote(str(self.adapter_port))}"

        adapter_exec = f"{adapter_bin} {adapter_args}"

        start_cmd = (
            f"cd {self.remote_dir} && "
            f"setsid {adapter_exec} "
            f"</dev/null >/tmp/cortex-adapter.log 2>&1 & "
            f"echo $! > /tmp/cortex-adapter.pid && cat /tmp/cortex-adapter.pid"
        )

        try:
            cmd = self._ssh_cmd(start_cmd)
            result = subprocess.run(
                cmd, check=True, capture_output=True, text=True, timeout=10
            )
            self.adapter_pid = int(result.stdout.strip())
        except subprocess.TimeoutExpired:
            # SSH hung (common with backgrounded daemons) — read PID file instead
            if verbose:
                print("  (SSH channel slow to close, reading PID file...)")
            try:
                pid_result = self._run_ssh("cat /tmp/cortex-adapter.pid", check=False)
                self.adapter_pid = int(pid_result.stdout.strip())
            except (subprocess.CalledProcessError, ValueError):
                raise DeploymentError(
                    f"Adapter start timed out and PID file not found on {self.host}\n"
                    f"Check adapter log:\n"
                    f"  ssh -p {self.ssh_port} {self.user}@{self.host} cat /tmp/cortex-adapter.log"
                )
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

            # Step 1: Check if adapter bound to port (remote-side)
            check = self._run_ssh(f"lsof -i :{shlex.quote(str(self.adapter_port))}", check=False)
            if check.returncode != 0:
                continue  # Not bound yet, retry

            # Step 2: Verify connectivity from host machine
            import socket
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect((self.host, self.adapter_port))
                sock.close()
                ready = True
                break
            except (socket.timeout, socket.error, OSError):
                # Port not reachable yet (firewall, adapter not accepting, etc.)
                continue

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
                    header = "[... truncated to last 10MB ...]\n"
                    content = header + content[-(MAX_LOG_SIZE - len(header)):]

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
                    header = "[... truncated to last 10MB ...]\n"
                    content = header + content[-(MAX_LOG_SIZE - len(header)):]

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
                    header = "[... truncated to last 10MB ...]\n"
                    content = header + content[-(MAX_LOG_SIZE - len(header)):]

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
                self._run_ssh(f"pkill -TERM -P {shlex.quote(str(pid))} 2>/dev/null || true", check=False)
                self._run_ssh(f"kill -TERM {shlex.quote(str(pid))} 2>/dev/null || true", check=False)
                time.sleep(5)  # Wait for graceful shutdown

                # Step 3: SIGKILL if still running
                self._run_ssh(f"pkill -KILL -P {shlex.quote(str(pid))} 2>/dev/null || true", check=False)
                self._run_ssh(f"kill -KILL {shlex.quote(str(pid))} 2>/dev/null || true", check=False)
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

        # Step 6: Restore original governor if we changed it
        original_gov = getattr(self, '_original_governor', None)
        if original_gov:
            try:
                self._run_ssh(
                    f"echo {original_gov} | sudo -n tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor >/dev/null",
                    check=False
                )
            except Exception as e:
                errors.append(f"Failed to restore governor to {original_gov}: {e}")

        # Step 7: Restore sleep targets if we masked them
        if getattr(self, '_sleep_inhibit_method', None) == "mask":
            try:
                self._run_ssh(
                    "sudo -n systemctl unmask sleep.target suspend.target hibernate.target 2>/dev/null",
                    check=False
                )
            except Exception as e:
                errors.append(f"Failed to unmask sleep targets: {e}")

        # Step 7: Cleanup files (only after killing processes)
        try:
            # Don't quote remote_dir - it needs shell expansion and is not user input
            self._run_ssh(f"rm -rf {self.remote_dir} /tmp/cortex-adapter.*", check=False)
        except Exception as e:
            errors.append(f"Failed to cleanup files: {e}")

        return CleanupResult(
            success=len(errors) == 0,
            errors=errors
        )
