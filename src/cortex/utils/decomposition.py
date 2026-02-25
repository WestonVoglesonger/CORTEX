"""Roofline-based latency prediction and characterization (SE-5).

Provides:
1. Predict: static pre-benchmark prediction using instruction analysis
2. Characterize: post-hoc characterization with distribution landmarks + provenance
3. Tail-latency attribution: attributes tail latency to platform vs algorithmic causes
"""
import json
import logging
import yaml
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, field, asdict

from cortex.utils.instruction_analyzer import (
    InstructionProfile, analyze_kernel, count_dynamic_instructions,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tail-latency attribution dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TailFactor:
    """A single platform factor contributing to tail latency."""
    name: str              # "cpu_freq", "osnoise", "backend_stalls"
    tail_prevalence: float   # fraction of tail windows with anomaly (0.0-1.0)
    base_prevalence: float   # fraction of non-tail windows with anomaly (0.0-1.0)
    enrichment: float        # tail_prevalence / base_prevalence (inf if base is 0)
    threshold: float         # anomaly threshold (MHz for cpu_freq, ns for osnoise, % for stalls)
    direction: str           # "low" or "high"


@dataclass
class TailAttribution:
    """Result of tail-latency attribution analysis."""
    kernel_name: str
    tail_percentile: int
    tail_factor: float           # p99 / p50
    p50_us: float
    p99_us: float
    dominant_cause: str          # "platform" | "algorithmic" | "mixed" | "insufficient data" | "insufficient tail windows for attribution"
    confidence: str              # "high" (freq + osnoise/PMU), "medium" (freq only), "low" (no freq data)
    n_tail_windows: int
    n_total_windows: int
    platform_explained_pct: float
    algorithmic_pct: float
    factors: List['TailFactor']
    tail_windows: object         # pd.DataFrame of all tail windows with platform anomaly flags


# ---------------------------------------------------------------------------
# Prediction dataclasses
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
    instruction_count: Optional[int] = None      # retired instructions (from PMU)
    probe_freq_hz: Optional[int] = None          # CPU freq at probe time (from PMU)


@dataclass
class ChainPrediction:
    """Prediction for a chained kernel pipeline."""
    stages: List[PredictionResult]
    cumulative_peak_us: float
    stage_names: List[str]


# ---------------------------------------------------------------------------
# Post-hoc characterization
# ---------------------------------------------------------------------------

@dataclass
class CharacterizationResult:
    """Post-hoc characterization of a kernel's latency distribution.

    Distribution landmarks (best_us, typical_us, tail_us) use the best
    available measurement source:
    - device_latency_us (kernel-only, from device_tstart/tend) when available
    - outer_latency_us (harness-inclusive, from start_ts/end_ts) as fallback

    Provenance field distinguishes: measured/timing/device vs measured/timing.

    Note on fits_in_l1: total addressable bytes, not active working set.
    Streaming kernels may fit in L1 despite large total.
    """
    kernel_name: str

    # Roofline classification
    bound: str                       # "compute" or "memory"
    operational_intensity: float

    # Working set
    working_set_bytes: int
    fits_in_l1: Optional[bool]

    # Floor estimates
    roofline_floor_us: float         # max(compute_bound, memory_bound)
    roofline_compute_us: float
    roofline_memory_us: float
    osaca_floor_us: Optional[float]  # None until OSACA integrated

    # Distribution landmarks (best available: device > outer)
    best_us: float                   # p5
    typical_us: float                # p50
    tail_us: float                   # p99

    # Distribution shape
    best_to_typical_gap_us: float    # p50 - p5
    tail_risk_us: float              # p99 - p50

    # Noop cross-validation (informational, not load-bearing)
    noop_p50_us: Optional[float]     # None if noop absent

    # Instruction profile from disassembly
    instruction_profile: Optional[InstructionProfile] = None

    # PMU enrichment (None if no PMU data)
    ipc: Optional[float] = None
    effective_freq_ghz: Optional[float] = None    # median of per-window cycles / device_wall_s
    frequency_tax_pct: Optional[float] = None     # (1 - effective_freq / max_freq) * 100

    # PMU stall decomposition (None if no backend stall data)
    backend_stall_pct: Optional[float] = None     # stall_cycles / total_cycles * 100
    compute_time_us: Optional[float] = None       # typical_us * (1 - stall_pct)
    memory_stall_time_us: Optional[float] = None  # typical_us * stall_pct


    n_windows: int = 0

    # Provenance: maps field name -> source string
    provenance: dict = field(default_factory=dict)
    # Unavailable: maps field name -> reason string
    unavailable: dict = field(default_factory=dict)


def characterize_kernel(
    kernel_name: str,
    outer_latencies_us: list,
    device_latencies_us: Optional[list],
    device_spec: dict,
    kernel_specs: dict,
    window_length: int = 160,
    channels: int = 64,
    dtype_bytes: int = 4,
    noop_latencies_us: Optional[list] = None,
    per_window_cycle_counts: Optional[list] = None,
    per_window_instruction_counts: Optional[list] = None,
    per_window_backend_stall_counts: Optional[list] = None,
) -> Optional[CharacterizationResult]:
    """Post-hoc characterization of a kernel's latency distribution.

    Returns a CharacterizationResult with distribution landmarks, roofline
    classification, and optional PMU enrichment. Returns None if kernel
    not found in specs.
    """
    import numpy as np

    spec = kernel_specs.get(kernel_name)
    if spec is None:
        return None
    comp = spec.get('computational')
    if comp is None:
        return None

    dev = device_spec.get('device', device_spec)
    provenance = {}
    unavailable = {}

    # --- 1. Roofline floor ---
    peak_gflops = dev.get('cpu_peak_gflops', dev.get('peak_gflops', 1.0))
    mem_bw_gb_s = dev.get('memory_bandwidth_gb_s', 1.0)

    flops_per_sample = comp.get('flops_per_sample', 0)
    loads_per_sample = comp.get('memory_loads_per_sample', 0)
    stores_per_sample = comp.get('memory_stores_per_sample', 0)

    total_samples = window_length * channels
    total_flops = flops_per_sample * total_samples
    total_bytes = (loads_per_sample + stores_per_sample) * total_samples * dtype_bytes

    oi = total_flops / total_bytes if total_bytes > 0 else 0.0
    compute_s = total_flops / (peak_gflops * 1e9) if peak_gflops > 0 and total_flops > 0 else 0.0
    memory_s = total_bytes / (mem_bw_gb_s * 1e9) if mem_bw_gb_s > 0 and total_bytes > 0 else 0.0
    roofline_compute_us = compute_s * 1e6
    roofline_memory_us = memory_s * 1e6
    roofline_floor_us = max(roofline_compute_us, roofline_memory_us)
    bound = "compute" if roofline_compute_us >= roofline_memory_us else "memory"
    provenance["roofline_floor_us"] = "estimated/roofline"
    provenance["bound"] = "estimated/roofline"

    # --- 2. Working set ---
    working_set_bytes = (loads_per_sample + stores_per_sample) * window_length * channels * dtype_bytes
    l1_kb = dev.get('l1_cache_kb')
    fits_in_l1 = working_set_bytes <= l1_kb * 1024 if l1_kb is not None else None
    provenance["working_set_bytes"] = "estimated/static"

    # --- 3. Distribution landmarks ---
    if device_latencies_us is not None and len(device_latencies_us) > 0:
        lat_arr = np.array(device_latencies_us, dtype=float)
        timing_prov = "measured/timing/device"
    else:
        lat_arr = np.array(outer_latencies_us, dtype=float)
        timing_prov = "measured/timing"

    if len(lat_arr) == 0:
        logger.warning("No latency samples for kernel %s, skipping", kernel_name)
        return None

    best = float(np.percentile(lat_arr, 5))
    typical = float(np.percentile(lat_arr, 50))
    tail = float(np.percentile(lat_arr, 99))
    best_to_typical_gap = max(0.0, typical - best)
    tail_risk = max(0.0, tail - typical)

    provenance["best_us"] = timing_prov
    provenance["typical_us"] = timing_prov
    provenance["tail_us"] = timing_prov

    n_windows = len(lat_arr)

    # --- 4. Harness overhead check (logged, not stored) ---
    if device_latencies_us is not None and len(device_latencies_us) > 0:
        outer_arr = np.array(outer_latencies_us, dtype=float)
        device_arr = np.array(device_latencies_us, dtype=float)
        min_len = min(len(outer_arr), len(device_arr))
        overhead = outer_arr[:min_len] - device_arr[:min_len]
        overhead_p50 = float(np.median(overhead))
        median_outer = float(np.median(outer_arr[:min_len]))
        pct = (overhead_p50 / median_outer * 100) if median_outer > 0 else 0.0
        logger.info("Harness overhead: %.1f us (%.1f%%)", overhead_p50, pct)

    # --- 5. Noop cross-validation ---
    noop_p50 = None
    if noop_latencies_us is not None and len(noop_latencies_us) > 0:
        noop_p50 = float(np.median(noop_latencies_us))
        provenance["noop_p50_us"] = "measured/timing/noop"

    # --- 6. Instruction profile ---
    profile = analyze_kernel(kernel_name)
    if profile is not None:
        provenance["instruction_profile"] = "estimated/static/disassembly"

    # --- 7. OSACA stub ---
    osaca_floor_us = None
    unavailable["osaca_floor_us"] = "OSACA not integrated"

    # --- 8. PMU enrichment ---
    ipc = None
    effective_freq_ghz = None
    frequency_tax_pct = None

    has_pmu = (per_window_cycle_counts is not None
               and per_window_instruction_counts is not None
               and len(per_window_cycle_counts) > 0
               and len(per_window_instruction_counts) > 0)

    if has_pmu:
        cycles = np.array(per_window_cycle_counts, dtype=float)
        insns = np.array(per_window_instruction_counts, dtype=float)

        # IPC: median of per-window insn/cycles (filter zeros)
        valid = cycles > 0
        if valid.any():
            per_window_ipc = insns[valid] / cycles[valid]
            ipc = float(np.median(per_window_ipc))
            provenance["ipc"] = "measured/PMU"

        # Effective freq + frequency tax
        # PMU counters are measured around kernel process() in the adapter,
        # so pair with device_latencies_us (device_tstart/device_tend).
        if device_latencies_us is not None and len(device_latencies_us) > 0:
            device_wall_s = np.array(device_latencies_us, dtype=float) * 1e-6
        else:
            device_wall_s = np.array(outer_latencies_us, dtype=float) * 1e-6
        min_len = min(len(cycles), len(device_wall_s))
        c = cycles[:min_len]
        w = device_wall_s[:min_len]
        valid_freq = (c > 0) & (w > 0)
        if valid_freq.any():
            per_window_freq = c[valid_freq] / w[valid_freq]
            effective_freq_hz = float(np.median(per_window_freq))
            effective_freq_ghz = effective_freq_hz / 1e9
            provenance["effective_freq_ghz"] = "measured/PMU+timing"

            max_freq_hz = dev.get('frequency', {}).get('max_hz', 0)
            if max_freq_hz > 0:
                frequency_tax_pct = (1 - effective_freq_hz / max_freq_hz) * 100
                provenance["frequency_tax_pct"] = "measured/PMU+timing"
            else:
                unavailable["frequency_tax_pct"] = "no max_hz in device spec"
        else:
            unavailable["effective_freq_ghz"] = "no valid cycle/wall-time pairs"
            unavailable["frequency_tax_pct"] = "no valid cycle/wall-time pairs"
    else:
        unavailable["ipc"] = "no PMU data"
        unavailable["effective_freq_ghz"] = "no PMU data"
        unavailable["frequency_tax_pct"] = "no PMU data"

    # --- 9. Backend stall decomposition ---
    backend_stall_pct = None
    compute_time_us = None
    memory_stall_time_us = None

    has_stalls = (has_pmu
                  and per_window_backend_stall_counts is not None
                  and len(per_window_backend_stall_counts) > 0)

    if has_stalls:
        stalls = np.array(per_window_backend_stall_counts, dtype=float)
        min_len = min(len(cycles), len(stalls))
        c = cycles[:min_len]
        s = stalls[:min_len]
        valid_stall = c > 0
        if valid_stall.any():
            per_window_stall_pct = s[valid_stall] / c[valid_stall]
            median_stall_pct = float(np.median(per_window_stall_pct))
            backend_stall_pct = median_stall_pct * 100
            compute_time_us = typical * (1 - median_stall_pct)
            memory_stall_time_us = typical * median_stall_pct
            provenance["backend_stall_pct"] = "measured/PMU"
            provenance["compute_time_us"] = "measured/PMU+timing"
            provenance["memory_stall_time_us"] = "measured/PMU+timing"
        else:
            unavailable["backend_stall_pct"] = "no valid cycle counts"
    elif has_pmu:
        unavailable["backend_stall_pct"] = "no backend stall data"
    else:
        unavailable["backend_stall_pct"] = "no PMU data"

    return CharacterizationResult(
        kernel_name=kernel_name,
        bound=bound,
        operational_intensity=oi,
        working_set_bytes=working_set_bytes,
        fits_in_l1=fits_in_l1,
        roofline_floor_us=roofline_floor_us,
        roofline_compute_us=roofline_compute_us,
        roofline_memory_us=roofline_memory_us,
        osaca_floor_us=osaca_floor_us,
        best_us=best,
        typical_us=typical,
        tail_us=tail,
        best_to_typical_gap_us=best_to_typical_gap,
        tail_risk_us=tail_risk,
        noop_p50_us=noop_p50,
        instruction_profile=profile,
        ipc=ipc,
        effective_freq_ghz=effective_freq_ghz,
        frequency_tax_pct=frequency_tax_pct,
        backend_stall_pct=backend_stall_pct,
        compute_time_us=compute_time_us,
        memory_stall_time_us=memory_stall_time_us,
        n_windows=n_windows,
        provenance=provenance,
        unavailable=unavailable,
    )


def _compute_enrichment(tail_prev, base_prev):
    """Compute enrichment ratio with division-by-zero guard."""
    if base_prev > 0:
        return tail_prev / base_prev
    elif tail_prev > 0:
        return float('inf')
    else:
        return 0.0


def _detect_anomaly(kdf, is_tail, col_name, anomaly_col, factor_name,
                    percentile, direction, threshold_scale=1.0):
    """Tag anomaly column on kdf, compute prevalence/enrichment.

    Returns (TailFactor, anomaly_col_name) or (None, None) if not applicable.
    """
    import numpy as np

    values = kdf[col_name].values
    nonzero = values[values > 0] if direction == "low" else values
    if len(nonzero) == 0:
        return None, None

    threshold = float(np.percentile(nonzero, percentile))
    if threshold <= 0:
        return None, None

    if direction == "low":
        kdf[anomaly_col] = kdf[col_name] < threshold
    else:
        kdf[anomaly_col] = kdf[col_name] > threshold

    tail_prev = kdf.loc[is_tail, anomaly_col].mean()
    base_prev = kdf.loc[~is_tail, anomaly_col].mean()
    enrichment = _compute_enrichment(tail_prev, base_prev)

    factor = TailFactor(
        name=factor_name, tail_prevalence=tail_prev,
        base_prevalence=base_prev, enrichment=enrichment,
        threshold=threshold * threshold_scale, direction=direction,
    )
    return factor, anomaly_col


def attribute_tail_latency(df, kernel_name, tail_percentile=95, device_spec=None):
    """Attribute tail latency to platform vs algorithmic causes.

    Analyzes per-window telemetry to determine whether tail latency is caused
    by platform factors (CPU frequency drops, OS noise, backend stalls) or
    algorithmic variance. Uses anomaly-tagging with base-rate comparison.

    Args:
        df: Telemetry DataFrame with per-window records. Required columns:
            'plugin', and one of 'device_latency_us' or 'latency_us'.
            Optional: 'warmup', 'window_failed', 'cpu_freq_mhz',
            'osnoise_total_ns', 'pmu_cycle_count', 'pmu_backend_stall_cycles'.
        kernel_name: Name of the kernel to analyze.
        tail_percentile: Percentile threshold for tail windows (default: 95).
        device_spec: Device specification dict (unused currently, reserved).

    Returns:
        TailAttribution dataclass with headline verdict, factor table,
        and annotated tail windows DataFrame.
    """
    import numpy as np
    import pandas as pd

    MIN_TAIL_WINDOWS = 10
    PLATFORM_DOMINATED_THRESHOLD = 0.70
    ALGORITHMIC_DOMINATED_THRESHOLD = 0.30

    def _empty_result(cause="insufficient data"):
        return TailAttribution(
            kernel_name=kernel_name, tail_percentile=tail_percentile,
            tail_factor=0.0, p50_us=0.0, p99_us=0.0,
            dominant_cause=cause, confidence="low",
            n_tail_windows=0, n_total_windows=0,
            platform_explained_pct=0.0, algorithmic_pct=0.0,
            factors=[], tail_windows=pd.DataFrame(),
        )

    # --- 1. Validate required columns and filter ---
    if 'plugin' not in df.columns:
        logger.warning("attribute_tail_latency: DataFrame missing 'plugin' column")
        return _empty_result()

    has_latency = 'latency_us' in df.columns
    has_device_latency = 'device_latency_us' in df.columns
    if not has_latency and not has_device_latency:
        logger.warning("attribute_tail_latency: DataFrame missing latency columns")
        return _empty_result()

    mask = df['plugin'] == kernel_name
    if 'warmup' in df.columns:
        mask = mask & (df['warmup'] == 0)
    if 'window_failed' in df.columns:
        mask = mask & (df['window_failed'] == 0)
    kdf = df[mask].copy()

    if kdf.empty:
        logger.warning("attribute_tail_latency: no valid windows for kernel %s", kernel_name)
        return _empty_result()

    # --- 2. Compute latency column ---
    if has_device_latency and (kdf['device_latency_us'] > 0).any():
        kdf['_latency'] = kdf['device_latency_us']
    else:
        kdf['_latency'] = kdf['latency_us']

    # Filter NaN latencies
    nan_mask = kdf['_latency'].isna()
    if nan_mask.any():
        n_nan = int(nan_mask.sum())
        logger.warning(
            "attribute_tail_latency: %d NaN latency values for kernel %s, filtering",
            n_nan, kernel_name,
        )
        kdf = kdf[~nan_mask].copy()
        if kdf.empty:
            return _empty_result()

    # --- 3. Distribution landmarks ---
    lat = kdf['_latency'].values
    p50 = float(np.percentile(lat, 50))
    p_tail = float(np.percentile(lat, tail_percentile))
    p99 = float(np.percentile(lat, 99))
    tail_factor = p99 / p50 if p50 > 0 else float('inf')

    # --- 4. Split into tail and non-tail ---
    # is_tail is index-aligned with kdf; no rows are added/removed after this point
    is_tail = kdf['_latency'] > p_tail
    n_tail = int(is_tail.sum())
    n_total = len(kdf)

    # --- 5. Minimum sample check ---
    if n_tail < MIN_TAIL_WINDOWS:
        logger.info(
            "attribute_tail_latency: only %d tail windows for kernel %s "
            "(need %d), skipping factor analysis",
            n_tail, kernel_name, MIN_TAIL_WINDOWS,
        )
        return TailAttribution(
            kernel_name=kernel_name, tail_percentile=tail_percentile,
            tail_factor=tail_factor, p50_us=p50, p99_us=p99,
            dominant_cause="insufficient tail windows for attribution",
            confidence="low",
            n_tail_windows=n_tail, n_total_windows=n_total,
            platform_explained_pct=0.0, algorithmic_pct=0.0,
            factors=[], tail_windows=kdf[is_tail].copy(),
        )

    # --- 6. Anomaly detection per platform variable ---
    factors = []
    anomaly_cols = []

    # cpu_freq_mhz: anomaly if < P10(all_freq) — direction "low"
    if 'cpu_freq_mhz' in kdf.columns and (kdf['cpu_freq_mhz'] > 0).any():
        factor, col = _detect_anomaly(
            kdf, is_tail, 'cpu_freq_mhz', '_anomaly_cpu_freq',
            'cpu_freq', percentile=10, direction='low')
        if factor:
            factors.append(factor)
            anomaly_cols.append(col)

    # osnoise_total_ns: anomaly if > P90(all_osnoise) — direction "high"
    if 'osnoise_total_ns' in kdf.columns and (kdf['osnoise_total_ns'] > 0).any():
        factor, col = _detect_anomaly(
            kdf, is_tail, 'osnoise_total_ns', '_anomaly_osnoise',
            'osnoise', percentile=90, direction='high')
        if factor:
            factors.append(factor)
            anomaly_cols.append(col)

    # pmu_backend_stall_cycles as % of pmu_cycle_count: anomaly if > P90 — direction "high"
    if ('pmu_backend_stall_cycles' in kdf.columns
            and 'pmu_cycle_count' in kdf.columns
            and (kdf['pmu_cycle_count'] > 0).any()):
        valid_pmu = kdf['pmu_cycle_count'] > 0
        kdf.loc[valid_pmu, '_stall_pct'] = (
            kdf.loc[valid_pmu, 'pmu_backend_stall_cycles']
            / kdf.loc[valid_pmu, 'pmu_cycle_count']
        )
        kdf.loc[~valid_pmu, '_stall_pct'] = 0.0
        if (kdf['_stall_pct'] > 0).any():
            factor, col = _detect_anomaly(
                kdf, is_tail, '_stall_pct', '_anomaly_stalls',
                'backend_stalls', percentile=90, direction='high',
                threshold_scale=100)  # store as percentage
            if factor:
                factors.append(factor)
                anomaly_cols.append(col)

    # --- 7. Classify tail windows ---
    tail_df = kdf[is_tail].copy()
    if anomaly_cols:
        tail_df['_any_platform_anomaly'] = tail_df[anomaly_cols].any(axis=1)
        n_platform = int(tail_df['_any_platform_anomaly'].sum())
    else:
        tail_df['_any_platform_anomaly'] = False
        n_platform = 0
        if not factors:
            logger.info(
                "attribute_tail_latency: no platform data available for kernel %s, "
                "confidence=low", kernel_name,
            )

    # --- 8. Compute percentages and verdict ---
    n_algorithmic = n_tail - n_platform
    platform_explained_pct = n_platform / n_tail if n_tail > 0 else 0.0
    algorithmic_pct = n_algorithmic / n_tail if n_tail > 0 else 0.0

    if platform_explained_pct >= PLATFORM_DOMINATED_THRESHOLD:
        dominant_cause = "platform"
    elif platform_explained_pct <= ALGORITHMIC_DOMINATED_THRESHOLD:
        dominant_cause = "algorithmic"
    else:
        dominant_cause = "mixed"

    # --- 9. Confidence ---
    has_freq = any(f.name == "cpu_freq" for f in factors)
    has_osnoise = any(f.name == "osnoise" for f in factors)
    has_pmu = any(f.name == "backend_stalls" for f in factors)
    if has_freq and (has_osnoise or has_pmu):
        confidence = "high"
    elif has_freq:
        confidence = "medium"
    else:
        confidence = "low"

    return TailAttribution(
        kernel_name=kernel_name,
        tail_percentile=tail_percentile,
        tail_factor=tail_factor,
        p50_us=p50,
        p99_us=p99,
        dominant_cause=dominant_cause,
        confidence=confidence,
        n_tail_windows=n_tail,
        n_total_windows=n_total,
        platform_explained_pct=platform_explained_pct,
        algorithmic_pct=algorithmic_pct,
        factors=factors,
        tail_windows=tail_df,
    )


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
        self.kernel_specs = kernel_specs

    # -------------------------------------------------------------------
    # Predict methods (pre-benchmark, static analysis)
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
            cycle_count = pmu_result.get("cycle_count", 0)
            if insn_count > 0 and cpu_freq_hz > 0:
                pmu_insn_count = insn_count
                pmu_freq_hz = cpu_freq_hz
                if cycle_count > 0:
                    compute_us = cycle_count / cpu_freq_hz * 1e6  # exact, no IPC
                else:
                    ipc = 1.0  # conservative lower bound
                    compute_us = insn_count / (cpu_freq_hz * ipc) * 1e6
                source = "pmu"
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
# Helpers
# ---------------------------------------------------------------------------

def load_device_spec(device_path: str) -> dict:
    """Load a device specification YAML file."""
    with open(device_path) as f:
        return yaml.safe_load(f)


def load_kernel_specs(kernels_dir: str = "primitives/kernels") -> Dict[str, dict]:
    """Load all kernel spec.yaml files and return dict keyed by kernel name.

    Computational annotations (flops_per_sample, etc.) are loaded from
    primitives/kernels/computational.yaml and merged into each spec,
    keeping immutable v1 spec.yaml files untouched.
    """
    specs = {}
    kernels_path = Path(kernels_dir)
    for spec_file in kernels_path.glob("v*/*/spec.yaml"):
        with open(spec_file) as f:
            spec = yaml.safe_load(f)
        kernel_section = spec.get('kernel', {})
        name = kernel_section.get('name', spec.get('name'))
        if name:
            specs[name] = spec

    # Merge computational annotations from the standalone file
    comp_file = kernels_path / "computational.yaml"
    if comp_file.exists():
        with open(comp_file) as f:
            comp_data = yaml.safe_load(f) or {}
        for name, comp in comp_data.items():
            if name in specs and isinstance(comp, dict):
                specs[name]['computational'] = comp

    return specs
