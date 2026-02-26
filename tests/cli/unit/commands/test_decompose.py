"""Tests for SE-5 latency characterization and SE-7 tail attribution."""
import argparse
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from cortex.utils.decomposition import (
    CharacterizationResult, characterize_kernel,
    TailAttribution, attribute_tail, _shapley_r_squared,
)

# Shared test fixtures — single source of truth for device + kernel specs
M1_DEVICE_SPEC = {
    "device": {
        "name": "Apple M1",
        "cpu_peak_gflops": 100.0,
        "memory_bandwidth_gb_s": 68.25,
        "l1_cache_kb": 192,
        "frequency": {"max_hz": 3_228_000_000},
    }
}

GOERTZEL_KERNEL_SPECS = {
    "goertzel": {
        "computational": {
            "flops_per_sample": 12,
            "memory_loads_per_sample": 1,
            "memory_stores_per_sample": 1,
        }
    }
}


# ===========================================================================
# New characterization tests (post-hoc decomposition refactor)
# ===========================================================================

class TestCharacterizeKernel:
    """Tests for characterize_kernel() base layer."""

    # Goertzel spec: flops_per_sample=12, loads=1, stores=1
    # M1 device: cpu_peak_gflops=100, memory_bw=68.25 GB/s, l1=192 KB, max_hz=3.228 GHz

    DEVICE_SPEC = M1_DEVICE_SPEC
    KERNEL_SPECS = GOERTZEL_KERNEL_SPECS

    def test_roofline_floor_compute_bound(self):
        """Correct roofline floor from spec + device."""
        # W=160, C=64, dtype=4
        # total_samples = 160*64 = 10240
        # total_flops = 12 * 10240 = 122880
        # total_bytes = (1+1) * 10240 * 4 = 81920
        # compute_us = 122880 / (100e9) * 1e6 = 1.2288 us
        # memory_us = 81920 / (68.25e9) * 1e6 = 1.200... us
        # OI = 122880 / 81920 = 1.5
        outer = [100.0] * 200
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )

        assert result is not None
        assert result.bound == "compute"
        assert result.operational_intensity == pytest.approx(1.5, rel=1e-3)
        assert result.roofline_compute_us == pytest.approx(1.2288, rel=1e-3)
        assert result.roofline_floor_us == pytest.approx(
            max(result.roofline_compute_us, result.roofline_memory_us), rel=1e-6
        )
        assert result.provenance["roofline_floor_us"] == "estimated/roofline"

    def test_device_latencies_preferred(self):
        """When device latencies provided, p5/p50/p99 from device distribution."""
        outer = [200.0] * 200  # harness-inclusive
        device = [100.0] * 200  # kernel-only
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=device,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )

        assert result.typical_us == pytest.approx(100.0, abs=1.0)
        assert result.provenance["best_us"] == "measured/timing/device"

    def test_outer_latencies_fallback(self):
        """When device latencies absent, uses outer distribution."""
        outer = [150.0] * 200
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )

        assert result.typical_us == pytest.approx(150.0, abs=1.0)
        assert result.provenance["best_us"] == "measured/timing"

    def test_best_to_typical_gap(self):
        """best_to_typical_gap = p50 - p5."""
        # Create a distribution with known spread
        outer = list(np.linspace(80, 120, 200))
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )

        expected_gap = result.typical_us - result.best_us
        assert result.best_to_typical_gap_us == pytest.approx(expected_gap, rel=1e-6)
        assert result.best_to_typical_gap_us >= 0

    def test_tail_risk(self):
        """tail_risk = p99 - p50."""
        outer = list(np.linspace(80, 120, 200))
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )

        expected_risk = result.tail_us - result.typical_us
        assert result.tail_risk_us == pytest.approx(expected_risk, rel=1e-6)
        assert result.tail_risk_us >= 0

    def test_working_set_and_fits_in_l1(self):
        """Working set = (loads + stores) * W * C * dtype_bytes; fits_in_l1 correct."""
        outer = [100.0] * 200
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )

        # (1+1) * 160 * 64 * 4 = 81920 bytes = 80 KB
        assert result.working_set_bytes == 81920
        # 80 KB < 192 KB L1
        assert result.fits_in_l1 is True
        assert result.provenance["working_set_bytes"] == "estimated/static"

    def test_unknown_kernel_returns_none(self):
        """Returns None for unknown kernel (no spec)."""
        outer = [100.0] * 200
        result = characterize_kernel(
            "unknown_kernel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )
        assert result is None

    def test_osaca_floor_is_none(self):
        """osaca_floor_us is None (OSACA not integrated yet)."""
        outer = [100.0] * 200
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )
        assert result.osaca_floor_us is None
        assert "osaca_floor_us" in result.unavailable

    def test_provenance_dict_has_correct_sources(self):
        """Provenance dict has correct source for each field."""
        outer = [100.0] * 200
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )
        assert "roofline_floor_us" in result.provenance
        assert "best_us" in result.provenance
        assert "working_set_bytes" in result.provenance

    def test_n_windows_set(self):
        """n_windows reflects the measurement source count."""
        outer = [100.0] * 150
        device = [90.0] * 150
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=device,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )
        assert result.n_windows == 150


