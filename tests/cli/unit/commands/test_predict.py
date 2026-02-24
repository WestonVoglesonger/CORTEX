"""Tests for SE-5: Roofline prediction, instruction analysis, device detection."""
import argparse
import json
import pytest
from unittest.mock import patch, MagicMock

from cortex.utils.decomposition import (
    RooflineDecomposer, PredictionResult, ChainPrediction,
    save_prediction, load_prediction,
)
from cortex.utils.instruction_analyzer import (
    InstructionProfile, _classify_arm64, _classify_x86_64,
    _extract_function_instructions, count_dynamic_instructions,
)


# ---------------------------------------------------------------------------
# TestInstructionAnalyzer
# ---------------------------------------------------------------------------

class TestInstructionAnalyzer:
    """Tests for instruction analysis with mocked disassembly."""

    def test_classify_arm64_basic(self):
        """ARM64 instruction classification."""
        instructions = [
            "ldr x0, [x1]",
            "fadd s0, s1, s2",
            "fmul s3, s4, s5",
            "str s0, [x2]",
            "b.ne label",
            "ret",
        ]
        profile = _classify_arm64(instructions)

        assert profile.arithmetic_count == 2   # fadd, fmul
        assert profile.load_count == 1         # ldr
        assert profile.store_count == 1        # str
        assert profile.branch_count == 2       # b.ne, ret
        assert profile.arch == "aarch64"
        assert profile.total_instructions == 6

    def test_classify_arm64_simd(self):
        """ARM64 SIMD detection via v-register operands."""
        instructions = [
            "fmla v0.4s, v1.4s, v2.4s",
            "fadd v3.4s, v4.4s, v5.4s",
            "ld1 {v6.4s}, [x0]",
        ]
        profile = _classify_arm64(instructions)

        assert profile.simd_count == 2         # fmla, fadd with v-regs
        assert profile.arithmetic_count == 2   # fmla, fadd
        assert profile.load_count == 1         # ld1
        assert profile.simd_width == 4

    def test_classify_x86_64_basic(self):
        """x86_64 instruction classification."""
        instructions = [
            "addps %xmm0, %xmm1",
            "mulps %xmm2, %xmm3",
            "movaps (%rdi), %xmm4",
            "jne .L1",
            "ret",
        ]
        profile = _classify_x86_64(instructions)

        assert profile.arithmetic_count == 2   # addps, mulps
        assert profile.simd_count == 2         # both packed
        assert profile.branch_count == 2       # jne, ret
        assert profile.arch == "x86_64"

    def test_classify_empty_instructions(self):
        """Empty instruction list."""
        profile = _classify_arm64([])
        assert profile.total_instructions == 0
        assert profile.arithmetic_count == 0

    def test_extract_function_otool_format(self):
        """Extract function from macOS otool output."""
        disasm = """_cortex_init:
0000000000001000\tadr\tx0, #0
0000000000001004\tret
_cortex_process:
0000000000001010\tldr\tx0, [x1]
0000000000001014\tfadd\ts0, s1, s2
0000000000001018\tstr\ts0, [x2]
000000000000101c\tret
_cortex_cleanup:
0000000000001020\tret
"""
        instructions = _extract_function_instructions(disasm, "cortex_process")
        assert len(instructions) >= 3  # ldr, fadd, str (ret might be included)

    def test_extract_function_not_found(self):
        """Missing function returns empty list."""
        disasm = "_other_function:\n0000\tret\n"
        instructions = _extract_function_instructions(disasm, "cortex_process")
        assert instructions == []


# ---------------------------------------------------------------------------
# TestPredictCommand
# ---------------------------------------------------------------------------

