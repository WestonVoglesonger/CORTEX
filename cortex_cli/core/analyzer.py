"""Data analysis and visualization"""
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from pathlib import Path
from typing import List, Optional

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['font.size'] = 11

def _extract_kernel_name(file_path: Path) -> Optional[str]:
    """
    Extract kernel name from telemetry file path or filename

    Supports new structure:
    - kernel-data/<kernel>/telemetry.{csv,ndjson}

    Args:
        file_path: Path to telemetry file

    Returns:
        Kernel name or None if not found
    """
    # New structure: kernel name is parent directory
    # e.g., results/run-2025-11-10-001/kernel-data/bandpass_fir/telemetry.ndjson
    parent_dir = file_path.parent.name

    # Check if we're in the expected structure
    if file_path.parent.parent.name == "kernel-data":
        # Parent directory is the kernel name
        if parent_dir:
            return parent_dir

    print(f"Warning: Could not extract kernel name from path {file_path}")
    print(f"Expected structure: .../kernel-data/<kernel>/telemetry.*")
    return None

def load_telemetry(results_dir: str, prefer_format: str = 'ndjson') -> Optional[pd.DataFrame]:
    """
    Load all telemetry files from a results directory

    Prefers NDJSON over CSV by default for better structured data handling.

    Args:
        results_dir: Path to batch results directory
        prefer_format: Preferred format ('ndjson' or 'csv')

    Returns:
        DataFrame with all telemetry data, or None if no data found
    """
    results_path = Path(results_dir)

    if not results_path.exists():
        print(f"Error: Results directory not found: {results_dir}")
        return None

    # Find all telemetry files in new structure (kernel-data/<kernel>/telemetry.*)
    ndjson_files = list(results_path.glob("kernel-data/*/telemetry.ndjson"))
    csv_files = list(results_path.glob("kernel-data/*/telemetry.csv"))

    # Determine which files to use based on preference
    if prefer_format == 'ndjson' and ndjson_files:
        files_to_load = ndjson_files
        file_format = 'ndjson'
    elif prefer_format == 'csv' and csv_files:
        files_to_load = csv_files
        file_format = 'csv'
    elif ndjson_files:
        # Fallback: use NDJSON if available
        files_to_load = ndjson_files
        file_format = 'ndjson'
    elif csv_files:
        # Fallback: use CSV if available
        files_to_load = csv_files
        file_format = 'csv'
    else:
        # Check if directory has kernel-data structure
        kernel_data_dir = results_path / "kernel-data"
        if not kernel_data_dir.exists():
            print(f"Error: No kernel-data directory found in {results_dir}")
            print(f"Expected structure: {results_dir}/kernel-data/<kernel>/telemetry.*")
            print(f"Run 'cortex run --all' to generate results first")
        else:
            kernel_dirs = list(kernel_data_dir.glob("*"))
            if not kernel_dirs:
                print(f"Error: kernel-data directory exists but is empty")
            else:
                print(f"Error: Found {len(kernel_dirs)} kernel directories but no telemetry files")
                print(f"Directories found: {[d.name for d in kernel_dirs]}")
                print(f"This may indicate all kernel runs failed")
        return None

    print(f"Loading {len(files_to_load)} {file_format.upper()} telemetry file(s)...")

    # Load all files
    dataframes = []
    failed_count = 0
    for file_path in files_to_load:
        try:
            if file_format == 'ndjson':
                # NDJSON: one JSON object per line
                df = pd.read_json(file_path, lines=True)
            else:
                # CSV format
                df = pd.read_csv(file_path)

            # Extract kernel name
            kernel_name = _extract_kernel_name(file_path)

            # Set plugin name if not present or if it's "(unnamed)"
            if kernel_name:
                if 'plugin' not in df.columns:
                    df['plugin'] = kernel_name
                elif df['plugin'].iloc[0] == '(unnamed)' if len(df) > 0 else False:
                    df['plugin'] = kernel_name

            dataframes.append(df)
        except pd.errors.ParserError as e:
            failed_count += 1
            print(f"Warning: Malformed {file_format.upper()} in {file_path.name}: {e}")
        except FileNotFoundError:
            failed_count += 1
            print(f"Warning: File disappeared during loading: {file_path.name}")
        except ValueError as e:
            failed_count += 1
            print(f"Warning: Invalid data format in {file_path.name}: {e}")
        except Exception as e:
            failed_count += 1
            print(f"Warning: Unexpected error loading {file_path.name}: {e}")
            import traceback
            traceback.print_exc()

    if failed_count > 0:
        print(f"\nWarning: {failed_count}/{len(files_to_load)} files failed to load")

    if not dataframes:
        print("Error: No valid telemetry data found")
        return None

    # Combine all dataframes
    combined = pd.concat(dataframes, ignore_index=True)

    # Calculate latency if not present
    if 'latency_ns' not in combined.columns:
        combined['latency_ns'] = combined['end_ts_ns'] - combined['start_ts_ns']

    # Convert to microseconds for readability
    combined['latency_us'] = combined['latency_ns'] / 1000.0

    print(f"Loaded {len(combined)} windows from {combined['plugin'].nunique()} kernel(s)")

    return combined

