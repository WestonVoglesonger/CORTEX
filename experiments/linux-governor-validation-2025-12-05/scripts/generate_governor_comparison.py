#!/usr/bin/env python3
"""
Generate Governor Comparison Figure
====================================
Creates a bar chart comparing aggregated kernel latency across Linux CPU governors.
This is analogous to the macOS "checkmark pattern" figure.
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np


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


def calculate_geometric_mean_median(base_path: Path, kernels: list) -> float:
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

    # Define governors and their display properties
    governors = [
        ('performance', 'run-002-performance', 'Performance', '#2ecc71'),           # Green
        ('schedutil-boosted', 'run-004-schedutil-boosted', 'Schedutil+stress', '#9b59b6'),  # Purple
        ('schedutil', 'run-003-schedutil', 'Schedutil', '#3498db'),                 # Blue
        ('powersave', 'run-001-powersave', 'Powersave', '#e74c3c'),                 # Red
    ]

    # Load data for each governor
    labels = []
    values = []
    colors = []

    for gov_name, run_dir, display_name, color in governors:
        base_path = experiment_dir / run_dir / 'kernel-data'
        geo_mean = calculate_geometric_mean_median(base_path, kernels)

        if geo_mean is not None:
            labels.append(display_name)
            values.append(geo_mean)
            colors.append(color)
            print(f"{display_name}: {geo_mean:.1f} us")
        else:
            print(f"{display_name}: No data available")

    if len(values) < 2:
        print("\nError: Need at least 2 governor runs to generate comparison")
        return 1

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6))

    # Create bar chart
    x_pos = np.arange(len(labels))
    bars = ax.bar(x_pos, values, color=colors, edgecolor='black', linewidth=1.5)

    # Add value labels on top of bars
    for bar, val in zip(bars, values):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 5,
                f'{val:.1f} us',
                ha='center', va='bottom', fontsize=14, fontweight='bold')

    # Add ratio annotations (compare to performance baseline)
    if len(values) >= 2:
        baseline = values[0]  # Performance is first
        for i, val in enumerate(values[1:], start=1):
            if baseline > 0:
                ratio = val / baseline
                # Draw comparison arrow
                ax.annotate('', xy=(i, val), xytext=(i, baseline),
                            arrowprops=dict(arrowstyle='<->', color='black', lw=2))
                # Add ratio label
                mid_y = (val + baseline) / 2
                color_bg = '#f39c12' if ratio < 1.5 else '#e74c3c'
                ax.text(i + 0.15, mid_y, f'{ratio:.2f}x\nslower',
                        ha='left', va='center', fontsize=11,
                        bbox=dict(boxstyle='round,pad=0.5', facecolor=color_bg, alpha=0.7))

    # Formatting
    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, fontsize=12)
    ax.set_ylabel('Aggregated Median Latency (us, geometric mean)', fontsize=13, fontweight='bold')
    ax.set_xlabel('CPU Governor', fontsize=13, fontweight='bold')
    ax.set_title('Linux CPU Governor Impact on Kernel Latency\n(Geometric Mean Across All Kernels)',
                 fontsize=14, fontweight='bold', pad=20)

    # Add grid for readability
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)

    # Add interpretation legend
    legend_items = []
    if 'Performance' in labels:
        legend_items.append('Performance: Optimal (CPU locked to max frequency)')
    if 'Schedutil+stress' in labels:
        legend_items.append('Schedutil+stress: Dynamic + background load (no effect!)')
    if 'Schedutil' in labels:
        legend_items.append('Schedutil: Linux default (dynamic scaling)')
    if 'Powersave' in labels:
        legend_items.append('Powersave: DVFS penalty (minimum frequency)')

    if legend_items:
        ax.text(0.02, 0.98, '\n'.join(legend_items),
                transform=ax.transAxes,
                fontsize=10,
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # Set y-axis limits with headroom
    max_val = max(values) if values else 100
    ax.set_ylim(0, max_val * 1.2)

    # Tighten layout
    plt.tight_layout()

    # Save figure
    output_path = figures_dir / 'governor_comparison.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\nFigure saved to: {output_path}")

    output_path_pdf = figures_dir / 'governor_comparison.pdf'
    plt.savefig(output_path_pdf, bbox_inches='tight')
    print(f"PDF version saved to: {output_path_pdf}")

    plt.close()

    # Also create per-kernel breakdown
    create_per_kernel_figure(experiment_dir, figures_dir, kernels, governors)

    return 0


def create_per_kernel_figure(experiment_dir: Path, figures_dir: Path,
                              kernels: list, governors: list):
    """Create a per-kernel comparison figure."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()

    for idx, kernel in enumerate(kernels):
        ax = axes[idx]

        labels = []
        values = []
        colors = []

        for gov_name, run_dir, display_name, color in governors:
            base_path = experiment_dir / run_dir / 'kernel-data'
            latencies = load_latencies(base_path, kernel)

            if len(latencies) > 0:
                labels.append(display_name)
                values.append(np.median(latencies))
                colors.append(color)

        if values:
            x_pos = np.arange(len(labels))
            bars = ax.bar(x_pos, values, color=colors, edgecolor='black', linewidth=1)

            for bar, val in zip(bars, values):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + height*0.02,
                        f'{val:.1f}',
                        ha='center', va='bottom', fontsize=10)

            ax.set_xticks(x_pos)
            ax.set_xticklabels(labels, fontsize=10)

        ax.set_ylabel('Median Latency (us)', fontsize=11)
        ax.set_title(f'{kernel}', fontsize=12, fontweight='bold')
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)

    fig.suptitle('Per-Kernel Latency Comparison by Governor', fontsize=14, fontweight='bold')
    plt.tight_layout()

    output_path = figures_dir / 'per_kernel_comparison.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Per-kernel figure saved to: {output_path}")

    plt.close()


if __name__ == '__main__':
    sys.exit(main())