class TestPredictCommand:
    """Tests for predict command parser and execution."""

    def test_parser_args(self):
        from cortex.commands.predict import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args([
            '--device', 'primitives/devices/m1.yaml',
            '--kernel', 'goertzel',
        ])
        assert args.device == 'primitives/devices/m1.yaml'
        assert args.kernel == 'goertzel'
        assert args.format == 'table'
        assert args.channels == 64
        assert args.window_length == 160

    def test_parser_chain_mode(self):
        from cortex.commands.predict import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args([
            '--chain', 'notch_iir,bandpass_fir,goertzel',
            '--format', 'json',
        ])
        assert args.chain == 'notch_iir,bandpass_fir,goertzel'
        assert args.format == 'json'

    def test_parser_output_flag(self):
        from cortex.commands.predict import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args(['-o', '/tmp/prediction.json'])
        assert args.output == '/tmp/prediction.json'

    def test_execute_device_not_found(self):
        from cortex.commands.predict import execute

        args = argparse.Namespace(
            device='nonexistent.yaml',
            kernel=None,
            chain=None,
            config=False,
            output=None,
            format='table',
            channels=64,
            window_length=160,
        )
        result = execute(args)
        assert result == 1

    def test_execute_auto_detect_fallback(self):
        """When no --device and auto-detect fails, should error."""
        from cortex.commands.predict import execute

        args = argparse.Namespace(
            device=None,
            kernel='goertzel',
            chain=None,
            config=False,
            output=None,
            format='table',
            channels=64,
            window_length=160,
        )
        with patch('cortex.commands.predict.resolve_device', return_value=None):
            result = execute(args)
            assert result == 1

    def test_predict_uses_spec_fallback(self):
        """Predict falls back to spec.yaml when objdump unavailable."""
        device = {
            'device': {
                'name': 'Test',
                'cpu_peak_gflops': 100.0,
                'memory_bandwidth_gb_s': 68.25,
            }
        }
        specs = {
            'goertzel': {
                'kernel': {'name': 'goertzel'},
                'computational': {
                    'flops_per_sample': 10,
                    'memory_loads_per_sample': 2,
                    'memory_stores_per_sample': 1,
                }
            }
        }
        decomposer = RooflineDecomposer(device, specs)

        with patch('cortex.utils.decomposition.analyze_kernel', return_value=None):
            result = decomposer.predict('goertzel')

        assert result is not None
        assert result.source == "spec.yaml"
        assert result.theoretical_peak_us > 0

    def test_predict_chain(self):
        """Chain prediction sums cumulative peak."""
        device = {
            'device': {
                'name': 'Test',
                'cpu_peak_gflops': 100.0,
                'memory_bandwidth_gb_s': 68.25,
            }
        }
        specs = {
            'a': {
                'kernel': {'name': 'a'},
                'computational': {'flops_per_sample': 100, 'memory_loads_per_sample': 2, 'memory_stores_per_sample': 1},
            },
            'b': {
                'kernel': {'name': 'b'},
                'computational': {'flops_per_sample': 200, 'memory_loads_per_sample': 2, 'memory_stores_per_sample': 1},
            },
        }
        decomposer = RooflineDecomposer(device, specs)

        with patch('cortex.utils.decomposition.analyze_kernel', return_value=None):
            chain = decomposer.predict_chain(['a', 'b'])

        assert chain is not None
        assert len(chain.stages) == 2
        assert chain.cumulative_peak_us == pytest.approx(
            chain.stages[0].theoretical_peak_us + chain.stages[1].theoretical_peak_us
        )


# ---------------------------------------------------------------------------
# TestResolveDevice (replaces TestDeviceDetect)
# ---------------------------------------------------------------------------

class TestResolveDevice:
    """Tests for YAML-based device resolution (replacing hardcoded lookup table)."""

    def test_resolve_by_yaml_path(self):
        """Explicit path loads YAML directly."""
        from cortex.utils.device import resolve_device
        spec = resolve_device("primitives/devices/m1.yaml")
        assert spec is not None
        assert spec["device"]["name"] == "Apple M1"
        assert spec["device"]["cpu_peak_gflops"] == 100.0

    def test_resolve_by_short_name(self):
        """Short name maps to primitives/devices/{name}.yaml."""
        from cortex.utils.device import resolve_device
        spec = resolve_device("m1")
        assert spec is not None
        assert spec["device"]["name"] == "Apple M1"

    def test_resolve_auto_match(self):
        """No arg → query OS CPU name → match against device YAMLs."""
        from cortex.utils.device import resolve_device
        with patch('cortex.utils.device._query_cpu_name', return_value="Apple M1"):
            spec = resolve_device()
        assert spec is not None
        assert "Apple M1" in spec["device"]["name"]

    def test_resolve_unknown_cpu_returns_none(self):
        """Unknown CPU name with no matching YAML returns None."""
        from cortex.utils.device import resolve_device
        with patch('cortex.utils.device._query_cpu_name', return_value="Unknown CPU 9000"):
            spec = resolve_device()
        assert spec is None

    def test_resolve_nonexistent_path_returns_none(self):
        """Non-existent YAML path returns None."""
        from cortex.utils.device import resolve_device
        spec = resolve_device("nonexistent.yaml")
        assert spec is None

    def test_resolve_short_name_nonexistent_returns_none(self):
        """Short name with no matching YAML file returns None."""
        from cortex.utils.device import resolve_device
        spec = resolve_device("nonexistent_device")
        assert spec is None


# ---------------------------------------------------------------------------
# TestValidateCapabilities
# ---------------------------------------------------------------------------

