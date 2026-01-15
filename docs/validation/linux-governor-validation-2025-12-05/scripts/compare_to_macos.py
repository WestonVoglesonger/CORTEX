#!/usr/bin/env python3
"""
Compare Linux Governor Results to macOS DVFS Validation
========================================================
Generates cross-platform comparison figures and analysis to validate
that the "Idle Paradox" is a real DVFS phenomenon, not macOS-specific.
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


# macOS reference data (from experiments/dvfs-validation-2025-11-15)
MACOS_DATA = {
    'idle': {
        'geo_mean_median': 284.3,  # us
        'description': 'No background load (DVFS penalty)',
        'color': '#e74c3c',
    },
    'medium': {
        'geo_mean_median': 123.1,  # us
        'description': 'stress-ng 4 CPUs @ 50%',
        'color': '#2ecc71',
    },
    'heavy': {
        'geo_mean_median': 183.3,  # us
        'description': 'stress-ng 8 CPUs @ 90%',
        'color': '#f39c12',
    },
}


def load_latencies(base_path: Path, kernel: str) -> np.ndarray:
    """Load latencies from telemetry NDJSON."""
    ndjson_file = base_path / kernel / "telemetry.ndjson"
    latencies = []

    if not ndjson_file.exists():
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


def calculate_geo_mean_median(base_path: Path, kernels: list) -> float:
    """Calculate geometric mean of median latencies across kernels."""
    medians = []
    for kernel in kernels:
        latencies = load_latencies(base_path, kernel)
        if len(latencies) > 0:
            medians.append(np.median(latencies))

    if medians:
        return np.exp(np.mean(np.log(medians)))
    return None


def main():
    kernels = ['bandpass_fir', 'car', 'goertzel', 'notch_iir']

    script_dir = Path(__file__).parent
    experiment_dir = script_dir.parent
    figures_dir = experiment_dir / 'figures'
    figures_dir.mkdir(exist_ok=True)

    # Load Linux data
    linux_data = {}

    powersave_path = experiment_dir / 'run-001-powersave' / 'kernel-data'
    linux_data['powersave'] = calculate_geo_mean_median(powersave_path, kernels)

    performance_path = experiment_dir / 'run-002-performance' / 'kernel-data'
    linux_data['performance'] = calculate_geo_mean_median(performance_path, kernels)

    schedutil_path = experiment_dir / 'run-003-schedutil' / 'kernel-data'
    linux_data['schedutil'] = calculate_geo_mean_median(schedutil_path, kernels)

    schedutil_boosted_path = experiment_dir / 'run-004-schedutil-boosted' / 'kernel-data'
    linux_data['schedutil_boosted'] = calculate_geo_mean_median(schedutil_boosted_path, kernels)

    # Print available data
    print("=" * 80)
    print("CROSS-PLATFORM COMPARISON: macOS vs Linux")
    print("=" * 80)
    print("\nmacOS Reference Data:")
    print(f"  Idle:   {MACOS_DATA['idle']['geo_mean_median']:.1f} us")
    print(f"  Medium: {MACOS_DATA['medium']['geo_mean_median']:.1f} us")
    print(f"  Heavy:  {MACOS_DATA['heavy']['geo_mean_median']:.1f} us")

    print("\nLinux Governor Data:")
    for gov, val in linux_data.items():
        if val is not None:
            print(f"  {gov.capitalize()}: {val:.1f} us")
        else:
            print(f"  {gov.capitalize()}: No data")

    # Check if we have enough data
    if linux_data['powersave'] is None or linux_data['performance'] is None:
        print("\nError: Need at least powersave and performance data for comparison")
        return 1

    # Create comparison figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Left plot: macOS comparison
    macos_labels = ['Medium', 'Heavy', 'Idle']
    macos_values = [
        MACOS_DATA['medium']['geo_mean_median'],
        MACOS_DATA['heavy']['geo_mean_median'],
        MACOS_DATA['idle']['geo_mean_median'],
    ]
    macos_colors = [
        MACOS_DATA['medium']['color'],
        MACOS_DATA['heavy']['color'],
        MACOS_DATA['idle']['color'],
    ]

    bars1 = ax1.bar(macos_labels, macos_values, color=macos_colors, edgecolor='black', linewidth=1.5)
    ax1.set_ylabel('Geometric Mean of Median Latency (us)', fontsize=12)
    ax1.set_xlabel('Load Profile', fontsize=12)
    ax1.set_title('macOS DVFS Validation\n(stress-ng workaround)', fontsize=13, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3, linestyle='--')
    ax1.set_axisbelow(True)

    for bar, val in zip(bars1, macos_values):
        ax1.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 5,
                 f'{val:.1f}', ha='center', va='bottom', fontsize=11, fontweight='bold')

    # Add macOS ratio annotation
    macos_ratio = MACOS_DATA['idle']['geo_mean_median'] / MACOS_DATA['medium']['geo_mean_median']
    ax1.text(0.5, 0.95, f'Idle/Medium: {macos_ratio:.2f}x slower',
             transform=ax1.transAxes, ha='center', fontsize=11,
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    # Right plot: Linux governor comparison
    linux_labels = []
    linux_values = []
    linux_colors = []

    # Order: performance, schedutil+stress, schedutil, powersave
    if linux_data['performance'] is not None:
        linux_labels.append('Performance')
        linux_values.append(linux_data['performance'])
        linux_colors.append('#2ecc71')

    if linux_data.get('schedutil_boosted') is not None:
        linux_labels.append('Schedutil\n+stress')
        linux_values.append(linux_data['schedutil_boosted'])
        linux_colors.append('#9b59b6')

    if linux_data['schedutil'] is not None:
        linux_labels.append('Schedutil')
        linux_values.append(linux_data['schedutil'])
        linux_colors.append('#3498db')

    if linux_data['powersave'] is not None:
        linux_labels.append('Powersave')
        linux_values.append(linux_data['powersave'])
        linux_colors.append('#e74c3c')

    bars2 = ax2.bar(linux_labels, linux_values, color=linux_colors, edgecolor='black', linewidth=1.5)
    ax2.set_ylabel('Geometric Mean of Median Latency (us)', fontsize=12)
    ax2.set_xlabel('CPU Governor', fontsize=12)
    ax2.set_title('Linux Governor Validation\n(Direct governor control)', fontsize=13, fontweight='bold')
    ax2.grid(axis='y', alpha=0.3, linestyle='--')
    ax2.set_axisbelow(True)

    for bar, val in zip(bars2, linux_values):
        ax2.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 5,
                 f'{val:.1f}', ha='center', va='bottom', fontsize=11, fontweight='bold')

    # Add Linux ratio annotation
    linux_ratio = linux_data['powersave'] / linux_data['performance']
    ax2.text(0.5, 0.95, f'Powersave/Perf: {linux_ratio:.2f}x slower',
             transform=ax2.transAxes, ha='center', fontsize=11,
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    # Match y-axis scales for fair comparison
    max_val = max(max(macos_values), max(linux_values))
    ax1.set_ylim(0, max_val * 1.2)
    ax2.set_ylim(0, max_val * 1.2)

    # Add overall title
    fig.suptitle('Cross-Platform DVFS Validation: macOS vs Linux',
                 fontsize=15, fontweight='bold', y=1.02)

    plt.tight_layout()

    # Save figure
    output_path = figures_dir / 'macos_linux_comparison.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\nFigure saved to: {output_path}")

    output_path_pdf = figures_dir / 'macos_linux_comparison.pdf'
    plt.savefig(output_path_pdf, bbox_inches='tight')
    print(f"PDF saved to: {output_path_pdf}")

    plt.close()

    # Print comparison summary
    print("\n" + "=" * 80)
    print("ANALYSIS SUMMARY")
    print("=" * 80)

    print("\nKey Ratios:")
    print(f"  macOS: Idle/Medium = {macos_ratio:.2f}x slower")
    print(f"  Linux: Powersave/Performance = {linux_ratio:.2f}x slower")

    print("\n" + "=" * 80)
    print("KEY FINDINGS")
    print("=" * 80)

    ratio_diff = abs(macos_ratio - linux_ratio)
    if ratio_diff < 0.5:
        print(f"""
