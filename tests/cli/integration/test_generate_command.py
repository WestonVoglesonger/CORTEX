"""
Integration tests for 'cortex generate' CLI command.

Tests the CLI wrapper for synthetic dataset generation, including:
- Argument parsing
- File creation and validation
- Error handling
- Overwrite behavior
"""

import pytest
import argparse
from pathlib import Path

# Add project root to path
import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.cortex.commands import generate


class TestGenerateCommandParser:
    """Test argument parser setup."""

    def test_setup_parser_configures_all_arguments(self):
        """Verify parser has all required arguments."""
        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)

        # Test with minimal required arguments
        args = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '10',
            '--output-dir', '/tmp/test'
        ])

        assert args.signal == 'pink_noise'
        assert args.channels == 64
        assert args.duration == 10
        assert args.output_dir == '/tmp/test'

    def test_parser_defaults(self):
        """Verify default values are set correctly."""
        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)

        args = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '10',
            '--output-dir', '/tmp/test'
        ])

        # Check defaults
        assert args.window_length == 160
        assert args.sample_rate == 160.0
        assert args.seed == 42
        assert args.amplitude == 100.0
        assert args.overwrite is False

    def test_parser_accepts_all_optional_arguments(self):
        """Verify all optional arguments can be parsed."""
        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)

        args = parser.parse_args([
            '--signal', 'sine_wave',
            '--channels', '128',
            '--duration', '5',
            '--output-dir', '/tmp/test',
            '--window-length', '256',
            '--sample-rate', '250.0',
            '--seed', '1234',
            '--amplitude', '50.0',
            '--frequency', '10.0',
            '--overwrite'
        ])

        assert args.signal == 'sine_wave'
        assert args.channels == 128
        assert args.duration == 5
        assert args.window_length == 256
        assert args.sample_rate == 250.0
        assert args.seed == 1234
        assert args.amplitude == 50.0
        assert args.frequency == 10.0
        assert args.overwrite is True

    def test_signal_type_choices(self):
        """Verify signal type is restricted to valid choices."""
        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)

        # Valid choice
        args = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '10',
            '--output-dir', '/tmp/test'
        ])
        assert args.signal == 'pink_noise'

        # Invalid choice should raise error
        with pytest.raises(SystemExit):
            parser.parse_args([
                '--signal', 'invalid_signal',
                '--channels', '64',
                '--duration', '10',
                '--output-dir', '/tmp/test'
            ])


class TestGenerateCommandExecution:
    """Test command execution with real filesystem."""

    def test_generate_creates_dataset_primitive(self, tmp_path):
        """Verify dataset primitive structure is created."""
        output_dir = tmp_path / "test_dataset"

        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)
        args = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '1',
            '--output-dir', str(output_dir),
            '--sample-rate', '160'
        ])

        # Execute command
        result = generate.execute(args)

        assert result == 0  # Success
        assert output_dir.exists()
        assert (output_dir / "data.float32").exists()
        assert (output_dir / "spec.yaml").exists()

    def test_generate_correct_file_size(self, tmp_path):
        """Verify generated file has correct size."""
        output_dir = tmp_path / "test_dataset"

        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)
        args = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '1',  # 1 second
            '--output-dir', str(output_dir),
            '--sample-rate', '160'
        ])

        generate.execute(args)

        data_file = output_dir / "data.float32"
        expected_size = 64 * 160 * 4  # channels * (duration * sample_rate) * bytes_per_float32
        actual_size = data_file.stat().st_size

        assert actual_size == expected_size

    def test_generate_high_channel_count(self, tmp_path):
        """Verify high channel counts work (>512)."""
        output_dir = tmp_path / "test_dataset"

        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)
        args = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '1024',
            '--duration', '1',
            '--output-dir', str(output_dir),
            '--sample-rate', '160'
        ])

        result = generate.execute(args)

        assert result == 0
        data_file = output_dir / "data.float32"
        expected_size = 1024 * 160 * 4
        actual_size = data_file.stat().st_size
        assert actual_size == expected_size

    def test_generate_sine_wave_requires_frequency(self, tmp_path):
        """Verify sine wave signal requires frequency argument."""
        output_dir = tmp_path / "test_dataset"

        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)
        args = parser.parse_args([
            '--signal', 'sine_wave',
            '--channels', '64',
            '--duration', '1',
            '--output-dir', str(output_dir)
        ])

        # Should fail without frequency
        result = generate.execute(args)
        assert result != 0  # Error

    def test_generate_sine_wave_with_frequency(self, tmp_path):
        """Verify sine wave generation with frequency."""
        output_dir = tmp_path / "test_dataset"

        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)
        args = parser.parse_args([
            '--signal', 'sine_wave',
            '--channels', '64',
            '--duration', '1',
            '--output-dir', str(output_dir),
            '--frequency', '10.0'
        ])

        result = generate.execute(args)
        assert result == 0

    def test_overwrite_flag_behavior(self, tmp_path):
        """Verify overwrite flag prevents/allows overwriting existing directory."""
        output_dir = tmp_path / "test_dataset"
        output_dir.mkdir()
        (output_dir / "existing_file.txt").write_text("test")

        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)

        # Without overwrite - should fail
        args = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '1',
            '--output-dir', str(output_dir)
        ])
        result = generate.execute(args)
        assert result != 0  # Should fail

        # With overwrite - should succeed
        args = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '1',
            '--output-dir', str(output_dir),
            '--overwrite'
        ])
        result = generate.execute(args)
        assert result == 0  # Should succeed

    def test_reproducibility_with_seed(self, tmp_path):
        """Verify same seed produces identical output."""
        output_dir1 = tmp_path / "dataset1"
        output_dir2 = tmp_path / "dataset2"

        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)

        # Generate first dataset
        args1 = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '1',
            '--output-dir', str(output_dir1),
            '--seed', '42'
        ])
        generate.execute(args1)

        # Generate second dataset with same seed
        args2 = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '1',
            '--output-dir', str(output_dir2),
            '--seed', '42'
        ])
        generate.execute(args2)

        # Read both files
        data1 = (output_dir1 / "data.float32").read_bytes()
        data2 = (output_dir2 / "data.float32").read_bytes()

        # Should be identical
        assert data1 == data2

    def test_different_seeds_produce_different_output(self, tmp_path):
        """Verify different seeds produce different output."""
        output_dir1 = tmp_path / "dataset1"
        output_dir2 = tmp_path / "dataset2"

        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)

        # Generate with seed 42
        args1 = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '1',
            '--output-dir', str(output_dir1),
            '--seed', '42'
        ])
        generate.execute(args1)

        # Generate with seed 123
        args2 = parser.parse_args([
            '--signal', 'pink_noise',
            '--channels', '64',
            '--duration', '1',
            '--output-dir', str(output_dir2),
            '--seed', '123'
        ])
        generate.execute(args2)

        # Read both files
        data1 = (output_dir1 / "data.float32").read_bytes()
        data2 = (output_dir2 / "data.float32").read_bytes()

        # Should be different
        assert data1 != data2


# Mark as integration test
pytestmark = pytest.mark.integration


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
