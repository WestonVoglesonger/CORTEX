"""Roofline-based latency decomposition and prediction (SE-5).

Provides three capabilities:
1. Decompose (legacy): break measured latency into compute/memory/overhead
2. Predict (new): static pre-benchmark prediction using instruction analysis
3. Attribute (new): fit predicted to measured with I/O, DVFS, scheduling breakdown
"""
import json
import yaml
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict

from cortex.utils.instruction_analyzer import (
    InstructionProfile, analyze_kernel, count_dynamic_instructions,
)


# ---------------------------------------------------------------------------
# Legacy dataclass (backward compatibility)
# ---------------------------------------------------------------------------

@dataclass
class DecompositionResult:
    """Result of latency decomposition for a single kernel."""
    kernel_name: str
    measured_latency_us: float
    theoretical_compute_us: float
    theoretical_memory_us: float
    theoretical_peak_us: float       # max(compute, memory)
    overhead_us: float               # measured - theoretical_peak
    compute_pct: float
    memory_pct: float
    overhead_pct: float
    bound: str                       # "compute", "memory", or "overhead"
    operational_intensity: float     # FLOPs / bytes
    total_flops: float
    total_bytes: float


# ---------------------------------------------------------------------------
# New prediction dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PredictionResult:
    """Static prediction for a single kernel (pre-benchmark)."""
    kernel_name: str
    theoretical_compute_us: float    # instruction_count / (freq * throughput)
    theoretical_memory_us: float     # (loads + stores) * dtype_bytes / bandwidth
    theoretical_io_us: float         # noop baseline (0 in predict, filled in attribute)
    theoretical_peak_us: float       # max(compute, memory) + io
    bound: str                       # "compute", "memory", or "io"
    operational_intensity: float
    instruction_profile: Optional[InstructionProfile]
    source: str                      # "objdump" or "spec.yaml"
    decomposition_tier: int = 0
    instruction_count: Optional[int] = None      # retired instructions (from PMU)
    probe_freq_hz: Optional[int] = None          # CPU freq at probe time (from PMU)


@dataclass
class ChainPrediction:
    """Prediction for a chained kernel pipeline."""
    stages: List[PredictionResult]
    cumulative_peak_us: float
    stage_names: List[str]


@dataclass
class AttributionResult:
    """Post-benchmark attribution breaking measured latency into components."""
    kernel_name: str
    predicted_peak_us: float
    measured_median_us: float
    io_overhead_us: float              # from noop baseline
    dvfs_overhead_us: Optional[float]  # from freq segmentation (None if no data)
    scheduling_overhead_us: float      # remaining residual
    nominal_freq_mhz: Optional[int]
    throttled_window_pct: float
    bound: str


@dataclass
class DistributionalAttribution:
    """Tier 1 distributional decomposition with per-window compute bound."""
    kernel_name: str
    tier: int
    # Measured
    measured_p50_us: float
    measured_p95_us: float
    measured_p99_us: float
    # Compute bound
    compute_p50_us: float
    compute_p95_us: float
    compute_p99_us: float
    # Residual (measured - compute)
    residual_p50_us: float
    residual_p95_us: float
    residual_p99_us: float
    # Noop baseline
    noop_p50_us: float
    noop_p95_us: float
    noop_p99_us: float
    # Net residual (residual - noop, quantile subtraction)
    net_residual_p50_us: float
    net_residual_p95_us: float
    net_residual_p99_us: float
    bound: str
    n_windows: int


# ---------------------------------------------------------------------------
# RooflineDecomposer (extended with predict methods)
# ---------------------------------------------------------------------------

