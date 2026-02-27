"""Tests for calibrate command helpers."""
import argparse
import pytest
from pathlib import Path

from cortex.commands.calibrate import _parse_label_pattern, _read_dataset_spec, setup_parser


class TestParseLabelPattern:
    """Tests for _parse_label_pattern()."""

    def test_basic_two_class(self):
        """Standard pattern: 100 class-0, 100 class-1."""
        labels_str, count = _parse_label_pattern("100x0,100x1")
        assert count == 200
        labels = labels_str.split(",")
        assert len(labels) == 200
        assert labels[:100] == ["0"] * 100
        assert labels[100:] == ["1"] * 100

    def test_physionet_pattern(self):
        """PhysioNet motor imagery: 125 class-0, 124 class-1."""
        labels_str, count = _parse_label_pattern("125x0,124x1")
        assert count == 249

    def test_single_class(self):
        """Single class pattern."""
        labels_str, count = _parse_label_pattern("50x0")
        assert count == 50
        assert labels_str == ",".join(["0"] * 50)

    def test_three_classes(self):
        """Multi-class pattern."""
        labels_str, count = _parse_label_pattern("10x0,10x1,10x2")
        assert count == 30
        labels = labels_str.split(",")
        assert labels[20:] == ["2"] * 10

    def test_zero_count(self):
        """Zero count is valid."""
        labels_str, count = _parse_label_pattern("0x0,10x1")
        assert count == 10

    def test_missing_x_raises(self):
        """Pattern without 'x' raises ValueError."""
        with pytest.raises(ValueError, match="Invalid label pattern"):
            _parse_label_pattern("100,100")

    def test_non_integer_raises(self):
        """Non-integer values raise ValueError."""
        with pytest.raises(ValueError, match="Invalid numbers"):
            _parse_label_pattern("abcx0")

    def test_negative_count_raises(self):
        """Negative count raises ValueError."""
        with pytest.raises(ValueError, match="Negative count"):
            _parse_label_pattern("-1x0")

    def test_negative_label_raises(self):
        """Negative label raises ValueError."""
        with pytest.raises(ValueError, match="Negative label"):
            _parse_label_pattern("10x-1")


class TestReadDatasetSpec:
    """Tests for _read_dataset_spec()."""

    def test_directory_with_spec(self, tmp_path):
        """Reads spec.yaml from directory correctly."""
        import yaml
        spec = {
            'format': {
                'channels': 64,
                'sample_rate_hz': 160,
                'window_length': 160,
            },
            'recordings': [
                {'path': 'data.float32', 'label_pattern': '100x0,100x1'}
            ],
        }
        (tmp_path / 'spec.yaml').write_text(yaml.dump(spec))
        # Create the data file
        (tmp_path / 'data.float32').write_bytes(b'\x00' * (64 * 160 * 4))

        result = _read_dataset_spec(str(tmp_path))

        assert result['channels'] == 64
        assert result['sample_rate_hz'] == 160
        assert result['window_length'] == 160
        assert result['label_pattern'] == '100x0,100x1'

    def test_directory_without_label_pattern(self, tmp_path):
        """Spec without label_pattern omits it from result."""
        import yaml
        spec = {
            'format': {'channels': 64, 'sample_rate_hz': 160},
            'recordings': [{'path': 'data.float32'}],
        }
        (tmp_path / 'spec.yaml').write_text(yaml.dump(spec))
        (tmp_path / 'data.float32').write_bytes(b'\x00' * 100)

        result = _read_dataset_spec(str(tmp_path))

        assert 'label_pattern' not in result
        assert result['window_length'] == 160  # default

    def test_missing_spec_raises(self, tmp_path):
        """Directory without spec.yaml raises ValueError."""
        with pytest.raises(ValueError, match="missing spec.yaml"):
            _read_dataset_spec(str(tmp_path))

    def test_missing_recordings_raises(self, tmp_path):
        """Spec without recordings raises ValueError."""
        import yaml
        spec = {'format': {'channels': 64}}
        (tmp_path / 'spec.yaml').write_text(yaml.dump(spec))

        with pytest.raises(ValueError, match="missing 'recordings'"):
            _read_dataset_spec(str(tmp_path))

    def test_float32_file_directly(self, tmp_path):
        """Direct .float32 path returns minimal info."""
        data_file = tmp_path / 'test.float32'
        data_file.write_bytes(b'\x00' * 100)

        result = _read_dataset_spec(str(data_file))

        assert result['data_path'] == data_file
        assert 'channels' not in result

    def test_missing_format_section_uses_defaults(self, tmp_path):
        """Spec without format section uses defaults."""
        import yaml
        spec = {'recordings': [{'path': 'data.float32'}]}
        (tmp_path / 'spec.yaml').write_text(yaml.dump(spec))
        (tmp_path / 'data.float32').write_bytes(b'\x00' * 100)

        result = _read_dataset_spec(str(tmp_path))

        assert result['channels'] is None
        assert result['window_length'] == 160


class TestCalibrateParser:
    """Tests for calibrate command parser."""

    def test_dtype_choices_enforced(self):
        """--dtype only accepts f32 and q15."""
        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args([
            '--kernel', 'csp', '--dataset', '/tmp/ds', '--output', 'out.cortex_state',
            '--dtype', 'q15',
        ])
        assert args.dtype == 'q15'

        with pytest.raises(SystemExit):
            parser.parse_args([
                '--kernel', 'csp', '--dataset', '/tmp/ds', '--output', 'out.cortex_state',
                '--dtype', 'invalid',
            ])

    def test_labels_flag_optional(self):
        """--labels is optional, defaults to None."""
        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args([
            '--kernel', 'csp', '--dataset', '/tmp/ds', '--output', 'out.cortex_state',
        ])
        assert args.labels is None

    def test_labels_flag_accepted(self):
        """--labels accepts a pattern string."""
        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args([
            '--kernel', 'csp', '--dataset', '/tmp/ds', '--output', 'out.cortex_state',
            '--labels', '125x0,124x1',
        ])
        assert args.labels == '125x0,124x1'