class TestValidateCapabilities:
    """Tests for runtime capability validation."""

    def test_returns_copy_not_mutating_original(self):
        """validate_capabilities returns a copy, not mutating the original."""
        from cortex.utils.device import validate_capabilities
        spec = {"device": {"name": "Test",
                           "pmu": {"instruction_count": True, "l1d_misses": True,
                                   "memory_stall_hierarchy": False, "backend_stall": False},
                           "os_noise": {"tracer": None},
                           "frequency": {"model": "fixed", "max_hz": 3e9, "per_sample": False}}}
        with patch('cortex.utils.device._probe_pmu',
                   return_value={"pmu_available": False, "cpu_freq_hz": 0}):
            validated = validate_capabilities(spec)
        # Original should be unchanged
        assert spec["device"]["name"] == "Test"
        assert validated["device"]["name"] == "Test"


# ---------------------------------------------------------------------------
# TestDynamicInstructionCount
# ---------------------------------------------------------------------------

class TestDynamicInstructionCount:
    """Tests for PMU-based dynamic instruction counting."""

    def test_valid_pmu_result(self):
        """Valid PMU JSON output returns dict with instruction_count and cpu_freq_hz."""
        pmu_json = '{"kernel": "bandpass_fir", "instruction_count": 12345, "cpu_freq_hz": 3228000000, "repeats": 3, "available": true}\n'

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = pmu_json

        with patch('cortex.utils.instruction_analyzer.Path.exists', return_value=True), \
             patch('cortex.utils.instruction_analyzer.find_kernel', return_value={'spec_uri': 'primitives/kernels/v1/bandpass_fir@f32', 'name': 'bandpass_fir'}), \
             patch('cortex.utils.instruction_analyzer.subprocess.run', return_value=mock_result):
            result = count_dynamic_instructions('bandpass_fir')

        assert result is not None
        assert result["instruction_count"] == 12345
        assert result["cpu_freq_hz"] == 3228000000

    def test_pmu_unavailable(self):
        """PMU available=false returns None."""
        pmu_json = '{"kernel": "bandpass_fir", "instruction_count": 0, "available": false, "error": "no permission"}\n'

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = pmu_json

        with patch('cortex.utils.instruction_analyzer.Path.exists', return_value=True), \
             patch('cortex.utils.instruction_analyzer.find_kernel', return_value={'spec_uri': 'primitives/kernels/v1/bandpass_fir@f32', 'name': 'bandpass_fir'}), \
             patch('cortex.utils.instruction_analyzer.subprocess.run', return_value=mock_result):
            count = count_dynamic_instructions('bandpass_fir')

        assert count is None

    def test_binary_not_found(self):
        """Missing cortex_inscount binary returns None."""
        with patch('cortex.utils.instruction_analyzer.Path.exists', return_value=False):
            count = count_dynamic_instructions('bandpass_fir')

        assert count is None

    def test_subprocess_timeout(self):
        """Subprocess timeout returns None."""
        import subprocess as sp

        with patch('cortex.utils.instruction_analyzer.Path.exists', return_value=True), \
             patch('cortex.utils.instruction_analyzer.find_kernel', return_value={'spec_uri': 'primitives/kernels/v1/bandpass_fir@f32', 'name': 'bandpass_fir'}), \
             patch('cortex.utils.instruction_analyzer.subprocess.run', side_effect=sp.TimeoutExpired(cmd='test', timeout=30)):
            count = count_dynamic_instructions('bandpass_fir')

        assert count is None

    def test_kernel_not_found(self):
        """Unknown kernel returns None."""
        with patch('cortex.utils.instruction_analyzer.Path.exists', return_value=True), \
             patch('cortex.utils.instruction_analyzer.find_kernel', return_value=None):
            count = count_dynamic_instructions('nonexistent')

        assert count is None

    def test_invalid_json(self):
        """Malformed JSON output returns None."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not json at all"

        with patch('cortex.utils.instruction_analyzer.Path.exists', return_value=True), \
             patch('cortex.utils.instruction_analyzer.find_kernel', return_value={'spec_uri': 'test', 'name': 'test'}), \
             patch('cortex.utils.instruction_analyzer.subprocess.run', return_value=mock_result):
            count = count_dynamic_instructions('test')

        assert count is None


# ---------------------------------------------------------------------------
# TestPredictWithPMU
# ---------------------------------------------------------------------------

class TestPredictWithPMU:
    """Tests for predict() with PMU integration."""

    def _make_device(self, cpu_gflops=100.0, mem_bw=68.25):
        return {
            'device': {
                'name': 'Test Device',
                'cpu_peak_gflops': cpu_gflops,
                'memory_bandwidth_gb_s': mem_bw,
            }
        }

    def _make_kernel_spec(self, flops=128, loads=2, stores=1):
        return {
            'kernel': {'name': 'test_kernel'},
            'computational': {
                'flops_per_sample': flops,
                'memory_loads_per_sample': loads,
                'memory_stores_per_sample': stores,
            }
        }

    def test_predict_uses_pmu_when_available(self):
        """When PMU returns a dict with count and freq, source should be 'pmu'."""
        device = self._make_device()
        spec = self._make_kernel_spec()
        decomposer = RooflineDecomposer(device, {'test_kernel': spec})

        pmu_result = {"instruction_count": 50000, "cpu_freq_hz": 3228000000}
        with patch('cortex.utils.decomposition.count_dynamic_instructions', return_value=pmu_result), \
             patch('cortex.utils.decomposition.analyze_kernel', return_value=None):
            result = decomposer.predict('test_kernel')

        assert result is not None
        assert result.source == "pmu"
        assert result.theoretical_compute_us > 0

    def test_predict_falls_back_to_spec(self):
        """When PMU returns None, source should be 'spec.yaml'."""
        device = self._make_device()
        spec = self._make_kernel_spec()
        decomposer = RooflineDecomposer(device, {'test_kernel': spec})

        with patch('cortex.utils.decomposition.count_dynamic_instructions', return_value=None), \
             patch('cortex.utils.decomposition.analyze_kernel', return_value=None):
            result = decomposer.predict('test_kernel')

        assert result is not None
        assert result.source == "spec.yaml"

    def test_predict_pmu_zero_count_falls_back(self):
        """PMU returning None (zero count) should fall back to spec.yaml."""
        device = self._make_device()
        spec = self._make_kernel_spec()
        decomposer = RooflineDecomposer(device, {'test_kernel': spec})

        # count_dynamic_instructions returns None when instruction_count <= 0
        with patch('cortex.utils.decomposition.count_dynamic_instructions', return_value=None), \
             patch('cortex.utils.decomposition.analyze_kernel', return_value=None):
            result = decomposer.predict('test_kernel')

        assert result is not None
        assert result.source == "spec.yaml"

    def test_predict_pmu_compute_time_calculation(self):
        """Verify PMU compute time: instructions / (cpu_freq_hz * IPC) * 1e6."""
        device = self._make_device(cpu_gflops=100.0)  # peak_gflops no longer used for PMU
        spec = self._make_kernel_spec(flops=1, loads=0, stores=0)
        decomposer = RooflineDecomposer(device, {'test_kernel': spec})

        # 1M instructions at 1 GHz, IPC=1.0 -> 1000.0 us
        pmu_result = {"instruction_count": 1_000_000, "cpu_freq_hz": 1_000_000_000}
        with patch('cortex.utils.decomposition.count_dynamic_instructions', return_value=pmu_result), \
             patch('cortex.utils.decomposition.analyze_kernel', return_value=None):
            result = decomposer.predict('test_kernel')

        assert result is not None
        assert result.source == "pmu"
        assert result.theoretical_compute_us == pytest.approx(1000.0, rel=1e-6)

    def test_predict_pmu_missing_freq_falls_back(self):
        """When PMU returns count but cpu_freq_hz=0, should fall back to spec.yaml."""
        device = self._make_device()
        spec = self._make_kernel_spec()
        decomposer = RooflineDecomposer(device, {'test_kernel': spec})

        pmu_result = {"instruction_count": 50000, "cpu_freq_hz": 0}
        with patch('cortex.utils.decomposition.count_dynamic_instructions', return_value=pmu_result), \
             patch('cortex.utils.decomposition.analyze_kernel', return_value=None):
            result = decomposer.predict('test_kernel')

        assert result is not None
        assert result.source == "spec.yaml"


# ---------------------------------------------------------------------------
# TestPredictionResultTier
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# TestPredictionResultPMUFields
# ---------------------------------------------------------------------------

class TestPredictionResultPMUFields:
    """Tests for instruction_count / probe_freq_hz on PredictionResult."""

    def test_prediction_result_stores_instruction_count(self):
        """PredictionResult accepts instruction_count and probe_freq_hz fields."""
        result = PredictionResult(
            kernel_name="goertzel",
            theoretical_compute_us=0.5,
            theoretical_memory_us=0.2,
            theoretical_io_us=0.0,
            theoretical_peak_us=0.5,
            bound="compute",
            operational_intensity=2.5,
            instruction_profile=None,
            source="pmu",
            instruction_count=50000,
            probe_freq_hz=3228000000,
        )
        assert result.instruction_count == 50000
        assert result.probe_freq_hz == 3228000000

    def test_prediction_result_pmu_fields_default_none(self):
        """Fields default to None when not provided."""
        result = PredictionResult(
            kernel_name="goertzel",
            theoretical_compute_us=0.5,
            theoretical_memory_us=0.2,
            theoretical_io_us=0.0,
            theoretical_peak_us=0.5,
            bound="compute",
            operational_intensity=2.5,
            instruction_profile=None,
            source="spec.yaml",
        )
        assert result.instruction_count is None
        assert result.probe_freq_hz is None


# ---------------------------------------------------------------------------
# TestSavePredictionPMUFields
# ---------------------------------------------------------------------------

class TestSavePredictionPMUFields:
    """Tests for PMU field persistence in prediction.json."""

    def _make_prediction(self, instruction_count=None, probe_freq_hz=None):
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
            instruction_count=instruction_count,
            probe_freq_hz=probe_freq_hz,
        )

    def test_save_prediction_includes_pmu_data(self, tmp_path):
        """When instruction_count is set, prediction.json contains PMU fields."""
        pred = self._make_prediction(instruction_count=50000, probe_freq_hz=3228000000)
        out = str(tmp_path / "prediction.json")
        device_spec = {"device": {"name": "Test"}}
        save_prediction([pred], device_spec, {"window_length": 160, "channels": 64}, out)

        import json
        with open(out) as f:
            data = json.load(f)
        entry = data["predictions"][0]
        assert entry["instruction_count"] == 50000
        assert entry["probe_freq_hz"] == 3228000000

    def test_save_prediction_omits_pmu_when_none(self, tmp_path):
        """When fields are None, prediction.json omits them."""
        pred = self._make_prediction()
        out = str(tmp_path / "prediction.json")
        device_spec = {"device": {"name": "Test"}}
        save_prediction([pred], device_spec, {"window_length": 160, "channels": 64}, out)

        import json
        with open(out) as f:
            data = json.load(f)
        entry = data["predictions"][0]
        assert "instruction_count" not in entry
        assert "probe_freq_hz" not in entry

    def test_load_prediction_roundtrip_pmu(self, tmp_path):
        """Save then load preserves instruction_count/probe_freq_hz."""
        pred = self._make_prediction(instruction_count=12345, probe_freq_hz=1800000000)
        out = str(tmp_path / "prediction.json")
        device_spec = {"device": {"name": "Test"}}
        save_prediction([pred], device_spec, {"window_length": 160, "channels": 64}, out)

        data = load_prediction(out)
        entry = data["predictions"][0]
        assert entry["instruction_count"] == 12345
        assert entry["probe_freq_hz"] == 1800000000


# ---------------------------------------------------------------------------
# TestPredictStoresPMUInResult
# ---------------------------------------------------------------------------

class TestPredictStoresPMUInResult:
    """Tests that predict() wires PMU values onto PredictionResult."""

    def _make_device(self):
        return {
            'device': {
                'name': 'Test Device',
                'cpu_peak_gflops': 100.0,
                'memory_bandwidth_gb_s': 68.25,
            }
        }

    def _make_kernel_spec(self):
        return {
            'kernel': {'name': 'test_kernel'},
            'computational': {
                'flops_per_sample': 128,
                'memory_loads_per_sample': 2,
                'memory_stores_per_sample': 1,
            }
        }

    def test_predict_pmu_result_has_instruction_count(self):
        """When PMU succeeds, result.instruction_count matches PMU output."""
        device = self._make_device()
        spec = self._make_kernel_spec()
        decomposer = RooflineDecomposer(device, {'test_kernel': spec})

        pmu_result = {"instruction_count": 50000, "cpu_freq_hz": 3228000000}
        with patch('cortex.utils.decomposition.count_dynamic_instructions', return_value=pmu_result), \
             patch('cortex.utils.decomposition.analyze_kernel', return_value=None):
            result = decomposer.predict('test_kernel')

        assert result is not None
        assert result.instruction_count == 50000
        assert result.probe_freq_hz == 3228000000

    def test_predict_spec_fallback_no_instruction_count(self):
        """When PMU unavailable, result.instruction_count is None."""
        device = self._make_device()
        spec = self._make_kernel_spec()
        decomposer = RooflineDecomposer(device, {'test_kernel': spec})

        with patch('cortex.utils.decomposition.count_dynamic_instructions', return_value=None), \
             patch('cortex.utils.decomposition.analyze_kernel', return_value=None):
            result = decomposer.predict('test_kernel')

        assert result is not None
        assert result.instruction_count is None
        assert result.probe_freq_hz is None
