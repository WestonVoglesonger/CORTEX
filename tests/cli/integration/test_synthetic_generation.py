"""
Integration tests for synthetic dataset generation workflow.

Tests cover end-to-end CLI integration:
- Detection → generation → config rewriting → harness invocation
- Temp file creation and cleanup
- Manifest generation and saving
- Error propagation
"""

import pytest
import os
import yaml
import tempfile
import shutil
from pathlib import Path

# Add project root to path
import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.cortex.generators.integration import (
    process_config_with_generators,
    save_generation_manifest,
    cleanup_temp_files,
    is_generator_dataset
)


class TestEndToEndGeneration:
    """Test complete generation workflow."""

    def test_static_dataset_passthrough(self, tmp_path):
        """
        Verify static datasets bypass generation entirely.

        This ensures we don't break existing PhysioNet workflow.
        """
        # Create static dataset config
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
dataset:
  path: "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
  format: "float32"
  channels: 64
  sample_rate_hz: 160
""")

        output_dir = tmp_path / "results"
        output_dir.mkdir()

        # Process config
        modified_config, manifest, temp_files = process_config_with_generators(
            str(config_path),
            str(output_dir)
        )

        # Should return original config unchanged
        assert modified_config == str(config_path)
        assert manifest is None
        assert len(temp_files) == 0

    def test_generator_dataset_execution(self, tmp_path):
        """
        Verify generator execution produces valid output.

        Tests Fix #1: High-channel mode returns file path
        Tests Fix #2: Channels only in dataset.channels
        """
        # Create generator config
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "sine_wave"
    frequency_hz: 10.0
    amplitude_uv_peak: 50.0
    duration_s: 1.0
  channels: 64
  sample_rate_hz: 160
""")

        output_dir = tmp_path / "results"
        output_dir.mkdir()

        # Process config
        modified_config, manifest, temp_files = process_config_with_generators(
            str(config_path),
            str(output_dir)
        )

        try:
            # Verify modified config was created
            assert modified_config != str(config_path)
            assert os.path.exists(modified_config)

            # Verify manifest returned
            assert manifest is not None
            assert 'generator_primitive' in manifest
            assert 'parameters' in manifest
            assert 'output' in manifest

            # Verify output characteristics
            assert manifest['output']['channels'] == 64
            assert manifest['output']['sample_rate_hz'] == 160
            assert manifest['output']['total_samples'] == 160  # 1.0s @ 160Hz

            # Verify temp files tracked
            assert len(temp_files) >= 2  # Generated data + modified config

            # Verify generated file exists
            with open(modified_config) as f:
                modified_cfg = yaml.safe_load(f)

            generated_path = modified_cfg['dataset']['path']
            assert os.path.exists(generated_path)
            assert generated_path.endswith('.float32')

            # Verify file size
            expected_size = 64 * 160 * 4  # channels * samples * bytes_per_float32
            actual_size = os.path.getsize(generated_path)
            assert actual_size == expected_size

        finally:
            # Cleanup
            cleanup_temp_files(temp_files)

    def test_high_channel_generation(self, tmp_path):
        """
        Verify high-channel mode (>512ch) produces file-backed output.

        This validates Fix #1: Generator returns file path, not ndarray.
        """
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "pink_noise"
    amplitude_uv_rms: 100.0
    duration_s: 1.0
    seed: 42
  channels: 1024
  sample_rate_hz: 160
""")

        output_dir = tmp_path / "results"
        output_dir.mkdir()

        modified_config, manifest, temp_files = process_config_with_generators(
            str(config_path),
            str(output_dir)
        )

        try:
            # Verify output
            assert manifest is not None
            assert manifest['output']['channels'] == 1024

            # Verify generated file exists and has correct size
            with open(modified_config) as f:
                modified_cfg = yaml.safe_load(f)

            generated_path = modified_cfg['dataset']['path']
            assert os.path.exists(generated_path)

            expected_size = 1024 * 160 * 4  # 1024ch × 160 samples × 4 bytes
            actual_size = os.path.getsize(generated_path)
            assert actual_size == expected_size

        finally:
            cleanup_temp_files(temp_files)

    def test_missing_required_fields(self, tmp_path):
        """Verify proper error handling for missing required fields."""
        # Missing signal_type
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    duration_s: 1.0
  channels: 64
  sample_rate_hz: 160
""")

        output_dir = tmp_path / "results"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="signal_type"):
            process_config_with_generators(str(config_path), str(output_dir))

    def test_channels_conflict_detection(self, tmp_path):
        """
        Verify error when channels specified in params (Fix #2).

        This validates the explicit error from executor.py:44-49.
        """
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "sine_wave"
    channels: 128  # WRONG: Should only be in dataset.channels
    duration_s: 1.0
  channels: 64
  sample_rate_hz: 160