def calculate_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate summary statistics per kernel"""
    # Filter out warmup windows
    df_filtered = df[df['warmup'] == 0].copy()

    stats = df_filtered.groupby('plugin').agg({
        'window_index': 'count',
        'latency_us': ['min', 'max', 'mean', 'std',
                       lambda x: x.quantile(0.50),
                       lambda x: x.quantile(0.95),
                       lambda x: x.quantile(0.99)],
        'deadline_missed': ['sum', 'mean']
    }).reset_index()

    # Flatten column names
    stats.columns = ['kernel', 'windows', 'lat_min', 'lat_max', 'lat_mean', 'lat_std',
                     'lat_p50', 'lat_p95', 'lat_p99', 'deadline_misses', 'miss_rate']

    # Calculate jitter
    stats['jitter_p95_p50'] = stats['lat_p95'] - stats['lat_p50']
    stats['jitter_p99_p50'] = stats['lat_p99'] - stats['lat_p50']

    # Convert miss rate to percentage
    stats['miss_rate_pct'] = stats['miss_rate'] * 100

    return stats

def plot_latency_comparison(df: pd.DataFrame, output_path: str, format: str = 'png'):
    """Generate latency comparison bar chart"""
    stats = calculate_statistics(df)

    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(stats))
    width = 0.25

    ax.bar(x - width, stats['lat_p50'], width, label='P50', alpha=0.8, color='#3498db')
    ax.bar(x, stats['lat_p95'], width, label='P95', alpha=0.8, color='#e74c3c')
    ax.bar(x + width, stats['lat_p99'], width, label='P99', alpha=0.8, color='#f39c12')

    ax.set_xlabel('Kernel', fontsize=12, fontweight='bold')
    ax.set_ylabel('Latency (µs)', fontsize=12, fontweight='bold')
    ax.set_title('Kernel Latency Comparison', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(stats['kernel'], rotation=45, ha='right')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    try:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved: {output_path}")
    except Exception as e:
        print(f"Error: Could not save plot to {output_path}: {e}")
        print("Tip: Try PNG format or install required backend")
    finally:
        plt.close()

def plot_deadline_misses(df: pd.DataFrame, output_path: str, format: str = 'png'):
    """Generate deadline miss rate comparison"""
    stats = calculate_statistics(df)

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ['#27ae60' if rate == 0 else '#e74c3c' for rate in stats['miss_rate_pct']]
    ax.bar(stats['kernel'], stats['miss_rate_pct'], alpha=0.8, color=colors)

    ax.set_xlabel('Kernel', fontsize=12, fontweight='bold')
    ax.set_ylabel('Deadline Miss Rate (%)', fontsize=12, fontweight='bold')
    ax.set_title('Deadline Miss Rate by Kernel', fontsize=14, fontweight='bold')
    plt.xticks(rotation=45, ha='right')
    ax.grid(axis='y', alpha=0.3)

    # Set y-axis limit
    max_rate = stats['miss_rate_pct'].max()
    ax.set_ylim([0, max(max_rate * 1.2, 1)])

    plt.tight_layout()
    try:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved: {output_path}")
    except Exception as e:
        print(f"Error: Could not save plot to {output_path}: {e}")
        print("Tip: Try PNG format or install required backend")
    finally:
        plt.close()

def plot_cdf_overlay(df: pd.DataFrame, output_path: str, format: str = 'png'):
    """Generate CDF overlay plot for all kernels"""
    df_filtered = df[df['warmup'] == 0].copy()

    fig, ax = plt.subplots(figsize=(10, 6))

    kernels = df_filtered['plugin'].unique()
    colors = plt.cm.tab10(np.linspace(0, 1, len(kernels)))

    for kernel, color in zip(kernels, colors):
        kernel_data = df_filtered[df_filtered['plugin'] == kernel]['latency_us']
        sorted_data = np.sort(kernel_data)
        cumulative = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
        ax.plot(sorted_data, cumulative, label=kernel, linewidth=2, color=color)

    ax.set_xlabel('Latency (µs)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Cumulative Probability', fontsize=12, fontweight='bold')
    ax.set_title('Latency CDF - All Kernels', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    try:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved: {output_path}")
    except Exception as e:
        print(f"Error: Could not save plot to {output_path}: {e}")
        print("Tip: Try PNG format or install required backend")
    finally:
        plt.close()

def plot_throughput_comparison(df: pd.DataFrame, output_path: str, format: str = 'png'):
    """Generate throughput comparison"""
    df_filtered = df[df['warmup'] == 0].copy()

    # Calculate throughput (windows per second)
    # Fs/H gives the theoretical throughput
    if 'Fs' in df_filtered.columns and 'H' in df_filtered.columns:
        throughput = df_filtered.groupby('plugin').apply(
            lambda x: x['Fs'].iloc[0] / x['H'].iloc[0] if len(x) > 0 else 0,
            include_groups=False
        ).reset_index(name='throughput')
    else:
        print("Warning: Could not calculate throughput (missing Fs/H columns)")
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(throughput['plugin'], throughput['throughput'], alpha=0.8, color='#3498db')

    ax.set_xlabel('Kernel', fontsize=12, fontweight='bold')
    ax.set_ylabel('Throughput (windows/sec)', fontsize=12, fontweight='bold')
    ax.set_title('Kernel Throughput Comparison', fontsize=14, fontweight='bold')
    plt.xticks(rotation=45, ha='right')
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    try:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved: {output_path}")
    except Exception as e:
        print(f"Error: Could not save plot to {output_path}: {e}")
        print("Tip: Try PNG format or install required backend")
    finally:
        plt.close()

def _calculate_deadline_from_config(config_path: str = "configs/cortex.yaml") -> float:
    """Extract deadline from config or calculate from data"""
    try:
        import yaml
        with open(config_path, 'r') as f:
            cfg = yaml.safe_load(f)

        # Get sample rate from dataset config
        sample_rate = cfg.get('dataset', {}).get('sample_rate_hz', 160)

        # Hop is derived as window_length / 2 in harness
        # Window length comes from kernel spec (default 160)
        # For now, use the documented calculation: hop=80, fs=160 -> 0.5s
        # TODO: Parse actual values from kernel spec.yaml files
        hop_samples = 80  # Default from harness

        deadline_sec = hop_samples / sample_rate
        return deadline_sec * 1000  # Convert to milliseconds
    except Exception:
        return 500.0  # Fallback to documented default

def generate_summary_table(df: pd.DataFrame, output_path: str):
    """Generate markdown summary table"""
    stats = calculate_statistics(df)

    # Round for readability
    stats_rounded = stats.round(2)

    with open(output_path, 'w') as f:
        f.write("# CORTEX Benchmark Results Summary\n\n")
        f.write(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## Overall Statistics\n\n")
        f.write("| Kernel | Windows | P50 (µs) | P95 (µs) | P99 (µs) | Jitter P95-P50 (µs) | Deadline Misses | Miss Rate (%) |\n")
        f.write("|--------|---------|----------|----------|----------|---------------------|-----------------|---------------|\n")

        for _, row in stats_rounded.iterrows():
            f.write(f"| {row['kernel']} | {int(row['windows'])} | "
                   f"{row['lat_p50']:.2f} | {row['lat_p95']:.2f} | {row['lat_p99']:.2f} | "
                   f"{row['jitter_p95_p50']:.2f} | {int(row['deadline_misses'])} | "
                   f"{row['miss_rate_pct']:.2f} |\n")

        f.write("\n## Interpretation\n\n")
        f.write("- **P50/P95/P99**: 50th/95th/99th percentile latencies\n")
        f.write("- **Jitter**: Difference between P95 and P50 (indicates timing variance)\n")
        deadline_ms = _calculate_deadline_from_config()
        f.write(f"- **Deadline Misses**: Number of windows that exceeded the {deadline_ms:.0f}ms deadline\n")
        f.write("- **Miss Rate**: Percentage of windows that missed the deadline\n")

    print(f"✓ Saved: {output_path}")

def run_full_analysis(
    results_dir: str,
    output_dir: str = "results/analysis",
    plots: List[str] = None,
    format: str = 'png',
    telemetry_format: str = 'ndjson'
) -> bool:
    """
    Run complete analysis pipeline

    Args:
        results_dir: Path to batch results directory
        output_dir: Where to save analysis outputs
        plots: List of plots to generate (default: all)
        format: Output format for plots (png, pdf, svg)
        telemetry_format: Preferred telemetry format ('ndjson' or 'csv')

    Returns:
        True if successful, False otherwise
    """
    # Load data
    df = load_telemetry(results_dir, prefer_format=telemetry_format)
    if df is None:
        return False

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Determine which plots to generate
    if plots is None or 'all' in plots:
        plots = ['latency', 'deadline', 'throughput', 'cdf']

    print(f"\nGenerating analysis plots...")

    # Generate plots
    if 'latency' in plots:
        plot_latency_comparison(df, str(output_path / f'latency_comparison.{format}'), format)

    if 'deadline' in plots:
        plot_deadline_misses(df, str(output_path / f'deadline_miss_rate.{format}'), format)

    if 'throughput' in plots:
        plot_throughput_comparison(df, str(output_path / f'throughput_comparison.{format}'), format)

    if 'cdf' in plots:
        plot_cdf_overlay(df, str(output_path / f'latency_cdf_overlay.{format}'), format)

    # Generate summary table
    generate_summary_table(df, str(output_path / 'SUMMARY.md'))

    print(f"\n✓ Analysis complete!")
    print(f"Output directory: {output_dir}")

    return True
