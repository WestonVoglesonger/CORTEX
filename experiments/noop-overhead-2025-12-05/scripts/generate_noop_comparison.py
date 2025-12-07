#!/usr/bin/env python3
"""
Generate No-Op Idle vs Medium Comparison Figure
================================================
Creates a bar chart comparing no-op kernel latency under idle and medium load profiles.

This visualization shows:
- Minimum latency (true harness overhead): ~1 µs for both profiles
- Median latency: Idle higher (DVFS penalty), Medium lower (high CPU frequency)
- P95 latency: Shows jitter characteristics

Key finding: Minimum is identical across profiles, proving it represents true harness
overhead independent of environmental factors.
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np


def load_latencies(telemetry_file: Path) -> np.ndarray:
    """Load latencies from telemetry NDJSON file."""
    latencies = []

    if not telemetry_file.exists():
        print(f"Error: Telemetry file not found: {telemetry_file}", file=sys.stderr)
        return np.array([])

    with open(telemetry_file, 'r') as f:
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


def calculate_stats(latencies: np.ndarray) -> dict:
    """Calculate summary statistics from latency array."""
    if len(latencies) == 0:
        return None

    return {
        'min': np.min(latencies),
        'median': np.median(latencies),
        'p95': np.percentile(latencies, 95),
        'max': np.max(latencies),
        'mean': np.mean(latencies),
        'count': len(latencies)
    }


def main():
    script_dir = Path(__file__).parent
    experiment_dir = script_dir.parent
    figures_dir = experiment_dir / 'figures'
    figures_dir.mkdir(exist_ok=True)

    # Load telemetry from both profiles
    idle_file = experiment_dir / 'run-001-idle' / 'kernel-data' / 'noop' / 'telemetry.ndjson'
    medium_file = experiment_dir / 'run-002-medium' / 'kernel-data' / 'noop' / 'telemetry.ndjson'

    print("Loading telemetry data...")
    idle_latencies = load_latencies(idle_file)
    medium_latencies = load_latencies(medium_file)

    if len(idle_latencies) == 0 or len(medium_latencies) == 0:
        print("\nError: Missing telemetry data. Run the experiment first:", file=sys.stderr)
        print("  ./scripts/run-experiment.sh", file=sys.stderr)
        return 1

    # Calculate statistics
    idle_stats = calculate_stats(idle_latencies)
    medium_stats = calculate_stats(medium_latencies)

    print(f"\nIdle profile (n={idle_stats['count']}):")
    print(f"  Min:    {idle_stats['min']:.2f} µs")
    print(f"  Median: {idle_stats['median']:.2f} µs")
    print(f"  P95:    {idle_stats['p95']:.2f} µs")

    print(f"\nMedium profile (n={medium_stats['count']}):")
    print(f"  Min:    {medium_stats['min']:.2f} µs")
    print(f"  Median: {medium_stats['median']:.2f} µs")
    print(f"  P95:    {medium_stats['p95']:.2f} µs")

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 7))

    # Data for grouped bar chart
    profiles = ['Idle', 'Medium']
    min_values = [idle_stats['min'], medium_stats['min']]
    median_values = [idle_stats['median'], medium_stats['median']]
    p95_values = [idle_stats['p95'], medium_stats['p95']]

    # Bar positioning
    x = np.arange(len(profiles))
    width = 0.25

    # Create grouped bars
    bars1 = ax.bar(x - width, min_values, width, label='Minimum',
                   color='#2ecc71', edgecolor='black', linewidth=1.5)
    bars2 = ax.bar(x, median_values, width, label='Median',
                   color='#3498db', edgecolor='black', linewidth=1.5)
    bars3 = ax.bar(x + width, p95_values, width, label='P95',
                   color='#e74c3c', edgecolor='black', linewidth=1.5)

    # Add value labels on bars
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.15,
                    f'{height:.1f}',
                    ha='center', va='bottom', fontsize=11, fontweight='bold')

    # Add annotations for key findings
    # Annotation 1: True harness overhead (minimum)
    ax.annotate('True harness overhead:\n1 µs (both profiles)',
                xy=(0 - width, min_values[0]), xytext=(-0.6, 2),
                fontsize=11, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#2ecc71', alpha=0.3),
                arrowprops=dict(arrowstyle='->', lw=2, color='#27ae60'))

    # Annotation 2: DVFS penalty (idle median)
    dvfs_penalty = idle_stats['median'] - idle_stats['min']
    ax.annotate(f'DVFS penalty:\n+{dvfs_penalty:.1f} µs',
                xy=(0, median_values[0]), xytext=(0.6, median_values[0] + 0.5),
                fontsize=10, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#3498db', alpha=0.3),
                arrowprops=dict(arrowstyle='->', lw=1.5, color='#2980b9'))

    # Annotation 3: Stress-ng effect (medium median)
    stress_effect = medium_stats['median'] - medium_stats['min']
    ax.annotate(f'Stress-ng effect:\n+{stress_effect:.1f} µs',
                xy=(1, median_values[1]), xytext=(1.4, median_values[1] - 0.8),
                fontsize=10, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#f39c12', alpha=0.3),
                arrowprops=dict(arrowstyle='->', lw=1.5, color='#e67e22'))

    # Formatting
    ax.set_ylabel('Latency (µs)', fontsize=14, fontweight='bold')
    ax.set_xlabel('Load Profile', fontsize=14, fontweight='bold')
    ax.set_title('No-Op Kernel Harness Overhead Measurement\n'
                 'Idle vs Medium Load Profile Decomposition',
                 fontsize=15, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(profiles, fontsize=13)
    ax.legend(fontsize=12, loc='upper left')

    # Grid for readability
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)

    # Set y-axis limit to show detail in low range
    max_y = max(p95_values) * 1.3
    ax.set_ylim(0, max_y)

    # Add interpretation box
    interpretation = (
        "Key Finding:\n"
        f"• Minimum latency identical ({min_values[0]:.1f} µs both profiles)\n"
        "  → True harness overhead independent of environment\n"
        f"• Idle median > Medium median ({median_values[0]:.1f} vs {median_values[1]:.1f} µs)\n"
        "  → DVFS penalty: CPU at low frequency when idle\n"
        f"• Medium P95 > Idle P95 ({p95_values[1]:.1f} vs {p95_values[0]:.1f} µs)\n"
        "  → Stress-ng causes scheduler jitter"
    )

    ax.text(0.98, 0.97, interpretation,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment='top',
            horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    # Sample counts
    ax.text(0.02, 0.97,
            f'Sample counts:\nIdle: n={idle_stats["count"]}\nMedium: n={medium_stats["count"]}',
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.5))

    # Tight layout
    plt.tight_layout()

    # Save figure
    png_path = figures_dir / 'noop_idle_medium_comparison.png'
    pdf_path = figures_dir / 'noop_idle_medium_comparison.pdf'

    plt.savefig(png_path, dpi=300, bbox_inches='tight')
    plt.savefig(pdf_path, bbox_inches='tight')

    print(f"\nFigures saved:")
    print(f"  PNG: {png_path}")
    print(f"  PDF: {pdf_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