class TestCharacterizeKernelPMU:
    """Tests for PMU enrichment in characterize_kernel()."""

    DEVICE_SPEC = M1_DEVICE_SPEC
    KERNEL_SPECS = GOERTZEL_KERNEL_SPECS

    def test_ipc_populated(self):
        """IPC populated when cycle_counts + instruction_counts provided."""
        n = 100
        outer = [100.0] * n
        # 200k instructions, 50k cycles per window → IPC = 4.0
        cycles = [50_000] * n
        insns = [200_000] * n

        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
            per_window_cycle_counts=cycles, per_window_instruction_counts=insns,
        )

        assert result.ipc == pytest.approx(4.0, rel=1e-2)
        assert result.provenance["ipc"] == "measured/PMU"

    def test_ipc_none_without_pmu(self):
        """IPC is None when no PMU data, added to unavailable."""
        outer = [100.0] * 100
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )

        assert result.ipc is None
        assert "ipc" in result.unavailable

    def test_effective_freq(self):
        """effective_freq_ghz = median(cycles / device_wall_s)."""
        n = 100
        outer = [200.0] * n
        device = [100.0] * n  # 100 us = 100e-6 s
        # 300k cycles per window, device_wall = 100e-6 s → freq = 3e9 Hz = 3.0 GHz
        cycles = [300_000] * n
        insns = [200_000] * n

        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=device,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
            per_window_cycle_counts=cycles, per_window_instruction_counts=insns,
        )

        assert result.effective_freq_ghz == pytest.approx(3.0, rel=1e-2)
        assert result.provenance["effective_freq_ghz"] == "measured/PMU+timing"

    def test_frequency_tax(self):
        """frequency_tax_pct = (1 - effective_freq / max_freq) * 100."""
        n = 100
        outer = [200.0] * n
        device = [100.0] * n  # 100 us
        # effective_freq = 300k / 100e-6 = 3.0 GHz
        # max_freq = 3.228 GHz
        # tax = (1 - 3.0/3.228) * 100 ≈ 7.06%
        cycles = [300_000] * n
        insns = [200_000] * n

        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=device,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
            per_window_cycle_counts=cycles, per_window_instruction_counts=insns,
        )

        expected_tax = (1 - 3.0e9 / 3.228e9) * 100
        assert result.frequency_tax_pct == pytest.approx(expected_tax, rel=1e-2)

    def test_no_device_ts_falls_back_to_outer(self):
        """Without device timestamps, effective_freq falls back to outer_latencies_us."""
        n = 100
        outer = [100.0] * n
        cycles = [50_000] * n
        insns = [200_000] * n

        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
            per_window_cycle_counts=cycles, per_window_instruction_counts=insns,
        )

        # IPC available (only needs cycles + insns)
        assert result.ipc is not None
        # Effective freq falls back to outer latencies when device timestamps absent
        assert result.effective_freq_ghz is not None
        assert result.frequency_tax_pct is not None

    def test_no_cycles_all_pmu_none(self):
        """Without cycle counts, all PMU fields None."""
        n = 100
        outer = [100.0] * n

        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
            per_window_cycle_counts=None, per_window_instruction_counts=None,
        )

        assert result.ipc is None
        assert result.effective_freq_ghz is None
        assert result.frequency_tax_pct is None


