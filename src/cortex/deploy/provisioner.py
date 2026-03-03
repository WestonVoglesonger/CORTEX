"""
DeviceProvisioner - One-time device setup for automated benchmarking.

Installs sudoers rules, logind config, and sysctl settings so that
`cortex run --device user@host` works without interactive prompts.

Usage:
    cortex setup-device nvidia@jetson.local
    cortex setup-device nvidia@jetson.local --verify
"""

import getpass
import subprocess


class DeviceProvisioner:
    """Provisions a remote Linux device for passwordless CORTEX benchmarking."""

    def __init__(self, user: str, host: str, ssh_port: int = 22):
        self.user = user
        self.host = host
        self.ssh_port = ssh_port

    def _ssh_run(self, command: str, input_data: str | None = None,
                 check: bool = True) -> subprocess.CompletedProcess:
        cmd = [
            "ssh", "-p", str(self.ssh_port),
            "-o", "BatchMode=yes",
            f"{self.user}@{self.host}",
            command,
        ]
        return subprocess.run(
            cmd, check=check, capture_output=True, text=True,
            input=input_data,
        )

    def _detect_privilege_tier(self) -> str:
        """Detect how we can get root on the device.

        Returns 'nopasswd_sudo', 'root_ssh', or 'password_needed'.
        """
        # Tier 1: NOPASSWD sudo (common on JetPack)
        result = self._ssh_run("sudo -n true", check=False)
        if result.returncode == 0:
            return "nopasswd_sudo"

        # Tier 2: root SSH
        root_cmd = [
            "ssh", "-p", str(self.ssh_port),
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            f"root@{self.host}",
            "true",
        ]
        result = subprocess.run(root_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return "root_ssh"

        return "password_needed"

    def _provisioning_script(self) -> str:
        """Generate idempotent provisioning script."""
        # Unquoted heredoc (SUDOERS not 'SUDOERS') so bash expands $variables.
        # The glob * in cpu*/cpufreq must be escaped to survive expansion.
        return f"""#!/bin/bash
set -euo pipefail
USER="{self.user}"
TEE=$(command -v tee)
SYSTEMCTL=$(command -v systemctl)
SYSCTL=$(command -v sysctl)

# 1. Sudoers (validated before install)
cat > /tmp/cortex-sudoers << SUDOERS
$USER ALL=(root) NOPASSWD: $TEE /sys/devices/system/cpu/cpu\\*/cpufreq/scaling_governor
$USER ALL=(root) NOPASSWD: $SYSTEMCTL mask sleep.target suspend.target hibernate.target
$USER ALL=(root) NOPASSWD: $SYSTEMCTL unmask sleep.target suspend.target hibernate.target
$USER ALL=(root) NOPASSWD: $SYSCTL -w kernel.perf_event_paranoid=-1
SUDOERS
visudo -cf /tmp/cortex-sudoers
mv /tmp/cortex-sudoers /etc/sudoers.d/cortex
chmod 0440 /etc/sudoers.d/cortex

# 2. logind (disable idle sleep)
mkdir -p /etc/systemd/logind.conf.d
cat > /etc/systemd/logind.conf.d/cortex.conf << 'LOGIND'
[Login]
IdleAction=ignore
HandleLidSwitch=ignore
LOGIND

# 3. sysctl (PMU access)
mkdir -p /etc/sysctl.d
cat > /etc/sysctl.d/99-cortex.conf << 'SYSCTL'
kernel.perf_event_paranoid = -1
SYSCTL
$SYSCTL -p /etc/sysctl.d/99-cortex.conf 2>/dev/null || true
$SYSTEMCTL restart systemd-logind 2>/dev/null || true
echo "CORTEX_PROVISION_OK"
"""

    def provision(self, verbose: bool = False) -> bool:
        """Provision the device. Returns True on success."""
        tier = self._detect_privilege_tier()
        if verbose:
            print(f"  Privilege tier: {tier}")

        script = self._provisioning_script()

        if tier == "nopasswd_sudo":
            result = self._ssh_run(
                "sudo bash -s", input_data=script, check=False
            )
        elif tier == "root_ssh":
            cmd = [
                "ssh", "-p", str(self.ssh_port),
                "-o", "BatchMode=yes",
                f"root@{self.host}",
                "bash -s",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, input=script
            )
        else:
            password = getpass.getpass(
                f"[sudo] password for {self.user}@{self.host}: "
            )
            # Feed password on first stdin line, script on remaining lines
            stdin_data = password + "\n" + script
            # Need interactive sudo -S, so disable BatchMode
            cmd = [
                "ssh", "-p", str(self.ssh_port),
                f"{self.user}@{self.host}",
                "sudo -S bash -s",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, input=stdin_data
            )

        output = (result.stdout or "") + (result.stderr or "")
        if verbose:
            print(output)

        if "CORTEX_PROVISION_OK" in result.stdout:
            return True

        if verbose:
            print(f"  Provisioning failed (exit {result.returncode})")
        return False

    def verify(self) -> bool:
        """Check if device is already provisioned."""
        checks = [
            "test -f /etc/sudoers.d/cortex",
            "test -f /etc/systemd/logind.conf.d/cortex.conf",
            "test -f /etc/sysctl.d/99-cortex.conf",
        ]
        for check in checks:
            result = self._ssh_run(check, check=False)
            if result.returncode != 0:
                return False
        return True
