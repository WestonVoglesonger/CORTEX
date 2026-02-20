"""Tests for SE-5 Step 3: Post-benchmark latency decomposition."""
import argparse
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from cortex.utils.decomposition import (
    PredictionResult, AttributionResult, attribute_latency,
    DistributionalAttribution, attribute_latency_distributional,
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


# ---------------------------------------------------------------------------
# TestDistributionalAttribution
# ---------------------------------------------------------------------------

class TestDistributionalAttribution:
    """Tests for tier 1 distributional latency decomposition."""

    def _make_prediction(self, instruction_count=50000, probe_freq_hz=3_000_000_000):
        return PredictionResult(
            kernel_name="goertzel",
            theoretical_compute_us=0.5,
            theoretical_memory_us=0.2,
            theoretical_io_us=0.0,
            theoretical_peak_us=0.5,
            bound="compute",
            operational_intensity=2.5,
            instruction_profile=None,
            source="pmu",
            decomposition_tier=1,
            instruction_count=instruction_count,
            probe_freq_hz=probe_freq_hz,
        )

    def test_distributional_returns_percentiles(self):
        """Returns p50, p95, p99 for measured, compute, and residual."""
        pred = self._make_prediction()
        measured = list(np.random.normal(50.0, 5.0, 200))
        noop = list(np.random.normal(5.0, 1.0, 200))

        result = attribute_latency_distributional(pred, measured, noop)

        assert isinstance(result, DistributionalAttribution)
        assert result.measured_p50_us > 0
        assert result.measured_p95_us >= result.measured_p50_us
        assert result.measured_p99_us >= result.measured_p95_us
        assert result.compute_p50_us >= 0
        assert result.residual_p50_us >= 0
        assert result.n_windows == 200

    def test_distributional_compute_bound_formula(self):
        """Each C_i = instruction_count / (freq_i * IPC) where IPC=1.0."""
        # 100k instructions at 1 GHz, IPC=1.0 → 100 us per window
        pred = self._make_prediction(instruction_count=100_000, probe_freq_hz=1_000_000_000)
        measured = [150.0] * 100
        noop = [5.0] * 100
        freqs = [1000.0] * 100  # 1000 MHz = 1 GHz

        result = attribute_latency_distributional(pred, measured, noop, cpu_freqs_mhz=freqs)

        assert result.compute_p50_us == pytest.approx(100.0, rel=1e-3)

    def test_distributional_uses_device_max_hz_when_freq_zero(self):
        """When telemetry freq is 0 (macOS), uses probe_freq_hz from prediction."""
        pred = self._make_prediction(instruction_count=100_000, probe_freq_hz=2_000_000_000)
        measured = [150.0] * 100
        noop = [5.0] * 100
        freqs = [0.0] * 100  # macOS — all zeros

        result = attribute_latency_distributional(pred, measured, noop, cpu_freqs_mhz=freqs)

        # 100k instructions / (2 GHz * 1.0 IPC) * 1e6 = 50 us
        assert result.compute_p50_us == pytest.approx(50.0, rel=1e-3)

    def test_distributional_residual_nonnegative(self):
        """residual_i = max(0, L_i - C_i), percentiles >= 0."""
        # Make compute >> measured so raw residual would be negative
        pred = self._make_prediction(instruction_count=1_000_000, probe_freq_hz=1_000_000_000)
        measured = [50.0] * 100  # 50 us, but compute = 1000 us
        noop = [5.0] * 100

        result = attribute_latency_distributional(pred, measured, noop)

        assert result.residual_p50_us >= 0
        assert result.residual_p95_us >= 0
        assert result.residual_p99_us >= 0

    def test_distributional_noop_subtraction(self):
        """Noop distribution subtracted via quantile matching."""
        pred = self._make_prediction(instruction_count=100_000, probe_freq_hz=1_000_000_000)
        # Compute = 100 us, measured = 150 us → residual ~50 us
        measured = [150.0] * 100
        noop = [10.0] * 100  # constant noop
        freqs = [1000.0] * 100

        result = attribute_latency_distributional(pred, measured, noop, cpu_freqs_mhz=freqs)

        # residual p50 = 50, noop p50 = 10 → net_residual p50 = 40
        assert result.net_residual_p50_us == pytest.approx(40.0, rel=1e-2)
        assert result.noop_p50_us == pytest.approx(10.0, rel=1e-2)

    def test_distributional_falls_back_to_scalar_tier0(self):
        """When tier=0 or no instruction_count, DistributionalAttribution not used."""
        pred = PredictionResult(
            kernel_name="goertzel",
            theoretical_compute_us=0.5,
            theoretical_memory_us=0.2,
            theoretical_io_us=0.0,
            theoretical_peak_us=0.5,
            bound="compute",
            operational_intensity=2.5,
            instruction_profile=None,
            source="spec.yaml",
            decomposition_tier=0,
        )
        # attribute_latency (scalar, tier 0) should still work
        latencies = [50.0] * 100
        result = attribute_latency(pred, latencies, noop_baseline_us=10.0)
        assert isinstance(result, AttributionResult)
        assert result.measured_median_us == 50.0


# ---------------------------------------------------------------------------
# TestDecomposeDistributionalRouting
# ---------------------------------------------------------------------------

class TestDecomposeDistributionalRouting:
    """Tests for tier-based routing in decompose execute()."""

    def _make_telemetry_df(self, kernel="goertzel", n=100, latency=50.0, noop_latency=5.0,
                           device_latency=None, noop_device_latency=None):
        """Create a mock telemetry DataFrame with kernel + noop rows."""
        import pandas as pd
        dev_lat = device_latency if device_latency is not None else latency
        noop_dev_lat = noop_device_latency if noop_device_latency is not None else noop_latency
        rows = []
        base_ns = 1000000000000
        for i in range(n):
            start = base_ns + i * 1000000
            rows.append({
                "plugin": kernel, "latency_us": latency, "cpu_freq_mhz": 3200, "warmup": 0,
                "device_tstart_ns": start, "device_tend_ns": start + int(dev_lat * 1000),
            })
        for i in range(n):
            start = base_ns + (n + i) * 1000000
            rows.append({
                "plugin": "noop", "latency_us": noop_latency, "cpu_freq_mhz": 3200, "warmup": 0,
                "device_tstart_ns": start, "device_tend_ns": start + int(noop_dev_lat * 1000),
            })
        return pd.DataFrame(rows)

    def _make_pred_data(self, tier=1, instruction_count=50000, probe_freq_hz=3_000_000_000):
        return {
            "device": "Test",
            "decomposition_tier": tier,
            "params": {"window_length": 160, "channels": 64},
            "predictions": [{
                "kernel_name": "goertzel",
                "theoretical_compute_us": 0.5,
                "theoretical_memory_us": 0.2,
                "theoretical_io_us": 0.0,
                "theoretical_peak_us": 0.5,
                "bound": "compute",
                "operational_intensity": 2.5,
                "source": "pmu",
                "decomposition_tier": tier,
                "instruction_count": instruction_count,
                "probe_freq_hz": probe_freq_hz,
            }],
        }

    @patch('cortex.commands.decompose.load_device_spec')
    @patch('cortex.commands.decompose.TelemetryAnalyzer')
    @patch('cortex.commands.decompose.load_prediction')
    @patch('cortex.commands.decompose.RealFileSystemService')
    def test_tier1_uses_distributional_path(self, mock_fs_cls, mock_load_pred,
                                             mock_analyzer_cls, mock_load_dev):
        """When prediction has tier=1 + instruction_count, uses distributional path."""
        from cortex.commands.decompose import execute

        mock_fs = MagicMock()
        mock_fs.exists.return_value = True
        mock_fs_cls.return_value = mock_fs

        mock_load_pred.return_value = self._make_pred_data(tier=1)
        mock_load_dev.return_value = {"device": {"name": "Test", "decomposition_tier": 1}}

        df = self._make_telemetry_df()
        mock_analyzer = MagicMock()
        mock_analyzer.load_telemetry.return_value = df
        mock_analyzer_cls.return_value = mock_analyzer

        args = argparse.Namespace(
            prediction='pred.json', run_name='test_run',
            device='dev.yaml', output=None, format='table',
        )
        result = execute(args)
        assert result == 0

    @patch('cortex.commands.decompose.load_device_spec')
    @patch('cortex.commands.decompose.TelemetryAnalyzer')
    @patch('cortex.commands.decompose.load_prediction')
    @patch('cortex.commands.decompose.RealFileSystemService')
    def test_tier0_uses_scalar_path(self, mock_fs_cls, mock_load_pred,
                                     mock_analyzer_cls, mock_load_dev):
        """When tier=0, uses existing attribute_latency() (backward compat)."""
        from cortex.commands.decompose import execute

        mock_fs = MagicMock()
        mock_fs.exists.return_value = True
        mock_fs_cls.return_value = mock_fs

        pred_data = self._make_pred_data(tier=0)
        # Remove PMU fields for tier 0
        del pred_data["predictions"][0]["instruction_count"]
        del pred_data["predictions"][0]["probe_freq_hz"]
        mock_load_pred.return_value = pred_data
        mock_load_dev.return_value = {"device": {"name": "Test", "decomposition_tier": 0}}

        df = self._make_telemetry_df()
        mock_analyzer = MagicMock()
        mock_analyzer.load_telemetry.return_value = df
        mock_analyzer_cls.return_value = mock_analyzer

        args = argparse.Namespace(
            prediction='pred.json', run_name='test_run',
            device='dev.yaml', output=None, format='table',
        )
        result = execute(args)
        assert result == 0

    @patch('cortex.commands.decompose.load_device_spec')
    @patch('cortex.commands.decompose.TelemetryAnalyzer')
    @patch('cortex.commands.decompose.load_prediction')
    @patch('cortex.commands.decompose.RealFileSystemService')
    def test_noop_passed_as_distribution(self, mock_fs_cls, mock_load_pred,
                                          mock_analyzer_cls, mock_load_dev):
        """Noop latencies passed as full list to distributional path."""
        from cortex.commands.decompose import execute

        mock_fs = MagicMock()
        mock_fs.exists.return_value = True
        mock_fs_cls.return_value = mock_fs

        mock_load_pred.return_value = self._make_pred_data(tier=1)
        mock_load_dev.return_value = {"device": {"name": "Test", "decomposition_tier": 1}}

        # Distinct device vs total latencies to verify correct path
        df = self._make_telemetry_df(
            noop_latency=1000.0, noop_device_latency=1.0,
            latency=500.0, device_latency=80.0, n=50,
        )
        mock_analyzer = MagicMock()
        mock_analyzer.load_telemetry.return_value = df
        mock_analyzer_cls.return_value = mock_analyzer

        # Patch attribute_latency_distributional to capture args
        with patch('cortex.commands.decompose.attribute_latency_distributional') as mock_dist:
            mock_dist.return_value = DistributionalAttribution(
                kernel_name="goertzel", tier=1,
                measured_p50_us=80.0, measured_p95_us=80.0, measured_p99_us=80.0,
                compute_p50_us=10.0, compute_p95_us=11.0, compute_p99_us=12.0,
                residual_p50_us=70.0, residual_p95_us=69.0, residual_p99_us=68.0,
                noop_p50_us=1.0, noop_p95_us=1.0, noop_p99_us=1.0,
                net_residual_p50_us=69.0, net_residual_p95_us=68.0, net_residual_p99_us=67.0,
                bound="compute", n_windows=50,
            )

            args = argparse.Namespace(
                prediction='pred.json', run_name='test_run',
                device='dev.yaml', output=None, format='table',
            )
            result = execute(args)
            assert result == 0

            # Verify distributional path received device latencies, not total
            call_args = mock_dist.call_args
            measured_arg = call_args[0][1]  # 2nd positional: measured latencies
            noop_arg = call_args[0][2]      # 3rd positional: noop latencies
            assert isinstance(noop_arg, list)
            assert len(noop_arg) == 50
            # Should be device latency (~1.0 us), not total (~1000 us)
            assert all(v < 10.0 for v in noop_arg)
            # Measured should be device latency (~80 us), not total (~500 us)
            assert all(v < 100.0 for v in measured_arg)


# ---------------------------------------------------------------------------
# TestDecomposeDistributionalOutput
# ---------------------------------------------------------------------------

class TestDecomposeDistributionalOutput:
    """Tests for distributional output formatting."""

    def _make_dist_result(self):
        return DistributionalAttribution(
            kernel_name="goertzel", tier=1,
            measured_p50_us=50.0, measured_p95_us=55.0, measured_p99_us=58.0,
            compute_p50_us=10.0, compute_p95_us=11.0, compute_p99_us=12.0,
            residual_p50_us=40.0, residual_p95_us=44.0, residual_p99_us=46.0,
            noop_p50_us=5.0, noop_p95_us=6.0, noop_p99_us=7.0,
            net_residual_p50_us=35.0, net_residual_p95_us=38.0, net_residual_p99_us=39.0,
            bound="compute", n_windows=200,
        )

    def test_table_output_shows_percentiles(self, capsys):
        """Table format includes p50/p95/p99 columns for tier 1."""
        from cortex.commands.decompose import _output_table_distributional

        dev = {"name": "Test Device"}
        results = [self._make_dist_result()]

        _output_table_distributional(results, dev, tier=1)
        captured = capsys.readouterr().out

        assert "p50" in captured or "P50" in captured
        assert "p95" in captured or "P95" in captured
        assert "p99" in captured or "P99" in captured
        assert "goertzel" in captured

    def test_markdown_output_shows_percentiles(self):
        """Markdown report includes distributional breakdown."""
        from cortex.commands.decompose import _generate_markdown_distributional

        dev = {"name": "Test Device"}
        results = [self._make_dist_result()]

        md = _generate_markdown_distributional(results, dev, tier=1)

        assert "p50" in md.lower() or "P50" in md
        assert "p95" in md.lower() or "P95" in md
        assert "Distributional" in md or "distributional" in md
        assert "goertzel" in md
