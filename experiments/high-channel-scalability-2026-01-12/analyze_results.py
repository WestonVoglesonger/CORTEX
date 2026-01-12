#!/usr/bin/env python3
"""
Analyze high-channel scalability benchmark results.

Extracts generation time, file size, and performance metrics
from benchmark logs and generates summary statistics.
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple


def parse_log_file(log_path: Path) -> Dict:
    """
    Extract metrics from benchmark log file.

    Returns dict with:
    - channels: Number of channels
    - file_size_mb: Generated file size in MB
    - generation_time_s: Time to generate dataset (if available)
    - success: Whether benchmark succeeded
    """
    with open(log_path) as f:
        content = f.read()

    # Extract channel count from filename
    match = re.search(r'scalability_(\d+)ch\.log', log_path.name)
    if not match:
        return None

    channels = int(match.group(1))

    # Extract file size
    # Format: "[cortex] File size: 39.3 MB"
    file_size_match = re.search(r'\[cortex\] File size: ([\d.]+) MB', content)
    file_size_mb = float(file_size_match.group(1)) if file_size_match else None

    # Extract generation info (may not be explicitly timed)
    # Look for "Generated file:" line
    has_generation = '[cortex] Generated file:' in content

    # Check if benchmark succeeded
    success = 'Benchmark completed' in content or 'telemetry.ndjson' in content

    return {
        'channels': channels,
        'file_size_mb': file_size_mb,
        'has_generation': has_generation,
        'success': success
    }


def calculate_scaling_factor(results: List[Dict]) -> Tuple[float, float]:
    """
    Calculate theoretical vs actual scaling factor.

    Returns (theoretical_factor, actual_factor)
    """
    if len(results) < 2:
        return None, None

    # Sort by channel count
    results = sorted(results, key=lambda x: x['channels'])

    # Theoretical: File size should scale linearly with channels
    min_channels = results[0]['channels']
    max_channels = results[-1]['channels']
    min_size = results[0]['file_size_mb']
    max_size = results[-1]['file_size_mb']

    theoretical_factor = max_channels / min_channels
    actual_factor = max_size / min_size if min_size and max_size else None

    return theoretical_factor, actual_factor


def main():
    script_dir = Path(__file__).parent
    results_dir = script_dir / 'results'

    if not results_dir.exists():
        print("Error: Results directory not found. Run benchmarks first.")
        return 1

    # Parse all log files
    results = []
    for log_file in sorted(results_dir.glob('scalability_*.log')):
        result = parse_log_file(log_file)
        if result:
            results.append(result)

    if not results:
        print("Error: No valid results found.")
        return 1

    # Sort by channel count
    results = sorted(results, key=lambda x: x['channels'])

    # Print summary table
    print("=" * 80)
    print("  High-Channel Scalability Benchmark Results")
    print("=" * 80)
    print()
    print(f"{'Channels':<12} {'File Size (MB)':<18} {'Generation':<15} {'Status':<10}")
    print("-" * 80)

    for r in results:
        channels = r['channels']
        file_size = f"{r['file_size_mb']:.1f}" if r['file_size_mb'] else "N/A"
        generation = "✓" if r['has_generation'] else "✗"
        status = "✓ PASS" if r['success'] else "✗ FAIL"

        print(f"{channels:<12} {file_size:<18} {generation:<15} {status:<10}")

    print()

    # Calculate scaling
    theoretical, actual = calculate_scaling_factor(results)
    if theoretical and actual:
        print(f"Scaling Analysis:")
        print(f"  Theoretical factor: {theoretical:.2f}×")
        print(f"  Actual factor:      {actual:.2f}×")
        print(f"  Scaling linearity:  {(actual/theoretical)*100:.1f}%")
        print()

    # Check success rate
    success_count = sum(1 for r in results if r['success'])
    total_count = len(results)
    success_rate = (success_count / total_count) * 100

    print(f"Success Rate: {success_count}/{total_count} ({success_rate:.0f}%)")
    print()

    # Validation checks
    print("Validation Checks:")
    print()

    # Check 1: All benchmarks succeeded
    if success_rate == 100:
        print("  ✓ All benchmarks completed successfully")
    else:
        print(f"  ✗ {total_count - success_count} benchmark(s) failed")

    # Check 2: File sizes scale linearly
    if actual and theoretical:
        linearity = (actual / theoretical) * 100
        if 95 <= linearity <= 105:
            print(f"  ✓ File sizes scale linearly ({linearity:.1f}% of theoretical)")
        else:
            print(f"  ⚠ File size scaling deviation: {linearity:.1f}% of theoretical")

    # Check 3: High-channel mode activated (>512ch)
    high_channel_results = [r for r in results if r['channels'] > 512]
    if high_channel_results:
        high_channel_success = all(r['has_generation'] for r in high_channel_results)
        if high_channel_success:
            print(f"  ✓ High-channel mode (>512ch) working correctly")
        else:
            print(f"  ✗ High-channel mode issues detected")

    # Check 4: Maximum channel count achieved
    max_channels = max(r['channels'] for r in results)
    if max_channels >= 2048:
        print(f"  ✓ Successfully tested up to {max_channels} channels")
    else:
        print(f"  ⚠ Maximum channel count: {max_channels} (target: 2048)")

    print()
    print("=" * 80)

    # Save summary JSON
    summary_path = results_dir / 'summary.json'
    with open(summary_path, 'w') as f:
        json.dump({
            'results': results,
            'success_rate': success_rate,
            'theoretical_factor': theoretical,
            'actual_factor': actual,
            'max_channels': max_channels
        }, f, indent=2)

    print(f"Summary saved to: {summary_path}")
    print()

    return 0 if success_rate == 100 else 1


if __name__ == '__main__':
    exit(main())
