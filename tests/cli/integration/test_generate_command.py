"""
Integration tests for 'cortex generate' CLI command.

Tests the CLI wrapper for synthetic dataset generation, including:
- Argument parsing
- Spec-driven generation
- Error handling
"""

import pytest
import argparse
import yaml
from pathlib import Path

# Add project root to path
import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.cortex.commands import generate


def _write_spec(output_dir, signal_type='pink_noise', channels=64,
                duration_s=1, sample_rate_hz=160.0, seed=42, **extra_params):
    """Helper to write a spec.yaml for testing."""
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        'dataset': {
            'name': f'synthetic-{signal_type}-{channels}ch',
        },
        'format': {
            'channels': channels,
            'sample_rate_hz': sample_rate_hz,
            'window_length': 160,
        },
        'generation_parameters': {
            'signal_type': signal_type,
            'duration_s': duration_s,
            'seed': seed,
        },
    }
    if signal_type == 'pink_noise':
        spec['generation_parameters']['amplitude_uv_rms'] = extra_params.get('amplitude_uv_rms', 100.0)
    if signal_type == 'sine_wave':
        spec['generation_parameters']['frequency_hz'] = extra_params.get('frequency_hz', 10.0)
        spec['generation_parameters']['amplitude_uv_peak'] = extra_params.get('amplitude_uv_peak', 100.0)

    spec_path = output_dir / 'spec.yaml'
    with open(spec_path, 'w') as f:
        yaml.dump(spec, f, default_flow_style=False, sort_keys=False)
    return spec_path


