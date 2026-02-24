"""Unit tests for HarnessRunner with dependency injection.

CRIT-004: These tests demonstrate the value of DI - we can test all logic
without any real filesystem, subprocess, or time dependencies. Fast and isolated!
"""

import pytest
from unittest.mock import Mock, MagicMock, call, patch
from pathlib import Path

from cortex.utils.runner import HarnessRunner, HARNESS_BINARY_PATH
from cortex.core.protocols import (
    FileSystemService,
    ProcessExecutor,
    ProcessHandle,
    ConfigLoader,
    TimeProvider,
    EnvironmentProvider,
    ToolLocator,
    Logger
)


class TestHarnessRunnerInit:
    """Test HarnessRunner initialization."""

    def test_init_stores_all_dependencies(self):
        """Test that __init__ properly stores all injected dependencies."""
        # Arrange
        fs = Mock(spec=FileSystemService)
        proc = Mock(spec=ProcessExecutor)
        config = Mock(spec=ConfigLoader)
        time = Mock(spec=TimeProvider)
        env = Mock(spec=EnvironmentProvider)
        tools = Mock(spec=ToolLocator)
        logger = Mock(spec=Logger)

        # Act
        runner = HarnessRunner(
            filesystem=fs,
            process_executor=proc,
            config_loader=config,
            time_provider=time,
            env_provider=env,
            tool_locator=tools,
            logger=logger
        )

        # Assert
        assert runner.fs is fs
        assert runner.process is proc
        assert runner.config is config
        assert runner.time is time
        assert runner.env is env
        assert runner.tools is tools
        assert runner.log is logger