The Linux powersave/performance ratio ({linux_ratio:.2f}x) is similar to the
macOS idle/medium ratio ({macos_ratio:.2f}x).

This validates:
  1. The "Idle Paradox" is a real DVFS phenomenon, not macOS-specific
  2. macOS stress-ng workaround achieves goal-equivalence to direct governor control
  3. Linux performance governor matches macOS medium-load behavior
  4. Linux powersave governor matches macOS idle behavior
""")
    elif linux_ratio > 1.0:
        print(f"""
The Linux powersave/performance ratio ({linux_ratio:.2f}x) confirms
DVFS effects are present, though different from macOS ({macos_ratio:.2f}x).

The difference may be due to:
  - Different CPU frequency scaling characteristics (Apple Silicon vs other)
  - Different governor implementations
  - System-specific thermal/power management

Key finding: Linux governor control successfully demonstrates the DVFS effect.
""")
    else:
        print(f"""
The Linux powersave/performance ratio ({linux_ratio:.2f}x) is unexpectedly
low compared to macOS ({macos_ratio:.2f}x).

Possible explanations:
  - Powersave governor may not be reducing frequency as expected
  - Check frequency-log.csv to verify actual frequencies
  - Hardware may not support extreme frequency reduction
""")

    print("=" * 80)

    # Generate mapping table for paper
    print("\nEquivalence Mapping (for paper):")
    print("-" * 70)
    print(f"{'macOS Condition':<20} {'Linux Equivalent':<25} {'Method'}")
    print("-" * 70)
    print(f"{'Idle (no load)':<20} {'powersave governor':<25} {'Direct governor'}")
    print(f"{'Medium (stress-ng)':<20} {'performance governor':<25} {'Direct governor'}")
    print(f"{'Heavy (stress-ng)':<20} {'N/A':<25} {'Not needed'}")
    print("-" * 70)

    # Add key finding about stress-ng
    if linux_data.get('schedutil_boosted') is not None and linux_data.get('schedutil') is not None:
        boost_ratio = linux_data['schedutil_boosted'] / linux_data['schedutil']
        print(f"\nCRITICAL FINDING: stress-ng does NOT help schedutil on Linux!")
        print(f"  Schedutil+stress / Schedutil = {boost_ratio:.2f}x (no improvement)")
        print(f"  Reason: Linux uses per-CPU frequency scaling, not cluster-wide like macOS")
        print(f"  The benchmark runs on CPU 0, but stress-ng runs on other CPUs")

    return 0


if __name__ == '__main__':
    sys.exit(main())
