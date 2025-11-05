"""Analyze results command"""
from cortex_cli.core.analyzer import run_full_analysis

def setup_parser(parser):
    """Setup argument parser for analyze command"""
    parser.add_argument(
        'results_dir',
        help='Results directory to analyze (e.g., results/batch_1234567890)'
    )
    parser.add_argument(
        '--output', '-o',
        default='results/analysis',
        help='Output directory for plots and summary (default: results/analysis)'
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
    print(f"\nResults directory: {args.results_dir}")
    print(f"Output directory: {args.output}")
    print(f"Plot format: {args.format}")
    print(f"Telemetry format: {args.telemetry_format}")
    print()

    success = run_full_analysis(
        args.results_dir,
        output_dir=args.output,
        plots=args.plots,
        format=args.format,
        telemetry_format=args.telemetry_format
    )

    if success:
        print("\n" + "=" * 80)
        print("Analysis Summary")
        print("=" * 80)
        print(f"Plots saved to: {args.output}/")
        print(f"Summary table: {args.output}/SUMMARY.md")
        print("\nView summary:")
        print(f"  cat {args.output}/SUMMARY.md")
        print("=" * 80)
        return 0
    else:
        return 1