class TestHarnessRunnerRun:
    """Test HarnessRunner.run() method."""

    def setup_method(self):
        """Set up test dependencies before each test."""
        self.fs = Mock(spec=FileSystemService)
        self.process = Mock(spec=ProcessExecutor)
        self.config = Mock(spec=ConfigLoader)
        self.time = Mock(spec=TimeProvider)
        self.env = Mock(spec=EnvironmentProvider)
        self.tools = Mock(spec=ToolLocator)
        self.logger = Mock(spec=Logger)

        self.runner = HarnessRunner(
            filesystem=self.fs,
            process_executor=self.process,
            config_loader=self.config,
            time_provider=self.time,
            env_provider=self.env,
            tool_locator=self.tools,
            logger=self.logger
        )

    def test_run_binary_not_found(self):
        """Test that run() fails gracefully when harness binary doesn't exist."""
        # Arrange
        self.fs.exists.return_value = False

        # Act
        result = self.runner.run("test.yaml", "test-run")

        # Assert
        assert result is None
        self.fs.exists.assert_called_once_with(HARNESS_BINARY_PATH)
        self.logger.error.assert_called_once()
        assert "Harness binary not found" in self.logger.error.call_args[0][0]

    def test_run_binary_is_not_file(self):
        """Test that run() fails when binary exists but is not a file."""
        # Arrange
        self.fs.exists.return_value = True
        self.fs.is_file.side_effect = lambda p: p != HARNESS_BINARY_PATH

        # Act
        result = self.runner.run("test.yaml", "test-run")

        # Assert
        assert result is None
        self.logger.error.assert_called()
        assert "exists but is not a file" in self.logger.error.call_args[0][0]

    def test_run_config_file_not_found(self):
        """Test that run() fails when config file doesn't exist."""
        # Arrange
        self.fs.exists.side_effect = lambda p: p == HARNESS_BINARY_PATH
        self.fs.is_file.return_value = True

        # Act
        result = self.runner.run("missing.yaml", "test-run")

        # Assert
        assert result is None
        self.logger.error.assert_called()
        assert "Config file not found" in self.logger.error.call_args[0][0]

    @patch('cortex.generators.process_config_with_generators')
    def test_run_successful_execution_darwin_with_caffeinate(self, mock_gen):
        """Test successful run on macOS with caffeinate available."""
        # Mock generator integration (no generator used)
        mock_gen.return_value = ("test.yaml", None, [])

        # Arrange
        # Mock to check specific paths
        def exists_side_effect(path):
            path_str = str(path)
            # Return True for binary, config, and run directory
            return ('cortex' in path_str or
                    'test.yaml' in path_str or
                    'test-run' in path_str)

        self.fs.exists.side_effect = exists_side_effect
        self.fs.is_file.return_value = True
        self.config.load_yaml.return_value = {
            'benchmark': {
                'parameters': {
                    'duration_seconds': 5,
                    'repeats': 3,
                    'warmup_seconds': 2
                }
            }
        }
        self.env.get_system_type.return_value = 'Darwin'
        self.env.get_environ.return_value = {'PATH': '/usr/bin'}
        self.tools.has_tool.side_effect = lambda tool: tool == 'caffeinate'

        # Mock process handle
        mock_handle = Mock(spec=ProcessHandle)
        # In verbose mode, we call wait() then poll() for return code
        mock_handle.wait.return_value = 0
        mock_handle.poll.return_value = 0  # After wait(), poll() returns exit code
        self.process.popen.return_value = mock_handle

        self.time.current_time.side_effect = [100.0, 100.5, 101.0]  # Simulated time progression

        # Mock file handle for log file
        mock_log_file = MagicMock()
        self.fs.open.return_value = mock_log_file

        # Act
        result = self.runner.run("test.yaml", "test-run", verbose=True)

        # Assert
        assert result is not None
        assert "test-run" in result
        self.process.popen.assert_called_once()
        cmd_arg = self.process.popen.call_args[0][0]
        assert 'caffeinate' in cmd_arg
        assert '-dims' in cmd_arg

    @patch('cortex.generators.process_config_with_generators')
    @patch('sys.stdin.isatty')
    def test_run_successful_execution_linux_with_systemd_inhibit(self, mock_isatty, mock_gen):
        """Test successful run on Linux with systemd-inhibit available."""
        # Mock generator integration (no generator used)
        mock_gen.return_value = ("test.yaml", None, [])

        # Arrange
        def exists_side_effect(path):
            path_str = str(path)
            return ('cortex' in path_str or 'test.yaml' in path_str or 'test-run' in path_str)

        self.fs.exists.side_effect = exists_side_effect
        self.fs.is_file.return_value = True
        self.config.load_yaml.return_value = {}
        self.env.get_system_type.return_value = 'Linux'
        self.env.get_environ.return_value = {}  # No SUDO_USER, not running under sudo
        self.tools.has_tool.side_effect = lambda tool: tool == 'systemd-inhibit'
        mock_isatty.return_value = True  # Simulate interactive terminal

        mock_handle = Mock(spec=ProcessHandle)
        # In verbose mode, we call wait() then poll() for return code
        mock_handle.wait.return_value = 0
        mock_handle.poll.return_value = 0  # After wait(), poll() returns exit code
        self.process.popen.return_value = mock_handle

        self.time.current_time.return_value = 100.0
        mock_log_file = MagicMock()
        self.fs.open.return_value = mock_log_file

        # Act
        result = self.runner.run("test.yaml", "test-run", verbose=True)

        # Assert
        assert result is not None
        assert "test-run" in result
        cmd_arg = self.process.popen.call_args[0][0]
        assert 'systemd-inhibit' in cmd_arg
        assert '--what=sleep:idle' in cmd_arg

    @patch('cortex.generators.process_config_with_generators')
    def test_run_subprocess_fails_nonzero_exit(self, mock_gen):
        """Test that run() handles subprocess failure with non-zero exit code."""
        # Mock generator integration (no generator used)
        mock_gen.return_value = ("test.yaml", None, [])

        # Arrange
        self.fs.exists.return_value = True
        self.fs.is_file.return_value = True
        self.config.load_yaml.return_value = {}
        self.env.get_system_type.return_value = 'Darwin'
        self.env.get_environ.return_value = {}
        self.tools.has_tool.return_value = False

        mock_handle = Mock(spec=ProcessHandle)
        mock_handle.poll.return_value = 1  # Exit code 1
        mock_handle.wait.return_value = 1
        self.process.popen.return_value = mock_handle

        self.time.current_time.return_value = 100.0
        mock_log_file = MagicMock()
        self.fs.open.return_value = mock_log_file

        # Act
        result = self.runner.run("test.yaml", "test-run", verbose=True)

        # Assert
        assert result is None
        self.logger.error.assert_called()
        assert "failed (exit code 1)" in self.logger.error.call_args[0][0]

    @patch('cortex.generators.process_config_with_generators')
    def test_run_with_spinner_in_clean_mode(self, mock_gen):
        """Test that spinner is shown in non-verbose mode."""
        # Mock generator integration (no generator used)
        mock_gen.return_value = ("test.yaml", None, [])

        # Arrange
        self.fs.exists.side_effect = lambda p: True
        self.fs.is_file.return_value = True
        self.config.load_yaml.return_value = {}
        self.env.get_system_type.return_value = 'Darwin'
        self.env.get_environ.return_value = {}
        self.tools.has_tool.return_value = False

        mock_handle = Mock(spec=ProcessHandle)
        poll_count = [0]

        def mock_poll():
            poll_count[0] += 1
            return 0 if poll_count[0] > 2 else None  # Poll 3 times then exit

        mock_handle.poll.side_effect = mock_poll
        self.process.popen.return_value = mock_handle

        self.time.current_time.side_effect = [100.0, 100.5, 101.0, 101.5]
        self.time.sleep.return_value = None

        mock_log_file = MagicMock()
        self.fs.open.return_value = mock_log_file

        # Act
        result = self.runner.run("test.yaml", "test-run", verbose=False)

        # Assert
        assert result is not None
        assert "test-run" in result
        # Verify sleep was called (spinner loop)
        assert self.time.sleep.called
        # Verify log file was opened
        self.fs.open.assert_called_once()

    def test_run_exception_handling(self):
        """Test that run() handles exceptions gracefully."""
        # Arrange
        self.fs.exists.side_effect = lambda p: True
        self.fs.is_file.return_value = True
        self.config.load_yaml.side_effect = Exception("Config parse error")
        self.env.get_environ.return_value = {}  # Real dict, not Mock

        # Act
        result = self.runner.run("test.yaml", "test-run")

        # Assert
        assert result is None
        # Should not crash, just return None


