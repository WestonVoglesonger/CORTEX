"""Analyze results command"""
from cortex_cli.core.analyzer import run_full_analysis
from cortex_cli.core.paths import get_most_recent_run, get_run_directory, get_analysis_dir

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
        '--format', '-f',
        choices=['png', 'pdf', 'svg'],
        default='png',
        help='Output format for plots (default: png)'
    )
    parser.add_argument(
        '--plots', '-p',
        nargs='+',
        choices=['latency', 'deadline', 'throughput', 'cdf', 'all'],
        default=['all'],
        help='Which plots to generate (default: all)'
    )
    parser.add_argument(
        '--telemetry-format', '-t',
        choices=['ndjson', 'csv', 'auto'],
        default='ndjson',
        help='Preferred telemetry format to load (default: ndjson)'
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
    print(f"Plot format: {args.format}")
    print(f"Telemetry format: {args.telemetry_format}")
    print()

    success = run_full_analysis(
        str(run_dir),
        output_dir=output_dir,
        plots=args.plots,
        format=args.format,
        telemetry_format=args.telemetry_format
    )

    if success:
        print("\n" + "=" * 80)
        print("Analysis Summary")
        print("=" * 80)
        print(f"Plots saved to: {output_dir}/")
        print(f"Summary table: {output_dir}/SUMMARY.md")
        print("\nView summary:")
        print(f"  cat {output_dir}/SUMMARY.md")
        print("=" * 80)
        return 0
    else:
        return 1
