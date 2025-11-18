"""Integration tests for check-system command with real dependencies.

CRIT-004 PR #3: These tests use real implementations to verify SystemChecker
end-to-end functionality. Tests actual command execution with production dependencies.
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from cortex.commands.check_system import SystemChecker, execute, SystemCheck
from cortex.core import (
    ConsoleLogger,
    RealFileSystemService,
    SubprocessExecutor,
    SystemEnvironmentProvider,
    SystemToolLocator,
)


class TestSystemCheckerIntegration:
    """Integration tests with real dependencies."""

    def setup_method(self):
        """Set up integration test environment."""
        self.filesystem = RealFileSystemService()
        self.process_executor = SubprocessExecutor()
        self.env_provider = SystemEnvironmentProvider()
        self.tool_locator = SystemToolLocator()
        self.logger = ConsoleLogger()

        self.checker = SystemChecker(
            filesystem=self.filesystem,
            process_executor=self.process_executor,
            env_provider=self.env_provider,
            tool_locator=self.tool_locator,
            logger=self.logger
        )

    def test_run_all_checks_on_current_platform(self):
        """Test that all checks run without crashing on current platform."""
        # Act - Run all checks with real dependencies
        checks, all_pass = self.checker.run_all_checks()

        # Assert - Should return 5 checks (one for each check method)
        assert len(checks) == 5

        # Verify all checks have proper structure
        for check in checks:
            assert isinstance(check, SystemCheck)
            assert check.name in [
                'CPU Governor',
                'Turbo Boost',
                'Thermal State',
                'Background Services',
                'Sleep Prevention'
            ]
            assert check.status in ['pass', 'warn', 'fail']
            assert isinstance(check.message, str)
            assert len(check.message) > 0
            assert isinstance(check.critical, bool)

        # all_pass should be a boolean
        assert isinstance(all_pass, bool)

    def test_platform_specific_checks(self):
        """Test that platform-specific checks work correctly."""
        system_type = self.env_provider.get_system_type()

        # Run individual checks
        cpu_check = self.checker.check_cpu_governor()
        turbo_check = self.checker.check_turbo_boost()
        thermal_check = self.checker.check_thermal_state()
        services_check = self.checker.check_background_services()
        sleep_check = self.checker.check_sleep_prevention()

        # Verify platform-appropriate results
        if system_type == 'Darwin':
            # macOS should pass CPU/turbo checks automatically
            assert cpu_check.status == 'pass'
            assert turbo_check.status == 'pass'
            assert 'macOS' in cpu_check.message
            assert 'macOS' in turbo_check.message

            # macOS should check for caffeinate
            if self.tool_locator.has_tool('caffeinate'):
                assert sleep_check.status == 'pass'
                assert 'caffeinate' in sleep_check.message
            else:
                assert sleep_check.status == 'fail'
                assert sleep_check.critical is True

        elif system_type == 'Linux':
            # Linux should check actual governor files
            assert cpu_check.status in ['pass', 'warn']

            # Linux should check for systemd-inhibit
            if self.tool_locator.has_tool('systemd-inhibit'):
                assert sleep_check.status == 'pass'
            else:
                assert sleep_check.status == 'warn'

        # Both platforms should check background services
        assert services_check.status in ['pass', 'warn']

        # Both platforms should check thermal state
        assert thermal_check.status in ['pass', 'warn']

    def test_execute_function_with_real_args(self):
        """Test the execute() facade function with real arguments."""
        # Create a mock args object (like argparse would create)
        class Args:
            verbose = False

        args = Args()

        # Act - Execute the command (this is what the CLI calls)
        exit_code = execute(args)

        # Assert - Should return 0 or 1
        assert exit_code in [0, 1]

        # If exit code is 1, there should be critical failures
        # If exit code is 0, all critical checks passed

    def test_print_results_produces_output(self, capsys):
        """Test that print_results produces properly formatted output."""
        # Run checks
        checks, all_pass = self.checker.run_all_checks()

        # Act - Print results (captures stdout via pytest fixture)
        self.checker.print_results(checks, verbose=False)

        # Assert - Verify output structure
        captured = capsys.readouterr()
        output = captured.out

        # Should contain header
        assert "SYSTEM CONFIGURATION CHECK" in output
        assert "=" * 80 in output

        # Should contain all check names
        for check in checks:
            assert check.name in output

        # Should contain summary
        assert "Summary:" in output
        assert "passed" in output
        assert "warnings" in output
        assert "failed" in output

        # Should contain status symbols
        assert any(symbol in output for symbol in ['✓', '⚠', '✗'])

    def test_critical_issues_section(self, capsys):
        """Test that critical issues are highlighted in output."""
        # Create a mix of checks including a critical warning
        checks = [
            SystemCheck('Test Pass', 'pass', 'Everything OK'),
            SystemCheck('Test Warn', 'warn', 'Minor issue', critical=False),
            SystemCheck('Test Critical', 'warn', 'Major problem', critical=True),
        ]

        # Act
        self.checker.print_results(checks, verbose=False)

        # Assert
        captured = capsys.readouterr()
        output = captured.out

        # Should have critical issues section
        assert "Critical Issues:" in output
        assert "Test Critical" in output
        assert "Major problem" in output
        assert "[CRITICAL]" in output

        # Should have recommendation
        assert "Recommendation:" in output
        assert "Address critical issues" in output


# Test discovery for pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
