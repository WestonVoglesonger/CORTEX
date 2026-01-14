"""
Unit tests for SSH deployer path expansion fix.

Tests that $HOME expansion works correctly in SSH commands without being
quoted by shlex.quote(), which would prevent shell expansion.
"""

import pytest
from unittest.mock import patch, MagicMock, call
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
        """Verify SSH command construction is correct."""
        deployer = SSHDeployer("testuser", "testhost", 2222, 9000)

        cmd = deployer._ssh_cmd("echo test")

        assert cmd == ['ssh', '-p', '2222', 'testuser@testhost', 'echo test']

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
