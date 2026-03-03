"""Unit tests for DeviceProvisioner."""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.cortex.deploy.provisioner import DeviceProvisioner


class TestPrivilegeTierDetection:
    """Test tiered privilege detection."""

    @patch("src.cortex.deploy.provisioner.subprocess.run")
    def test_tier1_nopasswd_sudo(self, mock_run):
        """NOPASSWD sudo detected when sudo -n true succeeds."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        p = DeviceProvisioner("nvidia", "jetson.local")
        assert p._detect_privilege_tier() == "nopasswd_sudo"

    @patch("src.cortex.deploy.provisioner.subprocess.run")
    def test_tier2_root_ssh(self, mock_run):
        """Root SSH detected when sudo fails but root@host succeeds."""
        def side_effect(cmd, **kwargs):
            # sudo -n true via _ssh_run → fails
            if "sudo -n true" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="")
            # root@host true → succeeds
            if f"root@jetson.local" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        mock_run.side_effect = side_effect
        p = DeviceProvisioner("nvidia", "jetson.local")
        assert p._detect_privilege_tier() == "root_ssh"

    @patch("src.cortex.deploy.provisioner.subprocess.run")
    def test_tier3_password_needed(self, mock_run):
        """Falls back to password_needed when both sudo and root SSH fail."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        p = DeviceProvisioner("nvidia", "jetson.local")
        assert p._detect_privilege_tier() == "password_needed"


class TestProvisioningScript:
    """Test generated provisioning script content."""

    def test_script_uses_command_v(self):
        """Script resolves paths at runtime with command -v."""
        p = DeviceProvisioner("nvidia", "jetson.local")
        script = p._provisioning_script()
        assert "command -v tee" in script
        assert "command -v systemctl" in script
        assert "command -v sysctl" in script

    def test_script_validates_sudoers(self):
        """Script validates sudoers before installing."""
        p = DeviceProvisioner("nvidia", "jetson.local")
        script = p._provisioning_script()
        assert "visudo -cf" in script

    def test_script_emits_ok_marker(self):
        """Script outputs CORTEX_PROVISION_OK on success."""
        p = DeviceProvisioner("nvidia", "jetson.local")
        script = p._provisioning_script()
        assert "CORTEX_PROVISION_OK" in script

    def test_script_has_all_sudoers_commands(self):
        """Sudoers file covers governor, sleep mask/unmask, and PMU."""
        p = DeviceProvisioner("nvidia", "jetson.local")
        script = p._provisioning_script()
        assert "scaling_governor" in script
        assert "mask sleep.target" in script
        assert "unmask sleep.target" in script
        assert "perf_event_paranoid" in script

    def test_script_no_hardcoded_paths(self):
        """No hardcoded /usr/bin paths — all resolved via command -v."""
        p = DeviceProvisioner("nvidia", "jetson.local")
        script = p._provisioning_script()
        # Paths should be variable references, not hardcoded
        assert "/usr/bin/tee" not in script
        assert "/usr/bin/systemctl" not in script
        assert "/usr/sbin/sysctl" not in script

    def test_script_uses_correct_user(self):
        """Script embeds the SSH user for sudoers."""
        p = DeviceProvisioner("myuser", "myhost")
        script = p._provisioning_script()
        assert 'USER="myuser"' in script


class TestVerify:
    """Test provisioning verification."""

    @patch("src.cortex.deploy.provisioner.subprocess.run")
    def test_verify_all_present(self, mock_run):
        """Returns True when all provisioning files exist."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        p = DeviceProvisioner("nvidia", "jetson.local")
        assert p.verify() is True

    @patch("src.cortex.deploy.provisioner.subprocess.run")
    def test_verify_missing_file(self, mock_run):
        """Returns False when any provisioning file is missing."""
        call_count = 0
        def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        mock_run.side_effect = side_effect
        p = DeviceProvisioner("nvidia", "jetson.local")
        assert p.verify() is False


class TestProvision:
    """Test provision execution."""

    @patch("src.cortex.deploy.provisioner.subprocess.run")
    def test_provision_nopasswd_success(self, mock_run):
        """Provisioning succeeds with NOPASSWD sudo."""
        def side_effect(cmd, **kwargs):
            # _detect_privilege_tier: sudo -n true
            if isinstance(cmd, list) and "sudo -n true" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            # provision: sudo bash -s
            if isinstance(cmd, list) and "sudo bash -s" in cmd:
                return MagicMock(returncode=0, stdout="CORTEX_PROVISION_OK", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        p = DeviceProvisioner("nvidia", "jetson.local")
        assert p.provision() is True

    @patch("src.cortex.deploy.provisioner.subprocess.run")
    def test_provision_failure(self, mock_run):
        """Provisioning returns False when script fails."""
        def side_effect(cmd, **kwargs):
            if isinstance(cmd, list) and "sudo -n true" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="error", stderr="")

        mock_run.side_effect = side_effect
        p = DeviceProvisioner("nvidia", "jetson.local")
        assert p.provision() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