class RooflineDecomposer:
    """Decomposes/predicts latency using the Roofline performance model.

    The Roofline model bounds achievable performance by two limits:
    1. Peak compute throughput (GFLOPS)
    2. Memory bandwidth x operational intensity

    Args:
        device_spec: Parsed device YAML dict
        kernel_specs: Dict mapping kernel_name -> parsed spec YAML dict
    """

    def __init__(self, device_spec: dict, kernel_specs: Dict[str, dict]):
        dev = device_spec.get('device', device_spec)
        self.device_name = dev.get('name', 'Unknown')
        self.peak_gflops = dev.get('cpu_peak_gflops', dev.get('peak_gflops', 1.0))
        self.memory_bw_gb_s = dev.get('memory_bandwidth_gb_s', 1.0)
        self.decomposition_tier = dev.get('decomposition_tier', 0)
        self.kernel_specs = kernel_specs

    # -------------------------------------------------------------------
    # Legacy decompose (backward compat)
    # -------------------------------------------------------------------

    def decompose(
        self,
        kernel_name: str,
        measured_latency_us: float,
        window_length: int = 160,
        channels: int = 64,
        dtype_bytes: int = 4
    ) -> Optional[DecompositionResult]:
        """Decompose measured latency for a kernel (legacy interface)."""
        spec = self.kernel_specs.get(kernel_name)
        if spec is None:
            return None

        comp = spec.get('computational')
        if comp is None:
            return None

        flops_per_sample = comp.get('flops_per_sample', 0)
        loads_per_sample = comp.get('memory_loads_per_sample', 0)
        stores_per_sample = comp.get('memory_stores_per_sample', 0)

        total_samples = window_length * channels
        total_flops = flops_per_sample * total_samples
        total_bytes = (loads_per_sample + stores_per_sample) * total_samples * dtype_bytes

        oi = total_flops / total_bytes if total_bytes > 0 else 0.0

        compute_s = total_flops / (self.peak_gflops * 1e9) if self.peak_gflops > 0 and total_flops > 0 else 0.0
        memory_s = total_bytes / (self.memory_bw_gb_s * 1e9) if self.memory_bw_gb_s > 0 and total_bytes > 0 else 0.0

        compute_us = compute_s * 1e6
        memory_us = memory_s * 1e6
        theoretical_peak_us = max(compute_us, memory_us)
        overhead_us = max(0.0, measured_latency_us - theoretical_peak_us)

        if measured_latency_us > 0:
            compute_pct = (compute_us / measured_latency_us) * 100.0
            memory_pct = (memory_us / measured_latency_us) * 100.0
            overhead_pct = (overhead_us / measured_latency_us) * 100.0
        else:
            compute_pct = memory_pct = overhead_pct = 0.0

        if theoretical_peak_us == 0:
            bound = "overhead"
        elif compute_us >= memory_us:
            bound = "compute"
        else:
            bound = "memory"

        if overhead_pct > 90.0:
            bound = "overhead"

        return DecompositionResult(
            kernel_name=kernel_name,
            measured_latency_us=measured_latency_us,
            theoretical_compute_us=compute_us,
            theoretical_memory_us=memory_us,
            theoretical_peak_us=theoretical_peak_us,
            overhead_us=overhead_us,
            compute_pct=compute_pct,
            memory_pct=memory_pct,
            overhead_pct=overhead_pct,
            bound=bound,
            operational_intensity=oi,
            total_flops=total_flops,
            total_bytes=total_bytes,
        )

    def decompose_all(
        self,
        latencies: Dict[str, float],
        window_length: int = 160,
        channels: int = 64,
        dtype_bytes: int = 4
    ) -> List[DecompositionResult]:
        """Decompose latency for all kernels with available specs (legacy)."""
        results = []
        for name, lat in latencies.items():
            result = self.decompose(name, lat, window_length, channels, dtype_bytes)
            if result is not None:
                results.append(result)
        return results

    # -------------------------------------------------------------------
    # New predict methods (pre-benchmark, static analysis)
    # -------------------------------------------------------------------

    def _compute_from_spec(
        self,
        kernel_name: str,
        window_length: int,
        channels: int,
        dtype_bytes: int,
    ) -> Optional[tuple]:
        """Compute theoretical times from spec.yaml annotations.

        Returns (compute_us, memory_us, oi, total_flops, total_bytes) or None.
        """
        spec = self.kernel_specs.get(kernel_name)
        if spec is None:
            return None
        comp = spec.get('computational')
        if comp is None:
            return None

        flops_per_sample = comp.get('flops_per_sample', 0)
        loads_per_sample = comp.get('memory_loads_per_sample', 0)
        stores_per_sample = comp.get('memory_stores_per_sample', 0)

        total_samples = window_length * channels
        total_flops = flops_per_sample * total_samples
        total_bytes = (loads_per_sample + stores_per_sample) * total_samples * dtype_bytes

        oi = total_flops / total_bytes if total_bytes > 0 else 0.0

        compute_s = total_flops / (self.peak_gflops * 1e9) if self.peak_gflops > 0 and total_flops > 0 else 0.0
        memory_s = total_bytes / (self.memory_bw_gb_s * 1e9) if self.memory_bw_gb_s > 0 and total_bytes > 0 else 0.0

        return (compute_s * 1e6, memory_s * 1e6, oi, total_flops, total_bytes)

    def predict(
        self,
        kernel_name: str,
        window_length: int = 160,
        channels: int = 64,
        dtype_bytes: int = 4,
    ) -> Optional[PredictionResult]:
        """Predict kernel latency before benchmarking.

        Attempts to use hardware PMU instruction counting first (exact retired
        instruction count from a real cortex_process() invocation). Falls back
        to spec.yaml per-sample annotations if PMU is unavailable.

        PMU model: compute_time = instruction_count / (cpu_freq_hz * IPC)
          - IPC=1.0 as conservative lower bound (actual IPC higher due to
            superscalar execution, making predictions pessimistic/safe)
          - cpu_freq_hz self-reported by cortex_inscount from OS (sysctl/sysfs)

        Memory time always comes from spec.yaml (PMU only gives instruction
        count, not memory traffic).

        Args:
            kernel_name: Name of the kernel
            window_length: Samples per window (W)
            channels: Number of channels (C)
            dtype_bytes: Bytes per element (4 for float32)

        Returns:
            PredictionResult or None if no data available.
        """
        spec_result = self._compute_from_spec(kernel_name, window_length, channels, dtype_bytes)
        if spec_result is None:
            return None

        _, memory_us, oi, _, _ = spec_result

        # Attach instruction profile as supplementary metadata (best-effort)
        profile = analyze_kernel(kernel_name)

        # Try hardware PMU instruction count first
        pmu_insn_count = None
        pmu_freq_hz = None
        pmu_result = count_dynamic_instructions(kernel_name, window_length, channels)
        if pmu_result is not None:
            insn_count = pmu_result["instruction_count"]
            cpu_freq_hz = pmu_result["cpu_freq_hz"]
            if insn_count > 0 and cpu_freq_hz > 0:
                ipc = 1.0  # conservative lower bound
                compute_us = insn_count / (cpu_freq_hz * ipc) * 1e6
                source = "pmu"
                pmu_insn_count = insn_count
                pmu_freq_hz = cpu_freq_hz
            else:
                # PMU available but freq unknown — fall back to spec
                compute_us, _, _, _, _ = spec_result
                source = "spec.yaml"
        else:
            compute_us, _, _, _, _ = spec_result
            source = "spec.yaml"

        theoretical_peak_us = max(compute_us, memory_us)

        if theoretical_peak_us == 0:
            bound = "io"
        elif compute_us >= memory_us:
            bound = "compute"
        else:
            bound = "memory"

        return PredictionResult(
            kernel_name=kernel_name,
            theoretical_compute_us=compute_us,
            theoretical_memory_us=memory_us,
            theoretical_io_us=0.0,  # filled during attribution
            theoretical_peak_us=theoretical_peak_us,
            bound=bound,
            operational_intensity=oi,
            instruction_profile=profile,
            source=source,
            decomposition_tier=self.decomposition_tier,
            instruction_count=pmu_insn_count,
            probe_freq_hz=pmu_freq_hz,
        )

    def predict_all(
        self,
        kernel_names: List[str],
        window_length: int = 160,
        channels: int = 64,
        dtype_bytes: int = 4,
    ) -> List[PredictionResult]:
        """Predict latency for multiple kernels."""
        results = []
        for name in kernel_names:
            result = self.predict(name, window_length, channels, dtype_bytes)
            if result is not None:
                results.append(result)
        return results

    def predict_chain(
        self,
        kernel_names: List[str],
        window_length: int = 160,
        channels: int = 64,
        dtype_bytes: int = 4,
    ) -> Optional[ChainPrediction]:
        """Predict cumulative latency for a kernel chain.

        Note: inter-kernel overhead is unknown at prediction time.
        """
        stages = self.predict_all(kernel_names, window_length, channels, dtype_bytes)
        if not stages:
            return None

        cumulative = sum(s.theoretical_peak_us for s in stages)
        return ChainPrediction(
            stages=stages,
            cumulative_peak_us=cumulative,
            stage_names=[s.kernel_name for s in stages],
        )


