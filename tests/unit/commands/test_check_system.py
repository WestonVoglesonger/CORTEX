"""Unit tests for SystemChecker (check_system command).

CRIT-004 PR #3: Comprehensive tests for cross-platform system checking logic.
Tests use mocked dependencies to verify behavior across Linux/macOS/Windows.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock

from cortex.commands.check_system import SystemChecker, SystemCheck


# Helper factories for creating mock dependencies

def create_mock_filesystem(files=None, dirs=None):
    """Create mock FileSystemService with configured files/directories."""
    fs = Mock()
    files = files or {}
    dirs = dirs or set()

    def mock_exists(path):
        return str(path) in files or str(path) in dirs

    def mock_read_file(path):
        return files.get(str(path), "")

    def mock_glob(directory, pattern):
        # Simple pattern matching for thermal_zone*
        if pattern == 'thermal_zone*':
            return [Path(d) for d in dirs if 'thermal_zone' in d and d.startswith(str(directory))]
        return []

    fs.exists.side_effect = mock_exists
    fs.read_file.side_effect = mock_read_file
    fs.glob.side_effect = mock_glob

    return fs


def create_mock_process(commands=None):
    """Create mock ProcessExecutor with configured command responses."""
    process = Mock()
    commands = commands or {}

    def mock_run(cmd, **kwargs):
        result = Mock()
        cmd_str = ' '.join(cmd)

        # Look up configured response
        for configured_cmd, (returncode, stdout, stderr) in commands.items():
            if configured_cmd in cmd_str:
                result.returncode = returncode
                result.stdout = stdout
                result.stderr = stderr
                return result

        # Default: command not found
        result.returncode = 1
        result.stdout = ""
        result.stderr = "command not found"
        return result

    process.run.side_effect = mock_run
    return process


def create_mock_env(system_type='Linux'):
    """Create mock EnvironmentProvider."""
    env = Mock()
    env.get_system_type.return_value = system_type
    return env


def create_mock_tools(available_tools=None):
    """Create mock ToolLocator."""
    tools = Mock()
    available_tools = available_tools or set()

    def has_tool(name):
        return name in available_tools

    tools.has_tool.side_effect = has_tool
    return tools


def create_mock_logger():
    """Create mock Logger."""
    logger = Mock()
    return logger


class TestSystemCheckerInit:
    """Test SystemChecker initialization."""

    def test_init_stores_dependencies(self):
        """Test that __init__ correctly stores all injected dependencies."""
        fs = create_mock_filesystem()
        process = create_mock_process()
        env = create_mock_env()
        tools = create_mock_tools()
        logger = create_mock_logger()

        checker = SystemChecker(
            filesystem=fs,
            process_executor=process,
            env_provider=env,
            tool_locator=tools,
            logger=logger
        )

        assert checker.fs == fs
        assert checker.process == process
        assert checker.env == env
        assert checker.tools == tools
        assert checker.log == logger


class TestCheckCpuGovernor:
    """Test check_cpu_governor method."""

    def test_linux_performance_governor_passes(self):
        """Linux with performance governor should pass."""
        fs = create_mock_filesystem({
            '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor': 'performance\n'
        })

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_cpu_governor()

        assert result.name == 'CPU Governor'
        assert result.status == 'pass'
        assert 'performance' in result.message
        assert result.critical == False

    def test_linux_powersave_governor_warns(self):
        """Linux with powersave governor should warn."""
        fs = create_mock_filesystem({
            '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor': 'powersave\n'
        })

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_cpu_governor()

        assert result.status == 'warn'
        assert 'powersave' in result.message
        assert 'recommend performance' in result.message

    def test_linux_missing_governor_file_warns(self):
        """Linux with missing governor file should warn."""
        fs = create_mock_filesystem({})  # No files

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_cpu_governor()

        assert result.status == 'warn'
        assert 'cpufreq not available' in result.message

    def test_macos_passes_automatically(self):
        """macOS should pass automatically (no governor control)."""
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_cpu_governor()

        assert result.status == 'pass'
        assert 'macOS' in result.message

    def test_unsupported_platform_warns(self):
        """Unsupported platform should warn."""
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Windows'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_cpu_governor()

        assert result.status == 'warn'
        assert 'Unsupported platform' in result.message


class TestCheckTurboBoost:
    """Test check_turbo_boost method."""

    def test_linux_intel_turbo_disabled_passes(self):
        """Linux with Intel turbo disabled should pass."""
        fs = create_mock_filesystem({
            '/sys/devices/system/cpu/intel_pstate/no_turbo': '1\n'
        })

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_turbo_boost()

        assert result.status == 'pass'
        assert 'Intel Turbo Boost off' in result.message

    def test_linux_intel_turbo_enabled_warns(self):
        """Linux with Intel turbo enabled should warn."""
        fs = create_mock_filesystem({
            '/sys/devices/system/cpu/intel_pstate/no_turbo': '0\n'
        })

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_turbo_boost()

        assert result.status == 'warn'
        assert 'frequency variance' in result.message

    def test_linux_amd_boost_disabled_passes(self):
        """Linux with AMD boost disabled should pass."""
        fs = create_mock_filesystem({
            '/sys/devices/system/cpu/cpufreq/boost': '0\n'
        })

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_turbo_boost()

        assert result.status == 'pass'
        assert 'AMD Turbo Core off' in result.message

    def test_linux_amd_boost_enabled_warns(self):
        """Linux with AMD boost enabled should warn."""
        fs = create_mock_filesystem({
            '/sys/devices/system/cpu/cpufreq/boost': '1\n'
        })

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_turbo_boost()

        assert result.status == 'warn'
        assert 'frequency variance' in result.message

    def test_linux_neither_intel_nor_amd_warns(self):
        """Linux with neither Intel nor AMD interface should warn."""
        fs = create_mock_filesystem({})  # No turbo files

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_turbo_boost()

        assert result.status == 'warn'
        assert 'neither Intel nor AMD' in result.message

    def test_macos_passes_automatically(self):
        """macOS should pass automatically."""
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_turbo_boost()

        assert result.status == 'pass'
        assert 'macOS' in result.message


class TestCheckThermalState:
    """Test check_thermal_state method."""

    def test_macos_no_throttling_passes(self):
        """macOS with no throttling (100% CPU limit) should pass."""
        process = create_mock_process({
            'pmset -g therm': (0, 'CPU_Speed_Limit = 100\n', '')
        })

        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=process,
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_thermal_state()

        assert result.status == 'pass'
        assert 'No thermal throttling' in result.message

    def test_macos_throttling_warns_critical(self):
        """macOS with thermal throttling should warn (critical)."""
        process = create_mock_process({
            'pmset -g therm': (0, 'CPU_Speed_Limit = 75\n', '')
        })

        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=process,
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_thermal_state()

        assert result.status == 'warn'
        assert result.critical == True
        assert 'Thermal throttling detected' in result.message

    def test_macos_pmset_no_cpu_limit_passes(self):
        """macOS pmset with no CPU limit info should pass."""
        process = create_mock_process({
            'pmset -g therm': (0, 'No thermal issues\n', '')
        })

        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=process,
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_thermal_state()

        assert result.status == 'pass'
        assert 'No thermal issues' in result.message

    def test_linux_normal_temp_passes(self):
        """Linux with normal temperature should pass."""
        fs = create_mock_filesystem(
            files={
                '/sys/class/thermal/thermal_zone0/temp': '50000\n',  # 50°C
                '/sys/class/thermal/thermal_zone1/temp': '60000\n',  # 60°C
            },
            dirs={
                '/sys/class/thermal',
                '/sys/class/thermal/thermal_zone0',
                '/sys/class/thermal/thermal_zone1'
            }
        )

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_thermal_state()

        assert result.status == 'pass'
        assert '60.0°C' in result.message

    def test_linux_high_temp_warns_critical(self):
        """Linux with high temperature (>80°C) should warn (critical)."""
        fs = create_mock_filesystem(
            files={
                '/sys/class/thermal/thermal_zone0/temp': '85000\n',  # 85°C
            },
            dirs={
                '/sys/class/thermal',
                '/sys/class/thermal/thermal_zone0'
            }
        )

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_thermal_state()

        assert result.status == 'warn'
        assert result.critical == True
        assert '85.0°C' in result.message
        assert 'let system cool down' in result.message

    def test_linux_no_thermal_zones_warns(self):
        """Linux with no thermal zones should warn."""
        fs = create_mock_filesystem({})  # No thermal directory

        checker = SystemChecker(
            filesystem=fs,
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_thermal_state()

        assert result.status == 'warn'
        assert 'Unable to detect thermal sensors' in result.message


class TestCheckBackgroundServices:
    """Test check_background_services method."""

    def test_unix_no_heavy_processes_passes(self):
        """Unix with no heavy processes should pass."""
        process = create_mock_process({
            'ps aux': (0, 'USER  PID  CMD\nuser  123  bash\nuser  456  python cortex\n', '')
        })

        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=process,
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_background_services()

        assert result.status == 'pass'
        assert 'No heavy background processes' in result.message

    def test_unix_heavy_processes_warns(self):
        """Unix with heavy processes should warn."""
        # Simulate multiple docker processes
        ps_output = 'USER  PID  CMD\n'
        for i in range(5):
            ps_output += f'user  {i}  docker run\n'

        process = create_mock_process({
            'ps aux': (0, ps_output, '')
        })

        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=process,
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_background_services()

        assert result.status == 'warn'
        assert 'Heavy processes detected' in result.message
        assert 'docker' in result.message

    def test_unsupported_platform_warns(self):
        """Unsupported platform should warn."""
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Windows'),
            tool_locator=create_mock_tools(),
            logger=create_mock_logger()
        )

        result = checker.check_background_services()

        assert result.status == 'warn'
        assert 'Unsupported platform' in result.message


class TestCheckSleepPrevention:
    """Test check_sleep_prevention method."""

    def test_macos_with_caffeinate_passes(self):
        """macOS with caffeinate available should pass."""
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools({'caffeinate'}),
            logger=create_mock_logger()
        )

        result = checker.check_sleep_prevention()

        assert result.status == 'pass'
        assert 'caffeinate available' in result.message

    def test_macos_without_caffeinate_fails_critical(self):
        """macOS without caffeinate should fail (critical)."""
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools(set()),  # No tools
            logger=create_mock_logger()
        )

        result = checker.check_sleep_prevention()

        assert result.status == 'fail'
        assert result.critical == True
        assert 'caffeinate not found' in result.message

    def test_linux_with_systemd_inhibit_passes(self):
        """Linux with systemd-inhibit should pass."""
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools({'systemd-inhibit'}),
            logger=create_mock_logger()
        )

        result = checker.check_sleep_prevention()

        assert result.status == 'pass'
        assert 'systemd-inhibit available' in result.message

    def test_linux_without_systemd_inhibit_warns(self):
        """Linux without systemd-inhibit should warn."""
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Linux'),
            tool_locator=create_mock_tools(set()),  # No tools
            logger=create_mock_logger()
        )

        result = checker.check_sleep_prevention()

        assert result.status == 'warn'
        assert 'systemd-inhibit not found' in result.message


class TestRunAllChecks:
    """Test run_all_checks orchestration method."""

    def test_all_checks_executed(self):
        """run_all_checks should execute all 5 checks."""
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools({'caffeinate'}),
            logger=create_mock_logger()
        )

        checks, all_pass = checker.run_all_checks()

        assert len(checks) == 5
        assert checks[0].name == 'CPU Governor'
        assert checks[1].name == 'Turbo Boost'
        assert checks[2].name == 'Thermal State'
        assert checks[3].name == 'Background Services'
        assert checks[4].name == 'Sleep Prevention'

    def test_all_pass_returns_true(self):
        """All checks passing should return True."""
        # macOS with caffeinate = all pass
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process({
                'pmset -g therm': (0, 'No thermal issues', ''),
                'ps aux': (0, 'user bash\n', '')
            }),
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools({'caffeinate'}),
            logger=create_mock_logger()
        )

        checks, all_pass = checker.run_all_checks()

        assert all_pass == True
        assert all(c.status == 'pass' for c in checks)

    def test_critical_failure_returns_false(self):
        """Critical failure should return False."""
        # macOS without caffeinate = critical fail
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process({
                'pmset -g therm': (0, 'No thermal issues', ''),
                'ps aux': (0, 'user bash\n', '')
            }),
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools(set()),  # No caffeinate
            logger=create_mock_logger()
        )

        checks, all_pass = checker.run_all_checks()

        assert all_pass == False
        # Find sleep prevention check
        sleep_check = [c for c in checks if c.name == 'Sleep Prevention'][0]
        assert sleep_check.status == 'fail'
        assert sleep_check.critical == True


class TestPrintResults:
    """Test print_results method."""

    def test_prints_all_checks(self):
        """print_results should log all check results."""
        logger = create_mock_logger()
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools({'caffeinate'}),
            logger=logger
        )

        checks = [
            SystemCheck('Check 1', 'pass', 'All good'),
            SystemCheck('Check 2', 'warn', 'Minor issue'),
            SystemCheck('Check 3', 'fail', 'Critical', critical=True)
        ]

        checker.print_results(checks)

        # Should log header, checks, summary, and footer
        assert logger.info.call_count > 5

        # Check that all check messages were logged
        logged_messages = [call[0][0] for call in logger.info.call_args_list]
        assert any('Check 1' in msg for msg in logged_messages)
        assert any('Check 2' in msg for msg in logged_messages)
        assert any('Check 3' in msg for msg in logged_messages)

    def test_includes_critical_issues_section(self):
        """print_results should include critical issues section when present."""
        logger = create_mock_logger()
        checker = SystemChecker(
            filesystem=create_mock_filesystem(),
            process_executor=create_mock_process(),
            env_provider=create_mock_env('Darwin'),
            tool_locator=create_mock_tools(),
            logger=logger
        )

        checks = [
            SystemCheck('Check 1', 'pass', 'All good'),
            SystemCheck('Thermal', 'warn', 'Too hot', critical=True)
        ]

        checker.print_results(checks)

        # Should log critical issues section
        logged_messages = [call[0][0] for call in logger.info.call_args_list]
        assert any('Critical Issues' in msg for msg in logged_messages)
        assert any('Thermal' in msg and 'Too hot' in msg for msg in logged_messages)


# Test discovery for pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