class TestCharacterizeKernelNoop:
    """Tests for noop cross-validation in characterize_kernel()."""

    DEVICE_SPEC = M1_DEVICE_SPEC
    KERNEL_SPECS = GOERTZEL_KERNEL_SPECS

    def test_noop_p50_populated(self):
        """noop_p50_us populated when noop provided."""
        outer = [100.0] * 100
        noop = [5.0] * 100
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
            noop_latencies_us=noop,
        )
        assert result.noop_p50_us == pytest.approx(5.0, abs=0.1)

    def test_noop_absent_no_error(self):
        """Noop absent: noop_p50_us is None, no error."""
        outer = [100.0] * 100
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
            noop_latencies_us=None,
        )
        assert result.noop_p50_us is None
        # Result still fully functional
        assert result.typical_us > 0


class TestCharacterizeDecomposeExecute:
    """Tests for new decompose execute() with characterize_kernel path."""

    def _make_telemetry_df(self, kernel="goertzel", n=100, latency=100.0,
                            noop_latency=5.0, has_device_ts=True,
                            device_latency=90.0, has_pmu=False):
        """Create a mock telemetry DataFrame."""
        import pandas as pd
        rows = []
        base_ns = 1_000_000_000_000
        for i in range(n):
            start = base_ns + i * 1_000_000
            row = {
                "plugin": kernel, "latency_us": latency,
                "cpu_freq_mhz": 3200, "warmup": 0,
            }
            if has_device_ts:
                row["device_tstart_ns"] = start
                row["device_tend_ns"] = start + int(device_latency * 1000)
            if has_pmu:
                row["pmu_cycle_count"] = 100_000
                row["pmu_instruction_count"] = 200_000
            rows.append(row)
        for i in range(n):
            start = base_ns + (n + i) * 1_000_000
            row = {
                "plugin": "noop", "latency_us": noop_latency,
                "cpu_freq_mhz": 3200, "warmup": 0,
            }
            if has_device_ts:
                row["device_tstart_ns"] = start
                row["device_tend_ns"] = start + int(noop_latency * 1000)
            if has_pmu:
                row["pmu_cycle_count"] = 100
                row["pmu_instruction_count"] = 200
            rows.append(row)
        return pd.DataFrame(rows)

    @patch('cortex.commands.decompose.load_kernel_specs')
    @patch('cortex.commands.decompose.load_device_spec')
    @patch('cortex.commands.decompose.TelemetryAnalyzer')
    @patch('cortex.commands.decompose.RealFileSystemService')
    def test_produces_characterization_result(self, mock_fs_cls, mock_analyzer_cls,
                                               mock_load_dev, mock_load_specs):
        """Produces CharacterizationResult list from telemetry."""
        from cortex.commands.decompose import execute

        mock_fs = MagicMock()
        mock_fs.exists.return_value = True
        mock_fs_cls.return_value = mock_fs

        mock_load_dev.return_value = M1_DEVICE_SPEC
        mock_load_specs.return_value = GOERTZEL_KERNEL_SPECS

        df = self._make_telemetry_df(has_device_ts=True)
        mock_analyzer = MagicMock()
        mock_analyzer.load_telemetry.return_value = df
        mock_analyzer_cls.return_value = mock_analyzer

        args = argparse.Namespace(
            run_name='test_run', device='dev.yaml',
            output=None, format='table',
        )
        result = execute(args)
        assert result == 0

    @patch('cortex.commands.decompose.load_kernel_specs')
    @patch('cortex.commands.decompose.load_device_spec')
    @patch('cortex.commands.decompose.TelemetryAnalyzer')
    @patch('cortex.commands.decompose.RealFileSystemService')
    def test_device_ts_passed_when_present(self, mock_fs_cls, mock_analyzer_cls,
                                            mock_load_dev, mock_load_specs):
        """Device timestamps present → passes device_latencies_us."""
        from cortex.commands.decompose import execute

        mock_fs = MagicMock()
        mock_fs.exists.return_value = True
        mock_fs_cls.return_value = mock_fs

        mock_load_dev.return_value = self._device_spec()
        mock_load_specs.return_value = self._kernel_specs()

        df = self._make_telemetry_df(has_device_ts=True, device_latency=90.0, latency=120.0)
        mock_analyzer = MagicMock()
        mock_analyzer.load_telemetry.return_value = df
        mock_analyzer_cls.return_value = mock_analyzer

        with patch('cortex.commands.decompose.characterize_kernel') as mock_ck:
            mock_ck.return_value = self._mock_result()

            args = argparse.Namespace(
                run_name='test_run', device='dev.yaml',
                output=None, format='table',
            )
            execute(args)

            call_kwargs = mock_ck.call_args
            # device_latencies_us should be provided (not None)
            assert call_kwargs.kwargs.get('device_latencies_us') is not None or \
                   (len(call_kwargs.args) > 2 and call_kwargs.args[2] is not None)

    @patch('cortex.commands.decompose.load_kernel_specs')
    @patch('cortex.commands.decompose.load_device_spec')
    @patch('cortex.commands.decompose.TelemetryAnalyzer')
    @patch('cortex.commands.decompose.RealFileSystemService')
    def test_device_ts_none_when_absent(self, mock_fs_cls, mock_analyzer_cls,
                                         mock_load_dev, mock_load_specs):
        """Device timestamps absent → passes None for device_latencies_us."""
        from cortex.commands.decompose import execute

        mock_fs = MagicMock()
        mock_fs.exists.return_value = True
        mock_fs_cls.return_value = mock_fs

        mock_load_dev.return_value = self._device_spec()
        mock_load_specs.return_value = self._kernel_specs()

        df = self._make_telemetry_df(has_device_ts=False)
        mock_analyzer = MagicMock()
        mock_analyzer.load_telemetry.return_value = df
        mock_analyzer_cls.return_value = mock_analyzer

        with patch('cortex.commands.decompose.characterize_kernel') as mock_ck:
            mock_ck.return_value = self._mock_result()

            args = argparse.Namespace(
                run_name='test_run', device='dev.yaml',
                output=None, format='table',
            )
            execute(args)

            call_kwargs = mock_ck.call_args
            # Check device_latencies_us is None
            if call_kwargs.kwargs:
                assert call_kwargs.kwargs.get('device_latencies_us') is None
            else:
                assert call_kwargs.args[2] is None

    @patch('cortex.commands.decompose.load_kernel_specs')
    @patch('cortex.commands.decompose.load_device_spec')
    @patch('cortex.commands.decompose.TelemetryAnalyzer')
    @patch('cortex.commands.decompose.RealFileSystemService')
    def test_pmu_columns_enriched(self, mock_fs_cls, mock_analyzer_cls,
                                    mock_load_dev, mock_load_specs):
        """PMU columns present → IPC + effective freq enriched."""
        from cortex.commands.decompose import execute

        mock_fs = MagicMock()
        mock_fs.exists.return_value = True
        mock_fs_cls.return_value = mock_fs

        mock_load_dev.return_value = self._device_spec()
        mock_load_specs.return_value = self._kernel_specs()

        df = self._make_telemetry_df(has_device_ts=True, has_pmu=True)
        mock_analyzer = MagicMock()
        mock_analyzer.load_telemetry.return_value = df
        mock_analyzer_cls.return_value = mock_analyzer

        with patch('cortex.commands.decompose.characterize_kernel') as mock_ck:
            mock_ck.return_value = self._mock_result()

            args = argparse.Namespace(
                run_name='test_run', device='dev.yaml',
                output=None, format='table',
            )
            execute(args)

            call_kwargs = mock_ck.call_args
            # PMU data should be passed
            kw = call_kwargs.kwargs if call_kwargs.kwargs else {}
            assert kw.get('per_window_cycle_counts') is not None

    @patch('cortex.commands.decompose.load_kernel_specs')
    @patch('cortex.commands.decompose.load_device_spec')
    @patch('cortex.commands.decompose.TelemetryAnalyzer')
    @patch('cortex.commands.decompose.RealFileSystemService')
    def test_pmu_absent_fields_unavailable(self, mock_fs_cls, mock_analyzer_cls,
                                            mock_load_dev, mock_load_specs):
        """PMU columns absent → PMU fields in unavailable list."""
        from cortex.commands.decompose import execute

        mock_fs = MagicMock()
        mock_fs.exists.return_value = True
        mock_fs_cls.return_value = mock_fs

        mock_load_dev.return_value = self._device_spec()
        mock_load_specs.return_value = self._kernel_specs()

        df = self._make_telemetry_df(has_device_ts=True, has_pmu=False)
        mock_analyzer = MagicMock()
        mock_analyzer.load_telemetry.return_value = df
        mock_analyzer_cls.return_value = mock_analyzer

        with patch('cortex.commands.decompose.characterize_kernel') as mock_ck:
            mock_ck.return_value = self._mock_result(ipc=None, unavailable={
                    "ipc": "no PMU data",
                    "effective_freq_ghz": "no PMU data",
                    "frequency_tax_pct": "no PMU data",
                })

            args = argparse.Namespace(
                run_name='test_run', device='dev.yaml',
                output=None, format='table',
            )
            execute(args)

            call_kwargs = mock_ck.call_args
            kw = call_kwargs.kwargs if call_kwargs.kwargs else {}
            assert kw.get('per_window_cycle_counts') is None

    def _device_spec(self):
        return M1_DEVICE_SPEC

    def _kernel_specs(self):
        return GOERTZEL_KERNEL_SPECS

    def _mock_result(self, ipc=3.2, unavailable=None):
        return CharacterizationResult(
            kernel_name="goertzel",
            bound="compute", operational_intensity=1.5,
            working_set_bytes=81920, fits_in_l1=True,
            roofline_floor_us=0.0013, roofline_compute_us=0.0013,
            roofline_memory_us=0.0012, osaca_floor_us=None,
            best_us=85.0, typical_us=100.0, tail_us=130.0,
            best_to_typical_gap_us=15.0, tail_risk_us=30.0,
            noop_p50_us=5.0, ipc=ipc, n_windows=100,
            provenance={"best_us": "measured/timing/device"},
            unavailable=unavailable or {},
        )


