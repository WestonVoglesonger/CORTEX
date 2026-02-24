"""Compare two benchmark runs with statistical analysis."""
from cortex.utils.analyzer import TelemetryAnalyzer
from cortex.utils.paths import get_run_directory
from cortex.core import ConsoleLogger, RealFileSystemService
from pathlib import Path
import json


def setup_parser(parser):
    """Setup argument parser for compare command"""
    parser.add_argument(
        '--baseline',
        required=True,
        help='Baseline run directory or run name'
    )
    parser.add_argument(
        '--candidate',
        required=True,
        help='Candidate run directory or run name'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output directory for comparison report (default: results/comparisons/)'
    )
    parser.add_argument(
        '--alpha',
        type=float,
        default=0.05,
        help='Significance level for statistical tests (default: 0.05)'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['png', 'pdf', 'svg'],
        default='png',
        help='Output format for plots (default: png)'
    )
    parser.add_argument(
        '--telemetry-format', '-t',
        choices=['ndjson', 'csv', 'auto'],
        default='ndjson',
        help='Preferred telemetry format to load (default: ndjson)'
    )


def _resolve_run_dir(name_or_path):
    """Resolve a run name or directory path to an actual directory."""
    p = Path(name_or_path)
    if p.is_dir():
        return p
    # Try as run name
    run_dir = get_run_directory(name_or_path)
    if run_dir.exists():
        return run_dir
    return None


def execute(args):
    """Execute compare command."""
    print("=" * 80)
    print("CORTEX Run Comparison")
    print("=" * 80)
    print()

    # Resolve directories
    baseline_dir = _resolve_run_dir(args.baseline)
    if baseline_dir is None:
        print(f"Error: Baseline not found: {args.baseline}")
        return 1

    candidate_dir = _resolve_run_dir(args.candidate)
    if candidate_dir is None:
        print(f"Error: Candidate not found: {args.candidate}")
        return 1

    print(f"Baseline:  {baseline_dir}")
    print(f"Candidate: {candidate_dir}")
    print()

    # Determine output directory
    if args.output:
        output_dir = args.output
    else:
        output_dir = "results/comparisons"

    # Create analyzer
    filesystem = RealFileSystemService()
    logger = ConsoleLogger()
    analyzer = TelemetryAnalyzer(filesystem=filesystem, logger=logger)

    # Load both runs
    df_baseline = analyzer.load_telemetry(str(baseline_dir), prefer_format=args.telemetry_format)
    baseline_info = dict(analyzer.system_info)
    analyzer.system_info = {}  # Reset for candidate

    df_candidate = analyzer.load_telemetry(str(candidate_dir), prefer_format=args.telemetry_format)

    if df_baseline is None or df_baseline.empty:
        print("Error: No telemetry data in baseline run")
        return 1
    if df_candidate is None or df_candidate.empty:
        print("Error: No telemetry data in candidate run")
        return 1

    # Run comparison
    comparison = analyzer.compare_runs(df_baseline, df_candidate, alpha=args.alpha)
    if comparison is None or comparison.empty:
        print("Error: No common kernels found between runs")
        return 1

    # Generate output directory
    filesystem.mkdir(Path(output_dir), parents=True, exist_ok=True)

    # Generate CDF overlay
    try:
        _generate_cdf_overlay(analyzer, df_baseline, df_candidate,
                              f"{output_dir}/cdf_comparison.{args.format}", args.format)
    except Exception as e:
        logger.warning(f"Failed to generate CDF overlay: {e}")

    # Generate comparison bar chart
    try:
        _generate_comparison_chart(comparison, f"{output_dir}/latency_comparison.{args.format}",
                                   args.format, filesystem)
    except Exception as e:
        logger.warning(f"Failed to generate comparison chart: {e}")

    # Generate markdown report
    report_path = f"{output_dir}/comparison_report.md"
    _generate_markdown_report(comparison, report_path, args, baseline_dir, candidate_dir, filesystem)

    # Print summary to stdout
    print("Comparison Results:")
    print("-" * 90)
    print(f"{'Kernel':<20} {'Baseline (us)':>14} {'Candidate (us)':>14} {'Change':>10} {'p-value':>10} {'Sig?':>6}")
    print("-" * 90)

    for _, row in comparison.iterrows():
        sig = "YES" if row['significant'] else "no"
        change_str = f"{row['relative_change_pct']:+.2f}%"
        p_str = f"{row['p_value']:.4f}" if row['p_value'] is not None else "N/A"
        print(f"{row['kernel']:<20} {row['baseline_mean']:>14.2f} {row['candidate_mean']:>14.2f} "
              f"{change_str:>10} {p_str:>10} {sig:>6}")

    print("-" * 90)
    print(f"\nReport saved: {report_path}")
    print(f"Plots saved:  {output_dir}/")
    print("=" * 80)

    return 0


