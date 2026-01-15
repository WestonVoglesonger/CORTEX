#!/usr/bin/env python3
"""
Calculate statistical significance for Linux Governor comparison.
Generates p-values and t-statistics comparing powersave vs performance governors.

This is the Linux counterpart to the macOS idle vs medium comparison.
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats


def load_latencies(base_path: Path, kernel: str) -> np.ndarray:
    """Load latencies from telemetry NDJSON."""
    ndjson_file = base_path / kernel / "telemetry.ndjson"
    latencies = []

    if not ndjson_file.exists():
        print(f"Warning: {ndjson_file} not found", file=sys.stderr)
        return np.array([])

    with open(ndjson_file, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                if 'start_ts_ns' in data and 'end_ts_ns' in data:
                    latency_ns = data['end_ts_ns'] - data['start_ts_ns']
                    latency_us = latency_ns / 1000.0
                    latencies.append(latency_us)
            except json.JSONDecodeError:
                continue

    return np.array(latencies)


def calculate_geometric_mean(medians: list) -> float:
    """Calculate geometric mean of median latencies."""
    if not medians:
        return 0.0
    return np.exp(np.mean(np.log(medians)))


def main():
    kernels = ['bandpass_fir', 'car', 'goertzel', 'notch_iir']

    script_dir = Path(__file__).parent
    experiment_dir = script_dir.parent

    powersave_base = experiment_dir / 'run-001-powersave' / 'kernel-data'
    performance_base = experiment_dir / 'run-002-performance' / 'kernel-data'
    schedutil_base = experiment_dir / 'run-003-schedutil' / 'kernel-data'

    print("=" * 90)
    print("STATISTICAL SIGNIFICANCE ANALYSIS: Linux CPU Governor Comparison")
    print("=" * 90)
    print("\nMethod: Welch's t-test on log-transformed latencies")
    print("(Log transform appropriate for log-normal latency distributions)")

    # Check which runs are available
    has_powersave = powersave_base.exists()
    has_performance = performance_base.exists()
    has_schedutil = schedutil_base.exists()

    if not has_powersave or not has_performance:
        print("\nError: Need at least powersave and performance runs for comparison")
        print(f"  powersave:   {'Found' if has_powersave else 'Not found'}")
        print(f"  performance: {'Found' if has_performance else 'Not found'}")
        print(f"  schedutil:   {'Found' if has_schedutil else 'Not found'}")
        return 1

    # Primary comparison: Powersave vs Performance
    print("\n" + "=" * 90)
    print("COMPARISON 1: Powersave vs Performance (Primary)")
    print("=" * 90)
    print(f"{'Kernel':<15} {'n_powersave':<12} {'n_perf':<10} {'t-statistic':<12} {'p-value':<12} {'Sig?'}")
    print("-" * 90)

    powersave_medians = []
    performance_medians = []
    t_stats = {}

    for kernel in kernels:
        powersave_lat = load_latencies(powersave_base, kernel)
        performance_lat = load_latencies(performance_base, kernel)

        if len(powersave_lat) == 0 or len(performance_lat) == 0:
            print(f"{kernel:<15} {'N/A':<12} {'N/A':<10} {'N/A':<12} {'N/A':<12} N/A")
            continue

        # Record medians
        powersave_medians.append(np.median(powersave_lat))
        performance_medians.append(np.median(performance_lat))

        # Log-transform for statistical test
        log_powersave = np.log(powersave_lat)
        log_performance = np.log(performance_lat)

        # Welch's t-test (doesn't assume equal variance)
        t_stat, p_val = stats.ttest_ind(log_powersave, log_performance, equal_var=False)
        t_stats[kernel] = (t_stat, p_val)

        sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < 0.05 else "ns"))

        print(f"{kernel:<15} {len(powersave_lat):<12} {len(performance_lat):<10} {t_stat:<12.2f} {p_val:<12.2e} {sig}")

    print("-" * 90)
    print("Significance codes: *** p<0.001, ** p<0.01, * p<0.05, ns = not significant")

    # Aggregate comparison
    if powersave_medians and performance_medians:
        geo_mean_powersave = calculate_geometric_mean(powersave_medians)
        geo_mean_performance = calculate_geometric_mean(performance_medians)
        ratio = geo_mean_powersave / geo_mean_performance

        print("\n" + "=" * 90)
        print("AGGREGATE COMPARISON (Geometric Mean of Medians)")
        print("=" * 90)
        print(f"  Powersave:    {geo_mean_powersave:.1f} us")
        print(f"  Performance:  {geo_mean_performance:.1f} us")
        print(f"  Ratio:        {ratio:.2f}x slower (powersave vs performance)")

    # Secondary comparison: Schedutil vs Performance (if available)
    if has_schedutil:
        print("\n" + "=" * 90)
        print("COMPARISON 2: Schedutil vs Performance (Secondary)")
        print("=" * 90)
        print(f"{'Kernel':<15} {'n_schedutil':<12} {'n_perf':<10} {'t-statistic':<12} {'p-value':<12} {'Sig?'}")
        print("-" * 90)

        schedutil_medians = []

        for kernel in kernels:
            schedutil_lat = load_latencies(schedutil_base, kernel)
            performance_lat = load_latencies(performance_base, kernel)

            if len(schedutil_lat) == 0 or len(performance_lat) == 0:
                print(f"{kernel:<15} {'N/A':<12} {'N/A':<10} {'N/A':<12} {'N/A':<12} N/A")
                continue

            schedutil_medians.append(np.median(schedutil_lat))

            log_schedutil = np.log(schedutil_lat)
            log_performance = np.log(performance_lat)

            t_stat, p_val = stats.ttest_ind(log_schedutil, log_performance, equal_var=False)
            sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < 0.05 else "ns"))

            print(f"{kernel:<15} {len(schedutil_lat):<12} {len(performance_lat):<10} {t_stat:<12.2f} {p_val:<12.2e} {sig}")

        print("-" * 90)

        if schedutil_medians and performance_medians:
            geo_mean_schedutil = calculate_geometric_mean(schedutil_medians)
            ratio_schedutil = geo_mean_schedutil / geo_mean_performance

            print(f"\n  Schedutil:    {geo_mean_schedutil:.1f} us")
            print(f"  Performance:  {geo_mean_performance:.1f} us")
            print(f"  Ratio:        {ratio_schedutil:.2f}x (schedutil vs performance)")

    # Final summary
    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)

    if powersave_medians and performance_medians:
        ratio = geo_mean_powersave / geo_mean_performance
        if ratio > 1.5:
            print(f"\nConclusion: Powersave governor is {ratio:.1f}x slower than performance governor,")
            print("confirming the DVFS/Idle Paradox observed on macOS. Direct governor control")
            print("achieves the same frequency locking effect as the macOS stress-ng workaround.")
        else:
            print(f"\nNote: Powersave governor is only {ratio:.2f}x slower than performance.")
            print("This may indicate different DVFS behavior on this Linux/hardware combination.")

    return 0


if __name__ == '__main__':
    sys.exit(main())
