"""Integration tests for run command with real dependencies.

CRIT-004: These tests use real implementations to verify end-to-end functionality.
Run these less frequently than unit tests as they're slower and require actual filesystem access.
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from cortex.utils.runner import HarnessRunner
from cortex.core import (
    ConsoleLogger,
    RealFileSystemService,
    SubprocessExecutor,
    SystemTimeProvider,
    SystemEnvironmentProvider,
    SystemToolLocator,
    YamlConfigLoader,
)


class TestHarnessRunnerIntegration:
    """Integration tests with real filesystem and dependencies."""

    def setup_method(self):
        """Set up integration test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.filesystem = RealFileSystemService()

        self.runner = HarnessRunner(
            filesystem=self.filesystem,
            process_executor=SubprocessExecutor(),
            config_loader=YamlConfigLoader(self.filesystem),
            time_provider=SystemTimeProvider(),
            env_provider=SystemEnvironmentProvider(),
            tool_locator=SystemToolLocator(),
            logger=ConsoleLogger()
        )

    def teardown_method(self):
        """Clean up temp directory after test."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_filesystem_service_real_operations(self):
        """Test that RealFileSystemService works with actual filesystem."""
        # Create a test file
        test_file = self.temp_dir / "test.txt"
        self.filesystem.write_file(test_file, "Hello, CORTEX!")

        # Verify it exists
        assert self.filesystem.exists(test_file)
        assert self.filesystem.is_file(test_file)

        # Read it back
        content = self.filesystem.read_file(test_file)
        assert content == "Hello, CORTEX!"

    def test_filesystem_service_glob(self):
        """Test glob operations with real filesystem."""
        # Create multiple test files
        for i in range(3):
            test_file = self.temp_dir / f"test_{i}.txt"
            self.filesystem.write_file(test_file, f"Content {i}")

        # Glob for them
        matches = self.filesystem.glob(self.temp_dir, "test_*.txt")
        assert len(matches) == 3

    def test_yaml_config_loader_real_file(self):
        """Test YAML config loader with real file."""
        # Create a test YAML file
        yaml_content = """
benchmark:
  parameters:
    duration_seconds: 10
    repeats: 3
    warmup_seconds: 5
"""
        yaml_file = self.temp_dir / "test_config.yaml"
        self.filesystem.write_file(yaml_file, yaml_content)

        # Load it
        config_loader = YamlConfigLoader(self.filesystem)
        config = config_loader.load_yaml(str(yaml_file))

        # Verify parsing
        assert config['benchmark']['parameters']['duration_seconds'] == 10
        assert config['benchmark']['parameters']['repeats'] == 3
        assert config['benchmark']['parameters']['warmup_seconds'] == 5

    def test_system_environment_provider(self):
        """Test that system environment provider returns real environment."""
        env_provider = SystemEnvironmentProvider()

        # Get environment
        env = env_provider.get_environ()
        assert isinstance(env, dict)
        assert len(env) > 0  # Should have some env vars

        # Get system type
        system_type = env_provider.get_system_type()
        assert system_type in ['Darwin', 'Linux', 'Windows']

    def test_system_tool_locator(self):
        """Test that tool locator can find real tools."""
        tool_locator = SystemToolLocator()

        # Python should be in PATH on any system where tests run
        python_path = tool_locator.find_tool('python3')
        if python_path:  # Might be python3 or python
            assert Path(python_path).exists()

        # has_tool should work
        has_python = tool_locator.has_tool('python3') or tool_locator.has_tool('python')
        assert has_python

    def test_runner_validates_missing_binary(self):
        """Test that runner properly validates missing harness binary (expected failure)."""
        # This should fail because the binary likely doesn't exist in test environment
        result = self.runner.run("nonexistent.yaml", "test-run")

        # Should return None (failure)
        assert result is None


# Test discovery for pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