def _generate_cdf_overlay(analyzer, df_baseline, df_candidate, output_path, fmt):
    """Generate overlaid CDF comparing both runs."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    analyzer.fs.mkdir(Path(output_path).parent, parents=True, exist_ok=True)

    df_b = df_baseline[df_baseline['warmup'] == 0]
    df_c = df_candidate[df_candidate['warmup'] == 0]

    # Find common kernels
    common = set(df_b['plugin'].unique()) & set(df_c['plugin'].unique())
    if not common:
        return

    fig, ax = plt.subplots(figsize=(12, 7))
    colors = plt.cm.tab10(range(len(common)))

    for kernel, color in zip(sorted(common), colors):
        for df, label_suffix, ls in [(df_b, 'baseline', '-'), (df_c, 'candidate', '--')]:
            data = np.sort(df[df['plugin'] == kernel]['latency_us'].values)
            cdf = np.arange(1, len(data) + 1) / len(data)
            ax.plot(data, cdf, label=f"{kernel} ({label_suffix})", color=color, linestyle=ls, linewidth=2)

    ax.set_xscale('log')
    ax.set_xlabel('Latency (us, log scale)')
    ax.set_ylabel('Cumulative Probability')
    ax.set_title('CDF Comparison: Baseline vs Candidate')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, which='both')
    plt.tight_layout()

    try:
        plt.savefig(output_path, dpi=300, bbox_inches='tight', format=fmt)
    finally:
        plt.close('all')


def _generate_comparison_chart(comparison, output_path, fmt, filesystem):
    """Generate grouped bar chart comparing mean latencies."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    filesystem.mkdir(Path(output_path).parent, parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 6))

    kernels = comparison['kernel'].values
    x = np.arange(len(kernels))
    width = 0.35

    ax.bar(x - width/2, comparison['baseline_mean'], width, label='Baseline', color='steelblue', alpha=0.8)
    ax.bar(x + width/2, comparison['candidate_mean'], width, label='Candidate', color='coral', alpha=0.8)

    ax.set_xlabel('Kernel')
    ax.set_ylabel('Mean Latency (us)')
    ax.set_title('Latency Comparison: Baseline vs Candidate')
    ax.set_xticks(x)
    ax.set_xticklabels(kernels, rotation=45, ha='right')
    ax.legend()
    plt.tight_layout()

    try:
        plt.savefig(output_path, dpi=300, bbox_inches='tight', format=fmt)
    finally:
        plt.close('all')


def _generate_markdown_report(comparison, output_path, args, baseline_dir, candidate_dir, filesystem):
    """Generate markdown comparison report."""
    import pandas as pd

    lines = []
    lines.append("# CORTEX Run Comparison Report\n\n")
    lines.append(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    lines.append(f"- **Baseline**: `{baseline_dir}`\n")
    lines.append(f"- **Candidate**: `{candidate_dir}`\n")
    lines.append(f"- **Significance level**: {args.alpha}\n\n")

    lines.append("## Results\n\n")
    lines.append("| Kernel | Baseline Mean (us) | Candidate Mean (us) | Change % | Cohen's d | p-value | Significant |\n")
    lines.append("|--------|-------------------:|--------------------:|---------:|----------:|--------:|:-----------:|\n")

    for _, row in comparison.iterrows():
        sig = "**YES**" if row['significant'] else "no"
        p_str = f"{row['p_value']:.4f}" if row['p_value'] is not None else "N/A"
        d_str = f"{row['cohens_d']:.3f}" if row['cohens_d'] is not None else "N/A"
        lines.append(
            f"| {row['kernel']} "
            f"| {row['baseline_mean']:.2f} "
            f"| {row['candidate_mean']:.2f} "
            f"| {row['relative_change_pct']:+.2f} "
            f"| {d_str} "
            f"| {p_str} "
            f"| {sig} |\n"
        )

    lines.append("\n## Interpretation\n\n")
    lines.append("- **Change %**: Positive = candidate is slower, Negative = candidate is faster\n")
    lines.append("- **Cohen's d**: Effect size (0.2=small, 0.5=medium, 0.8=large)\n")
    lines.append(f"- **Significant**: p-value < {args.alpha} (Welch's t-test)\n")

    filesystem.write_file(output_path, ''.join(lines))