class TestHarnessRunnerCleanup:
    """Test HarnessRunner._cleanup_partial_run() method."""

    def setup_method(self):
        """Set up test dependencies."""
        self.fs = Mock(spec=FileSystemService)
        self.logger = Mock(spec=Logger)

        self.runner = HarnessRunner(
            filesystem=self.fs,
            process_executor=Mock(),
            config_loader=Mock(),
            time_provider=Mock(),
            env_provider=Mock(),
            tool_locator=Mock(),
            logger=self.logger
        )

    def test_cleanup_partial_run_directory_does_not_exist(self):
        """Test cleanup when directory doesn't exist."""
        # Arrange
        self.fs.exists.return_value = False

        # Act
        self.runner._cleanup_partial_run(Path("/tmp/test"))

        # Assert
        self.fs.rmtree.assert_not_called()

    def test_cleanup_partial_run_has_data(self):
        """Test cleanup skips when directory has data."""
        # Arrange
        run_dir = Path("/tmp/test-run")
        kernel_data_dir = f"{run_dir}/kernel-data"

        self.fs.exists.side_effect = lambda p: str(p) in [str(run_dir), kernel_data_dir]
        self.fs.is_dir.return_value = True
        self.fs.iterdir.side_effect = [
            [Path(kernel_data_dir) / "kernel1"],  # First iterdir (kernel-data)
            [Path(kernel_data_dir) / "kernel1" / "file.txt"]  # Second iterdir (kernel1 dir has files)
        ]

        # Act
        self.runner._cleanup_partial_run(run_dir)

        # Assert
        self.fs.rmtree.assert_not_called()  # Should not remove because data exists

    def test_cleanup_partial_run_no_data(self):
        """Test cleanup removes empty directory."""
        # Arrange
        run_dir = Path("/tmp/test-run")
        kernel_data_dir = f"{run_dir}/kernel-data"

        self.fs.exists.side_effect = lambda p: str(p) in [str(run_dir), kernel_data_dir]
        self.fs.is_dir.return_value = True
        self.fs.iterdir.side_effect = [
            [Path(kernel_data_dir) / "kernel1"],  # First iterdir (kernel-data)
            []  # Second iterdir (kernel1 dir is empty)
        ]

        # Act
        self.runner._cleanup_partial_run(run_dir)

        # Assert
        self.fs.rmtree.assert_called_once_with(run_dir)
        self.logger.info.assert_called()

    def test_cleanup_partial_run_exception_handling(self):
        """Test cleanup handles exceptions gracefully."""
        # Arrange
        self.fs.exists.side_effect = Exception("Permission denied")

        # Act
        self.runner._cleanup_partial_run(Path("/tmp/test"))

        # Assert
        self.logger.warning.assert_called()
        assert "Could not clean up" in self.logger.warning.call_args[0][0]