class TestCharacterizeOutputFormatters:
    """Tests for characterization output formatters."""

    def _make_char_result(self):
        return CharacterizationResult(
            kernel_name="goertzel",
            bound="compute", operational_intensity=1.5,
            working_set_bytes=81920, fits_in_l1=True,
            roofline_floor_us=0.0013, roofline_compute_us=0.0013,
            roofline_memory_us=0.0012, osaca_floor_us=None,
            best_us=85.0, typical_us=108.0, tail_us=142.0,
            best_to_typical_gap_us=23.0, tail_risk_us=34.0,
            noop_p50_us=5.0, ipc=3.2,
            effective_freq_ghz=2.8, frequency_tax_pct=13.2,
            n_windows=200,
            tail_ratio=1.31, platform_tail_verdict="platform-dominated",
            provenance={
                "roofline_floor_us": "estimated/roofline",
                "best_us": "measured/timing/device",
                "typical_us": "measured/timing/device",
                "tail_us": "measured/timing/device",
                "working_set_bytes": "estimated/static",
                "ipc": "measured/PMU",
                "effective_freq_ghz": "measured/PMU+timing",
            },
            unavailable={"osaca_floor_us": "OSACA not integrated"},
        )

    def _make_tail_attribution(self):
        return TailAttribution(
            kernel_name="goertzel",
            n_windows=200,
            tail_ratio=1.31,
            noop_tail_ratio=1.2,
            normalized_ratio=1.09,
            verdict="platform-dominated",
            tier=1,
            provenance={"tail_ratio": "measured/timing"},
        )

    def _make_result(self):
        return (self._make_char_result(), self._make_tail_attribution())

    def test_table_shows_provenance(self, capsys):
        """Table shows provenance tags in brackets."""
        from cortex.commands.decompose import _output_characterization

        dev = {"name": "Apple M1"}
        results = [self._make_result()]

        _output_characterization(results, dev, 'table')
        captured = capsys.readouterr().out

        assert "goertzel" in captured
        assert "estimated/roofline" in captured or "roofline" in captured.lower()
        assert "compute" in captured
        # SE-7: tail attribution output
        assert "Tail ratio" in captured
        assert "Verdict" in captured or "verdict" in captured

    def test_unavailable_shows_na(self, capsys):
        """Unavailable metrics show N/A with reason."""
        from cortex.commands.decompose import _output_characterization

        dev = {"name": "Apple M1"}
        char_result = self._make_char_result()
        char_result.ipc = None
        char_result.effective_freq_ghz = None
        char_result.frequency_tax_pct = None
        char_result.unavailable = {
            "osaca_floor_us": "OSACA not integrated",
            "ipc": "no PMU data",
            "effective_freq_ghz": "no PMU data",
            "frequency_tax_pct": "no PMU data",
        }
        results = [(char_result, self._make_tail_attribution())]

        _output_characterization(results, dev, 'table')
        captured = capsys.readouterr().out

        assert "N/A" in captured

    def test_json_has_correct_keys(self):
        """JSON has correct keys including provenance, unavailable, and tail_attribution."""
        import json as json_mod
        from cortex.commands.decompose import _output_characterization
        from io import StringIO
        import sys

        dev = {"name": "Apple M1"}
        results = [self._make_result()]

        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            _output_characterization(results, dev, 'json')
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        data = json_mod.loads(output)
        assert "characterizations" in data
        char = data["characterizations"][0]
        assert "provenance" in char
        assert "unavailable" in char
        assert "kernel" in char
        # SE-7: tail attribution in JSON
        assert "tail_attribution" in char
        ta = char["tail_attribution"]
        assert "tail_ratio" in ta
        assert "verdict" in ta
        assert "tier" in ta

    def test_markdown_is_valid(self):
        """Markdown output contains expected structure."""
        from cortex.commands.decompose import _output_characterization
        from io import StringIO
        import sys

        dev = {"name": "Apple M1"}
        results = [self._make_result()]

        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            _output_characterization(results, dev, 'markdown')
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert "#" in output  # has headers
        assert "goertzel" in output
        # SE-7: tail attribution in markdown
        assert "Tail ratio" in output
        assert "Tail verdict" in output