""")

        output_dir = tmp_path / "results"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="must be specified in dataset.channels"):
            process_config_with_generators(str(config_path), str(output_dir))


class TestManifestHandling:
    """Test generation manifest creation and saving."""

    def test_manifest_structure(self, tmp_path):
        """Verify manifest contains all required fields."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "sine_wave"
    frequency_hz: 10.0
    duration_s: 1.0
  channels: 64
  sample_rate_hz: 160
""")

        output_dir = tmp_path / "results"
        output_dir.mkdir()

        _, manifest, temp_files = process_config_with_generators(
            str(config_path),
            str(output_dir)
        )

        try:
            # Verify required top-level fields
            assert 'generator_primitive' in manifest
            assert 'generator_version' in manifest
            assert 'timestamp' in manifest
            assert 'parameters' in manifest
            assert 'output' in manifest
            assert 'reproducibility_note' in manifest

            # Verify parameters preserved
            params = manifest['parameters']
            assert params['signal_type'] == 'sine_wave'
            assert params['frequency_hz'] == 10.0
            assert params['duration_s'] == 1.0

            # Verify output metadata
            output = manifest['output']
            assert output['channels'] == 64
            assert output['sample_rate_hz'] == 160
            assert output['total_samples'] == 160
            assert output['duration_s'] == 1.0
            assert 'file_size_bytes' in output
            assert 'temp_path' in output

        finally:
            cleanup_temp_files(temp_files)

    def test_manifest_saving(self, tmp_path):
        """Verify manifest saves to correct location."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "pink_noise"
    duration_s: 1.0
    seed: 42
  channels: 64
  sample_rate_hz: 160
""")

        output_dir = tmp_path / "results"
        output_dir.mkdir()

        _, manifest, temp_files = process_config_with_generators(
            str(config_path),
            str(output_dir)
        )

        try:
            # Save manifest
            save_generation_manifest(manifest, str(output_dir))

            # Verify file created at correct path
            manifest_path = output_dir / 'dataset' / 'generation_manifest.yaml'
            assert manifest_path.exists()

            # Verify contents
            with open(manifest_path) as f:
                saved_manifest = yaml.safe_load(f)

            assert saved_manifest == manifest

        finally:
            cleanup_temp_files(temp_files)


class TestTempFileCleanup:
    """Test temporary file lifecycle management."""

    def test_cleanup_removes_files(self, tmp_path):
        """Verify cleanup removes all temp files."""
        # Create temp files
        temp_files = [
            str(tmp_path / "temp1.float32"),
            str(tmp_path / "temp2.yaml")
        ]

        for path in temp_files:
            Path(path).write_text("test")

        # Verify files exist
        assert all(os.path.exists(p) for p in temp_files)

        # Cleanup
        cleanup_temp_files(temp_files)

        # Verify files removed
        assert not any(os.path.exists(p) for p in temp_files)

    def test_cleanup_handles_missing_files(self):
        """Verify cleanup handles nonexistent files gracefully."""
        # Should not raise exception
        cleanup_temp_files(["/nonexistent/file1.txt", "/nonexistent/file2.txt"])

    def test_cleanup_on_generation_failure(self, tmp_path):
        """Verify temp files cleaned up even if generation fails."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("""
dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "invalid_type"  # Will cause error
    duration_s: 1.0
  channels: 64
  sample_rate_hz: 160
""")

        output_dir = tmp_path / "results"
        output_dir.mkdir()

        temp_files = []
        try:
            _, _, temp_files = process_config_with_generators(
                str(config_path),
                str(output_dir)
            )
        except ValueError:
            # Expected error - verify temp files can still be cleaned
            cleanup_temp_files(temp_files)

            # Verify no temp files leaked
            for path in temp_files:
                assert not os.path.exists(path)


class TestGeneratorDetection:
    """Test generator vs static dataset detection."""

    def test_detects_synthetic_primitive(self):
        """Verify detection of synthetic generator primitive."""
        result = is_generator_dataset("primitives/datasets/v1/synthetic")
        assert result is True

    def test_rejects_static_primitive(self):
        """Verify static datasets not detected as generators."""
        # PhysioNet is static
        result = is_generator_dataset("primitives/datasets/v1/physionet-motor-imagery")
        assert result is False

    def test_handles_nonexistent_path(self):
        """Verify graceful handling of nonexistent paths."""
        result = is_generator_dataset("primitives/datasets/v1/nonexistent")
        assert result is False

    def test_handles_file_path(self):
        """Verify detection returns False for file paths (not directories)."""
        result = is_generator_dataset(
            "primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32"
        )
        assert result is False


# Mark all tests as integration tests
pytestmark = pytest.mark.integration


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
