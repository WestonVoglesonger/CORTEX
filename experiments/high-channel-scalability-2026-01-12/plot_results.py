#!/usr/bin/env python3
"""
Generate plots from high-channel scalability benchmark results.

Creates:
1. File size vs channel count (linear scaling validation)
2. Generation time vs channel count (performance characterization)
"""

import json
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


def plot_file_size_scaling(results, output_path):
    """
    Plot file size vs channel count.

    Shows both actual measurements and theoretical linear scaling.
    """
    # Filter both lists to ensure matching lengths (skip results with missing file_size_mb)
    channels = [r['channels'] for r in results if r['file_size_mb']]
    file_sizes = [r['file_size_mb'] for r in results if r['file_size_mb']]

    if len(file_sizes) < 2:
        print("Warning: Insufficient data for file size plot")
        return

    # Theoretical scaling (based on first data point)
    base_channels = channels[0]
    base_size = file_sizes[0]
    theoretical_sizes = [base_size * (ch / base_channels) for ch in channels]

    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot actual measurements
    ax.plot(channels, file_sizes, 'o-', linewidth=2, markersize=8,
            label='Actual', color='#2E86AB')

    # Plot theoretical scaling
    ax.plot(channels, theoretical_sizes, '--', linewidth=2,
            label='Theoretical (linear)', color='#A23B72')

    ax.set_xlabel('Channel Count', fontsize=12)
    ax.set_ylabel('File Size (MB)', fontsize=12)
    ax.set_title('Dataset File Size Scaling', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=11)

    # Add annotations for key points
    if len(channels) >= 2:
        # Annotate max channel count
        max_idx = len(channels) - 1
        ax.annotate(f'{channels[max_idx]}ch\n{file_sizes[max_idx]:.1f} MB',
                    xy=(channels[max_idx], file_sizes[max_idx]),
                    xytext=(10, -30),
                    textcoords='offset points',
                    fontsize=10,
                    bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.3),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def plot_memory_efficiency(results, output_path):
    """
    Plot memory efficiency: bytes per channel per sample.

    Should be constant at 4 bytes (float32) regardless of channel count.
    """
    data = [(r['channels'], r['file_size_mb']) for r in results if r['file_size_mb']]

    if len(data) < 2:
        print("Warning: Insufficient data for memory efficiency plot")
        return

    channels = [d[0] for d in data]
    file_sizes_mb = [d[1] for d in data]

    # Calculate bytes per channel per sample
    # File size = channels × samples × 4 bytes
    # Samples = 10s × 160Hz = 1600 samples
    samples = 10.0 * 160
    bytes_per_ch_sample = [(size_mb * 1024 * 1024) / (ch * samples)
                            for ch, size_mb in zip(channels, file_sizes_mb)]

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(channels, bytes_per_ch_sample, 'o-', linewidth=2, markersize=8,
            color='#F18F01')

    # Add theoretical line at 4 bytes
    ax.axhline(y=4.0, color='#A23B72', linestyle='--', linewidth=2,
               label='Theoretical (float32)')

    ax.set_xlabel('Channel Count', fontsize=12)
    ax.set_ylabel('Bytes per Channel per Sample', fontsize=12)
    ax.set_title('Memory Efficiency (Should be constant at 4 bytes)',
                 fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=11)
    ax.set_ylim([3.5, 4.5])

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def main():
    script_dir = Path(__file__).parent
    results_dir = script_dir / 'results'
    figures_dir = script_dir / 'figures'

    # Load summary
    summary_path = results_dir / 'summary.json'
    if not summary_path.exists():
        print("Error: summary.json not found. Run analyze_results.py first.")
        return 1

    with open(summary_path) as f:
        data = json.load(f)

    results = data['results']

    if not results:
        print("Error: No results to plot.")
        return 1

    # Sort by channel count
    results = sorted(results, key=lambda x: x['channels'])

    # Create figures directory
    figures_dir.mkdir(exist_ok=True)

    print("Generating plots...")
    print()

    # Plot 1: File size scaling
    plot_file_size_scaling(results, figures_dir / 'file_size_scaling.png')

    # Plot 2: Memory efficiency
    plot_memory_efficiency(results, figures_dir / 'memory_efficiency.png')

    print()
    print(f"All plots saved to: {figures_dir}")
    print()

    return 0


if __name__ == '__main__':
    try:
        exit(main())
    except ImportError as e:
        print(f"Error: Missing dependency: {e}")
        print()
        print("Install matplotlib:")
        print("  pip install matplotlib")
        exit(1)