# ===========================================================================
# SE-7: Tail-latency attribution tests
# ===========================================================================

class TestAttributeTailTier1:
    """Tier 1 tests: diagnostic ratios (always available)."""

    def test_basic_ratio(self):
        """P99=100, P50=50 → ratio=2.0."""
        # 90% of values at 50, top 10% at 100
        lats = [50.0] * 900 + [100.0] * 100
        result = attribute_tail("goertzel", lats)
        assert result.tail_ratio == pytest.approx(100.0 / 50.0, rel=0.1)
        assert result.tier >= 1
        assert result.kernel_name == "goertzel"

    def test_with_noop_normalization(self):
        """noop ratio=1.5, kernel ratio=3.0 → normalized=2.0 → 'mixed'."""
        # Kernel: P50=50, P99=150 → ratio=3.0
        kernel_lats = [50.0] * 900 + [150.0] * 100
        # Noop: P50=10, P99=15 → ratio=1.5
        noop_lats = [10.0] * 900 + [15.0] * 100
        result = attribute_tail("goertzel", kernel_lats, noop_latencies_us=noop_lats)
        assert result.noop_tail_ratio is not None
        assert result.normalized_ratio is not None
        assert result.normalized_ratio == pytest.approx(
            result.tail_ratio / result.noop_tail_ratio, rel=0.1
        )
        assert result.verdict == "mixed"

    def test_platform_dominated(self):
        """normalized < 1.5 → 'platform-dominated'."""
        # Kernel and noop have similar tail ratios
        kernel_lats = [100.0] * 900 + [120.0] * 100
        noop_lats = [10.0] * 900 + [12.0] * 100
        result = attribute_tail("goertzel", kernel_lats, noop_latencies_us=noop_lats)
        assert result.verdict == "platform-dominated"

    def test_algorithmic(self):
        """normalized > 3.0 → 'algorithmic'."""
        # Kernel has massive tail, noop is tight
        kernel_lats = [50.0] * 900 + [500.0] * 100
        noop_lats = [10.0] * 900 + [11.0] * 100
        result = attribute_tail("goertzel", kernel_lats, noop_latencies_us=noop_lats)
        assert result.verdict == "algorithmic"