class TestGenerateCommandParser:
    """Test argument parser setup."""

    def test_setup_parser_configures_spec_argument(self):
        """Verify parser has --spec argument."""
        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)

        args = parser.parse_args(['--spec', '/tmp/test/spec.yaml'])
        assert args.spec == '/tmp/test/spec.yaml'

    def test_spec_is_required(self):
        """Verify --spec is required."""
        parser = argparse.ArgumentParser()
        generate.setup_parser(parser)

        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestGenerateCommandExecution:
    """Test command execution with real filesystem."""

    def test_generate_creates_dataset_primitive(self, tmp_path):
        """Verify dataset primitive structure is created."""
        output_dir = tmp_path / "test_dataset"
        spec_path = _write_spec(output_dir)

        args = argparse.Namespace(spec=str(spec_path))
        result = generate.execute(args)

        assert result == 0
        assert output_dir.exists()
        assert (output_dir / "data.float32").exists()
        assert (output_dir / "spec.yaml").exists()

    def test_generate_correct_file_size(self, tmp_path):
        """Verify generated file has correct size."""
        output_dir = tmp_path / "test_dataset"
        spec_path = _write_spec(output_dir, channels=64, duration_s=1, sample_rate_hz=160.0)

        args = argparse.Namespace(spec=str(spec_path))
        generate.execute(args)

        data_file = output_dir / "data.float32"
        expected_size = 64 * 160 * 4  # channels * (duration * sample_rate) * bytes_per_float32
        actual_size = data_file.stat().st_size

        assert actual_size == expected_size

    def test_generate_high_channel_count(self, tmp_path):
        """Verify high channel counts work (>512)."""
        output_dir = tmp_path / "test_dataset"
        spec_path = _write_spec(output_dir, channels=1024, duration_s=1)

        args = argparse.Namespace(spec=str(spec_path))
        result = generate.execute(args)

        assert result == 0
        data_file = output_dir / "data.float32"
        expected_size = 1024 * 160 * 4
        actual_size = data_file.stat().st_size
        assert actual_size == expected_size

    def test_generate_sine_wave_requires_frequency(self, tmp_path):
        """Verify sine wave signal requires frequency_hz in spec."""
        output_dir = tmp_path / "test_dataset"
        output_dir.mkdir(parents=True)

        # Write spec without frequency_hz
        spec = {
            'format': {'channels': 64, 'sample_rate_hz': 160.0, 'window_length': 160},
            'generation_parameters': {
                'signal_type': 'sine_wave',
                'duration_s': 1,
                'seed': 42,
            },
        }
        spec_path = output_dir / 'spec.yaml'
        with open(spec_path, 'w') as f:
            yaml.dump(spec, f)

        args = argparse.Namespace(spec=str(spec_path))
        result = generate.execute(args)
        assert result != 0

    def test_generate_sine_wave_with_frequency(self, tmp_path):
        """Verify sine wave generation with frequency."""
        output_dir = tmp_path / "test_dataset"
        spec_path = _write_spec(output_dir, signal_type='sine_wave', frequency_hz=10.0)

        args = argparse.Namespace(spec=str(spec_path))
        result = generate.execute(args)
        assert result == 0

    def test_generate_regenerates_data(self, tmp_path):
        """Verify running generate again overwrites data.float32."""
        output_dir = tmp_path / "test_dataset"
        spec_path = _write_spec(output_dir)

        args = argparse.Namespace(spec=str(spec_path))
        generate.execute(args)

        size1 = (output_dir / "data.float32").stat().st_size

        # Re-read spec (it was updated by generate) and run again
        generate.execute(args)

        size2 = (output_dir / "data.float32").stat().st_size
        assert size1 == size2

    def test_reproducibility_with_seed(self, tmp_path):
        """Verify same seed produces identical output."""
        output_dir1 = tmp_path / "dataset1"
        output_dir2 = tmp_path / "dataset2"

        spec_path1 = _write_spec(output_dir1, seed=42)
        spec_path2 = _write_spec(output_dir2, seed=42)

        generate.execute(argparse.Namespace(spec=str(spec_path1)))
        generate.execute(argparse.Namespace(spec=str(spec_path2)))

        data1 = (output_dir1 / "data.float32").read_bytes()
        data2 = (output_dir2 / "data.float32").read_bytes()

        assert data1 == data2

    def test_different_seeds_produce_different_output(self, tmp_path):
        """Verify different seeds produce different output."""
        output_dir1 = tmp_path / "dataset1"
        output_dir2 = tmp_path / "dataset2"

        spec_path1 = _write_spec(output_dir1, seed=42)
        spec_path2 = _write_spec(output_dir2, seed=123)

        generate.execute(argparse.Namespace(spec=str(spec_path1)))
        generate.execute(argparse.Namespace(spec=str(spec_path2)))

        data1 = (output_dir1 / "data.float32").read_bytes()
        data2 = (output_dir2 / "data.float32").read_bytes()

        assert data1 != data2

    def test_spec_backfilled_with_recordings(self, tmp_path):
        """Verify spec.yaml is updated with recordings after generation."""
        output_dir = tmp_path / "test_dataset"
        spec_path = _write_spec(output_dir, channels=64, duration_s=1)

        generate.execute(argparse.Namespace(spec=str(spec_path)))

        with open(spec_path) as f:
            updated = yaml.safe_load(f)

        assert 'recordings' in updated
        assert updated['recordings'][0]['path'] == 'data.float32'
        assert updated['recordings'][0]['samples_per_channel'] == 160
        assert updated['dataset']['type'] == 'generated'

    def test_missing_spec_fails(self):
        """Verify missing spec file fails gracefully."""
        args = argparse.Namespace(spec='/nonexistent/spec.yaml')
        result = generate.execute(args)
        assert result == 1

    def test_missing_format_section_fails(self, tmp_path):
        """Verify spec without format section fails."""
        output_dir = tmp_path / "test_dataset"
        output_dir.mkdir(parents=True)

        spec = {'generation_parameters': {'signal_type': 'pink_noise', 'duration_s': 1}}
        spec_path = output_dir / 'spec.yaml'
        with open(spec_path, 'w') as f:
            yaml.dump(spec, f)

        args = argparse.Namespace(spec=str(spec_path))
        result = generate.execute(args)
        assert result == 1

    def test_missing_generation_parameters_fails(self, tmp_path):
        """Verify spec without generation_parameters fails."""
        output_dir = tmp_path / "test_dataset"
        output_dir.mkdir(parents=True)

        spec = {'format': {'channels': 64, 'sample_rate_hz': 160.0}}
        spec_path = output_dir / 'spec.yaml'
        with open(spec_path, 'w') as f:
            yaml.dump(spec, f)

        args = argparse.Namespace(spec=str(spec_path))
        result = generate.execute(args)
        assert result == 1


# Mark as integration test
pytestmark = pytest.mark.integration


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
