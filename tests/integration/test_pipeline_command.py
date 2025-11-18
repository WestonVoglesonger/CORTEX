"""Integration tests for pipeline command.

CRIT-004 PR #3: Pragmatic integration tests for pipeline orchestration.
Tests argument handling and error conditions without running full pipeline
(which would be too slow for test suite).
"""

import pytest
import argparse
from pathlib import Path
from unittest.mock import patch

from cortex.commands import pipeline
from cortex.utils.paths import generate_run_name


class TestPipelineCommand:
    """Integration tests for pipeline command argument handling and orchestration."""

    def test_setup_parser_configures_all_arguments(self):
        """Test that parser is configured with all required arguments."""
        parser = argparse.ArgumentParser()
        pipeline.setup_parser(parser)

        # Parse with no arguments (all optional)
        args = parser.parse_args([])

        # Verify all attributes exist with defaults
        assert hasattr(args, 'run_name')
        assert hasattr(args, 'skip_build')
        assert hasattr(args, 'skip_validate')
        assert hasattr(args, 'duration')
        assert hasattr(args, 'repeats')
        assert hasattr(args, 'warmup')
        assert hasattr(args, 'verbose')
        assert hasattr(args, 'skip_system_check')

        # Verify defaults
        assert args.run_name is None
        assert args.skip_build is False
        assert args.skip_validate is False
        assert args.duration is None
        assert args.repeats is None
        assert args.warmup is None
        assert args.verbose is False
        assert args.skip_system_check is False

    def test_parser_accepts_all_arguments(self):
        """Test that parser correctly parses all arguments."""
        parser = argparse.ArgumentParser()
        pipeline.setup_parser(parser)

        args = parser.parse_args([
            '--run-name', 'test-run-001',
            '--skip-build',
            '--skip-validate',
            '--duration', '30',
            '--repeats', '5',
            '--warmup', '10',
            '--verbose',
            '--skip-system-check',
        ])

        assert args.run_name == 'test-run-001'
        assert args.skip_build is True
        assert args.skip_validate is True
        assert args.duration == 30
        assert args.repeats == 5
        assert args.warmup == 10
        assert args.verbose is True
        assert args.skip_system_check is True

    def test_run_name_generation(self):
        """Test that run name generation works correctly."""
        # Auto-generated run name
        run_name = generate_run_name()
        assert run_name.startswith('run-')
        assert len(run_name) > len('run-')

        # Custom run name
        custom_name = generate_run_name('my-test')
        assert 'my-test' in custom_name

    def test_execute_build_failure_handling(self):
        """Test that execute fails gracefully when build fails."""
        args = argparse.Namespace(
            run_name=None,
            skip_build=False,  # Don't skip build
            skip_validate=True,
            skip_system_check=True,
            duration=None,
            repeats=None,
            warmup=None,
            verbose=False
        )

        # Mock components - build will fail
        with patch('cortex.commands.pipeline.generate_run_name') as mock_gen, \
             patch('cortex.commands.pipeline.load_base_config') as mock_config, \
             patch('cortex.commands.pipeline.discover_kernels') as mock_discover, \
             patch('cortex.commands.pipeline.smart_build') as mock_build:

            mock_gen.return_value = 'test-run-001'
            mock_config.return_value = {'plugins': []}
            mock_discover.return_value = []

            # Simulate build failure
            mock_build.return_value = {
                'success': False,
                'errors': ['Build failed: compiler error']
            }

            # Execute should fail gracefully
            result = pipeline.execute(args)

            # Should return error code
            assert result == 1

    def test_execute_with_invalid_run_name(self):
        """Test that execute fails gracefully with invalid run name."""
        args = argparse.Namespace(
            run_name='invalid/name/with/slashes',  # Invalid characters
            skip_build=True,
            skip_validate=True,
            skip_system_check=True,
            duration=None,
            repeats=None,
            warmup=None,
            verbose=False
        )

        # Mock generate_run_name to raise ValueError
        with patch('cortex.commands.pipeline.generate_run_name') as mock_gen:
            mock_gen.side_effect = ValueError("Invalid run name")

            # Execute should fail gracefully
            result = pipeline.execute(args)

            # Should return error code
            assert result == 1

    def test_execute_prints_pipeline_overview(self, capsys):
        """Test that execute prints pipeline overview before starting."""
        args = argparse.Namespace(
            run_name=None,
            skip_build=True,
            skip_validate=True,
            skip_system_check=True,
            duration=None,
            repeats=None,
            warmup=None,
            verbose=False
        )

        # Mock all the components to prevent actual execution
        with patch('cortex.commands.pipeline.generate_run_name') as mock_gen, \
             patch('cortex.commands.pipeline.HarnessRunner') as mock_runner, \
             patch('cortex.commands.pipeline.TelemetryAnalyzer') as mock_analyzer:

            # Setup mocks
            mock_gen.return_value = 'test-run-001'
            mock_runner_instance = mock_runner.return_value
            mock_runner_instance.run_all_kernels.return_value = '/fake/results/dir'

            mock_analyzer_instance = mock_analyzer.return_value
            mock_analyzer_instance.run_full_analysis.return_value = True

            # Execute
            result = pipeline.execute(args)

            # Capture output
            captured = capsys.readouterr()
            output = captured.out

            # Verify pipeline overview is printed
            assert "CORTEX FULL PIPELINE" in output
            assert "Run name:" in output
            assert "This will:" in output

            # Should complete successfully
            assert result == 0

    def test_validate_failure_handling(self):
        """Test that execute fails gracefully when validation fails."""
        args = argparse.Namespace(
            run_name=None,
            skip_build=True,
            skip_validate=False,  # Don't skip validate
            skip_system_check=True,
            duration=None,
            repeats=None,
            warmup=None,
            verbose=False
        )

        # Mock components - validate will fail
        with patch('cortex.commands.pipeline.generate_run_name') as mock_gen, \
             patch('cortex.commands.pipeline.validate') as mock_validate:

            mock_gen.return_value = 'test-run-001'

            # Simulate validation failure
            mock_validate.execute.return_value = 1

            # Execute should fail gracefully
            result = pipeline.execute(args)

            # Should return error code
            assert result == 1


# Test discovery for pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