class TestHarnessRunnerIntegration:
    """Integration-style tests that verify multiple components work together."""

    @patch('cortex.generators.process_config_with_generators')
    def test_run_end_to_end_darwin(self, mock_gen):
        """Test complete run flow on macOS."""
        # Mock generator integration (no generator used)
        mock_gen.return_value = ("config.yaml", None, [])

        # Arrange
        fs = Mock(spec=FileSystemService)

        def exists_side_effect(path):
            path_str = str(path)
            return ('cortex' in path_str or 'config.yaml' in path_str or 'test-run-001' in path_str)

        fs.exists.side_effect = exists_side_effect
        fs.is_file.return_value = True

        config_loader = Mock(spec=ConfigLoader)
        config_loader.load_yaml.return_value = {
            'benchmark': {
                'parameters': {
                    'duration_seconds': 10,
                    'repeats': 5,
                    'warmup_seconds': 3
                }
            }
        }

        process = Mock(spec=ProcessExecutor)
        mock_handle = Mock(spec=ProcessHandle)
        # In verbose mode, we call wait() then poll() for return code
        mock_handle.wait.return_value = 0
        mock_handle.poll.return_value = 0  # After wait(), poll() returns exit code
        process.popen.return_value = mock_handle

        time_provider = Mock(spec=TimeProvider)
        time_provider.current_time.side_effect = [100.0, 100.5, 101.0, 101.5]

        env = Mock(spec=EnvironmentProvider)
        env.get_system_type.return_value = 'Darwin'
        env.get_environ.return_value = {'HOME': '/Users/test'}  # Real dict

        tools = Mock(spec=ToolLocator)
        tools.has_tool.side_effect = lambda t: t in ['caffeinate', 'stdbuf']

        logger = Mock(spec=Logger)

        mock_log_file = MagicMock()
        fs.open.return_value = mock_log_file

        runner = HarnessRunner(
            filesystem=fs,
            process_executor=process,
            config_loader=config_loader,
            time_provider=time_provider,
            env_provider=env,
            tool_locator=tools,
            logger=logger
        )

        # Act
        result = runner.run("config.yaml", "test-run-001", verbose=True)

        # Assert
        assert result is not None
        assert "test-run-001" in result
        process.popen.assert_called_once()

        # Verify command construction
        cmd = process.popen.call_args[0][0]
        assert 'caffeinate' in cmd
        assert 'stdbuf' in cmd
        assert 'src/engine/harness/cortex' in cmd
        assert 'run' in cmd
        assert 'config.yaml' in cmd


# Test discovery for pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