class TestAttributeTailTier2:
    """Tier 2 tests: cohort stratification."""

    def _make_lats_with_freq(self, n=1000, seed=42):
        """Create latencies correlated with CPU frequency.

        Tail windows get low frequency (1600 MHz), typical get high (3200 MHz).
        """
        rng = np.random.RandomState(seed)
        freq = np.full(n, 3200.0)
        lats = rng.normal(100, 5, n)
        # Make top 5% have much higher latency AND lower freq
        tail_count = n // 20
        lats[-tail_count:] = rng.normal(300, 20, tail_count)
        freq[-tail_count:] = 1600.0
        return lats.tolist(), freq.tolist()

    def test_cohort_comparison(self):
        """1000 windows with tail windows having lower freq → significant."""
        lats, freq = self._make_lats_with_freq(n=1000)
        result = attribute_tail(
            "goertzel", lats,
            per_window_cpu_freq_mhz=freq,
        )
        assert result.tier >= 2
        assert result.tail_cohort_size is not None
        assert result.typical_cohort_size is not None
        assert "cpu_freq_mhz" in result.covariate_comparisons
        comp = result.covariate_comparisons["cpu_freq_mhz"]
        assert comp.significant is True
        assert comp.direction == "lower_in_tail"

    def test_freq_stratification(self):
        """Stable freq windows have lower P99 than unstable."""
        lats, freq = self._make_lats_with_freq(n=1000)
        result = attribute_tail(
            "goertzel", lats,
            per_window_cpu_freq_mhz=freq,
        )
        assert result.stable_freq_p99_us is not None
        assert result.unstable_freq_p99_us is not None
        # Unstable freq (1600 MHz) windows should have higher P99
        assert result.unstable_freq_p99_us > result.stable_freq_p99_us

    def test_insufficient_windows_falls_back(self):
        """50 windows → tier=1."""
        lats = [100.0] * 45 + [300.0] * 5
        freq = [3200.0] * 45 + [1600.0] * 5
        result = attribute_tail(
            "goertzel", lats,
            per_window_cpu_freq_mhz=freq,
        )
        assert result.tier == 1
        assert result.tail_cohort_size is None

    def test_all_zeros_covariates_skipped(self):
        """cpu_freq all 0 (macOS) → skips freq, stays tier 1 if no other covariates."""
        lats = [100.0] * 200 + [300.0] * 50
        freq = [0.0] * 250
        result = attribute_tail(
            "goertzel", lats,
            per_window_cpu_freq_mhz=freq,
        )
        # All-zero covariates should be skipped
        assert "cpu_freq_mhz" not in result.covariate_comparisons