# ---------------------------------------------------------------------------
# Prediction I/O
# ---------------------------------------------------------------------------

def save_prediction(
    results: List[PredictionResult],
    device_spec: dict,
    params: dict,
    output_path: str,
) -> None:
    """Write prediction results to JSON for later attribution.

    Args:
        results: List of PredictionResult
        device_spec: Device specification dict
        params: Dict with window_length, channels, dtype_bytes
        output_path: Path to write prediction.json
    """
    dev = device_spec.get('device', device_spec)
    data = {
        "device": dev.get("name", "Unknown"),
        "decomposition_tier": dev.get("decomposition_tier", 0),
        "params": params,
        "predictions": [],
    }
    for r in results:
        entry = {
            "kernel_name": r.kernel_name,
            "theoretical_compute_us": round(r.theoretical_compute_us, 6),
            "theoretical_memory_us": round(r.theoretical_memory_us, 6),
            "theoretical_io_us": round(r.theoretical_io_us, 6),
            "theoretical_peak_us": round(r.theoretical_peak_us, 6),
            "bound": r.bound,
            "operational_intensity": round(r.operational_intensity, 6),
            "source": r.source,
            "decomposition_tier": r.decomposition_tier,
        }
        if r.instruction_count is not None:
            entry["instruction_count"] = r.instruction_count
        if r.probe_freq_hz is not None:
            entry["probe_freq_hz"] = r.probe_freq_hz
        if r.instruction_profile is not None:
            entry["instruction_profile"] = asdict(r.instruction_profile)
        data["predictions"].append(entry)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


