"""Latency characterization and tail-attribution (SE-5, SE-7).

Provides:
1. Characterize: post-hoc characterization with distribution landmarks,
   PMU enrichment, backend stall decomposition, and provenance tracking
2. Attribute: tail-latency attribution — platform vs algorithmic decomposition
"""
import logging
import platform
from itertools import combinations
from math import factorial

import yaml
from typing import Dict, Literal, Optional, List, Tuple
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import mannwhitneyu, ks_2samp

from cortex.utils.instruction_analyzer import (
    InstructionProfile, analyze_kernel,
)

logger = logging.getLogger(__name__)


def _pmu_unavailable_reason() -> str:
    """Platform-specific guidance for missing PMU data."""
    system = platform.system()
    if system == 'Darwin':
        return "no PMU data (run with sudo for instruction/cycle counts)"
    elif system == 'Linux':
        return "no PMU data (one-time fix: sudo setcap cap_perfmon=ep <adapter_path>)"
    return "no PMU data"


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
    """
    kernel_name: str

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

    # Tail attribution summary (Tier 1, always available when latency data present)
    tail_ratio: Optional[float] = None              # P99 / P50
    platform_tail_verdict: Optional[str] = None     # "platform-dominated" | "mixed" | "algorithmic"

    # Provenance: maps field name -> source string
    provenance: dict = field(default_factory=dict)
    # Unavailable: maps field name -> reason string
    unavailable: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tail-latency attribution (SE-7)
# ---------------------------------------------------------------------------

@dataclass
class CovariateComparison:
    """Comparison of a single covariate between tail and typical cohorts."""
    name: str
    tail_median: float
    typical_median: float
    mann_whitney_p: float
    significant: bool        # p < 0.05
    direction: Literal["higher_in_tail", "lower_in_tail", "no_difference"]


@dataclass
class TailAttribution:
    """Tail-latency attribution result from attribute_tail()."""
    kernel_name: str
    n_windows: int

    # Tier 1: Always present
    tail_ratio: float                          # P99 / P50
    noop_tail_ratio: Optional[float]           # noop P99 / P50
    normalized_ratio: Optional[float]          # kernel / noop
    verdict: Literal["platform-dominated", "mixed", "algorithmic"]
    tier: Literal[1, 2, 3]                     # Highest tier achieved

    # Tier 2: Cohort comparison (None if < Tier 2)
    tail_cohort_size: Optional[int] = None     # Windows > P95
    typical_cohort_size: Optional[int] = None  # Windows P25-P75

    # Per-covariate comparison: {covariate_name: CovariateComparison}
    covariate_comparisons: Dict[str, CovariateComparison] = field(default_factory=dict)

    # Tier 2: Frequency stratification (None if no freq data or < Tier 2)
    stable_freq_p99_us: Optional[float] = None
    unstable_freq_p99_us: Optional[float] = None
    freq_ks_pvalue: Optional[float] = None

    # Tier 3: Shapley variance decomposition (None if < Tier 3)
    model_r_squared: Optional[float] = None
    shapley_pct: Optional[Dict[str, float]] = None
    algorithmic_residual_pct: Optional[float] = None

    provenance: Dict[str, str] = field(default_factory=dict)


def _verdict_from_ratio(normalized_ratio: Optional[float], tail_ratio: float) -> str:
    """Determine platform/algorithmic verdict from normalized tail ratio.

    If noop data is available, uses the normalized ratio (kernel/noop).
    Otherwise falls back to raw tail_ratio with wider thresholds.
    """
    if normalized_ratio is not None:
        if normalized_ratio < 1.5:
            return "platform-dominated"
        elif normalized_ratio <= 3.0:
            return "mixed"
        else:
            return "algorithmic"
    # No noop baseline — use raw ratio with conservative thresholds
    if tail_ratio < 2.0:
        return "platform-dominated"
    elif tail_ratio <= 5.0:
        return "mixed"
    else:
        return "algorithmic"


def _shapley_r_squared(
    y: np.ndarray,
    X: np.ndarray,
    covariate_names: List[str],
) -> Tuple[dict, float]:
    """Compute Shapley value R² decomposition for k covariates (k >= 1).

    Fits all 2^k subset OLS models and averages each covariate's marginal
    R² contribution across all orderings. Returns
    ({name: percentage_of_total_variance}, R²_full), where the Shapley
    percentages sum to approximately R²_full * 100.
    Uses numpy.linalg.lstsq — no external dependencies beyond numpy.
    """
    n, k = X.shape
    if k != len(covariate_names):
        raise ValueError(
            f"X has {k} columns but {len(covariate_names)} covariate names provided"
        )

    def _r_squared(indices: tuple) -> float:
        if not indices:
            return 0.0
        Xs = np.column_stack([np.ones(n), X[:, list(indices)]])
        coeffs, _, _, _ = np.linalg.lstsq(Xs, y, rcond=None)
        y_pred = Xs @ coeffs
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        if ss_tot == 0:
            return 0.0
        return max(0.0, 1.0 - ss_res / ss_tot)

    # Cache R² for all subsets
    all_indices = list(range(k))
    r2_cache = {}
    for size in range(k + 1):
        for subset in combinations(all_indices, size):
            r2_cache[subset] = _r_squared(subset)

    # Full model R²
    full_r2 = r2_cache[tuple(all_indices)]

    # Shapley values: for each feature i, iterate over all subsets S
    # that don't contain i, compute weight, and add marginal contribution
    shapley = {name: 0.0 for name in covariate_names}
    for i, name in enumerate(covariate_names):
        others = [j for j in all_indices if j != i]
        for size in range(k):
            for subset in combinations(others, size):
                subset_with_i = tuple(sorted(subset + (i,)))
                marginal = r2_cache[subset_with_i] - r2_cache[subset]
                # Weight: |S|! * (k - |S| - 1)! / k!
                weight = (factorial(size) * factorial(k - size - 1)) / factorial(k)
                shapley[name] += weight * marginal

    # Normalize to percentages of full R²
    total_shapley = sum(shapley.values())
    if total_shapley > 0:
        # Normalize to percentages of total variance (not just explained variance)
        # so that shapley_pct + algorithmic_residual_pct sums to 100%.
        shapley_pct = {name: val * 100 for name, val in shapley.items()}
    else:
        shapley_pct = {name: 0.0 for name in covariate_names}

    return shapley_pct, full_r2


def attribute_tail(
    kernel_name: str,
    latencies_us: list,
    noop_latencies_us: Optional[list] = None,
    per_window_cpu_freq_mhz: Optional[list] = None,
    per_window_osnoise_ns: Optional[list] = None,
    per_window_cycle_counts: Optional[list] = None,
    per_window_backend_stall_counts: Optional[list] = None,
) -> Optional[TailAttribution]:
    """Attribute tail latency to platform vs algorithmic causes.

    Three-tier analysis:
    - Tier 1 (always): Diagnostic ratios (P99/P50, noop-normalized)
    - Tier 2 (≥200 windows + covariates): Cohort stratification + Mann-Whitney
    - Tier 3 (≥500 windows + ≥2 covariates): Shapley variance decomposition
    """
    lat = np.array(latencies_us, dtype=float)
    n_windows = len(lat)

    if n_windows == 0:
        logger.warning("No latency samples for kernel %s, cannot attribute tail", kernel_name)
        return None

    provenance = {}

    # --- Tier 1: Always available ---
    p50 = float(np.percentile(lat, 50))
    p99 = float(np.percentile(lat, 99))
    tail_ratio = p99 / p50 if p50 > 0 else 1.0
    provenance["tail_ratio"] = "measured/timing"

    noop_tail_ratio = None
    normalized_ratio = None
    if noop_latencies_us is not None and len(noop_latencies_us) > 0:
        noop_arr = np.array(noop_latencies_us, dtype=float)
        noop_p50 = float(np.percentile(noop_arr, 50))
        noop_p99 = float(np.percentile(noop_arr, 99))
        noop_tail_ratio = noop_p99 / noop_p50 if noop_p50 > 0 else 1.0
        normalized_ratio = tail_ratio / noop_tail_ratio if noop_tail_ratio > 0 else tail_ratio
        provenance["normalized_ratio"] = "measured/timing"

    verdict = _verdict_from_ratio(normalized_ratio, tail_ratio)
    tier = 1

    result = TailAttribution(
        kernel_name=kernel_name,
        n_windows=n_windows,
        tail_ratio=tail_ratio,
        noop_tail_ratio=noop_tail_ratio,
        normalized_ratio=normalized_ratio,
        verdict=verdict,
        tier=tier,
        provenance=provenance,
    )

    # --- Detect available covariates ---
    def _has_data(arr):
        return arr is not None and len(arr) > 0 and np.any(np.array(arr) != 0)

    covariates = {}  # name -> (array, transform_for_regression)
    if _has_data(per_window_cpu_freq_mhz):
        freq_arr = np.array(per_window_cpu_freq_mhz, dtype=float)[:n_windows]
        covariates["cpu_freq_mhz"] = freq_arr
    if _has_data(per_window_osnoise_ns):
        noise_arr = np.array(per_window_osnoise_ns, dtype=float)[:n_windows]
        covariates["osnoise_total_ns"] = noise_arr
    if (_has_data(per_window_backend_stall_counts)
            and _has_data(per_window_cycle_counts)):
        stalls = np.array(per_window_backend_stall_counts, dtype=float)[:n_windows]
        cycles = np.array(per_window_cycle_counts, dtype=float)[:n_windows]
        valid = cycles > 0
        stall_pct = np.zeros(n_windows)
        stall_pct[valid] = stalls[valid] / cycles[valid]
        covariates["backend_stall_pct"] = stall_pct

    # --- Tier 2: Cohort stratification (≥200 windows + covariates) ---
    if n_windows >= 200 and len(covariates) > 0:
        p25 = float(np.percentile(lat, 25))
        p75 = float(np.percentile(lat, 75))
        p95 = float(np.percentile(lat, 95))

        tail_mask = lat > p95
        typical_mask = (lat >= p25) & (lat <= p75)
        tail_cohort_size = int(np.sum(tail_mask))
        typical_cohort_size = int(np.sum(typical_mask))

        if tail_cohort_size >= 5 and typical_cohort_size >= 5:
            tier = 2
            result.tail_cohort_size = tail_cohort_size
            result.typical_cohort_size = typical_cohort_size
            provenance["cohort_comparison"] = "measured/stratification"

            for cov_name, cov_arr in covariates.items():
                if len(cov_arr) < n_windows:
                    continue
                tail_vals = cov_arr[tail_mask]
                typical_vals = cov_arr[typical_mask]

                tail_med = float(np.median(tail_vals))
                typical_med = float(np.median(typical_vals))

                try:
                    stat, p_val = mannwhitneyu(
                        tail_vals, typical_vals, alternative='two-sided'
                    )
                except ValueError as e:
                    logger.info("Mann-Whitney test for %s: %s (treating as non-significant)", cov_name, e)
                    p_val = 1.0

                significant = bool(p_val < 0.05)
                if not significant:
                    direction = "no_difference"
                elif tail_med > typical_med:
                    direction = "higher_in_tail"
                else:
                    direction = "lower_in_tail"

                result.covariate_comparisons[cov_name] = CovariateComparison(
                    name=cov_name,
                    tail_median=tail_med,
                    typical_median=typical_med,
                    mann_whitney_p=float(p_val),
                    significant=significant,
                    direction=direction,
                )

            # Frequency stratification (if freq data available)
            if "cpu_freq_mhz" in covariates:
                freq = covariates["cpu_freq_mhz"]
                freq_median = float(np.median(freq))  # Use median as "stable" freq
                stable_mask = np.abs(freq - freq_median) < (freq_median * 0.02)
                unstable_mask = ~stable_mask

                stable_lats = lat[stable_mask]
                unstable_lats = lat[unstable_mask]

                if len(stable_lats) >= 20 and len(unstable_lats) >= 20:
                    result.stable_freq_p99_us = float(np.percentile(stable_lats, 99))
                    result.unstable_freq_p99_us = float(np.percentile(unstable_lats, 99))
                    try:
                        _, ks_p = ks_2samp(stable_lats, unstable_lats)
                        result.freq_ks_pvalue = float(ks_p)
                    except ValueError as e:
                        logger.info("KS test for freq stratification: %s (treating as non-significant)", e)
                        result.freq_ks_pvalue = 1.0
                    provenance["freq_stratification"] = "measured/stratification/KS"

    # --- Tier 3: Shapley variance decomposition (requires Tier 2 + ≥500 windows + ≥2 covariates) ---
    non_zero_covariates = {k: v for k, v in covariates.items() if np.any(v != 0)}
    if tier >= 2 and n_windows >= 500 and len(non_zero_covariates) >= 2:
        # Build regression matrix with transformed covariates
        cov_names = sorted(non_zero_covariates.keys())
        X_cols = []
        for name in cov_names:
            arr = non_zero_covariates[name]
            if name == "cpu_freq_mhz":
                # 1/freq: higher latency when freq is lower
                safe = np.where(arr > 0, arr, 1.0)
                X_cols.append(1.0 / safe)
            elif name == "osnoise_total_ns":
                X_cols.append(np.log1p(arr))
            else:
                X_cols.append(arr)

        X = np.column_stack(X_cols)
        y = lat[:len(X)]

        shapley_pct, full_r2 = _shapley_r_squared(y, X, cov_names)

        if full_r2 > 0:
            tier = 3
            result.model_r_squared = full_r2
            result.shapley_pct = shapley_pct
            result.algorithmic_residual_pct = (1.0 - full_r2) * 100
            provenance["shapley_decomposition"] = "measured/OLS+Shapley"

    result.tier = tier
    result.provenance = provenance
    return result


def characterize_kernel(
    kernel_name: str,
    outer_latencies_us: list,
    device_latencies_us: Optional[list],
    device_spec: dict,
    noop_latencies_us: Optional[list] = None,
    per_window_cycle_counts: Optional[list] = None,
    per_window_instruction_counts: Optional[list] = None,
    per_window_backend_stall_counts: Optional[list] = None,
) -> Optional[CharacterizationResult]:
    """Post-hoc characterization of a kernel's latency distribution.

    Returns a CharacterizationResult with distribution landmarks,
    PMU enrichment, backend stall decomposition, and provenance tracking.
    Returns None if no latency data available.
    """

    dev = device_spec.get('device', device_spec)
    provenance = {}
    unavailable = {}

    # --- 1. Distribution landmarks ---
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

    # --- 2. Harness overhead check (logged, not stored) ---
    if device_latencies_us is not None and len(device_latencies_us) > 0:
        outer_arr = np.array(outer_latencies_us, dtype=float)
        device_arr = np.array(device_latencies_us, dtype=float)
        min_len = min(len(outer_arr), len(device_arr))
        overhead = outer_arr[:min_len] - device_arr[:min_len]
        overhead_p50 = float(np.median(overhead))
        median_outer = float(np.median(outer_arr[:min_len]))
        pct = (overhead_p50 / median_outer * 100) if median_outer > 0 else 0.0
        logger.info("Harness overhead: %.1f us (%.1f%%)", overhead_p50, pct)

    # --- 3. Noop cross-validation ---
    noop_p50 = None
    if noop_latencies_us is not None and len(noop_latencies_us) > 0:
        noop_p50 = float(np.median(noop_latencies_us))
        provenance["noop_p50_us"] = "measured/timing/noop"

    # --- 4. Instruction profile ---
    profile = analyze_kernel(kernel_name)
    if profile is not None:
        provenance["instruction_profile"] = "estimated/static/disassembly"

    # --- 5. PMU enrichment ---
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
        #
        # Guard: skip effective_freq when kernel P50 is below 50 µs.
        # At sub-50 µs latencies, PMU counter read overhead (kpc/perf
        # start+stop) is a significant fraction of total cycles, making
        # cycles/wall_time exceed physical CPU frequency. IPC and stall
        # percentages are unaffected (both numerator and denominator come
        # from PMU, so overhead cancels).
        if typical < 50.0:
            unavailable["effective_freq_ghz"] = (
                f"kernel P50 ({typical:.0f} µs) < 50 µs; "
                "PMU overhead dominates cycle count"
            )
            unavailable["frequency_tax_pct"] = unavailable["effective_freq_ghz"]
        elif True:
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
        reason = _pmu_unavailable_reason()
        unavailable["ipc"] = reason
        unavailable["effective_freq_ghz"] = reason
        unavailable["frequency_tax_pct"] = reason

    # --- 6. Backend stall decomposition ---
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
        unavailable["backend_stall_pct"] = _pmu_unavailable_reason()

    # --- 7. Tail attribution summary (Tier 1) ---
    char_tail_ratio = tail / typical if typical > 0 else 1.0
    # Compute noop-normalized ratio if noop available
    noop_normalized = None
    if noop_latencies_us is not None and len(noop_latencies_us) > 0:
        noop_arr_ta = np.array(noop_latencies_us, dtype=float)
        noop_p50_ta = float(np.percentile(noop_arr_ta, 50))
        noop_p99_ta = float(np.percentile(noop_arr_ta, 99))
        noop_ratio = noop_p99_ta / noop_p50_ta if noop_p50_ta > 0 else 1.0
        noop_normalized = char_tail_ratio / noop_ratio if noop_ratio > 0 else char_tail_ratio
    char_verdict = _verdict_from_ratio(noop_normalized, char_tail_ratio)
    provenance["tail_ratio"] = timing_prov
    provenance["platform_tail_verdict"] = timing_prov

    return CharacterizationResult(
        kernel_name=kernel_name,
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
        tail_ratio=char_tail_ratio,
        platform_tail_verdict=char_verdict,
        provenance=provenance,
        unavailable=unavailable,
    )




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_device_spec(device_path: str) -> dict:
    """Load a device specification YAML file."""
    with open(device_path) as f:
        return yaml.safe_load(f)


