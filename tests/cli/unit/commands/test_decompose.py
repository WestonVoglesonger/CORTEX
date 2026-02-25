"""Tests for SE-5 latency characterization (post-hoc decomposition)."""
import argparse
import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock

from cortex.utils.decomposition import (
    CharacterizationResult, characterize_kernel,
    attribute_tail_latency, TailAttribution, TailFactor,
)



# ===========================================================================
# New characterization tests (post-hoc decomposition refactor)
# ===========================================================================

class TestCharacterizeKernel:
    """Tests for characterize_kernel() base layer."""

    # Goertzel spec: flops_per_sample=12, loads=1, stores=1
    # M1 device: cpu_peak_gflops=100, memory_bw=68.25 GB/s, l1=192 KB, max_hz=3.228 GHz

    DEVICE_SPEC = {
        "device": {
            "name": "Apple M1",
            "cpu_peak_gflops": 100.0,
            "memory_bandwidth_gb_s": 68.25,
            "l1_cache_kb": 192,
            "frequency": {"max_hz": 3_228_000_000},
        }
    }

    KERNEL_SPECS = {
        "goertzel": {
            "computational": {
                "flops_per_sample": 12,
                "memory_loads_per_sample": 1,
                "memory_stores_per_sample": 1,
            }
        }
    }

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

    DEVICE_SPEC = {
        "device": {
            "name": "Apple M1",
            "cpu_peak_gflops": 100.0,
            "memory_bandwidth_gb_s": 68.25,
            "l1_cache_kb": 192,
            "frequency": {"max_hz": 3_228_000_000},
        }
    }

    KERNEL_SPECS = {
        "goertzel": {
            "computational": {
                "flops_per_sample": 12,
                "memory_loads_per_sample": 1,
                "memory_stores_per_sample": 1,
            }
        }
    }

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

    DEVICE_SPEC = {
        "device": {
            "name": "Apple M1",
            "cpu_peak_gflops": 100.0,
            "memory_bandwidth_gb_s": 68.25,
            "l1_cache_kb": 192,
            "frequency": {"max_hz": 3_228_000_000},
        }
    }

    KERNEL_SPECS = {
        "goertzel": {
            "computational": {
                "flops_per_sample": 12,
                "memory_loads_per_sample": 1,
                "memory_stores_per_sample": 1,
            }
        }
    }

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

        mock_load_dev.return_value = {
            "device": {
                "name": "Apple M1", "cpu_peak_gflops": 100.0,
                "memory_bandwidth_gb_s": 68.25, "l1_cache_kb": 192,
                "frequency": {"max_hz": 3_228_000_000},
            }
        }
        mock_load_specs.return_value = {
            "goertzel": {
                "computational": {
                    "flops_per_sample": 12,
                    "memory_loads_per_sample": 1,
                    "memory_stores_per_sample": 1,
                }
            }
        }

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
        return {
            "device": {
                "name": "Apple M1", "cpu_peak_gflops": 100.0,
                "memory_bandwidth_gb_s": 68.25, "l1_cache_kb": 192,
                "frequency": {"max_hz": 3_228_000_000},
            }
        }

    def _kernel_specs(self):
        return {
            "goertzel": {
                "computational": {
                    "flops_per_sample": 12,
                    "memory_loads_per_sample": 1,
                    "memory_stores_per_sample": 1,
                }
            }
        }

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

    def _make_result(self):
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

    def test_unavailable_shows_na(self, capsys):
        """Unavailable metrics show N/A with reason."""
        from cortex.commands.decompose import _output_characterization

        dev = {"name": "Apple M1"}
        result = self._make_result()
        result.ipc = None
        result.effective_freq_ghz = None
        result.frequency_tax_pct = None
        result.unavailable = {
            "osaca_floor_us": "OSACA not integrated",
            "ipc": "no PMU data",
            "effective_freq_ghz": "no PMU data",
            "frequency_tax_pct": "no PMU data",
        }
        results = [result]

        _output_characterization(results, dev, 'table')
        captured = capsys.readouterr().out

        assert "N/A" in captured

    def test_json_has_correct_keys(self):
        """JSON has correct keys including provenance and unavailable."""
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


# ===========================================================================
# Tail-latency attribution tests (SE-7)
# ===========================================================================