class TestAttributeTailTier3:
    """Tier 3 tests: Shapley variance decomposition."""

    def test_shapley_decomposition(self):
        """500+ windows with known correlations → R² > 0, percentages sum to ~100%."""
        rng = np.random.RandomState(42)
        n = 600
        freq = rng.uniform(1600, 3200, n)
        noise = rng.exponential(100, n)
        # Latency = f(1/freq, noise) + small random
        lats = 1e6 / freq + 0.01 * noise + rng.normal(0, 5, n)
        lats = np.abs(lats)  # ensure positive

        stall_cycles = rng.uniform(100, 1000, n)
        cycle_counts = rng.uniform(10000, 50000, n)

        result = attribute_tail(
            "goertzel", lats.tolist(),
            per_window_cpu_freq_mhz=freq.tolist(),
            per_window_osnoise_ns=noise.tolist(),
            per_window_backend_stall_counts=stall_cycles.tolist(),
            per_window_cycle_counts=cycle_counts.tolist(),
        )
        assert result.tier == 3
        assert result.model_r_squared > 0
        assert result.shapley_pct is not None
        assert result.algorithmic_residual_pct is not None
        # Shapley pct + algorithmic residual should sum to ~100% (total variance)
        total = sum(result.shapley_pct.values()) + result.algorithmic_residual_pct
        assert total == pytest.approx(100.0, abs=1.0)

    def test_insufficient_windows_falls_back(self):
        """300 windows → tier=2 (not 3)."""
        rng = np.random.RandomState(42)
        n = 300
        freq = rng.uniform(1600, 3200, n)
        noise = rng.exponential(100, n)
        lats = 1e6 / freq + 0.01 * noise + rng.normal(0, 5, n)
        lats = np.abs(lats)

        stall_cycles = rng.uniform(100, 1000, n)
        cycle_counts = rng.uniform(10000, 50000, n)

        result = attribute_tail(
            "goertzel", lats.tolist(),
            per_window_cpu_freq_mhz=freq.tolist(),
            per_window_osnoise_ns=noise.tolist(),
            per_window_backend_stall_counts=stall_cycles.tolist(),
            per_window_cycle_counts=cycle_counts.tolist(),
        )
        assert result.tier == 2
        assert result.model_r_squared is None

    def test_single_covariate_falls_back(self):
        """Only one non-zero covariate → tier=2 (Shapley needs ≥2)."""
        rng = np.random.RandomState(42)
        n = 600
        freq = rng.uniform(1600, 3200, n)
        lats = 1e6 / freq + rng.normal(0, 5, n)
        lats = np.abs(lats)

        result = attribute_tail(
            "goertzel", lats.tolist(),
            per_window_cpu_freq_mhz=freq.tolist(),
        )
        # Only one covariate → can't do Shapley
        assert result.tier == 2
        assert result.model_r_squared is None


