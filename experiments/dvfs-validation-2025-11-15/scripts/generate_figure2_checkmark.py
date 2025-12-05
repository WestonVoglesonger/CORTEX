#!/usr/bin/env python3
"""
Generate Figure 2: Aggregated Kernel Latency by Load Profile
Shows the "checkmark pattern" across Idle/Medium/Heavy load profiles.
"""

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

# Aggregated median latencies (geometric mean across all kernels)
load_profiles = ['Medium', 'Heavy', 'Idle']
latencies_us = [123.1, 183.3, 284.3]
colors = ['#2ecc71', '#f39c12', '#e74c3c']  # Green, Yellow/Orange, Red

# Create figure
fig, ax = plt.subplots(figsize=(10, 6))

# Create bar chart
bars = ax.bar(load_profiles, latencies_us, color=colors, edgecolor='black', linewidth=1.5)

# Add value labels on top of bars
for bar, val in zip(bars, latencies_us):
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2., height + 5,
            f'{val:.1f} µs',
            ha='center', va='bottom', fontsize=14, fontweight='bold')

# Add ratio annotations
# Medium is baseline
ax.annotate('', xy=(1, 183.3), xytext=(1, 123.1),
            arrowprops=dict(arrowstyle='<->', color='black', lw=2))
ax.text(1.15, 153, '1.49×\nslower', ha='left', va='center', fontsize=11,
        bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.7))

ax.annotate('', xy=(2, 284.3), xytext=(2, 123.1),
            arrowprops=dict(arrowstyle='<->', color='black', lw=2))
ax.text(2.15, 203, '2.31×\nslower', ha='left', va='center', fontsize=11,
        bbox=dict(boxstyle='round,pad=0.5', facecolor='red', alpha=0.7))

# Formatting
ax.set_ylabel('Aggregated Median Latency (µs, geometric mean)', fontsize=13, fontweight='bold')
ax.set_xlabel('Load Profile', fontsize=13, fontweight='bold')
ax.set_title('Aggregated Kernel Latency by Load Profile\n(Geometric Mean Across All Kernels)',
             fontsize=14, fontweight='bold', pad=20)

# Add grid for readability
ax.grid(axis='y', alpha=0.3, linestyle='--')
ax.set_axisbelow(True)

# Add interpretation legend
legend_text = [
    '✓ Medium: Optimal (DVFS locked, no contention)',
    '○ Heavy: Resource contention (1.49× slower than Medium)',
    '✗ Idle: DVFS penalty - the "Idle Paradox" (2.31× slower than Medium)'
]
ax.text(0.02, 0.98, '\n'.join(legend_text),
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment='top',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

# Set y-axis limits with some headroom
ax.set_ylim(0, 320)

# Tighten layout
plt.tight_layout()

# Save figure
output_path = '../figure2_checkmark_pattern.png'
plt.savefig(output_path, dpi=300, bbox_inches='tight')
print(f"Figure saved to: {output_path}")

# Also save as PDF for publication quality
output_path_pdf = '../figure2_checkmark_pattern.pdf'
plt.savefig(output_path_pdf, bbox_inches='tight')
print(f"PDF version saved to: {output_path_pdf}")

print("\nDone! Figure 2 generated successfully.")