def load_prediction(path: str) -> dict:
    """Load a prediction.json file."""
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Attribution (post-benchmark)
# ---------------------------------------------------------------------------

def attribute_latency(
    prediction: PredictionResult,
    measured_latencies_us: list,
    noop_baseline_us: float,
    cpu_freqs_mhz: Optional[list] = None,
) -> AttributionResult:
    """Attribute measured latency into compute / I/O / DVFS / scheduling.

    Args:
        prediction: Static prediction for this kernel
        measured_latencies_us: Per-window latency values
        noop_baseline_us: Median noop latency (I/O overhead)
        cpu_freqs_mhz: Per-window CPU frequency values (or None)

    Returns:
        AttributionResult with breakdown.
    """
    import numpy as np

    measured_arr = np.array(measured_latencies_us)
    measured_median = float(np.median(measured_arr))

    io_overhead = noop_baseline_us
    dvfs_overhead: Optional[float] = None
    nominal_freq: Optional[int] = None
    throttled_pct = 0.0

    # DVFS attribution (if frequency data available and non-zero)
    if cpu_freqs_mhz is not None:
        freq_arr = np.array(cpu_freqs_mhz)
        nonzero = freq_arr[freq_arr > 0]

        if len(nonzero) > 0:
            # Nominal frequency = mode (most common)
            from scipy import stats as sp_stats
            mode_result = sp_stats.mode(nonzero, keepdims=False)
            nominal_freq = int(mode_result.mode)

            # Partition windows: nominal vs throttled
            is_nominal = freq_arr == nominal_freq
            is_throttled = (freq_arr > 0) & (freq_arr < nominal_freq)

            throttled_count = int(is_throttled.sum())
            total_nonzero = int((freq_arr > 0).sum())
            throttled_pct = (throttled_count / total_nonzero * 100.0) if total_nonzero > 0 else 0.0

            if throttled_count > 0 and is_nominal.sum() > 0:
                nominal_median = float(np.median(measured_arr[is_nominal]))
                throttled_median = float(np.median(measured_arr[is_throttled]))
                dvfs_overhead = max(0.0, throttled_median - nominal_median)
            else:
                dvfs_overhead = 0.0
        # else: all zeros (macOS) — skip DVFS

    # Scheduling overhead = residual
    predicted_peak = prediction.theoretical_peak_us
    dvfs_val = dvfs_overhead if dvfs_overhead is not None else 0.0
    scheduling = max(0.0, measured_median - predicted_peak - io_overhead - dvfs_val)

    return AttributionResult(
        kernel_name=prediction.kernel_name,
        predicted_peak_us=predicted_peak,
        measured_median_us=measured_median,
        io_overhead_us=io_overhead,
        dvfs_overhead_us=dvfs_overhead,
        scheduling_overhead_us=scheduling,
        nominal_freq_mhz=nominal_freq,
        throttled_window_pct=throttled_pct,
        bound=prediction.bound,
    )