class TestAttributeTailEdgeCases:
    """Edge cases for attribute_tail."""

    def test_zero_latency_variance(self):
        """All latencies identical → ratio=1.0, verdict='platform-dominated'."""
        lats = [100.0] * 500
        result = attribute_tail("goertzel", lats)
        assert result.tail_ratio == pytest.approx(1.0)
        assert result.verdict == "platform-dominated"


class TestShapleyRSquared:
    """Tests for _shapley_r_squared helper."""

    def test_known_decomposition(self):
        """y = 2*x1 + 3*x2 + noise → both covariates get meaningful shares."""
        rng = np.random.RandomState(42)
        n = 500
        x1 = rng.normal(0, 1, n)
        x2 = rng.normal(0, 1, n)
        noise = rng.normal(0, 0.1, n)
        y = 2 * x1 + 3 * x2 + noise

        X = np.column_stack([x1, x2])
        shapley_pct, full_r2 = _shapley_r_squared(y, X, ["x1", "x2"])

        assert full_r2 > 0.95  # Very high R² since noise is small
        assert shapley_pct["x1"] > 0
        assert shapley_pct["x2"] > 0
        # x2 has larger coefficient → should get larger share
        assert shapley_pct["x2"] > shapley_pct["x1"]
        # Should sum to ~R² * 100 (percentages of total variance)
        assert sum(shapley_pct.values()) == pytest.approx(full_r2 * 100, abs=1.0)

    def test_single_predictor(self):
        """1 covariate → Shapley = full R²."""
        rng = np.random.RandomState(42)
        n = 500
        x = rng.normal(0, 1, n)
        y = 3 * x + rng.normal(0, 0.1, n)

        X = x.reshape(-1, 1)
        shapley_pct, full_r2 = _shapley_r_squared(y, X, ["x"])

        assert full_r2 > 0.95
        # Single predictor: Shapley = R² * 100 (pct of total variance)
        assert shapley_pct["x"] == pytest.approx(full_r2 * 100, abs=1.0)

    def test_uncorrelated_predictors(self):
        """Independent covariates → Shapley ≈ marginal R²."""
        rng = np.random.RandomState(42)
        n = 500
        x1 = rng.normal(0, 1, n)
        x2 = rng.normal(0, 1, n)
        y = x1 + x2 + rng.normal(0, 0.1, n)

        X = np.column_stack([x1, x2])
        shapley_pct, full_r2 = _shapley_r_squared(y, X, ["x1", "x2"])

        # Equal coefficients, uncorrelated → roughly equal shares
        assert abs(shapley_pct["x1"] - shapley_pct["x2"]) < 15
        assert sum(shapley_pct.values()) == pytest.approx(full_r2 * 100, abs=1.0)


class TestCharacterizationTailFields:
    """Tests for tail_ratio and platform_tail_verdict in CharacterizationResult."""

    DEVICE_SPEC = M1_DEVICE_SPEC
    KERNEL_SPECS = GOERTZEL_KERNEL_SPECS

    def test_tail_ratio_populated(self):
        """characterize_kernel populates tail_ratio."""
        outer = [100.0] * 180 + [200.0] * 20
        result = characterize_kernel(
            "goertzel", outer_latencies_us=outer, device_latencies_us=None,
            device_spec=self.DEVICE_SPEC, kernel_specs=self.KERNEL_SPECS,
        )
        assert result.tail_ratio is not None
        assert result.tail_ratio > 1.0
        assert result.platform_tail_verdict is not None
        assert result.platform_tail_verdict in (
            "platform-dominated", "mixed", "algorithmic"
        )
        assert "tail_ratio" in result.provenance