class TestTailAttribution:
    """Tests for attribute_tail_latency()."""

    def _make_df(self, n=200, base_latency=100.0, tail_latency=400.0,
                 tail_fraction=0.05, cpu_freq_base=3200, cpu_freq_tail=None,
                 osnoise_base=1000, osnoise_tail=None,
                 stall_cycles_base=5000, stall_cycles_tail=None,
                 cycle_count=100000, kernel="goertzel"):
        """Create a synthetic telemetry DataFrame.

        Creates n total windows: n*(1-tail_fraction) base windows at base_latency
        and n*tail_fraction tail windows at tail_latency. Platform variables can be
        set independently for base and tail windows to create known anomaly patterns.
        """
        n_tail = int(n * tail_fraction)
        n_base = n - n_tail

        rows = []
        for i in range(n_base):
            rows.append({
                'plugin': kernel, 'warmup': 0, 'window_failed': 0,
                'latency_us': base_latency,
                'cpu_freq_mhz': cpu_freq_base,
                'osnoise_total_ns': osnoise_base,
                'pmu_backend_stall_cycles': stall_cycles_base,
                'pmu_cycle_count': cycle_count,
            })
        for i in range(n_tail):
            rows.append({
                'plugin': kernel, 'warmup': 0, 'window_failed': 0,
                'latency_us': tail_latency,
                'cpu_freq_mhz': cpu_freq_tail if cpu_freq_tail is not None else cpu_freq_base,
                'osnoise_total_ns': osnoise_tail if osnoise_tail is not None else osnoise_base,
                'pmu_backend_stall_cycles': stall_cycles_tail if stall_cycles_tail is not None else stall_cycles_base,
                'pmu_cycle_count': cycle_count,
            })
        return pd.DataFrame(rows)

    def test_tail_attribution_basic(self):
        """Known freq drops causing high latency → platform-dominated."""
        # 200 windows: 190 base at 3200 MHz, 10 tail at 800 MHz (well below P10)
        df = self._make_df(
            n=200, base_latency=100.0, tail_latency=400.0,
            tail_fraction=0.05,
            cpu_freq_base=3200, cpu_freq_tail=800,
            osnoise_base=100, osnoise_tail=100,
        )
        result = attribute_tail_latency(df, "goertzel")

        assert isinstance(result, TailAttribution)
        assert result.tail_factor > 1.0
        assert result.dominant_cause == "platform"
        # freq factor should have enrichment > 1.0
        freq_factors = [f for f in result.factors if f.name == "cpu_freq"]
        assert len(freq_factors) == 1
        assert freq_factors[0].enrichment > 1.0

    def test_tail_attribution_algorithmic(self):
        """Flat freq/osnoise but high tail variance → algorithmic-dominated."""
        # All platform variables identical — tail latency is purely algorithmic
        df = self._make_df(
            n=200, base_latency=100.0, tail_latency=400.0,
            tail_fraction=0.05,
            cpu_freq_base=3200, cpu_freq_tail=3200,
            osnoise_base=100, osnoise_tail=100,
            stall_cycles_base=5000, stall_cycles_tail=5000,
        )
        result = attribute_tail_latency(df, "goertzel")

        assert result.dominant_cause == "algorithmic"
        assert result.algorithmic_pct == pytest.approx(1.0, abs=0.01)

    def test_tail_attribution_no_platform_data(self):
        """All-zero freq/osnoise/PMU → confidence=low, factors empty."""
        df = self._make_df(
            n=200, base_latency=100.0, tail_latency=400.0,
            tail_fraction=0.05,
            cpu_freq_base=0, cpu_freq_tail=0,
            osnoise_base=0, osnoise_tail=0,
            stall_cycles_base=0, stall_cycles_tail=0,
            cycle_count=0,
        )
        result = attribute_tail_latency(df, "goertzel")

        assert result.confidence == "low"
        assert len(result.factors) == 0

    def test_tail_attribution_custom_percentile(self):
        """tail_percentile=99 → fewer tail windows."""
        df = self._make_df(n=200, tail_fraction=0.05)
        result_95 = attribute_tail_latency(df, "goertzel", tail_percentile=95)
        result_99 = attribute_tail_latency(df, "goertzel", tail_percentile=99)

        assert result_99.n_tail_windows <= result_95.n_tail_windows

    def test_tail_attribution_enrichment_math(self):
        """Verify enrichment = tail_prev / base_prev with known values."""
        # Create data where ALL tail windows have low freq, NO base windows do
        n = 200
        n_tail = int(n * 0.05)
        n_base = n - n_tail

        rows = []
        # Base windows: all at 3200 MHz (well above any P10 threshold)
        for _ in range(n_base):
            rows.append({
                'plugin': 'goertzel', 'warmup': 0, 'window_failed': 0,
                'latency_us': 100.0, 'cpu_freq_mhz': 3200,
                'osnoise_total_ns': 0, 'pmu_backend_stall_cycles': 0,
                'pmu_cycle_count': 0,
            })
        # Tail windows: at 100 MHz (well below P10)
        for _ in range(n_tail):
            rows.append({
                'plugin': 'goertzel', 'warmup': 0, 'window_failed': 0,
                'latency_us': 500.0, 'cpu_freq_mhz': 100,
                'osnoise_total_ns': 0, 'pmu_backend_stall_cycles': 0,
                'pmu_cycle_count': 0,
            })
        df = pd.DataFrame(rows)
        result = attribute_tail_latency(df, "goertzel")

        freq_factors = [f for f in result.factors if f.name == "cpu_freq"]
        assert len(freq_factors) == 1
        f = freq_factors[0]
        # tail_prevalence should be 1.0 (all tail windows are anomalous)
        assert f.tail_prevalence == pytest.approx(1.0, abs=0.01)
        # Verify enrichment formula
        if f.base_prevalence > 0:
            assert f.enrichment == pytest.approx(f.tail_prevalence / f.base_prevalence, rel=1e-3)
        else:
            assert f.enrichment == float('inf')

    def test_tail_attribution_too_few_windows(self):
        """<10 tail windows → factors empty, verdict mentions insufficient."""
        # Only 20 windows total, P95 → 1 tail window (< MIN_TAIL_WINDOWS=10)
        df = self._make_df(
            n=20, base_latency=100.0, tail_latency=400.0,
            tail_fraction=0.05,
        )
        result = attribute_tail_latency(df, "goertzel")

        assert len(result.factors) == 0
        assert "insufficient" in result.dominant_cause

    def test_tail_attribution_zero_base_prevalence(self):
        """All base windows normal, all tail anomalous → enrichment=inf, handled."""
        # Ensure no base windows are anomalous for freq
        n = 400
        rows = []
        # 380 base windows: all at 3200 MHz
        for _ in range(380):
            rows.append({
                'plugin': 'goertzel', 'warmup': 0, 'window_failed': 0,
                'latency_us': 100.0, 'cpu_freq_mhz': 3200,
                'osnoise_total_ns': 0, 'pmu_backend_stall_cycles': 0,
                'pmu_cycle_count': 0,
            })
        # 20 tail windows: all at 50 MHz (guaranteed below P10)
        for _ in range(20):
            rows.append({
                'plugin': 'goertzel', 'warmup': 0, 'window_failed': 0,
                'latency_us': 800.0, 'cpu_freq_mhz': 50,
                'osnoise_total_ns': 0, 'pmu_backend_stall_cycles': 0,
                'pmu_cycle_count': 0,
            })
        df = pd.DataFrame(rows)
        result = attribute_tail_latency(df, "goertzel")

        freq_factors = [f for f in result.factors if f.name == "cpu_freq"]
        assert len(freq_factors) == 1
        f = freq_factors[0]
        assert f.enrichment == float('inf')
        assert result.dominant_cause == "platform"

    def test_tail_attribution_mixed_verdict(self):
        """~50% platform anomaly rate → mixed verdict."""
        n = 200
        n_tail = int(n * 0.10)  # 20 tail windows (P90)
        n_base = n - n_tail
        rows = []
        for _ in range(n_base):
            rows.append({
                'plugin': 'goertzel', 'warmup': 0, 'window_failed': 0,
                'latency_us': 100.0, 'cpu_freq_mhz': 3200,
                'osnoise_total_ns': 0, 'pmu_backend_stall_cycles': 0,
                'pmu_cycle_count': 0,
            })
        # Half tail windows with low freq (platform), half with normal freq (algorithmic)
        for i in range(n_tail):
            rows.append({
                'plugin': 'goertzel', 'warmup': 0, 'window_failed': 0,
                'latency_us': 500.0 + i,  # distinct to avoid ties
                'cpu_freq_mhz': 100 if i < n_tail // 2 else 3200,
                'osnoise_total_ns': 0, 'pmu_backend_stall_cycles': 0,
                'pmu_cycle_count': 0,
            })
        df = pd.DataFrame(rows)
        result = attribute_tail_latency(df, "goertzel", tail_percentile=90)
        assert result.dominant_cause == "mixed"

    def test_tail_attribution_nonexistent_kernel(self):
        """Kernel not in DataFrame → insufficient data."""
        df = self._make_df(n=200, kernel="goertzel")
        result = attribute_tail_latency(df, "nonexistent_kernel")
        assert result.dominant_cause == "insufficient data"
        assert result.n_total_windows == 0
        assert result.tail_factor == 0.0

    def test_tail_attribution_nan_latency_filtered(self):
        """NaN latency values are filtered out gracefully."""
        df = self._make_df(n=200, base_latency=100.0, tail_latency=400.0,
                           tail_fraction=0.05)
        # Inject NaN values
        df.loc[0:4, 'latency_us'] = float('nan')
        result = attribute_tail_latency(df, "goertzel")
        # Should still produce a valid result (no NaN in output)
        assert not np.isnan(result.p50_us)
        assert not np.isnan(result.p99_us)

    def test_tail_attribution_zero_zero_enrichment(self):
        """When both tail and base prevalence are 0, enrichment is 0 (not inf)."""
        # All freq values identical and nonzero → no anomalies anywhere
        df = self._make_df(
            n=200, base_latency=100.0, tail_latency=400.0,
            tail_fraction=0.10,
            cpu_freq_base=3200, cpu_freq_tail=3200,
            osnoise_base=0, osnoise_tail=0,
            stall_cycles_base=0, stall_cycles_tail=0,
            cycle_count=0,
        )
        result = attribute_tail_latency(df, "goertzel", tail_percentile=90)
        for f in result.factors:
            if f.tail_prevalence == 0.0 and f.base_prevalence == 0.0:
                assert f.enrichment == 0.0
