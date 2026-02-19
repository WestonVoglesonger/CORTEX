"""Tests for SE-5 Step 3: Post-benchmark latency decomposition."""
import argparse
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from cortex.utils.decomposition import (
    PredictionResult, AttributionResult, attribute_latency,
)


class TestAttributeLatency:
    """Tests for attribute_latency() core logic."""

    def _make_prediction(self, kernel="goertzel", compute_us=0.5, memory_us=0.2):
        return PredictionResult(
            kernel_name=kernel,
            theoretical_compute_us=compute_us,
            theoretical_memory_us=memory_us,
            theoretical_io_us=0.0,
            theoretical_peak_us=max(compute_us, memory_us),
            bound="compute" if compute_us >= memory_us else "memory",
            operational_intensity=2.5,
            instruction_profile=None,
            source="spec.yaml",
        )

    def test_uniform_freq_no_dvfs(self):
        """Uniform CPU frequency → dvfs_overhead_us = 0."""
        pred = self._make_prediction(compute_us=0.5, memory_us=0.2)
        latencies = [50.0] * 100
        freqs = [3200] * 100
        noop_baseline = 10.0

        result = attribute_latency(pred, latencies, noop_baseline, freqs)

        assert result.dvfs_overhead_us == 0.0
        assert result.io_overhead_us == 10.0
        assert result.measured_median_us == 50.0
        assert result.scheduling_overhead_us == pytest.approx(
            50.0 - 0.5 - 10.0 - 0.0, abs=0.1
        )
        assert result.throttled_window_pct == 0.0

    def test_mixed_freq_dvfs_attribution(self):
        """Mixed CPU frequencies → nonzero DVFS attribution."""
        pred = self._make_prediction(compute_us=0.5)

        # 80 windows at 3200 MHz with latency ~50us
        # 20 windows at 2400 MHz with latency ~70us
        latencies = [50.0] * 80 + [70.0] * 20
        freqs = [3200] * 80 + [2400] * 20
        noop_baseline = 10.0

        result = attribute_latency(pred, latencies, noop_baseline, freqs)

        assert result.dvfs_overhead_us is not None
        assert result.dvfs_overhead_us == pytest.approx(20.0, abs=0.1)
        assert result.throttled_window_pct == pytest.approx(20.0, abs=0.1)
        assert result.nominal_freq_mhz == 3200

    def test_macos_all_zeros_skip_dvfs(self):
        """macOS reports cpu_freq_mhz=0 → skip DVFS, full residual unattributed."""
        pred = self._make_prediction(compute_us=0.5)
        latencies = [50.0] * 100
        freqs = [0] * 100
        noop_baseline = 10.0

        result = attribute_latency(pred, latencies, noop_baseline, freqs)

        assert result.dvfs_overhead_us is None
        assert result.throttled_window_pct == 0.0
        # All residual goes to scheduling
        assert result.scheduling_overhead_us == pytest.approx(
            50.0 - 0.5 - 10.0, abs=0.1
        )

    def test_no_freq_data(self):
        """No cpu_freq_mhz data → skip DVFS."""
        pred = self._make_prediction(compute_us=0.5)
        latencies = [50.0] * 100
        noop_baseline = 10.0

        result = attribute_latency(pred, latencies, noop_baseline, cpu_freqs_mhz=None)

        assert result.dvfs_overhead_us is None
        assert result.nominal_freq_mhz is None

    def test_missing_noop_io_zero(self):
        """When noop baseline is 0, I/O overhead is 0."""
        pred = self._make_prediction(compute_us=0.5)
        latencies = [50.0] * 100

        result = attribute_latency(pred, latencies, noop_baseline_us=0.0)

        assert result.io_overhead_us == 0.0

    def test_scheduling_never_negative(self):
        """Scheduling overhead clamped to >= 0."""
        pred = self._make_prediction(compute_us=100.0)  # predicted > measured
        latencies = [50.0] * 100
        noop_baseline = 10.0

        result = attribute_latency(pred, latencies, noop_baseline)

        assert result.scheduling_overhead_us >= 0.0

    def test_bound_preserved_from_prediction(self):
        """Attribution preserves the bound classification from prediction."""
        pred = self._make_prediction(compute_us=0.1, memory_us=5.0)
        latencies = [50.0] * 100

        result = attribute_latency(pred, latencies, noop_baseline_us=0.0)

        assert result.bound == "memory"


class TestDecomposeParserSetup:
    """Tests for decompose command parser."""

    def test_parser_required_args(self):
        from cortex.commands.decompose import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args([
            '--prediction', '/tmp/prediction.json',
            '--run-name', 'test_run',
            '--device', 'primitives/devices/m1.yaml',
        ])
        assert args.prediction == '/tmp/prediction.json'
        assert args.run_name == 'test_run'
        assert args.device == 'primitives/devices/m1.yaml'
        assert args.format == 'table'

    def test_parser_markdown_format(self):
        from cortex.commands.decompose import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args([
            '--prediction', 'p.json',
            '--run-name', 'r',
            '--device', 'd.yaml',
            '--format', 'markdown',
        ])
        assert args.format == 'markdown'

    def test_parser_missing_required(self):
        from cortex.commands.decompose import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        with pytest.raises(SystemExit):
            parser.parse_args([])  # Missing required args


class TestDecomposeExecute:
    """Tests for decompose execute with mocked dependencies."""

    def test_execute_prediction_not_found(self):
        from cortex.commands.decompose import execute

        args = argparse.Namespace(
            prediction='nonexistent.json',
            run_name='test_run',
            device='primitives/devices/m1.yaml',
            output=None,
            format='table',
        )
        result = execute(args)
        assert result == 1

    def test_execute_device_not_found(self):
        import tempfile, json, os
        from cortex.commands.decompose import execute

        # Create a valid prediction.json
        pred = {"predictions": [{"kernel_name": "goertzel", "theoretical_compute_us": 0.5,
                                 "theoretical_memory_us": 0.2, "theoretical_peak_us": 0.5,
                                 "bound": "compute", "source": "spec.yaml"}]}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(pred, f)
            pred_path = f.name

        try:
            args = argparse.Namespace(
                prediction=pred_path,
                run_name='test_run',
                device='nonexistent.yaml',
                output=None,
                format='table',
            )

            with patch('cortex.commands.decompose.RealFileSystemService') as mock_fs_cls:
                mock_fs = MagicMock()
                mock_fs.exists.return_value = False
                mock_fs_cls.return_value = mock_fs

                result = execute(args)
                assert result == 1
        finally:
            os.unlink(pred_path)
