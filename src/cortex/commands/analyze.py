"""Analyze results command"""
from pathlib import Path
from cortex.utils.analyzer import TelemetryAnalyzer, format_mean_ci
from cortex.utils.paths import get_most_recent_run, get_run_directory, get_analysis_dir
from cortex.core import ConsoleLogger, RealFileSystemService

def setup_parser(parser):
    """Setup argument parser for analyze command"""
    parser.add_argument(
        '--run-name',
        help='Name of run to analyze (default: most recent run)'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output directory for plots and summary (default: <run_dir>/analysis)'
    )
    parser.add_argument(
        '--plots', '-p',
        nargs='+',
        choices=['latency', 'deadline', 'throughput', 'cdf', 'all'],
        default=['all'],
        help='Which plots to generate (default: all)'
    )

def execute(args):
    """Execute analyze command"""
    print("=" * 80)
    print("CORTEX Results Analysis")
    print("=" * 80)
    print()

    # Determine which run to analyze
    if args.run_name:
        run_name = args.run_name
        print(f"Analyzing run: {run_name}")
    else:
        run_name = get_most_recent_run()
        if not run_name:
            print("Error: No runs found in results/")
            print("Run 'cortex run --all' first to generate results")
            return 1
        print(f"Analyzing most recent run: {run_name}")

    # Get run directory
    run_dir = get_run_directory(run_name)
    if not run_dir.exists():
        print(f"Error: Run directory not found: {run_dir}")
        return 1

    # Determine output directory
    if args.output:
        output_dir = args.output
    else:
        output_dir = str(get_analysis_dir(run_name))

    print(f"Results directory: {run_dir}")
    print(f"Output directory: {output_dir}")
    print()

    # Create analyzer with production dependencies
    filesystem = RealFileSystemService()
    analyzer = TelemetryAnalyzer(
        filesystem=filesystem,
        logger=ConsoleLogger()
    )

    success = analyzer.run_full_analysis(
        str(run_dir),
        output_dir=output_dir,
        plots=args.plots,
        format='png',
        telemetry_format='ndjson'
    )

    # Detect and analyze pipeline subdirectories
    pipe_dirs = sorted(Path(run_dir).glob("pipeline-*"))
    pipe_success = False
    if pipe_dirs:
        print(f"\nDetected {len(pipe_dirs)} pipeline subdirectory(ies)")
        for pipe_dir in pipe_dirs:
            if not pipe_dir.is_dir():
                continue
            pipe_analyzer = TelemetryAnalyzer(
                filesystem=filesystem,
                logger=ConsoleLogger()
            )
            pipe_output = str(pipe_dir / "analysis")
            ok = pipe_analyzer.run_full_analysis(
                str(pipe_dir),
                output_dir=pipe_output,
                plots=args.plots,
                format='png',
                telemetry_format='ndjson'
            )
            status = "OK" if ok else "no data"
            print(f"  {pipe_dir.name}: {status}")
            if ok:
                pipe_success = True

    if success or pipe_success:
        print("\n" + "=" * 80)
        print("Analysis Summary")
        print("=" * 80)
        if success:
            # Print quick stats table to console (reuse cached stats from run_full_analysis)
            try:
                stats = getattr(analyzer, 'last_stats', None)
                if stats is not None:
                    has_ci = ('latency_us_mean_ci_half' in stats.columns
                              and stats['latency_us_mean_ci_half'].notna().any())
                    mean_hdr = "Mean ± 95% CI" if has_ci else "Mean"
                    print(f"\n{'Kernel':<18} {mean_hdr:>24} {'P50':>10} {'P95':>10} {'P99':>10} {'N':>8}")
                    print("-" * 84)
                    for kernel_name in stats.index:
                        row = stats.loc[kernel_name]
                        mean_str = format_mean_ci(
                            row.get('latency_us_mean', float('nan')),
                            row.get('latency_us_mean_ci_lower', float('nan')) if has_ci else float('nan'),
                            row.get('latency_us_mean_ci_upper', float('nan')) if has_ci else float('nan'),
                            ci_pct=row.get('latency_us_mean_ci_pct', float('nan')) if has_ci else None,
                        )
                        p50 = f"{row.get('latency_us_median', float('nan')):.1f}"
                        p95 = f"{row.get('latency_us_p95', float('nan')):.1f}"
                        p99 = f"{row.get('latency_us_p99', float('nan')):.1f}"
                        n = int(row.get('sample_count', 0))
                        print(f"{kernel_name:<18} {mean_str:>24} {p50:>10} {p95:>10} {p99:>10} {n:>8}")
                    print()
            except (KeyError, ValueError, AttributeError) as e:
                print(f"  (Console stats unavailable: {e})")
            print(f"Plots saved to: {output_dir}/")
            print(f"Summary table: {output_dir}/SUMMARY.md")
            print("\nView summary:")
            print(f"  cat {output_dir}/SUMMARY.md")
        if pipe_success:
            for pipe_dir in pipe_dirs:
                pipe_analysis = pipe_dir / "analysis"
                if (pipe_analysis / "SUMMARY.md").exists():
                    print(f"\nPipeline summary: {pipe_analysis}/SUMMARY.md")
        print("=" * 80)
        return 0
    else:
        return 1
