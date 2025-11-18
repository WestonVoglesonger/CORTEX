"""Integration tests for CLI wrapper commands.

CRIT-004 PR #3: Pragmatic integration tests for thin wrapper commands
(build, clean, validate, list). These commands don't need full DI refactoring
since they're simple wrappers. Integration tests verify actual behavior.
"""

import pytest
import argparse
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

from cortex.commands import build, clean, validate, list_kernels


class TestBuildCommand:
    """Integration tests for build command."""

    def test_setup_parser_configures_all_arguments(self):
        """Test that parser is configured with all required arguments."""
        parser = argparse.ArgumentParser()
        build.setup_parser(parser)

        args = parser.parse_args([])

        assert hasattr(args, 'clean')
        assert hasattr(args, 'verbose')
        assert hasattr(args, 'kernels_only')
        assert hasattr(args, 'jobs')

        assert args.clean is False
        assert args.verbose is False
        assert args.kernels_only is False
        assert args.jobs is None

    def test_parser_accepts_all_arguments(self):
        """Test that parser correctly parses all arguments."""
        parser = argparse.ArgumentParser()
        build.setup_parser(parser)

        args = parser.parse_args(['--clean', '--verbose', '--kernels-only', '--jobs', '8'])

        assert args.clean is True
        assert args.verbose is True
        assert args.kernels_only is True
        assert args.jobs == 8

    def test_execute_with_mock_subprocess(self):
        """Test execute command with mocked subprocess."""
        args = argparse.Namespace(
            clean=False,
            verbose=False,
            kernels_only=False,
            jobs=None
        )

        # Mock subprocess.run
        with patch('cortex.commands.build.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr='')

            result = build.execute(args)

            # Should succeed
            assert result == 0

            # Should have called make
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == 'make'
            assert 'all' in call_args


class TestCleanCommand:
    """Integration tests for clean command."""

    def test_setup_parser_configures_all_arguments(self):
        """Test that parser is configured with all required arguments."""
        parser = argparse.ArgumentParser()
        clean.setup_parser(parser)

        args = parser.parse_args([])

        assert hasattr(args, 'results')
        assert hasattr(args, 'build')
        assert hasattr(args, 'all')

        assert args.results is False
        assert args.build is False
        assert args.all is False

    def test_parser_accepts_arguments(self):
        """Test that parser correctly parses arguments."""
        parser = argparse.ArgumentParser()
        clean.setup_parser(parser)

        args = parser.parse_args(['--results', '--build', '--all'])

        assert args.results is True
        assert args.build is True
        assert args.all is True

    def test_execute_defaults_to_all(self):
        """Test that execute defaults to cleaning everything."""
        args = argparse.Namespace(
            results=False,
            build=False,
            all=False
        )

        # Mock subprocess and filesystem operations
        with patch('cortex.commands.clean.subprocess.run') as mock_run, \
             patch('cortex.commands.clean.Path') as mock_path:

            mock_run.return_value = MagicMock(returncode=0)
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = False
            mock_path.return_value = mock_path_instance

            result = clean.execute(args)

            # Should succeed
            assert result == 0

            # Should have set all=True
            assert args.all is True

    def test_execute_with_real_temp_directory(self):
        """Test clean command with real temporary directories."""
        temp_dir = Path(tempfile.mkdtemp())
        fake_results = temp_dir / "results"
        fake_results.mkdir()

        # Create some fake result directories
        (fake_results / "run-001").mkdir()
        (fake_results / "run-002").mkdir()

        args = argparse.Namespace(
            results=True,
            build=False,
            all=False
        )

        # Mock subprocess and patch Path to use our temp dir
        with patch('cortex.commands.clean.subprocess.run') as mock_run, \
             patch('cortex.commands.clean.Path') as mock_path:

            mock_run.return_value = MagicMock(returncode=0)

            # Mock Path to return our fake results dir
            def path_side_effect(path_str):
                if path_str == 'results':
                    return fake_results
                elif path_str == 'results/analysis':
                    return fake_results / 'analysis'
                elif path_str == 'primitives/configs/generated':
                    return temp_dir / 'nonexistent'
                return Path(path_str)

            mock_path.side_effect = path_side_effect

            result = clean.execute(args)

            # Should succeed
            assert result == 0

        # Cleanup
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


class TestValidateCommand:
    """Integration tests for validate command."""

    def test_setup_parser_configures_all_arguments(self):
        """Test that parser is configured with all required arguments."""
        parser = argparse.ArgumentParser()
        validate.setup_parser(parser)

        args = parser.parse_args([])

        assert hasattr(args, 'kernel')
        assert hasattr(args, 'verbose')

        assert args.kernel is None
        assert args.verbose is False

    def test_parser_accepts_arguments(self):
        """Test that parser correctly parses arguments."""
        parser = argparse.ArgumentParser()
        validate.setup_parser(parser)

        args = parser.parse_args(['--kernel', 'goertzel', '--verbose'])

        assert args.kernel == 'goertzel'
        assert args.verbose is True

    def test_execute_fails_if_test_binary_missing(self):
        """Test that execute fails gracefully if test binary is missing."""
        args = argparse.Namespace(
            kernel=None,
            verbose=False
        )

        # Mock Path to simulate missing test binary
        with patch('cortex.commands.validate.Path') as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = False
            mock_path.return_value = mock_path_instance

            result = validate.execute(args)

            # Should fail
            assert result == 1

    def test_execute_with_mock_subprocess(self):
        """Test execute command with mocked subprocess."""
        args = argparse.Namespace(
            kernel='goertzel',
            verbose=False
        )

        # Mock Path and subprocess
        with patch('cortex.commands.validate.Path') as mock_path, \
             patch('cortex.commands.validate.subprocess.run') as mock_run:

            # Mock test binary exists
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path.return_value = mock_path_instance

            # Mock successful validation
            mock_run.return_value = MagicMock(returncode=0, stderr='')

            result = validate.execute(args)

            # Should succeed
            assert result == 0

            # Should have called test binary
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert '--kernel' in call_args
            assert 'goertzel' in call_args


class TestListKernelsCommand:
    """Integration tests for list command."""

    def test_setup_parser_configures_all_arguments(self):
        """Test that parser is configured with all required arguments."""
        parser = argparse.ArgumentParser()
        list_kernels.setup_parser(parser)

        args = parser.parse_args([])

        assert hasattr(args, 'verbose')
        assert args.verbose is False

    def test_parser_accepts_arguments(self):
        """Test that parser correctly parses arguments."""
        parser = argparse.ArgumentParser()
        list_kernels.setup_parser(parser)

        args = parser.parse_args(['--verbose'])

        assert args.verbose is True

    def test_discover_kernels_returns_list(self):
        """Test that discover_kernels returns a list with expected structure."""
        # This tests with real discovery (should find actual kernels in repo)
        kernels = list_kernels.discover_kernels()

        # Should return a list
        assert isinstance(kernels, list)

        # If kernels are found, verify structure
        if kernels:
            kernel = kernels[0]
            assert 'name' in kernel
            assert 'version' in kernel
            assert 'dtype' in kernel
            assert 'path' in kernel
            assert 'built' in kernel
            assert 'c_impl' in kernel
            assert 'spec' in kernel
            assert 'oracle' in kernel

    def test_execute_with_real_discovery(self):
        """Test execute command with real kernel discovery."""
        args = argparse.Namespace(verbose=False)

        # Execute with real discovery
        result = list_kernels.execute(args)

        # Should succeed (even if no kernels found, it returns 1 but doesn't crash)
        assert result in [0, 1]

    def test_execute_verbose_mode(self):
        """Test execute command in verbose mode."""
        args = argparse.Namespace(verbose=True)

        # Execute with real discovery
        result = list_kernels.execute(args)

        # Should succeed (even if no kernels found, it returns 1 but doesn't crash)
        assert result in [0, 1]

    def test_execute_with_mocked_empty_discovery(self, capsys):
        """Test execute handles empty kernel list gracefully."""
        args = argparse.Namespace(verbose=False)

        # Mock discover_kernels to return empty list
        with patch('cortex.commands.list_kernels.discover_kernels') as mock_discover:
            mock_discover.return_value = []

            result = list_kernels.execute(args)

            # Should return error code
            assert result == 1

            # Should print helpful message
            captured = capsys.readouterr()
            assert "No kernels found" in captured.out

    def test_execute_with_mocked_kernels(self, capsys):
        """Test execute with mocked kernel list."""
        args = argparse.Namespace(verbose=False)

        # Mock discover_kernels
        with patch('cortex.commands.list_kernels.discover_kernels') as mock_discover:
            mock_discover.return_value = [
                {
                    'name': 'test_kernel',
                    'version': 'v1.0',
                    'dtype': 'float32',
                    'path': '/fake/path',
                    'built': True,
                    'c_impl': True,
                    'spec': True,
                    'oracle': True
                }
            ]

            result = list_kernels.execute(args)

            # Should succeed
            assert result == 0

            # Should print kernel info
            captured = capsys.readouterr()
            assert "test_kernel" in captured.out
            assert "Summary:" in captured.out


# Test discovery for pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
