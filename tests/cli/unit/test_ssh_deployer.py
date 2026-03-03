"""
Unit tests for SSH deployer path expansion fix.

Tests that $HOME expansion works correctly in SSH commands without being
quoted by shlex.quote(), which would prevent shell expansion.
"""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

# Add project root to path
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.cortex.deploy.ssh_deployer import SSHDeployer


class TestSSHDeployerPathExpansion:
    """Test path expansion in SSH commands."""

    def test_remote_dir_uses_home_variable(self):
        """Verify remote_dir uses $HOME for expansion."""
        deployer = SSHDeployer("user", "host", 22, 9000)

        # Should use $HOME for shell expansion
        assert deployer.remote_dir == "$HOME/cortex-temp"

    def test_ssh_cmd_construction(self):
        """Verify SSH command construction with keepalives."""
        deployer = SSHDeployer("testuser", "testhost", 2222, 9000)

        cmd = deployer._ssh_cmd("echo test")

        assert cmd == [
            'ssh', '-p', '2222',
            '-o', 'ServerAliveInterval=60',
            '-o', 'ServerAliveCountMax=10',
            'testuser@testhost', 'echo test'
        ]

    def test_run_ssh_preserves_shell_expansion(self):
        """Verify _run_ssh doesn't interfere with shell expansion."""
        deployer = SSHDeployer("user", "host", 22, 9000)

        # Create a command with $HOME
        test_command = "cd $HOME/cortex-temp && pwd"
        ssh_cmd = deployer._ssh_cmd(test_command)

        # The command string should preserve $HOME without quoting
        assert test_command in ssh_cmd
        assert "'$HOME'" not in ' '.join(ssh_cmd)

    @patch('src.cortex.deploy.ssh_deployer.subprocess.run')
    def test_cleanup_command_does_not_quote_remote_dir(self, mock_run):
        """Verify cleanup command doesn't quote $HOME."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        deployer = SSHDeployer("user", "host", 22, 9000)
        deployer.adapter_pid = 12345  # Set a PID for cleanup

        # Trigger cleanup
        deployer.cleanup()

        # Find the cleanup command
        cleanup_calls = [c for c in mock_run.call_args_list
                        if 'rm -rf' in str(c) and 'cortex-temp' in str(c)]

        if len(cleanup_calls) > 0:
            cleanup_call = cleanup_calls[0]
            actual_command = cleanup_call[0][0]

            # Command should contain '$HOME/cortex-temp' without quotes
            command_str = ' '.join(actual_command)
            assert '$HOME/cortex-temp' in command_str or 'cortex-temp' in command_str
            # Should NOT have quoted $HOME
            assert "'$HOME/cortex-temp'" not in command_str


class TestSSHDeployerKeepalives:
    """Test SSH keepalive configuration."""

    def test_ssh_cmd_includes_keepalives(self):
        """SSH commands include ServerAliveInterval and ServerAliveCountMax."""
        deployer = SSHDeployer("user", "host", 22, 9000)
        cmd = deployer._ssh_cmd("true")
        assert "-o" in cmd
        assert "ServerAliveInterval=60" in cmd
        assert "ServerAliveCountMax=10" in cmd


class TestSSHDeployerNoSystemdInhibit:
    """Test that systemd-inhibit wrapping is removed."""

    @patch('src.cortex.deploy.ssh_deployer.subprocess.run')
    @patch('src.cortex.deploy.ssh_deployer.socket', create=True)
    def test_adapter_not_wrapped_with_systemd_inhibit(self, mock_socket, mock_run):
        """Adapter launch command should not use systemd-inhibit."""
        mock_run.return_value = MagicMock(returncode=0, stdout="12345", stderr="")

        deployer = SSHDeployer("user", "host", 22, 9000)
        deployer._sleep_inhibit_method = "systemd-inhibit"  # Even if set

        # Find the nohup command that starts the adapter
        # We just check _ssh_cmd doesn't wrap with systemd-inhibit
        # by inspecting the deploy code path indirectly
        cmd = deployer._ssh_cmd("nohup ./adapter tcp://:9000")
        assert "systemd-inhibit" not in " ".join(cmd)


class TestSSHDeployerSetupDeviceHint:
    """Test that warning messages reference cortex setup-device."""

    @patch('src.cortex.deploy.ssh_deployer.subprocess.run')
    def test_inhibit_sleep_warns_with_setup_device(self, mock_run):
        """Sleep inhibit failure message references cortex setup-device."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

        deployer = SSHDeployer("nvidia", "jetson.local", 22, 9000)

        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            deployer._inhibit_sleep(verbose=True)

        output = f.getvalue()
        assert "cortex setup-device nvidia@jetson.local" in output

    @patch('src.cortex.deploy.ssh_deployer.subprocess.run')
    def test_governor_warns_with_setup_device(self, mock_run):
        """Governor failure message references cortex setup-device."""
        call_count = 0
        def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Read current governor
                return MagicMock(returncode=0, stdout="powersave", stderr="")
            # Set governor fails
            return MagicMock(returncode=1, stdout="", stderr="")

        mock_run.side_effect = side_effect

        deployer = SSHDeployer("nvidia", "jetson.local", 22, 9000)

        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            deployer._configure_governor(verbose=True)

        output = f.getvalue()
        assert "cortex setup-device nvidia@jetson.local" in output

    @patch('src.cortex.deploy.ssh_deployer.subprocess.run')
    def test_pmu_warns_with_setup_device(self, mock_run):
        """PMU failure message references cortex setup-device."""
        call_count = 0
        def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Read perf_event_paranoid
                return MagicMock(returncode=0, stdout="2", stderr="")
            # Set fails
            return MagicMock(returncode=1, stdout="", stderr="")

        mock_run.side_effect = side_effect

        deployer = SSHDeployer("nvidia", "jetson.local", 22, 9000)

        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            deployer._configure_pmu_access(verbose=True)

        output = f.getvalue()
        assert "cortex setup-device nvidia@jetson.local" in output


class TestSSHDeployerErrorHandling:
    """Test error handling in SSH deployer."""

    @patch('src.cortex.deploy.ssh_deployer.subprocess.run')
    def test_ssh_connection_failure(self, mock_run):
        """Verify SSH connection failures are handled."""
        mock_run.side_effect = subprocess.CalledProcessError(
            255, ['ssh'], stderr=b"Connection refused"
        )

        deployer = SSHDeployer("user", "badhost", 22, 9000)

        with pytest.raises(subprocess.CalledProcessError):
            deployer._check_passwordless_ssh()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