def attribute_latency_distributional(
    prediction: PredictionResult,
    measured_latencies_us: list,
    noop_latencies_us: list,
    cpu_freqs_mhz: Optional[list] = None,
) -> DistributionalAttribution:
    """Tier 1 distributional decomposition with per-window compute bound.

    For each sample L_i:
      C_i = instruction_count / (freq_i * IPC)
      residual_i = max(0, L_i - C_i)
    Output: percentiles for measured, compute, residual, noop, net_residual.

    Args:
        prediction: PredictionResult with instruction_count and probe_freq_hz
        measured_latencies_us: Per-window latency values
        noop_latencies_us: Per-window noop latency values (full distribution)
        cpu_freqs_mhz: Per-window CPU frequency in MHz (or None)
    """
    import numpy as np

    measured = np.array(measured_latencies_us, dtype=float)
    noop = np.array(noop_latencies_us, dtype=float)

    instruction_count = prediction.instruction_count
    probe_freq_hz = prediction.probe_freq_hz
    ipc = 1.0

    # Build per-window frequency array (Hz)
    if cpu_freqs_mhz is not None:
        freq_arr = np.array(cpu_freqs_mhz, dtype=float) * 1e6  # MHz → Hz
        # Replace zeros (macOS) with probe_freq_hz
        freq_arr[freq_arr == 0] = probe_freq_hz
    else:
        freq_arr = np.full(len(measured), probe_freq_hz, dtype=float)

    # Per-window compute bound: C_i = instruction_count / (freq_i * IPC) * 1e6 → us
    compute = instruction_count / (freq_arr * ipc) * 1e6

    # Residual clamped to non-negative
    residual = np.maximum(0.0, measured - compute)

    # Percentile extraction
    def pcts(arr):
        return (
            float(np.percentile(arr, 50)),
            float(np.percentile(arr, 95)),
            float(np.percentile(arr, 99)),
        )

    m50, m95, m99 = pcts(measured)
    c50, c95, c99 = pcts(compute)
    r50, r95, r99 = pcts(residual)
    n50, n95, n99 = pcts(noop)

    # Quantile subtraction: net_residual_pX = max(0, residual_pX - noop_pX)
    nr50 = max(0.0, r50 - n50)
    nr95 = max(0.0, r95 - n95)
    nr99 = max(0.0, r99 - n99)

    # Determine bound from compute vs residual dominance
    bound = prediction.bound

    return DistributionalAttribution(
        kernel_name=prediction.kernel_name,
        tier=prediction.decomposition_tier,
        measured_p50_us=m50,
        measured_p95_us=m95,
        measured_p99_us=m99,
        compute_p50_us=c50,
        compute_p95_us=c95,
        compute_p99_us=c99,
        residual_p50_us=r50,
        residual_p95_us=r95,
        residual_p99_us=r99,
        noop_p50_us=n50,
        noop_p95_us=n95,
        noop_p99_us=n99,
        net_residual_p50_us=nr50,
        net_residual_p95_us=nr95,
        net_residual_p99_us=nr99,
        bound=bound,
        n_windows=len(measured),
    )


# ---------------------------------------------------------------------------
# Legacy helpers
# ---------------------------------------------------------------------------

def load_device_spec(device_path: str) -> dict:
    """Load a device specification YAML file."""
    with open(device_path) as f:
        return yaml.safe_load(f)


def load_kernel_specs(kernels_dir: str = "primitives/kernels") -> Dict[str, dict]:
    """Load all kernel spec.yaml files and return dict keyed by kernel name."""
    specs = {}
    kernels_path = Path(kernels_dir)
    for spec_file in kernels_path.glob("v*/*/spec.yaml"):
        with open(spec_file) as f:
            spec = yaml.safe_load(f)
        kernel_section = spec.get('kernel', {})
        name = kernel_section.get('name', spec.get('name'))
        if name:
            specs[name] = spec
    return specs
